"""Minimal stable-file inbox poller for incremental source arrivals."""

from __future__ import annotations

import asyncio
import hashlib
import io
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import UploadFile
from sqlalchemy import select
from starlette.datastructures import Headers

from app.config import Settings
from app.db import SessionFactory
from app.errors import NotFoundError, Phase02Error, ValidationError
from app.examine_graph import utcnow
from app.incremental_service import IncrementalFinalizeInjectedError, IncrementalService
from app.models import WatcherFile
from app.parsers import FORMAT_EXTENSIONS, FORMAT_MEDIA_TYPES, SourceFormat
from app.services import Phase02Service

_EXTENSION_FORMAT: dict[str, SourceFormat] = {
    extension: declared
    for declared, extensions in FORMAT_EXTENSIONS.items()
    for extension in extensions
}

_TERMINAL_WATCHER_CODES = frozenset(
    {
        "watcher_format_unsupported",
        "watcher_path_invalid",
        "watcher_corpus_invalid",
        "watcher_logical_name_invalid",
        "empty_upload",
        "upload_too_large",
    }
)


@dataclass(frozen=True, slots=True)
class WatcherPollEvent:
    relative_path: str
    status: str
    content_sha256: str | None
    incremental_run_id: UUID | None
    error_code: str | None


@dataclass(frozen=True, slots=True)
class WatcherPollResult:
    examined: int
    ingested: int
    unchanged: int
    triggered: int
    failed: int
    events: tuple[WatcherPollEvent, ...]


