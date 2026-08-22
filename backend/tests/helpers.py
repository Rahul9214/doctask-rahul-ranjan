import io
import json
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Literal
from uuid import UUID

from fastapi import UploadFile
from starlette.datastructures import Headers

from app.examine_service import ExamineService
from app.incremental_service import IncrementalService
from app.model_gateway import (
    BlockContext,
    ClassificationBatch,
    DeterministicModelAdapter,
    ExtractionBatch,
    ModelAdapter,
)
from app.models import Corpus
from app.operation_ledger import default_identity_versions
from app.parsers import SourceFormat
from app.publication_service import PublicationService
from app.review_service import ReviewService
from app.schemas import ReviewDecisionCreate
from app.services import IngestionResult, Phase02Service
from app.understand_service import UnderstandService
from app.watcher import WatcherService
from app.workflow_service import WorkflowService

MEDIA_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "markdown": "text/markdown",
    "txt": "text/plain",
}


def fixture_upload(path: Path, source_format: SourceFormat) -> UploadFile:
    return UploadFile(
        io.BytesIO(path.read_bytes()),
        filename=path.name,
        headers=Headers({"content-type": MEDIA_TYPES[source_format]}),
    )


def bytes_upload(
    content: bytes,
    filename: str,
    source_format: SourceFormat,
) -> UploadFile:
    return UploadFile(
        io.BytesIO(content),
        filename=filename,
        headers=Headers({"content-type": MEDIA_TYPES[source_format]}),
    )


async def ingest_text(
    service: Phase02Service,
    corpus_id: UUID,
    logical_name: str,
    text: str,
    *,
    filename: str = "note.txt",
) -> IngestionResult:
    return await service.ingest(
        corpus_id=corpus_id,
        logical_name=logical_name,
        declared_format="txt",
        upload=bytes_upload(text.encode("utf-8"), filename, "txt"),
    )


def assert_controlled_error(
    error: object,
    *,
    code: str,
    leaked: str | None = None,
) -> None:
    detail = str(getattr(error, "detail", error))
    action = str(getattr(error, "action", ""))
    assert getattr(error, "code", None) == code
    combined = f"{detail}\n{action}".casefold()
    assert "traceback" not in combined
    assert "traceback (most recent call last)" not in combined
    if leaked:
        assert leaked not in detail
        assert leaked not in action


async def ingest_corpus(service: Phase02Service, corpus_dir: Path) -> Corpus:
    manifest = json.loads((corpus_dir / "manifest.json").read_text(encoding="utf-8"))
    corpus = await service.create_corpus(
        name=str(manifest["name"]),
        domain=str(manifest["domain"]),
        declared_formats=list(manifest["declared_formats"]),
    )
    for document in manifest["documents"]:
        await service.ingest(
            corpus_id=corpus.id,
            logical_name=str(document["logical_name"]),
            declared_format=str(document["declared_format"]),  # type: ignore[arg-type]
            upload=fixture_upload(
                corpus_dir / str(document["filename"]),
                str(document["declared_format"]),  # type: ignore[arg-type]
            ),
        )
    return corpus


def make_understand(
    phase02: Phase02Service,
    adapter: ModelAdapter | None = None,
) -> UnderstandService:
    return UnderstandService(
        phase02.session_factory,
        phase02,
        adapter or DeterministicModelAdapter(),
    )


def make_examine(
    phase02: Phase02Service,
    adapter: ModelAdapter | None = None,
    understand: UnderstandService | None = None,
) -> ExamineService:
    resolved = understand or make_understand(phase02, adapter)
    return ExamineService(phase02.session_factory, phase02, resolved)


def make_review(
    phase02: Phase02Service,
    adapter: ModelAdapter | None = None,
    examine: ExamineService | None = None,
) -> ReviewService:
    resolved = examine or make_examine(phase02, adapter)
    return ReviewService(phase02.session_factory, phase02, resolved)


def make_workflow(
    phase02: Phase02Service,
    adapter: ModelAdapter | None = None,
    review: ReviewService | None = None,
) -> WorkflowService:
    resolved = review or make_review(phase02, adapter)
    database_url = os.environ["TEST_DATABASE_URL"]
    return WorkflowService(
        phase02.session_factory,
        phase02,
        resolved.examine,
        resolved,
        adapter or DeterministicModelAdapter(),
        database_url=database_url,
    )


def make_incremental(
    phase02: Phase02Service,
    adapter: ModelAdapter | None = None,
    review: ReviewService | None = None,
) -> IncrementalService:
    resolved = review or make_review(phase02, adapter)
    return IncrementalService(
        phase02.session_factory,
        phase02,
        resolved.examine.understand,
        resolved.examine,
        resolved,
        adapter or DeterministicModelAdapter(),
    )


async def prepare_incremental_corpus(
    phase02: Phase02Service,
    corpus_dir: Path,
    adapter: ModelAdapter | None = None,
) -> tuple[Corpus, IncrementalService]:
    corpus = await ingest_corpus(phase02, corpus_dir)
    incremental = make_incremental(phase02, adapter)
    analysis = await incremental.understand.create_run(corpus.id)
    examination = await incremental.examine.create_run(corpus.id, analysis.id)
    session, _created = await incremental.review.create_session(corpus.id, examination.id)
    await complete_required_review(incremental.review, corpus.id, session.id)
    await incremental.create_baseline_revision(
        corpus.id,
        analysis_run_id=analysis.id,
        examination_run_id=examination.id,
        review_session_id=session.id,
    )
    return corpus, incremental


