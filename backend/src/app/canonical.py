"""Deterministic canonical serialization for incremental unchanged-byte proof.

This contract is independent of ORM identity and mutable metadata. Equality of
canonical hashes proves that reusable business content was preserved exactly.
It does not by itself prove that a full rerun was avoided.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from typing import Any
from uuid import UUID

CANONICAL_SERIALIZATION_VERSION = "incremental-artifact.v1"


def canonical_dumps(value: object) -> str:
    """UTF-8 JSON with sorted keys, compact separators, and no NaN."""

    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=str,
    )


def canonical_bytes(value: object) -> bytes:
    return canonical_dumps(value).encode("utf-8")


def canonical_hash(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _citation_payload(citation: dict[str, Any] | None) -> dict[str, object] | None:
    if citation is None:
        return None
    source_sha = citation.get("source_sha256") or citation.get("sha256")
    source_version_id = citation.get("source_version_id")
    exact_quote = citation.get("exact_quote")
    native_locator = citation.get("native_locator")
    declared_format = citation.get("format")
    if (
        source_sha is None
        or source_version_id is None
        or exact_quote is None
        or native_locator is None
        or declared_format is None
    ):
        return None
    try:
        return {
            "exact_quote": str(exact_quote),
            "format": str(declared_format),
            "native_locator": str(native_locator),
            "normalized_end": int(citation["normalized_end"]),
            "normalized_start": int(citation["normalized_start"]),
            "source_sha256": str(source_sha),
            "source_version_id": str(source_version_id),
        }
    except (KeyError, TypeError, ValueError):
        return None


def fact_canonical_payload(
    *,
    category: str,
    subject_key: str,
    normalized_value: str,
    confidence: float,
    support_status: str,
    rejection_reason: str | None,
    citation: dict[str, Any] | None,
    source_block_id: UUID | str | None,
) -> dict[str, object]:
    """Business fields for a fact. Excludes id, run_id, and timestamps."""

    return {
        "category": category,
        "citation": _citation_payload(citation),
        "confidence": confidence,
        "kind": "fact",
        "normalized_value": normalized_value,
        "rejection_reason": rejection_reason,
        "serialization_version": CANONICAL_SERIALIZATION_VERSION,
        "source_block_id": str(source_block_id) if source_block_id is not None else None,
        "subject_key": subject_key,
        "support_status": support_status,
    }


def contradiction_canonical_payload(
    *,
    contradiction_type: str,
    reason: str,
    status: str,
    fact_a: dict[str, object],
    fact_b: dict[str, object],
) -> dict[str, object]:
    """Business fields for a contradiction. Fact IDs are replaced by payloads."""

    left, right = fact_a, fact_b
    if canonical_dumps(left) > canonical_dumps(right):
        left, right = right, left
    return {
        "contradiction_type": contradiction_type,
        "fact_a": left,
        "fact_b": right,
        "kind": "contradiction",
        "reason": reason,
        "serialization_version": CANONICAL_SERIALIZATION_VERSION,
        "status": status,
    }


def finding_canonical_payload(
    *,
    rule_id: str,
    rule_version: str,
    outcome: str,
    severity: str,
    title: str,
    message: str,
    structured_reason: dict[str, Any],
    evidence_kind: str,
    confidence: float,
    fact_hashes: list[str],
    contradiction_hashes: list[str],
) -> dict[str, object]:
    """Business fields for a finding. Run IDs, finding IDs, and timestamps excluded."""

    return {
        "confidence": confidence,
        "contradiction_canonical_hashes": sorted(contradiction_hashes),
        "evidence_kind": evidence_kind,
        "fact_canonical_hashes": sorted(fact_hashes),
        "kind": "finding",
        "message": message,
        "outcome": outcome,
        "rule_id": rule_id,
        "rule_version": rule_version,
        "serialization_version": CANONICAL_SERIALIZATION_VERSION,
        "severity": severity,
        "structured_reason": dict(structured_reason),
        "title": title,
    }


def review_item_canonical_payload(
    *,
    rule_id: str,
    rule_version: str,
    outcome: str,
    severity: str,
    title: str,
    message: str,
    structured_reason: dict[str, Any],
    evidence_kind: str,
    fact_hashes: list[str],
    contradiction_hashes: list[str],
    citations: Sequence[dict[str, Any] | None] | None,
    review_required: bool,
) -> dict[str, object]:
    """Business fields for a review proposal.

    Session/item IDs, timestamps, and current decision state are excluded.
    """

    citation_identities = [
        payload
        for citation in citations or ()
        if (payload := _citation_payload(citation if isinstance(citation, dict) else None))
        is not None
    ]
    citation_identities.sort(key=canonical_dumps)
    return {
        "citation_identities": citation_identities,
        "contradiction_canonical_hashes": sorted(contradiction_hashes),
        "evidence_kind": evidence_kind,
        "fact_canonical_hashes": sorted(fact_hashes),
        "kind": "review_item",
        "message": message,
        "outcome": outcome,
        "review_required": review_required,
        "rule_id": rule_id,
        "rule_version": rule_version,
        "serialization_version": CANONICAL_SERIALIZATION_VERSION,
        "severity": severity,
        "structured_reason": dict(structured_reason),
        "title": title,
    }
