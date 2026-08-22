from uuid import uuid4

import httpx
import pytest
from helpers import complete_required_review, ingest_text, make_review
from sqlalchemy import select

from app.errors import ValidationError
from app.main import create_app
from app.models import Corpus, ReviewDecision, ReviewSession
from app.review_service import ReviewService
from app.schemas import ReviewDecisionCreate
from app.services import Phase02Service
from app.storage import LocalFileStorage


async def _open_conflict_review(
    phase02: Phase02Service,
) -> tuple[Corpus, ReviewService, ReviewSession, bool]:
    corpus = await phase02.create_corpus(
        name="Review Gate",
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
    review = make_review(phase02)
    analysis = await review.examine.understand.create_run(corpus.id)
    examination = await review.examine.create_run(corpus.id, analysis.id)
    session, created = await review.create_session(corpus.id, examination.id)
    return corpus, review, session, created


@pytest.mark.integration
@pytest.mark.adversarial
async def test_human_review_remains_explicit_irreversible_gate(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
) -> None:
    phase02, _storage = phase02_service
    corpus, review, session, created = await _open_conflict_review(phase02)
    assert created is True
    assert session.status == "waiting_for_review"
    assert session.pending_count > 0
    items = await review.list_items(corpus.id, session.id)
    required = [item for item in items if item.review_required]
    assert required
    assert all(item.review_status == "pending" for item in required)
    async with phase02.session_factory() as db_session:
        assert list(await db_session.scalars(select(ReviewDecision))) == []

    target = required[0]
    with pytest.raises(ValidationError) as blank:
        await review.record_decision(
            corpus.id,
            session.id,
            target.id,
            ReviewDecisionCreate(
                action="edit",
                edited_content="   ",
                reviewer_authored_acknowledged=True,
                decision_source="api",
            ),
        )
    assert blank.value.code == "edit_content_required"

    with pytest.raises(ValidationError) as ack:
        await review.record_decision(
            corpus.id,
            session.id,
            target.id,
            ReviewDecisionCreate(
                action="edit",
                edited_content="Reviewer restates the gap.",
                reviewer_authored_acknowledged=False,
                decision_source="api",
            ),
        )
    assert ack.value.code == "reviewer_authored_acknowledgement_required"

    with pytest.raises(ValidationError) as smuggle:
        await review.record_decision(
            corpus.id,
            session.id,
            target.id,
            ReviewDecisionCreate(
                action="approve",
                edited_content="smuggled replacement",
                decision_source="api",
            ),
        )
    assert smuggle.value.code == "edit_content_not_allowed"

    first = await review.record_decision(
        corpus.id,
        session.id,
        target.id,
        ReviewDecisionCreate(action="approve", decision_source="api"),
    )
    second = await review.record_decision(
        corpus.id,
        session.id,
        target.id,
        ReviewDecisionCreate(action="reject", decision_source="api", comment="changed mind"),
    )
    assert first.decision.id != second.decision.id
    reloaded = await review.get_item(corpus.id, session.id, target.id)
    assert reloaded.review_status == "rejected"
    assert [item.action for item in reloaded.decisions] == ["approve", "reject"]

    with pytest.raises(ValidationError) as incomplete:
        await review.complete_session(corpus.id, session.id)
    assert incomplete.value.code == "review_session_incomplete"

    await complete_required_review(review, corpus.id, session.id)
    completed = await review.get_session(corpus.id, session.id)
    assert completed.status == "completed"

    with pytest.raises(ValidationError) as after:
        await review.record_decision(
            corpus.id,
            session.id,
            target.id,
            ReviewDecisionCreate(action="approve", decision_source="api"),
        )
    assert after.value.code == "review_session_already_completed"

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
        mutation = await client.post(
            f"/corpora/{corpus.id}/review-sessions/{session.id}/items/{target.id}/decisions",
            json={"action": "approve", "decision_source": "api"},
        )
        assert mutation.status_code == 400
        assert mutation.json()["code"] == "review_session_already_completed"
        assert "traceback" not in mutation.text.casefold()
        missing = await client.post(f"/corpora/{uuid4()}/review-sessions/{session.id}/complete")
        assert missing.status_code == 404
