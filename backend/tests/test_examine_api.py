from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from helpers import ingest_corpus, make_examine

from app.main import create_app
from app.services import Phase02Service
from app.storage import LocalFileStorage


@pytest.mark.integration
async def test_examine_api_creates_and_inspects_runs(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, _storage = phase02_service
    corpus = await ingest_corpus(phase02, corpus_fixtures / "aurora-control-hub")
    examine = make_examine(phase02)
    application = create_app(
        phase02_service=phase02,
        understand_service=examine.understand,
        examine_service=examine,
    )
    transport = httpx.ASGITransport(app=application)
    async with (
        application.router.lifespan_context(application),
        httpx.AsyncClient(transport=transport, base_url="http://test") as client,
    ):
        analysis = await client.post(f"/corpora/{corpus.id}/analysis-runs")
        assert analysis.status_code == 201
        analysis_id = analysis.json()["id"]
        created = await client.post(
            f"/corpora/{corpus.id}/analysis-runs/{analysis_id}/examination-runs"
        )
        assert created.status_code == 201
        run = created.json()
        run_id = run["id"]
        assert run["status"] == "completed"
        assert run["corpus_id"] == str(corpus.id)
        assert run["analysis_run_id"] == analysis_id
        assert run["ruleset_version"] == "software-project-assurance.v1"

        fetched = await client.get(f"/corpora/{corpus.id}/examination-runs/{run_id}")
        assert fetched.status_code == 200
        findings = await client.get(f"/corpora/{corpus.id}/examination-runs/{run_id}/findings")
        summary = await client.get(f"/corpora/{corpus.id}/examination-runs/{run_id}/summary")
        events = await client.get(f"/corpora/{corpus.id}/examination-runs/{run_id}/stage-events")
        assert findings.status_code == 200
        body = findings.json()
        assert body
        outcomes = {item["outcome"] for item in body}
        assert "pass" in outcomes
        assert "fail" in outcomes
        assert "warning" in outcomes
        assert "unknown" in outcomes
        fail_item = next(
            item for item in body if item["rule_id"] == "spa.milestone.production-readiness"
        )
        assert fail_item["outcome"] == "fail"
        assert fail_item["evidence_kind"] == "grounded_facts"
        assert len(fail_item["fact_ids"]) == 2
        assert fail_item["citations"]
        assert {item["exact_quote"] for item in fail_item["citations"]}
        open_item = next(item for item in body if item["rule_id"] == "spa.contradiction.open")
        assert open_item["outcome"] == "pass"
        assert open_item["evidence_kind"] == "process_attestation"
        assert open_item["fact_ids"] == []
        assert open_item["citations"] == []
        unknown_item = next(item for item in body if item["rule_id"] == "spa.ownership.budget")
        assert unknown_item["outcome"] == "unknown"
        assert unknown_item["evidence_kind"] == "none"
        assert unknown_item["fact_ids"] == []
        assert unknown_item["citations"] == []
        assert summary.status_code == 200
        assert summary.json()["no_findings"] is False
        assert events.status_code == 200
        assert events.json()

        missing_corpus = await client.post(
            f"/corpora/{uuid4()}/analysis-runs/{analysis_id}/examination-runs"
        )
        assert missing_corpus.status_code == 404
        other = await client.post(
            "/corpora",
            json={
                "name": "Empty",
                "domain": "software-project-assurance",
                "declared_formats": ["txt"],
            },
        )
        leaked = await client.get(f"/corpora/{other.json()['id']}/examination-runs/{run_id}")
        assert leaked.status_code == 404
        assert leaked.json()["code"] == "examination_run_not_found"
        assert "traceback" not in leaked.text.casefold()
        wrong_analysis = await client.post(
            f"/corpora/{other.json()['id']}/analysis-runs/{analysis_id}/examination-runs"
        )
        assert wrong_analysis.status_code == 404
        assert wrong_analysis.json()["code"] == "analysis_run_not_found"
        missing_run = await client.get(f"/corpora/{corpus.id}/examination-runs/{uuid4()}")
        assert missing_run.status_code == 404
        assert missing_run.json()["code"] == "examination_run_not_found"
