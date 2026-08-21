from pathlib import Path

import httpx
import pytest
from helpers import fixture_upload, prepare_incremental_corpus

from app.main import create_app
from app.services import Phase02Service
from app.storage import LocalFileStorage


@pytest.mark.integration
async def test_incremental_api_and_cross_corpus_isolation(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
    tmp_path: Path,
) -> None:
    phase02, _storage = phase02_service
    aurora, incremental = await prepare_incremental_corpus(
        phase02, corpus_fixtures / "aurora-control-hub"
    )
    harbor, _harbor_inc = await prepare_incremental_corpus(
        phase02, corpus_fixtures / "harbor-ledger-modernization"
    )
    application = create_app(
        phase02_service=phase02,
        understand_service=incremental.understand,
        examine_service=incremental.examine,
        review_service=incremental.review,
        incremental_service=incremental,
    )
    transport = httpx.ASGITransport(app=application)
    async with (
        application.router.lifespan_context(application),
        httpx.AsyncClient(transport=transport, base_url="http://test") as client,
    ):
        current = await client.get(f"/corpora/{aurora.id}/revisions/current")
        assert current.status_code == 200
        baseline_id = current.json()["id"]
        changed = tmp_path / "decision-log.txt"
        source = (corpus_fixtures / "aurora-control-hub" / "decision-log.txt").read_text(
            encoding="utf-8"
        )
        changed.write_text(source.replace("2026-10-30", "2026-12-01"), encoding="utf-8")
        await phase02.ingest(
            corpus_id=aurora.id,
            logical_name="Decision Log",
            declared_format="txt",
            upload=fixture_upload(changed, "txt"),
        )
        created = await client.post(
            f"/corpora/{aurora.id}/incremental-runs",
            json={"baseline_revision_id": baseline_id},
        )
        assert created.status_code == 201
        run = created.json()
        run_id = run["id"]
        fetched = await client.get(f"/corpora/{aurora.id}/incremental-runs/{run_id}")
        assert fetched.status_code == 200
        impact = await client.get(f"/corpora/{aurora.id}/incremental-runs/{run_id}/impact")
        assert impact.status_code == 200
        assert impact.json()["impact"]["change_kind"] == "changed"
        evidence = await client.get(f"/corpora/{aurora.id}/incremental-runs/{run_id}/evidence")
        assert evidence.status_code == 200
        assert evidence.json()["evidence"]["full_rerun"] is False
        isolated = await client.get(f"/corpora/{harbor.id}/incremental-runs/{run_id}")
        assert isolated.status_code == 404
        assert isolated.json()["code"] == "incremental_run_not_found"
        stale = await client.post(
            f"/corpora/{aurora.id}/incremental-runs",
            json={"baseline_revision_id": baseline_id},
        )
        assert stale.status_code == 409
        assert stale.json()["code"] == "stale_baseline"