class WatcherService:
    def __init__(
        self,
        session_factory: SessionFactory,
        phase02: Phase02Service,
        incremental: IncrementalService,
        *,
        inbox_path: Path,
        poll_seconds: float = 2.0,
        stable_polls: int = 2,
        max_upload_bytes: int | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.phase02 = phase02
        self.incremental = incremental
        self.inbox_path = inbox_path.expanduser().resolve()
        self.poll_seconds = poll_seconds
        self.stable_polls = stable_polls
        self.max_upload_bytes = max_upload_bytes or 10 * 1024 * 1024
        self.inbox_path.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_settings(
        cls,
        session_factory: SessionFactory,
        phase02: Phase02Service,
        incremental: IncrementalService,
        settings: Settings,
    ) -> WatcherService | None:
        if settings.watch_input_path is None:
            return None
        return cls(
            session_factory,
            phase02,
            incremental,
            inbox_path=settings.watch_input_path,
            poll_seconds=settings.watch_poll_seconds,
            stable_polls=settings.watch_stable_polls,
            max_upload_bytes=settings.max_upload_bytes,
        )

    async def run_forever(self, stop: asyncio.Event | None = None) -> None:
        while stop is None or not stop.is_set():
            with suppress(Exception):
                await self.poll_once()
            if stop is None:
                await asyncio.sleep(self.poll_seconds)
                continue
            try:
                await asyncio.wait_for(stop.wait(), timeout=self.poll_seconds)
            except TimeoutError:
                continue

    async def poll_once(self) -> WatcherPollResult:
        events: list[WatcherPollEvent] = []
        present = self._list_inbox_files()
        present_rel = {relative for relative, _path in present}
        for relative, path in present:
            events.append(await self._observe_file(relative, path))
        async with self.session_factory() as session:
            tracked = list(
                await session.scalars(
                    select(WatcherFile).where(
                        WatcherFile.inbox_root == str(self.inbox_path),
                        WatcherFile.status != "missing",
                    )
                )
            )
        for row in tracked:
            if row.relative_path not in present_rel:
                events.append(await self._mark_missing(row))
        return WatcherPollResult(
            examined=len(events),
            ingested=sum(
                1
                for event in events
                if event.status in {"completed", "ingested_incremental_pending"}
            ),
            unchanged=sum(1 for event in events if event.status == "unchanged"),
            triggered=sum(1 for event in events if event.incremental_run_id is not None),
            failed=sum(
                1 for event in events if event.status in {"failed_retryable", "failed_terminal"}
            ),
            events=tuple(events),
        )

    def _list_inbox_files(self) -> list[tuple[str, Path]]:
        files: list[tuple[str, Path]] = []
        if not self.inbox_path.exists():
            return files
        for path in sorted(self.inbox_path.rglob("*")):
            if not path.is_file():
                continue
            if path.name.startswith("."):
                continue
            try:
                relative = path.resolve().relative_to(self.inbox_path).as_posix()
            except ValueError:
                continue
            if ".." in Path(relative).parts:
                continue
            files.append((relative, path))
        return files

    async def _observe_file(self, relative: str, path: Path) -> WatcherPollEvent:
        try:
            digest, byte_size = await asyncio.to_thread(self._hash_file, path)
        except ValidationError as error:
            return await self._fail(relative, error.code, error.detail, content_sha256=None)
        row = await self._row_for(relative)
        now = utcnow()
        if row is not None and row.content_sha256 == digest and row.byte_size == byte_size:
            if row.status in {"completed", "unchanged"}:
                row.last_seen_at = now
                row.updated_at = now
                await self._save(row)
                return WatcherPollEvent(relative, "unchanged", digest, None, None)
            if row.status in {
                "ingested_incremental_pending",
                "processing_incremental",
                "failed_retryable",
            }:
                return await self._retry_incremental(row)
            if row.status == "failed_terminal":
                row.last_seen_at = now
                row.updated_at = now
                await self._save(row)
                return WatcherPollEvent(relative, "failed_terminal", digest, None, row.error_code)
        if row is None:
            row = WatcherFile(
                id=uuid4(),
                inbox_root=str(self.inbox_path),
                relative_path=relative,
                content_sha256=digest,
                byte_size=byte_size,
                stable_poll_count=1,
                status="observing",
                last_seen_at=now,
                updated_at=now,
            )
        elif row.content_sha256 == digest and row.byte_size == byte_size:
            row.stable_poll_count += 1
            row.last_seen_at = now
            row.updated_at = now
            if row.stable_poll_count >= self.stable_polls:
                row.status = "stable"
        else:
            row.content_sha256 = digest
            row.byte_size = byte_size
            row.stable_poll_count = 1
            row.status = "observing"
            row.error_code = None
            row.error_detail = None
            row.last_seen_at = now
            row.updated_at = now
        await self._save(row)
        if row.status != "stable":
            return WatcherPollEvent(relative, row.status, digest, None, None)
        return await self._ingest_stable(row, path, digest)

    async def _ingest_stable(self, row: WatcherFile, path: Path, digest: str) -> WatcherPollEvent:
        try:
            corpus_id, logical_name, declared_format = _parse_inbox_path(row.relative_path)
        except ValidationError as error:
            return await self._fail(row.relative_path, error.code, error.detail, digest)
        try:
            await self.phase02.get_corpus(corpus_id)
        except NotFoundError as error:
            return await self._fail(row.relative_path, error.code, error.detail, digest)
        data = await asyncio.to_thread(path.read_bytes)
        if hashlib.sha256(data).hexdigest() != digest:
            row.status = "observing"
            row.stable_poll_count = 1
            row.updated_at = utcnow()
            await self._save(row)
            return WatcherPollEvent(row.relative_path, "observing", digest, None, None)
        media_type = sorted(FORMAT_MEDIA_TYPES[declared_format])[0]
        upload = UploadFile(
            io.BytesIO(data),
            filename=path.name,
            headers=Headers({"content-type": media_type}),
        )
        try:
            result = await self.phase02.ingest(
                corpus_id=corpus_id,
                logical_name=logical_name,
                declared_format=declared_format,
                upload=upload,
            )
        except Phase02Error as error:
            return await self._fail(row.relative_path, error.code, error.detail, digest)
        finally:
            await upload.close()
        row.corpus_id = corpus_id
        row.logical_name = logical_name
        row.declared_format = declared_format
        row.content_sha256 = digest
        row.processed_at = utcnow()
        row.updated_at = utcnow()
        row.error_code = None
        row.error_detail = None
        if result.duplicate and row.status in {
            "ingested_incremental_pending",
            "failed_retryable",
            "processing_incremental",
        }:
            return await self._retry_incremental(row)
        row.status = "ingested_incremental_pending"
        await self._save(row)
        return await self._run_incremental(row)

    async def _retry_incremental(self, row: WatcherFile) -> WatcherPollEvent:
        if row.corpus_id is None:
            return await self._fail(
                row.relative_path,
                "watcher_corpus_invalid",
                "Pending incremental recovery is missing a corpus identifier.",
                row.content_sha256,
                terminal=True,
            )
        return await self._run_incremental(row)

    async def _run_incremental(self, row: WatcherFile) -> WatcherPollEvent:
        assert row.corpus_id is not None
        row.status = "processing_incremental"
        row.updated_at = utcnow()
        await self._save(row)
        try:
            incremental = await self.incremental.create_run(row.corpus_id)
        except IncrementalFinalizeInjectedError:
            row.status = "failed_retryable"
            row.error_code = "incremental_finalize_injected_failure"
            row.error_detail = (
                "Incremental finalization was interrupted before the revision commit."
            )
            row.updated_at = utcnow()
            await self._save(row)
            return WatcherPollEvent(
                row.relative_path,
                "failed_retryable",
                row.content_sha256,
                None,
                "incremental_finalize_injected_failure",
            )
        except Phase02Error as error:
            row.status = "failed_retryable"
            row.error_code = error.code
            row.error_detail = error.detail
            row.updated_at = utcnow()
            await self._save(row)
            return WatcherPollEvent(
                row.relative_path,
                "failed_retryable",
                row.content_sha256,
                None,
                error.code,
            )
        if incremental.status == "failed":
            row.status = "failed_retryable"
            row.last_incremental_run_id = incremental.id
            row.error_code = incremental.error_code
            row.error_detail = incremental.error_detail
            row.updated_at = utcnow()
            await self._save(row)
            return WatcherPollEvent(
                row.relative_path,
                "failed_retryable",
                row.content_sha256,
                incremental.id,
                incremental.error_code,
            )
        row.status = "completed"
        row.last_incremental_run_id = incremental.id
        row.error_code = None
        row.error_detail = None
        row.updated_at = utcnow()
        await self._save(row)
        return WatcherPollEvent(
            row.relative_path,
            "completed",
            row.content_sha256,
            incremental.id,
            incremental.error_code,
        )

    async def _mark_missing(self, row: WatcherFile) -> WatcherPollEvent:
        row.status = "missing"
        row.updated_at = utcnow()
        await self._save(row)
        return WatcherPollEvent(row.relative_path, "missing", row.content_sha256, None, None)

    async def _fail(
        self,
        relative: str,
        code: str,
        detail: str,
        content_sha256: str | None,
        *,
        terminal: bool | None = None,
    ) -> WatcherPollEvent:
        status = (
            "failed_terminal"
            if (terminal if terminal is not None else code in _TERMINAL_WATCHER_CODES)
            else "failed_retryable"
        )
        row = await self._row_for(relative)
        if row is None:
            row = WatcherFile(
                id=uuid4(),
                inbox_root=str(self.inbox_path),
                relative_path=relative,
                content_sha256=content_sha256,
                byte_size=0,
                stable_poll_count=0,
                status=status,
            )
        row.status = status
        row.error_code = code
        row.error_detail = detail
        row.content_sha256 = content_sha256
        row.updated_at = utcnow()
        await self._save(row)
        return WatcherPollEvent(relative, status, content_sha256, None, code)

    async def _row_for(self, relative: str) -> WatcherFile | None:
        async with self.session_factory() as session:
            row = await session.scalar(
                select(WatcherFile).where(
                    WatcherFile.inbox_root == str(self.inbox_path),
                    WatcherFile.relative_path == relative,
                )
            )
        return row if isinstance(row, WatcherFile) else None

    async def _save(self, row: WatcherFile) -> None:
        async with self.session_factory() as session:
            merged = await session.merge(row)
            await session.commit()
            await session.refresh(merged)
            row.id = merged.id
            row.status = merged.status
            row.stable_poll_count = merged.stable_poll_count
            row.content_sha256 = merged.content_sha256
            row.last_incremental_run_id = merged.last_incremental_run_id
            row.error_code = merged.error_code
            row.corpus_id = merged.corpus_id

    def _hash_file(self, path: Path) -> tuple[str, int]:
        digest = hashlib.sha256()
        byte_size = 0
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                byte_size += len(chunk)
                if byte_size > self.max_upload_bytes:
                    raise ValidationError(
                        "upload_too_large",
                        f"The watched file exceeds the {self.max_upload_bytes}-byte limit.",
                        "Reduce the file size or increase MAX_UPLOAD_BYTES deliberately.",
                    )
                digest.update(chunk)
        if byte_size == 0:
            raise ValidationError(
                "empty_upload",
                "The watched file is empty.",
                "Write a non-empty supported document into the inbox.",
            )
        return digest.hexdigest(), byte_size


def _parse_inbox_path(relative: str) -> tuple[UUID, str, SourceFormat]:
    parts = Path(relative).parts
    if len(parts) != 2:
        raise ValidationError(
            "watcher_path_invalid",
            "Watched files must be placed at {corpus_id}/{logical_name}.{ext}.",
            "Use a corpus UUID directory and a filename matching the logical source.",
        )
    try:
        corpus_id = UUID(parts[0])
    except ValueError as error:
        raise ValidationError(
            "watcher_corpus_invalid",
            "The inbox directory name must be a corpus UUID.",
            "Place the file under the target corpus identifier.",
        ) from error
    filename = parts[1]
    suffix = Path(filename).suffix.lower()
    declared = _EXTENSION_FORMAT.get(suffix)
    if declared is None:
        raise ValidationError(
            "watcher_format_unsupported",
            "The watched file extension is not a declared source format.",
            "Use pdf, docx, md, markdown, or txt.",
        )
    logical_name = Path(filename).stem.strip()
    if not logical_name:
        raise ValidationError(
            "watcher_logical_name_invalid",
            "The watched filename does not contain a logical source name.",
            "Name the file after the logical source, for example Decision Log.txt.",
        )
    return corpus_id, logical_name, declared
