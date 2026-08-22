from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from helpers import ingest_corpus, make_publication, make_workflow

from app.main import create_app
from app.publication_service import PublicationService
from app.services import Phase02Service
from app.storage import LocalFileStorage
from app.workflow_service import WorkflowService


def _client_app(
    phase02: Phase02Service,
    workflow: WorkflowService,
    publication: PublicationService,
) -> Any:
    return create_app(
        phase02_service=phase02,
        understand_service=workflow.examine.understand,
        examine_service=workflow.examine,
        review_service=workflow.review,
        workflow_service=workflow,
        publication_service=publication,
    )


async def _publish_mixed_workflow(client: httpx.AsyncClient, corpus_id: object) -> dict[str, Any]:
    created = await client.post(f"/corpora/{corpus_id}/workflow-runs")
    assert created.status_code == 201
    run = created.json()
    assert run["status"] == "waiting_for_review"
    session_id = run["review_session_id"]
    items = (await client.get(f"/corpora/{corpus_id}/review-sessions/{session_id}/items")).json()
    required = [item for item in items if item["review_required"]]
    assert required
    readiness = next(
        (item for item in required if item["rule_id"] == "spa.milestone.production-readiness"),
        required[0],
    )
    reject_target = next((item for item in required if item["id"] != readiness["id"]), None)
    edit_target = next(
        (
            item
            for item in reversed(required)
            if item["id"] not in {readiness["id"], reject_target["id"] if reject_target else ""}
        ),
        None,
    )
    await client.post(
        f"/corpora/{corpus_id}/review-sessions/{session_id}/items/{readiness['id']}/decisions",
        json={"action": "approve", "decision_source": "api"},
    )
    if reject_target is not None:
        await client.post(
            f"/corpora/{corpus_id}/review-sessions/{session_id}/items/{reject_target['id']}/decisions",
            json={"action": "reject", "decision_source": "api"},
        )
    if edit_target is not None:
        await client.post(
            f"/corpora/{corpus_id}/review-sessions/{session_id}/items/{edit_target['id']}/decisions",
            json={
                "action": "edit",
                "edited_content": (
                    "Reviewer-authored restatement distinguished from grounded evidence."
                ),
                "reviewer_authored_acknowledged": True,
                "decision_source": "api",
            },
        )
    remaining = (
        await client.get(f"/corpora/{corpus_id}/review-sessions/{session_id}/items")
    ).json()
    for item in remaining:
        if item["review_required"] and item["review_status"] == "pending":
            await client.post(
                f"/corpora/{corpus_id}/review-sessions/{session_id}/items/{item['id']}/decisions",
                json={"action": "approve", "decision_source": "api"},
            )
    completed = await client.post(f"/corpora/{corpus_id}/review-sessions/{session_id}/complete")
    assert completed.json()["status"] == "completed"
    resumed = await client.post(f"/corpora/{corpus_id}/workflow-runs/{run['id']}/resume")
    assert resumed.json()["status"] == "completed"
    usage = await client.get(f"/corpora/{corpus_id}/workflow-runs/{run['id']}/usage")
    assert usage.status_code == 200
    usage_body = usage.json()
    assert usage_body["stages"]
    assert usage_body["duration_basis"] == "outer_workflow_events"
    assert usage_body["total_duration_ms"] == sum(
        stage["duration_ms"] or 0 for stage in usage_body["stages"] if stage["graph"] == "workflow"
    )
    assert usage_body["cost_basis"] == "zero_deterministic"
    assert usage_body["estimated_cost_usd"] == 0
    assert (
        "pricing" in usage_body["pricing_basis"].casefold()
        or "deterministic" in usage_body["pricing_basis"].casefold()
    )
    unpublished = await client.get(f"/corpora/{corpus_id}/register")
    assert unpublished.status_code == 404
    published = await client.post(f"/corpora/{corpus_id}/review-sessions/{session_id}/publish")
    assert published.status_code == 201
    body = cast(dict[str, Any], published.json())
    body["workflow_run_id"] = run["id"]
    body["rejected_rule_id"] = reject_target["rule_id"] if reject_target else ""
    body["edit_rule_id"] = edit_target["rule_id"] if edit_target else ""
    return body


@pytest.mark.integration
async def test_final_aurora_and_harbor_acceptance_with_isolation(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, _storage = phase02_service
    aurora = await ingest_corpus(phase02, corpus_fixtures / "aurora-control-hub")
    harbor = await ingest_corpus(phase02, corpus_fixtures / "harbor-ledger-modernization")
    workflow = make_workflow(phase02)
    publication = make_publication(phase02, review=workflow.review)
    application = _client_app(phase02, workflow, publication)
    transport = httpx.ASGITransport(app=application)
    async with (
        application.router.lifespan_context(application),
        httpx.AsyncClient(transport=transport, base_url="http://test") as client,
    ):
        aurora_register = await _publish_mixed_workflow(client, aurora.id)
        harbor_register = await _publish_mixed_workflow(client, harbor.id)
        assert aurora_register["id"] != harbor_register["id"]
        assert aurora_register["corpus_id"] == str(aurora.id)
        assert harbor_register["corpus_id"] == str(harbor.id)
        aurora_quotes = {
            citation["exact_quote"]
            for item in aurora_register["items"]
            for citation in item["citations"]
        }
        harbor_quotes = {
            citation["exact_quote"]
            for item in harbor_register["items"]
            for citation in item["citations"]
        }
        assert aurora_quotes
        assert aurora_quotes != harbor_quotes
        assert not any("Aurora Control Hub" in quote for quote in harbor_quotes)
        assert "Elena Marlow" not in str(harbor_register)
        assert "Aurora Control Hub" not in str(harbor_register)
        harbor_outcomes = {item["outcome"] for item in harbor_register["items"]}
        if harbor_register["items"] and harbor_outcomes <= {"unknown"}:
            assert harbor_register["register_status"] == "insufficient_evidence"
        assert harbor_register["register_status"] != "pass"
        assert aurora_register["rejected_rule_id"] in aurora_register["omitted_rejected_rule_ids"]
        assert aurora_register["rejected_rule_id"] not in {
            item["rule_id"] for item in aurora_register["items"]
        }
        if aurora_register["edit_rule_id"]:
            edited = next(
                item
                for item in aurora_register["items"]
                if item["rule_id"] == aurora_register["edit_rule_id"]
            )
            assert edited["reviewer_authored"] is True
            assert edited["system_grounded"] is False
        readiness = next(
            (
                item
                for item in aurora_register["items"]
                if item["rule_id"] == "spa.milestone.production-readiness"
            ),
            None,
        )
        if readiness is not None:
            quotes = {citation["exact_quote"] for citation in readiness["citations"]}
            assert any("2026-10-30" in quote for quote in quotes)
            assert any("2026-11-14" in quote for quote in quotes)
        cross = await client.get(f"/corpora/{harbor.id}/register/{aurora_register['id']}")
        assert cross.status_code == 404
        current_aurora = await client.get(f"/corpora/{aurora.id}/register")
        current_harbor = await client.get(f"/corpora/{harbor.id}/register")
        assert current_aurora.json()["id"] == aurora_register["id"]
        assert current_harbor.json()["id"] == harbor_register["id"]
