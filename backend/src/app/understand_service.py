"""Application service for corpus-scoped Understand runs."""

from uuid import UUID, uuid4

from sqlalchemy import select

from app.config import Settings
from app.db import SessionFactory
from app.errors import NotFoundError
from app.model_gateway import ModelAdapter, create_model_adapter
from app.models import AnalysisRun, Contradiction, Fact, StageEvent
from app.schemas import (
    AnalysisRunResponse,
    BlockClassificationResponse,
    ContradictionResponse,
    FactResponse,
    RejectedAssertionResponse,
    StageEventResponse,
    UnderstandingResponse,
)
from app.services import Phase02Service
from app.taxonomy import GRAPH_VERSION, INSPECTION_FIELDS, TAXONOMY_VERSION
from app.understand_graph import UnderstandWorkflow, utcnow


class UnderstandService:
    def __init__(
        self,
        session_factory: SessionFactory,
        phase02: Phase02Service,
        adapter: ModelAdapter | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.phase02 = phase02
        self.adapter = adapter or create_model_adapter(settings or Settings())
        self.workflow = UnderstandWorkflow(
            session_factory=session_factory,
            phase02=phase02,
            adapter=self.adapter,
        )

    async def create_run(self, corpus_id: UUID) -> AnalysisRun:
        await self.phase02.get_corpus(corpus_id)
        run = AnalysisRun(
            id=uuid4(),
            corpus_id=corpus_id,
            status="running",
            findings_status="pending",
            started_at=utcnow(),
            model_provider_mode=self.adapter.mode,
            model_name=self.adapter.model_name,
            taxonomy_version=TAXONOMY_VERSION,
            graph_version=GRAPH_VERSION,
            configuration={
                "inspection_fields": [
                    {"category": field.category, "subject_key": field.subject_key}
                    for field in INSPECTION_FIELDS
                ]
            },
            result_payload={},
        )
        async with self.session_factory() as session:
            session.add(run)
            await session.commit()
            await session.refresh(run)
        await self.workflow.ainvoke(corpus_id, run.id)
        return await self.get_run(corpus_id, run.id)

    async def get_run(self, corpus_id: UUID, run_id: UUID) -> AnalysisRun:
        await self.phase02.get_corpus(corpus_id)
        async with self.session_factory() as session:
            run = await session.scalar(
                select(AnalysisRun).where(
                    AnalysisRun.id == run_id,
                    AnalysisRun.corpus_id == corpus_id,
                )
            )
            if run is None:
                raise _run_not_found()
            return run

    async def list_facts(self, corpus_id: UUID, run_id: UUID) -> list[Fact]:
        await self.get_run(corpus_id, run_id)
        async with self.session_factory() as session:
            facts = await session.scalars(
                select(Fact)
                .where(Fact.run_id == run_id, Fact.corpus_id == corpus_id)
                .order_by(Fact.support_status, Fact.category, Fact.subject_key, Fact.id)
            )
            return list(facts)

    async def list_contradictions(self, corpus_id: UUID, run_id: UUID) -> list[Contradiction]:
        await self.get_run(corpus_id, run_id)
        async with self.session_factory() as session:
            rows = await session.scalars(
                select(Contradiction)
                .where(
                    Contradiction.run_id == run_id,
                    Contradiction.corpus_id == corpus_id,
                )
                .order_by(Contradiction.created_at, Contradiction.id)
            )
            return list(rows)

    async def list_contradiction_responses(
        self, corpus_id: UUID, run_id: UUID
    ) -> list[ContradictionResponse]:
        facts = await self.list_facts(corpus_id, run_id)
        fact_by_id = {fact.id: fact for fact in facts}
        return [
            _contradiction_response(item, fact_by_id)
            for item in await self.list_contradictions(corpus_id, run_id)
        ]

    async def list_stage_events(self, corpus_id: UUID, run_id: UUID) -> list[StageEvent]:
        await self.get_run(corpus_id, run_id)
        async with self.session_factory() as session:
            events = await session.scalars(
                select(StageEvent)
                .where(StageEvent.run_id == run_id, StageEvent.corpus_id == corpus_id)
                .order_by(StageEvent.started_at, StageEvent.created_at, StageEvent.id)
            )
            return list(events)

    async def get_understanding(self, corpus_id: UUID, run_id: UUID) -> UnderstandingResponse:
        run = await self.get_run(corpus_id, run_id)
        facts = await self.list_facts(corpus_id, run_id)
        contradictions = await self.list_contradictions(corpus_id, run_id)
        events = await self.list_stage_events(corpus_id, run_id)
        fact_by_id = {fact.id: fact for fact in facts}
        payload = run.result_payload or {}
        retrieval_mode = payload.get("retrieval_mode")
        return UnderstandingResponse(
            run=AnalysisRunResponse.model_validate(run),
            no_findings=bool(payload.get("no_findings", run.findings_status == "no_findings")),
            retrieval_mode=str(retrieval_mode) if retrieval_mode is not None else None,
            classifications=[
                BlockClassificationResponse.model_validate(item)
                for item in payload.get("classifications", [])
            ],
            retrieved_block_ids=[
                UUID(str(item)) for item in payload.get("retrieved_block_ids", [])
            ],
            rejected_assertions=[
                RejectedAssertionResponse.model_validate(item)
                for item in payload.get("rejected_assertions", [])
            ],
            facts=[_fact_response(fact) for fact in facts],
            contradictions=[_contradiction_response(item, fact_by_id) for item in contradictions],
            stage_events=[StageEventResponse.model_validate(event) for event in events],
        )


def _fact_response(fact: Fact) -> FactResponse:
    return FactResponse.model_validate(fact)


def _contradiction_response(
    item: Contradiction,
    fact_by_id: dict[UUID, Fact],
) -> ContradictionResponse:
    fact_a = fact_by_id[item.fact_a_id]
    fact_b = fact_by_id[item.fact_b_id]
    return ContradictionResponse(
        id=item.id,
        run_id=item.run_id,
        corpus_id=item.corpus_id,
        contradiction_type=item.contradiction_type,
        reason=item.reason,
        confidence=item.confidence,
        status=item.status,
        fact_a=_fact_response(fact_a),
        fact_b=_fact_response(fact_b),
        created_at=item.created_at,
    )


def _run_not_found() -> NotFoundError:
    return NotFoundError(
        "analysis_run_not_found",
        "The analysis run was not found in this corpus.",
        "Use an analysis run identifier returned for the same corpus.",
    )
