"""LangGraph Examine workflow over grounded Phase 03 understanding."""

from __future__ import annotations

import time
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Literal, TypedDict, cast
from uuid import UUID, uuid4

from langgraph.graph import END, START, StateGraph
from sqlalchemy import select

from app.db import SessionFactory
from app.errors import NotFoundError, Phase02Error, ProvenanceError, ValidationError
from app.grounding import UNTRUSTED_CATEGORY, validate_assertion
from app.models import (
    AnalysisRun,
    Contradiction,
    ExaminationRun,
    ExaminationStageEvent,
    Fact,
    Finding,
    FindingContradictionEvidence,
    FindingFactEvidence,
    StageEvent,
)
from app.ruleset import (
    EXAMINE_GRAPH_VERSION,
    RULESET_VERSION,
    EvidenceKind,
    GroundedContradictionView,
    GroundedFactView,
    Outcome,
    RuleEvaluation,
    UnderstandingView,
    evaluate_rules,
    select_rules,
    validate_evaluation,
)
from app.schemas import CitationRequest
from app.services import Phase02Service

CANONICAL_STAGES = (
    "load_understanding",
    "select_rules",
    "evaluate_rules",
    "validate_evidence",
    "summarize_findings",
    "finalize",
)


class ExamineState(TypedDict, total=False):
    corpus_id: str
    examination_run_id: str
    analysis_run_id: str
    understanding: dict[str, object]
    selected_rule_ids: list[str]
    findings: list[dict[str, object]]
    summary: dict[str, object]
    no_findings: bool
    error_code: str
    error_detail: str
    error_action: str


def utcnow() -> datetime:
    return datetime.now(UTC)


