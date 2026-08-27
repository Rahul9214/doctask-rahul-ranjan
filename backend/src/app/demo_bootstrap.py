"""Idempotent demo corpus bootstrap: sources plus the initial durable revision.

Canonical fixtures live under ``backend/fixtures/corpora``. This path creates
missing Aurora/Harbor corpora, ingests fixture documents without duplicating
existing source versions, rematerializes missing demo source bytes from those
fixtures onto the recorded storage key, and creates the first current revision
when it is missing. It does not delete corpora, complete human review, start a
durable workflow run, or repair non-demo corpora.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import io
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast
from uuid import UUID

from fastapi import UploadFile
from starlette.datastructures import Headers

from app.checkpointer import configure_windows_psycopg_loop
from app.errors import NotFoundError, ProvenanceError, StorageError, ValidationError
from app.incremental_service import IncrementalService
from app.models import Source, SourceVersion
from app.parsers import SourceFormat
from app.runtime import build_application_services
from app.services import Phase02Service
from app.storage import StagedUpload

MEDIA_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "markdown": "text/markdown",
    "txt": "text/plain",
}


@dataclass(frozen=True, slots=True)
class CorpusBootstrapResult:
    corpus_id: UUID
    name: str
    created_corpus: bool
    sources_ingested: int
    sources_reused: int
    sources_repaired: int
    revision_id: UUID
    created_revision: bool


class DemoBootstrap:
    def __init__(
        self,
        phase02: Phase02Service,
        incremental: IncrementalService,
        fixture_root: Path | None = None,
    ) -> None:
        self.phase02 = phase02
        self.incremental = incremental
        self.fixture_root = fixture_root or resolve_fixture_root()

    async def bootstrap(self) -> list[CorpusBootstrapResult]:
        results: list[CorpusBootstrapResult] = []
        for corpus_dir in iter_fixture_dirs(self.fixture_root):
            results.extend(await self.bootstrap_fixture(corpus_dir))
        return results

    async def bootstrap_fixture(self, corpus_dir: Path) -> list[CorpusBootstrapResult]:
        manifest = _load_manifest(corpus_dir / "manifest.json")
        name = str(manifest["name"])
        existing = await self.phase02.list_corpora(name=name)
        created_corpus = False
        if not existing:
            corpus = await self.phase02.create_corpus(
                name=name,
                domain=str(manifest["domain"]),
                declared_formats=list(manifest["declared_formats"]),
            )
            existing = [corpus]
            created_corpus = True
        results: list[CorpusBootstrapResult] = []
        for index, corpus in enumerate(existing):
            ingested, reused, repaired = await self._ingest_manifest_documents(
                corpus.id, corpus_dir, manifest
            )
            created_revision = False
            try:
                await self.incremental.get_current_revision(corpus.id)
            except NotFoundError as error:
                if error.code != "corpus_revision_not_found":
                    raise
                created_revision = True
            revision = await self.incremental.ensure_initial_revision(corpus.id)
            results.append(
                CorpusBootstrapResult(
                    corpus_id=corpus.id,
                    name=name,
                    created_corpus=created_corpus and index == 0,
                    sources_ingested=ingested,
                    sources_reused=reused,
                    sources_repaired=repaired,
                    revision_id=revision.id,
                    created_revision=created_revision,
                )
            )
        return results

    async def _ingest_manifest_documents(
        self,
        corpus_id: UUID,
        corpus_dir: Path,
        manifest: dict[str, Any],
    ) -> tuple[int, int, int]:
        ingested = 0
        reused = 0
        repaired = 0
        for document in manifest["documents"]:
            disposition = await self._ensure_fixture_document(corpus_id, corpus_dir, document)
            if disposition == "ingested":
                ingested += 1
            elif disposition == "reused":
                reused += 1
            else:
                repaired += 1
        return ingested, reused, repaired

    async def _ensure_fixture_document(
        self,
        corpus_id: UUID,
        corpus_dir: Path,
        document: dict[str, Any],
    ) -> Literal["ingested", "reused", "repaired"]:
        declared_format = cast(SourceFormat, str(document["declared_format"]))
        logical_name = str(document["logical_name"])
        fixture_path = corpus_dir / str(document["filename"])
        fixture_sha = hashlib.sha256(fixture_path.read_bytes()).hexdigest()
        matching = await self._matching_demo_version(
            corpus_id,
            logical_name=logical_name,
            sha256=fixture_sha,
            declared_format=declared_format,
        )
        if matching is None:
            result = await self.phase02.ingest(
                corpus_id=corpus_id,
                logical_name=logical_name,
                declared_format=declared_format,
                upload=_fixture_upload(fixture_path, declared_format),
            )
            return "reused" if result.duplicate else "ingested"
        _source, version = matching
        try:
            actual_sha = await self.phase02.storage.sha256_for_key(version.storage_key)
        except StorageError as error:
            if error.code != "source_bytes_unavailable":
                raise
            await self._rematerialize_demo_version(version, fixture_path, declared_format)
            return "repaired"
        if actual_sha != version.sha256:
            raise ProvenanceError(
                "source_bytes_tampered",
                "Stored source bytes no longer match the registered SHA-256.",
                "Restore the exact immutable source bytes; do not silently repair them.",
            )
        return "reused"

    async def _matching_demo_version(
        self,
        corpus_id: UUID,
        *,
        logical_name: str,
        sha256: str,
        declared_format: SourceFormat,
    ) -> tuple[Source, SourceVersion] | None:
        for source in await self.phase02.list_sources(corpus_id):
            if source.logical_name != logical_name:
                continue
            _source, versions = await self.phase02.get_source(corpus_id, source.id)
            for version in versions:
                if version.sha256 != sha256:
                    continue
                if version.declared_format != declared_format:
                    raise ValidationError(
                        "duplicate_format_mismatch",
                        "These bytes already exist under a different declared format.",
                        "Use the original format or a different logical source.",
                    )
                return source, version
        return None

    async def _rematerialize_demo_version(
        self,
        version: SourceVersion,
        fixture_path: Path,
        declared_format: SourceFormat,
    ) -> None:
        """Restore missing bytes onto the recorded SourceVersion storage key.

        Same SHA-256 must keep the same immutable version row. A new version is
        not created merely because the filesystem object disappeared.
        """

        staged: StagedUpload | None = None
        try:
            staged = await self.phase02.storage.stage(
                _fixture_upload(fixture_path, declared_format)
            )
            if staged.sha256 != version.sha256:
                raise ProvenanceError(
                    "source_bytes_tampered",
                    "Canonical demo fixture bytes do not match the registered SHA-256.",
                    "Restore the exact immutable source bytes; do not silently repair them.",
                )
            await self.phase02.storage.restore_missing(staged, version.storage_key)
            staged = None
            actual_sha = await self.phase02.storage.sha256_for_key(version.storage_key)
            if actual_sha != version.sha256:
                raise ProvenanceError(
                    "source_bytes_tampered",
                    "Stored source bytes no longer match the registered SHA-256.",
                    "Restore the exact immutable source bytes; do not silently repair them.",
                )
        finally:
            if staged is not None:
                await self.phase02.storage.remove_staged(staged)


def iter_fixture_dirs(root: Path) -> list[Path]:
    return sorted(
        path for path in root.iterdir() if path.is_dir() and (path / "manifest.json").is_file()
    )


def resolve_fixture_root(explicit: Path | None = None) -> Path:
    if explicit is not None:
        return explicit
    candidates = (
        Path.cwd() / "fixtures" / "corpora",
        Path(__file__).resolve().parents[2] / "fixtures" / "corpora",
    )
    for path in candidates:
        if path.is_dir():
            return path
    raise FileNotFoundError(
        "Demo corpus fixtures were not found. Run from the backend directory "
        "or pass --fixture-root."
    )


def _load_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Corpus manifest must be a JSON object: {path}")
    return payload


def _fixture_upload(path: Path, source_format: SourceFormat) -> UploadFile:
    return UploadFile(
        io.BytesIO(path.read_bytes()),
        filename=path.name,
        headers=Headers({"content-type": MEDIA_TYPES[source_format]}),
    )


def serialize_bootstrap_results(results: list[CorpusBootstrapResult]) -> list[dict[str, object]]:
    return [
        {
            "corpus_id": str(item.corpus_id),
            "name": item.name,
            "created_corpus": item.created_corpus,
            "sources_ingested": item.sources_ingested,
            "sources_reused": item.sources_reused,
            "sources_repaired": item.sources_repaired,
            "revision_id": str(item.revision_id),
            "created_revision": item.created_revision,
        }
        for item in results
    ]


async def bootstrap_demo_corpora(
    *,
    fixture_root: Path | None = None,
) -> list[CorpusBootstrapResult]:
    runtime = build_application_services(include_watcher=False)
    try:
        return await DemoBootstrap(
            runtime.phase02,
            runtime.incremental,
            fixture_root=fixture_root,
        ).bootstrap()
    finally:
        await runtime.aclose()


async def _async_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Idempotently create missing demo corpora, ingest fixture sources, "
            "and establish the current durable revision."
        )
    )
    parser.add_argument(
        "--fixture-root",
        type=Path,
        default=None,
        help="Directory containing demo corpus fixture folders with manifest.json.",
    )
    args = parser.parse_args(argv)
    results = await bootstrap_demo_corpora(fixture_root=args.fixture_root)
    json.dump(serialize_bootstrap_results(results), sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def main(argv: list[str] | None = None) -> None:
    configure_windows_psycopg_loop()
    raise SystemExit(asyncio.run(_async_main(argv)))


if __name__ == "__main__":
    main()
