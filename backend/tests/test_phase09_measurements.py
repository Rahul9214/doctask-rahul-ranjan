from __future__ import annotations

import json
import os
import platform
import time
from pathlib import Path
from typing import Any

import pytest
from helpers import (
    CountingModelAdapter,
    complete_required_review,
    ingest_text,
    make_incremental,
    make_workflow,
)

from app.phase09_measurements import (
    DEFAULT_PATH,
    build_record,
    invariant_fields,
    validate_record,
    write_record,
)
from app.services import Phase02Service
from app.storage import LocalFileStorage

MEASUREMENT_PATH = (
    Path(__file__).resolve().parents[2] / "docs" / "measurements" / "phase-09-local.json"
)


def _sample_record(
    os_name: str,
    platform_name: str,
    *,
    baseline_seconds: list[float],
    review_resume_seconds: list[float],
    incremental_seconds: list[float],
) -> dict[str, Any]:
    return build_record(
        os_name=os_name,
        platform_name=platform_name,
        database="project_assurance_test",
        baseline_seconds=baseline_seconds,
        review_resume_seconds=review_resume_seconds,
        incremental_seconds=incremental_seconds,
        baseline_ops=2,
        incremental_ops=2,
        avoided_ops=2,
    )


def test_invariant_fields_ignore_os_platform_and_timings() -> None:
    windows = _sample_record(
        "nt",
        "windows",
        baseline_seconds=[3.818553700000848],
        review_resume_seconds=[1.53495760000078],
        incremental_seconds=[1.443162099998517],
    )
    linux = _sample_record(
        "posix",
        "linux",
        baseline_seconds=[0.4],
        review_resume_seconds=[0.2],
        incremental_seconds=[0.3],
    )
    validate_record(windows)
    validate_record(linux)
    assert windows["environment"]["os"] == "nt"
    assert windows["environment"]["platform"] == "windows"
    assert linux["environment"]["os"] == "posix"
    assert linux["environment"]["platform"] == "linux"
    windows_invariants = invariant_fields(windows)
    linux_invariants = invariant_fields(linux)
    assert windows_invariants == linux_invariants
    assert "environment_os" not in windows_invariants
    assert "environment_platform" not in windows_invariants
    assert windows_invariants["model_provider"] == "deterministic"
    assert windows_invariants["database"] == "project_assurance_test"
    assert windows_invariants["logical_model_operations"] == linux["logical_model_operations"]


def test_validate_record_still_requires_os_and_platform() -> None:
    record = _sample_record(
        "nt",
        "windows",
        baseline_seconds=[1.0],
        review_resume_seconds=[1.0],
        incremental_seconds=[1.0],
    )
    del record["environment"]["os"]
    with pytest.raises(ValueError, match="environment missing os"):
        validate_record(record)
    record["environment"]["os"] = "nt"
    del record["environment"]["platform"]
    with pytest.raises(ValueError, match="environment missing platform"):
        validate_record(record)


@pytest.mark.integration
async def test_phase09_local_measurements_are_deterministic_and_zero_cost(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
) -> None:
    phase02, _storage = phase02_service
    adapter = CountingModelAdapter()
    corpus = await phase02.create_corpus(
        name="Measurement Mini",
        domain="software-project-assurance",
        declared_formats=["txt"],
    )
    await ingest_text(
        phase02,
        corpus.id,
        "Plan A",
        "Project sponsor: Elena Marlow\n\nProduction readiness milestone: 2026-10-30",
    )
    await ingest_text(
        phase02,
        corpus.id,
        "Plan B",
        "Overall status is GREEN.\n\nProduction readiness baseline at 2026-11-14",
    )
    workflow = make_workflow(phase02, adapter)
    started = time.perf_counter()
    run = await workflow.create_run(corpus.id)
    baseline_seconds = time.perf_counter() - started
    assert run.status == "waiting_for_review"
    assert run.analysis_run_id is not None
    assert run.examination_run_id is not None
    assert run.review_session_id is not None
    baseline_ops = adapter.classify_operations + adapter.extract_operations

    review = workflow.review
    complete_started = time.perf_counter()
    await complete_required_review(review, corpus.id, run.review_session_id)
    resumed = await workflow.resume_run(corpus.id, run.id)
    review_resume_seconds = time.perf_counter() - complete_started
    assert resumed.status == "completed"

    incremental = make_incremental(phase02, adapter, review=review)
    await incremental.create_baseline_revision(
        corpus.id,
        analysis_run_id=run.analysis_run_id,
        examination_run_id=run.examination_run_id,
        review_session_id=run.review_session_id,
    )
    await ingest_text(
        phase02,
        corpus.id,
        "Plan A",
        "Project sponsor: Elena Marlow\n\nProduction readiness milestone: 2026-12-01",
        filename="plan-a-changed.txt",
    )
    inc_started = time.perf_counter()
    incremental_run = await incremental.create_run(corpus.id)
    incremental_seconds = time.perf_counter() - inc_started
    assert incremental_run.status == "completed"
    incremental_ops = (adapter.classify_operations + adapter.extract_operations) - baseline_ops
    evidence = await incremental.get_evidence(corpus.id, incremental_run.id)
    payload = evidence["evidence"]
    assert isinstance(payload, dict)
    assert payload["full_rerun"] is False
    avoided = len(payload["classify_skipped_source_version_ids"]) + len(
        payload["extract_skipped_source_version_ids"]
    )
    assert incremental_run.measurement["estimated_cost_usd"] == 0.0

    record = build_record(
        os_name=os.name,
        platform_name=platform.system().casefold() or os.name,
        database="project_assurance_test",
        baseline_seconds=[baseline_seconds],
        review_resume_seconds=[review_resume_seconds],
        incremental_seconds=[incremental_seconds],
        baseline_ops=baseline_ops,
        incremental_ops=incremental_ops,
        avoided_ops=avoided,
    )
    validate_record(record)
    if os.environ.get("WRITE_PHASE09_MEASUREMENTS") == "1":
        written = write_record(record, MEASUREMENT_PATH)
        assert written in {DEFAULT_PATH, MEASUREMENT_PATH}
    assert MEASUREMENT_PATH.exists()
    committed = json.loads(MEASUREMENT_PATH.read_text(encoding="utf-8"))
    validate_record(committed)
    assert invariant_fields(record) == invariant_fields(committed)
    for label, generated in record["operations"].items():
        stored = committed["operations"][label]
        assert stored["sample_count"] == generated["sample_count"]
        assert stored["units"] == generated["units"]
        assert isinstance(stored["raw_seconds"], list)
        assert all(isinstance(value, int | float) for value in stored["raw_seconds"])
