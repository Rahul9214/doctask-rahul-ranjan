import asyncio
from pathlib import Path

import pytest
from helpers import fixture_upload, prepare_incremental_corpus

from app.services import Phase02Service
from app.storage import LocalFileStorage


@pytest.mark.integration
async def test_concurrent_incremental_runs_from_same_baseline_serialize(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
    tmp_path: Path,
) -> None:
    phase02, _storage = phase02_service
    corpus, incremental = await prepare_incremental_corpus(
        phase02, corpus_fixtures / "aurora-control-hub"
    )
    baseline = await incremental.get_current_revision(corpus.id)
    changed = tmp_path / "decision-log.txt"
    original = (corpus_fixtures / "aurora-control-hub" / "decision-log.txt").read_text(
        encoding="utf-8"
    )
    changed.write_text(original.replace("2026-10-30", "2026-12-01"), encoding="utf-8")
    await phase02.ingest(
        corpus_id=corpus.id,
        logical_name="Decision Log",
        declared_format="txt",
        upload=fixture_upload(changed, "txt"),
    )

    first, second = await asyncio.gather(
        incremental.create_run(corpus.id, baseline_revision_id=baseline.id),
        incremental.create_run(corpus.id, baseline_revision_id=baseline.id),
    )
    statuses = {first.status, second.status}
    assert "completed" in statuses
    assert "stale_baseline" in statuses
    winner = first if first.status == "completed" else second
    loser = second if first.status == "completed" else first
    assert winner.result_revision_id is not None
    assert loser.result_revision_id is None
    assert loser.error_code == "stale_baseline"
    current = await incremental.get_current_revision(corpus.id)
    assert current.id == winner.result_revision_id
    assert current.revision_number == baseline.revision_number + 1
    stale = await incremental.create_run(corpus.id, baseline_revision_id=baseline.id)
    assert stale.status == "stale_baseline"
    assert stale.impact["requested_baseline_revision_id"] == str(baseline.id)
    assert stale.evidence["mixed_base"] is False
