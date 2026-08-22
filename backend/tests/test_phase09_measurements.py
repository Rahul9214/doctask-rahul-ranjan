from __future__ import annotations

import json
import os
import platform
import time
from pathlib import Path

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
