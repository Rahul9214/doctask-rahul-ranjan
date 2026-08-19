import io
import json
from pathlib import Path

from fastapi import UploadFile
from starlette.datastructures import Headers

from app.examine_service import ExamineService
from app.model_gateway import DeterministicModelAdapter, ModelAdapter
from app.models import Corpus
from app.parsers import SourceFormat
from app.services import Phase02Service
from app.understand_service import UnderstandService

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
