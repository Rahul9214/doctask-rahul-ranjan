"""Explicit item-level human review over Phase 04 examination findings."""

from __future__ import annotations

import time
from collections.abc import Sequence
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified

from app.db import SessionFactory
from app.errors import NotFoundError, ValidationError
from app.examine_graph import utcnow
from app.examine_service import ExamineService, finding_response
from app.models import (
    Contradiction,
    Fact,
    Finding,
    ReviewDecision,
    ReviewItem,
    ReviewSession,
    Source,
    SourceVersion,
)
from app.parsers import SourceFormat
from app.schemas import (
    ContradictionResponse,
    FactResponse,
    FindingResponse,
    ReviewCitation,
    ReviewDecisionCreate,
    ReviewDecisionResponse,
    ReviewDecisionResult,
    ReviewItemResponse,
    ReviewSessionResponse,
)
from app.services import Phase02Service

PROPOSAL_SET_VERSION = 1
REVIEWABLE_OUTCOMES = frozenset({"fail", "warning", "unknown"})
STATUS_BY_ACTION: dict[str, str] = {
    "approve": "approved",
    "reject": "rejected",
    "edit": "edited",
}


class ReviewService:
    def __init__(
        self,
        session_factory: SessionFactory,
        phase02: Phase02Service,
        examine: ExamineService,
    ) -> None:
        self.session_factory = session_factory
        self.phase02 = phase02
        self.examine = examine

    async def create_session(
        self, corpus_id: UUID, examination_run_id: UUID
    ) -> tuple[ReviewSession, bool]:
        started = time.perf_counter()
        await self.phase02.get_corpus(corpus_id)
        examination = await self.examine.get_run(corpus_id, examination_run_id)
        if examination.status != "completed":
            raise ValidationError(
                "examination_run_not_reviewable",
                "Human review requires a completed examination run in the same corpus.",
                "Wait for the examination run to complete, then create the review session.",
            )
        existing = await self._session_for_examination(corpus_id, examination_run_id)
        if existing is not None:
            return existing, False

        findings = await self.examine.list_findings(corpus_id, examination_run_id)
        finding_responses = await self.examine.list_finding_responses(corpus_id, examination_run_id)
        response_by_id = {item.id: item for item in finding_responses}
        session_id = uuid4()
        items = [
            _build_item(
                session_id=session_id,
                finding=finding,
                finding_view=response_by_id[finding.id],
            )
            for finding in findings
        ]
        counts = _count_items(items)
        session = ReviewSession(
            id=session_id,
            corpus_id=corpus_id,
            examination_run_id=examination_run_id,
            analysis_run_id=examination.analysis_run_id,
            status="waiting_for_review",
            proposal_set_version=PROPOSAL_SET_VERSION,
            required_item_count=counts["required_item_count"],
            optional_item_count=counts["optional_item_count"],
            pending_count=counts["pending_count"],
            approved_count=counts["approved_count"],
            rejected_count=counts["rejected_count"],
            edited_count=counts["edited_count"],
            session_creation_ms=max(0, int((time.perf_counter() - started) * 1000)),
            failed_complete_attempts=0,
            result_payload={
                "decision_counts": {"approve": 0, "reject": 0, "edit": 0},
                "authorship": "system_generated",
                "implicit_approval": False,
            },
        )
        try:
            async with self.session_factory() as db_session:
                db_session.add(session)
                await db_session.flush()
                db_session.add_all(items)
                await db_session.commit()
        except IntegrityError:
            existing = await self._session_for_examination(corpus_id, examination_run_id)
            if existing is None:
                raise
            return existing, False
        created = await self.get_session(corpus_id, session_id)
        return created, True

    async def get_session(self, corpus_id: UUID, review_session_id: UUID) -> ReviewSession:
        await self.phase02.get_corpus(corpus_id)
        async with self.session_factory() as session:
            row: ReviewSession | None = await session.scalar(
                select(ReviewSession).where(
                    ReviewSession.id == review_session_id,
                    ReviewSession.corpus_id == corpus_id,
                )
            )
            if row is None:
                raise _session_not_found()
            return row

    async def list_items(
        self, corpus_id: UUID, review_session_id: UUID
    ) -> list[ReviewItemResponse]:
        session = await self.get_session(corpus_id, review_session_id)
        return await self._item_responses(session)

    async def get_item(
        self, corpus_id: UUID, review_session_id: UUID, item_id: UUID
    ) -> ReviewItemResponse:
        session = await self.get_session(corpus_id, review_session_id)
        responses = await self._item_responses(session, item_id=item_id)
        if not responses:
            raise _item_not_found()
        return responses[0]

    async def record_decision(
        self,
        corpus_id: UUID,
        review_session_id: UUID,
        item_id: UUID,
        payload: ReviewDecisionCreate,
    ) -> ReviewDecisionResult:
        await self.phase02.get_corpus(corpus_id)
        edited_content = _normalized_edit(payload.action, payload.edited_content)
        acknowledged = _normalized_acknowledgement(
            payload.action, payload.reviewer_authored_acknowledged
        )
        new_status = STATUS_BY_ACTION[payload.action]
        comment = _optional_text(payload.comment)
        actor = payload.actor.strip()
        async with self.session_factory() as db_session:
            locked_session = await _lock_session(db_session, corpus_id, review_session_id)
            if locked_session.status != "waiting_for_review":
                raise _session_completed_error()
            if (
                payload.proposal_set_version is not None
                and payload.proposal_set_version != locked_session.proposal_set_version
            ):
                raise _stale_proposal_error()
            item = await db_session.scalar(
                select(ReviewItem)
                .where(
                    ReviewItem.id == item_id,
                    ReviewItem.review_session_id == locked_session.id,
                    ReviewItem.corpus_id == locked_session.corpus_id,
                    ReviewItem.examination_run_id == locked_session.examination_run_id,
                )
                .with_for_update()
            )
            if item is None:
                raise _item_not_found()
            previous_status = item.review_status
            decision = ReviewDecision(
                id=uuid4(),
                review_item_id=item.id,
                review_session_id=locked_session.id,
                corpus_id=corpus_id,
                action=payload.action,
                previous_status=previous_status,
                new_status=new_status,
                original_proposed_content=dict(item.proposed_content),
                edited_content=edited_content,
                edited_content_is_reviewer_authored=payload.action == "edit",
                reviewer_authored_acknowledged=acknowledged,
                comment=comment,
                actor=actor,
                decision_source=payload.decision_source,
                decided_at=utcnow(),
            )
            item.review_status = new_status
            if payload.action == "edit":
                item.current_edited_content = edited_content
                item.edited_content_is_reviewer_authored = True
            else:
                item.current_edited_content = None
                item.edited_content_is_reviewer_authored = False
            db_session.add(decision)
            await db_session.flush()
            await _recompute_counts(db_session, locked_session)
            payload_data = dict(locked_session.result_payload or {})
            decision_counts = dict(payload_data.get("decision_counts") or {})
            decision_counts[payload.action] = int(decision_counts.get(payload.action, 0)) + 1
            payload_data["decision_counts"] = {
                "approve": int(decision_counts.get("approve", 0)),
                "reject": int(decision_counts.get("reject", 0)),
                "edit": int(decision_counts.get("edit", 0)),
            }
            locked_session.result_payload = payload_data
            flag_modified(locked_session, "result_payload")
            await db_session.commit()
        session = await self.get_session(corpus_id, review_session_id)
        item_response = await self.get_item(corpus_id, review_session_id, item_id)
        latest = item_response.decisions[-1]
        return ReviewDecisionResult(
            session=session_response(session),
            item=item_response,
            decision=latest,
        )

    async def complete_session(self, corpus_id: UUID, review_session_id: UUID) -> ReviewSession:
        await self.phase02.get_corpus(corpus_id)
        async with self.session_factory() as db_session:
            current = await _lock_session(db_session, corpus_id, review_session_id)
            if current.status != "completed":
                await _recompute_counts(db_session, current)
                if current.pending_count > 0:
                    current.failed_complete_attempts += 1
                    await db_session.commit()
                    raise ValidationError(
                        "review_session_incomplete",
                        "A review session cannot complete while required items remain pending.",
                        "Submit an explicit approve, reject, or edit decision for every "
                        "required item.",
                    )
                current.status = "completed"
                current.completed_at = utcnow()
                await db_session.commit()
        return await self.get_session(corpus_id, review_session_id)

    async def _session_for_examination(
        self, corpus_id: UUID, examination_run_id: UUID
    ) -> ReviewSession | None:
        async with self.session_factory() as session:
            existing: ReviewSession | None = await session.scalar(
                select(ReviewSession).where(
                    ReviewSession.corpus_id == corpus_id,
                    ReviewSession.examination_run_id == examination_run_id,
                )
            )
            return existing

    async def _item_responses(
        self,
        session: ReviewSession,
        *,
        item_id: UUID | None = None,
    ) -> list[ReviewItemResponse]:
        async with self.session_factory() as db_session:
            item_query = (
                select(ReviewItem)
                .where(
                    ReviewItem.review_session_id == session.id,
                    ReviewItem.corpus_id == session.corpus_id,
                )
                .order_by(ReviewItem.rule_id, ReviewItem.id)
            )
            if item_id is not None:
                item_query = item_query.where(ReviewItem.id == item_id)
            items = list(await db_session.scalars(item_query))
            if item_id is not None and not items:
                return []
            finding_ids = [item.finding_id for item in items]
            findings = list(
                await db_session.scalars(
                    select(Finding)
                    .options(
                        selectinload(Finding.fact_evidence),
                        selectinload(Finding.contradiction_evidence),
                    )
                    .where(
                        Finding.corpus_id == session.corpus_id,
                        Finding.examination_run_id == session.examination_run_id,
                        Finding.id.in_(finding_ids),
                    )
                )
            )
            findings_by_id = {finding.id: finding for finding in findings}
            fact_ids = [fact_id for finding in findings for fact_id in finding.fact_ids]
            contradiction_ids = [
                contradiction_id
                for finding in findings
                for contradiction_id in finding.contradiction_ids
            ]
            facts_by_id: dict[UUID, Fact] = {}
            if fact_ids:
                facts_by_id = {
                    fact.id: fact
                    for fact in await db_session.scalars(
                        select(Fact).where(
                            Fact.corpus_id == session.corpus_id,
                            Fact.run_id == session.analysis_run_id,
                            Fact.id.in_(fact_ids),
                        )
                    )
                }
            extra_fact_ids: set[UUID] = set()
            contradictions: list[Contradiction] = []
            if contradiction_ids:
                contradictions = list(
                    await db_session.scalars(
                        select(Contradiction).where(
                            Contradiction.corpus_id == session.corpus_id,
                            Contradiction.run_id == session.analysis_run_id,
                            Contradiction.id.in_(contradiction_ids),
                        )
                    )
                )
                extra_fact_ids = {
                    fact_id
                    for item in contradictions
                    for fact_id in (item.fact_a_id, item.fact_b_id)
                    if fact_id not in facts_by_id
                }
            if extra_fact_ids:
                for fact in await db_session.scalars(
                    select(Fact).where(
                        Fact.corpus_id == session.corpus_id,
                        Fact.run_id == session.analysis_run_id,
                        Fact.id.in_(extra_fact_ids),
                    )
                ):
                    facts_by_id[fact.id] = fact
            contradictions_by_id = {item.id: item for item in contradictions}
            version_ids = [
                UUID(str(fact.citation["source_version_id"]))
                for fact in facts_by_id.values()
                if fact.citation is not None and fact.citation.get("source_version_id")
            ]
            source_names: dict[UUID, str] = {}
            if version_ids:
                rows = await db_session.execute(
                    select(SourceVersion.id, Source.logical_name)
                    .join(
                        Source,
                        (Source.id == SourceVersion.source_id)
                        & (Source.corpus_id == SourceVersion.corpus_id),
                    )
                    .where(
                        SourceVersion.corpus_id == session.corpus_id,
                        SourceVersion.id.in_(version_ids),
                    )
                )
                source_names = {row.id: row.logical_name for row in rows}
            decisions = list(
                await db_session.scalars(
                    select(ReviewDecision)
                    .where(
                        ReviewDecision.review_session_id == session.id,
                        ReviewDecision.corpus_id == session.corpus_id,
                    )
                    .order_by(ReviewDecision.decided_at, ReviewDecision.id)
                )
            )
        decisions_by_item: dict[UUID, list[ReviewDecision]] = {}
        for decision in decisions:
            decisions_by_item.setdefault(decision.review_item_id, []).append(decision)
        return [
            item_response(
                item,
                findings_by_id[item.finding_id],
                facts_by_id,
                contradictions_by_id,
                source_names,
                decisions_by_item.get(item.id, []),
            )
            for item in items
        ]


