"""Pure change detection and provenance impact planning for incremental runs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from app.model_gateway import BlockContext
from app.operation_ledger import canonical_json, sha256_hex
from app.ruleset import OPEN_CONTRADICTION_RULE_ID, RULES, Rule


@dataclass(frozen=True, slots=True)
class SourceSnapshot:
    source_id: UUID
    source_version_id: UUID
    logical_name: str
    sha256: str


@dataclass(frozen=True, slots=True)
class ChangeSet:
    unchanged: tuple[SourceSnapshot, ...]
    changed: tuple[tuple[SourceSnapshot, SourceSnapshot], ...]
    added: tuple[SourceSnapshot, ...]
    removed: tuple[SourceSnapshot, ...]

    @property
    def change_kind(self) -> str:
        kinds: list[str] = []
        if self.changed:
            kinds.append("changed")
        if self.added:
            kinds.append("added")
        if self.removed:
            kinds.append("removed")
        if not kinds:
            return "unchanged"
        if len(kinds) == 1:
            return kinds[0]
        return "mixed"

    @property
    def has_changes(self) -> bool:
        return self.change_kind != "unchanged"

    @property
    def changed_source_ids(self) -> set[UUID]:
        ids = {old.source_id for old, _new in self.changed}
        ids.update(item.source_id for item in self.added)
        ids.update(item.source_id for item in self.removed)
        return ids

    @property
    def changed_source_version_ids(self) -> set[UUID]:
        ids = {new.source_version_id for _old, new in self.changed}
        ids.update(item.source_version_id for item in self.added)
        return ids

    @property
    def retired_source_version_ids(self) -> set[UUID]:
        ids = {old.source_version_id for old, _new in self.changed}
        ids.update(item.source_version_id for item in self.removed)
        return ids

    @property
    def unchanged_source_version_ids(self) -> set[UUID]:
        return {item.source_version_id for item in self.unchanged}


@dataclass(frozen=True, slots=True)
class FactImpactRef:
    id: UUID
    category: str
    subject_key: str
    support_status: str
    source_version_id: UUID | None
    source_block_id: UUID | None
    canonical_hash: str


@dataclass(frozen=True, slots=True)
class ContradictionImpactRef:
    id: UUID
    fact_a_id: UUID
    fact_b_id: UUID
    category: str
    subject_key: str
    canonical_hash: str


@dataclass(frozen=True, slots=True)
class ImpactSet:
    affected_fact_ids: frozenset[UUID]
    reused_fact_ids: frozenset[UUID]
    affected_contradiction_ids: frozenset[UUID]
    reused_contradiction_ids: frozenset[UUID]
    affected_rule_ids: frozenset[str]
    reused_rule_ids: frozenset[str]
    affected_block_ids: frozenset[UUID]
    affected_keys: frozenset[tuple[str, str]]
    global_rule_reasons: dict[str, str] = field(default_factory=dict)


def snapshots_from_payload(payload: Sequence[Mapping[str, Any]]) -> tuple[SourceSnapshot, ...]:
    items = [
        SourceSnapshot(
            source_id=UUID(str(item["source_id"])),
            source_version_id=UUID(str(item["source_version_id"])),
            logical_name=str(item["logical_name"]),
            sha256=str(item["sha256"]),
        )
        for item in payload
    ]
    return tuple(sorted(items, key=lambda item: str(item.source_id)))


def snapshots_to_payload(snapshots: Sequence[SourceSnapshot]) -> list[dict[str, str]]:
    return [
        {
            "logical_name": item.logical_name,
            "sha256": item.sha256,
            "source_id": str(item.source_id),
            "source_version_id": str(item.source_version_id),
        }
        for item in sorted(snapshots, key=lambda item: str(item.source_id))
    ]


def diff_snapshots(
    baseline: Sequence[SourceSnapshot],
    current: Sequence[SourceSnapshot],
) -> ChangeSet:
    """Identity is logical source plus SHA-256. Timestamps are not used."""

    baseline_by_source = {item.source_id: item for item in baseline}
    current_by_source = {item.source_id: item for item in current}
    unchanged: list[SourceSnapshot] = []
    changed: list[tuple[SourceSnapshot, SourceSnapshot]] = []
    added: list[SourceSnapshot] = []
    removed: list[SourceSnapshot] = []
    for source_id, current_item in current_by_source.items():
        previous = baseline_by_source.get(source_id)
        if previous is None:
            added.append(current_item)
        elif previous.sha256 == current_item.sha256:
            unchanged.append(current_item)
        else:
            changed.append((previous, current_item))
    for source_id, previous in baseline_by_source.items():
        if source_id not in current_by_source:
            removed.append(previous)
    return ChangeSet(
        unchanged=tuple(sorted(unchanged, key=lambda item: str(item.source_id))),
        changed=tuple(sorted(changed, key=lambda item: str(item[0].source_id))),
        added=tuple(sorted(added, key=lambda item: str(item.source_id))),
        removed=tuple(sorted(removed, key=lambda item: str(item.source_id))),
    )


def citation_source_version_id(citation: Mapping[str, Any] | None) -> UUID | None:
    if citation is None or "source_version_id" not in citation:
        return None
    return UUID(str(citation["source_version_id"]))


def plan_impact(
    *,
    changes: ChangeSet,
    facts: Sequence[FactImpactRef],
    contradictions: Sequence[ContradictionImpactRef],
    block_ids_by_version: Mapping[UUID, Sequence[UUID]],
    extracted_facts: Sequence[FactImpactRef] = (),
    rules: Sequence[Rule] = RULES,
) -> ImpactSet:
    """Plan impact from retired versions, then union newly extracted fact keys."""

    retired = changes.retired_source_version_ids
    new_versions = changes.changed_source_version_ids
    retired_facts = [
        fact
        for fact in facts
        if fact.source_version_id is not None and fact.source_version_id in retired
    ]
    extracted_keys = {(fact.category, fact.subject_key) for fact in extracted_facts}
    retired_keys = {(fact.category, fact.subject_key) for fact in retired_facts}
    affected_keys = retired_keys | extracted_keys
    affected_facts = retired_facts
    reused_facts = [fact for fact in facts if fact.id not in {item.id for item in affected_facts}]
    affected_contradictions = [
        item
        for item in contradictions
        if (item.category, item.subject_key) in affected_keys
        or item.fact_a_id in {fact.id for fact in affected_facts}
        or item.fact_b_id in {fact.id for fact in affected_facts}
    ]
    reused_contradictions = [
        item
        for item in contradictions
        if (item.category, item.subject_key) not in affected_keys
        and item.id not in {row.id for row in affected_contradictions}
    ]
    affected_block_ids: set[UUID] = set()
    for version_id in retired | new_versions:
        affected_block_ids.update(block_ids_by_version.get(version_id, ()))
    affected_rule_ids: set[str] = set()
    global_rule_reasons: dict[str, str] = {}
    for rule in rules:
        if _rule_is_affected(
            rule,
            dependency_keys=affected_keys,
            affected_contradictions=affected_contradictions,
            has_new_or_changed_source=bool(changes.changed or changes.added),
        ):
            affected_rule_ids.add(rule.rule_id)
            if rule.rule_id == OPEN_CONTRADICTION_RULE_ID:
                global_rule_reasons[rule.rule_id] = (
                    "corpus-wide remaining-contradiction state may have changed"
                )
    reused_rule_ids = {rule.rule_id for rule in rules} - affected_rule_ids
    return ImpactSet(
        affected_fact_ids=frozenset(item.id for item in affected_facts),
        reused_fact_ids=frozenset(item.id for item in reused_facts),
        affected_contradiction_ids=frozenset(item.id for item in affected_contradictions),
        reused_contradiction_ids=frozenset(item.id for item in reused_contradictions),
        affected_rule_ids=frozenset(affected_rule_ids),
        reused_rule_ids=frozenset(reused_rule_ids),
        affected_block_ids=frozenset(affected_block_ids),
        affected_keys=frozenset(affected_keys),
        global_rule_reasons=global_rule_reasons,
    )


def _rule_is_affected(
    rule: Rule,
    *,
    dependency_keys: set[tuple[str, str]],
    affected_contradictions: Sequence[ContradictionImpactRef],
    has_new_or_changed_source: bool,
) -> bool:
    if rule.rule_id == OPEN_CONTRADICTION_RULE_ID:
        return bool(affected_contradictions) or has_new_or_changed_source
    if rule.required_subject_keys:
        subjects = set(rule.required_subject_keys)
        categories = set(rule.required_fact_categories)
        return any(
            category in categories and subject in subjects for category, subject in dependency_keys
        )
    if rule.required_fact_categories:
        categories = set(rule.required_fact_categories)
        return any(category in categories for category, _subject in dependency_keys)
    return bool(dependency_keys or affected_contradictions)


def blocks_source_input_version(blocks: Sequence[BlockContext]) -> str:
    pairs = sorted({(str(item.source_version_id), item.source_sha256) for item in blocks})
    return sha256_hex("|".join(f"{version}:{digest}" for version, digest in pairs))


def request_hash_for_blocks(blocks: Sequence[BlockContext]) -> str:
    payload = [item.model_dump(mode="json") for item in blocks]
    return sha256_hex(canonical_json(payload))
