from pathlib import Path

import pytest
from helpers import make_watcher, prepare_incremental_corpus

from app.services import Phase02Service
from app.storage import LocalFileStorage
from app.watcher import WatcherService


@pytest.mark.integration
async def test_watcher_stable_polling_duplicate_suppression_and_restart(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
    tmp_path: Path,
) -> None:
    phase02, _storage = phase02_service
    corpus, incremental = await prepare_incremental_corpus(
        phase02, corpus_fixtures / "aurora-control-hub"
    )
    inbox = tmp_path / "inbox"
    target_dir = inbox / str(corpus.id)
    target_dir.mkdir(parents=True)
    watcher = make_watcher(phase02, inbox, incremental=incremental, stable_polls=2)
    original = (corpus_fixtures / "aurora-control-hub" / "decision-log.txt").read_bytes()
    changed_text = (
        (corpus_fixtures / "aurora-control-hub" / "decision-log.txt")
        .read_text(encoding="utf-8")
        .replace("2026-10-30", "2026-12-01")
    )
    target = target_dir / "Decision Log.txt"

    target.write_bytes(original[:20])
    first = await watcher.poll_once()
    assert first.ingested == 0
    assert first.triggered == 0
    assert any(event.status == "observing" for event in first.events)

    target.write_text(changed_text, encoding="utf-8")
    second = await watcher.poll_once()
    assert second.triggered == 0
    third = await watcher.poll_once()
    assert third.ingested == 1
    assert third.triggered == 1
    ingested_id = next(
        event.incremental_run_id for event in third.events if event.incremental_run_id
    )
    fourth = await watcher.poll_once()
    assert fourth.unchanged >= 1
    assert fourth.triggered == 0

    restarted = WatcherService(
        phase02.session_factory,
        phase02,
        incremental,
        inbox_path=inbox,
        poll_seconds=0.01,
        stable_polls=2,
    )
    after_restart = await restarted.poll_once()
    assert after_restart.triggered == 0
    assert any(event.status == "unchanged" for event in after_restart.events)

    target.write_text(changed_text.replace("2026-12-01", "2026-12-15"), encoding="utf-8")
    fifth = await restarted.poll_once()
    sixth = await restarted.poll_once()
    assert fifth.triggered == 0
    assert sixth.triggered == 1
    assert sixth.ingested == 1
    new_id = next(event.incremental_run_id for event in sixth.events if event.incremental_run_id)
    assert new_id != ingested_id

    duplicate = await restarted.poll_once()
    assert duplicate.triggered == 0


@pytest.mark.integration
async def test_watcher_retries_incremental_after_ingest_without_new_version(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
    tmp_path: Path,
) -> None:
    phase02, _storage = phase02_service
    corpus, incremental = await prepare_incremental_corpus(
        phase02, corpus_fixtures / "aurora-control-hub"
    )
    inbox = tmp_path / "inbox"
    target_dir = inbox / str(corpus.id)
    target_dir.mkdir(parents=True)
    watcher = make_watcher(phase02, inbox, incremental=incremental, stable_polls=2)
    changed_text = (
        (corpus_fixtures / "aurora-control-hub" / "decision-log.txt")
        .read_text(encoding="utf-8")
        .replace("2026-10-30", "2026-12-01")
    )
    target = target_dir / "Decision Log.txt"
    target.write_text(changed_text, encoding="utf-8")
    await watcher.poll_once()
    incremental.fail_before_finalize = True
    second = await watcher.poll_once()
    incremental.fail_before_finalize = False
    assert any(event.status == "failed_retryable" for event in second.events)
    retry = await watcher.poll_once()
    assert retry.triggered == 1
    assert any(event.status == "completed" for event in retry.events)
    again = await watcher.poll_once()
    assert again.triggered == 0
    assert any(event.status == "unchanged" for event in again.events)


@pytest.mark.integration
async def test_watcher_rejects_malformed_empty_and_missing_files(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
    tmp_path: Path,
) -> None:
    phase02, _storage = phase02_service
    corpus, incremental = await prepare_incremental_corpus(
        phase02, corpus_fixtures / "aurora-control-hub"
    )
    inbox = tmp_path / "inbox"
    target_dir = inbox / str(corpus.id)
    target_dir.mkdir(parents=True)
    watcher = make_watcher(phase02, inbox, incremental=incremental, stable_polls=2)

    malformed = target_dir / "Decision Log.bin"
    malformed.write_bytes(b"not-a-supported-source")
    first = await watcher.poll_once()
    assert first.ingested == 0
    second = await watcher.poll_once()
    assert any(event.error_code == "watcher_format_unsupported" for event in second.events)

    empty = target_dir / "Empty Note.txt"
    empty.write_bytes(b"")
    empty_poll = await watcher.poll_once()
    assert any(event.error_code == "empty_upload" for event in empty_poll.events)

    oversized_watcher = WatcherService(
        phase02.session_factory,
        phase02,
        incremental,
        inbox_path=inbox,
        poll_seconds=0.01,
        stable_polls=2,
        max_upload_bytes=16,
    )
    too_large = target_dir / "Too Large.txt"
    too_large.write_text("this file is larger than sixteen bytes\n", encoding="utf-8")
    large_poll = await oversized_watcher.poll_once()
    assert any(event.error_code == "upload_too_large" for event in large_poll.events)

    disappearing = target_dir / "Temporary.txt"
    disappearing.write_text("temporary note\n", encoding="utf-8")
    observing = await watcher.poll_once()
    assert any(event.status == "observing" for event in observing.events)
    disappearing.unlink()
    missing = await watcher.poll_once()
    assert any(event.status == "missing" for event in missing.events)