def session_response(session: ReviewSession) -> ReviewSessionResponse:
    return ReviewSessionResponse(
        id=session.id,
        corpus_id=session.corpus_id,
        examination_run_id=session.examination_run_id,
        analysis_run_id=session.analysis_run_id,
        status=session.status,
        proposal_set_version=session.proposal_set_version,
        required_item_count=session.required_item_count,
        optional_item_count=session.optional_item_count,
        pending_count=session.pending_count,
        approved_count=session.approved_count,
        rejected_count=session.rejected_count,
        edited_count=session.edited_count,
        completion_allowed=session.status != "completed" and session.pending_count == 0,
        session_creation_ms=session.session_creation_ms,
        failed_complete_attempts=session.failed_complete_attempts,
        created_at=session.created_at,
        completed_at=session.completed_at,
    )


def item_response(
    item: ReviewItem,
    finding: Finding,
    facts_by_id: dict[UUID, Fact],
    contradictions_by_id: dict[UUID, Contradiction],
    source_names: dict[UUID, str],
    decisions: Sequence[ReviewDecision],
) -> ReviewItemResponse:
    finding_view = finding_response(finding, facts_by_id)
    cited_facts = [facts_by_id[fact_id] for fact_id in finding.fact_ids if fact_id in facts_by_id]
    contradiction_views = [
        _contradiction_response(contradictions_by_id[contradiction_id], facts_by_id)
        for contradiction_id in finding.contradiction_ids
        if contradiction_id in contradictions_by_id
    ]
    return ReviewItemResponse(
        id=item.id,
        review_session_id=item.review_session_id,
        corpus_id=item.corpus_id,
        examination_run_id=item.examination_run_id,
        finding_id=item.finding_id,
        rule_id=finding_view.rule_id,
        rule_version=finding_view.rule_version,
        title=finding_view.title,
        outcome=finding_view.outcome,
        severity=finding_view.severity,
        message=finding_view.message,
        structured_reason=dict(finding_view.structured_reason),
        evidence_kind=finding_view.evidence_kind,
        review_required=item.review_required,
        review_status=item.review_status,
        proposed_content=dict(item.proposed_content),
        edited_content=item.current_edited_content,
        edited_content_is_reviewer_authored=item.edited_content_is_reviewer_authored,
        fact_ids=list(finding_view.fact_ids),
        contradiction_ids=list(finding_view.contradiction_ids),
        citations=_review_citations(cited_facts, source_names),
        grounded_facts=[FactResponse.model_validate(fact) for fact in cited_facts],
        contradictions=contradiction_views,
        confidence=finding_view.confidence,
        created_at=item.created_at,
        decisions=[ReviewDecisionResponse.model_validate(decision) for decision in decisions],
    )


