"""Versioned Software Project Assurance examination ruleset.

Rules are centrally defined data plus named evaluators. Document text cannot add,
remove, or override a rule. Evaluation consumes only Phase 03 grounded facts and
contradictions; retrieval hits and unsupported assertions are ignored.

Subject-specific lookups require both the rule's category and subject_key. A
contradiction satisfies such a rule only when both grounded fact sides match that
category and subject.

Evidence kinds:

- source evidence: Phase 02 exact provenance over original bytes (never attached
  by Examine except as derived from a grounded fact).
- grounded fact evidence: Phase 03 SUPPORTED facts and their contradictions.
- deterministic analysis-stage attestation: same-run/same-corpus completed
  `detect_contradictions` stage proving contradiction detection finished. This is
  process evidence, not source provenance, and must not attach unrelated facts.
"""

from __future__ import annotations

import json
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from app.taxonomy import comparison_key

RULESET_VERSION = "software-project-assurance.v1"
EXAMINE_GRAPH_VERSION = "examine.v1"
RULE_VERSION = "1"
OPEN_CONTRADICTION_RULE_ID = "spa.contradiction.open"

Outcome = Literal["pass", "fail", "warning", "unknown"]
EvidenceKind = Literal["none", "grounded_facts", "process_attestation"]

UNASSIGNED_VALUES = frozenset({"unassigned", "unknown", "tbd", "n/a", "none", "unspecified"})
EVIDENCE_STATUSES = frozenset({"supported"})


@dataclass(frozen=True, slots=True)
class Rule:
    rule_id: str
    version: str
    title: str
    category: str
    severity: str
    description: str
    evaluator: str
    required_fact_categories: tuple[str, ...]
    required_subject_keys: tuple[str, ...]
    consumes_contradictions: bool
    unknown_behavior: str
    configuration: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class RulesetConfig:
    version: str
    rules: tuple[Rule, ...]

    @property
    def rules_by_id(self) -> dict[str, Rule]:
        return {rule.rule_id: rule for rule in self.rules}


@dataclass(frozen=True, slots=True)
class GroundedFactView:
    id: str
    category: str
    subject_key: str
    normalized_value: str
    support_status: str
    citation: dict[str, Any] | None
    source_block_id: str | None


@dataclass(frozen=True, slots=True)
class GroundedContradictionView:
    id: str
    contradiction_type: str
    fact_a_id: str
    fact_b_id: str
    reason: str
    status: str


@dataclass(frozen=True, slots=True)
class UnderstandingView:
    facts: tuple[GroundedFactView, ...]
    contradictions: tuple[GroundedContradictionView, ...]
    contradiction_detection_attested: bool = False


@dataclass(frozen=True, slots=True)
class RuleEvaluation:
    rule_id: str
    rule_version: str
    outcome: Outcome
    severity: str
    title: str
    message: str
    reason: dict[str, Any]
    fact_ids: tuple[str, ...]
    contradiction_ids: tuple[str, ...]
    citations: tuple[dict[str, Any], ...]
    confidence: float
    evidence_kind: EvidenceKind


PACKAGED_RULESET_PATH = (
    Path(__file__).resolve().parent / "rulesets" / "software-project-assurance.v1.json"
)


def default_ruleset_path() -> Path:
    return PACKAGED_RULESET_PATH


def rule_from_mapping(raw: Mapping[str, Any]) -> Rule:
    return Rule(
        rule_id=str(raw["rule_id"]),
        version=str(raw.get("version") or RULE_VERSION),
        title=str(raw["title"]),
        category=str(raw["category"]),
        severity=str(raw["severity"]),
        description=str(raw["description"]),
        evaluator=str(raw["evaluator"]),
        required_fact_categories=tuple(str(item) for item in raw["required_fact_categories"]),
        required_subject_keys=tuple(str(item) for item in raw["required_subject_keys"]),
        consumes_contradictions=bool(raw["consumes_contradictions"]),
        unknown_behavior=str(raw["unknown_behavior"]),
        configuration=dict(raw.get("configuration") or {}),
    )


def load_ruleset_config(path: Path | None = None) -> RulesetConfig:
    """Load validated ruleset data without import-time environment configuration."""
    resolved = path or default_ruleset_path()
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    rules = tuple(rule_from_mapping(item) for item in payload["rules"])
    if not rules:
        raise ValueError("ruleset must contain at least one rule")
    ids = [rule.rule_id for rule in rules]
    if len(ids) != len(set(ids)):
        raise ValueError("ruleset rule ids must be unique")
    version = str(payload.get("ruleset_version") or "").strip()
    if not version:
        raise ValueError("ruleset_version must be non-empty")
    return RulesetConfig(version=version, rules=rules)