class ExamineWorkflow:
    def __init__(self, *, session_factory: SessionFactory, phase02: Phase02Service) -> None:
        self.session_factory = session_factory
        self.phase02 = phase02
        graph = StateGraph(ExamineState)
        graph.add_node("load_understanding", self.load_understanding)
        graph.add_node("select_rules", self.select_rules_node)
        graph.add_node("evaluate_rules", self.evaluate_rules_node)
        graph.add_node("validate_evidence", self.validate_evidence)
        graph.add_node("summarize_findings", self.summarize_findings)
        graph.add_node("finalize", self.finalize)
        graph.add_edge(START, "load_understanding")
        graph.add_edge("load_understanding", "select_rules")
        graph.add_edge("select_rules", "evaluate_rules")
        graph.add_edge("evaluate_rules", "validate_evidence")
        graph.add_edge("validate_evidence", "summarize_findings")
        graph.add_edge("summarize_findings", "finalize")
        graph.add_edge("finalize", END)
        self.graph = graph.compile()

    async def ainvoke(
        self, corpus_id: UUID, examination_run_id: UUID, analysis_run_id: UUID
    ) -> ExamineState:
        result = await self.graph.ainvoke(
            {
                "corpus_id": str(corpus_id),
                "examination_run_id": str(examination_run_id),
                "analysis_run_id": str(analysis_run_id),
            }
        )
        return cast(ExamineState, result)

    async def load_understanding(self, state: ExamineState) -> ExamineState:
        started = utcnow()
        perf = time.perf_counter()
        corpus_id = UUID(state["corpus_id"])
        run_id = UUID(state["examination_run_id"])
        analysis_run_id = UUID(state["analysis_run_id"])
        try:
            await self.phase02.get_corpus(corpus_id)
            async with self.session_factory() as session:
                analysis = await session.scalar(
                    select(AnalysisRun).where(
                        AnalysisRun.id == analysis_run_id,
                        AnalysisRun.corpus_id == corpus_id,
                    )
                )
                if analysis is None:
                    raise NotFoundError(
                        "analysis_run_not_found",
                        "The analysis run was not found in this corpus.",
                        "Use an analysis run identifier returned for the same corpus.",
                    )
                if analysis.status != "completed":
                    raise ValidationError(
                        "analysis_run_not_examinable",
                        "Examine requires a completed Understand analysis run.",
                        "Wait for the analysis run to complete, then retry examination.",
                    )
                facts = list(
                    await session.scalars(
                        select(Fact).where(
                            Fact.run_id == analysis_run_id,
                            Fact.corpus_id == corpus_id,
                        )
                    )
                )
                contradictions = list(
                    await session.scalars(
                        select(Contradiction).where(
                            Contradiction.run_id == analysis_run_id,
                            Contradiction.corpus_id == corpus_id,
                        )
                    )
                )
                attested = await session.scalar(
                    select(StageEvent.id).where(
                        StageEvent.run_id == analysis_run_id,
                        StageEvent.corpus_id == corpus_id,
                        StageEvent.stage_name == "detect_contradictions",
                        StageEvent.status == "completed",
                    )
                )
                raw_classifications = (analysis.result_payload or {}).get("classifications", [])
            classifications = (
                list(raw_classifications) if isinstance(raw_classifications, list) else []
            )
            payload: dict[str, object] = {
                "analysis_run_id": str(analysis_run_id),
                "analysis_status": analysis.status,
                "analysis_findings_status": analysis.findings_status,
                "contradiction_detection_attested": attested is not None,
                "classifications": classifications,
                "facts": [_fact_payload(fact) for fact in facts],
                "contradictions": [_contradiction_payload(item) for item in contradictions],
            }
            await self._record_stage(
                run_id,
                corpus_id,
                "load_understanding",
                started,
                perf,
                "completed",
            )
            return {"understanding": payload}
        except Phase02Error as error:
            await self._record_stage(
                run_id,
                corpus_id,
                "load_understanding",
                started,
                perf,
                "failed",
                error_code=error.code,
            )
            return _error_state(error)

    async def select_rules_node(self, state: ExamineState) -> ExamineState:
        started = utcnow()
        perf = time.perf_counter()
        corpus_id = UUID(state["corpus_id"])
        run_id = UUID(state["examination_run_id"])
        if state.get("error_code"):
            await self._record_skip(run_id, corpus_id, "select_rules", started, perf)
            return {"selected_rule_ids": []}
        view = _view_from_payload(state.get("understanding", {}))
        selected = select_rules(view)
        skip_reason = "no_applicable_evidence" if not selected else None
        status = "skipped" if skip_reason else "completed"
        await self._record_stage(
            run_id,
            corpus_id,
            "select_rules",
            started,
            perf,
            status,
            skip_reason=skip_reason,
        )
        return {"selected_rule_ids": [rule.rule_id for rule in selected]}

    async def evaluate_rules_node(self, state: ExamineState) -> ExamineState:
        started = utcnow()
        perf = time.perf_counter()
        corpus_id = UUID(state["corpus_id"])
        run_id = UUID(state["examination_run_id"])
        if state.get("error_code"):
            await self._record_skip(run_id, corpus_id, "evaluate_rules", started, perf)
            return {"findings": []}
        selected_ids = state.get("selected_rule_ids", [])
        if not selected_ids:
            await self._record_stage(
                run_id,
                corpus_id,
                "evaluate_rules",
                started,
                perf,
                "skipped",
                skip_reason="no_applicable_evidence",
            )
            return {"findings": []}
        view = _view_from_payload(state.get("understanding", {}))
        selected = [rule for rule in select_rules(view) if rule.rule_id in set(selected_ids)]
        evaluations = evaluate_rules(view, selected)
        await self._record_stage(
            run_id,
            corpus_id,
            "evaluate_rules",
            started,
            perf,
            "completed",
            rule_evaluation_count=len(evaluations),
        )
        return {"findings": [_evaluation_payload(item) for item in evaluations]}

    async def validate_evidence(self, state: ExamineState) -> ExamineState:
        started = utcnow()
        perf = time.perf_counter()
        corpus_id = UUID(state["corpus_id"])
        run_id = UUID(state["examination_run_id"])
        analysis_run_id = UUID(state["analysis_run_id"])
        if state.get("error_code"):
            await self._record_skip(run_id, corpus_id, "validate_evidence", started, perf)
            return {}
        view = _view_from_payload(state.get("understanding", {}))
        findings = state.get("findings", [])
        untrusted_ids = _untrusted_block_ids(state.get("understanding", {}))
        for raw in findings:
            evaluation = _evaluation_from_payload(raw)
            reason = validate_evaluation(evaluation, view)
            if reason is not None:
                error = ValidationError(
                    "examination_evidence_invalid",
                    "An examination finding was not grounded in supported Phase 03 evidence.",
                    "Inspect the analysis run facts and contradictions, then retry.",
                )
                await self._record_stage(
                    run_id,
                    corpus_id,
                    "validate_evidence",
                    started,
                    perf,
                    "failed",
                    error_code=reason,
                )
                return _error_state(error)
            try:
                await self._revalidate_finding_evidence(
                    corpus_id=corpus_id,
                    analysis_run_id=analysis_run_id,
                    evaluation=evaluation,
                    untrusted_ids=untrusted_ids,
                )
            except Phase02Error as error:
                await self._record_stage(
                    run_id,
                    corpus_id,
                    "validate_evidence",
                    started,
                    perf,
                    "failed",
                    error_code=error.code,
                )
                return _error_state(error)
        await self._record_stage(
            run_id,
            corpus_id,
            "validate_evidence",
            started,
            perf,
            "completed",
        )
        return {}

    async def revalidate_finding_payloads(
        self,
        *,
        corpus_id: UUID,
        analysis_run_id: UUID,
        findings: Sequence[dict[str, object]],
        view: UnderstandingView,
        classifications: Sequence[dict[str, object]] = (),
    ) -> None:
        """Reuse Phase 04 citation/assertion revalidation for incremental findings."""

        untrusted_ids = _untrusted_block_ids({"classifications": list(classifications)})
        for raw in findings:
            evaluation = _evaluation_from_payload(raw)
            reason = validate_evaluation(evaluation, view)
            if reason is not None:
                raise ValidationError(
                    "examination_evidence_invalid",
                    "An examination finding was not grounded in supported Phase 03 evidence.",
                    "Inspect the analysis run facts and contradictions, then retry.",
                )
            await self._revalidate_finding_evidence(
                corpus_id=corpus_id,
                analysis_run_id=analysis_run_id,
                evaluation=evaluation,
                untrusted_ids=untrusted_ids,
            )

    async def summarize_findings(self, state: ExamineState) -> ExamineState:
        started = utcnow()
        perf = time.perf_counter()
        corpus_id = UUID(state["corpus_id"])
        run_id = UUID(state["examination_run_id"])
        if state.get("error_code"):
            await self._record_skip(run_id, corpus_id, "summarize_findings", started, perf)
            return {"summary": {}, "no_findings": False}
        findings = state.get("findings", [])
        summary = _summarize(findings)
        no_findings = summary["evaluated_rule_count"] == 0
        await self._record_stage(
            run_id,
            corpus_id,
            "summarize_findings",
            started,
            perf,
            "completed",
        )
        return {"summary": summary, "no_findings": no_findings}

    async def finalize(self, state: ExamineState) -> ExamineState:
        started = utcnow()
        perf = time.perf_counter()
        corpus_id = UUID(state["corpus_id"])
        run_id = UUID(state["examination_run_id"])
        analysis_run_id = UUID(state["analysis_run_id"])
        failed = bool(state.get("error_code"))
        findings = state.get("findings", [])
        summary = state.get("summary", {})
        findings_status: Literal["populated", "no_findings", "failed"]
        if failed:
            findings_status = "failed"
        elif not findings:
            findings_status = "no_findings"
        else:
            findings_status = "populated"
        async with self.session_factory() as session, session.begin():
            run = await session.scalar(
                select(ExaminationRun).where(
                    ExaminationRun.id == run_id,
                    ExaminationRun.corpus_id == corpus_id,
                )
            )
            if run is None:
                raise NotFoundError(
                    "examination_run_not_found",
                    "The examination run was not found in this corpus.",
                    "Create an examination run for this corpus and retry.",
                )
            if not failed:
                for item in findings:
                    reason = item.get("reason")
                    fact_ids = [UUID(str(value)) for value in _as_list(item.get("fact_ids"))]
                    contradiction_ids = [
                        UUID(str(value)) for value in _as_list(item.get("contradiction_ids"))
                    ]
                    evidence_kind = _evidence_kind_from_payload(item)
                    outcome = str(item["outcome"])
                    if outcome == "unknown" and (fact_ids or contradiction_ids):
                        raise ValidationError(
                            "unknown_must_not_claim_evidence",
                            "UNKNOWN findings cannot persist fact or contradiction evidence.",
                            "Remove evidence references from the unknown finding.",
                        )
                    if evidence_kind != "grounded_facts" and (fact_ids or contradiction_ids):
                        raise ValidationError(
                            "process_attestation_must_not_claim_source_or_fact_evidence",
                            "Process attestation cannot persist evidence rows.",
                            "Persist grounded-fact evidence only for PASS, FAIL, or WARNING.",
                        )
                    finding = Finding(
                        id=UUID(str(item["id"])),
                        examination_run_id=run_id,
                        corpus_id=corpus_id,
                        analysis_run_id=analysis_run_id,
                        rule_id=str(item["rule_id"]),
                        rule_version=str(item["rule_version"]),
                        outcome=outcome,
                        severity=str(item["severity"]),
                        title=str(item["title"]),
                        message=str(item["message"]),
                        structured_reason=dict(reason) if isinstance(reason, dict) else {},
                        evidence_kind=evidence_kind,
                        confidence=float(str(item["confidence"])),
                        status="recorded",
                    )
                    session.add(finding)
                    if evidence_kind == "grounded_facts":
                        for fact_id in fact_ids:
                            session.add(
                                FindingFactEvidence(
                                    finding_id=finding.id,
                                    examination_run_id=run_id,
                                    corpus_id=corpus_id,
                                    analysis_run_id=analysis_run_id,
                                    fact_id=fact_id,
                                    evidence_kind="grounded_facts",
                                )
                            )
                        for contradiction_id in contradiction_ids:
                            session.add(
                                FindingContradictionEvidence(
                                    finding_id=finding.id,
                                    examination_run_id=run_id,
                                    corpus_id=corpus_id,
                                    analysis_run_id=analysis_run_id,
                                    contradiction_id=contradiction_id,
                                    evidence_kind="grounded_facts",
                                )
                            )
            run.status = "failed" if failed else "completed"
            run.findings_status = findings_status
            run.completed_at = utcnow()
            run.pass_count = _as_int(summary.get("pass_count", 0)) if not failed else 0
            run.fail_count = _as_int(summary.get("fail_count", 0)) if not failed else 0
            run.warning_count = _as_int(summary.get("warning_count", 0)) if not failed else 0
            run.unknown_count = _as_int(summary.get("unknown_count", 0)) if not failed else 0
            run.evaluated_rule_count = (
                _as_int(summary.get("evaluated_rule_count", 0)) if not failed else 0
            )
            run.error_code = state.get("error_code")
            run.error_detail = state.get("error_detail")
            run.result_payload = {
                "no_findings": findings_status == "no_findings",
                "selected_rule_ids": state.get("selected_rule_ids", []),
                "summary": summary,
                "ruleset_version": RULESET_VERSION,
                "graph_version": EXAMINE_GRAPH_VERSION,
            }
        await self._record_stage(
            run_id,
            corpus_id,
            "finalize",
            started,
            perf,
            "failed" if failed else "completed",
            error_code=state.get("error_code"),
        )
        return {"no_findings": findings_status == "no_findings"}

    async def _revalidate_finding_evidence(
        self,
        *,
        corpus_id: UUID,
        analysis_run_id: UUID,
        evaluation: RuleEvaluation,
        untrusted_ids: set[UUID],
    ) -> None:
        if evaluation.outcome == "unknown" or evaluation.evidence_kind != "grounded_facts":
            return
        fact_ids = [UUID(item) for item in evaluation.fact_ids]
        for fact_id in fact_ids:
            await self._revalidate_supported_fact(
                corpus_id=corpus_id,
                analysis_run_id=analysis_run_id,
                fact_id=fact_id,
                untrusted_ids=untrusted_ids,
            )
        for contradiction_id in evaluation.contradiction_ids:
            await self._revalidate_contradiction(
                corpus_id=corpus_id,
                analysis_run_id=analysis_run_id,
                contradiction_id=UUID(contradiction_id),
                expected_fact_ids=set(fact_ids),
                untrusted_ids=untrusted_ids,
            )

    async def _revalidate_supported_fact(
        self,
        *,
        corpus_id: UUID,
        analysis_run_id: UUID,
        fact_id: UUID,
        untrusted_ids: set[UUID],
    ) -> None:
        async with self.session_factory() as session:
            fact = await session.scalar(
                select(Fact).where(
                    Fact.id == fact_id,
                    Fact.run_id == analysis_run_id,
                    Fact.corpus_id == corpus_id,
                )
            )
        if fact is None:
            raise ValidationError(
                "unknown_fact_reference",
                "A finding referenced a fact outside this analysis run and corpus.",
                "Use grounded facts from the same completed analysis run.",
            )
        if (
            fact.support_status != "supported"
            or fact.citation is None
            or fact.source_block_id is None
        ):
            raise ValidationError(
                "non_supported_fact_reference",
                "A finding referenced a fact that is not currently supported with provenance.",
                "Use supported Phase 03 facts only.",
            )
        citation = CitationRequest.model_validate(fact.citation)
        try:
            validation = await self.phase02.validate_citation(
                corpus_id=corpus_id,
                citation=citation,
            )
        except (ProvenanceError, NotFoundError, ValidationError) as error:
            raise ValidationError(
                "citation_revalidation_failed",
                "Persisted Phase 03 citation evidence failed exact provenance revalidation.",
                "Restore the original source bytes and grounded citation, then retry Examine.",
            ) from error
        if validation.source_block_id != fact.source_block_id:
            raise ValidationError(
                "source_block_mismatch",
                "The revalidated citation resolved to a different source block than the fact.",
                "Use the source block bound to the grounded fact.",
            )
        reason = validate_assertion(
            category=fact.category,
            subject_key=fact.subject_key,
            normalized_value=fact.normalized_value,
            proposed_source_block_id=fact.source_block_id,
            evidence_text=validation.resolved_quote,
            resolved_block_id=validation.source_block_id,
            untrusted_block_ids=untrusted_ids,
        )
        if reason is not None:
            raise ValidationError(
                "assertion_grounding_revalidation_failed",
                "The grounded assertion is no longer supported by revalidated source evidence.",
                "Restore the original source quote that supports the Phase 03 assertion.",
            )

    async def _revalidate_contradiction(
        self,
        *,
        corpus_id: UUID,
        analysis_run_id: UUID,
        contradiction_id: UUID,
        expected_fact_ids: set[UUID],
        untrusted_ids: set[UUID],
    ) -> None:
        async with self.session_factory() as session:
            item = await session.scalar(
                select(Contradiction).where(
                    Contradiction.id == contradiction_id,
                    Contradiction.run_id == analysis_run_id,
                    Contradiction.corpus_id == corpus_id,
                )
            )
        if item is None:
            raise ValidationError(
                "unknown_contradiction_reference",
                "A finding referenced a contradiction outside this analysis run and corpus.",
                "Use grounded contradictions from the same completed analysis run.",
            )
        if item.fact_a_id not in expected_fact_ids or item.fact_b_id not in expected_fact_ids:
            raise ValidationError(
                "contradiction_facts_not_referenced",
                "Contradiction evidence must include both grounded fact sides.",
                "Attach both contradiction facts before persisting the finding.",
            )
        for fact_id in (item.fact_a_id, item.fact_b_id):
            await self._revalidate_supported_fact(
                corpus_id=corpus_id,
                analysis_run_id=analysis_run_id,
                fact_id=fact_id,
                untrusted_ids=untrusted_ids,
            )

    async def _record_skip(
        self,
        run_id: UUID,
        corpus_id: UUID,
        stage_name: str,
        started: datetime,
        perf: float,
    ) -> None:
        await self._record_stage(
            run_id,
            corpus_id,
            stage_name,
            started,
            perf,
            "skipped",
            skip_reason="prior_stage_failed",
        )

    async def _record_stage(
        self,
        run_id: UUID,
        corpus_id: UUID,
        stage_name: str,
        started_at: datetime,
        perf: float,
        status: str,
        *,
        error_code: str | None = None,
        skip_reason: str | None = None,
        rule_evaluation_count: int = 0,
    ) -> None:
        if stage_name not in CANONICAL_STAGES:
            raise ValueError(f"unknown examine stage: {stage_name}")
        skipped = status == "skipped"
        async with self.session_factory() as session, session.begin():
            session.add(
                ExaminationStageEvent(
                    examination_run_id=run_id,
                    corpus_id=corpus_id,
                    stage_name=stage_name,
                    started_at=started_at,
                    completed_at=utcnow(),
                    duration_ms=0 if skipped else _duration_ms(perf),
                    model_operation_count=0,
                    model_attempt_count=0,
                    rule_evaluation_count=0 if skipped else rule_evaluation_count,
                    input_tokens=None,
                    output_tokens=None,
                    estimated_cost_usd=0.0,
                    cost_basis="zero_deterministic",
                    status=status,
                    error_code=error_code,
                    skip_reason=skip_reason,
                )
            )


