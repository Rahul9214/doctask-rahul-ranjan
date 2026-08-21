from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from helpers import (
    CountingModelAdapter,
    fixture_upload,
    prepare_incremental_corpus,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.canonical import canonical_bytes, canonical_hash, contradiction_canonical_payload
from app.errors import NotFoundError
from app.incremental_service import (
    IncrementalFinalizeInjectedError,
    _finding_canonical,
    _orm_fact_payload,
    _review_item_canonical,
)
from app.models import (
    Contradiction,
    CorpusRevision,
    CorpusRevisionSource,
    DurableOperation,
    Fact,
    ReviewItem,
    SourceVersion,
)
from app.ruleset import OPEN_CONTRADICTION_RULE_ID
from app.services import Phase02Service
from app.storage import LocalFileStorage


def _json_object(value: object) -> dict[str, Any]:
    assert isinstance(value, dict)
    return value


def _require_uuid(value: UUID | None) -> UUID:
    assert value is not None
    return value


def _changed_copy(src: Path, dest: Path, old: str, new: str) -> Path:
    dest.write_text(src.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")
    return dest


def _contradiction_canonical(item: Contradiction, facts: dict[UUID, Fact]) -> dict[str, object]:
    return contradiction_canonical_payload(
        contradiction_type=item.contradiction_type,
        reason=item.reason,
        status=item.status,
        fact_a=_orm_fact_payload(facts[item.fact_a_id]),
        fact_b=_orm_fact_payload(facts[item.fact_b_id]),
    )


def _ops_for_type(rows: list[dict[str, Any]], operation_type: str) -> list[dict[str, Any]]:
    return [item for item in rows if item.get("operation_type") == operation_type]


def _subject_contradictions(
    contradictions: list[Contradiction],
    facts: dict[UUID, Fact],
    subject_key: str,
) -> list[Contradiction]:
    return [
        item
        for item in contradictions
        if facts[item.fact_a_id].subject_key == subject_key
        or facts[item.fact_b_id].subject_key == subject_key
    ]


@pytest.mark.integration
async def test_aurora_one_source_incremental_reuses_unaffected_work(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
    tmp_path: Path,
) -> None:
    phase02, _storage = phase02_service
    adapter = CountingModelAdapter()
    corpus, incremental = await prepare_incremental_corpus(
        phase02,
        corpus_fixtures / "aurora-control-hub",
        adapter,
    )
    baseline = await incremental.get_current_revision(corpus.id)
    baseline_ops = adapter.classify_operations
    baseline_extract = adapter.extract_operations
    versions_before = {
        item["logical_name"]: item["source_version_id"] for item in baseline.source_version_set
    }
    original = corpus_fixtures / "aurora-control-hub" / "decision-log.txt"
    changed = _changed_copy(original, tmp_path / "decision-log.txt", "2026-10-30", "2026-12-01")
    ingested = await phase02.ingest(
        corpus_id=corpus.id,
        logical_name="Decision Log",
        declared_format="txt",
        upload=fixture_upload(changed, "txt"),
    )
    assert ingested.duplicate is False
    unchanged_ingest = await phase02.ingest(
        corpus_id=corpus.id,
        logical_name="Decision Log",
        declared_format="txt",
        upload=fixture_upload(changed, "txt"),
    )
    assert unchanged_ingest.duplicate is True
    assert unchanged_ingest.version.id == ingested.version.id

    run = await incremental.create_run(corpus.id, baseline_revision_id=baseline.id)
    assert run.status == "completed"
    evidence = await incremental.get_evidence(corpus.id, run.id)
    payload = _json_object(evidence["evidence"])
    current = await incremental.get_current_revision(corpus.id)
    versions_after = {
        item["logical_name"]: item["source_version_id"] for item in current.source_version_set
    }

    assert versions_after["Decision Log"] != versions_before["Decision Log"]
    assert versions_after["Decision Log"] == str(ingested.version.id)
    for name in ("Project Charter", "Weekly Status Report", "Risk Register"):
        assert versions_after[name] == versions_before[name]

    assert payload["full_rerun"] is False
    assert "classify" in payload["stages_executed"]
    assert "extract_facts" in payload["stages_executed"]
    assert "validate_evidence" in payload["stages_executed"]
    assert "retrieve_context" in payload["stages_skipped"]
    assert str(ingested.version.id) in payload["classify_executed_source_version_ids"]
    assert str(ingested.version.id) in payload["extract_executed_source_version_ids"]
    assert versions_before["Project Charter"] in payload["classify_skipped_source_version_ids"]
    assert versions_before["Project Charter"] in payload["extract_skipped_source_version_ids"]
    assert versions_before["Decision Log"] not in payload["classify_executed_source_version_ids"]
    assert versions_before["Decision Log"] not in payload["extract_executed_source_version_ids"]
    assert adapter.classify_operations == baseline_ops + 1
    assert adapter.extract_operations == baseline_extract + 1
    assert len(payload["classify_executed_source_version_ids"]) == 1
    assert len(payload["extract_executed_source_version_ids"]) == 1
    assert len(payload["classify_skipped_source_version_ids"]) >= 3
    assert (
        payload["classify_skipped_source_version_ids"]
        == payload["extract_skipped_source_version_ids"]
    )
    assert run.measurement["avoided_model_operations"] >= 3
    assert run.measurement["estimated_cost_usd"] == 0.0
    assert payload["reused_fact_ids"]
    assert payload["recomputed_fact_ids"]
    for pair in payload["canonical_unchanged_facts"]:
        assert pair["canonical_hash_before"] == pair["canonical_hash_after"]
        assert pair["canonical_bytes_equal"] is True
        assert len(pair["canonical_hash_before"]) == 64
    skipped_ops = payload["skipped_operation_keys"]
    assert skipped_ops
    skipped_classify = _ops_for_type(skipped_ops, "classify")
    skipped_extract = _ops_for_type(skipped_ops, "extract")
    assert skipped_classify
    assert skipped_extract
    assert {item["source_version_id"] for item in skipped_classify} == set(
        payload["classify_skipped_source_version_ids"]
    )
    assert {item["source_version_id"] for item in skipped_extract} == set(
        payload["extract_skipped_source_version_ids"]
    )
    for item in skipped_ops:
        assert item["executed"] is False
        assert item["disposition"] == "skipped"
        assert item["durable_operation_id"] is None
        assert item["operation_type"] in {"classify", "extract"}
    reused_ops = payload["reused_operation_keys"]
    for item in reused_ops:
        assert item["executed"] is False
        assert item["durable_operation_id"]
        assert item["disposition"] == "reused"
    executed_ops = payload["executed_operation_keys"]
    assert executed_ops
    assert {item["operation_type"] for item in executed_ops} == {"classify", "extract"}
    assert all(item["executed"] is True for item in executed_ops)
    assert all(item.get("durable_operation_id") for item in executed_ops)
    assert all(str(ingested.version.id) in item["source_version_ids"] for item in executed_ops)
    assert "spa.ownership.sponsor" in payload["rules_reused"]
    assert "spa.milestone.production-readiness" in payload["rules_evaluated"]

    async with incremental.session_factory() as session:
        retired = await session.scalar(
            select(SourceVersion).where(
                SourceVersion.id == UUID(str(versions_before["Decision Log"])),
                SourceVersion.corpus_id == corpus.id,
            )
        )
        assert retired is not None
        membership = list(
            await session.scalars(
                select(CorpusRevisionSource).where(
                    CorpusRevisionSource.revision_id == current.id,
                    CorpusRevisionSource.corpus_id == corpus.id,
                )
            )
        )
        assert {row.logical_name for row in membership} == set(versions_after)
        for member in membership:
            version = await session.scalar(
                select(SourceVersion).where(
                    SourceVersion.id == member.source_version_id,
                    SourceVersion.corpus_id == corpus.id,
                )
            )
            assert version is not None
            assert version.source_id == member.source_id
            assert version.sha256 == member.sha256
        ledger_rows = list(
            await session.scalars(
                select(DurableOperation).where(
                    DurableOperation.corpus_id == corpus.id,
                    DurableOperation.incremental_run_id == run.id,
                    DurableOperation.status == "completed",
                )
            )
        )
    assert ledger_rows
    executed_types = {operation.operation_type for operation in ledger_rows}
    assert executed_types == {"classify", "extract"}
    assert len(ledger_rows) == 2
    skipped_keys = {str(item["content_key"]) for item in skipped_ops}
    ledger_keys = {operation.operation_key for operation in ledger_rows}
    assert skipped_keys.isdisjoint(ledger_keys)
    skipped_version_ids = {str(item["source_version_id"]) for item in skipped_ops}
    executed_version_ids = {
        str(version_id) for item in executed_ops for version_id in item["source_version_ids"]
    }
    assert executed_version_ids.isdisjoint(skipped_version_ids)
    for operation in ledger_rows:
        assert operation.workflow_run_id is None
        assert operation.incremental_run_id == run.id

    baseline_facts = await incremental.understand.list_facts(corpus.id, baseline.analysis_run_id)
    new_facts = await incremental.understand.list_facts(
        corpus.id, _require_uuid(run.analysis_run_id)
    )
    baseline_contradictions = await incremental.understand.list_contradictions(
        corpus.id, baseline.analysis_run_id
    )
    new_contradictions = await incremental.understand.list_contradictions(
        corpus.id, _require_uuid(run.analysis_run_id)
    )
    facts_before = {fact.id: fact for fact in baseline_facts}
    facts_after = {fact.id: fact for fact in new_facts}
    new_by_hash = {canonical_hash(_orm_fact_payload(fact)): fact for fact in new_facts}
    reused_baseline = [
        fact
        for fact in baseline_facts
        if fact.support_status == "supported"
        and fact.citation
        and str(fact.citation.get("source_version_id")) != versions_before["Decision Log"]
    ]
    assert reused_baseline
    for fact in reused_baseline:
        before_bytes = canonical_bytes(_orm_fact_payload(fact))
        after = new_by_hash[canonical_hash(_orm_fact_payload(fact))]
        assert canonical_bytes(_orm_fact_payload(after)) == before_bytes

    supported = [fact for fact in new_facts if fact.support_status == "supported"]
    production = [fact for fact in supported if fact.subject_key == "production_readiness"]
    assert any(
        fact.normalized_value == "2026-12-01"
        and fact.citation is not None
        and str(fact.citation.get("source_version_id")) == str(ingested.version.id)
        for fact in production
    )
    assert any(fact.normalized_value == "2026-11-14" for fact in production)
    assert any(
        fact.normalized_value == "2026-10-30"
        and fact.citation is not None
        and str(fact.citation.get("source_version_id")) != versions_before["Decision Log"]
        for fact in production
    )
    assert not any(
        fact.citation is not None
        and str(fact.citation.get("source_version_id")) == versions_before["Decision Log"]
        for fact in production
    )

    baseline_prod_conflicts = _subject_contradictions(
        baseline_contradictions, facts_before, "production_readiness"
    )
    incremental_prod_conflicts = _subject_contradictions(
        new_contradictions, facts_after, "production_readiness"
    )
    assert baseline_prod_conflicts
    baseline_conflict_values = [
        {
            facts_before[item.fact_a_id].normalized_value,
            facts_before[item.fact_b_id].normalized_value,
        }
        for item in baseline_prod_conflicts
    ]
    assert {"2026-10-30", "2026-11-14"} in baseline_conflict_values
    assert {item.id for item in baseline_prod_conflicts}.isdisjoint(
        {item.id for item in incremental_prod_conflicts}
    )
    incremental_conflict_values = [
        {
            facts_after[item.fact_a_id].normalized_value,
            facts_after[item.fact_b_id].normalized_value,
        }
        for item in incremental_prod_conflicts
    ]
    assert {"2026-12-01", "2026-11-14"} in incremental_conflict_values
    assert incremental_conflict_values.count({"2026-12-01", "2026-11-14"}) == 1
    for item in incremental_prod_conflicts:
        citation_a = facts_after[item.fact_a_id].citation
        citation_b = facts_after[item.fact_b_id].citation
        assert isinstance(citation_a, dict)
        assert isinstance(citation_b, dict)
        versions = {
            str(citation_a["source_version_id"]),
            str(citation_b["source_version_id"]),
        }
        assert versions_before["Decision Log"] not in versions
        if "2026-12-01" in {
            facts_after[item.fact_a_id].normalized_value,
            facts_after[item.fact_b_id].normalized_value,
        }:
            assert str(ingested.version.id) in versions
    assert incremental_prod_conflicts
    assert all(
        item.contradiction_type == "conflicting_dates" for item in incremental_prod_conflicts
    )
    baseline_findings = await incremental.examine.list_findings(
        corpus.id, baseline.examination_run_id
    )
    new_findings = await incremental.examine.list_findings(
        corpus.id, _require_uuid(run.examination_run_id)
    )
    baseline_readiness = next(
        item for item in baseline_findings if item.rule_id == "spa.milestone.production-readiness"
    )
    incremental_readiness = next(
        item for item in new_findings if item.rule_id == "spa.milestone.production-readiness"
    )
    assert baseline_readiness.outcome == "fail"
    assert incremental_readiness.outcome == "fail"
    assert incremental_readiness.id != baseline_readiness.id

    previous_session = await incremental.review.get_session(
        corpus.id, _require_uuid(baseline.review_session_id)
    )
    assert previous_session.status == "completed"
    new_items = await incremental.review.list_items(corpus.id, _require_uuid(run.review_session_id))
    assert all(item.review_status == "pending" for item in new_items)
    review = _json_object(payload["review"])
    assert review["implicit_approval"] is False
    assert review["previous_review_session_id"] == str(baseline.review_session_id)
    assert review["new_review_session_id"] != review["previous_review_session_id"]
    assert review["new_decision_count"] == 0
    review_items = cast(list[dict[str, Any]], review["items"])
    changed_items = [item for item in review_items if item["disposition"] == "changed"]
    assert changed_items
    assert all(item["require_fresh_review"] for item in changed_items)
    assert all(item.get("canonical_bytes_equal") is False for item in changed_items)
    reused_items = [item for item in review_items if item["disposition"] == "reused"]
    assert reused_items
    assert all(item["canonical_bytes_equal"] is True for item in reused_items)
    assert all(
        item["canonical_hash_before"] == item["canonical_hash_after"] for item in reused_items
    )
    baseline_review_items: dict[str, ReviewItem]
    incremental_review_items: dict[str, ReviewItem]
    async with incremental.session_factory() as session:
        baseline_review_items = {
            item.rule_id: item
            for item in await session.scalars(
                select(ReviewItem).where(
                    ReviewItem.review_session_id == _require_uuid(baseline.review_session_id),
                    ReviewItem.corpus_id == corpus.id,
                )
            )
        }
        incremental_review_items = {
            item.rule_id: item
            for item in await session.scalars(
                select(ReviewItem).where(
                    ReviewItem.review_session_id == _require_uuid(run.review_session_id),
                    ReviewItem.corpus_id == corpus.id,
                )
            )
        }
    baseline_review_findings = {item.id: item for item in baseline_findings}
    new_review_findings = {item.id: item for item in new_findings}
    for evidence_item in reused_items:
        rule_id = str(evidence_item["rule_id"])
        before_item = baseline_review_items[rule_id]
        after_item = incremental_review_items[rule_id]
        before_bytes = canonical_bytes(
            _review_item_canonical(
                before_item,
                baseline_review_findings[before_item.finding_id],
                facts_before,
                {item.id: item for item in baseline_contradictions},
            )
        )
        after_bytes = canonical_bytes(
            _review_item_canonical(
                after_item,
                new_review_findings[after_item.finding_id],
                facts_after,
                {item.id: item for item in new_contradictions},
            )
        )
        assert after_bytes == before_bytes
    assert all(item.review_status == "pending" for item in new_items)


@pytest.mark.integration
async def test_harbor_incremental_uses_same_engine_and_stays_isolated(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
    tmp_path: Path,
) -> None:
    phase02, _storage = phase02_service
    aurora, aurora_inc = await prepare_incremental_corpus(
        phase02, corpus_fixtures / "aurora-control-hub"
    )
    harbor_adapter = CountingModelAdapter()
    harbor, harbor_inc = await prepare_incremental_corpus(
        phase02, corpus_fixtures / "harbor-ledger-modernization", harbor_adapter
    )
    harbor_baseline = await harbor_inc.get_current_revision(harbor.id)
    baseline_classify = harbor_adapter.classify_operations
    baseline_extract = harbor_adapter.extract_operations
    versions_before = {
        item["logical_name"]: item["source_version_id"]
        for item in harbor_baseline.source_version_set
    }
    old_governance_version = UUID(str(versions_before["Governance Notes"]))
    changed = _changed_copy(
        corpus_fixtures / "harbor-ledger-modernization" / "governance-notes.txt",
        tmp_path / "governance-notes.txt",
        "2026-12-04",
        "2026-12-18",
    )
    ingested = await phase02.ingest(
        corpus_id=harbor.id,
        logical_name="Governance Notes",
        declared_format="txt",
        upload=fixture_upload(changed, "txt"),
    )
    run = await harbor_inc.create_run(harbor.id, baseline_revision_id=harbor_baseline.id)
    assert run.status == "completed"
    evidence = await harbor_inc.get_evidence(harbor.id, run.id)
    harbor_payload = _json_object(evidence["evidence"])
    current = await harbor_inc.get_current_revision(harbor.id)
    versions_after = {
        item["logical_name"]: item["source_version_id"] for item in current.source_version_set
    }
    assert versions_after["Governance Notes"] == str(ingested.version.id)
    assert versions_after["Governance Notes"] != versions_before["Governance Notes"]
    for name, version_id in versions_before.items():
        if name == "Governance Notes":
            continue
        assert versions_after[name] == version_id
    assert harbor_payload["full_rerun"] is False
    assert "classify" in harbor_payload["stages_executed"]
    assert "extract_facts" in harbor_payload["stages_executed"]
    assert str(ingested.version.id) in harbor_payload["classify_executed_source_version_ids"]
    assert str(ingested.version.id) in harbor_payload["extract_executed_source_version_ids"]
    unchanged_names = [name for name in versions_before if name != "Governance Notes"]
    assert unchanged_names
    for name in unchanged_names:
        assert versions_before[name] in harbor_payload["classify_skipped_source_version_ids"]
        assert versions_before[name] in harbor_payload["extract_skipped_source_version_ids"]
    skipped_ops = harbor_payload["skipped_operation_keys"]
    assert _ops_for_type(skipped_ops, "classify")
    assert _ops_for_type(skipped_ops, "extract")
    for item in skipped_ops:
        assert item["executed"] is False
        assert item["disposition"] == "skipped"
        assert item["durable_operation_id"] is None
    executed_ops = harbor_payload["executed_operation_keys"]
    assert {item["operation_type"] for item in executed_ops} == {"classify", "extract"}
    assert all(item["executed"] is True for item in executed_ops)
    assert harbor_adapter.classify_operations == baseline_classify + 1
    assert harbor_adapter.extract_operations == baseline_extract + 1
    assert OPEN_CONTRADICTION_RULE_ID in harbor_payload["rules_evaluated"]
    assert harbor_payload["rules_reused"]
    assert "spa.milestone.production-readiness" not in harbor_payload.get("rules_evaluated", [])
    assert "spa.milestone.production-readiness" in harbor_payload["rules_reused"]

    async with harbor_inc.session_factory() as session:
        retired = await session.scalar(
            select(SourceVersion).where(
                SourceVersion.id == old_governance_version,
                SourceVersion.corpus_id == harbor.id,
            )
        )
        assert retired is not None
        ledger_rows = list(
            await session.scalars(
                select(DurableOperation).where(
                    DurableOperation.corpus_id == harbor.id,
                    DurableOperation.incremental_run_id == run.id,
                    DurableOperation.status == "completed",
                )
            )
        )
    assert {row.operation_type for row in ledger_rows} == {"classify", "extract"}
    assert len(ledger_rows) == 2
    skipped_keys = {str(item["content_key"]) for item in skipped_ops}
    assert skipped_keys.isdisjoint({row.operation_key for row in ledger_rows})

    baseline_facts = await harbor_inc.understand.list_facts(
        harbor.id, harbor_baseline.analysis_run_id
    )
    harbor_facts = await harbor_inc.understand.list_facts(
        harbor.id, _require_uuid(run.analysis_run_id)
    )
    new_contradictions = await harbor_inc.understand.list_contradictions(
        harbor.id, _require_uuid(run.analysis_run_id)
    )
    facts_after = {fact.id: fact for fact in harbor_facts}
    incremental_legacy_conflicts = _subject_contradictions(
        new_contradictions, facts_after, "legacy_retirement"
    )
    baseline_legacy = [
        fact
        for fact in baseline_facts
        if fact.support_status == "supported" and fact.subject_key == "legacy_retirement"
    ]
    incremental_legacy = [
        fact
        for fact in harbor_facts
        if fact.support_status == "supported" and fact.subject_key == "legacy_retirement"
    ]
    assert any(fact.normalized_value == "2026-12-04" for fact in baseline_legacy)
    assert any(fact.normalized_value == "2026-12-04" for fact in incremental_legacy)
    assert all(fact.category == "milestone_date" for fact in incremental_legacy)
    legacy_values = {fact.normalized_value for fact in incremental_legacy}
    assert "2026-12-04" in legacy_values
    assert "2026-12-18" not in legacy_values
    if len(legacy_values) == 1:
        assert incremental_legacy_conflicts == []
    assert not any(
        fact.citation is not None
        and str(fact.citation.get("source_version_id")) == str(old_governance_version)
        for fact in harbor_facts
        if fact.support_status == "supported"
    )
    assert not any("Aurora" in (fact.normalized_value or "") for fact in harbor_facts)
    assert not any("Elena Marlow" in (fact.normalized_value or "") for fact in harbor_facts)
    assert not any(
        "Decision Log" in str(item.get("logical_name", "")) for item in current.source_version_set
    )
    review = _json_object(harbor_payload["review"])
    assert review["implicit_approval"] is False
    assert review["previous_review_session_id"] == str(harbor_baseline.review_session_id)
    assert review["new_review_session_id"] != review["previous_review_session_id"]
    assert review["new_decision_count"] == 0
    previous_session = await harbor_inc.review.get_session(
        harbor.id, _require_uuid(harbor_baseline.review_session_id)
    )
    assert previous_session.status == "completed"
    new_items = await harbor_inc.review.list_items(harbor.id, _require_uuid(run.review_session_id))
    assert new_items
    assert all(item.review_status == "pending" for item in new_items)
    with pytest.raises(NotFoundError) as exc:
        await aurora_inc.get_run(aurora.id, run.id)
    assert exc.value.code == "incremental_run_not_found"


@pytest.mark.integration
async def test_new_source_is_added_and_identical_bytes_do_not_advance(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
    tmp_path: Path,
) -> None:
    phase02, _storage = phase02_service
    corpus, incremental = await prepare_incremental_corpus(
        phase02, corpus_fixtures / "aurora-control-hub"
    )
    baseline = await incremental.get_current_revision(corpus.id)
    added = tmp_path / "extra-note.txt"
    added.write_text("Extra note: delivery lead remains Dev Shah.\n", encoding="utf-8")
    await phase02.ingest(
        corpus_id=corpus.id,
        logical_name="Extra Note",
        declared_format="txt",
        upload=fixture_upload(added, "txt"),
    )
    added_run = await incremental.create_run(corpus.id, baseline_revision_id=baseline.id)
    assert added_run.change_kind == "added"
    current = await incremental.get_current_revision(corpus.id)
    noop = await incremental.create_run(corpus.id, baseline_revision_id=current.id)
    assert noop.change_kind == "unchanged"
    assert noop.result_revision_id == current.id
    assert noop.analysis_run_id is None


@pytest.mark.integration
async def test_reused_contradiction_and_finding_canonical_bytes_from_persisted_rows(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
    tmp_path: Path,
) -> None:
    phase02, _storage = phase02_service
    corpus, incremental = await prepare_incremental_corpus(
        phase02, corpus_fixtures / "aurora-control-hub"
    )
    baseline = await incremental.get_current_revision(corpus.id)
    added = tmp_path / "extra-note.txt"
    added.write_text("Extra note: delivery lead remains Dev Shah.\n", encoding="utf-8")
    await phase02.ingest(
        corpus_id=corpus.id,
        logical_name="Extra Note",
        declared_format="txt",
        upload=fixture_upload(added, "txt"),
    )
    run = await incremental.create_run(corpus.id, baseline_revision_id=baseline.id)
    assert run.status == "completed"
    evidence = await incremental.get_evidence(corpus.id, run.id)
    payload = _json_object(evidence["evidence"])
    reused_contradiction_ids = payload["reused_contradiction_ids"]
    assert reused_contradiction_ids
    canonical_contradictions = payload["canonical_unchanged_contradictions"]
    assert canonical_contradictions
    reused_findings = payload["canonical_unchanged_findings"]
    assert reused_findings

    baseline_facts = {
        fact.id: fact
        for fact in await incremental.understand.list_facts(corpus.id, baseline.analysis_run_id)
    }
    new_facts = {
        fact.id: fact
        for fact in await incremental.understand.list_facts(
            corpus.id, _require_uuid(run.analysis_run_id)
        )
    }
    baseline_contradictions = {
        item.id: item
        for item in await incremental.understand.list_contradictions(
            corpus.id, baseline.analysis_run_id
        )
    }
    new_contradictions = {
        item.id: item
        for item in await incremental.understand.list_contradictions(
            corpus.id, _require_uuid(run.analysis_run_id)
        )
    }
    pair = canonical_contradictions[0]
    before_item = baseline_contradictions[UUID(str(pair["baseline_contradiction_id"]))]
    after_item = new_contradictions[UUID(str(pair["incremental_contradiction_id"]))]
    before_bytes = canonical_bytes(_contradiction_canonical(before_item, baseline_facts))
    after_bytes = canonical_bytes(_contradiction_canonical(after_item, new_facts))
    assert after_bytes == before_bytes
    assert pair["canonical_bytes_equal"] is True
    assert pair["canonical_hash_before"] == pair["canonical_hash_after"]

    baseline_findings = {
        item.rule_id: item
        for item in await incremental.examine.list_findings(corpus.id, baseline.examination_run_id)
    }
    new_findings = {
        item.rule_id: item
        for item in await incremental.examine.list_findings(
            corpus.id, _require_uuid(run.examination_run_id)
        )
    }
    finding_pair = reused_findings[0]
    rule_id = str(finding_pair["rule_id"])
    before_finding = baseline_findings[rule_id]
    after_finding = new_findings[rule_id]
    before_finding_bytes = canonical_bytes(
        _finding_canonical(before_finding, baseline_facts, baseline_contradictions)
    )
    after_finding_bytes = canonical_bytes(
        _finding_canonical(after_finding, new_facts, new_contradictions)
    )
    assert after_finding_bytes == before_finding_bytes
    assert finding_pair["canonical_bytes_equal"] is True
    assert finding_pair["canonical_hash_before"] == finding_pair["canonical_hash_after"]


@pytest.mark.integration
async def test_corpus_revision_sources_reject_inconsistent_membership(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, _storage = phase02_service
    aurora, aurora_inc = await prepare_incremental_corpus(
        phase02, corpus_fixtures / "aurora-control-hub"
    )
    harbor, _harbor_inc = await prepare_incremental_corpus(
        phase02, corpus_fixtures / "harbor-ledger-modernization"
    )
    aurora_rev = await aurora_inc.get_current_revision(aurora.id)

    async with aurora_inc.session_factory() as session:
        aurora_membership = list(
            await session.scalars(
                select(CorpusRevisionSource).where(
                    CorpusRevisionSource.revision_id == aurora_rev.id,
                    CorpusRevisionSource.corpus_id == aurora.id,
                )
            )
        )
        harbor_membership = list(
            await session.scalars(
                select(CorpusRevisionSource).where(CorpusRevisionSource.corpus_id == harbor.id)
            )
        )
    charter = next(row for row in aurora_membership if row.logical_name == "Project Charter")
    risk = next(row for row in aurora_membership if row.logical_name == "Risk Register")
    harbor_row = harbor_membership[0]
    offset = 90

    async def _reject(
        *,
        source_id: UUID,
        source_version_id: UUID,
        sha256: str,
        logical_name: str,
    ) -> None:
        nonlocal offset
        offset += 1
        async with aurora_inc.session_factory() as session:
            baseline = await session.scalar(
                select(CorpusRevision).where(
                    CorpusRevision.id == aurora_rev.id,
                    CorpusRevision.corpus_id == aurora.id,
                )
            )
            assert baseline is not None
            scratch = CorpusRevision(
                id=uuid4(),
                corpus_id=aurora.id,
                revision_number=baseline.revision_number + offset,
                is_current=False,
                analysis_run_id=baseline.analysis_run_id,
                examination_run_id=baseline.examination_run_id,
                review_session_id=baseline.review_session_id,
                source_version_set=list(baseline.source_version_set),
                taxonomy_version=baseline.taxonomy_version,
                understand_graph_version=baseline.understand_graph_version,
                prompt_config_version=baseline.prompt_config_version,
                ruleset_version=baseline.ruleset_version,
                examine_graph_version=baseline.examine_graph_version,
                configuration=dict(baseline.configuration),
            )
            session.add(scratch)
            await session.flush()
            session.add(
                CorpusRevisionSource(
                    revision_id=scratch.id,
                    corpus_id=aurora.id,
                    source_id=source_id,
                    source_version_id=source_version_id,
                    sha256=sha256,
                    logical_name=logical_name,
                )
            )
            with pytest.raises(IntegrityError):
                await session.commit()

    await _reject(
        source_id=charter.source_id,
        source_version_id=risk.source_version_id,
        sha256=risk.sha256,
        logical_name="wrong-source",
    )
    await _reject(
        source_id=charter.source_id,
        source_version_id=harbor_row.source_version_id,
        sha256=harbor_row.sha256,
        logical_name="wrong-corpus",
    )
    await _reject(
        source_id=charter.source_id,
        source_version_id=charter.source_version_id,
        sha256="f" * 64,
        logical_name="wrong-sha",
    )
    await _reject(
        source_id=charter.source_id,
        source_version_id=uuid4(),
        sha256=charter.sha256,
        logical_name="random-version",
    )


@pytest.mark.integration
async def test_cross_corpus_incremental_access_is_rejected(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, _storage = phase02_service
    aurora, aurora_inc = await prepare_incremental_corpus(
        phase02, corpus_fixtures / "aurora-control-hub"
    )
    harbor, harbor_inc = await prepare_incremental_corpus(
        phase02, corpus_fixtures / "harbor-ledger-modernization"
    )
    aurora_rev = await aurora_inc.get_current_revision(aurora.id)
    with pytest.raises(NotFoundError) as exc:
        await harbor_inc.get_revision(harbor.id, aurora_rev.id)
    assert exc.value.code == "corpus_revision_not_found"
    with pytest.raises(NotFoundError) as exc:
        await harbor_inc.get_run(harbor.id, uuid4())
    assert exc.value.code == "incremental_run_not_found"


@pytest.mark.integration
async def test_finalize_crash_leaves_baseline_current(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
    tmp_path: Path,
) -> None:
    phase02, _storage = phase02_service
    corpus, incremental = await prepare_incremental_corpus(
        phase02, corpus_fixtures / "aurora-control-hub"
    )
    baseline = await incremental.get_current_revision(corpus.id)
    changed = _changed_copy(
        corpus_fixtures / "aurora-control-hub" / "decision-log.txt",
        tmp_path / "decision-log-crash.txt",
        "2026-10-30",
        "2026-12-01",
    )
    await phase02.ingest(
        corpus_id=corpus.id,
        logical_name="Decision Log",
        declared_format="txt",
        upload=fixture_upload(changed, "txt"),
    )
    incremental.fail_before_finalize = True
    with pytest.raises(IncrementalFinalizeInjectedError):
        await incremental.create_run(corpus.id, baseline_revision_id=baseline.id)
    incremental.fail_before_finalize = False
    still_current = await incremental.get_current_revision(corpus.id)
    assert still_current.id == baseline.id
    assert still_current.revision_number == baseline.revision_number
    retry = await incremental.create_run(corpus.id, baseline_revision_id=baseline.id)
    assert retry.status == "completed"
    advanced = await incremental.get_current_revision(corpus.id)
    assert advanced.revision_number == baseline.revision_number + 1
    assert advanced.id != baseline.id