def load_ruleset(path: Path | None = None) -> tuple[Rule, ...]:
    """Load versioned rules as configuration data. Evaluators remain named Python functions."""
    return load_ruleset_config(path).rules


RULESET_CONFIG = load_ruleset_config(PACKAGED_RULESET_PATH)
RULES: tuple[Rule, ...] = RULESET_CONFIG.rules
RULES_BY_ID = {rule.rule_id: rule for rule in RULES}


def is_unassigned(value: str) -> bool:
    return comparison_key(value) in UNASSIGNED_VALUES


def expected_category(rule: Rule) -> str:
    if "category" in rule.configuration:
        return str(rule.configuration["category"])
    return rule.category


def expected_subject_key(rule: Rule) -> str | None:
    if "subject_key" in rule.configuration:
        return str(rule.configuration["subject_key"])
    return None


def supported_facts(
    view: UnderstandingView,
    *,
    category: str | None = None,
    subject_key: str | None = None,
) -> tuple[GroundedFactView, ...]:
    selected: list[GroundedFactView] = []
    for fact in view.facts:
        if fact.support_status not in EVIDENCE_STATUSES:
            continue
        if category is not None and fact.category != category:
            continue
        if subject_key is not None and fact.subject_key != subject_key:
            continue
        selected.append(fact)
    return tuple(selected)


def facts_by_id(view: UnderstandingView) -> dict[str, GroundedFactView]:
    return {fact.id: fact for fact in view.facts}


def citations_for(facts: Sequence[GroundedFactView]) -> tuple[dict[str, Any], ...]:
    citations: list[dict[str, Any]] = []
    for fact in facts:
        if fact.citation is None or fact.support_status not in EVIDENCE_STATUSES:
            continue
        citations.append(dict(fact.citation))
    return tuple(citations)


def contradictions_for_category_subject(
    view: UnderstandingView, category: str, subject_key: str
) -> tuple[GroundedContradictionView, ...]:
    """A contradiction matches only when both grounded sides share category and subject."""
    by_id = facts_by_id(view)
    matched: list[GroundedContradictionView] = []
    for item in view.contradictions:
        if item.status != "open":
            continue
        fact_a = by_id.get(item.fact_a_id)
        fact_b = by_id.get(item.fact_b_id)
        if fact_a is None or fact_b is None:
            continue
        if not _fact_matches(fact_a, category, subject_key):
            continue
        if not _fact_matches(fact_b, category, subject_key):
            continue
        matched.append(item)
    return tuple(matched)


def contradictions_for_subject(
    view: UnderstandingView, subject_key: str, *, category: str
) -> tuple[GroundedContradictionView, ...]:
    return contradictions_for_category_subject(view, category, subject_key)


def _fact_matches(fact: GroundedFactView, category: str, subject_key: str) -> bool:
    return fact.category == category and fact.subject_key == subject_key


def paired_facts(
    view: UnderstandingView, item: GroundedContradictionView
) -> tuple[GroundedFactView, ...]:
    by_id = facts_by_id(view)
    sides: list[GroundedFactView] = []
    for fact_id in (item.fact_a_id, item.fact_b_id):
        fact = by_id.get(fact_id)
        if fact is not None:
            sides.append(fact)
    return tuple(sides)


def has_supported_evidence(view: UnderstandingView) -> bool:
    return any(fact.support_status in EVIDENCE_STATUSES for fact in view.facts)


def select_rules(view: UnderstandingView, rules: Sequence[Rule] = RULES) -> tuple[Rule, ...]:
    """All ruleset members apply when grounded evidence exists; otherwise none apply."""
    if not has_supported_evidence(view):
        return ()
    return tuple(rules)


def evaluate_rule(rule: Rule, view: UnderstandingView) -> RuleEvaluation:
    evaluator = EVALUATORS.get(rule.evaluator)
    if evaluator is None:
        raise ValueError(f"unknown examiner evaluator: {rule.evaluator}")
    return evaluator(rule, view)


