import hashlib
import io
from pathlib import Path
from uuid import uuid4

import pytest

from app.embeddings import DeterministicEmbedding
from app.errors import StorageError, ValidationError
from app.storage import UPLOAD_CHUNK_BYTES, LocalFileStorage


class MemoryUpload:
    def __init__(self, content: bytes) -> None:
        self.content = io.BytesIO(content)
        self.requested_sizes: list[int] = []

    async def read(self, size: int = -1) -> bytes:
        self.requested_sizes.append(size)
        return self.content.read(size)


@pytest.mark.asyncio
async def test_storage_streams_hashes_promotes_and_uses_generated_key(tmp_path: Path) -> None:
    content = b"a" * (UPLOAD_CHUNK_BYTES + 137)
    upload = MemoryUpload(content)
    storage = LocalFileStorage(tmp_path, max_upload_bytes=len(content) + 1)

    staged = await storage.stage(upload)
    key = storage.storage_key(
        corpus_id=uuid4(),
        source_id=uuid4(),
        version_id=uuid4(),
        sha256=staged.sha256,
        declared_format="txt",
    )
    target = await storage.promote(staged, key)

    assert upload.requested_sizes
    assert set(upload.requested_sizes) == {UPLOAD_CHUNK_BYTES}
    assert len(upload.requested_sizes) == 3
    assert staged.sha256 == hashlib.sha256(content).hexdigest()
    assert target.read_bytes() == content
    assert staged.sha256 in key
    assert "streamed content" not in key
    assert await storage.sha256_for_key(key) == staged.sha256


@pytest.mark.asyncio
async def test_storage_restore_missing_writes_only_when_absent(tmp_path: Path) -> None:
    storage = LocalFileStorage(tmp_path, max_upload_bytes=100)
    first = await storage.stage(MemoryUpload(b"demo-bytes"))
    key = storage.storage_key(
        corpus_id=uuid4(),
        source_id=uuid4(),
        version_id=uuid4(),
        sha256=first.sha256,
        declared_format="txt",
    )
    target = await storage.restore_missing(first, key)
    assert target.read_bytes() == b"demo-bytes"
    assert await storage.sha256_for_key(key) == first.sha256

    collision = await storage.stage(MemoryUpload(b"demo-bytes"))
    with pytest.raises(StorageError) as raised:
        await storage.restore_missing(collision, key)
    assert raised.value.code == "storage_collision"
    assert target.read_bytes() == b"demo-bytes"
    await storage.remove_staged(collision)


@pytest.mark.asyncio
async def test_storage_cleans_partial_file_after_size_failure(tmp_path: Path) -> None:
    storage = LocalFileStorage(tmp_path, max_upload_bytes=4)

    with pytest.raises(ValidationError) as raised:
        await storage.stage(MemoryUpload(b"too large"))

    assert raised.value.code == "upload_too_large"
    assert list(storage.staging_root.iterdir()) == []


def test_storage_rejects_escaping_internal_key(tmp_path: Path) -> None:
    storage = LocalFileStorage(tmp_path, max_upload_bytes=100)

    with pytest.raises(StorageError) as raised:
        storage.path_for_key("../outside")

    assert raised.value.code == "unsafe_storage_key"


def test_embedding_is_stable_fixed_dimension_and_token_sensitive() -> None:
    embedding = DeterministicEmbedding()

    first = embedding.embed("Milestone owner delivery")
    second = embedding.embed("Milestone owner delivery")
    related = embedding.embed("delivery milestone")
    unrelated = embedding.embed("banana telescope")

    assert first == second
    assert len(first) == 64
    assert sum(a * b for a, b in zip(first, related, strict=True)) > sum(
        a * b for a, b in zip(first, unrelated, strict=True)
    )
    assert embedding.embed("") == [0.0] * 64
