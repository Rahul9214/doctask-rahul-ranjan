"""Application service for corpus-scoped Examine runs."""

from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db import SessionFactory
from app.errors import NotFoundError, ValidationError
from app.examine_graph import ExamineWorkflow, utcnow
from app.models import ExaminationRun, ExaminationStageEvent, Fact, Finding
from app.ruleset import EXAMINE_GRAPH_VERSION, RULES, RULESET_VERSION
from app.schemas import (
    CitationRequest,
    ExaminationRunResponse,
    ExaminationStageEventResponse,
    ExaminationSummaryResponse,
    FindingResponse,
)
from app.services import Phase02Service
from app.understand_service import UnderstandService


class ExamineService:
    def __init__(
        self,
        session_factory: SessionFactory,
        phase02: Phase02Service,
        understand: UnderstandService,
    ) -> None:
        self.session_factory = session_factory
        self.phase02 = phase02
        self.understand = understand
        self.workflow = ExamineWorkflow(session_factory=session_factory, phase02=phase02)

    async def create_run(self, corpus_id: UUID, analysis_run_id: UUID) -> ExaminationRun:
        await self.phase02.get_corpus(corpus_id)
        analysis = await self.understand.get_run(corpus_id, analysis_run_id)
        if analysis.status != "completed":
            raise ValidationError(
                "analysis_run_not_examinable",
                "Examine requires a completed Understand analysis run in the same corpus.",
                "Wait for the analysis run to complete, then retry examination.",
            )
        run = ExaminationRun(
            id=uuid4(),
            corpus_id=corpus_id,
            analysis_run_id=analysis_run_id,
            status="running",
            findings_status="pending",
            ruleset_version=RULESET_VERSION,
            graph_version=EXAMINE_GRAPH_VERSION,
            started_at=utcnow(),
            configuration={
                "ruleset_version": RULESET_VERSION,
                "rule_ids": [rule.rule_id for rule in RULES],
            },
            result_payload={},
        )
        async with self.session_factory() as session:
            session.add(run)
            await session.commit()
            await session.refresh(run)
        await self.workflow.ainvoke(corpus_id, run.id, analysis_run_id)
        return await self.get_run(corpus_id, run.id)

    async def get_run(self, corpus_id: UUID, examination_run_id: UUID) -> ExaminationRun:
        await self.phase02.get_corpus(corpus_id)
        async with self.session_factory() as session:
            run = await session.scalar(
                select(ExaminationRun).where(
                    ExaminationRun.id == examination_run_id,
                    ExaminationRun.corpus_id == corpus_id,
                )
            )
            if run is None:
                raise _run_not_found()
            return run

    async def list_findings(self, corpus_id: UUID, examination_run_id: UUID) -> list[Finding]:
        await self.get_run(corpus_id, examination_run_id)
        async with self.session_factory() as session:
            rows = await session.scalars(
                select(Finding)
                .options(
                    selectinload(Finding.fact_evidence),
                    selectinload(Finding.contradiction_evidence),
                )
                .where(
                    Finding.examination_run_id == examination_run_id,
                    Finding.corpus_id == corpus_id,
                )
                .order_by(Finding.rule_id, Finding.id)
            )
            return list(rows)

    async def list_finding_responses(
        self, corpus_id: UUID, examination_run_id: UUID
    ) -> list[FindingResponse]:
        run = await self.get_run(corpus_id, examination_run_id)
        findings = await self.list_findings(corpus_id, examination_run_id)
        fact_ids = [item.fact_id for finding in findings for item in finding.fact_evidence]
        facts_by_id: dict[UUID, Fact] = {}
        if fact_ids:
            async with self.session_factory() as session:
                rows = await session.scalars(
                    select(Fact).where(
                        Fact.corpus_id == corpus_id,
                        Fact.run_id == run.analysis_run_id,
                        Fact.id.in_(fact_ids),
                    )
                )
                facts_by_id = {fact.id: fact for fact in rows}
        return [finding_response(finding, facts_by_id) for finding in findings]

    async def list_stage_events(
        self, corpus_id: UUID, examination_run_id: UUID
    ) -> list[ExaminationStageEvent]:
        await self.get_run(corpus_id, examination_run_id)
        async with self.session_factory() as session:
            rows = await session.scalars(
                select(ExaminationStageEvent)
                .where(
                    ExaminationStageEvent.examination_run_id == examination_run_id,
                    ExaminationStageEvent.corpus_id == corpus_id,
                )
                .order_by(
                    ExaminationStageEvent.started_at,
                    ExaminationStageEvent.created_at,
                    ExaminationStageEvent.id,
                )
            )
            return list(rows)

    async def get_summary(
        self, corpus_id: UUID, examination_run_id: UUID
    ) -> ExaminationSummaryResponse:
        run = await self.get_run(corpus_id, examination_run_id)
        findings = await self.list_findings(corpus_id, examination_run_id)
        payload = run.result_payload or {}
        return ExaminationSummaryResponse(
            run=ExaminationRunResponse.model_validate(run),
            no_findings=bool(payload.get("no_findings", run.findings_status == "no_findings")),
            pass_count=run.pass_count,
            fail_count=run.fail_count,
            warning_count=run.warning_count,
            unknown_count=run.unknown_count,
            evaluated_rule_count=run.evaluated_rule_count,
            ruleset_version=run.ruleset_version,
            outcomes={
                "pass": run.pass_count,
                "fail": run.fail_count,
                "warning": run.warning_count,
                "unknown": run.unknown_count,
            },
            finding_rule_ids=[finding.rule_id for finding in findings],
        )


def finding_response(
    finding: Finding, facts_by_id: dict[UUID, Fact] | None = None
) -> FindingResponse:
    resolved_facts = facts_by_id or {}
    citations: list[CitationRequest] = []
    for fact_id in finding.fact_ids:
        fact = resolved_facts.get(fact_id)
        if fact is None or fact.citation is None:
            continue
        citations.append(CitationRequest.model_validate(fact.citation))
    return FindingResponse(
        id=finding.id,
        examination_run_id=finding.examination_run_id,
        corpus_id=finding.corpus_id,
        rule_id=finding.rule_id,
        rule_version=finding.rule_version,
        outcome=finding.outcome,
        severity=finding.severity,
        title=finding.title,
        message=finding.message,
        structured_reason=dict(finding.structured_reason),
        evidence_kind=finding.evidence_kind,
        fact_ids=list(finding.fact_ids),
        contradiction_ids=list(finding.contradiction_ids),
        citations=citations,
        confidence=finding.confidence,
        status=finding.status,
        created_at=finding.created_at,
    )


def stage_event_response(event: ExaminationStageEvent) -> ExaminationStageEventResponse:
    return ExaminationStageEventResponse.model_validate(event)


def _run_not_found() -> NotFoundError:
    return NotFoundError(
        "examination_run_not_found",
        "The examination run was not found in this corpus.",
        "Use an examination run identifier returned for the same corpus.",
    )
