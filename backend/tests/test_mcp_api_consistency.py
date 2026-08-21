from pathlib import Path
from uuid import UUID

import httpx
import pytest
from helpers import fixture_upload, ingest_corpus, prepare_incremental_corpus
from mcp_helpers import call_err, call_ok, in_memory_mcp

from app.main import create_app
from app.services import Phase02Service
from app.storage import LocalFileStorage


@pytest.mark.integration
async def test_mcp_and_http_share_review_workflow_and_incremental_semantics(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, _storage = phase02_service
    aurora = await ingest_corpus(phase02, corpus_fixtures / "aurora-control-hub")
    harbor = await ingest_corpus(phase02, corpus_fixtures / "harbor-ledger-modernization")
    async with in_memory_mcp(phase02) as (mcp_client, services):
        application = create_app(
            phase02_service=phase02,
            understand_service=services.understand,
            examine_service=services.examine,
            review_service=services.review,
            workflow_service=services.workflow,
            incremental_service=services.incremental,
        )
        transport = httpx.ASGITransport(app=application)
        async with (
            application.router.lifespan_context(application),
            httpx.AsyncClient(transport=transport, base_url="http://test") as http,
        ):
            created = await http.post(f"/corpora/{aurora.id}/workflow-runs")
            assert created.status_code == 201
            run = created.json()
            session_id = run["review_session_id"]
            items = await http.get(f"/corpora/{aurora.id}/review-sessions/{session_id}/items")
            required = [item for item in items.json() if item["review_required"]]
            first = required[0]

            http_cross = await http.post(
                f"/corpora/{harbor.id}/review-sessions/{session_id}/items/{first['id']}/decisions",
                json={"action": "approve", "decision_source": "api"},
            )
            mcp_cross = await call_err(
                mcp_client,
                "approve_review_item",
                {
                    "corpus_id": harbor.id,
                    "review_session_id": session_id,
                    "item_id": first["id"],
                },
            )
            assert http_cross.status_code == 404
            assert http_cross.json()["code"] == mcp_cross["code"] == "review_session_not_found"

            http_incomplete = await http.post(
                f"/corpora/{aurora.id}/review-sessions/{session_id}/complete"
            )
            mcp_incomplete = await call_err(
                mcp_client,
                "complete_review",
                {"corpus_id": aurora.id, "review_session_id": session_id},
            )
            assert http_incomplete.status_code == 400
            assert (
                http_incomplete.json()["code"]
                == mcp_incomplete["code"]
                == "review_session_incomplete"
            )

            http_unacked = await http.post(
                f"/corpora/{aurora.id}/review-sessions/{session_id}/items/{first['id']}/decisions",
                json={
                    "action": "edit",
                    "edited_content": "HTTP unacked",
                    "reviewer_authored_acknowledged": False,
                },
            )
            mcp_unacked = await call_err(
                mcp_client,
                "edit_review_item",
                {
                    "corpus_id": aurora.id,
                    "review_session_id": session_id,
                    "item_id": first["id"],
                    "edited_content": "MCP unacked",
                    "reviewer_authored_acknowledged": False,
                },
            )
            assert http_unacked.status_code == 400
            assert (
                http_unacked.json()["code"]
                == mcp_unacked["code"]
                == "reviewer_authored_acknowledgement_required"
            )

            remaining = await http.get(f"/corpora/{aurora.id}/review-sessions/{session_id}/items")
            for item in remaining.json():
                if item["review_required"] and item["review_status"] == "pending":
                    decided = await http.post(
                        f"/corpora/{aurora.id}/review-sessions/{session_id}/items/{item['id']}/decisions",
                        json={"action": "approve", "decision_source": "api"},
                    )
                    assert decided.status_code == 201
            completed = await http.post(
                f"/corpora/{aurora.id}/review-sessions/{session_id}/complete"
            )
            assert completed.status_code == 200
            finished = await http.post(f"/corpora/{aurora.id}/workflow-runs/{run['id']}/resume")
            assert finished.status_code == 200
            assert finished.json()["status"] == "completed"
            http_resume = await http.post(f"/corpora/{aurora.id}/workflow-runs/{run['id']}/resume")
            mcp_resume = await call_err(
                mcp_client,
                "resume_workflow",
                {"corpus_id": aurora.id, "workflow_run_id": run["id"]},
            )
            assert http_resume.status_code == 400
            assert (
                http_resume.json()["code"] == mcp_resume["code"] == "workflow_run_already_completed"
            )


@pytest.mark.integration
async def test_mcp_and_http_stale_incremental_baseline_match(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
    tmp_path: Path,
) -> None:
    phase02, _storage = phase02_service
    aurora, incremental = await prepare_incremental_corpus(
        phase02, corpus_fixtures / "aurora-control-hub"
    )
    async with in_memory_mcp(phase02) as (mcp_client, services):
        application = create_app(
            phase02_service=phase02,
            understand_service=services.understand,
            examine_service=services.examine,
            review_service=services.review,
            incremental_service=incremental,
        )
        transport = httpx.ASGITransport(app=application)
        async with (
            application.router.lifespan_context(application),
            httpx.AsyncClient(transport=transport, base_url="http://test") as http,
        ):
            current = await http.get(f"/corpora/{aurora.id}/revisions/current")
            baseline_id = current.json()["id"]
            changed = tmp_path / "decision-log.txt"
            source = (corpus_fixtures / "aurora-control-hub" / "decision-log.txt").read_text(
                encoding="utf-8"
            )
            changed.write_text(source.replace("2026-10-30", "2026-12-01"), encoding="utf-8")
            await phase02.ingest(
                corpus_id=aurora.id,
                logical_name="Decision Log",
                declared_format="txt",
                upload=fixture_upload(changed, "txt"),
            )
            first = await http.post(
                f"/corpora/{aurora.id}/incremental-runs",
                json={"baseline_revision_id": baseline_id},
            )
            assert first.status_code == 201
            stale_http = await http.post(
                f"/corpora/{aurora.id}/incremental-runs",
                json={"baseline_revision_id": baseline_id},
            )
            stale_mcp = await call_err(
                mcp_client,
                "start_incremental_run",
                {
                    "corpus_id": aurora.id,
                    "baseline_revision_id": UUID(baseline_id),
                },
            )
            assert stale_http.status_code == 409
            assert stale_http.json()["code"] == stale_mcp["code"] == "stale_baseline"
            evidence = await call_ok(
                mcp_client,
                "get_incremental_evidence",
                {"corpus_id": aurora.id, "incremental_run_id": first.json()["id"]},
            )
            assert evidence["status"] == "completed"
            http_evidence = await http.get(
                f"/corpora/{aurora.id}/incremental-runs/{first.json()['id']}/evidence"
            )
            assert http_evidence.status_code == 200
            assert http_evidence.json()["evidence"]["full_rerun"] is False
            assert evidence["evidence"]["full_rerun"] is False