def _as_int(value: object, default: int = 0) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default


def _as_list(value: object) -> list[object]:
    return list(value) if isinstance(value, list) else []


def _duration_ms(started: float) -> int:
    return max(0, int((time.perf_counter() - started) * 1000))


def _error_state(error: Phase02Error) -> ExamineState:
    return {
        "error_code": error.code,
        "error_detail": error.detail,
        "error_action": error.action,
        "findings": [],
        "selected_rule_ids": [],
        "no_findings": False,
    }


def _fact_payload(fact: Fact) -> dict[str, object]:
    return {
        "id": str(fact.id),
        "category": fact.category,
        "subject_key": fact.subject_key,
        "normalized_value": fact.normalized_value,
        "support_status": fact.support_status,
        "citation": fact.citation,
        "source_block_id": str(fact.source_block_id) if fact.source_block_id else None,
    }


def _contradiction_payload(item: Contradiction) -> dict[str, object]:
    return {
        "id": str(item.id),
        "contradiction_type": item.contradiction_type,
        "fact_a_id": str(item.fact_a_id),
        "fact_b_id": str(item.fact_b_id),
        "reason": item.reason,
        "status": item.status,
    }


def _untrusted_block_ids(payload: dict[str, object]) -> set[UUID]:
    raw = payload.get("classifications", [])
    items = raw if isinstance(raw, list) else []
    untrusted: set[UUID] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("category") != UNTRUSTED_CATEGORY:
            continue
        block_id = item.get("source_block_id")
        if block_id:
            untrusted.add(UUID(str(block_id)))
    return untrusted


