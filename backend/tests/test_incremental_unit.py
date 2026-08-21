from uuid import uuid4

import pytest

from app.canonical import (
    CANONICAL_SERIALIZATION_VERSION,
    canonical_bytes,
    canonical_hash,
    fact_canonical_payload,
    review_item_canonical_payload,
)
from app.errors import ValidationError
from app.incremental_planning import (
    ContradictionImpactRef,
    FactImpactRef,
    SourceSnapshot,
    diff_snapshots,
    plan_impact,
)
from app.ruleset import OPEN_CONTRADICTION_RULE_ID
from app.watcher import _parse_inbox_path


def test_canonical_serialization_is_deterministic_and_excludes_identity() -> None:
    payload = fact_canonical_payload(
        category="status",
        subject_key="overall_status",
        normalized_value="amber",
        confidence=1.0,
        support_status="supported",
        rejection_reason=None,
        citation={
            "source_version_id": "11111111-1111-1111-1111-111111111111",
            "source_sha256": "a" * 64,
            "format": "txt",
            "native_locator": "lines[1-1]/block[0]",
            "normalized_start": 0,
            "normalized_end": 5,
            "exact_quote": "amber",
        },
        source_block_id="22222222-2222-2222-2222-222222222222",
    )
    again = fact_canonical_payload(
        category="status",
        subject_key="overall_status",
        normalized_value="amber",
        confidence=1.0,
        support_status="supported",
        rejection_reason=None,
        citation={
            "exact_quote": "amber",
            "format": "txt",
            "native_locator": "lines[1-1]/block[0]",
            "normalized_end": 5,
            "normalized_start": 0,
            "source_sha256": "a" * 64,
            "source_version_id": "11111111-1111-1111-1111-111111111111",
        },
        source_block_id="22222222-2222-2222-2222-222222222222",
    )
    assert payload["serialization_version"] == CANONICAL_SERIALIZATION_VERSION
    assert "id" not in payload
    assert "run_id" not in payload
    assert canonical_bytes(payload) == canonical_bytes(again)
    assert canonical_hash(payload) == canonical_hash(again)


def test_review_item_canonical_excludes_session_identity_and_decision_state() -> None:
    payload = review_item_canonical_payload(
        rule_id="spa.ownership.sponsor",
        rule_version="1",
        outcome="pass",
        severity="medium",
        title="Sponsor is assigned",
        message="Named sponsor is present.",
        structured_reason={"evaluator": "required_assigned_owner"},
        evidence_kind="grounded_facts",
        fact_hashes=["a" * 64],
        contradiction_hashes=[],
        citations=[
            {
                "exact_quote": "Elena Marlow",
                "format": "txt",
                "native_locator": "lines[1-1]/block[0]",
                "normalized_end": 12,
                "normalized_start": 0,
                "source_sha256": "b" * 64,
                "source_version_id": "11111111-1111-1111-1111-111111111111",
            }
        ],
        review_required=True,
    )
    assert payload["serialization_version"] == CANONICAL_SERIALIZATION_VERSION
    assert payload["kind"] == "review_item"
    assert payload["review_required"] is True
    assert "review_session_id" not in payload
    assert "review_item_id" not in payload
    assert "review_status" not in payload
    assert "created_at" not in payload
    again = review_item_canonical_payload(
        rule_id="spa.ownership.sponsor",
        rule_version="1",
        outcome="pass",
        severity="medium",
        title="Sponsor is assigned",
        message="Named sponsor is present.",
        structured_reason={"evaluator": "required_assigned_owner"},
        evidence_kind="grounded_facts",
        fact_hashes=["a" * 64],
        contradiction_hashes=[],
        citations=[
            {
                "source_version_id": "11111111-1111-1111-1111-111111111111",
                "source_sha256": "b" * 64,
                "format": "txt",
                "native_locator": "lines[1-1]/block[0]",
                "normalized_start": 0,
                "normalized_end": 12,
                "exact_quote": "Elena Marlow",
            }
        ],
        review_required=True,
    )
    assert canonical_bytes(payload) == canonical_bytes(again)