def is_review_required(outcome: str) -> bool:
    return outcome in REVIEWABLE_OUTCOMES


def _build_item(
    *,
    session_id: UUID,
    finding: Finding,
    finding_view: FindingResponse,
) -> ReviewItem:
    proposed = finding_view.model_dump(mode="json")
    proposed["authorship"] = "system_generated"
    proposed["reviewer_authored"] = False
    return ReviewItem(
        id=uuid4(),
        review_session_id=session_id,
        corpus_id=finding.corpus_id,
        examination_run_id=finding.examination_run_id,
        analysis_run_id=finding.analysis_run_id,
        finding_id=finding.id,
        rule_id=finding.rule_id,
        outcome=finding.outcome,
        severity=finding.severity,
        title=finding.title,
        review_required=is_review_required(finding.outcome),
        review_status="pending",
        proposed_content=proposed,
        current_edited_content=None,
        edited_content_is_reviewer_authored=False,
    )


def _count_items(items: Sequence[ReviewItem]) -> dict[str, int]:
    pending = approved = rejected = edited = required = optional = 0
    for item in items:
        if item.review_required:
            required += 1
            if item.review_status == "pending":
                pending += 1
        else:
            optional += 1
        if item.review_status == "approved":
            approved += 1
        elif item.review_status == "rejected":
            rejected += 1
        elif item.review_status == "edited":
            edited += 1
    return {
        "required_item_count": required,
        "optional_item_count": optional,
        "pending_count": pending,
        "approved_count": approved,
        "rejected_count": rejected,
        "edited_count": edited,
    }


