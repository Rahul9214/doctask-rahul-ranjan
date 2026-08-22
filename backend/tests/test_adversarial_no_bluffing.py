from uuid import uuid4

import httpx
import pytest
from helpers import ingest_text, make_examine, make_understand

from app.main import create_app
from app.services import Phase02Service
from app.storage import LocalFileStorage


@pytest.mark.integration
@pytest.mark.adversarial
async def test_insufficient_and_unrelated_evidence_never_become_definitive(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
) -> None:
    phase02, _storage = phase02_service
    corpus = await phase02.create_corpus(
        name="Sparse Evidence",
        domain="software-project-assurance",
        declared_formats=["txt"],
    )
    await ingest_text(
        phase02,
        corpus.id,
        "Sparse Notes",
        "\n\n".join(
            [
                "The programme is currently being discussed.",
                "Overall status is maybe fine depending on later review.",
                "A date might be agreed after the next steering meeting.",
            ]
        ),
    )
    understand = make_understand(phase02)
    analysis = await understand.create_run(corpus.id)
    understanding = await understand.get_understanding(corpus.id, analysis.id)
    unknown = [fact for fact in understanding.facts if fact.support_status == "unknown"]
    supported = [fact for fact in understanding.facts if fact.support_status == "supported"]
    assert unknown
    assert all(fact.normalized_value == "INSUFFICIENT_EVIDENCE" for fact in unknown)
    assert all(fact.citation is None for fact in unknown)
    assert all(fact.normalized_value != "INSUFFICIENT_EVIDENCE" for fact in supported)
    owner = [fact for fact in unknown if fact.subject_key in {"project_sponsor", "budget_owner"}]
    dates = [fact for fact in unknown if "date" in fact.category or "milestone" in fact.category]
    assert owner
    assert dates or any(fact.subject_key == "production_readiness" for fact in unknown)

    examine = make_examine(phase02, understand=understand)
    examination = await examine.create_run(corpus.id, analysis.id)
    summary = await examine.get_summary(corpus.id, examination.id)
    findings = await examine.list_finding_responses(corpus.id, examination.id)
    assert summary.run.status == "completed"
    assert all(
        item.outcome != "pass" or item.evidence_kind != "grounded_facts" for item in findings
    )
    unknown_findings = [item for item in findings if item.outcome == "unknown"]
    assert unknown_findings
    assert all(item.citations == [] for item in unknown_findings)
    assert all(item.fact_ids == [] for item in unknown_findings)

    application = create_app(
        phase02_service=phase02,
        understand_service=understand,
        examine_service=examine,
    )
    transport = httpx.ASGITransport(app=application)
    async with (
        application.router.lifespan_context(application),
        httpx.AsyncClient(transport=transport, base_url="http://test") as client,
    ):
        facts = await client.get(f"/corpora/{corpus.id}/analysis-runs/{analysis.id}/facts")
        assert facts.status_code == 200
        assert "traceback" not in facts.text.casefold()
        assert any(item["support_status"] == "unknown" for item in facts.json())
        assert all(
            item["citation"] is None for item in facts.json() if item["support_status"] == "unknown"
        )
        missing = await client.get(f"/corpora/{uuid4()}/analysis-runs/{analysis.id}/facts")
        assert missing.status_code == 404
        assert missing.json()["code"] in {"corpus_not_found", "analysis_run_not_found"}


@pytest.mark.integration
@pytest.mark.adversarial
async def test_conflicting_documents_surface_both_sides_without_silent_pass(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
) -> None:
    phase02, _storage = phase02_service
    corpus = await phase02.create_corpus(
        name="Conflict Corpus",
        domain="software-project-assurance",
        declared_formats=["txt"],
    )
    await ingest_text(
        phase02,
        corpus.id,
        "Plan A",
        "Project sponsor: Elena Marlow\n\nProduction readiness milestone: 2026-10-30",
    )
    await ingest_text(
        phase02,
        corpus.id,
        "Plan B",
        "Project sponsor: Elena Marlow\n\nProduction readiness baseline at 2026-11-14",
    )
    understand = make_understand(phase02)
    analysis = await understand.create_run(corpus.id)
    understanding = await understand.get_understanding(corpus.id, analysis.id)
    assert understanding.contradictions
    production = [
        item
        for item in understanding.contradictions
        if {item.fact_a.normalized_value, item.fact_b.normalized_value}
        == {"2026-10-30", "2026-11-14"}
    ]
    assert production
    assert production[0].fact_a.citation is not None
    assert production[0].fact_b.citation is not None

    examine = make_examine(phase02, understand=understand)
    examination = await examine.create_run(corpus.id, analysis.id)
    findings = await examine.list_finding_responses(corpus.id, examination.id)
    readiness = next(
        item for item in findings if item.rule_id == "spa.milestone.production-readiness"
    )
    assert readiness.outcome == "fail"
    assert len(readiness.citations) >= 2
