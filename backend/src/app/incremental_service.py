"""Focused incremental Understand/Examine over an immutable corpus baseline."""

from __future__ import annotations

import time
from collections.abc import Sequence
from contextlib import asynccontextmanager
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.canonical import (
    canonical_bytes,
    canonical_hash,
    contradiction_canonical_payload,
    fact_canonical_payload,
    finding_canonical_payload,
    review_item_canonical_payload,
)
from app.config import Settings
from app.db import SessionFactory
from app.errors import ConflictError, NotFoundError, Phase02Error, ValidationError
from app.examine_graph import utcnow
from app.examine_service import ExamineService
from app.grounding import UNTRUSTED_CATEGORY, contains_untrusted_instruction, validate_assertion
from app.incremental_planning import (
    ChangeSet,
    ContradictionImpactRef,
    FactImpactRef,
    ImpactSet,
    SourceSnapshot,
    blocks_source_input_version,
    diff_snapshots,
    plan_impact,
    request_hash_for_blocks,
    snapshots_from_payload,
    snapshots_to_payload,
)
from app.model_gateway import (
    PROMPT_CONFIG_VERSION,
    BlockContext,
    ClassificationBatch,
    ExtractionBatch,
    ModelAdapter,
    ProposedFact,
    create_model_adapter,
)
from app.models import (
    AnalysisRun,
    Contradiction,
    CorpusRevision,
    CorpusRevisionSource,
    ExaminationRun,
    ExaminationStageEvent,
    Fact,
    Finding,
    FindingContradictionEvidence,
    FindingFactEvidence,
    IncrementalArtifactEvidence,
    IncrementalRun,
    ReviewDecision,
    ReviewItem,
    ReviewSession,
    Source,
    SourceBlock,
    SourceVersion,
    StageEvent,
)
from app.operation_ledger import (
    OperationLedger,
    make_content_operation_key,
)
from app.review_service import ReviewService
from app.ruleset import (
    EXAMINE_GRAPH_VERSION,
    OPEN_CONTRADICTION_RULE_ID,
    UnderstandingView,
    citations_for,
    evaluate_open_contradictions,
    evaluate_rule,
    facts_by_id,
    select_rules,
)
from app.services import Phase02Service
from app.taxonomy import GRAPH_VERSION, TAXONOMY_VERSION
from app.understand_graph import (
    _enforce_untrusted_classifications,
    _unknown_fields,
    detect_supported_contradictions,
)
from app.understand_service import UnderstandService

INCREMENTAL_GRAPH_VERSION = "incremental.v1"


class IncrementalFinalizeInjectedError(RuntimeError):
    """Test-only crash before the atomic revision commit."""