def make_watcher(
    phase02: Phase02Service,
    inbox_path: Path,
    *,
    adapter: ModelAdapter | None = None,
    incremental: IncrementalService | None = None,
    stable_polls: int = 2,
) -> WatcherService:
    resolved = incremental or make_incremental(phase02, adapter)
    return WatcherService(
        phase02.session_factory,
        phase02,
        resolved,
        inbox_path=inbox_path,
        poll_seconds=0.01,
        stable_polls=stable_polls,
    )


class CountingModelAdapter:
    """Deterministic adapter with in-provider retry/attempt instrumentation."""

    mode: Literal["deterministic", "openai"] = "deterministic"
    model_name = "deterministic-local"

    def __init__(self, *, fail_classify_attempts: int = 0) -> None:
        self.inner = DeterministicModelAdapter()
        self.fail_classify_attempts = fail_classify_attempts
        self.classify_operations = 0
        self.classify_attempts = 0
        self.extract_operations = 0
        self.extract_attempts = 0

    async def classify_blocks(self, blocks: Sequence[BlockContext]) -> ClassificationBatch:
        self.classify_operations += 1
        attempts = 0
        while True:
            attempts += 1
            self.classify_attempts += 1
            if attempts <= self.fail_classify_attempts:
                continue
            batch = await self.inner.classify_blocks(blocks)
            usage = batch.usage.model_copy(update={"operation_count": 1, "attempt_count": attempts})
            return batch.model_copy(update={"usage": usage})

    async def extract_facts(self, blocks: Sequence[BlockContext]) -> ExtractionBatch:
        self.extract_operations += 1
        self.extract_attempts += 1
        batch = await self.inner.extract_facts(blocks)
        usage = batch.usage.model_copy(update={"operation_count": 1, "attempt_count": 1})
        return batch.model_copy(update={"usage": usage})


def make_publication(
    phase02: Phase02Service,
    adapter: ModelAdapter | None = None,
    review: ReviewService | None = None,
) -> PublicationService:
    resolved = review or make_review(phase02, adapter)
    return PublicationService(
        phase02.session_factory,
        phase02,
        resolved,
        resolved.examine,
    )


async def mixed_review_then_complete(
    review: ReviewService,
    corpus_id: UUID,
    session_id: UUID,
) -> tuple[str, str, str]:
    """Approve one required item, reject one, edit one, approve remaining required items."""

    items = await review.list_items(corpus_id, session_id)
    required = [item for item in items if item.review_required]
    approve_id = required[0].rule_id if required else ""
    reject_id = required[1].rule_id if len(required) > 1 else ""
    edit_id = required[-1].rule_id if len(required) > 2 else ""
    if required:
        await review.record_decision(
            corpus_id,
            session_id,
            required[0].id,
            ReviewDecisionCreate(action="approve", decision_source="api", comment="Approve"),
        )
    if len(required) > 1:
        await review.record_decision(
            corpus_id,
            session_id,
            required[1].id,
            ReviewDecisionCreate(action="reject", decision_source="api", comment="Reject"),
        )
    if len(required) > 2:
        await review.record_decision(
            corpus_id,
            session_id,
            required[-1].id,
            ReviewDecisionCreate(
                action="edit",
                edited_content=(
                    "Reviewer-authored restatement distinguished from grounded evidence."
                ),
                reviewer_authored_acknowledged=True,
                decision_source="api",
                comment="Edit",
            ),
        )
    remaining = await review.list_items(corpus_id, session_id)
    for item in remaining:
        if item.review_required and item.review_status == "pending":
            await review.record_decision(
                corpus_id,
                session_id,
                item.id,
                ReviewDecisionCreate(action="approve", decision_source="api"),
            )
    await review.complete_session(corpus_id, session_id)
    return approve_id, reject_id, edit_id


async def complete_required_review(
    review: ReviewService,
    corpus_id: UUID,
    session_id: UUID,
) -> None:
    items = await review.list_items(corpus_id, session_id)
    for item in items:
        if item.review_required and item.review_status == "pending":
            await review.record_decision(
                corpus_id,
                session_id,
                item.id,
                ReviewDecisionCreate(action="approve", decision_source="api"),
            )
    await review.complete_session(corpus_id, session_id)


def ledger_identity(run: object | None = None) -> dict[str, str]:
    versions = default_identity_versions()
    configuration = getattr(run, "configuration", None)
    if isinstance(configuration, dict):
        for field in (
            "taxonomy_version",
            "understand_graph_version",
            "prompt_config_version",
            "workflow_graph_version",
        ):
            value = configuration.get(field)
            if value is not None:
                versions[field] = str(value)
    graph_version = getattr(run, "graph_version", None)
    if isinstance(graph_version, str) and graph_version:
        versions["workflow_graph_version"] = graph_version
    return versions