def _apply_counts(session: ReviewSession, items: Sequence[ReviewItem]) -> None:
    counts = _count_items(items)
    session.required_item_count = counts["required_item_count"]
    session.optional_item_count = counts["optional_item_count"]
    session.pending_count = counts["pending_count"]
    session.approved_count = counts["approved_count"]
    session.rejected_count = counts["rejected_count"]
    session.edited_count = counts["edited_count"]


async def _lock_session(
    db_session: AsyncSession, corpus_id: UUID, review_session_id: UUID
) -> ReviewSession:
    locked: ReviewSession | None = await db_session.scalar(
        select(ReviewSession)
        .where(
            ReviewSession.id == review_session_id,
            ReviewSession.corpus_id == corpus_id,
        )
        .with_for_update()
    )
    if locked is None:
        raise _session_not_found()
    return locked


async def _recompute_counts(db_session: AsyncSession, session: ReviewSession) -> None:
    items = list(
        await db_session.scalars(
            select(ReviewItem).where(
                ReviewItem.review_session_id == session.id,
                ReviewItem.corpus_id == session.corpus_id,
            )
        )
    )
    _apply_counts(session, items)


def _review_citations(facts: Sequence[Fact], source_names: dict[UUID, str]) -> list[ReviewCitation]:
    citations: list[ReviewCitation] = []
    for fact in facts:
        if fact.citation is None:
            continue
        citation = dict(fact.citation)
        version_id = UUID(str(citation["source_version_id"]))
        citations.append(
            ReviewCitation(
                source_version_id=version_id,
                source_sha256=str(citation["source_sha256"]),
                format=cast(SourceFormat, citation["format"]),
                native_locator=str(citation["native_locator"]),
                normalized_start=int(citation["normalized_start"]),
                normalized_end=int(citation["normalized_end"]),
                exact_quote=str(citation["exact_quote"]),
                source_logical_name=source_names.get(version_id),
                source_block_id=fact.source_block_id,
            )
        )
    return citations


