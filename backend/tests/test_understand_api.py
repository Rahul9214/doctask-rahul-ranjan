from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from helpers import ingest_corpus, make_understand

from app.main import create_app
from app.services import Phase02Service
from app.storage import LocalFileStorage


@pytest.mark.integration
async def test_understand_api_creates_and_inspects_runs(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, _storage = phase02_service
    corpus = await ingest_corpus(phase02, corpus_fixtures / "aurora-control-hub")
    understand = make_understand(phase02)
    application = create_app(phase02_service=phase02, understand_service=understand)
    transport = httpx.ASGITransport(app=application)
    async with (
        application.router.lifespan_context(application),
        httpx.AsyncClient(transport=transport, base_url="http://test") as client,
    ):
        created = await client.post(f"/corpora/{corpus.id}/analysis-runs")
        assert created.status_code == 201
        run = created.json()
        run_id = run["id"]
        assert run["status"] == "completed"
        assert run["corpus_id"] == str(corpus.id)

        fetched = await client.get(f"/corpora/{corpus.id}/analysis-runs/{run_id}")
        assert fetched.status_code == 200
        facts = await client.get(f"/corpora/{corpus.id}/analysis-runs/{run_id}/facts")
        contradictions = await client.get(
            f"/corpora/{corpus.id}/analysis-runs/{run_id}/contradictions"
        )
        understanding = await client.get(
            f"/corpora/{corpus.id}/analysis-runs/{run_id}/understanding"
        )
        events = await client.get(f"/corpora/{corpus.id}/analysis-runs/{run_id}/stage-events")
        assert facts.status_code == 200
        assert any(item["support_status"] == "supported" for item in facts.json())
        assert contradictions.status_code == 200
        assert contradictions.json()
        assert contradictions.json()[0]["fact_a"]["citation"]
        assert contradictions.json()[0]["fact_b"]["citation"]
        assert understanding.status_code == 200
        assert understanding.json()["no_findings"] is False
        assert events.status_code == 200
        assert events.json()

        missing_corpus = await client.post(f"/corpora/{uuid4()}/analysis-runs")
        assert missing_corpus.status_code == 404
        assert missing_corpus.json()["code"] == "corpus_not_found"
        other = await client.post(
            "/corpora",
            json={
                "name": "Empty",
                "domain": "software-project-assurance",
                "declared_formats": ["txt"],
            },
        )
        leaked = await client.get(f"/corpora/{other.json()['id']}/analysis-runs/{run_id}")
        assert leaked.status_code == 404
        assert leaked.json()["code"] == "analysis_run_not_found"
        assert "traceback" not in leaked.text.casefold()
