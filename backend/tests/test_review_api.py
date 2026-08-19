from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from helpers import ingest_corpus, make_review

from app.main import create_app
from app.services import Phase02Service
from app.storage import LocalFileStorage


@pytest.mark.integration
async def test_review_api_machine_flow_and_safe_errors(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, _storage = phase02_service
    corpus = await ingest_corpus(phase02, corpus_fixtures / "aurora-control-hub")
    review = make_review(phase02)
    application = create_app(
        phase02_service=phase02,
        understand_service=review.examine.understand,
        examine_service=review.examine,
        review_service=review,
    )
    transport = httpx.ASGITransport(app=application)
    async with (
        application.router.lifespan_context(application),
        httpx.AsyncClient(transport=transport, base_url="http://test") as client,
    ):
        analysis = await client.post(f"/corpora/{corpus.id}/analysis-runs")
        assert analysis.status_code == 201
        analysis_id = analysis.json()["id"]
        exam = await client.post(
            f"/corpora/{corpus.id}/analysis-runs/{analysis_id}/examination-runs"
        )
        assert exam.status_code == 201
        exam_id = exam.json()["id"]

        created = await client.post(
            f"/corpora/{corpus.id}/examination-runs/{exam_id}/review-sessions"
        )
        assert created.status_code == 201
        session = created.json()
        session_id = session["id"]
        assert session["status"] == "waiting_for_review"
        assert session["completion_allowed"] is False
        assert session["pending_count"] > 0
        repeated = await client.post(
            f"/corpora/{corpus.id}/examination-runs/{exam_id}/review-sessions"
        )
        assert repeated.status_code == 200
        assert repeated.json()["id"] == session_id

        items = await client.get(f"/corpora/{corpus.id}/review-sessions/{session_id}/items")
        assert items.status_code == 200
        body = items.json()
        assert body
        required = [item for item in body if item["review_required"]]
        optional = [item for item in body if not item["review_required"]]
        assert required
        assert all(item["review_status"] == "pending" for item in body)
        assert all(item["outcome"] == "pass" for item in optional)
        evidenced = next(item for item in required if item["citations"])
        citation = evidenced["citations"][0]
        assert citation["exact_quote"]
        assert citation["native_locator"]
        assert citation["source_version_id"]
        assert "score" not in citation
        readiness = next(
            item for item in body if item["rule_id"] == "spa.milestone.production-readiness"
        )
        assert readiness["outcome"] == "fail"
        assert len(readiness["citations"]) == 2
        quotes = {item["exact_quote"] for item in readiness["citations"]}
        names = {item["source_logical_name"] for item in readiness["citations"]}
        locators = {item["native_locator"] for item in readiness["citations"]}
        assert any("2026-10-30" in quote for quote in quotes)
        assert any("2026-11-14" in quote for quote in quotes)
        assert "Project Charter" in names
        assert "Weekly Status Report" in names
        assert "page[1]/block[0]" in locators
        assert "paragraph[2]" in locators
        detail = await client.get(
            f"/corpora/{corpus.id}/review-sessions/{session_id}/items/{evidenced['id']}"
        )
        assert detail.status_code == 200
        assert detail.json()["finding_id"] == evidenced["finding_id"]

        blocked = await client.post(f"/corpora/{corpus.id}/review-sessions/{session_id}/complete")
        assert blocked.status_code == 400
        assert blocked.json()["code"] == "review_session_incomplete"
        assert "traceback" not in blocked.text.casefold()

        approve = await client.post(
            f"/corpora/{corpus.id}/review-sessions/{session_id}/items/{required[0]['id']}/decisions",
            json={"action": "approve", "comment": "Accept", "decision_source": "api"},
        )
        assert approve.status_code == 201
        assert approve.json()["item"]["review_status"] == "approved"
        reject_target = required[1] if len(required) > 1 else required[0]
        reject = await client.post(
            f"/corpora/{corpus.id}/review-sessions/{session_id}/items/{reject_target['id']}/decisions",
            json={"action": "reject", "decision_source": "api"},
        )
        assert reject.status_code == 201
        assert reject.json()["item"]["review_status"] == "rejected"
        edit_target = required[-1]
        missing_edit = await client.post(
            f"/corpora/{corpus.id}/review-sessions/{session_id}/items/{edit_target['id']}/decisions",
            json={"action": "edit"},
        )
        assert missing_edit.status_code == 400
        assert missing_edit.json()["code"] == "edit_content_required"
        smuggled = await client.post(
            f"/corpora/{corpus.id}/review-sessions/{session_id}/items/{edit_target['id']}/decisions",
            json={"action": "approve", "edited_content": "smuggled text"},
        )
        assert smuggled.status_code == 400
        assert smuggled.json()["code"] == "edit_content_not_allowed"
        smuggled_reject = await client.post(
            f"/corpora/{corpus.id}/review-sessions/{session_id}/items/{edit_target['id']}/decisions",
            json={"action": "reject", "edited_content": "smuggled text"},
        )
        assert smuggled_reject.status_code == 400
        assert smuggled_reject.json()["code"] == "edit_content_not_allowed"
        unacked = await client.post(
            f"/corpora/{corpus.id}/review-sessions/{session_id}/items/{edit_target['id']}/decisions",
            json={
                "action": "edit",
                "edited_content": "Reviewer-authored restatement of the finding.",
                "reviewer_authored_acknowledged": False,
            },
        )
        assert unacked.status_code == 400
        assert unacked.json()["code"] == "reviewer_authored_acknowledgement_required"
        edited = await client.post(
            f"/corpora/{corpus.id}/review-sessions/{session_id}/items/{edit_target['id']}/decisions",
            json={
                "action": "edit",
                "edited_content": "Reviewer-authored restatement of the finding.",
                "reviewer_authored_acknowledged": True,
                "decision_source": "api",
            },
        )
        assert edited.status_code == 201
        assert edited.json()["item"]["edited_content_is_reviewer_authored"] is True
        assert edited.json()["decision"]["reviewer_authored_acknowledged"] is True
        assert edited.json()["item"]["proposed_content"]["rule_id"] == edit_target["rule_id"]

        remaining = await client.get(f"/corpora/{corpus.id}/review-sessions/{session_id}/items")
        for item in remaining.json():
            if item["review_required"] and item["review_status"] == "pending":
                decided = await client.post(
                    f"/corpora/{corpus.id}/review-sessions/{session_id}/items/{item['id']}/decisions",
                    json={"action": "approve"},
                )
                assert decided.status_code == 201

        fetched = await client.get(f"/corpora/{corpus.id}/review-sessions/{session_id}")
        assert fetched.json()["completion_allowed"] is True
        completed = await client.post(f"/corpora/{corpus.id}/review-sessions/{session_id}/complete")
        assert completed.status_code == 200
        assert completed.json()["status"] == "completed"
        assert completed.json()["completed_at"]
        after_complete = await client.post(
            f"/corpora/{corpus.id}/review-sessions/{session_id}/items/{required[0]['id']}/decisions",
            json={"action": "approve"},
        )
        assert after_complete.status_code == 400
        assert after_complete.json()["code"] == "review_session_already_completed"

        other = await client.post(
            "/corpora",
            json={
                "name": "Empty",
                "domain": "software-project-assurance",
                "declared_formats": ["txt"],
            },
        )
        leaked = await client.get(f"/corpora/{other.json()['id']}/review-sessions/{session_id}")
        assert leaked.status_code == 404
        assert leaked.json()["code"] == "review_session_not_found"
        assert "traceback" not in leaked.text.casefold()
        missing_item = await client.get(
            f"/corpora/{corpus.id}/review-sessions/{session_id}/items/{uuid4()}"
        )
        assert missing_item.status_code == 404
        assert missing_item.json()["code"] == "review_item_not_found"
        missing_session = await client.get(f"/corpora/{corpus.id}/review-sessions/{uuid4()}")
        assert missing_session.status_code == 404
        wrong_exam = await client.post(
            f"/corpora/{other.json()['id']}/examination-runs/{exam_id}/review-sessions"
        )
        assert wrong_exam.status_code == 404
        assert wrong_exam.json()["code"] == "examination_run_not_found"