def _view_from_payload(payload: dict[str, object]) -> UnderstandingView:
    raw_facts = payload.get("facts", [])
    fact_items = raw_facts if isinstance(raw_facts, list) else []
    facts = tuple(
        GroundedFactView(
            id=str(item["id"]),
            category=str(item["category"]),
            subject_key=str(item["subject_key"]),
            normalized_value=str(item["normalized_value"]),
            support_status=str(item["support_status"]),
            citation=dict(item["citation"]) if isinstance(item.get("citation"), dict) else None,
            source_block_id=(str(item["source_block_id"]) if item.get("source_block_id") else None),
        )
        for item in fact_items
        if isinstance(item, dict)
    )
    raw_conflicts = payload.get("contradictions", [])
    contradiction_items = raw_conflicts if isinstance(raw_conflicts, list) else []
    contradictions = tuple(
        GroundedContradictionView(
            id=str(item["id"]),
            contradiction_type=str(item["contradiction_type"]),
            fact_a_id=str(item["fact_a_id"]),
            fact_b_id=str(item["fact_b_id"]),
            reason=str(item["reason"]),
            status=str(item["status"]),
        )
        for item in contradiction_items
        if isinstance(item, dict)
    )
    return UnderstandingView(
        facts=facts,
        contradictions=contradictions,
        contradiction_detection_attested=bool(payload.get("contradiction_detection_attested")),
    )