class IncrementalService:
    def __init__(
        self,
        session_factory: SessionFactory,
        phase02: Phase02Service,
        understand: UnderstandService,
        examine: ExamineService,
        review: ReviewService,
        adapter: ModelAdapter | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.phase02 = phase02
        self.understand = understand
        self.examine = examine
        self.review = review
        self.settings = settings or Settings()
        self.adapter = adapter or create_model_adapter(self.settings)
        self.ledger = OperationLedger(session_factory)
        self.fail_before_finalize = False

    def _engine(self) -> AsyncEngine:
        return cast(AsyncEngine, self.session_factory.kw["bind"])

    @asynccontextmanager
    async def _corpus_lock(self, corpus_id: UUID) -> Any:
        lock_key = f"incremental-corpus:{corpus_id}"
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

    async def create_baseline_revision(
        self,
        corpus_id: UUID,
        *,
        analysis_run_id: UUID,
        examination_run_id: UUID,
        review_session_id: UUID | None = None,
    ) -> CorpusRevision:
        await self.phase02.get_corpus(corpus_id)
        analysis = await self.understand.get_run(corpus_id, analysis_run_id)
        if analysis.status != "completed":
            raise ValidationError(
                "analysis_run_not_ready",
                "A baseline revision requires a completed Understand analysis run.",
                "Wait for the analysis run to complete, then create the baseline.",
            )
        examination = await self.examine.get_run(corpus_id, examination_run_id)
        if examination.status != "completed":
            raise ValidationError(
                "examination_run_not_ready",
                "A baseline revision requires a completed Examine run.",
                "Wait for the examination run to complete, then create the baseline.",
            )
        if examination.analysis_run_id != analysis_run_id:
            raise ValidationError(
                "examination_analysis_mismatch",
                "The examination run does not belong to the supplied analysis run.",
                "Use the examination created from that analysis run.",
            )
        if review_session_id is not None:
            review_session = await self.review.get_session(corpus_id, review_session_id)
            if review_session.examination_run_id != examination_run_id:
                raise ValidationError(
                    "review_examination_mismatch",
                    "The review session does not belong to the supplied examination run.",
                    "Use the review session created from that examination.",
                )
        async with self._corpus_lock(corpus_id):
            existing = await self._current_revision(corpus_id)
            if existing is not None:
                raise ValidationError(
                    "corpus_revision_exists",
                    "This corpus already has a current incremental baseline.",
                    "Ingest a changed source and create an incremental run instead.",
                )
            snapshots = await self._latest_snapshots(corpus_id)
            operation_keys = await self._source_operation_keys(corpus_id, snapshots)
            revision = CorpusRevision(
                id=uuid4(),
                corpus_id=corpus_id,
                revision_number=1,
                is_current=True,
                analysis_run_id=analysis_run_id,
                examination_run_id=examination_run_id,
                review_session_id=review_session_id,
                source_version_set=snapshots_to_payload(snapshots),
                taxonomy_version=analysis.taxonomy_version,
                understand_graph_version=analysis.graph_version,
                prompt_config_version=PROMPT_CONFIG_VERSION,
                ruleset_version=examination.ruleset_version,
                examine_graph_version=examination.graph_version,
                configuration={
                    "incremental_graph_version": INCREMENTAL_GRAPH_VERSION,
                    "source_operation_keys": operation_keys,
                },
            )
            async with self.session_factory() as session:
                session.add(revision)
                for snapshot in snapshots:
                    session.add(_revision_source_row(revision.id, corpus_id, snapshot))
                await session.commit()
                await session.refresh(revision)
            return revision

    async def get_current_revision(self, corpus_id: UUID) -> CorpusRevision:
        await self.phase02.get_corpus(corpus_id)
        revision = await self._current_revision(corpus_id)
        if revision is None:
            raise NotFoundError(
                "corpus_revision_not_found",
                "No incremental baseline exists for this corpus.",
                "Create a baseline revision from completed Understand and Examine runs.",
            )
        return revision

    async def get_revision(self, corpus_id: UUID, revision_id: UUID) -> CorpusRevision:
        await self.phase02.get_corpus(corpus_id)
        async with self.session_factory() as session:
            revision = await session.scalar(
                select(CorpusRevision).where(
                    CorpusRevision.id == revision_id,
                    CorpusRevision.corpus_id == corpus_id,
                )
            )
        if revision is None:
            raise NotFoundError(
                "corpus_revision_not_found",
                "The corpus revision was not found in this corpus.",
                "Use a revision identifier returned for the same corpus.",
            )
        return revision

    async def create_run(
        self,
        corpus_id: UUID,
        *,
        baseline_revision_id: UUID | None = None,
    ) -> IncrementalRun:
        await self.phase02.get_corpus(corpus_id)
        async with self._corpus_lock(corpus_id):
            current = await self._current_revision(corpus_id)
            if current is None:
                raise ValidationError(
                    "corpus_revision_not_found",
                    "Incremental processing requires a current corpus baseline.",
                    "Create a baseline revision from completed Understand and Examine runs.",
                )
            if baseline_revision_id is not None and baseline_revision_id != current.id:
                await self.get_revision(corpus_id, baseline_revision_id)
                return await self._persist_stale(corpus_id, baseline_revision_id, current.id)
            return await self._execute(current)

    async def get_run(self, corpus_id: UUID, run_id: UUID) -> IncrementalRun:
        await self.phase02.get_corpus(corpus_id)
        async with self.session_factory() as session:
            run = await session.scalar(
                select(IncrementalRun).where(
                    IncrementalRun.id == run_id,
                    IncrementalRun.corpus_id == corpus_id,
                )
            )
        if run is None:
            raise NotFoundError(
                "incremental_run_not_found",
                "The incremental run was not found in this corpus.",
                "Use an incremental run identifier returned for the same corpus.",
            )
        return run

    async def get_impact(self, corpus_id: UUID, run_id: UUID) -> dict[str, object]:
        run = await self.get_run(corpus_id, run_id)
        return dict(run.impact)

    async def get_evidence(self, corpus_id: UUID, run_id: UUID) -> dict[str, object]:
        run = await self.get_run(corpus_id, run_id)
        async with self.session_factory() as session:
            rows = list(
                await session.scalars(
                    select(IncrementalArtifactEvidence)
                    .where(
                        IncrementalArtifactEvidence.incremental_run_id == run_id,
                        IncrementalArtifactEvidence.corpus_id == corpus_id,
                    )
                    .order_by(
                        IncrementalArtifactEvidence.artifact_kind,
                        IncrementalArtifactEvidence.artifact_id,
                    )
                )
            )
        return {
            "run_id": str(run.id),
            "status": run.status,
            "change_kind": run.change_kind,
            "evidence": dict(run.evidence),
            "measurement": dict(run.measurement),
            "artifacts": [_artifact_payload(row) for row in rows],
        }

    async def _execute(self, baseline: CorpusRevision) -> IncrementalRun:
        started = utcnow()
        perf = time.perf_counter()
        run_id = uuid4()
        corpus_id = baseline.corpus_id
        current_snapshots = await self._latest_snapshots(corpus_id)
        changes = diff_snapshots(
            snapshots_from_payload(baseline.source_version_set),
            current_snapshots,
        )
        run = IncrementalRun(
            id=run_id,
            corpus_id=corpus_id,
            baseline_revision_id=baseline.id,
            status="running",
            change_kind=changes.change_kind,
            impact={},
            evidence={},
            measurement={},
            started_at=started,
        )
        async with self.session_factory() as session:
            session.add(run)
            await session.commit()
        if not changes.has_changes:
            return await self._complete_unchanged(run, baseline, changes, perf)
        try:
            return await self._process_changes(run, baseline, changes, current_snapshots, perf)
        except ConflictError as error:
            if error.code != "stale_baseline":
                await self._fail_run(run_id, corpus_id, error)
                raise
            await self._mark_stale(run_id, corpus_id, error)
            return await self.get_run(corpus_id, run_id)
        except Phase02Error as error:
            await self._fail_run(run_id, corpus_id, error)
            raise
        except IncrementalFinalizeInjectedError:
            await self._fail_run(
                run_id,
                corpus_id,
                ValidationError(
                    "incremental_finalize_injected_failure",
                    "Incremental finalization was interrupted before the revision commit.",
                    "Retry the incremental run against the still-current baseline.",
                ),
            )
            raise

    async def _process_changes(
        self,
        run: IncrementalRun,
        baseline: CorpusRevision,
        changes: ChangeSet,
        current_snapshots: tuple[SourceSnapshot, ...],
        perf: float,
    ) -> IncrementalRun:
        corpus_id = run.corpus_id
        facts = await self.understand.list_facts(corpus_id, baseline.analysis_run_id)
        contradictions = await self.understand.list_contradictions(
            corpus_id, baseline.analysis_run_id
        )
        findings = await self.examine.list_findings(corpus_id, baseline.examination_run_id)
        block_ids_by_version = await self._block_ids_by_version(
            corpus_id,
            {item.source_version_id for item in snapshots_from_payload(baseline.source_version_set)}
            | changes.changed_source_version_ids,
        )
        fact_refs = [_fact_impact_ref(fact) for fact in facts]
        contradiction_refs = [
            _contradiction_impact_ref(item, {fact.id: fact for fact in facts})
            for item in contradictions
        ]
        versions_match = (
            baseline.taxonomy_version == TAXONOMY_VERSION
            and baseline.understand_graph_version == GRAPH_VERSION
            and baseline.prompt_config_version == PROMPT_CONFIG_VERSION
            and baseline.ruleset_version == self.examine.ruleset.version
            and baseline.examine_graph_version == EXAMINE_GRAPH_VERSION
        )
        impact = plan_impact(
            changes=changes,
            facts=fact_refs,
            contradictions=contradiction_refs,
            block_ids_by_version=block_ids_by_version,
            rules=self.examine.ruleset.rules,
        )
        if not versions_match:
            impact = ImpactSet(
                affected_fact_ids=frozenset(fact.id for fact in facts),
                reused_fact_ids=frozenset(),
                affected_contradiction_ids=frozenset(item.id for item in contradictions),
                reused_contradiction_ids=frozenset(),
                affected_rule_ids=frozenset(rule.rule_id for rule in self.examine.ruleset.rules),
                reused_rule_ids=frozenset(),
                affected_block_ids=impact.affected_block_ids,
                affected_keys=frozenset((fact.category, fact.subject_key) for fact in facts),
                global_rule_reasons={
                    OPEN_CONTRADICTION_RULE_ID: "taxonomy/graph/config version changed"
                },
            )
        analysis = await self._incremental_understand(
            run_id=run.id,
            corpus_id=corpus_id,
            baseline=baseline,
            changes=changes,
            facts=facts,
            contradictions=contradictions,
            impact=impact,
            versions_match=versions_match,
        )
        impact = analysis["impact"]
        examination, rule_evidence = await self._incremental_examine(
            corpus_id=corpus_id,
            analysis=analysis,
            impact=impact,
            baseline_findings=findings,
            fact_id_map=analysis["fact_id_map"],
            contradiction_id_map=analysis["contradiction_id_map"],
        )
        review_session, created = await self.review.create_session(corpus_id, examination.id)
        del created
        review_evidence = await self._review_evidence(
            corpus_id=corpus_id,
            baseline=baseline,
            new_session=review_session,
        )
        persisted_proof = await self._persisted_canonical_proof(
            corpus_id=corpus_id,
            baseline=baseline,
            analysis_run_id=analysis["run"].id,
            examination_run_id=examination.id,
            fact_id_map=analysis["fact_id_map"],
            contradiction_id_map=analysis["contradiction_id_map"],
            reused_rule_ids=_as_str_list(rule_evidence.get("reused_rule_ids")),
        )
        analysis["canonical_unchanged_facts"] = persisted_proof["facts"]
        analysis["canonical_unchanged_contradictions"] = persisted_proof["contradictions"]
        analysis["canonical_unchanged_findings"] = persisted_proof["findings"]
        evidence, artifacts = _compose_evidence(
            changes=changes,
            impact=impact,
            analysis=analysis,
            rule_evidence=rule_evidence,
            review_evidence=review_evidence,
        )
        measurement = _measurement(
            baseline_analysis_id=baseline.analysis_run_id,
            baseline_examination_id=baseline.examination_run_id,
            incremental_analysis=analysis["run"],
            incremental_examination=examination,
            changes=changes,
            impact=impact,
            duration_ms=max(0, int((time.perf_counter() - perf) * 1000)),
            baseline_stage_counts=await self._stage_counts(
                corpus_id, baseline.analysis_run_id, baseline.examination_run_id
            ),
            incremental_stage_counts=await self._stage_counts(
                corpus_id, analysis["run"].id, examination.id
            ),
        )
        return await self._commit_incremental_result(
            run_id=run.id,
            corpus_id=corpus_id,
            baseline=baseline,
            snapshots=current_snapshots,
            status="completed",
            change_kind=changes.change_kind,
            analysis_run_id=analysis["run"].id,
            examination_run_id=examination.id,
            review_session_id=review_session.id,
            impact=_impact_payload(changes, impact),
            evidence=evidence,
            measurement=measurement,
            artifacts=artifacts,
        )

    async def _incremental_understand(
        self,
        *,
        run_id: UUID,
        corpus_id: UUID,
        baseline: CorpusRevision,
        changes: ChangeSet,
        facts: Sequence[Fact],
        contradictions: Sequence[Contradiction],
        impact: ImpactSet,
        versions_match: bool,
    ) -> dict[str, Any]:
        analysis_id = uuid4()
        analysis = AnalysisRun(
            id=analysis_id,
            corpus_id=corpus_id,
            status="running",
            findings_status="pending",
            started_at=utcnow(),
            model_provider_mode=self.adapter.mode,
            model_name=self.adapter.model_name,
            taxonomy_version=TAXONOMY_VERSION,
            graph_version=GRAPH_VERSION,
            configuration={
                "mode": "incremental",
                "incremental_run_id": str(run_id),
                "baseline_revision_id": str(baseline.id),
            },
            result_payload={},
        )
        async with self.session_factory() as session:
            session.add(analysis)
            await session.commit()
        changed_blocks = await self._block_contexts(corpus_id, changes.changed_source_version_ids)
        reused_keys, skipped_versions = await self._unchanged_operation_keys(
            corpus_id=corpus_id,
            unchanged=changes.unchanged,
        )
        executed_keys: list[dict[str, object]] = []
        classifications: list[dict[str, object]] = []
        proposed: list[dict[str, object]] = []
        classify_versions: list[str] = []
        extract_versions: list[str] = []
        classify_executed = False
        extract_executed = False
        if changed_blocks:
            classify_versions = sorted({str(item.source_version_id) for item in changed_blocks})
            batch, classify_meta = await self._execute_classify(
                run_id=run_id,
                corpus_id=corpus_id,
                blocks=changed_blocks,
            )
            executed_keys.append(classify_meta)
            classify_executed = True
            enforced = _enforce_untrusted_classifications(changed_blocks, batch.classifications)
            classifications = [item.model_dump(mode="json") for item in enforced]
            await self._record_understand_stage(
                analysis_id,
                corpus_id,
                "classify",
                "completed",
                operation_count=batch.usage.operation_count,
                attempt_count=batch.usage.attempt_count,
            )
            relevant_ids = {
                str(item["source_block_id"])
                for item in classifications
                if item.get("relevant") is True and item.get("category") != UNTRUSTED_CATEGORY
            }
            extract_blocks = [
                item
                for item in changed_blocks
                if str(item.source_block_id) in relevant_ids
                and not contains_untrusted_instruction(item.normalized_text)
            ]
            if extract_blocks:
                extract_versions = sorted({str(item.source_version_id) for item in extract_blocks})
                extracted, extract_meta = await self._execute_extract(
                    run_id=run_id,
                    corpus_id=corpus_id,
                    blocks=extract_blocks,
                )
                executed_keys.append(extract_meta)
                extract_executed = True
                proposed = [item.model_dump(mode="json") for item in extracted.facts]
                await self._record_understand_stage(
                    analysis_id,
                    corpus_id,
                    "extract_facts",
                    "completed",
                    operation_count=extracted.usage.operation_count,
                    attempt_count=extracted.usage.attempt_count,
                )
            else:
                await self._record_understand_stage(
                    analysis_id,
                    corpus_id,
                    "extract_facts",
                    "skipped",
                    skip_reason="no_relevant_blocks",
                )
        else:
            await self._record_understand_stage(
                analysis_id, corpus_id, "classify", "skipped", skip_reason="no_changed_blocks"
            )
            await self._record_understand_stage(
                analysis_id,
                corpus_id,
                "extract_facts",
                "skipped",
                skip_reason="no_changed_blocks",
            )
        await self._record_understand_stage(analysis_id, corpus_id, "load_corpus", "completed")
        await self._record_understand_stage(
            analysis_id,
            corpus_id,
            "retrieve_context",
            "skipped",
            skip_reason="incremental_changed_sources_only",
        )
        supported_new = await self._validate_proposed(corpus_id, proposed, classifications)
        await self._record_understand_stage(
            analysis_id, corpus_id, "validate_provenance", "completed"
        )
        extracted_refs = [
            FactImpactRef(
                id=UUID(str(item["id"])),
                category=str(item["category"]),
                subject_key=str(item["subject_key"]),
                support_status=str(item["support_status"]),
                source_version_id=(
                    UUID(str(cast(dict[str, object], item["citation"])["source_version_id"]))
                    if isinstance(item.get("citation"), dict)
                    else None
                ),
                source_block_id=(
                    UUID(str(item["source_block_id"])) if item.get("source_block_id") else None
                ),
                canonical_hash=_fact_payload_hash(item),
            )
            for item in supported_new
        ]
        if versions_match:
            impact = plan_impact(
                changes=changes,
                facts=[_fact_impact_ref(fact) for fact in facts],
                contradictions=[
                    _contradiction_impact_ref(item, {fact.id: fact for fact in facts})
                    for item in contradictions
                ],
                block_ids_by_version=await self._block_ids_by_version(
                    corpus_id,
                    {item.source_version_id for item in changes.unchanged}
                    | changes.changed_source_version_ids
                    | {item.source_version_id for item in changes.added}
                    | changes.retired_source_version_ids,
                ),
                rules=self.examine.ruleset.rules,
                extracted_facts=extracted_refs,
            )
        reused_facts, fact_id_map, fact_hashes = _copy_reused_facts(
            [fact for fact in facts if fact.support_status == "supported"],
            impact.reused_fact_ids,
        )
        all_supported = [
            *[item for item in reused_facts if item["support_status"] == "supported"],
            *supported_new,
        ]
        unknown = _unknown_fields(all_supported)
        unknown_hashes = {str(item["id"]): _fact_payload_hash(item) for item in unknown}
        recompute_keys = set(impact.affected_keys)
        recomputed_contradictions = detect_supported_contradictions(
            [
                item
                for item in all_supported
                if (str(item["category"]), str(item["subject_key"])) in recompute_keys
            ]
        )
        for item in recomputed_contradictions:
            item["id"] = str(uuid4())
        reused_contradictions, contradiction_id_map, contradiction_hashes = (
            _copy_reused_contradictions(
                contradictions,
                facts,
                fact_id_map,
                impact.reused_contradiction_ids,
            )
        )
        new_contradiction_hashes = {
            str(item["id"]): _contradiction_payload_hash(
                item, {str(row["id"]): row for row in [*reused_facts, *supported_new, *unknown]}
            )
            for item in recomputed_contradictions
        }
        contradiction_hashes.update(new_contradiction_hashes)
        all_facts = [*reused_facts, *supported_new, *unknown]
        fact_hashes.update({str(item["id"]): _fact_payload_hash(item) for item in supported_new})
        fact_hashes.update(unknown_hashes)
        await self._persist_analysis(
            analysis_id=analysis_id,
            corpus_id=corpus_id,
            facts=all_facts,
            contradictions=[*reused_contradictions, *recomputed_contradictions],
            classifications=classifications,
        )
        await self._record_understand_stage(
            analysis_id, corpus_id, "detect_contradictions", "completed"
        )
        await self._record_understand_stage(analysis_id, corpus_id, "finalize", "completed")
        run = await self.understand.get_run(corpus_id, analysis_id)
        facts_by_baseline_id = {fact.id: fact for fact in facts}
        baseline_contradiction_hashes = {
            str(item.id): _contradiction_impact_ref(item, facts_by_baseline_id).canonical_hash
            for item in contradictions
        }
        return {
            "run": run,
            "impact": impact,
            "fact_id_map": fact_id_map,
            "contradiction_id_map": contradiction_id_map,
            "fact_hashes": fact_hashes,
            "contradiction_hashes": contradiction_hashes,
            "reused_fact_ids": [str(item["id"]) for item in reused_facts],
            "recomputed_fact_ids": [str(item["id"]) for item in supported_new],
            "reused_contradiction_ids": [str(item["id"]) for item in reused_contradictions],
            "recomputed_contradiction_ids": [str(item["id"]) for item in recomputed_contradictions],
            "executed_operation_keys": executed_keys,
            "reused_operation_keys": [
                item for item in reused_keys if item["disposition"] == "reused"
            ],
            "skipped_operation_keys": [
                item for item in reused_keys if item["disposition"] == "skipped"
            ],
            "classify_executed_source_version_ids": classify_versions,
            "classify_skipped_source_version_ids": skipped_versions,
            "extract_executed_source_version_ids": extract_versions,
            "extract_skipped_source_version_ids": skipped_versions,
            "classify_executed": classify_executed,
            "extract_executed": extract_executed,
            "validate_provenance_executed": True,
            "detect_contradictions_executed": True,
            "evaluate_rules_executed": False,
            "classifications": classifications,
            "baseline_fact_hashes": {
                str(fact.id): _orm_fact_hash(fact)
                for fact in facts
                if fact.id in impact.reused_fact_ids
            },
            "baseline_contradiction_hashes": baseline_contradiction_hashes,
        }

    async def _incremental_examine(
        self,
        *,
        corpus_id: UUID,
        analysis: dict[str, Any],
        impact: ImpactSet,
        baseline_findings: Sequence[Finding],
        fact_id_map: dict[UUID, UUID],
        contradiction_id_map: dict[UUID, UUID],
    ) -> tuple[ExaminationRun, dict[str, object]]:
        analysis_run: AnalysisRun = analysis["run"]
        examination_id = uuid4()
        examination = ExaminationRun(
            id=examination_id,
            corpus_id=corpus_id,
            analysis_run_id=analysis_run.id,
            status="running",
            findings_status="pending",
            ruleset_version=self.examine.ruleset.version,
            graph_version=EXAMINE_GRAPH_VERSION,
            started_at=utcnow(),
            configuration={
                "mode": "incremental",
                "affected_rule_ids": sorted(impact.affected_rule_ids),
                "reused_rule_ids": sorted(impact.reused_rule_ids),
                "global_rule_reasons": impact.global_rule_reasons,
            },
            result_payload={},
        )
        async with self.session_factory() as session:
            session.add(examination)
            await session.commit()
        new_facts = await self.understand.list_facts(corpus_id, analysis_run.id)
        new_contradictions = await self.understand.list_contradictions(corpus_id, analysis_run.id)
        view = _understanding_view(new_facts, new_contradictions, attested=True)
        selected = select_rules(view, self.examine.ruleset.rules)
        selected_ids = [rule.rule_id for rule in selected]
        reused_findings: list[dict[str, object]] = []
        recomputed_findings: list[dict[str, object]] = []
        reused_rule_ids: list[str] = []
        evaluated_rule_ids: list[str] = []
        baseline_by_rule = {item.rule_id: item for item in baseline_findings}
        specific_results: list[Any] = []
        for rule in selected:
            if rule.rule_id == OPEN_CONTRADICTION_RULE_ID:
                continue
            if rule.rule_id in impact.reused_rule_ids and rule.rule_id in baseline_by_rule:
                payload = _remap_finding(
                    baseline_by_rule[rule.rule_id],
                    fact_id_map,
                    contradiction_id_map,
                )
                reused_findings.append(payload)
                reused_rule_ids.append(rule.rule_id)
                specific_results.append(payload)
            else:
                evaluation = evaluate_rule(rule, view)
                payload = _evaluation_finding_payload(evaluation)
                recomputed_findings.append(payload)
                evaluated_rule_ids.append(rule.rule_id)
                specific_results.append(payload)
        consumed = {
            str(item_id)
            for payload in specific_results
            for item_id in _as_str_list(payload.get("contradiction_ids"))
        }
        open_rule = next(
            rule
            for rule in self.examine.ruleset.rules
            if rule.rule_id == OPEN_CONTRADICTION_RULE_ID
        )
        if OPEN_CONTRADICTION_RULE_ID in selected_ids:
            if (
                OPEN_CONTRADICTION_RULE_ID in impact.reused_rule_ids
                and OPEN_CONTRADICTION_RULE_ID in baseline_by_rule
            ):
                reused_findings.append(
                    _remap_finding(
                        baseline_by_rule[OPEN_CONTRADICTION_RULE_ID],
                        fact_id_map,
                        contradiction_id_map,
                    )
                )
                reused_rule_ids.append(OPEN_CONTRADICTION_RULE_ID)
            else:
                evaluation = evaluate_open_contradictions(open_rule, view, consumed=consumed)
                recomputed_findings.append(_evaluation_finding_payload(evaluation))
                evaluated_rule_ids.append(OPEN_CONTRADICTION_RULE_ID)
        all_findings = [*reused_findings, *recomputed_findings]
        by_id = facts_by_id(view)
        for payload in all_findings:
            fact_ids = _as_str_list(payload.get("fact_ids"))
            cited = tuple(by_id[item] for item in fact_ids if item in by_id)
            payload["citations"] = [dict(item) for item in citations_for(cited)]
        summary = _summarize_findings(all_findings)
        await self._record_examine_stage(
            examination_id, corpus_id, "load_understanding", "completed"
        )
        await self._record_examine_stage(examination_id, corpus_id, "select_rules", "completed")
        await self._record_examine_stage(
            examination_id,
            corpus_id,
            "evaluate_rules",
            "completed" if evaluated_rule_ids else "skipped",
            rule_evaluation_count=len(evaluated_rule_ids),
            skip_reason=None if evaluated_rule_ids else "all_rules_reused",
        )
        await self.examine.revalidate_finding_payloads(
            corpus_id=corpus_id,
            analysis_run_id=analysis_run.id,
            findings=all_findings,
            view=view,
            classifications=analysis.get("classifications", ()),
        )
        await self._record_examine_stage(
            examination_id, corpus_id, "validate_evidence", "completed"
        )
        await self._record_examine_stage(
            examination_id, corpus_id, "summarize_findings", "completed"
        )
        await self._persist_examination(
            examination_id=examination_id,
            corpus_id=corpus_id,
            analysis_run_id=analysis_run.id,
            findings=all_findings,
            summary=summary,
            selected_ids=selected_ids,
        )
        await self._record_examine_stage(examination_id, corpus_id, "finalize", "completed")
        persisted = await self.examine.get_run(corpus_id, examination_id)
        return persisted, {
            "evaluated_rule_ids": evaluated_rule_ids,
            "reused_rule_ids": reused_rule_ids,
            "global_rule_reasons": impact.global_rule_reasons,
            "evaluate_rules_executed": bool(evaluated_rule_ids),
            "validate_evidence_executed": True,
            "open_review_executed": True,
        }

    async def _review_evidence(
        self,
        *,
        corpus_id: UUID,
        baseline: CorpusRevision,
        new_session: ReviewSession,
    ) -> dict[str, object]:
        new_items: list[ReviewItem] = []
        async with self.session_factory() as session:
            new_items = list(
                await session.scalars(
                    select(ReviewItem).where(
                        ReviewItem.review_session_id == new_session.id,
                        ReviewItem.corpus_id == corpus_id,
                    )
                )
            )
        new_findings = {
            item.id: item
            for item in await self.examine.list_findings(corpus_id, new_session.examination_run_id)
        }
        new_facts = {
            item.id: item
            for item in await self.understand.list_facts(corpus_id, new_session.analysis_run_id)
        }
        new_contradictions = {
            item.id: item
            for item in await self.understand.list_contradictions(
                corpus_id, new_session.analysis_run_id
            )
        }
        previous_items: dict[str, ReviewItem] = {}
        previous_findings: dict[UUID, Finding] = {}
        previous_facts: dict[UUID, Fact] = {}
        previous_contradictions: dict[UUID, Contradiction] = {}
        previous_decisions = 0
        previous_session_id: str | None = None
        if baseline.review_session_id is not None:
            previous_session_id = str(baseline.review_session_id)
            async with self.session_factory() as session:
                rows = list(
                    await session.scalars(
                        select(ReviewItem).where(
                            ReviewItem.review_session_id == baseline.review_session_id,
                            ReviewItem.corpus_id == corpus_id,
                        )
                    )
                )
                previous_items = {item.rule_id: item for item in rows}
                previous_decisions = len(
                    list(
                        await session.scalars(
                            select(ReviewDecision).where(
                                ReviewDecision.review_session_id == baseline.review_session_id,
                                ReviewDecision.corpus_id == corpus_id,
                            )
                        )
                    )
                )
            previous_findings = {
                item.id: item
                for item in await self.examine.list_findings(corpus_id, baseline.examination_run_id)
            }
            previous_facts = {
                item.id: item
                for item in await self.understand.list_facts(corpus_id, baseline.analysis_run_id)
            }
            previous_contradictions = {
                item.id: item
                for item in await self.understand.list_contradictions(
                    corpus_id, baseline.analysis_run_id
                )
            }
        items: list[dict[str, object]] = []
        reused_pairs: list[dict[str, object]] = []
        for item in new_items:
            after_finding = new_findings.get(item.finding_id)
            after_payload = (
                _review_item_canonical(item, after_finding, new_facts, new_contradictions)
                if after_finding is not None
                else None
            )
            previous = previous_items.get(item.rule_id)
            before_payload: dict[str, object] | None = None
            if previous is not None:
                before_finding = previous_findings.get(previous.finding_id)
                if before_finding is not None:
                    before_payload = _review_item_canonical(
                        previous,
                        before_finding,
                        previous_facts,
                        previous_contradictions,
                    )
            if previous is None or before_payload is None or after_payload is None:
                disposition = "added"
                require_fresh = True
                bytes_equal = False
            else:
                before_bytes = canonical_bytes(before_payload)
                after_bytes = canonical_bytes(after_payload)
                bytes_equal = before_bytes == after_bytes
                if bytes_equal:
                    disposition = "reused"
                    require_fresh = item.review_required
                else:
                    disposition = "changed"
                    require_fresh = True
            entry: dict[str, object] = {
                "item_id": str(item.id),
                "rule_id": item.rule_id,
                "disposition": disposition,
                "review_status": item.review_status,
                "review_required": item.review_required,
                "require_fresh_review": require_fresh,
                "implicit_approval": False,
            }
            if before_payload is not None and after_payload is not None:
                entry["canonical_hash_before"] = canonical_hash(before_payload)
                entry["canonical_hash_after"] = canonical_hash(after_payload)
                entry["canonical_bytes_equal"] = bytes_equal
                entry["baseline_review_item_id"] = (
                    str(previous.id) if previous is not None else None
                )
                if disposition == "reused":
                    reused_pairs.append(
                        {
                            "rule_id": item.rule_id,
                            "baseline_review_item_id": str(previous.id)
                            if previous is not None
                            else None,
                            "incremental_review_item_id": str(item.id),
                            "canonical_hash_before": entry["canonical_hash_before"],
                            "canonical_hash_after": entry["canonical_hash_after"],
                            "canonical_bytes_equal": True,
                        }
                    )
            items.append(entry)
        obsolete = [
            {"rule_id": rule_id, "disposition": "obsolete"}
            for rule_id in previous_items
            if rule_id not in {item.rule_id for item in new_items}
        ]
        return {
            "previous_review_session_id": previous_session_id,
            "new_review_session_id": str(new_session.id),
            "previous_decision_count": previous_decisions,
            "new_decision_count": 0,
            "implicit_approval": False,
            "items": items,
            "obsolete": obsolete,
            "canonical_unchanged_review_items": reused_pairs,
        }

    async def _commit_incremental_result(
        self,
        *,
        run_id: UUID,
        corpus_id: UUID,
        baseline: CorpusRevision,
        snapshots: tuple[SourceSnapshot, ...],
        status: str,
        change_kind: str,
        analysis_run_id: UUID,
        examination_run_id: UUID,
        review_session_id: UUID,
        impact: dict[str, object],
        evidence: dict[str, object],
        measurement: dict[str, object],
        artifacts: list[IncrementalArtifactEvidence],
    ) -> IncrementalRun:
        operation_keys = await self._source_operation_keys(corpus_id, snapshots)
        revision = CorpusRevision(
            id=uuid4(),
            corpus_id=corpus_id,
            revision_number=baseline.revision_number + 1,
            is_current=True,
            analysis_run_id=analysis_run_id,
            examination_run_id=examination_run_id,
            review_session_id=review_session_id,
            source_version_set=snapshots_to_payload(snapshots),
            taxonomy_version=TAXONOMY_VERSION,
            understand_graph_version=GRAPH_VERSION,
            prompt_config_version=PROMPT_CONFIG_VERSION,
            ruleset_version=self.examine.ruleset.version,
            examine_graph_version=EXAMINE_GRAPH_VERSION,
            configuration={
                "incremental_graph_version": INCREMENTAL_GRAPH_VERSION,
                "source_operation_keys": operation_keys,
                "baseline_revision_id": str(baseline.id),
            },
        )
        async with self.session_factory() as session, session.begin():
            current = await session.scalar(
                select(CorpusRevision)
                .where(
                    CorpusRevision.id == baseline.id,
                    CorpusRevision.corpus_id == corpus_id,
                )
                .with_for_update()
            )
            if current is None or not current.is_current:
                raise ConflictError(
                    "stale_baseline",
                    "The corpus baseline changed before this incremental run could advance.",
                    "Reload the current revision and retry incremental processing.",
                )
            if self.fail_before_finalize:
                raise IncrementalFinalizeInjectedError("fail_before_finalize")
            current.is_current = False
            session.add(revision)
            for snapshot in snapshots:
                session.add(_revision_source_row(revision.id, corpus_id, snapshot))
            run = await session.scalar(
                select(IncrementalRun).where(
                    IncrementalRun.id == run_id,
                    IncrementalRun.corpus_id == corpus_id,
                )
            )
            if run is None:
                raise NotFoundError(
                    "incremental_run_not_found",
                    "The incremental run disappeared before finalization.",
                    "Retry the incremental run after verifying PostgreSQL is reachable.",
                )
            run.status = status
            run.change_kind = change_kind
            run.result_revision_id = revision.id
            run.analysis_run_id = analysis_run_id
            run.examination_run_id = examination_run_id
            run.review_session_id = review_session_id
            run.impact = impact
            run.evidence = evidence
            run.measurement = measurement
            run.completed_at = utcnow() if status == "completed" else None
            for artifact in artifacts:
                artifact.incremental_run_id = run_id
                artifact.corpus_id = corpus_id
                session.add(artifact)
        return await self.get_run(corpus_id, run_id)

    async def _complete_unchanged(
        self,
        run: IncrementalRun,
        baseline: CorpusRevision,
        changes: ChangeSet,
        perf: float,
    ) -> IncrementalRun:
        reused_keys, skipped = await self._unchanged_operation_keys(
            corpus_id=run.corpus_id,
            unchanged=changes.unchanged,
        )
        skipped_ops = [item for item in reused_keys if item["disposition"] == "skipped"]
        reused_ops = [item for item in reused_keys if item["disposition"] == "reused"]
        evidence = {
            "changed_source_ids": [],
            "changed_source_version_ids": [],
            "classify_executed_source_version_ids": [],
            "classify_skipped_source_version_ids": skipped,
            "extract_executed_source_version_ids": [],
            "extract_skipped_source_version_ids": skipped,
            "executed_operation_keys": [],
            "reused_operation_keys": reused_ops,
            "skipped_operation_keys": skipped_ops,
            "stages_executed": ["detect_changes"],
            "stages_skipped": [
                "classify",
                "extract_facts",
                "evaluate_rules",
                "open_review",
            ],
            "full_rerun": False,
        }
        return await self._finalize_run(
            run_id=run.id,
            corpus_id=run.corpus_id,
            status="completed",
            change_kind="unchanged",
            result_revision_id=baseline.id,
            analysis_run_id=None,
            examination_run_id=None,
            review_session_id=None,
            impact=_impact_payload(changes, None),
            evidence=evidence,
            measurement={
                "changed_source_count": 0,
                "incremental_model_operations": 0,
                "estimated_cost_usd": 0.0,
                "cost_basis": "zero_deterministic",
                "duration_ms": max(0, int((time.perf_counter() - perf) * 1000)),
            },
            artifacts=[],
        )

    async def _persist_stale(
        self,
        corpus_id: UUID,
        requested_baseline_id: UUID,
        current_revision_id: UUID,
    ) -> IncrementalRun:
        run = IncrementalRun(
            id=uuid4(),
            corpus_id=corpus_id,
            baseline_revision_id=requested_baseline_id,
            status="stale_baseline",
            change_kind="stale_baseline",
            impact={
                "requested_baseline_revision_id": str(requested_baseline_id),
                "current_revision_id": str(current_revision_id),
            },
            evidence={"full_rerun": False, "mixed_base": False},
            measurement={"changed_source_count": 0, "estimated_cost_usd": 0.0},
            error_code="stale_baseline",
            error_detail="The supplied baseline is not the current corpus revision.",
            error_action="Reload the current corpus revision and retry.",
            started_at=utcnow(),
        )
        async with self.session_factory() as session:
            session.add(run)
            await session.commit()
            await session.refresh(run)
        return run

    async def _finalize_run(
        self,
        *,
        run_id: UUID,
        corpus_id: UUID,
        status: str,
        change_kind: str,
        result_revision_id: UUID | None,
        analysis_run_id: UUID | None,
        examination_run_id: UUID | None,
        review_session_id: UUID | None,
        impact: dict[str, object],
        evidence: dict[str, object],
        measurement: dict[str, object],
        artifacts: list[IncrementalArtifactEvidence],
    ) -> IncrementalRun:
        async with self.session_factory() as session, session.begin():
            run = await session.scalar(
                select(IncrementalRun).where(
                    IncrementalRun.id == run_id,
                    IncrementalRun.corpus_id == corpus_id,
                )
            )
            if run is None:
                raise NotFoundError(
                    "incremental_run_not_found",
                    "The incremental run disappeared before finalization.",
                    "Retry the incremental run after verifying PostgreSQL is reachable.",
                )
            run.status = status
            run.change_kind = change_kind
            run.result_revision_id = result_revision_id
            run.analysis_run_id = analysis_run_id
            run.examination_run_id = examination_run_id
            run.review_session_id = review_session_id
            run.impact = impact
            run.evidence = evidence
            run.measurement = measurement
            run.completed_at = utcnow() if status == "completed" else None
            for artifact in artifacts:
                artifact.incremental_run_id = run_id
                artifact.corpus_id = corpus_id
                session.add(artifact)
        return await self.get_run(corpus_id, run_id)

    async def _fail_run(self, run_id: UUID, corpus_id: UUID, error: Phase02Error) -> None:
        async with self.session_factory() as session, session.begin():
            run = await session.scalar(
                select(IncrementalRun).where(
                    IncrementalRun.id == run_id,
                    IncrementalRun.corpus_id == corpus_id,
                )
            )
            if run is None:
                return
            run.status = "failed"
            run.error_code = error.code
            run.error_detail = error.detail
            run.error_action = error.action

    async def _mark_stale(self, run_id: UUID, corpus_id: UUID, error: ConflictError) -> None:
        async with self.session_factory() as session, session.begin():
            run = await session.scalar(
                select(IncrementalRun).where(
                    IncrementalRun.id == run_id,
                    IncrementalRun.corpus_id == corpus_id,
                )
            )
            if run is None:
                return
            run.status = "stale_baseline"
            run.change_kind = "stale_baseline"
            run.result_revision_id = None
            run.evidence = {"full_rerun": False, "mixed_base": False}
            run.error_code = error.code
            run.error_detail = error.detail
            run.error_action = error.action
            run.completed_at = None

    async def _current_revision(self, corpus_id: UUID) -> CorpusRevision | None:
        async with self.session_factory() as session:
            revision = await session.scalar(
                select(CorpusRevision).where(
                    CorpusRevision.corpus_id == corpus_id,
                    CorpusRevision.is_current.is_(True),
                )
            )
        return revision if isinstance(revision, CorpusRevision) else None

    async def _latest_snapshots(self, corpus_id: UUID) -> tuple[SourceSnapshot, ...]:
        async with self.session_factory() as session:
            sources = {
                source.id: source
                for source in await session.scalars(
                    select(Source).where(Source.corpus_id == corpus_id)
                )
            }
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
        return tuple(
            SourceSnapshot(
                source_id=version.source_id,
                source_version_id=version.id,
                logical_name=sources[version.source_id].logical_name,
                sha256=version.sha256,
            )
            for version in latest.values()
            if version.source_id in sources
        )

    async def _block_contexts(self, corpus_id: UUID, version_ids: set[UUID]) -> list[BlockContext]:
        if not version_ids:
            return []
        async with self.session_factory() as session:
            versions = {
                version.id: version
                for version in await session.scalars(
                    select(SourceVersion).where(
                        SourceVersion.corpus_id == corpus_id,
                        SourceVersion.id.in_(version_ids),
                    )
                )
            }
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
        return [
            BlockContext(
                source_block_id=block.id,
                source_version_id=block.source_version_id,
                source_sha256=versions[block.source_version_id].sha256,
                format=versions[block.source_version_id].declared_format,  # type: ignore[arg-type]
                native_locator=block.native_locator,
                normalized_text=block.normalized_text,
                block_type=block.block_type,
            )
            for block in blocks
            if block.source_version_id in versions
        ]

    async def _block_ids_by_version(
        self, corpus_id: UUID, version_ids: set[UUID]
    ) -> dict[UUID, list[UUID]]:
        if not version_ids:
            return {}
        async with self.session_factory() as session:
            blocks = list(
                await session.scalars(
                    select(SourceBlock).where(
                        SourceBlock.corpus_id == corpus_id,
                        SourceBlock.source_version_id.in_(version_ids),
                    )
                )
            )
        grouped: dict[UUID, list[UUID]] = {}
        for block in blocks:
            grouped.setdefault(block.source_version_id, []).append(block.id)
        return grouped

    async def _source_operation_keys(
        self, corpus_id: UUID, snapshots: Sequence[SourceSnapshot]
    ) -> dict[str, dict[str, str]]:
        keys: dict[str, dict[str, str]] = {}
        for snapshot in snapshots:
            blocks = await self._block_contexts(corpus_id, {snapshot.source_version_id})
            keys[str(snapshot.source_version_id)] = {
                "classify": self._content_key_for_blocks(
                    corpus_id=corpus_id,
                    operation_type="classify",
                    snapshot=snapshot,
                    blocks=blocks,
                ),
                "extract": self._content_key_for_blocks(
                    corpus_id=corpus_id,
                    operation_type="extract",
                    snapshot=snapshot,
                    blocks=blocks,
                ),
                "sha256": snapshot.sha256,
            }
        return keys

    def _content_key_for_blocks(
        self,
        *,
        corpus_id: UUID,
        operation_type: str,
        snapshot: SourceSnapshot,
        blocks: Sequence[BlockContext],
    ) -> str:
        return make_content_operation_key(
            corpus_id=corpus_id,
            stage="understand",
            operation_type=operation_type,
            source_input_version=(
                blocks_source_input_version(blocks) if blocks else snapshot.sha256
            ),
            request_hash=request_hash_for_blocks(blocks),
            model_provider=self.adapter.mode,
            model_name=self.adapter.model_name,
            taxonomy_version=TAXONOMY_VERSION,
            understand_graph_version=GRAPH_VERSION,
            prompt_config_version=PROMPT_CONFIG_VERSION,
        )

    async def _unchanged_operation_keys(
        self,
        *,
        corpus_id: UUID,
        unchanged: tuple[SourceSnapshot, ...],
    ) -> tuple[list[dict[str, object]], list[str]]:
        entries: list[dict[str, object]] = []
        skipped: list[str] = []
        for snapshot in unchanged:
            blocks = await self._block_contexts(corpus_id, {snapshot.source_version_id})
            for operation_type in ("classify", "extract"):
                key = self._content_key_for_blocks(
                    corpus_id=corpus_id,
                    operation_type=operation_type,
                    snapshot=snapshot,
                    blocks=blocks,
                )
                row = await self.ledger.get_completed(key)
                if row is None:
                    disposition = "skipped"
                    durable_operation_id = None
                else:
                    disposition = "reused"
                    durable_operation_id = str(row.id)
                entries.append(
                    {
                        "operation_type": operation_type,
                        "source_version_id": str(snapshot.source_version_id),
                        "content_key": key,
                        "content_key_before": row.operation_key if row is not None else None,
                        "disposition": disposition,
                        "executed": False,
                        "durable_operation_id": durable_operation_id,
                    }
                )
            skipped.append(str(snapshot.source_version_id))
        return entries, skipped

    async def _execute_classify(
        self,
        *,
        run_id: UUID,
        corpus_id: UUID,
        blocks: Sequence[BlockContext],
    ) -> tuple[ClassificationBatch, dict[str, object]]:
        source_input_version = blocks_source_input_version(blocks)
        request = [item.model_dump(mode="json") for item in blocks]
        result, row, reused = await self.ledger.execute_content(
            corpus_id=corpus_id,
            incremental_run_id=run_id,
            stage="understand",
            operation_type="classify",
            source_input_version=source_input_version,
            request=request,
            model_provider=self.adapter.mode,
            model_name=self.adapter.model_name,
            taxonomy_version=TAXONOMY_VERSION,
            understand_graph_version=GRAPH_VERSION,
            prompt_config_version=PROMPT_CONFIG_VERSION,
            fn=lambda: self.adapter.classify_blocks(blocks),
            dump=lambda batch: cast(dict[str, object], batch.model_dump(mode="json")),
            restore=lambda payload: ClassificationBatch.model_validate(payload),
            reconcile_ambiguous=self.adapter.mode == "deterministic",
        )
        return result, _operation_meta(
            operation_type="classify",
            corpus_id=corpus_id,
            blocks=blocks,
            source_input_version=source_input_version,
            row_id=row.id,
            reused=reused,
            model_provider=self.adapter.mode,
            model_name=self.adapter.model_name,
        )

    async def _execute_extract(
        self,
        *,
        run_id: UUID,
        corpus_id: UUID,
        blocks: Sequence[BlockContext],
    ) -> tuple[ExtractionBatch, dict[str, object]]:
        source_input_version = blocks_source_input_version(blocks)
        request = [item.model_dump(mode="json") for item in blocks]
        result, row, reused = await self.ledger.execute_content(
            corpus_id=corpus_id,
            incremental_run_id=run_id,
            stage="understand",
            operation_type="extract",
            source_input_version=source_input_version,
            request=request,
            model_provider=self.adapter.mode,
            model_name=self.adapter.model_name,
            taxonomy_version=TAXONOMY_VERSION,
            understand_graph_version=GRAPH_VERSION,
            prompt_config_version=PROMPT_CONFIG_VERSION,
            fn=lambda: self.adapter.extract_facts(blocks),
            dump=lambda batch: cast(dict[str, object], batch.model_dump(mode="json")),
            restore=lambda payload: ExtractionBatch.model_validate(payload),
            reconcile_ambiguous=self.adapter.mode == "deterministic",
        )
        return result, _operation_meta(
            operation_type="extract",
            corpus_id=corpus_id,
            blocks=blocks,
            source_input_version=source_input_version,
            row_id=row.id,
            reused=reused,
            model_provider=self.adapter.mode,
            model_name=self.adapter.model_name,
        )

    async def _persisted_canonical_proof(
        self,
        *,
        corpus_id: UUID,
        baseline: CorpusRevision,
        analysis_run_id: UUID,
        examination_run_id: UUID,
        fact_id_map: dict[UUID, UUID],
        contradiction_id_map: dict[UUID, UUID],
        reused_rule_ids: list[str],
    ) -> dict[str, list[dict[str, object]]]:
        baseline_facts = await self.understand.list_facts(corpus_id, baseline.analysis_run_id)
        new_facts = await self.understand.list_facts(corpus_id, analysis_run_id)
        baseline_contradictions = await self.understand.list_contradictions(
            corpus_id, baseline.analysis_run_id
        )
        new_contradictions = await self.understand.list_contradictions(corpus_id, analysis_run_id)
        baseline_findings = await self.examine.list_findings(corpus_id, baseline.examination_run_id)
        new_findings = await self.examine.list_findings(corpus_id, examination_run_id)
        facts_before = {fact.id: fact for fact in baseline_facts}
        facts_after = {fact.id: fact for fact in new_facts}
        fact_pairs: list[dict[str, object]] = []
        for old_id, new_id in fact_id_map.items():
            before_fact = facts_before.get(old_id)
            after_fact = facts_after.get(new_id)
            if before_fact is None or after_fact is None:
                continue
            before_payload = _orm_fact_payload(before_fact)
            after_payload = _orm_fact_payload(after_fact)
            before_bytes = canonical_bytes(before_payload)
            after_bytes = canonical_bytes(after_payload)
            fact_pairs.append(
                {
                    "baseline_fact_id": str(old_id),
                    "incremental_fact_id": str(new_id),
                    "canonical_hash_before": canonical_hash(before_payload),
                    "canonical_hash_after": canonical_hash(after_payload),
                    "canonical_bytes_equal": before_bytes == after_bytes,
                }
            )
        contradictions_before = {item.id: item for item in baseline_contradictions}
        contradictions_after = {item.id: item for item in new_contradictions}
        contradiction_pairs: list[dict[str, object]] = []
        for old_id, new_id in contradiction_id_map.items():
            before_item = contradictions_before.get(old_id)
            after_item = contradictions_after.get(new_id)
            if before_item is None or after_item is None:
                continue
            before_payload = contradiction_canonical_payload(
                contradiction_type=before_item.contradiction_type,
                reason=before_item.reason,
                status=before_item.status,
                fact_a=_orm_fact_payload(facts_before[before_item.fact_a_id]),
                fact_b=_orm_fact_payload(facts_before[before_item.fact_b_id]),
            )
            after_payload = contradiction_canonical_payload(
                contradiction_type=after_item.contradiction_type,
                reason=after_item.reason,
                status=after_item.status,
                fact_a=_orm_fact_payload(facts_after[after_item.fact_a_id]),
                fact_b=_orm_fact_payload(facts_after[after_item.fact_b_id]),
            )
            contradiction_pairs.append(
                {
                    "baseline_contradiction_id": str(old_id),
                    "incremental_contradiction_id": str(new_id),
                    "canonical_hash_before": canonical_hash(before_payload),
                    "canonical_hash_after": canonical_hash(after_payload),
                    "canonical_bytes_equal": canonical_bytes(before_payload)
                    == canonical_bytes(after_payload),
                }
            )
        findings_before = {item.rule_id: item for item in baseline_findings}
        findings_after = {item.rule_id: item for item in new_findings}
        finding_pairs: list[dict[str, object]] = []
        for rule_id in reused_rule_ids:
            before_finding = findings_before.get(rule_id)
            after_finding = findings_after.get(rule_id)
            if before_finding is None or after_finding is None:
                continue
            before_payload = _finding_canonical(before_finding, facts_before, contradictions_before)
            after_payload = _finding_canonical(after_finding, facts_after, contradictions_after)
            finding_pairs.append(
                {
                    "rule_id": rule_id,
                    "canonical_hash_before": canonical_hash(before_payload),
                    "canonical_hash_after": canonical_hash(after_payload),
                    "canonical_bytes_equal": canonical_bytes(before_payload)
                    == canonical_bytes(after_payload),
                }
            )
        return {
            "facts": fact_pairs,
            "contradictions": contradiction_pairs,
            "findings": finding_pairs,
        }

    async def _validate_proposed(
        self,
        corpus_id: UUID,
        proposed: list[dict[str, object]],
        classifications: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        untrusted_ids = {
            UUID(str(item["source_block_id"]))
            for item in classifications
            if item.get("category") == UNTRUSTED_CATEGORY
        }
        supported: list[dict[str, object]] = []
        for raw in proposed:
            item = ProposedFact.model_validate(raw)
            if item.citation is None:
                continue
            try:
                validation = await self.phase02.validate_citation(
                    corpus_id=corpus_id,
                    citation=item.citation,
                )
            except Phase02Error:
                continue
            reason = validate_assertion(
                category=item.category,
                subject_key=item.subject_key,
                normalized_value=item.normalized_value,
                proposed_source_block_id=item.source_block_id,
                evidence_text=validation.resolved_quote,
                resolved_block_id=validation.source_block_id,
                untrusted_block_ids=untrusted_ids,
            )
            if reason is not None:
                continue
            supported.append(
                {
                    "id": str(uuid4()),
                    "category": item.category,
                    "subject_key": item.subject_key,
                    "normalized_value": item.normalized_value,
                    "confidence": item.confidence,
                    "support_status": "supported",
                    "citation": item.citation.model_dump(mode="json"),
                    "source_block_id": str(validation.source_block_id),
                }
            )
        return supported

    async def _persist_analysis(
        self,
        *,
        analysis_id: UUID,
        corpus_id: UUID,
        facts: Sequence[dict[str, object]],
        contradictions: Sequence[dict[str, object]],
        classifications: list[dict[str, object]],
    ) -> None:
        supported = [item for item in facts if item["support_status"] == "supported"]
        async with self.session_factory() as session, session.begin():
            run = await session.scalar(
                select(AnalysisRun).where(
                    AnalysisRun.id == analysis_id,
                    AnalysisRun.corpus_id == corpus_id,
                )
            )
            if run is None:
                raise NotFoundError(
                    "analysis_run_not_found",
                    "The incremental analysis run was not found.",
                    "Retry the incremental run.",
                )
            for item in facts:
                session.add(
                    Fact(
                        id=UUID(str(item["id"])),
                        run_id=analysis_id,
                        corpus_id=corpus_id,
                        category=str(item["category"]),
                        subject_key=str(item["subject_key"]),
                        normalized_value=str(item["normalized_value"]),
                        confidence=float(str(item["confidence"])),
                        support_status=str(item["support_status"]),
                        rejection_reason=None,
                        citation=(
                            item.get("citation") if isinstance(item.get("citation"), dict) else None
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
                fact_a = UUID(str(item["fact_a_id"]))
                fact_b = UUID(str(item["fact_b_id"]))
                if fact_a > fact_b:
                    fact_a, fact_b = fact_b, fact_a
                contradiction_id = UUID(str(item["id"])) if item.get("id") is not None else uuid4()
                session.add(
                    Contradiction(
                        id=contradiction_id,
                        run_id=analysis_id,
                        corpus_id=corpus_id,
                        fact_a_id=fact_a,
                        fact_b_id=fact_b,
                        contradiction_type=str(item["contradiction_type"]),
                        reason=str(item["reason"]),
                        confidence=float(str(item.get("confidence", 1.0))),
                        status="open",
                    )
                )
            run.status = "completed"
            run.findings_status = "populated" if supported else "no_findings"
            run.completed_at = utcnow()
            run.result_payload = {
                "no_findings": not supported,
                "classifications": classifications,
                "retrieved_block_ids": [],
                "retrieval_mode": "incremental_changed_sources_only",
                "taxonomy_version": TAXONOMY_VERSION,
                "graph_version": GRAPH_VERSION,
                "mode": "incremental",
            }

    async def _persist_examination(
        self,
        *,
        examination_id: UUID,
        corpus_id: UUID,
        analysis_run_id: UUID,
        findings: Sequence[dict[str, object]],
        summary: dict[str, int],
        selected_ids: list[str],
    ) -> None:
        async with self.session_factory() as session, session.begin():
            run = await session.scalar(
                select(ExaminationRun).where(
                    ExaminationRun.id == examination_id,
                    ExaminationRun.corpus_id == corpus_id,
                )
            )
            if run is None:
                raise NotFoundError(
                    "examination_run_not_found",
                    "The incremental examination run was not found.",
                    "Retry the incremental run.",
                )
            for item in findings:
                fact_ids = [UUID(value) for value in _as_str_list(item.get("fact_ids"))]
                contradiction_ids = [
                    UUID(value) for value in _as_str_list(item.get("contradiction_ids"))
                ]
                evidence_kind = str(item.get("evidence_kind", "none"))
                finding = Finding(
                    id=UUID(str(item["id"])),
                    examination_run_id=examination_id,
                    corpus_id=corpus_id,
                    analysis_run_id=analysis_run_id,
                    rule_id=str(item["rule_id"]),
                    rule_version=str(item["rule_version"]),
                    outcome=str(item["outcome"]),
                    severity=str(item["severity"]),
                    title=str(item["title"]),
                    message=str(item["message"]),
                    structured_reason=json_object(item.get("reason")),
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
                                examination_run_id=examination_id,
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
                                examination_run_id=examination_id,
                                corpus_id=corpus_id,
                                analysis_run_id=analysis_run_id,
                                contradiction_id=contradiction_id,
                                evidence_kind="grounded_facts",
                            )
                        )
            run.status = "completed"
            run.findings_status = "populated" if findings else "no_findings"
            run.completed_at = utcnow()
            run.pass_count = summary["pass_count"]
            run.fail_count = summary["fail_count"]
            run.warning_count = summary["warning_count"]
            run.unknown_count = summary["unknown_count"]
            run.evaluated_rule_count = summary["evaluated_rule_count"]
            run.result_payload = {
                "no_findings": not findings,
                "selected_rule_ids": selected_ids,
                "summary": summary,
                "mode": "incremental",
            }

    async def _record_understand_stage(
        self,
        run_id: UUID,
        corpus_id: UUID,
        stage_name: str,
        status: str,
        *,
        skip_reason: str | None = None,
        operation_count: int = 0,
        attempt_count: int = 0,
    ) -> None:
        skipped = status == "skipped"
        async with self.session_factory() as session, session.begin():
            session.add(
                StageEvent(
                    run_id=run_id,
                    corpus_id=corpus_id,
                    stage_name=stage_name,
                    started_at=utcnow(),
                    completed_at=utcnow(),
                    duration_ms=0 if skipped else 1,
                    model_operation_count=0 if skipped else operation_count,
                    model_attempt_count=0 if skipped else attempt_count,
                    estimated_cost_usd=0.0,
                    cost_basis="zero_deterministic",
                    status=status,
                    skip_reason=skip_reason,
                )
            )

    async def _record_examine_stage(
        self,
        run_id: UUID,
        corpus_id: UUID,
        stage_name: str,
        status: str,
        *,
        skip_reason: str | None = None,
        rule_evaluation_count: int = 0,
    ) -> None:
        skipped = status == "skipped"
        async with self.session_factory() as session, session.begin():
            session.add(
                ExaminationStageEvent(
                    examination_run_id=run_id,
                    corpus_id=corpus_id,
                    stage_name=stage_name,
                    started_at=utcnow(),
                    completed_at=utcnow(),
                    duration_ms=0 if skipped else 1,
                    model_operation_count=0,
                    model_attempt_count=0,
                    rule_evaluation_count=0 if skipped else rule_evaluation_count,
                    estimated_cost_usd=0.0,
                    cost_basis="zero_deterministic",
                    status=status,
                    skip_reason=skip_reason,
                )
            )

    async def _stage_counts(
        self, corpus_id: UUID, analysis_run_id: UUID, examination_run_id: UUID
    ) -> dict[str, int]:
        async with self.session_factory() as session:
            understand_events = list(
                await session.scalars(
                    select(StageEvent).where(
                        StageEvent.run_id == analysis_run_id,
                        StageEvent.corpus_id == corpus_id,
                    )
                )
            )
            examine_events = list(
                await session.scalars(
                    select(ExaminationStageEvent).where(
                        ExaminationStageEvent.examination_run_id == examination_run_id,
                        ExaminationStageEvent.corpus_id == corpus_id,
                    )
                )
            )
        return {
            "understand_model_operations": sum(
                event.model_operation_count for event in understand_events
            ),
            "understand_model_attempts": sum(
                event.model_attempt_count for event in understand_events
            ),
            "examine_rule_evaluations": sum(
                event.rule_evaluation_count for event in examine_events
            ),
            "understand_stages_executed": sum(
                1 for event in understand_events if event.status == "completed"
            ),
            "understand_stages_skipped": sum(
                1 for event in understand_events if event.status == "skipped"
            ),
        }


def _fact_impact_ref(fact: Fact) -> FactImpactRef:
    citation = fact.citation if isinstance(fact.citation, dict) else None
    source_version_id = None
    if citation is not None and "source_version_id" in citation:
        source_version_id = UUID(str(citation["source_version_id"]))
    return FactImpactRef(
        id=fact.id,
        category=fact.category,
        subject_key=fact.subject_key,
        support_status=fact.support_status,
        source_version_id=source_version_id,
        source_block_id=fact.source_block_id,
        canonical_hash=_orm_fact_hash(fact),
    )


def _contradiction_impact_ref(
    item: Contradiction, facts: dict[UUID, Fact]
) -> ContradictionImpactRef:
    fact_a = facts[item.fact_a_id]
    fact_b = facts[item.fact_b_id]
    return ContradictionImpactRef(
        id=item.id,
        fact_a_id=item.fact_a_id,
        fact_b_id=item.fact_b_id,
        category=fact_a.category,
        subject_key=fact_a.subject_key,
        canonical_hash=canonical_hash(
            contradiction_canonical_payload(
                contradiction_type=item.contradiction_type,
                reason=item.reason,
                status=item.status,
                fact_a=_orm_fact_payload(fact_a),
                fact_b=_orm_fact_payload(fact_b),
            )
        ),
    )


def _orm_fact_payload(fact: Fact) -> dict[str, object]:
    return fact_canonical_payload(
        category=fact.category,
        subject_key=fact.subject_key,
        normalized_value=fact.normalized_value,
        confidence=fact.confidence,
        support_status=fact.support_status,
        rejection_reason=fact.rejection_reason,
        citation=fact.citation if isinstance(fact.citation, dict) else None,
        source_block_id=fact.source_block_id,
    )


def _orm_fact_hash(fact: Fact) -> str:
    return canonical_hash(_orm_fact_payload(fact))


def _operation_meta(
    *,
    operation_type: str,
    corpus_id: UUID,
    blocks: Sequence[BlockContext],
    source_input_version: str,
    row_id: UUID,
    reused: bool,
    model_provider: str,
    model_name: str,
) -> dict[str, object]:
    return {
        "operation_type": operation_type,
        "source_version_ids": sorted({str(item.source_version_id) for item in blocks}),
        "source_input_version": source_input_version,
        "content_key": make_content_operation_key(
            corpus_id=corpus_id,
            stage="understand",
            operation_type=operation_type,
            source_input_version=source_input_version,
            request_hash=request_hash_for_blocks(blocks),
            model_provider=model_provider,
            model_name=model_name,
            taxonomy_version=TAXONOMY_VERSION,
            understand_graph_version=GRAPH_VERSION,
            prompt_config_version=PROMPT_CONFIG_VERSION,
        ),
        "durable_operation_id": str(row_id),
        "disposition": "reused" if reused else "executed",
        "executed": not reused,
    }


def _revision_source_row(
    revision_id: UUID, corpus_id: UUID, snapshot: SourceSnapshot
) -> CorpusRevisionSource:
    return CorpusRevisionSource(
        revision_id=revision_id,
        corpus_id=corpus_id,
        source_id=snapshot.source_id,
        source_version_id=snapshot.source_version_id,
        sha256=snapshot.sha256,
        logical_name=snapshot.logical_name,
    )


def _finding_canonical(
    finding: Finding,
    facts: dict[UUID, Fact],
    contradictions: dict[UUID, Contradiction],
) -> dict[str, object]:
    fact_hashes = [
        _orm_fact_hash(facts[fact_id]) for fact_id in finding.fact_ids if fact_id in facts
    ]
    contradiction_hashes: list[str] = []
    for contradiction_id in finding.contradiction_ids:
        item = contradictions.get(contradiction_id)
        if item is None or item.fact_a_id not in facts or item.fact_b_id not in facts:
            continue
        contradiction_hashes.append(
            canonical_hash(
                contradiction_canonical_payload(
                    contradiction_type=item.contradiction_type,
                    reason=item.reason,
                    status=item.status,
                    fact_a=_orm_fact_payload(facts[item.fact_a_id]),
                    fact_b=_orm_fact_payload(facts[item.fact_b_id]),
                )
            )
        )
    return finding_canonical_payload(
        rule_id=finding.rule_id,
        rule_version=finding.rule_version,
        outcome=finding.outcome,
        severity=finding.severity,
        title=finding.title,
        message=finding.message,
        structured_reason=dict(finding.structured_reason),
        evidence_kind=finding.evidence_kind,
        confidence=finding.confidence,
        fact_hashes=fact_hashes,
        contradiction_hashes=contradiction_hashes,
    )


def _fact_payload_hash(item: dict[str, object]) -> str:
    citation = item.get("citation")
    return canonical_hash(
        fact_canonical_payload(
            category=str(item["category"]),
            subject_key=str(item["subject_key"]),
            normalized_value=str(item["normalized_value"]),
            confidence=float(str(item["confidence"])),
            support_status=str(item["support_status"]),
            rejection_reason=None,
            citation=citation if isinstance(citation, dict) else None,
            source_block_id=item.get("source_block_id"),  # type: ignore[arg-type]
        )
    )


def _contradiction_payload_hash(
    item: dict[str, object], facts: dict[str, dict[str, object]]
) -> str:
    fact_a = facts[str(item["fact_a_id"])]
    fact_b = facts[str(item["fact_b_id"])]
    return canonical_hash(
        contradiction_canonical_payload(
            contradiction_type=str(item["contradiction_type"]),
            reason=str(item["reason"]),
            status="open",
            fact_a=_dict_fact_payload(fact_a),
            fact_b=_dict_fact_payload(fact_b),
        )
    )


def _dict_fact_payload(item: dict[str, object]) -> dict[str, object]:
    citation = item.get("citation")
    return fact_canonical_payload(
        category=str(item["category"]),
        subject_key=str(item["subject_key"]),
        normalized_value=str(item["normalized_value"]),
        confidence=float(str(item.get("confidence", 0.0))),
        support_status=str(item["support_status"]),
        rejection_reason=None,
        citation=citation if isinstance(citation, dict) else None,
        source_block_id=item.get("source_block_id"),  # type: ignore[arg-type]
    )


def _copy_reused_facts(
    facts: Sequence[Fact], reused_ids: frozenset[UUID]
) -> tuple[list[dict[str, object]], dict[UUID, UUID], dict[str, str]]:
    copied: list[dict[str, object]] = []
    id_map: dict[UUID, UUID] = {}
    hashes: dict[str, str] = {}
    for fact in facts:
        if fact.id not in reused_ids:
            continue
        new_id = uuid4()
        id_map[fact.id] = new_id
        payload = {
            "id": str(new_id),
            "category": fact.category,
            "subject_key": fact.subject_key,
            "normalized_value": fact.normalized_value,
            "confidence": fact.confidence,
            "support_status": fact.support_status,
            "citation": fact.citation,
            "source_block_id": str(fact.source_block_id) if fact.source_block_id else None,
            "baseline_fact_id": str(fact.id),
        }
        copied.append(payload)
        hashes[str(new_id)] = _orm_fact_hash(fact)
    return copied, id_map, hashes


def _copy_reused_contradictions(
    contradictions: Sequence[Contradiction],
    facts: Sequence[Fact],
    fact_id_map: dict[UUID, UUID],
    reused_ids: frozenset[UUID],
) -> tuple[list[dict[str, object]], dict[UUID, UUID], dict[str, str]]:
    facts_by_id = {fact.id: fact for fact in facts}
    copied: list[dict[str, object]] = []
    id_map: dict[UUID, UUID] = {}
    hashes: dict[str, str] = {}
    for item in contradictions:
        if item.id not in reused_ids:
            continue
        if item.fact_a_id not in fact_id_map or item.fact_b_id not in fact_id_map:
            continue
        new_id = uuid4()
        id_map[item.id] = new_id
        payload = {
            "id": str(new_id),
            "fact_a_id": str(fact_id_map[item.fact_a_id]),
            "fact_b_id": str(fact_id_map[item.fact_b_id]),
            "contradiction_type": item.contradiction_type,
            "reason": item.reason,
            "confidence": item.confidence,
            "baseline_contradiction_id": str(item.id),
        }
        copied.append(payload)
        hashes[str(new_id)] = _contradiction_impact_ref(item, facts_by_id).canonical_hash
    return copied, id_map, hashes


def _remap_finding(
    finding: Finding,
    fact_id_map: dict[UUID, UUID],
    contradiction_id_map: dict[UUID, UUID],
) -> dict[str, object]:
    fact_ids = [str(fact_id_map[item]) for item in finding.fact_ids if item in fact_id_map]
    contradiction_ids = [
        str(contradiction_id_map[item])
        for item in finding.contradiction_ids
        if item in contradiction_id_map
    ]
    return {
        "id": str(uuid4()),
        "rule_id": finding.rule_id,
        "rule_version": finding.rule_version,
        "outcome": finding.outcome,
        "severity": finding.severity,
        "title": finding.title,
        "message": finding.message,
        "reason": dict(finding.structured_reason),
        "fact_ids": fact_ids,
        "contradiction_ids": contradiction_ids,
        "confidence": finding.confidence,
        "evidence_kind": finding.evidence_kind,
        "citations": [],
        "baseline_finding_id": str(finding.id),
        "disposition": "reused",
    }


def _evaluation_finding_payload(evaluation: Any) -> dict[str, object]:
    return {
        "id": str(uuid4()),
        "rule_id": evaluation.rule_id,
        "rule_version": evaluation.rule_version,
        "outcome": evaluation.outcome,
        "severity": evaluation.severity,
        "title": evaluation.title,
        "message": evaluation.message,
        "reason": dict(evaluation.reason),
        "fact_ids": list(evaluation.fact_ids),
        "contradiction_ids": list(evaluation.contradiction_ids),
        "confidence": evaluation.confidence,
        "evidence_kind": evaluation.evidence_kind,
        "citations": list(evaluation.citations),
        "disposition": "recomputed",
    }


def _summarize_findings(findings: Sequence[dict[str, object]]) -> dict[str, int]:
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
    }


def _understanding_view(
    facts: Sequence[Fact],
    contradictions: Sequence[Contradiction],
    *,
    attested: bool,
) -> UnderstandingView:
    from app.ruleset import GroundedContradictionView, GroundedFactView

    return UnderstandingView(
        facts=tuple(
            GroundedFactView(
                id=str(fact.id),
                category=fact.category,
                subject_key=fact.subject_key,
                normalized_value=fact.normalized_value,
                support_status=fact.support_status,
                citation=dict(fact.citation) if isinstance(fact.citation, dict) else None,
                source_block_id=str(fact.source_block_id) if fact.source_block_id else None,
            )
            for fact in facts
        ),
        contradictions=tuple(
            GroundedContradictionView(
                id=str(item.id),
                contradiction_type=item.contradiction_type,
                fact_a_id=str(item.fact_a_id),
                fact_b_id=str(item.fact_b_id),
                reason=item.reason,
                status=item.status,
            )
            for item in contradictions
        ),
        contradiction_detection_attested=attested,
    )


def _review_item_canonical(
    item: ReviewItem,
    finding: Finding,
    facts: dict[UUID, Fact],
    contradictions: dict[UUID, Contradiction],
) -> dict[str, object]:
    citations: list[dict[str, Any] | None] = []
    for fact_id in finding.fact_ids:
        fact = facts.get(fact_id)
        if fact is not None and isinstance(fact.citation, dict):
            citations.append(fact.citation)
    proposed = item.proposed_content
    if isinstance(proposed, dict):
        extra = proposed.get("citations")
        if isinstance(extra, list):
            for citation in extra:
                if isinstance(citation, dict):
                    citations.append(citation)
    fact_hashes = [
        _orm_fact_hash(facts[fact_id]) for fact_id in finding.fact_ids if fact_id in facts
    ]
    contradiction_hashes: list[str] = []
    for contradiction_id in finding.contradiction_ids:
        contradiction = contradictions.get(contradiction_id)
        if (
            contradiction is None
            or contradiction.fact_a_id not in facts
            or contradiction.fact_b_id not in facts
        ):
            continue
        contradiction_hashes.append(
            canonical_hash(
                contradiction_canonical_payload(
                    contradiction_type=contradiction.contradiction_type,
                    reason=contradiction.reason,
                    status=contradiction.status,
                    fact_a=_orm_fact_payload(facts[contradiction.fact_a_id]),
                    fact_b=_orm_fact_payload(facts[contradiction.fact_b_id]),
                )
            )
        )
    return review_item_canonical_payload(
        rule_id=item.rule_id,
        rule_version=finding.rule_version,
        outcome=item.outcome,
        severity=item.severity,
        title=item.title,
        message=finding.message,
        structured_reason=dict(finding.structured_reason),
        evidence_kind=finding.evidence_kind,
        fact_hashes=fact_hashes,
        contradiction_hashes=contradiction_hashes,
        citations=citations,
        review_required=item.review_required,
    )


def _impact_payload(changes: ChangeSet, impact: ImpactSet | None) -> dict[str, object]:
    payload: dict[str, object] = {
        "change_kind": changes.change_kind,
        "unchanged_source_version_ids": [str(item.source_version_id) for item in changes.unchanged],
        "changed_source_ids": [str(item) for item in sorted(changes.changed_source_ids, key=str)],
        "changed_source_version_ids": [
            str(item) for item in sorted(changes.changed_source_version_ids, key=str)
        ],
        "added_source_ids": [str(item.source_id) for item in changes.added],
        "removed_source_ids": [str(item.source_id) for item in changes.removed],
    }
    if impact is not None:
        payload.update(
            {
                "affected_fact_ids": [
                    str(item) for item in sorted(impact.affected_fact_ids, key=str)
                ],
                "reused_fact_ids": [str(item) for item in sorted(impact.reused_fact_ids, key=str)],
                "affected_contradiction_ids": [
                    str(item) for item in sorted(impact.affected_contradiction_ids, key=str)
                ],
                "reused_contradiction_ids": [
                    str(item) for item in sorted(impact.reused_contradiction_ids, key=str)
                ],
                "affected_rule_ids": sorted(impact.affected_rule_ids),
                "reused_rule_ids": sorted(impact.reused_rule_ids),
                "affected_block_ids": [
                    str(item) for item in sorted(impact.affected_block_ids, key=str)
                ],
                "global_rule_reasons": impact.global_rule_reasons,
            }
        )
    return payload


def _compose_evidence(
    *,
    changes: ChangeSet,
    impact: ImpactSet,
    analysis: dict[str, Any],
    rule_evidence: dict[str, object],
    review_evidence: dict[str, object],
) -> tuple[dict[str, object], list[IncrementalArtifactEvidence]]:
    persisted_facts = analysis.get("canonical_unchanged_facts")
    unchanged_pairs: list[dict[str, object]] = (
        list(persisted_facts) if isinstance(persisted_facts, list) else []
    )
    stages_executed = ["detect_changes", "plan_impact"]
    stages_skipped = ["retrieve_context"]
    if analysis.get("classify_executed"):
        stages_executed.append("classify")
    else:
        stages_skipped.append("classify")
    if analysis.get("extract_executed"):
        stages_executed.append("extract_facts")
    else:
        stages_skipped.append("extract_facts")
    if analysis.get("validate_provenance_executed"):
        stages_executed.append("validate_provenance")
    if analysis.get("detect_contradictions_executed"):
        stages_executed.append("detect_contradictions")
    if rule_evidence.get("evaluate_rules_executed"):
        stages_executed.append("evaluate_rules")
    else:
        stages_skipped.append("evaluate_rules")
    if rule_evidence.get("validate_evidence_executed"):
        stages_executed.append("validate_evidence")
    stages_executed.append("open_review")
    evidence = {
        "changed_source_ids": [str(item) for item in sorted(changes.changed_source_ids, key=str)],
        "changed_source_version_ids": [
            str(item) for item in sorted(changes.changed_source_version_ids, key=str)
        ],
        "affected_block_ids": [str(item) for item in sorted(impact.affected_block_ids, key=str)],
        "reused_fact_ids": analysis["reused_fact_ids"],
        "recomputed_fact_ids": analysis["recomputed_fact_ids"],
        "reused_contradiction_ids": analysis["reused_contradiction_ids"],
        "recomputed_contradiction_ids": analysis["recomputed_contradiction_ids"],
        "rules_evaluated": rule_evidence["evaluated_rule_ids"],
        "rules_reused": rule_evidence["reused_rule_ids"],
        "executed_operation_keys": analysis["executed_operation_keys"],
        "reused_operation_keys": analysis["reused_operation_keys"],
        "skipped_operation_keys": analysis.get("skipped_operation_keys", []),
        "classify_executed_source_version_ids": analysis["classify_executed_source_version_ids"],
        "classify_skipped_source_version_ids": analysis["classify_skipped_source_version_ids"],
        "extract_executed_source_version_ids": analysis["extract_executed_source_version_ids"],
        "extract_skipped_source_version_ids": analysis.get(
            "extract_skipped_source_version_ids", []
        ),
        "canonical_unchanged_facts": unchanged_pairs,
        "canonical_unchanged_contradictions": analysis.get(
            "canonical_unchanged_contradictions", []
        ),
        "canonical_unchanged_findings": analysis.get("canonical_unchanged_findings", []),
        "canonical_unchanged_review_items": review_evidence.get(
            "canonical_unchanged_review_items", []
        ),
        "review": review_evidence,
        "global_rule_reasons": rule_evidence["global_rule_reasons"],
        "stages_executed": stages_executed,
        "stages_skipped": stages_skipped,
        "full_rerun": False,
    }
    artifacts: list[IncrementalArtifactEvidence] = []
    after_hashes = analysis["fact_hashes"]
    for pair in unchanged_pairs:
        artifacts.append(
            IncrementalArtifactEvidence(
                artifact_kind="fact",
                artifact_id=str(pair["incremental_fact_id"]),
                disposition="reused",
                canonical_hash_before=str(pair["canonical_hash_before"]),
                canonical_hash_after=str(pair["canonical_hash_after"]),
                payload={"baseline_fact_id": pair["baseline_fact_id"]},
            )
        )
    for fact_id in analysis["recomputed_fact_ids"]:
        artifacts.append(
            IncrementalArtifactEvidence(
                artifact_kind="fact",
                artifact_id=str(fact_id),
                disposition="recomputed",
                canonical_hash_after=after_hashes.get(str(fact_id)),
                payload={},
            )
        )
    for key in analysis["executed_operation_keys"]:
        artifacts.append(
            IncrementalArtifactEvidence(
                artifact_kind="operation",
                artifact_id=str(key.get("durable_operation_id") or key.get("content_key")),
                disposition=str(key.get("disposition", "executed")),
                durable_operation_id=(
                    UUID(str(key["durable_operation_id"]))
                    if key.get("durable_operation_id")
                    else None
                ),
                payload=key,
            )
        )
    for key in analysis["reused_operation_keys"]:
        artifacts.append(
            IncrementalArtifactEvidence(
                artifact_kind="operation",
                artifact_id=str(key.get("durable_operation_id") or key["content_key"]),
                disposition="reused",
                durable_operation_id=(
                    UUID(str(key["durable_operation_id"]))
                    if key.get("durable_operation_id")
                    else None
                ),
                canonical_hash_before=(
                    str(key["content_key_before"])
                    if key.get("content_key_before") is not None
                    else None
                ),
                canonical_hash_after=str(key["content_key"]),
                payload=key,
            )
        )
    for key in analysis.get("skipped_operation_keys", []):
        artifacts.append(
            IncrementalArtifactEvidence(
                artifact_kind="operation",
                artifact_id=str(key["content_key"]),
                disposition="skipped",
                payload=key,
            )
        )
    for pair in json_object_list(analysis.get("canonical_unchanged_contradictions")):
        artifacts.append(
            IncrementalArtifactEvidence(
                artifact_kind="contradiction",
                artifact_id=str(pair["incremental_contradiction_id"]),
                disposition="reused",
                canonical_hash_before=str(pair["canonical_hash_before"]),
                canonical_hash_after=str(pair["canonical_hash_after"]),
                payload={"baseline_contradiction_id": pair["baseline_contradiction_id"]},
            )
        )
    for pair in json_object_list(analysis.get("canonical_unchanged_findings")):
        artifacts.append(
            IncrementalArtifactEvidence(
                artifact_kind="finding",
                artifact_id=str(pair["rule_id"]),
                disposition="reused",
                canonical_hash_before=str(pair["canonical_hash_before"]),
                canonical_hash_after=str(pair["canonical_hash_after"]),
                payload={"rule_id": pair["rule_id"]},
            )
        )
    for item in json_object_list(review_evidence.get("items")):
        disposition = str(item.get("disposition"))
        if disposition == "reused":
            artifacts.append(
                IncrementalArtifactEvidence(
                    artifact_kind="review_item",
                    artifact_id=str(item["item_id"]),
                    disposition="reused",
                    canonical_hash_before=str(item.get("canonical_hash_before"))
                    if item.get("canonical_hash_before") is not None
                    else None,
                    canonical_hash_after=str(item.get("canonical_hash_after"))
                    if item.get("canonical_hash_after") is not None
                    else None,
                    payload={
                        "rule_id": item["rule_id"],
                        "canonical_bytes_equal": item.get("canonical_bytes_equal"),
                        "baseline_review_item_id": item.get("baseline_review_item_id"),
                    },
                )
            )
        elif disposition == "changed":
            artifacts.append(
                IncrementalArtifactEvidence(
                    artifact_kind="review_item",
                    artifact_id=str(item["item_id"]),
                    disposition="recomputed",
                    canonical_hash_before=str(item.get("canonical_hash_before"))
                    if item.get("canonical_hash_before") is not None
                    else None,
                    canonical_hash_after=str(item.get("canonical_hash_after"))
                    if item.get("canonical_hash_after") is not None
                    else None,
                    payload={
                        "rule_id": item["rule_id"],
                        "canonical_bytes_equal": item.get("canonical_bytes_equal"),
                    },
                )
            )
    for rule_id in _as_str_list(rule_evidence.get("evaluated_rule_ids")):
        artifacts.append(
            IncrementalArtifactEvidence(
                artifact_kind="rule",
                artifact_id=rule_id,
                disposition="recomputed",
                payload={},
            )
        )
    for rule_id in _as_str_list(rule_evidence.get("reused_rule_ids")):
        artifacts.append(
            IncrementalArtifactEvidence(
                artifact_kind="rule",
                artifact_id=rule_id,
                disposition="reused",
                payload={},
            )
        )
    return evidence, artifacts


def _measurement(
    *,
    baseline_analysis_id: UUID,
    baseline_examination_id: UUID,
    incremental_analysis: AnalysisRun,
    incremental_examination: ExaminationRun,
    changes: ChangeSet,
    impact: ImpactSet,
    duration_ms: int,
    baseline_stage_counts: dict[str, int],
    incremental_stage_counts: dict[str, int],
) -> dict[str, object]:
    del baseline_analysis_id, baseline_examination_id, incremental_analysis
    return {
        "changed_source_count": len(changes.changed) + len(changes.added) + len(changes.removed),
        "reused_fact_count": len(impact.reused_fact_ids),
        "affected_fact_count": len(impact.affected_fact_ids),
        "reused_contradiction_count": len(impact.reused_contradiction_ids),
        "affected_contradiction_count": len(impact.affected_contradiction_ids),
        "rules_evaluated": len(impact.affected_rule_ids),
        "rules_reused": len(impact.reused_rule_ids),
        "baseline_understand_model_operations": baseline_stage_counts[
            "understand_model_operations"
        ],
        "incremental_understand_model_operations": incremental_stage_counts[
            "understand_model_operations"
        ],
        "baseline_rule_evaluations": baseline_stage_counts["examine_rule_evaluations"],
        "incremental_rule_evaluations": incremental_stage_counts["examine_rule_evaluations"],
        "incremental_examination_evaluated_rule_count": (
            incremental_examination.evaluated_rule_count
        ),
        "avoided_model_operations": len(changes.unchanged),
        "estimated_cost_usd": 0.0,
        "cost_basis": "zero_deterministic",
        "duration_ms": duration_ms,
    }


def _artifact_payload(row: IncrementalArtifactEvidence) -> dict[str, object]:
    return {
        "artifact_kind": row.artifact_kind,
        "artifact_id": row.artifact_id,
        "disposition": row.disposition,
        "canonical_hash_before": row.canonical_hash_before,
        "canonical_hash_after": row.canonical_hash_after,
        "durable_operation_id": str(row.durable_operation_id)
        if row.durable_operation_id is not None
        else None,
        "payload": dict(row.payload),
    }


def _as_str_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def json_object(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return {str(key): item for key, item in value.items()}
    return {}


def json_object_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [json_object(item) for item in value]