def test_identical_bytes_are_unchanged_and_changed_bytes_create_new_version() -> None:
    source_a = uuid4()
    source_b = uuid4()
    version_a = uuid4()
    version_b1 = uuid4()
    version_b2 = uuid4()
    baseline = (
        SourceSnapshot(source_a, version_a, "A", "a" * 64),
        SourceSnapshot(source_b, version_b1, "B", "b" * 64),
    )
    current_same = (
        SourceSnapshot(source_a, version_a, "A", "a" * 64),
        SourceSnapshot(source_b, version_b1, "B", "b" * 64),
    )
    current_changed = (
        SourceSnapshot(source_a, version_a, "A", "a" * 64),
        SourceSnapshot(source_b, version_b2, "B", "c" * 64),
    )
    unchanged = diff_snapshots(baseline, current_same)
    assert unchanged.change_kind == "unchanged"
    assert not unchanged.has_changes
    changed = diff_snapshots(baseline, current_changed)
    assert changed.change_kind == "changed"
    assert changed.changed_source_ids == {source_b}
    assert changed.unchanged_source_version_ids == {version_a}


def test_new_source_is_added_without_corpus_name_special_cases() -> None:
    source_a = uuid4()
    source_c = uuid4()
    baseline = (SourceSnapshot(source_a, uuid4(), "Charter", "a" * 64),)
    current = (
        SourceSnapshot(source_a, baseline[0].source_version_id, "Charter", "a" * 64),
        SourceSnapshot(source_c, uuid4(), "New Notes", "d" * 64),
    )
    added = diff_snapshots(baseline, current)
    assert added.change_kind == "added"
    assert added.added[0].logical_name == "New Notes"
    mixed_current = (
        SourceSnapshot(source_a, uuid4(), "Charter", "e" * 64),
        SourceSnapshot(source_c, uuid4(), "New Notes", "d" * 64),
    )
    mixed = diff_snapshots(baseline, mixed_current)
    assert mixed.change_kind == "mixed"


def test_impact_marks_only_facts_citing_changed_versions() -> None:
    source_a = uuid4()
    source_b = uuid4()
    version_a = uuid4()
    version_b1 = uuid4()
    version_b2 = uuid4()
    fact_a = uuid4()
    fact_b = uuid4()
    fact_c = uuid4()
    contradiction = uuid4()
    changes = diff_snapshots(
        (
            SourceSnapshot(source_a, version_a, "A", "a" * 64),
            SourceSnapshot(source_b, version_b1, "B", "b" * 64),
        ),
        (
            SourceSnapshot(source_a, version_a, "A", "a" * 64),
            SourceSnapshot(source_b, version_b2, "B", "c" * 64),
        ),
    )
    facts = (
        FactImpactRef(fact_a, "status", "overall_status", "supported", version_a, uuid4(), "h1"),
        FactImpactRef(
            fact_b, "milestone_date", "production_readiness", "supported", version_b1, uuid4(), "h2"
        ),
        FactImpactRef(
            fact_c, "owner_accountability", "project_sponsor", "supported", version_a, uuid4(), "h3"
        ),
    )
    contradictions = (
        ContradictionImpactRef(
            contradiction,
            fact_b,
            fact_a,
            "milestone_date",
            "production_readiness",
            "hc",
        ),
    )
    impact = plan_impact(
        changes=changes,
        facts=facts,
        contradictions=contradictions,
        block_ids_by_version={version_b1: [uuid4()], version_b2: [uuid4()]},
    )
    assert fact_b in impact.affected_fact_ids
    assert fact_a in impact.reused_fact_ids
    assert fact_c in impact.reused_fact_ids
    assert contradiction in impact.affected_contradiction_ids
    assert "spa.milestone.production-readiness" in impact.affected_rule_ids
    assert "spa.ownership.sponsor" in impact.reused_rule_ids
    assert OPEN_CONTRADICTION_RULE_ID in impact.affected_rule_ids