def _contradiction_response(
    item: Contradiction, facts_by_id: dict[UUID, Fact]
) -> ContradictionResponse:
    return ContradictionResponse(
        id=item.id,
        run_id=item.run_id,
        corpus_id=item.corpus_id,
        contradiction_type=item.contradiction_type,
        reason=item.reason,
        confidence=item.confidence,
        status=item.status,
        fact_a=FactResponse.model_validate(facts_by_id[item.fact_a_id]),
        fact_b=FactResponse.model_validate(facts_by_id[item.fact_b_id]),
        created_at=item.created_at,
    )


def _normalized_edit(action: str, edited_content: str | None) -> str | None:
    if action != "edit":
        if edited_content is not None and edited_content.strip():
            raise ValidationError(
                "edit_content_not_allowed",
                "Approve and reject decisions cannot carry edited reviewer content.",
                "Omit edited_content unless the action is edit.",
            )
        return None
    if edited_content is None or not edited_content.strip():
        raise ValidationError(
            "edit_content_required",
            "An edit decision requires non-blank reviewer-authored content.",
            "Provide edited_content that records the reviewer-authored replacement text.",
        )
    return edited_content.strip()


def _normalized_acknowledgement(action: str, acknowledged: bool) -> bool:
    if action == "edit":
        if not acknowledged:
            raise ValidationError(
                "reviewer_authored_acknowledgement_required",
                "An edit decision requires explicit acknowledgement that the text is "
                "reviewer-authored and not system-grounded evidence.",
                "Set reviewer_authored_acknowledged to true when submitting an edit.",
            )
        return True
    return False


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _session_completed_error() -> ValidationError:
    return ValidationError(
        "review_session_already_completed",
        "Completed review sessions cannot accept additional decisions.",
        "Open a new review session from a later examination run if another review is needed.",
    )


def _stale_proposal_error() -> ValidationError:
    return ValidationError(
        "proposal_set_version_mismatch",
        "The decision referenced a stale review proposal set.",
        "Reload the review session and submit the decision against the current proposal set.",
    )


def _session_not_found() -> NotFoundError:
    return NotFoundError(
        "review_session_not_found",
        "The review session was not found in this corpus.",
        "Use a review session identifier returned for the same corpus.",
    )


def _item_not_found() -> NotFoundError:
    return NotFoundError(
        "review_item_not_found",
        "The review item was not found in this review session and corpus.",
        "Use a review item identifier returned for the same session and corpus.",
    )
