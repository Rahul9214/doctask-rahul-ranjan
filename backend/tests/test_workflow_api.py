from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from helpers import (
    complete_required_review,
    ingest_corpus,
    ingest_workflow_corpus,
    make_workflow,
)

from app.main import create_app
from app.services import Phase02Service
from app.storage import LocalFileStorage


@pytest.mark.integration
async def test_workflow_api_start_inspect_resume_and_isolation(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, _storage = phase02_service
    aurora = await ingest_workflow_corpus(phase02, corpus_fixtures / "aurora-control-hub")
    harbor = await ingest_corpus(phase02, corpus_fixtures / "harbor-ledger-modernization")
    workflow = make_workflow(phase02)
    application = create_app(
        phase02_service=phase02,
        understand_service=workflow.examine.understand,
        examine_service=workflow.examine,
        review_service=workflow.review,
        workflow_service=workflow,
    )
    transport = httpx.ASGITransport(app=application)
    async with (
        application.router.lifespan_context(application),
        httpx.AsyncClient(transport=transport, base_url="http://test") as client,
    ):
        created = await client.post(f"/corpora/{aurora.id}/workflow-runs")
        assert created.status_code == 201
        run = created.json()
        run_id = run["id"]
        assert run["status"] == "waiting_for_review"
        assert run["current_stage"] == "wait_for_review"
        assert run["checkpoint_thread_id"] == run_id
        fetched = await client.get(f"/corpora/{aurora.id}/workflow-runs/{run_id}")
        assert fetched.status_code == 200
        events = await client.get(f"/corpora/{aurora.id}/workflow-runs/{run_id}/events")
        assert events.status_code == 200
        assert any(item["event_type"] == "waiting_for_review" for item in events.json())
        resumed = await client.post(f"/corpora/{aurora.id}/workflow-runs/{run_id}/resume")
        assert resumed.status_code == 200
        assert resumed.json()["status"] == "waiting_for_review"
        missing = await client.get(f"/corpora/{harbor.id}/workflow-runs/{run_id}")
        assert missing.status_code == 404
        assert missing.json()["code"] == "workflow_run_not_found"
        assert "traceback" not in missing.text.casefold()
        unknown = await client.get(f"/corpora/{aurora.id}/workflow-runs/{uuid4()}")
        assert unknown.status_code == 404

        session_id = run["review_session_id"]
        await complete_required_review(workflow.review, aurora.id, UUID(session_id))
        finished = await client.post(f"/corpora/{aurora.id}/workflow-runs/{run_id}/resume")
        assert finished.status_code == 200
        assert finished.json()["status"] == "completed"
        again = await client.post(f"/corpora/{aurora.id}/workflow-runs/{run_id}/resume")
        assert again.status_code == 400
        assert again.json()["code"] == "workflow_run_already_completed"