def evaluate_rules(
    view: UnderstandingView, rules: Sequence[Rule] = RULES
) -> tuple[RuleEvaluation, ...]:
    specific = [rule for rule in rules if rule.rule_id != OPEN_CONTRADICTION_RULE_ID]
    generic = [rule for rule in rules if rule.rule_id == OPEN_CONTRADICTION_RULE_ID]
    specific_results = [evaluate_rule(rule, view) for rule in specific]
    consumed = {item_id for result in specific_results for item_id in result.contradiction_ids}
    generic_results = [
        evaluate_open_contradictions(rule, view, consumed=consumed) for rule in generic
    ]
    by_id = {result.rule_id: result for result in [*specific_results, *generic_results]}
    return tuple(by_id[rule.rule_id] for rule in rules if rule.rule_id in by_id)


def validate_evaluation(
    evaluation: RuleEvaluation,
    view: UnderstandingView,
    rules_by_id: Mapping[str, Rule] | None = None,
) -> str | None:
    """Return a reason code when a finding is not safely grounded."""
    by_id = facts_by_id(view)
    contradiction_by_id = {item.id: item for item in view.contradictions}
    rule = (rules_by_id or RULES_BY_ID).get(evaluation.rule_id)
    if evaluation.outcome not in {"pass", "fail", "warning", "unknown"}:
        return "invalid_outcome"
    if evaluation.evidence_kind not in {"none", "grounded_facts", "process_attestation"}:
        return "invalid_evidence_kind"
    if evaluation.outcome == "unknown":
        if evaluation.evidence_kind != "none":
            return "unknown_must_not_claim_evidence"
        if evaluation.fact_ids or evaluation.contradiction_ids or evaluation.citations:
            return "unknown_must_not_claim_evidence"
        return None
    if evaluation.evidence_kind == "process_attestation":
        if evaluation.outcome != "pass":
            return "process_attestation_must_be_pass"
        if evaluation.fact_ids or evaluation.contradiction_ids or evaluation.citations:
            return "process_attestation_must_not_claim_source_or_fact_evidence"
        if not view.contradiction_detection_attested:
            return "process_attestation_missing"
        return None
    if evaluation.evidence_kind != "grounded_facts":
        return "grounded_outcome_missing_facts"
    if not evaluation.fact_ids:
        return "grounded_outcome_missing_facts"
    for fact_id in evaluation.fact_ids:
        fact = by_id.get(fact_id)
        if fact is None:
            return "unknown_fact_reference"
        if fact.support_status not in EVIDENCE_STATUSES:
            return "non_supported_fact_reference"
        if fact.citation is None:
            return "supported_fact_missing_citation"
        if (
            rule is not None
            and rule.required_fact_categories
            and fact.category not in rule.required_fact_categories
        ):
            return "fact_category_mismatch"
        if (
            rule is not None
            and rule.required_subject_keys
            and fact.subject_key not in rule.required_subject_keys
        ):
            return "fact_subject_mismatch"
    for contradiction_id in evaluation.contradiction_ids:
        item = contradiction_by_id.get(contradiction_id)
        if item is None:
            return "unknown_contradiction_reference"
        if item.fact_a_id not in evaluation.fact_ids or item.fact_b_id not in evaluation.fact_ids:
            return "contradiction_facts_not_referenced"
        if rule is not None and rule.required_fact_categories and rule.required_subject_keys:
            side_a = by_id.get(item.fact_a_id)
            side_b = by_id.get(item.fact_b_id)
            if side_a is None or side_b is None:
                return "unknown_fact_reference"
            category = expected_category(rule)
            subject_key = expected_subject_key(rule)
            if subject_key is None:
                continue
            if not _fact_matches(side_a, category, subject_key) or not _fact_matches(
                side_b, category, subject_key
            ):
                return "contradiction_side_category_or_subject_mismatch"
    expected = citations_for(tuple(by_id[fact_id] for fact_id in evaluation.fact_ids))
    if list(evaluation.citations) != list(expected):
        return "citation_mismatch"
    return None


def _base_reason(rule: Rule, **extra: Any) -> dict[str, Any]:
    return {
        "evaluator": rule.evaluator,
        "required_fact_categories": list(rule.required_fact_categories),
        "required_subject_keys": list(rule.required_subject_keys),
        "unknown_behavior": rule.unknown_behavior,
        **extra,
    }


def _unknown(rule: Rule, missing: Sequence[str]) -> RuleEvaluation:
    return RuleEvaluation(
        rule_id=rule.rule_id,
        rule_version=rule.version,
        outcome="unknown",
        severity="info",
        title=rule.title,
        message="Missing required grounded evidence: " + "; ".join(missing) + ".",
        reason=_base_reason(rule, evidence_kind="none", missing=list(missing)),
        fact_ids=(),
        contradiction_ids=(),
        citations=(),
        confidence=0.0,
        evidence_kind="none",
    )


