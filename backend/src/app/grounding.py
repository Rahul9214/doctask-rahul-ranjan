"""Deterministic assertion-to-evidence validation. Not an LLM and not vector search."""

from __future__ import annotations

from uuid import UUID

from app.taxonomy import INJECTION_PATTERN, derive_assertions, values_equivalent

UNTRUSTED_CATEGORY = "untrusted_instruction"


def values_match(left: str, right: str) -> bool:
    return values_equivalent(left, right)


def contains_untrusted_instruction(evidence: str) -> bool:
    return INJECTION_PATTERN.search(evidence) is not None


def validate_assertion(
    *,
    category: str,
    subject_key: str,
    normalized_value: str,
    proposed_source_block_id: UUID | None,
    evidence_text: str,
    resolved_block_id: UUID,
    untrusted_block_ids: set[UUID],
) -> str | None:
    """Return a safe reason code when the assertion is not grounded; otherwise None."""
    if proposed_source_block_id is not None and proposed_source_block_id != resolved_block_id:
        return "source_block_mismatch"
    if resolved_block_id in untrusted_block_ids or contains_untrusted_instruction(evidence_text):
        return "untrusted_instruction"
    derived = derive_assertions(evidence_text)
    matching_subject = [
        item for item in derived if item.category == category and item.subject_key == subject_key
    ]
    if any(values_match(item.normalized_value, normalized_value) for item in matching_subject):
        return None
    if any(
        item.subject_key == subject_key and values_match(item.normalized_value, normalized_value)
        for item in derived
    ):
        return "category_mismatch"
    if any(
        item.category == category and values_match(item.normalized_value, normalized_value)
        for item in derived
    ):
        return "subject_key_mismatch"
    if matching_subject:
        return "normalized_value_mismatch"
    return "assertion_not_supported"
