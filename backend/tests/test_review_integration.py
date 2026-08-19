import asyncio
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

import pytest
from helpers import ingest_corpus, make_review
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.errors import NotFoundError, ValidationError
from app.models import Corpus, ExaminationRun, Finding, ReviewDecision, ReviewItem, ReviewSession
from app.review_service import (
    REVIEWABLE_OUTCOMES,
    ReviewService,
    is_review_required,
    session_response,
)
from app.ruleset import RULESET_VERSION
from app.schemas import ReviewDecisionCreate, ReviewDecisionResult, ReviewItemResponse
from app.services import Phase02Service
from app.storage import LocalFileStorage


def test_fail_warning_unknown_require_review_and_pass_does_not() -> None:
    assert is_review_required("fail")
    assert is_review_required("warning")
    assert is_review_required("unknown")
    assert not is_review_required("pass")
    assert {"fail", "warning", "unknown"} == REVIEWABLE_OUTCOMES


@pytest.mark.integration
async def test_review_session_maps_findings_and_is_idempotent(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, _storage = phase02_service
    corpus = await ingest_corpus(phase02, corpus_fixtures / "aurora-control-hub")
    review = make_review(phase02)
    analysis = await review.examine.understand.create_run(corpus.id)
    examination = await review.examine.create_run(corpus.id, analysis.id)
    session, created = await review.create_session(corpus.id, examination.id)
    again, created_again = await review.create_session(corpus.id, examination.id)
    items = await review.list_items(corpus.id, session.id)
    findings = await review.examine.list_finding_responses(corpus.id, examination.id)

    assert created is True
    assert created_again is False
    assert again.id == session.id
    assert session.status == "waiting_for_review"
    assert session.completed_at is None
    assert session.proposal_set_version == 1
    assert {item.finding_id for item in items} == {finding.id for finding in findings}
    assert [item.rule_id for item in items] == sorted(item.rule_id for item in items)
    required = [item for item in items if item.review_required]
    optional = [item for item in items if not item.review_required]
    assert {item.outcome for item in required} <= REVIEWABLE_OUTCOMES
    assert all(item.outcome == "pass" for item in optional)
    assert all(item.review_status == "pending" for item in items)
    assert session.pending_count == len(required)
    assert session.required_item_count == len(required)
    assert session.optional_item_count == len(optional)
    assert session.approved_count == 0
    assert session_response(session).completion_allowed is False
    fail_item = next(item for item in items if item.outcome == "fail" and item.citations)
    assert fail_item.citations[0].exact_quote
    assert fail_item.citations[0].native_locator
    assert fail_item.citations[0].source_logical_name
    readiness = next(item for item in items if item.rule_id == "spa.milestone.production-readiness")
    assert readiness.outcome == "fail"
    assert len(readiness.citations) == 2
    quotes = {citation.exact_quote for citation in readiness.citations}
    names = {citation.source_logical_name for citation in readiness.citations}
    locators = {citation.native_locator for citation in readiness.citations}
    assert any("2026-10-30" in quote for quote in quotes)
    assert any("2026-11-14" in quote for quote in quotes)
    assert "Project Charter" in names
    assert "Weekly Status Report" in names
    assert "page[1]/block[0]" in locators
    assert "paragraph[2]" in locators
    assert all("score" not in item.proposed_content for item in items)
    assert all(
        "vector" not in citation.model_dump() for item in items for citation in item.citations
    )


@pytest.mark.integration
async def test_incomplete_or_failed_examination_cannot_open_review(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, _storage = phase02_service
    corpus = await ingest_corpus(phase02, corpus_fixtures / "aurora-control-hub")
    review = make_review(phase02)
    analysis = await review.examine.understand.create_run(corpus.id)
    failed_id = uuid4()
    async with phase02.session_factory() as session:
        session.add(
            ExaminationRun(
                id=failed_id,
                corpus_id=corpus.id,
                analysis_run_id=analysis.id,
                status="failed",
                findings_status="failed",
                ruleset_version=RULESET_VERSION,
                graph_version="examine.v1",
                result_payload={},
            )
        )
        await session.commit()
    with pytest.raises(ValidationError) as not_reviewable:
        await review.create_session(corpus.id, failed_id)
    assert not_reviewable.value.code == "examination_run_not_reviewable"


@pytest.mark.integration
async def test_approve_reject_edit_history_and_completion(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, _storage = phase02_service
    corpus = await ingest_corpus(phase02, corpus_fixtures / "aurora-control-hub")
    review = make_review(phase02)
    analysis = await review.examine.understand.create_run(corpus.id)
    examination = await review.examine.create_run(corpus.id, analysis.id)
    session, _created = await review.create_session(corpus.id, examination.id)
    items = await review.list_items(corpus.id, session.id)
    required = [item for item in items if item.review_required]
    approve_item = next(item for item in required if item.outcome == "fail")
    reject_item = next(item for item in required if item.id != approve_item.id)
    edit_item = next(item for item in required if item.id not in {approve_item.id, reject_item.id})
    original_finding_message = edit_item.message
    original_proposal = dict(edit_item.proposed_content)

    with pytest.raises(ValidationError) as incomplete:
        await review.complete_session(corpus.id, session.id)
    assert incomplete.value.code == "review_session_incomplete"
    blocked = await review.get_session(corpus.id, session.id)
    assert blocked.status == "waiting_for_review"
    assert blocked.failed_complete_attempts >= 1

    approved = await review.record_decision(
        corpus.id,
        session.id,
        approve_item.id,
        ReviewDecisionCreate(action="approve", comment="Accept the grounded finding."),
    )
    assert approved.item.review_status == "approved"
    assert approved.item.edited_content is None
    assert approved.decision.previous_status == "pending"
    assert approved.decision.new_status == "approved"
    assert approved.item.citations == approve_item.citations

    with pytest.raises(ValidationError) as missing_edit:
        await review.record_decision(
            corpus.id,
            session.id,
            edit_item.id,
            ReviewDecisionCreate(action="edit", edited_content="   "),
        )
    assert missing_edit.value.code == "edit_content_required"

    edited = await review.record_decision(
        corpus.id,
        session.id,
        edit_item.id,
        ReviewDecisionCreate(
            action="edit",
            edited_content="Reviewer restates the gap without claiming new source facts.",
            reviewer_authored_acknowledged=True,
            actor="reviewer",
            decision_source="api",
        ),
    )
    assert edited.item.review_status == "edited"
    assert edited.item.edited_content_is_reviewer_authored is True
    assert edited.decision.reviewer_authored_acknowledged is True
    assert edited.item.proposed_content == original_proposal
    assert edited.decision.edited_content_is_reviewer_authored is True
    assert edited.item.citations == edit_item.citations

    rejected = await review.record_decision(
        corpus.id,
        session.id,
        reject_item.id,
        ReviewDecisionCreate(action="reject", comment="Do not accept this finding."),
    )
    assert rejected.item.review_status == "rejected"
    assert rejected.item.proposed_content["rule_id"] == reject_item.rule_id

    remaining = [
        item
        for item in await review.list_items(corpus.id, session.id)
        if item.review_required and item.review_status == "pending"
    ]
    for item in remaining:
        await review.record_decision(
            corpus.id,
            session.id,
            item.id,
            ReviewDecisionCreate(action="approve"),
        )

    repeated = await review.record_decision(
        corpus.id,
        session.id,
        approve_item.id,
        ReviewDecisionCreate(action="reject", comment="Changed mind after a second look."),
    )
    assert repeated.item.review_status == "rejected"
    assert [decision.action for decision in repeated.item.decisions] == ["approve", "reject"]
    assert repeated.decision.previous_status == "approved"

    completed = await review.complete_session(corpus.id, session.id)
    assert completed.status == "completed"
    assert completed.completed_at is not None
    assert completed.pending_count == 0
    assert completed.approved_count + completed.rejected_count + completed.edited_count >= 3
    again = await review.complete_session(corpus.id, session.id)
    assert again.id == completed.id
    with pytest.raises(ValidationError) as already_complete:
        await review.record_decision(
            corpus.id,
            session.id,
            approve_item.id,
            ReviewDecisionCreate(action="approve"),
        )
    assert already_complete.value.code == "review_session_already_completed"

    async with phase02.session_factory() as db_session:
        finding = await db_session.scalar(select(Finding).where(Finding.id == edit_item.finding_id))
        stored_item = await db_session.scalar(
            select(ReviewItem).where(ReviewItem.id == edit_item.id)
        )
        history = list(
            await db_session.scalars(
                select(ReviewDecision)
                .where(ReviewDecision.review_item_id == approve_item.id)
                .order_by(ReviewDecision.decided_at, ReviewDecision.id)
            )
        )
    assert finding is not None
    assert finding.message == original_finding_message
    assert stored_item is not None
    assert stored_item.proposed_content == original_proposal
    assert len(history) == 2


@pytest.mark.integration
async def test_harbor_review_is_isolated_from_aurora(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, _storage = phase02_service
    aurora = await ingest_corpus(phase02, corpus_fixtures / "aurora-control-hub")
    harbor = await ingest_corpus(phase02, corpus_fixtures / "harbor-ledger-modernization")
    review = make_review(phase02)
    aurora_analysis = await review.examine.understand.create_run(aurora.id)
    harbor_analysis = await review.examine.understand.create_run(harbor.id)
    aurora_exam = await review.examine.create_run(aurora.id, aurora_analysis.id)
    harbor_exam = await review.examine.create_run(harbor.id, harbor_analysis.id)
    aurora_session, _created = await review.create_session(aurora.id, aurora_exam.id)
    harbor_session, _created_harbor = await review.create_session(harbor.id, harbor_exam.id)
    aurora_items = await review.list_items(aurora.id, aurora_session.id)
    harbor_items = await review.list_items(harbor.id, harbor_session.id)

    aurora_required = {item.rule_id: item.outcome for item in aurora_items if item.review_required}
    harbor_required = {item.rule_id: item.outcome for item in harbor_items if item.review_required}
    assert aurora_session.pending_count != harbor_session.pending_count or aurora_required != (
        harbor_required
    )
    assert aurora_required != harbor_required
    harbor_text = " ".join(item.message for item in harbor_items)
    assert "Elena Marlow" not in harbor_text
    assert "Aurora" not in harbor_text

    with pytest.raises(NotFoundError) as session_leak:
        await review.get_session(harbor.id, aurora_session.id)
    assert session_leak.value.code == "review_session_not_found"
    with pytest.raises(NotFoundError) as item_leak:
        await review.get_item(aurora.id, aurora_session.id, harbor_items[0].id)
    assert item_leak.value.code == "review_item_not_found"
    with pytest.raises(NotFoundError) as decision_leak:
        await review.record_decision(
            aurora.id,
            aurora_session.id,
            harbor_items[0].id,
            ReviewDecisionCreate(action="approve"),
        )
    assert decision_leak.value.code == "review_item_not_found"
    with pytest.raises(NotFoundError) as exam_leak:
        await review.create_session(harbor.id, aurora_exam.id)
    assert exam_leak.value.code == "examination_run_not_found"

    aurora_exam_two = await review.examine.create_run(aurora.id, aurora_analysis.id)
    aurora_session_two, _created_two = await review.create_session(aurora.id, aurora_exam_two.id)
    with pytest.raises(NotFoundError) as wrong_session:
        await review.record_decision(
            aurora.id,
            aurora_session_two.id,
            aurora_items[0].id,
            ReviewDecisionCreate(action="approve"),
        )
    assert wrong_session.value.code == "review_item_not_found"


@pytest.mark.integration
async def test_empty_examination_can_complete_after_explicit_complete(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
) -> None:
    phase02, _storage = phase02_service
    corpus = await phase02.create_corpus(
        name="Empty Review Corpus",
        domain="software-project-assurance",
        declared_formats=["txt"],
    )
    review = make_review(phase02)
    analysis = await review.examine.understand.create_run(corpus.id)
    examination = await review.examine.create_run(corpus.id, analysis.id)
    session, created = await review.create_session(corpus.id, examination.id)
    items = await review.list_items(corpus.id, session.id)
    assert created is True
    assert items == []
    assert session.pending_count == 0
    assert session.required_item_count == 0
    assert session.status == "waiting_for_review"
    assert session_response(session).completion_allowed is True
    completed = await review.complete_session(corpus.id, session.id)
    assert completed.status == "completed"


@pytest.mark.integration
async def test_review_decision_edit_constraint_rejects_blank_content(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, _storage = phase02_service
    corpus = await ingest_corpus(phase02, corpus_fixtures / "aurora-control-hub")
    review = make_review(phase02)
    analysis = await review.examine.understand.create_run(corpus.id)
    examination = await review.examine.create_run(corpus.id, analysis.id)
    session, _created = await review.create_session(corpus.id, examination.id)
    items = await review.list_items(corpus.id, session.id)
    item = next(item for item in items if item.review_required)
    async with phase02.session_factory() as db_session:
        db_session.add(
            ReviewDecision(
                review_item_id=item.id,
                review_session_id=session.id,
                corpus_id=corpus.id,
                action="edit",
                previous_status="pending",
                new_status="edited",
                original_proposed_content=dict(item.proposed_content),
                edited_content=" ",
                edited_content_is_reviewer_authored=True,
                reviewer_authored_acknowledged=True,
                actor="reviewer",
                decision_source="api",
                decided_at=session.created_at,
            )
        )
        with pytest.raises(IntegrityError):
            await db_session.commit()


async def _open_aurora_review(
    phase02: Phase02Service, corpus_fixtures: Path
) -> tuple[Corpus, ReviewService, ReviewSession, list[ReviewItemResponse]]:
    corpus = await ingest_corpus(phase02, corpus_fixtures / "aurora-control-hub")
    review = make_review(phase02)
    analysis = await review.examine.understand.create_run(corpus.id)
    examination = await review.examine.create_run(corpus.id, analysis.id)
    session, _created = await review.create_session(corpus.id, examination.id)
    items = await review.list_items(corpus.id, session.id)
    return corpus, review, session, items


@pytest.mark.integration
async def test_edit_content_and_acknowledgement_validation(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, _storage = phase02_service
    corpus, review, session, items = await _open_aurora_review(phase02, corpus_fixtures)
    required = [item for item in items if item.review_required]
    target = required[0]
    with pytest.raises(ValidationError) as approve_edit:
        await review.record_decision(
            corpus.id,
            session.id,
            target.id,
            ReviewDecisionCreate(action="approve", edited_content="smuggled text"),
        )
    assert approve_edit.value.code == "edit_content_not_allowed"
    with pytest.raises(ValidationError) as reject_edit:
        await review.record_decision(
            corpus.id,
            session.id,
            target.id,
            ReviewDecisionCreate(action="reject", edited_content="smuggled text"),
        )
    assert reject_edit.value.code == "edit_content_not_allowed"
    with pytest.raises(ValidationError) as blank_edit:
        await review.record_decision(
            corpus.id,
            session.id,
            target.id,
            ReviewDecisionCreate(
                action="edit",
                edited_content="   ",
                reviewer_authored_acknowledged=True,
            ),
        )
    assert blank_edit.value.code == "edit_content_required"
    with pytest.raises(ValidationError) as unacked:
        await review.record_decision(
            corpus.id,
            session.id,
            target.id,
            ReviewDecisionCreate(
                action="edit",
                edited_content="Reviewer-authored restatement.",
                reviewer_authored_acknowledged=False,
            ),
        )
    assert unacked.value.code == "reviewer_authored_acknowledgement_required"
    edited = await review.record_decision(
        corpus.id,
        session.id,
        target.id,
        ReviewDecisionCreate(
            action="edit",
            edited_content="Reviewer-authored restatement.",
            reviewer_authored_acknowledged=True,
        ),
    )
    assert edited.item.review_status == "edited"
    assert edited.decision.reviewer_authored_acknowledged is True
    assert edited.decision.edited_content_is_reviewer_authored is True
    ignored_ack = await review.record_decision(
        corpus.id,
        session.id,
        required[1].id,
        ReviewDecisionCreate(action="approve", reviewer_authored_acknowledged=True),
    )
    assert ignored_ack.decision.reviewer_authored_acknowledged is False
    assert ignored_ack.item.edited_content is None


@pytest.mark.integration
async def test_concurrent_distinct_required_item_decisions_recompute_counts(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, _storage = phase02_service
    corpus, review, session, items = await _open_aurora_review(phase02, corpus_fixtures)
    required = [item for item in items if item.review_required]
    assert len(required) >= 2
    for item in required[2:]:
        await review.record_decision(
            corpus.id, session.id, item.id, ReviewDecisionCreate(action="approve")
        )
    item_a, item_b = required[0], required[1]
    barrier = asyncio.Barrier(2)

    async def decide(item_id: UUID, action: Literal["approve", "reject"]) -> ReviewDecisionResult:
        await barrier.wait()
        return await review.record_decision(
            corpus.id,
            session.id,
            item_id,
            ReviewDecisionCreate(action=action),
        )

    approved, rejected = await asyncio.gather(
        decide(item_a.id, "approve"),
        decide(item_b.id, "reject"),
    )
    assert approved.item.review_status == "approved"
    assert rejected.item.review_status == "rejected"
    current = await review.get_session(corpus.id, session.id)
    listed = await review.list_items(corpus.id, session.id)
    required_pending = [
        item for item in listed if item.review_required and item.review_status == "pending"
    ]
    assert required_pending == []
    assert current.pending_count == 0
    assert current.approved_count == 1 + len(required[2:])
    assert current.rejected_count == 1
    assert session_response(current).completion_allowed is True
    completed = await review.complete_session(corpus.id, session.id)
    assert completed.status == "completed"
    assert completed.pending_count == 0


@pytest.mark.integration
async def test_concurrent_same_item_decisions_preserve_history(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, _storage = phase02_service
    corpus, review, session, items = await _open_aurora_review(phase02, corpus_fixtures)
    target = next(item for item in items if item.review_required)
    barrier = asyncio.Barrier(2)

    async def decide(action: Literal["approve", "reject"]) -> ReviewDecisionResult:
        await barrier.wait()
        return await review.record_decision(
            corpus.id,
            session.id,
            target.id,
            ReviewDecisionCreate(action=action),
        )

    first, second = await asyncio.gather(decide("approve"), decide("reject"))
    assert {first.item.review_status, second.item.review_status} <= {"approved", "rejected"}
    stored = await review.get_item(corpus.id, session.id, target.id)
    history = stored.decisions
    assert len(history) == 2
    assert history[0].id != history[1].id
    assert history[0].previous_status == "pending"
    assert history[1].previous_status == history[0].new_status
    assert stored.review_status == history[-1].new_status
    assert (history[0].decided_at, history[0].id) <= (history[1].decided_at, history[1].id)


@pytest.mark.integration
async def test_decision_versus_completion_race_preserves_invariants(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, _storage = phase02_service
    corpus, review, session, items = await _open_aurora_review(phase02, corpus_fixtures)
    required = [item for item in items if item.review_required]
    last = required[-1]
    for item in required[:-1]:
        await review.record_decision(
            corpus.id, session.id, item.id, ReviewDecisionCreate(action="approve")
        )
    barrier = asyncio.Barrier(2)

    async def decide() -> ReviewDecisionResult:
        await barrier.wait()
        return await review.record_decision(
            corpus.id,
            session.id,
            last.id,
            ReviewDecisionCreate(action="approve"),
        )

    async def complete() -> ReviewSession:
        await barrier.wait()
        return await review.complete_session(corpus.id, session.id)

    decision_result, complete_result = await asyncio.gather(
        decide(), complete(), return_exceptions=True
    )
    current = await review.get_session(corpus.id, session.id)
    listed = await review.list_items(corpus.id, session.id)
    required_pending = [
        item for item in listed if item.review_required and item.review_status == "pending"
    ]
    assert not (current.status == "completed" and required_pending)
    assert current.pending_count == len(required_pending)
    if isinstance(decision_result, BaseException):
        assert isinstance(decision_result, ValidationError)
        assert decision_result.code == "review_session_already_completed"
        assert current.status == "completed"
        assert required_pending == []
    else:
        assert decision_result.item.review_status == "approved"
    if isinstance(complete_result, BaseException):
        assert isinstance(complete_result, ValidationError)
        assert complete_result.code == "review_session_incomplete"
        assert current.status == "waiting_for_review"
        current = await review.complete_session(corpus.id, session.id)
    assert current.status == "completed"
    assert current.pending_count == 0
    assert current.completed_at is not None
    with pytest.raises(ValidationError) as later:
        await review.record_decision(
            corpus.id,
            session.id,
            last.id,
            ReviewDecisionCreate(action="reject"),
        )
    assert later.value.code == "review_session_already_completed"


@pytest.mark.integration
async def test_completion_recomputes_counts_instead_of_cached_pending(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, _storage = phase02_service
    corpus, review, session, items = await _open_aurora_review(phase02, corpus_fixtures)
    required = [item for item in items if item.review_required]
    async with phase02.session_factory() as db_session:
        await db_session.execute(
            update(ReviewSession).where(ReviewSession.id == session.id).values(pending_count=0)
        )
        await db_session.commit()
    with pytest.raises(ValidationError) as stale_zero:
        await review.complete_session(corpus.id, session.id)
    assert stale_zero.value.code == "review_session_incomplete"
    blocked = await review.get_session(corpus.id, session.id)
    assert blocked.status == "waiting_for_review"
    assert blocked.pending_count == len(required)
    for item in required:
        await review.record_decision(
            corpus.id, session.id, item.id, ReviewDecisionCreate(action="approve")
        )
    async with phase02.session_factory() as db_session:
        await db_session.execute(
            update(ReviewSession)
            .where(ReviewSession.id == session.id)
            .values(pending_count=9, approved_count=0)
        )
        await db_session.commit()
    completed = await review.complete_session(corpus.id, session.id)
    assert completed.status == "completed"
    assert completed.pending_count == 0
    assert completed.approved_count == len(required)
    assert completed.completed_at is not None


@pytest.mark.integration
async def test_review_decision_edit_constraint_requires_acknowledgement(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, _storage = phase02_service
    corpus, review, session, items = await _open_aurora_review(phase02, corpus_fixtures)
    item = next(item for item in items if item.review_required)
    async with phase02.session_factory() as db_session:
        db_session.add(
            ReviewDecision(
                review_item_id=item.id,
                review_session_id=session.id,
                corpus_id=corpus.id,
                action="edit",
                previous_status="pending",
                new_status="edited",
                original_proposed_content=dict(item.proposed_content),
                edited_content="Reviewer restates the gap.",
                edited_content_is_reviewer_authored=True,
                reviewer_authored_acknowledged=False,
                actor="reviewer",
                decision_source="api",
                decided_at=session.created_at,
            )
        )
        with pytest.raises(IntegrityError):
            await db_session.commit()
