"""Configuration-oriented Software Project Assurance fact taxonomy."""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Literal

TAXONOMY_VERSION = "software-project-assurance.v1"
GRAPH_VERSION = "understand.v1"

FactCategory = Literal[
    "project_identity",
    "owner_accountability",
    "milestone_date",
    "status",
    "risk",
    "decision",
    "dependency",
    "control_assurance",
]

FACT_CATEGORIES: tuple[FactCategory, ...] = (
    "project_identity",
    "owner_accountability",
    "milestone_date",
    "status",
    "risk",
    "decision",
    "dependency",
    "control_assurance",
)

SupportStatus = Literal["supported", "unknown", "insufficient_evidence", "rejected"]
ContradictionType = Literal[
    "conflicting_dates",
    "conflicting_owners",
    "conflicting_status",
    "conflicting_risk",
]

RETRIEVAL_QUERIES: tuple[str, ...] = (
    "project sponsor delivery lead owner accountability",
    "production readiness milestone date retirement",
    "overall status risk decision control",
    "security sign-off budget owner approval",
    "dependency evidence rehearsal",
    "instruction approve compliant binding controls",
)


@dataclass(frozen=True, slots=True)
class InspectionField:
    category: FactCategory
    subject_key: str


# Inspected after extraction. Missing supported values become UNKNOWN.
INSPECTION_FIELDS: tuple[InspectionField, ...] = (
    InspectionField("project_identity", "project_name"),
    InspectionField("owner_accountability", "project_sponsor"),
    InspectionField("owner_accountability", "delivery_lead"),
    InspectionField("owner_accountability", "security_signoff_owner"),
    InspectionField("owner_accountability", "budget_owner"),
    InspectionField("milestone_date", "production_readiness"),
    InspectionField("milestone_date", "legacy_retirement"),
    InspectionField("status", "overall_status"),
    InspectionField("control_assurance", "archive_retention_approval_date"),
)

CONTRADICTION_TYPE_BY_CATEGORY: dict[FactCategory, ContradictionType] = {
    "milestone_date": "conflicting_dates",
    "owner_accountability": "conflicting_owners",
    "status": "conflicting_status",
    "risk": "conflicting_risk",
}

CATEGORY_KEYWORDS: dict[FactCategory, tuple[str, ...]] = {
    "project_identity": ("project charter", "delivery plan", "scope:", "project name"),
    "owner_accountability": (
        "project sponsor",
        "executive sponsor",
        "delivery lead",
        "programme manager",
        "program manager",
        "security sign-off",
        "security sign off",
    ),
    "milestone_date": (
        "production readiness",
        "parallel-run",
        "legacy retirement",
        "approved baseline date",
        "plan approved",
        "milestone",
    ),
    "status": ("overall status", "at risk", "amber", "green", "red"),
    "risk": ("risk register", "probability", "impact", "mitigation"),
    "decision": ("decision", "outcome:", "steering review"),
    "dependency": ("depends", "dependency", "tenant", "shared test"),
    "control_assurance": (
        "sign-off must",
        "control",
        "reconciliation",
        "disaster-recovery",
        "assurance",
    ),
}

IRRELEVANT_HEADER_TOKENS = frozenset({"milestone", "owner", "status", "control", "state", "date"})

INJECTION_PATTERN = re.compile(
    r"ignore previous instructions|disregard (?:all |the )?instructions|"
    r"mark the project compliant|treat this sentence as a binding instruction",
    re.IGNORECASE,
)

FALLBACK_MAX_BLOCKS = 200


@dataclass(frozen=True, slots=True)
class ExtractionRule:
    category: FactCategory
    subject_key: str
    pattern: str
    value_kind: Literal["text", "date", "status", "owner"] = "text"