def _grounded(
    rule: Rule,
    *,
    outcome: Outcome,
    message: str,
    facts: Sequence[GroundedFactView],
    contradictions: Sequence[GroundedContradictionView] = (),
    extra_reason: Mapping[str, Any] | None = None,
) -> RuleEvaluation:
    severity = rule.severity if outcome in {"fail", "warning"} else "info"
    return RuleEvaluation(
        rule_id=rule.rule_id,
        rule_version=rule.version,
        outcome=outcome,
        severity=severity,
        title=rule.title,
        message=message,
        reason=_base_reason(rule, evidence_kind="grounded_facts", **dict(extra_reason or {})),
        fact_ids=tuple(fact.id for fact in facts),
        contradiction_ids=tuple(item.id for item in contradictions),
        citations=citations_for(facts),
        confidence=1.0,
        evidence_kind="grounded_facts",
    )


def _process_attestation(
    rule: Rule, *, message: str, extra_reason: Mapping[str, Any]
) -> RuleEvaluation:
    return RuleEvaluation(
        rule_id=rule.rule_id,
        rule_version=rule.version,
        outcome="pass",
        severity="info",
        title=rule.title,
        message=message,
        reason=_base_reason(rule, evidence_kind="process_attestation", **dict(extra_reason)),
        fact_ids=(),
        contradiction_ids=(),
        citations=(),
        confidence=1.0,
        evidence_kind="process_attestation",
    )


def evaluate_required_assigned_owner(rule: Rule, view: UnderstandingView) -> RuleEvaluation:
    config = rule.configuration
    category = str(config["category"])
    subject_key = str(config["subject_key"])
    matches = supported_facts(view, category=category, subject_key=subject_key)
    conflicts = contradictions_for_category_subject(view, category, subject_key)
    if conflicts:
        item = conflicts[0]
        sides = paired_facts(view, item)
        return _grounded(
            rule,
            outcome="fail",
            message=(
                f"Grounded {subject_key} values conflict: "
                + " vs ".join(fact.normalized_value for fact in sides)
                + "."
            ),
            facts=sides,
            contradictions=(item,),
            extra_reason={
                "category": category,
                "subject_key": subject_key,
                "contradiction_type": item.contradiction_type,
            },
        )
    if not matches:
        return _unknown(rule, [f"{category}/{subject_key} supported fact"])
    unique: dict[str, GroundedFactView] = {}
    for fact in matches:
        unique.setdefault(comparison_key(fact.normalized_value), fact)
    if len(unique) > 1:
        values = [fact.normalized_value for fact in unique.values()]
        return _grounded(
            rule,
            outcome="fail",
            message=f"Grounded {subject_key} values conflict: " + " vs ".join(values) + ".",
            facts=tuple(unique.values()),
            extra_reason={"category": category, "subject_key": subject_key, "values": values},
        )
    fact = next(iter(unique.values()))
    if is_unassigned(fact.normalized_value):
        return _grounded(
            rule,
            outcome="fail",
            message=f"{subject_key} is grounded as unassigned.",
            facts=(fact,),
            extra_reason={
                "category": category,
                "subject_key": subject_key,
                "value": fact.normalized_value,
            },
        )
    return _grounded(
        rule,
        outcome="pass",
        message=f"{subject_key} is grounded as {fact.normalized_value}.",
        facts=(fact,),
        extra_reason={
            "category": category,
            "subject_key": subject_key,
            "value": fact.normalized_value,
        },
    )


def evaluate_mapped_supported_value(rule: Rule, view: UnderstandingView) -> RuleEvaluation:
    config = rule.configuration
    category = str(config["category"])
    subject_key = str(config["subject_key"])
    value_outcomes = {
        comparison_key(str(key)): str(value)
        for key, value in dict(config["value_outcomes"]).items()
    }
    unmapped_outcome = str(config.get("unmapped_outcome", "warning"))
    conflicts = contradictions_for_category_subject(view, category, subject_key)
    if conflicts:
        item = conflicts[0]
        sides = paired_facts(view, item)
        return _grounded(
            rule,
            outcome="fail",
            message=(
                f"Grounded {subject_key} values conflict: "
                + " vs ".join(fact.normalized_value for fact in sides)
                + "."
            ),
            facts=sides,
            contradictions=(item,),
            extra_reason={
                "category": category,
                "subject_key": subject_key,
                "contradiction_type": item.contradiction_type,
            },
        )
    matches = supported_facts(view, category=category, subject_key=subject_key)
    if not matches:
        return _unknown(rule, [f"{category}/{subject_key} supported fact"])
    fact = matches[0]
    mapped = value_outcomes.get(comparison_key(fact.normalized_value), unmapped_outcome)
    allowed: dict[str, Outcome] = {"pass": "pass", "fail": "fail", "warning": "warning"}
    outcome = allowed.get(mapped, "warning")
    return _grounded(
        rule,
        outcome=outcome,
        message=f"{subject_key} is grounded as {fact.normalized_value}.",
        facts=(fact,),
        extra_reason={
            "category": category,
            "subject_key": subject_key,
            "value": fact.normalized_value,
            "mapped": outcome,
        },
    )


