"""LangGraph Understand workflow: classify, extract, ground, and contradict."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Literal, TypedDict, cast
from uuid import UUID, uuid4

from langgraph.graph import END, START, StateGraph
from sqlalchemy import select

from app.db import SessionFactory
from app.errors import ModelError, NotFoundError, Phase02Error, ProvenanceError, ValidationError
from app.grounding import UNTRUSTED_CATEGORY, contains_untrusted_instruction, validate_assertion
from app.model_gateway import (
    BlockClassification,
    BlockContext,
    ModelAdapter,
    ModelUsage,
    ProposedFact,
)
from app.models import AnalysisRun, Contradiction, Fact, SourceBlock, SourceVersion, StageEvent
from app.schemas import SearchRequest
from app.services import Phase02Service
from app.taxonomy import (
    CONTRADICTION_TYPE_BY_CATEGORY,
    FALLBACK_MAX_BLOCKS,
    GRAPH_VERSION,
    INSPECTION_FIELDS,
    RETRIEVAL_QUERIES,
    TAXONOMY_VERSION,
    comparison_key,
)

CANONICAL_STAGES = (
    "load_corpus",
    "retrieve_context",
    "classify",
    "extract_facts",
    "validate_provenance",
    "detect_contradictions",
    "finalize",
)


class UnderstandState(TypedDict, total=False):
    corpus_id: str
    run_id: str
    source_blocks: list[dict[str, object]]
    retrieved_block_ids: list[str]
    candidate_block_ids: list[str]
    retrieval_mode: str
    classifications: list[dict[str, object]]
    proposed_facts: list[dict[str, object]]
    supported_facts: list[dict[str, object]]
    unknown_facts: list[dict[str, object]]
    rejected_assertions: list[dict[str, object]]
    contradictions: list[dict[str, object]]
    no_findings: bool
    error_code: str
    error_detail: str
    error_action: str


def utcnow() -> datetime:
    return datetime.now(UTC)


class UnderstandWorkflow:
    def __init__(
        self,
        *,
        session_factory: SessionFactory,
        phase02: Phase02Service,
        adapter: ModelAdapter,
    ) -> None:
        self.session_factory = session_factory
        self.phase02 = phase02
        self.adapter = adapter
        graph = StateGraph(UnderstandState)
        graph.add_node("load_corpus", self.load_corpus)
        graph.add_node("retrieve_context", self.retrieve_context)
        graph.add_node("classify", self.classify)
        graph.add_node("extract_facts", self.extract_facts)
        graph.add_node("validate_provenance", self.validate_provenance)
        graph.add_node("detect_contradictions", self.detect_contradictions)
        graph.add_node("finalize", self.finalize)
        graph.add_edge(START, "load_corpus")
        graph.add_edge("load_corpus", "retrieve_context")
        graph.add_edge("retrieve_context", "classify")
        graph.add_edge("classify", "extract_facts")
        graph.add_edge("extract_facts", "validate_provenance")
        graph.add_edge("validate_provenance", "detect_contradictions")
        graph.add_edge("detect_contradictions", "finalize")
        graph.add_edge("finalize", END)
        self.graph = graph.compile()

    async def ainvoke(self, corpus_id: UUID, run_id: UUID) -> UnderstandState:
        result = await self.graph.ainvoke({"corpus_id": str(corpus_id), "run_id": str(run_id)})
        return cast(UnderstandState, result)

    async def load_corpus(self, state: UnderstandState) -> UnderstandState:
        started = utcnow()
        perf = time.perf_counter()
        corpus_id = UUID(state["corpus_id"])
        run_id = UUID(state["run_id"])
        try:
            await self.phase02.get_corpus(corpus_id)
            contexts = await self._load_latest_blocks(corpus_id)
            empty = not contexts
            await self._record_stage(
                run_id=run_id,
                corpus_id=corpus_id,
                stage_name="load_corpus",
                started_at=started,
                duration_ms=_duration_ms(perf),
                usage=_idle_usage(),
                status="skipped" if empty else "completed",
                skip_reason="empty_corpus" if empty else None,
            )
            return {
                "source_blocks": [context.model_dump(mode="json") for context in contexts],
                "no_findings": empty,
            }
        except Phase02Error as error:
            await self._record_stage(
                run_id=run_id,
                corpus_id=corpus_id,
                stage_name="load_corpus",
                started_at=started,
                duration_ms=_duration_ms(perf),
                usage=_idle_usage(),
                status="failed",
                error_code=error.code,
            )
            return _error_state(error)

    async def retrieve_context(self, state: UnderstandState) -> UnderstandState:
        started = utcnow()
        perf = time.perf_counter()
        corpus_id = UUID(state["corpus_id"])
        run_id = UUID(state["run_id"])
        blocks = state.get("source_blocks", [])
        if state.get("error_code"):
            await self._record_skip(
                run_id, corpus_id, "retrieve_context", started, perf, "prior_stage_failed"
            )
            return {
                "retrieved_block_ids": [],
                "candidate_block_ids": [],
                "retrieval_mode": "prior_stage_failed",
            }
        if not blocks:
            await self._record_skip(
                run_id, corpus_id, "retrieve_context", started, perf, "empty_corpus"
            )
            return {
                "retrieved_block_ids": [],
                "candidate_block_ids": [],
                "retrieval_mode": "empty_corpus",
            }
        retrieved: list[str] = []
        seen: set[str] = set()
        for query in RETRIEVAL_QUERIES:
            try:
                matches = await self.phase02.search(
                    corpus_id=corpus_id,
                    request=SearchRequest(query=query, limit=10),
                )
            except ValidationError:
                continue
            for match in matches:
                block_id = str(match.block.id)
                if block_id not in seen:
                    seen.add(block_id)
                    retrieved.append(block_id)
        loaded_ids = [str(item["source_block_id"]) for item in blocks]
        if retrieved:
            await self._record_stage(
                run_id=run_id,
                corpus_id=corpus_id,
                stage_name="retrieve_context",
                started_at=started,
                duration_ms=_duration_ms(perf),
                usage=_idle_usage(),
                status="completed",
            )
            return {
                "retrieved_block_ids": retrieved,
                "candidate_block_ids": [
                    block_id for block_id in retrieved if block_id in set(loaded_ids)
                ],
                "retrieval_mode": "retrieved",
            }
        fallback_ids = loaded_ids[:FALLBACK_MAX_BLOCKS]
        await self._record_skip(
            run_id,
            corpus_id,
            "retrieve_context",
            started,
            perf,
            "retrieval_empty_fallback",
        )
        return {
            "retrieved_block_ids": [],
            "candidate_block_ids": fallback_ids,
            "retrieval_mode": "fallback_full_corpus",
        }

    async def classify(self, state: UnderstandState) -> UnderstandState:
        started = utcnow()
        perf = time.perf_counter()
        corpus_id = UUID(state["corpus_id"])
        run_id = UUID(state["run_id"])
        if state.get("error_code"):
            await self._record_skip(
                run_id, corpus_id, "classify", started, perf, "prior_stage_failed"
            )
            return {"classifications": []}
        candidate_ids = set(state.get("candidate_block_ids", []))
        blocks = [
            BlockContext.model_validate(item)
            for item in state.get("source_blocks", [])
            if str(item["source_block_id"]) in candidate_ids
        ]
        if not blocks:
            reason = (
                "empty_corpus" if not state.get("source_blocks") else "retrieval_empty_fallback"
            )
            await self._record_skip(run_id, corpus_id, "classify", started, perf, reason)
            return {"classifications": []}
        try:
            batch = await self.adapter.classify_blocks(blocks)
        except ModelError as error:
            await self._record_stage(
                run_id=run_id,
                corpus_id=corpus_id,
                stage_name="classify",
                started_at=started,
                duration_ms=_duration_ms(perf),
                usage=_usage_from_model_error(error, self.adapter),
                status="failed",
                error_code=error.code,
            )
            return {**_error_state(error), "classifications": []}
        enforced = _enforce_untrusted_classifications(blocks, batch.classifications)
        await self._record_stage(
            run_id=run_id,
            corpus_id=corpus_id,
            stage_name="classify",
            started_at=started,
            duration_ms=_duration_ms(perf),
            usage=batch.usage,
            status="completed",
        )
        return {"classifications": [item.model_dump(mode="json") for item in enforced]}

    async def extract_facts(self, state: UnderstandState) -> UnderstandState:
        started = utcnow()
        perf = time.perf_counter()
        corpus_id = UUID(state["corpus_id"])
        run_id = UUID(state["run_id"])
        if state.get("error_code"):
            await self._record_skip(
                run_id, corpus_id, "extract_facts", started, perf, "prior_stage_failed"
            )
            return {"proposed_facts": []}
        classified_ids = {str(item["source_block_id"]) for item in state.get("classifications", [])}
        relevant_ids = {
            str(item["source_block_id"])
            for item in state.get("classifications", [])
            if item.get("relevant") is True and item.get("category") != UNTRUSTED_CATEGORY
        }
        untrusted_ids = {
            str(item["source_block_id"])
            for item in state.get("classifications", [])
            if item.get("category") == UNTRUSTED_CATEGORY
        }
        blocks = [
            BlockContext.model_validate(item)
            for item in state.get("source_blocks", [])
            if str(item["source_block_id"]) in classified_ids
            and str(item["source_block_id"]) in relevant_ids
            and str(item["source_block_id"]) not in untrusted_ids
            and not contains_untrusted_instruction(str(item["normalized_text"]))
        ]
        if not blocks:
            reason = "empty_corpus" if not state.get("source_blocks") else "no_relevant_blocks"
            await self._record_skip(run_id, corpus_id, "extract_facts", started, perf, reason)
            return {"proposed_facts": []}
        try:
            batch = await self.adapter.extract_facts(blocks)
        except ModelError as error:
            await self._record_stage(
                run_id=run_id,
                corpus_id=corpus_id,
                stage_name="extract_facts",
                started_at=started,
                duration_ms=_duration_ms(perf),
                usage=_usage_from_model_error(error, self.adapter),
                status="failed",
                error_code=error.code,
            )
            return {**_error_state(error), "proposed_facts": []}
        await self._record_stage(
            run_id=run_id,
            corpus_id=corpus_id,
            stage_name="extract_facts",
            started_at=started,
            duration_ms=_duration_ms(perf),
            usage=batch.usage,
            status="completed",
        )
        return {"proposed_facts": [item.model_dump(mode="json") for item in batch.facts]}

    async def validate_provenance(self, state: UnderstandState) -> UnderstandState:
        started = utcnow()
        perf = time.perf_counter()
        corpus_id = UUID(state["corpus_id"])
        run_id = UUID(state["run_id"])
        if state.get("error_code"):
            await self._record_skip(
                run_id, corpus_id, "validate_provenance", started, perf, "prior_stage_failed"
            )
            return {
                "supported_facts": [],
                "unknown_facts": [],
                "rejected_assertions": [],
            }
        untrusted_ids = {
            UUID(str(item["source_block_id"]))
            for item in state.get("classifications", [])
            if item.get("category") == UNTRUSTED_CATEGORY
        }
        supported: list[dict[str, object]] = []
        rejected: list[dict[str, object]] = []
        for raw in state.get("proposed_facts", []):
            proposed = ProposedFact.model_validate(raw)
            if proposed.citation is None:
                rejected.append(_rejection(proposed, "missing_citation"))
                continue
            try:
                validation = await self.phase02.validate_citation(
                    corpus_id=corpus_id,
                    citation=proposed.citation,
                )
            except (ProvenanceError, NotFoundError, ValidationError) as error:
                rejected.append(_rejection(proposed, error.code))
                continue
            reason = validate_assertion(
                category=proposed.category,
                subject_key=proposed.subject_key,
                normalized_value=proposed.normalized_value,
                proposed_source_block_id=proposed.source_block_id,
                evidence_text=validation.resolved_quote,
                resolved_block_id=validation.source_block_id,
                untrusted_block_ids=untrusted_ids,
            )
            if reason is not None:
                rejected.append(_rejection(proposed, reason))
                continue
            supported.append(
                {
                    "id": str(uuid4()),
                    "category": proposed.category,
                    "subject_key": proposed.subject_key,
                    "normalized_value": proposed.normalized_value,
                    "confidence": proposed.confidence,
                    "support_status": "supported",
                    "citation": proposed.citation.model_dump(mode="json"),
                    "source_block_id": str(validation.source_block_id),
                }
            )
        unknown = _unknown_fields(supported)
        await self._record_stage(
            run_id=run_id,
            corpus_id=corpus_id,
            stage_name="validate_provenance",
            started_at=started,
            duration_ms=_duration_ms(perf),
            usage=_idle_usage(),
            status="completed",
        )
        return {
            "supported_facts": supported,
            "unknown_facts": unknown,
            "rejected_assertions": rejected,
            "no_findings": not supported,
        }

    async def detect_contradictions(self, state: UnderstandState) -> UnderstandState:
        started = utcnow()
        perf = time.perf_counter()
        corpus_id = UUID(state["corpus_id"])
        run_id = UUID(state["run_id"])
        if state.get("error_code"):
            await self._record_skip(
                run_id, corpus_id, "detect_contradictions", started, perf, "prior_stage_failed"
            )
            return {"contradictions": []}
        contradictions = detect_supported_contradictions(state.get("supported_facts", []))
        await self._record_stage(
            run_id=run_id,
            corpus_id=corpus_id,
            stage_name="detect_contradictions",
            started_at=started,
            duration_ms=_duration_ms(perf),
            usage=_idle_usage(),
            status="completed",
        )
        return {"contradictions": contradictions}

    async def finalize(self, state: UnderstandState) -> UnderstandState:
        started = utcnow()
        perf = time.perf_counter()
        corpus_id = UUID(state["corpus_id"])
        run_id = UUID(state["run_id"])
        failed = bool(state.get("error_code"))
        supported = state.get("supported_facts", [])
        unknown = state.get("unknown_facts", [])
        contradictions = state.get("contradictions", [])
        findings_status: Literal["populated", "no_findings", "failed"]
        if failed:
            findings_status = "failed"
        elif supported:
            findings_status = "populated"
        else:
            findings_status = "no_findings"
        async with self.session_factory() as session, session.begin():
            run = await session.scalar(
                select(AnalysisRun).where(
                    AnalysisRun.id == run_id,
                    AnalysisRun.corpus_id == corpus_id,
                )
            )
            if run is None:
                raise NotFoundError(
                    "analysis_run_not_found",
                    "The analysis run was not found in this corpus.",
                    "Create an analysis run for this corpus and retry.",
                )
            if not failed:
                for item in [*supported, *unknown]:
                    session.add(
                        Fact(
                            id=UUID(str(item["id"])),
                            run_id=run_id,
                            corpus_id=corpus_id,
                            category=str(item["category"]),
                            subject_key=str(item["subject_key"]),
                            normalized_value=str(item["normalized_value"]),
                            confidence=float(str(item["confidence"])),
                            support_status=str(item["support_status"]),
                            rejection_reason=None,
                            citation=(
                                item.get("citation")
                                if isinstance(item.get("citation"), dict)
                                else None
                            ),
                            source_block_id=(
                                UUID(str(item["source_block_id"]))
                                if item.get("source_block_id")
                                else None
                            ),
                        )
                    )
                await session.flush()
                for item in contradictions:
                    session.add(
                        Contradiction(
                            run_id=run_id,
                            corpus_id=corpus_id,
                            fact_a_id=UUID(str(item["fact_a_id"])),
                            fact_b_id=UUID(str(item["fact_b_id"])),
                            contradiction_type=str(item["contradiction_type"]),
                            reason=str(item["reason"]),
                            confidence=float(str(item["confidence"])),
                            status="open",
                        )
                    )
            run.status = "failed" if failed else "completed"
            run.findings_status = findings_status
            run.completed_at = utcnow()
            run.error_code = state.get("error_code")
            run.error_detail = state.get("error_detail")
            run.result_payload = {
                "no_findings": findings_status == "no_findings",
                "classifications": state.get("classifications", []),
                "retrieved_block_ids": state.get("retrieved_block_ids", []),
                "retrieval_mode": state.get("retrieval_mode", "empty_corpus"),
                "rejected_assertions": state.get("rejected_assertions", []),
                "taxonomy_version": TAXONOMY_VERSION,
                "graph_version": GRAPH_VERSION,
            }
        await self._record_stage(
            run_id=run_id,
            corpus_id=corpus_id,
            stage_name="finalize",
            started_at=started,
            duration_ms=_duration_ms(perf),
            usage=_idle_usage(),
            status="failed" if failed else "completed",
            error_code=state.get("error_code"),
        )
        return {"no_findings": findings_status == "no_findings"}

    async def _load_latest_blocks(self, corpus_id: UUID) -> list[BlockContext]:
        async with self.session_factory() as session:
            versions = list(
                await session.scalars(
                    select(SourceVersion)
                    .where(SourceVersion.corpus_id == corpus_id)
                    .order_by(SourceVersion.created_at.desc(), SourceVersion.id.desc())
                )
            )
            latest: dict[UUID, SourceVersion] = {}
            for version in versions:
                if version.source_id not in latest:
                    latest[version.source_id] = version
            if not latest:
                return []
            version_ids = [version.id for version in latest.values()]
            blocks = list(
                await session.scalars(
                    select(SourceBlock)
                    .where(
                        SourceBlock.corpus_id == corpus_id,
                        SourceBlock.source_version_id.in_(version_ids),
                    )
                    .order_by(SourceBlock.block_index, SourceBlock.id)
                )
            )
            version_by_id = {version.id: version for version in latest.values()}
            contexts: list[BlockContext] = []
            for block in blocks:
                version = version_by_id[block.source_version_id]
                contexts.append(
                    BlockContext(
                        source_block_id=block.id,
                        source_version_id=version.id,
                        source_sha256=version.sha256,
                        format=version.declared_format,  # type: ignore[arg-type]
                        native_locator=block.native_locator,
                        normalized_text=block.normalized_text,
                        block_type=block.block_type,
                    )
                )
            return contexts

    async def _record_skip(
        self,
        run_id: UUID,
        corpus_id: UUID,
        stage_name: str,
        started: datetime,
        perf: float,
        skip_reason: str,
    ) -> None:
        await self._record_stage(
            run_id=run_id,
            corpus_id=corpus_id,
            stage_name=stage_name,
            started_at=started,
            duration_ms=_duration_ms(perf),
            usage=_idle_usage(),
            status="skipped",
            skip_reason=skip_reason,
        )

    async def _record_stage(
        self,
        *,
        run_id: UUID,
        corpus_id: UUID,
        stage_name: str,
        started_at: datetime,
        duration_ms: int,
        usage: ModelUsage,
        status: str,
        error_code: str | None = None,
        skip_reason: str | None = None,
    ) -> None:
        if stage_name not in CANONICAL_STAGES:
            raise ValueError(f"unknown understand stage: {stage_name}")
        cost_basis = usage.cost_basis
        if self.adapter.mode == "deterministic":
            cost_basis = "zero_deterministic"
        operation_count = usage.operation_count
        attempt_count = usage.attempt_count
        estimated_cost = usage.estimated_cost_usd
        if status == "skipped":
            operation_count = 0
            attempt_count = 0
            estimated_cost = 0.0
            cost_basis = (
                "zero_deterministic" if self.adapter.mode == "deterministic" else cost_basis
            )
        async with self.session_factory() as session, session.begin():
            session.add(
                StageEvent(
                    run_id=run_id,
                    corpus_id=corpus_id,
                    stage_name=stage_name,
                    started_at=started_at,
                    completed_at=utcnow(),
                    duration_ms=duration_ms if status != "skipped" else 0,
                    model_operation_count=operation_count,
                    model_attempt_count=attempt_count,
                    input_tokens=usage.input_tokens if status != "skipped" else None,
                    output_tokens=usage.output_tokens if status != "skipped" else None,
                    estimated_cost_usd=(
                        0.0
                        if status == "skipped" or cost_basis == "zero_deterministic"
                        else estimated_cost
                    ),
                    cost_basis=cost_basis,
                    status=status,
                    error_code=error_code,
                    skip_reason=skip_reason,
                )
            )


def detect_supported_contradictions(
    supported_facts: list[dict[str, object]],
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], dict[str, dict[str, object]]] = {}
    for fact in supported_facts:
        category = str(fact["category"])
        subject = str(fact["subject_key"])
        value_key = comparison_key(str(fact["normalized_value"]))
        grouped.setdefault((category, subject), {}).setdefault(value_key, fact)
    contradictions: list[dict[str, object]] = []
    seen_pairs: set[tuple[str, str]] = set()
    for (category, subject), by_value in grouped.items():
        if len(by_value) < 2:
            continue
        if category not in CONTRADICTION_TYPE_BY_CATEGORY:
            continue
        contradiction_type = CONTRADICTION_TYPE_BY_CATEGORY[category]
        representatives = list(by_value.values())
        for index, left in enumerate(representatives):
            for right in representatives[index + 1 :]:
                fact_a = left
                fact_b = right
                fact_a_id = str(fact_a["id"])
                fact_b_id = str(fact_b["id"])
                if fact_a_id > fact_b_id:
                    fact_a, fact_b = fact_b, fact_a
                    fact_a_id, fact_b_id = fact_b_id, fact_a_id
                pair = (fact_a_id, fact_b_id)
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                contradictions.append(
                    {
                        "fact_a_id": fact_a_id,
                        "fact_b_id": fact_b_id,
                        "contradiction_type": contradiction_type,
                        "reason": (
                            f"{category}/{subject} has incompatible values "
                            f"{fact_a['normalized_value']!s} and {fact_b['normalized_value']!s}."
                        ),
                        "confidence": 1.0,
                    }
                )
    return contradictions


def _unknown_fields(supported: list[dict[str, object]]) -> list[dict[str, object]]:
    present = {(str(item["category"]), str(item["subject_key"])) for item in supported}
    unknown: list[dict[str, object]] = []
    for field in INSPECTION_FIELDS:
        key = (field.category, field.subject_key)
        if key in present:
            continue
        unknown.append(
            {
                "id": str(uuid4()),
                "category": field.category,
                "subject_key": field.subject_key,
                "normalized_value": "INSUFFICIENT_EVIDENCE",
                "confidence": 0.0,
                "support_status": "unknown",
                "citation": None,
                "source_block_id": None,
            }
        )
    return unknown


def _enforce_untrusted_classifications(
    blocks: list[BlockContext],
    classifications: list[BlockClassification],
) -> list[BlockClassification]:
    by_id = {item.source_block_id: item for item in classifications}
    enforced: list[BlockClassification] = []
    for block in blocks:
        item = by_id.get(block.source_block_id)
        if contains_untrusted_instruction(block.normalized_text):
            enforced.append(
                BlockClassification(
                    source_block_id=block.source_block_id,
                    relevant=False,
                    category=UNTRUSTED_CATEGORY,
                    confidence=1.0,
                    rationale="Untrusted instruction treated as source data.",
                )
            )
            continue
        if item is None:
            continue
        if item.category == UNTRUSTED_CATEGORY:
            enforced.append(item.model_copy(update={"relevant": False}))
        else:
            enforced.append(item)
    return enforced


def _rejection(proposed: ProposedFact, reason: str) -> dict[str, object]:
    return {
        "category": proposed.category,
        "subject_key": proposed.subject_key,
        "normalized_value": proposed.normalized_value,
        "reason": reason,
        "citation": proposed.citation.model_dump(mode="json") if proposed.citation else None,
    }


def _error_state(error: Phase02Error) -> UnderstandState:
    return {
        "error_code": error.code,
        "error_detail": error.detail,
        "error_action": error.action,
        "no_findings": False,
        "proposed_facts": [],
        "supported_facts": [],
        "unknown_facts": [],
        "rejected_assertions": [],
        "contradictions": [],
        "classifications": [],
    }


def _idle_usage() -> ModelUsage:
    return ModelUsage(
        operation_count=0,
        attempt_count=0,
        estimated_cost_usd=0.0,
        cost_basis="zero_deterministic",
    )


def _duration_ms(started: float) -> int:
    return max(0, int((time.perf_counter() - started) * 1000))


def _cost_basis(adapter: ModelAdapter) -> str:
    if adapter.mode == "deterministic":
        return "zero_deterministic"
    return "unavailable"


def _usage_from_model_error(error: ModelError, adapter: ModelAdapter) -> ModelUsage:
    attempts = error.attempt_count if error.attempt_count is not None else 0
    return ModelUsage(
        operation_count=1,
        attempt_count=attempts,
        cost_basis=_cost_basis(adapter),
    )
