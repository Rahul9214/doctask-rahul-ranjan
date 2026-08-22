"""Explicit approved-only register publication after completed human review."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import Any, Literal, cast
from uuid import UUID, uuid4

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.canonical import canonical_hash
from app.db import SessionFactory
from app.errors import NotFoundError, Phase02Error, ValidationError
from app.examine_graph import utcnow
from app.examine_service import ExamineService
from app.models import (
    Contradiction,
    CorpusRevision,
    ExaminationRun,
    Fact,
    PublicationEvent,
    PublishedRegister,
    PublishedRegisterItem,
    PublishedRegisterItemContradiction,
    PublishedRegisterItemFact,
    ReviewSession,
    Source,
    SourceVersion,
    WorkflowRun,
)
from app.review_service import ReviewService, _review_citations
from app.schemas import (
    ContradictionResponse,
    FactResponse,
    PublicationEventResponse,
    PublishedRegisterItemResponse,
    PublishedRegisterResponse,
)
from app.services import Phase02Service

APPLIED_STATUSES = frozenset({"approved", "edited"})
PUBLICATION_LOCK_PREFIX = "publish-corpus:"
SERIALIZATION_VERSION = "published-register.v1"


class PublicationService:
    def __init__(
        self,
        session_factory: SessionFactory,
        phase02: Phase02Service,
        review: ReviewService,
        examine: ExamineService,
    ) -> None:
        self.session_factory = session_factory
        self.phase02 = phase02
        self.review = review
        self.examine = examine

    def _engine(self) -> AsyncEngine:
        return cast(AsyncEngine, self.session_factory.kw["bind"])

    @asynccontextmanager
    async def _corpus_lock(self, corpus_id: UUID) -> AsyncIterator[None]:
        lock_key = f"{PUBLICATION_LOCK_PREFIX}{corpus_id}"
        async with self._engine().connect() as lock_conn:
            locked = await lock_conn.execution_options(isolation_level="AUTOCOMMIT")
            await locked.execute(
                text("SELECT pg_advisory_lock(hashtext(:key))"),
                {"key": lock_key},
            )
            try:
                yield
            finally:
                await locked.execute(
                    text("SELECT pg_advisory_unlock(hashtext(:key))"),
                    {"key": lock_key},
                )

    async def publish(
        self,
        corpus_id: UUID,
        review_session_id: UUID,
        *,
        actor: str = "reviewer",
        publication_source: Literal["api", "ui"] = "api",
    ) -> tuple[PublishedRegisterResponse, bool]:
        resolved_actor = actor.strip()
        if not resolved_actor:
            raise ValidationError(
                "publication_actor_required",
                "Publication requires a non-blank actor.",
                "Supply a non-empty actor name.",
            )
        if publication_source not in {"api", "ui"}:
            raise ValidationError(
                "publication_source_invalid",
                "Publication source must be api or ui.",
                "Use api or ui as the publication source.",
            )
        await self.phase02.get_corpus(corpus_id)
        async with self._corpus_lock(corpus_id):
            existing = await self._row_for_session(corpus_id, review_session_id)
            if existing is not None:
                return await self.get_register(corpus_id, existing.id), False
            try:
                publication_id = await self._create_publication(
                    corpus_id,
                    review_session_id,
                    actor=resolved_actor,
                    publication_source=publication_source,
                )
            except IntegrityError:
                raced = await self._row_for_session(corpus_id, review_session_id)
                if raced is None:
                    raise
                return await self.get_register(corpus_id, raced.id), False
        return await self.get_register(corpus_id, publication_id), True

    async def get_current_register(self, corpus_id: UUID) -> PublishedRegisterResponse:
        await self.phase02.get_corpus(corpus_id)
        async with self.session_factory() as session:
            row: PublishedRegister | None = await session.scalar(
                select(PublishedRegister).where(
                    PublishedRegister.corpus_id == corpus_id,
                    PublishedRegister.is_current.is_(True),
                )
            )
            if row is None:
                raise _publication_not_found()
            publication_id = row.id
        return await self.get_register(corpus_id, publication_id)

    async def get_register(
        self, corpus_id: UUID, publication_id: UUID
    ) -> PublishedRegisterResponse:
        await self.phase02.get_corpus(corpus_id)
        async with self.session_factory() as session:
            register = await session.scalar(
                select(PublishedRegister).where(
                    PublishedRegister.id == publication_id,
                    PublishedRegister.corpus_id == corpus_id,
                )
            )
            if register is None:
                raise _publication_not_found()
            items = list(
                await session.scalars(
                    select(PublishedRegisterItem)
                    .where(
                        PublishedRegisterItem.published_register_id == register.id,
                        PublishedRegisterItem.corpus_id == corpus_id,
                    )
                    .order_by(PublishedRegisterItem.rule_id, PublishedRegisterItem.id)
                )
            )
            facts_links = list(
                await session.scalars(
                    select(PublishedRegisterItemFact).where(
                        PublishedRegisterItemFact.published_register_id == register.id,
                        PublishedRegisterItemFact.corpus_id == corpus_id,
                    )
                )
            )
            contradiction_links = list(
                await session.scalars(
                    select(PublishedRegisterItemContradiction).where(
                        PublishedRegisterItemContradiction.published_register_id == register.id,
                        PublishedRegisterItemContradiction.corpus_id == corpus_id,
                    )
                )
            )
            events = list(
                await session.scalars(
                    select(PublicationEvent)
                    .where(
                        PublicationEvent.published_register_id == register.id,
                        PublicationEvent.corpus_id == corpus_id,
                    )
                    .order_by(PublicationEvent.created_at, PublicationEvent.id)
                )
            )
            fact_ids = [link.fact_id for link in facts_links]
            contradiction_ids = [link.contradiction_id for link in contradiction_links]
            facts_by_id: dict[UUID, Fact] = {}
            if fact_ids:
                facts_by_id = {
                    fact.id: fact
                    for fact in await session.scalars(
                        select(Fact).where(
                            Fact.corpus_id == corpus_id,
                            Fact.run_id == register.analysis_run_id,
                            Fact.id.in_(fact_ids),
                        )
                    )
                }
            contradictions_by_id: dict[UUID, Contradiction] = {}
            if contradiction_ids:
                loaded_contradictions = list(
                    await session.scalars(
                        select(Contradiction).where(
                            Contradiction.corpus_id == corpus_id,
                            Contradiction.run_id == register.analysis_run_id,
                            Contradiction.id.in_(contradiction_ids),
                        )
                    )
                )
                contradictions_by_id = {item.id: item for item in loaded_contradictions}
                missing_fact_ids = {
                    fact_id
                    for item in loaded_contradictions
                    for fact_id in (item.fact_a_id, item.fact_b_id)
                    if fact_id not in facts_by_id
                }
                if missing_fact_ids:
                    for fact in await session.scalars(
                        select(Fact).where(
                            Fact.corpus_id == corpus_id,
                            Fact.run_id == register.analysis_run_id,
                            Fact.id.in_(missing_fact_ids),
                        )
                    ):
                        facts_by_id[fact.id] = fact
            facts_by_item: dict[UUID, list[UUID]] = {}
            contradictions_by_item: dict[UUID, list[UUID]] = {}
            for fact_link in facts_links:
                facts_by_item.setdefault(fact_link.published_item_id, []).append(fact_link.fact_id)
            for contradiction_link in contradiction_links:
                contradictions_by_item.setdefault(contradiction_link.published_item_id, []).append(
                    contradiction_link.contradiction_id
                )
            source_names = await self._source_names(session, corpus_id, facts_by_id)
            item_views = [
                _item_view(
                    item,
                    [
                        facts_by_id[fact_id]
                        for fact_id in facts_by_item.get(item.id, [])
                        if fact_id in facts_by_id
                    ],
                    [
                        contradictions_by_id[item_id]
                        for item_id in contradictions_by_item.get(item.id, [])
                        if item_id in contradictions_by_id
                    ],
                    facts_by_id,
                    source_names,
                )
                for item in items
            ]
            omitted = [
                str(event.payload.get("rule_id"))
                for event in events
                if event.event_type == "item_omitted_rejected" and event.payload.get("rule_id")
            ]
            return PublishedRegisterResponse(
                id=register.id,
                corpus_id=register.corpus_id,
                publication_number=register.publication_number,
                is_current=register.is_current,
                review_session_id=register.review_session_id,
                examination_run_id=register.examination_run_id,
                analysis_run_id=register.analysis_run_id,
                workflow_run_id=register.workflow_run_id,
                corpus_revision_id=register.corpus_revision_id,
                status=register.status,
                register_status=register.register_status,
                version_identity=register.version_identity,
                content_sha256=register.content_sha256,
                actor=register.actor,
                publication_source=register.publication_source,
                applied_count=register.applied_count,
                rejected_omitted_count=register.rejected_omitted_count,
                pending_optional_omitted_count=register.pending_optional_omitted_count,
                edited_count=register.edited_count,
                omitted_rejected_rule_ids=omitted,
                published_at=register.published_at,
                created_at=register.created_at,
                items=item_views,
                events=[PublicationEventResponse.model_validate(event) for event in events],
            )

    async def _create_publication(
        self,
        corpus_id: UUID,
        review_session_id: UUID,
        *,
        actor: str,
        publication_source: Literal["api", "ui"],
    ) -> UUID:
        review_items = await self.review.list_items(corpus_id, review_session_id)
        async with self.session_factory() as db_session:
            locked = await _lock_session(db_session, corpus_id, review_session_id)
            if locked.status != "completed":
                raise ValidationError(
                    "review_session_not_completed",
                    "A register can be published only after the review session is completed.",
                    "Complete every required review decision, then publish explicitly.",
                )
            examination = await db_session.scalar(
                select(ExaminationRun).where(
                    ExaminationRun.id == locked.examination_run_id,
                    ExaminationRun.corpus_id == corpus_id,
                )
            )
            if examination is None or examination.status != "completed":
                raise ValidationError(
                    "examination_run_not_publishable",
                    "Publication requires a completed examination in the same corpus.",
                    "Wait for Examine to complete, finish review, then publish.",
                )
            if examination.analysis_run_id != locked.analysis_run_id:
                raise ValidationError(
                    "publication_chain_mismatch",
                    "The review session is not linked to the same analysis and examination chain.",
                    "Publish using the review session created for this examination.",
                )
            workflow_run_id = await db_session.scalar(
                select(WorkflowRun.id).where(
                    WorkflowRun.corpus_id == corpus_id,
                    WorkflowRun.review_session_id == locked.id,
                )
            )
            revision_id = await db_session.scalar(
                select(CorpusRevision.id).where(
                    CorpusRevision.corpus_id == corpus_id,
                    CorpusRevision.review_session_id == locked.id,
                )
            )
            applied = [item for item in review_items if item.review_status in APPLIED_STATUSES]
            rejected = [item for item in review_items if item.review_status == "rejected"]
            pending_optional = [
                item
                for item in review_items
                if item.review_status == "pending" and not item.review_required
            ]
            if any(
                item.review_required and item.review_status == "pending" for item in review_items
            ):
                raise ValidationError(
                    "review_session_incomplete",
                    "A register cannot be published while required review items remain pending.",
                    "Submit an explicit decision for every required item and complete review.",
                )
            try:
                await self.examine.revalidate_persisted_findings(
                    corpus_id=corpus_id,
                    analysis_run_id=locked.analysis_run_id,
                    examination_run_id=locked.examination_run_id,
                    finding_ids=[item.finding_id for item in applied],
                )
            except (Phase02Error, PydanticValidationError) as error:
                raise ValidationError(
                    "publication_evidence_validation_failed",
                    "Approved publication evidence failed exact provenance or "
                    "grounding validation.",
                    "Restore valid immutable source evidence and rerun review before publishing.",
                ) from error
            register_status = _register_status(examination.findings_status, applied)
            publication_id = uuid4()
            next_number = await _next_publication_number(db_session, corpus_id)
            canonical_items = [_canonical_item(item) for item in applied]
            content_sha256 = canonical_hash(
                {
                    "serialization": SERIALIZATION_VERSION,
                    "corpus_id": str(corpus_id),
                    "review_session_id": str(locked.id),
                    "examination_run_id": str(locked.examination_run_id),
                    "analysis_run_id": str(locked.analysis_run_id),
                    "register_status": register_status,
                    "items": canonical_items,
                    "omitted_rejected_rule_ids": sorted(item.rule_id for item in rejected),
                }
            )
            await db_session.execute(
                update(PublishedRegister)
                .where(
                    PublishedRegister.corpus_id == corpus_id,
                    PublishedRegister.is_current.is_(True),
                )
                .values(is_current=False)
            )
            register = PublishedRegister(
                id=publication_id,
                corpus_id=corpus_id,
                publication_number=next_number,
                is_current=True,
                review_session_id=locked.id,
                examination_run_id=locked.examination_run_id,
                analysis_run_id=locked.analysis_run_id,
                workflow_run_id=workflow_run_id,
                corpus_revision_id=revision_id,
                status="published",
                register_status=register_status,
                version_identity=f"register.v1.{next_number}.{content_sha256[:12]}",
                content_sha256=content_sha256,
                actor=actor,
                publication_source=publication_source,
                applied_count=len(applied),
                rejected_omitted_count=len(rejected),
                pending_optional_omitted_count=len(pending_optional),
                edited_count=sum(1 for item in applied if item.review_status == "edited"),
                configuration={
                    "serialization": SERIALIZATION_VERSION,
                    "implicit_approval": False,
                    "auto_published": False,
                },
                published_at=utcnow(),
            )
            db_session.add(register)
            await db_session.flush()
            events: list[PublicationEvent] = [
                PublicationEvent(
                    id=uuid4(),
                    published_register_id=publication_id,
                    corpus_id=corpus_id,
                    event_type="published",
                    payload={
                        "review_session_id": str(locked.id),
                        "register_status": register_status,
                        "applied_count": len(applied),
                    },
                    actor=actor,
                    publication_source=publication_source,
                )
            ]
            for item in applied:
                row_id = uuid4()
                edited = item.review_status == "edited"
                db_session.add(
                    PublishedRegisterItem(
                        id=row_id,
                        published_register_id=publication_id,
                        corpus_id=corpus_id,
                        review_session_id=locked.id,
                        review_item_id=item.id,
                        examination_run_id=locked.examination_run_id,
                        analysis_run_id=locked.analysis_run_id,
                        finding_id=item.finding_id,
                        rule_id=item.rule_id,
                        rule_version=item.rule_version,
                        outcome=item.outcome,
                        severity=item.severity,
                        title=item.title,
                        message=item.message,
                        structured_reason=dict(item.structured_reason),
                        evidence_kind=item.evidence_kind,
                        review_status=item.review_status,
                        content_origin="mixed" if edited else "system_grounded",
                        reviewer_authored_content=item.edited_content if edited else None,
                        reviewer_authored_acknowledged=edited,
                        value_hash=canonical_hash(_canonical_item(item)),
                    )
                )
                for fact_id in item.fact_ids:
                    db_session.add(
                        PublishedRegisterItemFact(
                            id=uuid4(),
                            published_item_id=row_id,
                            published_register_id=publication_id,
                            corpus_id=corpus_id,
                            analysis_run_id=locked.analysis_run_id,
                            fact_id=fact_id,
                        )
                    )
                for contradiction_id in item.contradiction_ids:
                    db_session.add(
                        PublishedRegisterItemContradiction(
                            id=uuid4(),
                            published_item_id=row_id,
                            published_register_id=publication_id,
                            corpus_id=corpus_id,
                            analysis_run_id=locked.analysis_run_id,
                            contradiction_id=contradiction_id,
                        )
                    )
                events.append(
                    PublicationEvent(
                        id=uuid4(),
                        published_register_id=publication_id,
                        corpus_id=corpus_id,
                        event_type=(
                            "item_applied_with_reviewer_edit" if edited else "item_applied"
                        ),
                        payload={
                            "rule_id": item.rule_id,
                            "review_item_id": str(item.id),
                            "content_origin": "mixed" if edited else "system_grounded",
                        },
                        actor=actor,
                        publication_source=publication_source,
                    )
                )
            for item in rejected:
                events.append(
                    PublicationEvent(
                        id=uuid4(),
                        published_register_id=publication_id,
                        corpus_id=corpus_id,
                        event_type="item_omitted_rejected",
                        payload={"rule_id": item.rule_id, "review_item_id": str(item.id)},
                        actor=actor,
                        publication_source=publication_source,
                    )
                )
            for item in pending_optional:
                events.append(
                    PublicationEvent(
                        id=uuid4(),
                        published_register_id=publication_id,
                        corpus_id=corpus_id,
                        event_type="item_omitted_pending_optional",
                        payload={"rule_id": item.rule_id, "review_item_id": str(item.id)},
                        actor=actor,
                        publication_source=publication_source,
                    )
                )
            db_session.add_all(events)
            await db_session.commit()
            return publication_id

    async def _row_for_session(
        self, corpus_id: UUID, review_session_id: UUID
    ) -> PublishedRegister | None:
        async with self.session_factory() as session:
            row: PublishedRegister | None = await session.scalar(
                select(PublishedRegister).where(
                    PublishedRegister.corpus_id == corpus_id,
                    PublishedRegister.review_session_id == review_session_id,
                )
            )
            return row

    async def _source_names(
        self,
        session: AsyncSession,
        corpus_id: UUID,
        facts_by_id: dict[UUID, Fact],
    ) -> dict[UUID, str]:
        version_ids = [
            UUID(str(fact.citation["source_version_id"]))
            for fact in facts_by_id.values()
            if fact.citation is not None
        ]
        if not version_ids:
            return {}
        rows = await session.execute(
            select(SourceVersion.id, Source.logical_name)
            .join(
                Source,
                (Source.id == SourceVersion.source_id)
                & (Source.corpus_id == SourceVersion.corpus_id),
            )
            .where(
                SourceVersion.corpus_id == corpus_id,
                SourceVersion.id.in_(version_ids),
            )
        )
        return {row.id: row.logical_name for row in rows}


def publish_lock_key(corpus_id: UUID) -> str:
    return f"{PUBLICATION_LOCK_PREFIX}{corpus_id}"


async def _lock_session(
    db_session: AsyncSession, corpus_id: UUID, review_session_id: UUID
) -> ReviewSession:
    row: ReviewSession | None = await db_session.scalar(
        select(ReviewSession)
        .where(
            ReviewSession.id == review_session_id,
            ReviewSession.corpus_id == corpus_id,
        )
        .with_for_update()
    )
    if row is None:
        raise NotFoundError(
            "review_session_not_found",
            "The review session was not found in this corpus.",
            "Use a review session identifier returned for the same corpus.",
        )
    return row


async def _next_publication_number(session: AsyncSession, corpus_id: UUID) -> int:
    current = await session.scalar(
        select(PublishedRegister.publication_number)
        .where(PublishedRegister.corpus_id == corpus_id)
        .order_by(PublishedRegister.publication_number.desc())
        .limit(1)
    )
    return int(current or 0) + 1


def _register_status(
    examination_findings_status: str,
    applied: Sequence[Any],
) -> str:
    if examination_findings_status == "no_findings":
        return "no_findings"
    if applied and all(item.outcome == "unknown" for item in applied):
        return "insufficient_evidence"
    if applied:
        return "populated"
    return "empty_after_review"


def _canonical_item(item: Any) -> dict[str, object]:
    citations = [
        {
            "source_version_id": str(citation.source_version_id),
            "source_sha256": citation.source_sha256,
            "format": citation.format,
            "native_locator": citation.native_locator,
            "normalized_start": citation.normalized_start,
            "normalized_end": citation.normalized_end,
            "exact_quote": citation.exact_quote,
            "source_logical_name": citation.source_logical_name,
        }
        for citation in item.citations
    ]
    return {
        "rule_id": item.rule_id,
        "rule_version": item.rule_version,
        "outcome": item.outcome,
        "severity": item.severity,
        "title": item.title,
        "message": item.message,
        "structured_reason": dict(item.structured_reason),
        "evidence_kind": item.evidence_kind,
        "review_status": item.review_status,
        "content_origin": "mixed" if item.review_status == "edited" else "system_grounded",
        "reviewer_authored_content": item.edited_content,
        "fact_ids": sorted(str(item_id) for item_id in item.fact_ids),
        "contradiction_ids": sorted(str(item_id) for item_id in item.contradiction_ids),
        "citations": citations,
    }


def _item_view(
    item: PublishedRegisterItem,
    facts: Sequence[Fact],
    contradictions: Sequence[Contradiction],
    facts_by_id: dict[UUID, Fact],
    source_names: dict[UUID, str],
) -> PublishedRegisterItemResponse:
    citations = _review_citations(facts, source_names)
    contradiction_views = [
        ContradictionResponse(
            id=row.id,
            run_id=row.run_id,
            corpus_id=row.corpus_id,
            contradiction_type=row.contradiction_type,
            reason=row.reason,
            confidence=row.confidence,
            status=row.status,
            fact_a=FactResponse.model_validate(facts_by_id[row.fact_a_id]),
            fact_b=FactResponse.model_validate(facts_by_id[row.fact_b_id]),
            created_at=row.created_at,
        )
        for row in contradictions
        if row.fact_a_id in facts_by_id and row.fact_b_id in facts_by_id
    ]
    return PublishedRegisterItemResponse(
        id=item.id,
        published_register_id=item.published_register_id,
        corpus_id=item.corpus_id,
        review_item_id=item.review_item_id,
        finding_id=item.finding_id,
        rule_id=item.rule_id,
        rule_version=item.rule_version,
        outcome=item.outcome,
        severity=item.severity,
        title=item.title,
        message=item.message,
        structured_reason=dict(item.structured_reason),
        evidence_kind=item.evidence_kind,
        review_status=item.review_status,
        content_origin=item.content_origin,
        system_grounded=item.content_origin == "system_grounded",
        reviewer_authored=item.content_origin == "mixed",
        reviewer_authored_content=item.reviewer_authored_content,
        reviewer_authored_acknowledged=item.reviewer_authored_acknowledged,
        value_hash=item.value_hash,
        fact_ids=[fact.id for fact in facts],
        contradiction_ids=[row.id for row in contradictions],
        citations=citations,
        grounded_facts=[FactResponse.model_validate(fact) for fact in facts],
        contradictions=contradiction_views,
    )


def _publication_not_found() -> NotFoundError:
    return NotFoundError(
        "publication_not_found",
        "The published register was not found in this corpus.",
        "Publish a completed review session in this corpus, then inspect that publication.",
    )