def evaluate_subject_contradiction(rule: Rule, view: UnderstandingView) -> RuleEvaluation:
    category = expected_category(rule)
    subject_key = str(rule.configuration["subject_key"])
    conflicts = contradictions_for_category_subject(view, category, subject_key)
    matches = supported_facts(view, category=category, subject_key=subject_key)
    if conflicts:
        item = conflicts[0]
        sides = paired_facts(view, item)
        return _grounded(
            rule,
            outcome="fail",
            message=(
                f"Grounded facts disagree on {subject_key}: "
                + " vs ".join(fact.normalized_value for fact in sides)
                + "."
            ),
            facts=sides,
            contradictions=(item,),
            extra_reason={
                "category": category,
                "subject_key": subject_key,
                "contradiction_type": item.contradiction_type,
            },
        )
    if not matches:
        return _unknown(rule, [f"{category}/{subject_key} supported fact"])
    unique: dict[str, GroundedFactView] = {}
    for fact in matches:
        unique.setdefault(comparison_key(fact.normalized_value), fact)
    fact = next(iter(unique.values()))
    return _grounded(
        rule,
        outcome="pass",
        message=f"{subject_key} is grounded as {fact.normalized_value} without contradiction.",
        facts=(fact,),
        extra_reason={
            "category": category,
            "subject_key": subject_key,
            "value": fact.normalized_value,
        },
    )


def evaluate_open_contradictions(
    rule: Rule,
    view: UnderstandingView,
    consumed: Collection[str] = (),
) -> RuleEvaluation:
    consumed_ids = set(consumed)
    remaining = tuple(
        item
        for item in view.contradictions
        if item.status == "open" and item.id not in consumed_ids
    )
    if remaining:
        facts_by_seen: dict[str, GroundedFactView] = {}
        for item in remaining:
            for fact in paired_facts(view, item):
                facts_by_seen.setdefault(fact.id, fact)
        return _grounded(
            rule,
            outcome="fail",
            message=remaining[0].reason,
            facts=tuple(facts_by_seen.values()),
            contradictions=remaining,
            extra_reason={
                "open_contradiction_count": len(remaining),
                "consumed_contradiction_count": len(consumed_ids),
                "contradiction_type": remaining[0].contradiction_type,
            },
        )
    if view.contradiction_detection_attested:
        return _process_attestation(
            rule,
            message=(
                "Contradiction detection completed with no remaining unconsumed "
                "open grounded contradictions."
            ),
            extra_reason={
                "attestation_stage": "detect_contradictions",
                "open_contradiction_count": 0,
                "consumed_contradiction_count": len(consumed_ids),
            },
        )
    return _unknown(
        rule,
        ["completed detect_contradictions attestation with zero remaining contradictions"],
    )


def evaluate_required_supported_category(rule: Rule, view: UnderstandingView) -> RuleEvaluation:
    categories = tuple(str(item) for item in list(rule.configuration["categories"]))
    matches = tuple(fact for fact in supported_facts(view) if fact.category in set(categories))
    if not matches:
        missing = [f"supported fact in category {category}" for category in categories]
        return _unknown(rule, missing)
    labels = ", ".join(sorted({f"{fact.category}/{fact.subject_key}" for fact in matches}))
    return _grounded(
        rule,
        outcome="pass",
        message=f"Supported evidence is present for {labels}.",
        facts=matches,
        extra_reason={
            "categories": list(categories),
            "subjects": [fact.subject_key for fact in matches],
        },
    )


EVALUATORS = {
    "required_assigned_owner": evaluate_required_assigned_owner,
    "mapped_supported_value": evaluate_mapped_supported_value,
    "subject_contradiction": evaluate_subject_contradiction,
    "open_contradictions": evaluate_open_contradictions,
    "required_supported_category": evaluate_required_supported_category,
}
