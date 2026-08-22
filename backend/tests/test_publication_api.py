from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from helpers import (
    ingest_corpus,
    ingest_text,
    make_publication,
    make_review,
    mixed_review_then_complete,
)

from app.main import create_app
from app.publication_service import PublicationService
from app.review_service import ReviewService
from app.services import Phase02Service
from app.storage import LocalFileStorage


def _app(
    phase02: Phase02Service,
    publication: PublicationService | None = None,
    review: ReviewService | None = None,
) -> FastAPI:
    resolved_review = review or (
        publication.review if publication is not None else make_review(phase02)
    )
    resolved_publication = publication or make_publication(phase02, review=resolved_review)
    return create_app(
        phase02_service=phase02,
        understand_service=resolved_review.examine.understand,
        examine_service=resolved_review.examine,
        review_service=resolved_review,
        publication_service=resolved_publication,
    )


@pytest.mark.integration
async def test_publication_requires_completed_review_and_publishes_approved_only(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, _storage = phase02_service
    corpus = await ingest_corpus(phase02, corpus_fixtures / "aurora-control-hub")
    publication = make_publication(phase02)
    review = publication.review
    application = _app(phase02, publication=publication, review=review)
    transport = httpx.ASGITransport(app=application)
    async with (
        application.router.lifespan_context(application),
        httpx.AsyncClient(transport=transport, base_url="http://test") as client,
    ):
        analysis = await client.post(f"/corpora/{corpus.id}/analysis-runs")
        exam = await client.post(
            f"/corpora/{corpus.id}/analysis-runs/{analysis.json()['id']}/examination-runs"
        )
        session = await client.post(
            f"/corpora/{corpus.id}/examination-runs/{exam.json()['id']}/review-sessions"
        )
        session_id = session.json()["id"]
        pending = await client.post(f"/corpora/{corpus.id}/review-sessions/{session_id}/publish")
        assert pending.status_code == 400
        assert pending.json()["code"] == "review_session_not_completed"
        assert "traceback" not in pending.text.casefold()

        items = (
            await client.get(f"/corpora/{corpus.id}/review-sessions/{session_id}/items")
        ).json()
        required = [item for item in items if item["review_required"]]
        readiness = next(
            item for item in required if item["rule_id"] == "spa.milestone.production-readiness"
        )
        reject_target = next(item for item in required if item["id"] != readiness["id"])
        edit_target = next(
            item
            for item in reversed(required)
            if item["id"] not in {readiness["id"], reject_target["id"]}
        )
        await client.post(
            f"/corpora/{corpus.id}/review-sessions/{session_id}/items/{readiness['id']}/decisions",
            json={"action": "approve", "decision_source": "api"},
        )
        await client.post(
            f"/corpora/{corpus.id}/review-sessions/{session_id}/items/{reject_target['id']}/decisions",
            json={"action": "reject", "decision_source": "api"},
        )
        await client.post(
            f"/corpora/{corpus.id}/review-sessions/{session_id}/items/{edit_target['id']}/decisions",
            json={
                "action": "edit",
                "edited_content": "Reviewer-authored overlay, not system-grounded evidence.",
                "reviewer_authored_acknowledged": True,
                "decision_source": "api",
            },
        )
        remaining = (
            await client.get(f"/corpora/{corpus.id}/review-sessions/{session_id}/items")
        ).json()
        for item in remaining:
            if item["review_required"] and item["review_status"] == "pending":
                await client.post(
                    f"/corpora/{corpus.id}/review-sessions/{session_id}/items/{item['id']}/decisions",
                    json={"action": "approve", "decision_source": "api"},
                )
        completed = await client.post(f"/corpora/{corpus.id}/review-sessions/{session_id}/complete")
        assert completed.status_code == 200
        assert completed.json()["status"] == "completed"

        missing_current = await client.get(f"/corpora/{corpus.id}/register")
        assert missing_current.status_code == 404
        assert missing_current.json()["code"] == "publication_not_found"

        created = await client.post(f"/corpora/{corpus.id}/review-sessions/{session_id}/publish")
        assert created.status_code == 201
        body = created.json()
        assert body["status"] == "published"
        assert body["is_current"] is True
        assert body["review_session_id"] == session_id
        applied = {item["rule_id"] for item in body["items"]}
        assert reject_target["rule_id"] in body["omitted_rejected_rule_ids"]
        assert reject_target["rule_id"] not in applied
        assert "spa.milestone.production-readiness" in applied
        readiness_item = next(
            item
            for item in body["items"]
            if item["rule_id"] == "spa.milestone.production-readiness"
        )
        assert readiness_item["content_origin"] == "system_grounded"
        assert readiness_item["system_grounded"] is True
        assert readiness_item["reviewer_authored"] is False
        quotes = {citation["exact_quote"] for citation in readiness_item["citations"]}
        assert any("2026-10-30" in quote for quote in quotes)
        assert any("2026-11-14" in quote for quote in quotes)
        edited_item = next(item for item in body["items"] if item["reviewer_authored"])
        assert edited_item["content_origin"] == "mixed"
        assert edited_item["system_grounded"] is False
        assert "Reviewer-authored overlay" in edited_item["reviewer_authored_content"]
        unknown_items = [item for item in body["items"] if item["outcome"] == "unknown"]
        assert all(item["outcome"] == "unknown" for item in unknown_items)

        repeated = await client.post(f"/corpora/{corpus.id}/review-sessions/{session_id}/publish")
        assert repeated.status_code == 200
        assert repeated.json()["id"] == body["id"]
        assert repeated.json()["content_sha256"] == body["content_sha256"]

        current = await client.get(f"/corpora/{corpus.id}/register")
        assert current.status_code == 200
        assert current.json()["id"] == body["id"]
        by_id = await client.get(f"/corpora/{corpus.id}/register/{body['id']}")
        assert by_id.status_code == 200
        assert by_id.json()["version_identity"] == body["version_identity"]

        mutation = await client.post(
            f"/corpora/{corpus.id}/review-sessions/{session_id}/items/{readiness['id']}/decisions",
            json={"action": "reject", "decision_source": "api"},
        )
        assert mutation.status_code == 400
        assert mutation.json()["code"] == "review_session_already_completed"


@pytest.mark.integration
async def test_publication_rejects_wrong_corpus_and_session(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, _storage = phase02_service
    aurora = await ingest_corpus(phase02, corpus_fixtures / "aurora-control-hub")
    harbor = await ingest_corpus(phase02, corpus_fixtures / "harbor-ledger-modernization")
    publication = make_publication(phase02)
    application = _app(phase02, publication=publication)
    transport = httpx.ASGITransport(app=application)
    async with (
        application.router.lifespan_context(application),
        httpx.AsyncClient(transport=transport, base_url="http://test") as client,
    ):
        aurora_analysis = await client.post(f"/corpora/{aurora.id}/analysis-runs")
        aurora_exam = await client.post(
            f"/corpora/{aurora.id}/analysis-runs/{aurora_analysis.json()['id']}/examination-runs"
        )
        aurora_session = await client.post(
            f"/corpora/{aurora.id}/examination-runs/{aurora_exam.json()['id']}/review-sessions"
        )
        harbor_analysis = await client.post(f"/corpora/{harbor.id}/analysis-runs")
        harbor_exam = await client.post(
            f"/corpora/{harbor.id}/analysis-runs/{harbor_analysis.json()['id']}/examination-runs"
        )
        harbor_session = await client.post(
            f"/corpora/{harbor.id}/examination-runs/{harbor_exam.json()['id']}/review-sessions"
        )
        await mixed_review_then_complete(publication.review, aurora.id, aurora_session.json()["id"])
        published = await client.post(
            f"/corpora/{aurora.id}/review-sessions/{aurora_session.json()['id']}/publish"
        )
        assert published.status_code == 201
        wrong_corpus = await client.post(
            f"/corpora/{harbor.id}/review-sessions/{aurora_session.json()['id']}/publish"
        )
        assert wrong_corpus.status_code == 404
        assert wrong_corpus.json()["code"] == "review_session_not_found"
        missing_session = await client.post(
            f"/corpora/{aurora.id}/review-sessions/{uuid4()}/publish"
        )
        assert missing_session.status_code == 404
        cross_get = await client.get(f"/corpora/{harbor.id}/register/{published.json()['id']}")
        assert cross_get.status_code == 404
        assert cross_get.json()["code"] == "publication_not_found"
        pending_harbor = await client.post(
            f"/corpora/{harbor.id}/review-sessions/{harbor_session.json()['id']}/publish"
        )
        assert pending_harbor.status_code == 400
        assert pending_harbor.json()["code"] == "review_session_not_completed"


@pytest.mark.integration
async def test_empty_corpus_publication_is_honest_no_findings(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
) -> None:
    phase02, _storage = phase02_service
    corpus = await phase02.create_corpus(
        name="Blank notes",
        domain="software-project-assurance",
        declared_formats=["txt"],
    )
    await ingest_text(
        phase02,
        corpus.id,
        "Blank",
        "This page intentionally left blank.\nWeather notes: sunny.",
    )
    publication = make_publication(phase02)
    review = publication.review
    analysis = await review.examine.understand.create_run(corpus.id)
    exam = await review.examine.create_run(corpus.id, analysis.id)
    session, _created = await review.create_session(corpus.id, exam.id)
    completed = await review.complete_session(corpus.id, session.id)
    assert completed.status == "completed"
    register, created = await publication.publish(corpus.id, session.id)
    assert created is True
    assert register.register_status == "no_findings"
    assert register.items == []
    assert all(item.outcome != "pass" for item in register.items)
