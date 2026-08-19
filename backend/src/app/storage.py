import hashlib
import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol
from uuid import UUID, uuid4

import anyio

from app.errors import StorageError, ValidationError
from app.parsers import FORMAT_EXTENSIONS, SourceFormat

UPLOAD_CHUNK_BYTES = 1024 * 1024


class AsyncUpload(Protocol):
    async def read(self, size: int = -1) -> bytes: ...


@dataclass(frozen=True, slots=True)
class StagedUpload:
    path: Path
    sha256: str
    byte_size: int


class LocalFileStorage:
    """Corpus-scoped immutable file storage rooted at a configured directory."""

    def __init__(self, root: Path, max_upload_bytes: int) -> None:
        self.root = root.resolve()
        self.max_upload_bytes = max_upload_bytes
        self.staging_root = self.root / ".staging"
        self.staging_root.mkdir(parents=True, exist_ok=True)

    async def stage(self, upload: AsyncUpload) -> StagedUpload:
        staged_path = self.staging_root / f"{uuid4()}.part"
        digest = hashlib.sha256()
        byte_size = 0
        try:
            async with await anyio.open_file(staged_path, "xb") as staged_file:
                while chunk := await upload.read(UPLOAD_CHUNK_BYTES):
                    byte_size += len(chunk)
                    if byte_size > self.max_upload_bytes:
                        raise ValidationError(
                            "upload_too_large",
                            f"The upload exceeds the {self.max_upload_bytes}-byte limit.",
                            "Reduce the file size or increase MAX_UPLOAD_BYTES deliberately.",
                        )
                    digest.update(chunk)
                    await staged_file.write(chunk)
            if byte_size == 0:
                raise ValidationError(
                    "empty_upload",
                    "The uploaded file is empty.",
                    "Upload a non-empty supported document.",
                )
            return StagedUpload(staged_path, digest.hexdigest(), byte_size)
        except BaseException:
            await self.remove_path(staged_path)
            raise

    def storage_key(
        self,
        *,
        corpus_id: UUID,
        source_id: UUID,
        version_id: UUID,
        sha256: str,
        declared_format: SourceFormat,
    ) -> str:
        extension = sorted(FORMAT_EXTENSIONS[declared_format])[0]
        return f"{corpus_id}/{source_id}/{sha256[:2]}/{sha256}/{version_id}{extension}"

    async def promote(self, staged: StagedUpload, storage_key: str) -> Path:
        target = self.path_for_key(storage_key)
        await anyio.to_thread.run_sync(target.parent.mkdir, 0o755, True, True)
        if target.exists():
            raise StorageError(
                "storage_collision",
                "The generated immutable storage destination already exists.",
                "Retry ingestion so a new version identifier is generated.",
            )
        try:
            await anyio.to_thread.run_sync(os.replace, staged.path, target)
        except OSError as error:
            raise StorageError(
                "storage_write_failed",
                "The uploaded file could not be promoted to durable storage.",
                "Verify SOURCE_STORAGE_PATH is writable and retry.",
            ) from error
        return target

    def path_for_key(self, storage_key: str) -> Path:
        key = PurePosixPath(storage_key)
        if key.is_absolute() or not key.parts or any(part in {"", ".", ".."} for part in key.parts):
            raise StorageError(
                "unsafe_storage_key",
                "The stored object key is invalid.",
                "Restore coherent source metadata before retrying.",
            )
        target = self.root.joinpath(*key.parts).resolve()
        if not target.is_relative_to(self.root):
            raise StorageError(
                "unsafe_storage_key",
                "The stored object key escapes the configured storage root.",
                "Restore coherent source metadata before retrying.",
            )
        return target

    async def sha256_for_key(self, storage_key: str) -> str:
        path = self.path_for_key(storage_key)

        def calculate() -> str:
            digest = hashlib.sha256()
            with path.open("rb") as source:
                while chunk := source.read(UPLOAD_CHUNK_BYTES):
                    digest.update(chunk)
            return digest.hexdigest()

        try:
            return await anyio.to_thread.run_sync(calculate)
        except OSError as error:
            raise StorageError(
                "source_bytes_unavailable",
                "The immutable source bytes are unavailable.",
                "Restore the content-addressed source file before validating provenance.",
            ) from error

    async def remove_key(self, storage_key: str) -> None:
        await self.remove_path(self.path_for_key(storage_key))

    async def remove_staged(self, staged: StagedUpload) -> None:
        await self.remove_path(staged.path)

    async def remove_path(self, path: Path) -> None:
        try:
            await anyio.to_thread.run_sync(path.unlink, True)
        except OSError:
            return