def test_new_extracted_fact_key_replans_dependent_rules() -> None:
    source_a = uuid4()
    source_b = uuid4()
    version_a = uuid4()
    version_b1 = uuid4()
    version_b2 = uuid4()
    fact_a = uuid4()
    extracted_id = uuid4()
    changes = diff_snapshots(
        (
            SourceSnapshot(source_a, version_a, "A", "a" * 64),
            SourceSnapshot(source_b, version_b1, "B", "b" * 64),
        ),
        (
            SourceSnapshot(source_a, version_a, "A", "a" * 64),
            SourceSnapshot(source_b, version_b2, "B", "c" * 64),
        ),
    )
    facts = (
        FactImpactRef(fact_a, "status", "overall_status", "supported", version_a, uuid4(), "h1"),
    )
    extracted = (
        FactImpactRef(
            extracted_id,
            "owner_accountability",
            "budget_owner",
            "supported",
            version_b2,
            uuid4(),
            "h2",
        ),
    )
    before = plan_impact(
        changes=changes,
        facts=facts,
        contradictions=(),
        block_ids_by_version={version_b1: [uuid4()], version_b2: [uuid4()]},
    )
    assert "spa.ownership.budget" in before.reused_rule_ids
    after = plan_impact(
        changes=changes,
        facts=facts,
        contradictions=(),
        block_ids_by_version={version_b1: [uuid4()], version_b2: [uuid4()]},
        extracted_facts=extracted,
    )
    assert fact_a in after.reused_fact_ids
    assert "spa.ownership.budget" in after.affected_rule_ids
    assert ("owner_accountability", "budget_owner") in after.affected_keys


def test_contradiction_keys_are_recomputed_or_reused_never_both() -> None:
    source_a = uuid4()
    source_b = uuid4()
    version_a = uuid4()
    version_b1 = uuid4()
    version_b2 = uuid4()
    fact_a = uuid4()
    fact_b = uuid4()
    reused_conflict = uuid4()
    affected_conflict = uuid4()
    changes = diff_snapshots(
        (
            SourceSnapshot(source_a, version_a, "A", "a" * 64),
            SourceSnapshot(source_b, version_b1, "B", "b" * 64),
        ),
        (
            SourceSnapshot(source_a, version_a, "A", "a" * 64),
            SourceSnapshot(source_b, version_b2, "B", "c" * 64),
        ),
    )
    facts = (
        FactImpactRef(fact_a, "status", "overall_status", "supported", version_a, uuid4(), "h1"),
        FactImpactRef(
            fact_b, "milestone_date", "production_readiness", "supported", version_b1, uuid4(), "h2"
        ),
    )
    contradictions = (
        ContradictionImpactRef(
            affected_conflict,
            fact_b,
            fact_a,
            "milestone_date",
            "production_readiness",
            "hc1",
        ),
        ContradictionImpactRef(
            reused_conflict,
            fact_a,
            fact_a,
            "status",
            "overall_status",
            "hc2",
        ),
    )
    impact = plan_impact(
        changes=changes,
        facts=facts,
        contradictions=contradictions,
        block_ids_by_version={version_b1: [uuid4()], version_b2: [uuid4()]},
    )
    overlap = impact.affected_contradiction_ids & impact.reused_contradiction_ids
    assert not overlap
    assert affected_conflict in impact.affected_contradiction_ids
    assert reused_conflict in impact.reused_contradiction_ids


def test_watcher_path_contract_maps_corpus_and_logical_source() -> None:
    corpus_id, logical_name, declared = _parse_inbox_path(
        "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/Decision Log.txt"
    )
    assert str(corpus_id) == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    assert logical_name == "Decision Log"
    assert declared == "txt"
    with pytest.raises(ValidationError) as exc:
        _parse_inbox_path("not-a-uuid/Decision Log.txt")
    assert exc.value.code == "watcher_corpus_invalid"
    with pytest.raises(ValidationError) as exc:
        _parse_inbox_path("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/Decision Log.bin")
    assert exc.value.code == "watcher_format_unsupported"