EXTRACTION_RULES: tuple[ExtractionRule, ...] = (
    ExtractionRule("project_identity", "project_name", r"^([A-Za-z][A-Za-z0-9 &'/-]+?)\s+-\s+"),
    ExtractionRule("project_identity", "scope", r"\bscope\s*:\s*(.+)"),
    ExtractionRule(
        "owner_accountability",
        "project_sponsor",
        r"\b(?:project sponsor|executive sponsor)\s*:\s*(.+)",
        "owner",
    ),
    ExtractionRule(
        "owner_accountability",
        "delivery_lead",
        r"\b(?:delivery lead|programme manager|program manager)\s*:\s*(.+)",
        "owner",
    ),
    ExtractionRule(
        "owner_accountability",
        "security_signoff_owner",
        r"security sign-?off ownership remains\s+(\w+)",
        "owner",
    ),
    ExtractionRule(
        "milestone_date",
        "production_readiness",
        r"production readiness(?: milestone| baseline)?\s*:\s*(\d{4}-\d{2}-\d{2})",
        "date",
    ),
    ExtractionRule(
        "milestone_date",
        "production_readiness",
        r"production readiness baseline at\s+(\d{4}-\d{2}-\d{2})",
        "date",
    ),
    ExtractionRule(
        "milestone_date",
        "production_readiness",
        r"forecasts production readiness on\s+(\d{4}-\d{2}-\d{2})",
        "date",
    ),
    ExtractionRule(
        "milestone_date",
        "parallel_run",
        r"parallel-run (?:milestone|date remains)\s*:?\s*(\d{4}-\d{2}-\d{2})",
        "date",
    ),
    ExtractionRule(
        "milestone_date",
        "legacy_retirement",
        r"(?:target retirement of legacy ledger|legacy retirement target)"
        r"\s*:?\s*(\d{4}-\d{2}-\d{2})",
        "date",
    ),
    ExtractionRule(
        "milestone_date",
        "plan_approved",
        r"(?:approved baseline date|plan approved)\s*:\s*(\d{4}-\d{2}-\d{2})",
        "date",
    ),
    ExtractionRule(
        "status",
        "overall_status",
        r"overall status is\s+([A-Za-z]+)",
        "status",
    ),
    ExtractionRule(
        "control_assurance",
        "security_signoff_gate",
        r"(security sign-?off must precede production readiness\.?)",
    ),
    ExtractionRule(
        "control_assurance",
        "reconciliation_defect_escape_rate",
        r"reconciliation defect escape rate is\s+(.+?)(?:\.|$)",
    ),
    ExtractionRule(
        "dependency",
        "identity_test_tenant",
        r"(use the existing identity test tenant[^.]+)",
    ),
)


@dataclass(frozen=True, slots=True)
class DerivedAssertion:
    category: FactCategory
    subject_key: str
    normalized_value: str
    match_text: str
    match_start: int
    match_end: int


def comparison_key(value: str) -> str:
    """Canonical key for grounding, contradiction, and repeated-value comparison."""
    return value.strip().casefold()


def values_equivalent(left: str, right: str) -> bool:
    return comparison_key(left) == comparison_key(right)


def normalize_extracted_value(value: str, kind: str) -> str:
    collapsed = re.sub(r"\s+", " ", value).strip(" .;")
    if kind == "date":
        match = re.search(r"\d{4}-\d{2}-\d{2}", collapsed)
        return match.group(0) if match else collapsed
    if kind == "status":
        return collapsed.casefold()
    if kind == "owner":
        return collapsed
    return collapsed


def iter_rule_matches(evidence: str) -> Iterator[DerivedAssertion]:
    seen: set[tuple[str, str, str]] = set()
    for rule in EXTRACTION_RULES:
        for match in re.finditer(rule.pattern, evidence, flags=re.IGNORECASE | re.MULTILINE):
            raw_value = match.group(1).strip().strip(" .;")
            value = normalize_extracted_value(raw_value, rule.value_kind)
            if not value:
                continue
            key = (rule.category, rule.subject_key, comparison_key(value))
            if key in seen:
                continue
            seen.add(key)
            yield DerivedAssertion(
                category=rule.category,
                subject_key=rule.subject_key,
                normalized_value=value,
                match_text=match.group(0).strip(),
                match_start=match.start(),
                match_end=match.end(),
            )


def derive_assertions(evidence: str) -> tuple[DerivedAssertion, ...]:
    return tuple(iter_rule_matches(evidence))