def _evaluation_payload(item: RuleEvaluation) -> dict[str, object]:
    return {
        "id": str(uuid4()),
        "rule_id": item.rule_id,
        "rule_version": item.rule_version,
        "outcome": item.outcome,
        "severity": item.severity,
        "title": item.title,
        "message": item.message,
        "reason": item.reason,
        "fact_ids": list(item.fact_ids),
        "contradiction_ids": list(item.contradiction_ids),
        "citations": list(item.citations),
        "confidence": item.confidence,
        "evidence_kind": item.evidence_kind,
    }


def _evidence_kind_from_payload(raw: dict[str, object]) -> EvidenceKind:
    lookup: dict[str, EvidenceKind] = {
        "none": "none",
        "grounded_facts": "grounded_facts",
        "process_attestation": "process_attestation",
    }
    return lookup.get(str(raw.get("evidence_kind", "")), "none")


def _evaluation_from_payload(raw: dict[str, object]) -> RuleEvaluation:
    raw_citations = raw.get("citations", [])
    citation_items = raw_citations if isinstance(raw_citations, list) else []
    citations = tuple(dict(item) for item in citation_items if isinstance(item, dict))
    raw_facts = raw.get("fact_ids", [])
    fact_items = raw_facts if isinstance(raw_facts, list) else []
    raw_conflicts = raw.get("contradiction_ids", [])
    conflict_items = raw_conflicts if isinstance(raw_conflicts, list) else []
    outcome_lookup: dict[str, Outcome] = {
        "pass": "pass",
        "fail": "fail",
        "warning": "warning",
        "unknown": "unknown",
    }
    outcome = outcome_lookup.get(str(raw["outcome"]), "unknown")
    reason_raw = raw.get("reason", {})
    return RuleEvaluation(
        rule_id=str(raw["rule_id"]),
        rule_version=str(raw["rule_version"]),
        outcome=outcome,
        severity=str(raw["severity"]),
        title=str(raw["title"]),
        message=str(raw["message"]),
        reason=dict(reason_raw) if isinstance(reason_raw, dict) else {},
        fact_ids=tuple(str(item) for item in fact_items),
        contradiction_ids=tuple(str(item) for item in conflict_items),
        citations=citations,
        confidence=float(str(raw["confidence"])),
        evidence_kind=_evidence_kind_from_payload(raw),
    )


def _summarize(findings: list[dict[str, object]]) -> dict[str, object]:
    counts = {"pass": 0, "fail": 0, "warning": 0, "unknown": 0}
    for item in findings:
        outcome = str(item.get("outcome", ""))
        if outcome in counts:
            counts[outcome] += 1
    return {
        "pass_count": counts["pass"],
        "fail_count": counts["fail"],
        "warning_count": counts["warning"],
        "unknown_count": counts["unknown"],
        "evaluated_rule_count": len(findings),
        "no_findings": len(findings) == 0,
    }
