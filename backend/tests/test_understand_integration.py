from collections.abc import Sequence
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from fastapi import UploadFile
from helpers import ingest_corpus, make_understand
from sqlalchemy.exc import IntegrityError
from starlette.datastructures import Headers

from app.errors import ModelError, NotFoundError
from app.model_gateway import (
    BlockClassification,
    BlockContext,
    ClassificationBatch,
    DeterministicModelAdapter,
    ExtractionBatch,
    OpenAICompatibleAdapter,
    ProposedFact,
    zero_usage,
)
from app.models import AnalysisRun, Contradiction, Corpus, Fact, SourceBlock, SourceVersion
from app.schemas import CitationRequest, SearchRequest
from app.services import Phase02Service, SearchMatch
from app.storage import LocalFileStorage
from app.taxonomy import GRAPH_VERSION, TAXONOMY_VERSION, derive_assertions
from app.understand_graph import CANONICAL_STAGES


@pytest.mark.integration
async def test_aurora_understand_grounds_facts_contradiction_unknown_and_injection(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, _storage = phase02_service
    corpus = await ingest_corpus(phase02, corpus_fixtures / "aurora-control-hub")
    understand = make_understand(phase02)
    run = await understand.create_run(corpus.id)
    understanding = await understand.get_understanding(corpus.id, run.id)

    assert run.status == "completed"
    assert run.model_provider_mode == "deterministic"
    assert understanding.no_findings is False
    supported = [fact for fact in understanding.facts if fact.support_status == "supported"]
    assert supported
    assert all(fact.citation is not None for fact in supported)
    production = [fact for fact in supported if fact.subject_key == "production_readiness"]
    values = {fact.normalized_value for fact in production}
    assert "2026-10-30" in values
    assert "2026-11-14" in values
    assert understanding.contradictions
    contradiction = understanding.contradictions[0]
    assert contradiction.contradiction_type == "conflicting_dates"
    assert contradiction.fact_a.citation is not None
    assert contradiction.fact_b.citation is not None
    assert contradiction.fact_a.normalized_value != contradiction.fact_b.normalized_value

    budget = [fact for fact in understanding.facts if fact.subject_key == "budget_owner"]
    assert budget
    assert budget[0].support_status == "unknown"
    assert budget[0].normalized_value == "INSUFFICIENT_EVIDENCE"
    assert budget[0].citation is None

    injection = [
        item for item in understanding.classifications if item.category == "untrusted_instruction"
    ]
    assert injection
    assert all(item.relevant is False for item in injection)
    assert all(
        "compliant" not in fact.normalized_value.casefold() or fact.support_status != "supported"
        for fact in understanding.facts
    )
    assert all(event.estimated_cost_usd == 0.0 for event in understanding.stage_events)
    assert all(event.cost_basis == "zero_deterministic" for event in understanding.stage_events)
    assert {event.stage_name for event in understanding.stage_events} >= set(CANONICAL_STAGES)
    assert understanding.retrieval_mode in {"retrieved", "fallback_full_corpus"}
    skipped = [event for event in understanding.stage_events if event.status == "skipped"]
    assert all(event.model_operation_count == 0 for event in skipped)
    assert all(event.estimated_cost_usd == 0.0 for event in skipped)
    assert all(event.model_attempt_count == 0 for event in skipped)
    retrieved = set(understanding.retrieved_block_ids)
    cited_blocks = {fact.source_block_id for fact in supported if fact.source_block_id}
    assert retrieved
    uncited_retrieved = retrieved - cited_blocks
    assert uncited_retrieved or any(
        item.relevant is False for item in understanding.classifications
    )


@pytest.mark.integration
async def test_harbor_understand_is_not_aurora_specific(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, _storage = phase02_service
    aurora = await ingest_corpus(phase02, corpus_fixtures / "aurora-control-hub")
    harbor = await ingest_corpus(phase02, corpus_fixtures / "harbor-ledger-modernization")
    understand = make_understand(phase02)
    aurora_run = await understand.create_run(aurora.id)
    harbor_run = await understand.create_run(harbor.id)
    aurora_facts = await understand.list_facts(aurora.id, aurora_run.id)
    harbor_facts = await understand.list_facts(harbor.id, harbor_run.id)
    harbor_supported = [fact for fact in harbor_facts if fact.support_status == "supported"]
    aurora_supported = [fact for fact in aurora_facts if fact.support_status == "supported"]

    harbor_values = {fact.normalized_value for fact in harbor_supported}
    aurora_values = {fact.normalized_value for fact in aurora_supported}
    assert "Tomas Reed" in harbor_values
    assert "Elena Marlow" not in harbor_values
    assert "Elena Marlow" in aurora_values
    assert "Tomas Reed" not in aurora_values
    harbor_keys = {fact.subject_key for fact in harbor_supported}
    aurora_keys = {fact.subject_key for fact in aurora_supported}
    assert "legacy_retirement" in harbor_keys
    assert "production_readiness" in aurora_keys
    harbor_unknown_production = [
        fact
        for fact in harbor_facts
        if fact.subject_key == "production_readiness" and fact.support_status == "unknown"
    ]
    assert harbor_unknown_production
    assert all(fact.corpus_id == harbor.id for fact in harbor_facts)
    assert all(fact.corpus_id == aurora.id for fact in aurora_facts)


@pytest.mark.integration
async def test_no_findings_is_explicit_empty_result(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
) -> None:
    phase02, _storage = phase02_service
    corpus = await phase02.create_corpus(
        name="Blank notes",
        domain="software-project-assurance",
        declared_formats=["txt"],
    )
    await phase02.ingest(
        corpus_id=corpus.id,
        logical_name="Blank",
        declared_format="txt",
        upload=UploadFile(
            BytesIO(b"This page intentionally left blank.\nWeather notes: sunny."),
            filename="blank.txt",
            headers=Headers({"content-type": "text/plain"}),
        ),
    )
    understand = make_understand(phase02)
    run = await understand.create_run(corpus.id)
    understanding = await understand.get_understanding(corpus.id, run.id)
    supported = [fact for fact in understanding.facts if fact.support_status == "supported"]
    assert run.findings_status == "no_findings"
    assert understanding.no_findings is True
    assert supported == []
    assert understanding.contradictions == []


@pytest.mark.integration
async def test_malformed_and_unsupported_model_assertions_are_rejected(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, _storage = phase02_service
    corpus = await ingest_corpus(phase02, corpus_fixtures / "aurora-control-hub")
    sources = await phase02.list_sources(corpus.id)
    versions = (await phase02.get_source(corpus.id, sources[0].id))[1]
    version = versions[0]
    first_block = (await phase02.get_blocks(corpus.id, version.id))[0]
    declared = version.declared_format

    class ScriptedAdapter(DeterministicModelAdapter):
        async def extract_facts(self, selected: Sequence[BlockContext]) -> ExtractionBatch:
            batch = await super().extract_facts(selected)
            bad_quote = ProposedFact(
                category="status",
                subject_key="overall_status",
                normalized_value="invented-green",
                confidence=0.99,
                source_block_id=first_block.id,
                citation=CitationRequest(
                    source_version_id=version.id,
                    source_sha256=version.sha256,
                    format=declared,  # type: ignore[arg-type]
                    native_locator=first_block.native_locator,
                    normalized_start=0,
                    normalized_end=8,
                    exact_quote="NOT-REAL",
                ),
            )
            missing = ProposedFact(
                category="status",
                subject_key="fabricated_field",
                normalized_value="fabricated",
                confidence=0.99,
                source_block_id=first_block.id,
                citation=CitationRequest(
                    source_version_id=version.id,
                    source_sha256=version.sha256,
                    format=declared,  # type: ignore[arg-type]
                    native_locator="lines[999-999]/block[0]",
                    normalized_start=0,
                    normalized_end=4,
                    exact_quote="fake",
                ),
            )
            return ExtractionBatch(facts=[*batch.facts, bad_quote, missing], usage=zero_usage())

    understand = make_understand(phase02, ScriptedAdapter())
    run = await understand.create_run(corpus.id)
    understanding = await understand.get_understanding(corpus.id, run.id)
    reasons = {item.reason for item in understanding.rejected_assertions}
    assert "exact_quote_mismatch" in reasons
    assert "native_locator_mismatch" in reasons
    supported_values = {
        fact.normalized_value for fact in understanding.facts if fact.support_status == "supported"
    }
    assert "invented-green" not in supported_values
    assert "fabricated" not in supported_values


@pytest.mark.integration
async def test_analysis_run_is_corpus_scoped(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, _storage = phase02_service
    first = await ingest_corpus(phase02, corpus_fixtures / "aurora-control-hub")
    second = await phase02.create_corpus(
        name="Other",
        domain="software-project-assurance",
        declared_formats=["txt"],
    )
    understand = make_understand(phase02)
    run = await understand.create_run(first.id)
    with pytest.raises(NotFoundError) as error:
        await understand.get_run(second.id, run.id)
    assert error.value.code == "analysis_run_not_found"
    facts = await understand.list_facts(first.id, run.id)
    assert all(fact.corpus_id == first.id for fact in facts)


@pytest.mark.integration
async def test_retrieval_context_is_not_automatic_evidence(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, _storage = phase02_service
    corpus = await ingest_corpus(phase02, corpus_fixtures / "aurora-control-hub")
    understand = make_understand(phase02)
    run = await understand.create_run(corpus.id)
    understanding = await understand.get_understanding(corpus.id, run.id)
    retrieved = set(understanding.retrieved_block_ids)
    assert retrieved
    matches = await phase02.search(
        corpus_id=corpus.id,
        request=SearchRequest(query="production readiness owner status", limit=10),
    )
    assert all(match.block.corpus_id == corpus.id for match in matches)
    supported_ids = {
        fact.source_block_id
        for fact in understanding.facts
        if fact.support_status == "supported" and fact.source_block_id is not None
    }
    assert not retrieved <= supported_ids or any(
        item.relevant is False for item in understanding.classifications
    )


@pytest.mark.integration
async def test_model_failure_marks_run_failed_without_supported_facts(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, _storage = phase02_service
    corpus = await ingest_corpus(phase02, corpus_fixtures / "aurora-control-hub")

    class FailingAdapter(DeterministicModelAdapter):
        async def classify_blocks(self, blocks: Sequence[BlockContext]) -> ClassificationBatch:
            raise ModelError(
                "model_unavailable",
                "The model provider could not be reached.",
                "Retry the analysis run or use MODEL_PROVIDER=deterministic.",
                retryable=False,
            )

    understand = make_understand(phase02, FailingAdapter())
    run = await understand.create_run(corpus.id)
    assert run.status == "failed"
    assert run.findings_status == "failed"
    assert run.error_code == "model_unavailable"
    facts = await understand.list_facts(corpus.id, run.id)
    assert facts == []
    events = await understand.list_stage_events(corpus.id, run.id)
    by_name = {event.stage_name: event for event in events}
    assert by_name["classify"].status == "failed"
    assert by_name["extract_facts"].status == "skipped"
    assert by_name["extract_facts"].skip_reason == "prior_stage_failed"
    assert by_name["validate_provenance"].skip_reason == "prior_stage_failed"
    assert by_name["detect_contradictions"].skip_reason == "prior_stage_failed"


@pytest.mark.integration
async def test_failed_retries_record_actual_attempt_count(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    phase02, _storage = phase02_service
    corpus = await phase02.create_corpus(
        name="Retry accounting",
        domain="software-project-assurance",
        declared_formats=["txt"],
    )
    await phase02.ingest(
        corpus_id=corpus.id,
        logical_name="Status",
        declared_format="txt",
        upload=UploadFile(
            BytesIO(b"Overall status is GREEN.\nProject sponsor: Elena Marlow.\n"),
            filename="status.txt",
            headers=Headers({"content-type": "text/plain"}),
        ),
    )

    async def _no_sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr("app.model_gateway.asyncio.sleep", _no_sleep)
    attempts = {"count": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(503, json={"error": "busy"})

    adapter = OpenAICompatibleAdapter(
        api_key="sk-test-secret-should-not-leak",
        model="gpt-4o-mini",
        base_url="https://example.test/v1",
        timeout_seconds=1,
        max_retries=2,
        transport=httpx.MockTransport(handler),
    )
    understand = make_understand(phase02, adapter)
    run = await understand.create_run(corpus.id)
    events = await understand.list_stage_events(corpus.id, run.id)
    classify = next(event for event in events if event.stage_name == "classify")
    assert run.status == "failed"
    assert classify.status == "failed"
    assert classify.model_operation_count == 1
    assert classify.model_attempt_count == 3
    assert attempts["count"] == 3
    assert classify.estimated_cost_usd is None or classify.cost_basis == "unavailable"


async def _corpus_blocks(
    phase02: Phase02Service, corpus_id: UUID
) -> list[tuple[SourceVersion, SourceBlock]]:
    rows: list[tuple[SourceVersion, SourceBlock]] = []
    for source in await phase02.list_sources(corpus_id):
        _source, versions = await phase02.get_source(corpus_id, source.id)
        version = versions[0]
        for block in await phase02.get_blocks(corpus_id, version.id):
            rows.append((version, block))
    return rows


def _citation(
    version: SourceVersion, block: SourceBlock, quote: str | None = None
) -> CitationRequest:
    text = block.normalized_text
    exact = quote if quote is not None else text
    start = 0 if quote is None else text.find(quote)
    assert start >= 0
    return CitationRequest(
        source_version_id=version.id,
        source_sha256=version.sha256,
        format=version.declared_format,  # type: ignore[arg-type]
        native_locator=block.native_locator,
        normalized_start=start,
        normalized_end=start + len(exact),
        exact_quote=exact,
    )


class _SearchFilter:
    def __init__(
        self,
        inner: Phase02Service,
        *,
        allow: set[UUID] | None = None,
        empty: bool = False,
    ) -> None:
        self._inner = inner
        self._allow = allow
        self._empty = empty

    def __getattr__(self, name: str) -> object:
        return getattr(self._inner, name)

    async def search(self, *, corpus_id: UUID, request: SearchRequest) -> list[SearchMatch]:
        if self._empty:
            return []
        results = await self._inner.search(corpus_id=corpus_id, request=request)
        if self._allow is None:
            return results
        return [item for item in results if item.block.id in self._allow]


@pytest.mark.integration
async def test_invented_value_with_valid_unrelated_citation_is_rejected(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, _storage = phase02_service
    corpus = await ingest_corpus(phase02, corpus_fixtures / "aurora-control-hub")
    rows = await _corpus_blocks(phase02, corpus.id)
    sponsor = next(
        row
        for row in rows
        if any(
            item.subject_key == "project_sponsor" and "Elena Marlow" in item.normalized_value
            for item in derive_assertions(str(row[1].normalized_text))
        )
    )
    production = next(
        row
        for row in rows
        if any(
            item.subject_key == "production_readiness"
            for item in derive_assertions(str(row[1].normalized_text))
        )
        and row[1].id != sponsor[1].id
    )
    other = next(row for row in rows if row[1].id not in {sponsor[1].id, production[1].id})
    sponsor_quote = next(
        item.match_text
        for item in derive_assertions(str(sponsor[1].normalized_text))
        if item.subject_key == "project_sponsor"
    )
    production_match = next(
        item
        for item in derive_assertions(str(production[1].normalized_text))
        if item.subject_key == "production_readiness"
    )
    production_quote = production_match.match_text
    production_value = production_match.normalized_value

    class ScriptedAdapter(DeterministicModelAdapter):
        async def extract_facts(self, selected: Sequence[BlockContext]) -> ExtractionBatch:
            batch = await super().extract_facts(selected)
            invented = ProposedFact(
                category="milestone_date",
                subject_key="production_readiness",
                normalized_value="2099-01-01",
                confidence=0.99,
                source_block_id=sponsor[1].id,
                citation=_citation(*sponsor, sponsor_quote),
            )
            mismatched_block = ProposedFact(
                category="owner_accountability",
                subject_key="project_sponsor",
                normalized_value="Elena Marlow",
                confidence=0.99,
                source_block_id=other[1].id,
                citation=_citation(*sponsor, sponsor_quote),
            )
            wrong_category = ProposedFact(
                category="owner_accountability",
                subject_key="production_readiness",
                normalized_value=production_value,
                confidence=0.99,
                source_block_id=production[1].id,
                citation=_citation(*production, production_quote),
            )
            wrong_subject = ProposedFact(
                category="milestone_date",
                subject_key="legacy_retirement",
                normalized_value=production_value,
                confidence=0.99,
                source_block_id=production[1].id,
                citation=_citation(*production, production_quote),
            )
            invented_conflict = ProposedFact(
                category="milestone_date",
                subject_key="production_readiness",
                normalized_value="2098-01-01",
                confidence=0.99,
                source_block_id=sponsor[1].id,
                citation=_citation(*sponsor, sponsor_quote),
            )
            return ExtractionBatch(
                facts=[
                    *batch.facts,
                    invented,
                    mismatched_block,
                    wrong_category,
                    wrong_subject,
                    invented_conflict,
                ],
                usage=zero_usage(),
            )

    understand = make_understand(phase02, ScriptedAdapter())
    run = await understand.create_run(corpus.id)
    understanding = await understand.get_understanding(corpus.id, run.id)
    reasons = {item.reason for item in understanding.rejected_assertions}
    assert "assertion_not_supported" in reasons or "normalized_value_mismatch" in reasons
    assert "source_block_mismatch" in reasons
    assert "category_mismatch" in reasons
    assert "subject_key_mismatch" in reasons
    supported_values = {
        fact.normalized_value for fact in understanding.facts if fact.support_status == "supported"
    }
    assert "2099-01-01" not in supported_values
    assert "2098-01-01" not in supported_values
    assert "2026-10-30" in supported_values
    assert all(
        {item.fact_a.normalized_value, item.fact_b.normalized_value} != {"2099-01-01", "2098-01-01"}
        for item in understanding.contradictions
    )


@pytest.mark.integration
async def test_injection_block_fact_is_rejected_even_if_model_proposes_it(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, _storage = phase02_service
    corpus = await ingest_corpus(phase02, corpus_fixtures / "aurora-control-hub")
    injection = next(
        row
        for row in await _corpus_blocks(phase02, corpus.id)
        if "ignore previous instructions" in str(row[1].normalized_text).casefold()
    )

    class LiveShapedAdapter(DeterministicModelAdapter):
        async def classify_blocks(self, blocks: Sequence[BlockContext]) -> ClassificationBatch:
            batch = await super().classify_blocks(blocks)
            by_id = {item.source_block_id: item for item in batch.classifications}
            forced: list[BlockClassification] = []
            for block in blocks:
                item = by_id[block.source_block_id]
                if block.source_block_id == injection[1].id:
                    forced.append(
                        BlockClassification(
                            source_block_id=block.source_block_id,
                            relevant=True,
                            category="control_assurance",
                            confidence=0.99,
                            rationale="model followed injection",
                        )
                    )
                else:
                    forced.append(item)
            return ClassificationBatch(classifications=forced, usage=zero_usage())

        async def extract_facts(self, selected: Sequence[BlockContext]) -> ExtractionBatch:
            approval = ProposedFact(
                category="control_assurance",
                subject_key="compliance_status",
                normalized_value="approved",
                confidence=0.99,
                source_block_id=injection[1].id,
                citation=_citation(*injection),
            )
            return ExtractionBatch(facts=[approval], usage=zero_usage())

    understand = make_understand(phase02, LiveShapedAdapter())
    run = await understand.create_run(corpus.id)
    understanding = await understand.get_understanding(corpus.id, run.id)
    injection_classes = [
        item for item in understanding.classifications if item.source_block_id == injection[1].id
    ]
    assert injection_classes
    assert all(item.category == "untrusted_instruction" for item in injection_classes)
    assert all(item.relevant is False for item in injection_classes)
    assert any(item.reason == "untrusted_instruction" for item in understanding.rejected_assertions)
    supported_values = {
        fact.normalized_value.casefold()
        for fact in understanding.facts
        if fact.support_status == "supported"
    }
    assert "approved" not in supported_values
    assert all("compliant" not in value for value in supported_values)


@pytest.mark.integration
async def test_retrieval_controls_classification_unless_fallback(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, _storage = phase02_service
    corpus = await ingest_corpus(phase02, corpus_fixtures / "aurora-control-hub")
    rows = await _corpus_blocks(phase02, corpus.id)
    allowed = next(
        row
        for row in rows
        if any(
            item.subject_key == "identity_test_tenant"
            for item in derive_assertions(str(row[1].normalized_text))
        )
    )
    excluded = next(
        row
        for row in rows
        if any(
            item.subject_key == "production_readiness"
            for item in derive_assertions(str(row[1].normalized_text))
        )
        and row[1].id != allowed[1].id
    )
    filtered = _SearchFilter(phase02, allow={allowed[1].id})
    understand = make_understand(filtered)  # type: ignore[arg-type]
    run = await understand.create_run(corpus.id)
    understanding = await understand.get_understanding(corpus.id, run.id)
    classified_ids = {item.source_block_id for item in understanding.classifications}
    assert classified_ids == {allowed[1].id}
    assert excluded[1].id not in classified_ids
    assert understanding.retrieval_mode == "retrieved"
    supported_keys = {
        fact.subject_key for fact in understanding.facts if fact.support_status == "supported"
    }
    assert "identity_test_tenant" in supported_keys
    assert "production_readiness" not in supported_keys

    fallback_service = _SearchFilter(phase02, empty=True)
    fallback = make_understand(fallback_service)  # type: ignore[arg-type]
    fallback_run = await fallback.create_run(corpus.id)
    fallback_understanding = await fallback.get_understanding(corpus.id, fallback_run.id)
    assert fallback_understanding.retrieval_mode == "fallback_full_corpus"
    retrieve = next(
        event
        for event in fallback_understanding.stage_events
        if event.stage_name == "retrieve_context"
    )
    assert retrieve.status == "skipped"
    assert retrieve.skip_reason == "retrieval_empty_fallback"
    fallback_classified = {item.source_block_id for item in fallback_understanding.classifications}
    assert excluded[1].id in fallback_classified
    fallback_keys = {
        fact.subject_key
        for fact in fallback_understanding.facts
        if fact.support_status == "supported"
    }
    assert "production_readiness" in fallback_keys


@pytest.mark.integration
async def test_empty_corpus_records_skipped_canonical_stages(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
) -> None:
    phase02, _storage = phase02_service
    corpus = await phase02.create_corpus(
        name="Empty",
        domain="software-project-assurance",
        declared_formats=["txt"],
    )
    understand = make_understand(phase02)
    run = await understand.create_run(corpus.id)
    understanding = await understand.get_understanding(corpus.id, run.id)
    by_name = {event.stage_name: event for event in understanding.stage_events}
    assert set(by_name) >= set(CANONICAL_STAGES)
    assert by_name["load_corpus"].status == "skipped"
    assert by_name["load_corpus"].skip_reason == "empty_corpus"
    assert by_name["retrieve_context"].skip_reason == "empty_corpus"
    assert by_name["classify"].skip_reason == "empty_corpus"
    assert by_name["extract_facts"].skip_reason == "empty_corpus"
    assert understanding.no_findings is True
    assert understanding.retrieval_mode == "empty_corpus"


def _analysis_run(corpus_id: UUID) -> AnalysisRun:
    return AnalysisRun(
        corpus_id=corpus_id,
        status="completed",
        findings_status="populated",
        started_at=datetime.now(UTC),
        model_provider_mode="deterministic",
        model_name="test",
        taxonomy_version=TAXONOMY_VERSION,
        graph_version=GRAPH_VERSION,
        configuration={},
        result_payload={},
    )


@pytest.mark.integration
async def test_database_rejects_ungrounded_supported_facts_and_bad_contradictions(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
) -> None:
    phase02, _storage = phase02_service

    async def tiny(name: str, body: bytes) -> Corpus:
        corpus = await phase02.create_corpus(
            name=name,
            domain="software-project-assurance",
            declared_formats=["txt"],
        )
        await phase02.ingest(
            corpus_id=corpus.id,
            logical_name="Notes",
            declared_format="txt",
            upload=UploadFile(
                BytesIO(body),
                filename="notes.txt",
                headers=Headers({"content-type": "text/plain"}),
            ),
        )
        return corpus

    aurora = await tiny("A-side", b"Project sponsor: Elena Marlow\n")
    harbor = await tiny("B-side", b"Project sponsor: Tomas Reed\n")
    aurora_block = (await _corpus_blocks(phase02, aurora.id))[0][1]
    harbor_block = (await _corpus_blocks(phase02, harbor.id))[0][1]

    async with phase02.session_factory() as session:
        run = _analysis_run(aurora.id)
        session.add(run)
        await session.flush()
        session.add(
            Fact(
                run_id=run.id,
                corpus_id=aurora.id,
                category="milestone_date",
                subject_key="production_readiness",
                normalized_value="2099-01-01",
                confidence=1.0,
                support_status="supported",
                citation=None,
                source_block_id=None,
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()

    async with phase02.session_factory() as session:
        run = _analysis_run(aurora.id)
        session.add(run)
        await session.flush()
        session.add(
            Fact(
                run_id=run.id,
                corpus_id=aurora.id,
                category="project_identity",
                subject_key="project_name",
                normalized_value="Aurora Control Hub",
                confidence=1.0,
                support_status="supported",
                citation={"exact_quote": "Aurora Control Hub"},
                source_block_id=harbor_block.id,
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()

    async with phase02.session_factory() as session:
        run = _analysis_run(aurora.id)
        session.add(run)
        await session.flush()
        unknown = Fact(
            run_id=run.id,
            corpus_id=aurora.id,
            category="owner_accountability",
            subject_key="budget_owner",
            normalized_value="INSUFFICIENT_EVIDENCE",
            confidence=0.0,
            support_status="unknown",
            citation=None,
            source_block_id=None,
        )
        left = Fact(
            run_id=run.id,
            corpus_id=aurora.id,
            category="milestone_date",
            subject_key="production_readiness",
            normalized_value="2026-10-30",
            confidence=1.0,
            support_status="supported",
            citation={"exact_quote": "2026-10-30"},
            source_block_id=aurora_block.id,
        )
        right = Fact(
            run_id=run.id,
            corpus_id=aurora.id,
            category="milestone_date",
            subject_key="production_readiness",
            normalized_value="2026-11-14",
            confidence=1.0,
            support_status="supported",
            citation={"exact_quote": "2026-11-14"},
            source_block_id=aurora_block.id,
        )
        session.add_all([unknown, left, right])
        await session.flush()
        first, second = sorted((left.id, right.id))
        session.add(
            Contradiction(
                run_id=run.id,
                corpus_id=aurora.id,
                fact_a_id=first,
                fact_b_id=second,
                contradiction_type="conflicting_dates",
                reason="dates",
                confidence=1.0,
                status="open",
            )
        )
        await session.flush()
        session.add(
            Contradiction(
                run_id=run.id,
                corpus_id=aurora.id,
                fact_a_id=first,
                fact_b_id=second,
                contradiction_type="conflicting_dates",
                reason="duplicate",
                confidence=1.0,
                status="open",
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()

    async with phase02.session_factory() as session:
        run = _analysis_run(aurora.id)
        other = _analysis_run(aurora.id)
        session.add_all([run, other])
        await session.flush()
        left = Fact(
            run_id=run.id,
            corpus_id=aurora.id,
            category="status",
            subject_key="overall_status",
            normalized_value="amber",
            confidence=1.0,
            support_status="supported",
            citation={"exact_quote": "amber"},
            source_block_id=aurora_block.id,
        )
        right = Fact(
            run_id=run.id,
            corpus_id=aurora.id,
            category="status",
            subject_key="overall_status",
            normalized_value="green",
            confidence=1.0,
            support_status="supported",
            citation={"exact_quote": "green"},
            source_block_id=aurora_block.id,
        )
        session.add_all([left, right])
        await session.flush()
        first, second = sorted((left.id, right.id))
        session.add(
            Contradiction(
                run_id=other.id,
                corpus_id=aurora.id,
                fact_a_id=first,
                fact_b_id=second,
                contradiction_type="conflicting_status",
                reason="cross-run",
                confidence=1.0,
                status="open",
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()
