"""Canonical Phase 09 local-measurement record shape. Not a production SLA."""

from __future__ import annotations

import json
from pathlib import Path
from statistics import median
from typing import Any

SCHEMA = "phase-09-measurements.v1"
PHASE = "Phase 09 — Hardening"
UNITS = "seconds"
DISCLAIMER = "Recorded local sample. Not a production SLA."
DEFAULT_PATH = Path(__file__).resolve().parents[3] / "docs" / "measurements" / "phase-09-local.json"

OPERATION_LABELS = (
    "baseline_workflow_waiting_for_review",
    "review_complete_and_resume",
    "incremental_one_source_update",
)


def summarize_seconds(values: list[float]) -> dict[str, Any]:
    ordered = sorted(values)
    return {
        "sample_count": len(ordered),
        "units": UNITS,
        "raw_seconds": ordered,
        "median_seconds": median(ordered) if ordered else None,
        "min_seconds": ordered[0] if ordered else None,
        "max_seconds": ordered[-1] if ordered else None,
    }


def build_record(
    *,
    os_name: str,
    platform_name: str,
    database: str,
    baseline_seconds: list[float],
    review_resume_seconds: list[float],
    incremental_seconds: list[float],
    baseline_ops: int,
    incremental_ops: int,
    avoided_ops: int,
) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "phase": PHASE,
        "disclaimer": DISCLAIMER,
        "units": UNITS,
        "sample_count": 1,
        "environment": {
            "os": os_name,
            "platform": platform_name,
            "model_provider": "deterministic",
            "database": database,
            "note": DISCLAIMER,
        },
        "deterministic_external_cost_usd": 0,
        "operations": {
            "baseline_workflow_waiting_for_review": summarize_seconds(baseline_seconds),
            "review_complete_and_resume": summarize_seconds(review_resume_seconds),
            "incremental_one_source_update": summarize_seconds(incremental_seconds),
        },
        "logical_model_operations": {
            "baseline": baseline_ops,
            "incremental_additional": incremental_ops,
            "operations_avoided_by_skipped_classify_extract": avoided_ops,
        },
    }


def invariant_fields(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": record["schema"],
        "phase": record["phase"],
        "disclaimer": record["disclaimer"],
        "units": record["units"],
        "sample_count": record["sample_count"],
        "model_provider": record["environment"]["model_provider"],
        "database": record["environment"]["database"],
        "environment_note": record["environment"]["note"],
        "deterministic_external_cost_usd": record["deterministic_external_cost_usd"],
        "operation_labels": list(record["operations"]),
        "logical_model_operations": record["logical_model_operations"],
        "operation_sample_counts": {
            label: record["operations"][label]["sample_count"] for label in OPERATION_LABELS
        },
        "operation_units": {
            label: record["operations"][label]["units"] for label in OPERATION_LABELS
        },
    }


def validate_record(record: dict[str, Any]) -> None:
    required = {
        "schema",
        "phase",
        "disclaimer",
        "units",
        "sample_count",
        "environment",
        "deterministic_external_cost_usd",
        "operations",
        "logical_model_operations",
    }
    missing = required - set(record)
    if missing:
        raise ValueError(f"measurement record missing fields: {sorted(missing)}")
    if record["schema"] != SCHEMA:
        raise ValueError("unexpected measurement schema")
    if record["phase"] != PHASE:
        raise ValueError("unexpected measurement phase")
    if record["disclaimer"] != DISCLAIMER:
        raise ValueError("unexpected measurement disclaimer")
    if record["units"] != UNITS:
        raise ValueError("unexpected measurement units")
    if record["sample_count"] != 1:
        raise ValueError("measurement sample_count must be 1")
    if record["deterministic_external_cost_usd"] != 0:
        raise ValueError("deterministic external cost must be 0")
    env = record["environment"]
    for key in ("os", "platform", "model_provider", "database", "note"):
        if key not in env:
            raise ValueError(f"measurement environment missing {key}")
    if env["model_provider"] != "deterministic":
        raise ValueError("measurement provider must be deterministic")
    operations = record["operations"]
    if tuple(operations) != OPERATION_LABELS:
        raise ValueError("measurement operation labels drifted")
    for label in OPERATION_LABELS:
        item = operations[label]
        for field in (
            "sample_count",
            "units",
            "raw_seconds",
            "median_seconds",
            "min_seconds",
            "max_seconds",
        ):
            if field not in item:
                raise ValueError(f"{label} missing {field}")
        if item["units"] != UNITS:
            raise ValueError(f"{label} units must be seconds")
        if item["sample_count"] < 1:
            raise ValueError(f"{label} sample_count must be at least 1")
    logical = record["logical_model_operations"]
    for key in (
        "baseline",
        "incremental_additional",
        "operations_avoided_by_skipped_classify_extract",
    ):
        if key not in logical:
            raise ValueError(f"logical_model_operations missing {key}")
        if int(logical[key]) < 1:
            raise ValueError(f"{key} must be at least 1")


def write_record(record: dict[str, Any], path: Path = DEFAULT_PATH) -> Path:
    validate_record(record)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return path
