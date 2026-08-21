from pathlib import Path

import httpx
import pytest

from app.config import Settings
from app.main import create_app
from app.request_limits import MULTIPART_OVERHEAD_BYTES
from app.services import Phase02Service
from app.storage import LocalFileStorage


@pytest.mark.integration
async def test_phase02_api_exercises_ingestion_inspection_citation_and_search(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    service, storage = phase02_service
    application = create_app(phase02_service=service)
    transport = httpx.ASGITransport(app=application)
    async with (
        application.router.lifespan_context(application),
        httpx.AsyncClient(transport=transport, base_url="http://test") as client,
    ):
        corpus_response = await client.post(
            "/corpora",
            json={
                "name": "API Corpus",
                "domain": "software-project-assurance",
                "declared_formats": ["pdf", "docx", "markdown", "txt"],
            },
        )
        assert corpus_response.status_code == 201
        corpus_id = corpus_response.json()["id"]
        fetched_corpus = await client.get(f"/corpora/{corpus_id}")
        assert fetched_corpus.json()["name"] == "API Corpus"
        listed = await client.get("/corpora")
        assert listed.status_code == 200
        assert any(item["id"] == corpus_id for item in listed.json())
        named = await client.get("/corpora", params={"name": "API Corpus"})
        assert named.status_code == 200
        assert named.json()[0]["id"] == corpus_id

        source_path = corpus_fixtures / "aurora-control-hub" / "decision-log.txt"
        ingest_response = await client.post(
            f"/corpora/{corpus_id}/sources",
            data={"logical_name": "Decision Log", "declared_format": "txt"},
            files={"file": (source_path.name, source_path.read_bytes(), "text/plain")},
        )
        assert ingest_response.status_code == 201
        ingestion = ingest_response.json()
        source_id = ingestion["source"]["id"]
        version_id = ingestion["version"]["id"]

        duplicate_response = await client.post(
            f"/corpora/{corpus_id}/sources",
            data={"logical_name": "Decision Log", "declared_format": "txt"},
            files={"file": (source_path.name, source_path.read_bytes(), "text/plain")},
        )
        assert duplicate_response.status_code == 200
        assert duplicate_response.json()["duplicate"] is True

        sources = await client.get(f"/corpora/{corpus_id}/sources")
        source = await client.get(f"/corpora/{corpus_id}/sources/{source_id}")
        version = await client.get(f"/corpora/{corpus_id}/source-versions/{version_id}")
        blocks = await client.get(f"/corpora/{corpus_id}/source-versions/{version_id}/blocks")
        assert len(sources.json()) == 1
        assert len(source.json()["versions"]) == 1
        assert version.json()["sha256"] == ingestion["version"]["sha256"]
        first_block = blocks.json()[0]

        citation_response = await client.post(
            f"/corpora/{corpus_id}/citations/validate",
            json={
                "source_version_id": version_id,
                "source_sha256": ingestion["version"]["sha256"],
                "format": "txt",
                "native_locator": first_block["native_locator"],
                "normalized_start": 0,
                "normalized_end": len(first_block["normalized_text"]),
                "exact_quote": first_block["normalized_text"],
            },
        )
        assert citation_response.status_code == 200
        assert citation_response.json()["valid"] is True

        search_response = await client.post(
            f"/corpora/{corpus_id}/search",
            json={"query": "decision owner", "declared_format": "txt"},
        )
        assert search_response.status_code == 200
        assert search_response.json()["results"]

        unsafe_response = await client.post(
            f"/corpora/{corpus_id}/sources",
            data={"logical_name": "Unsafe", "declared_format": "txt"},
            files={"file": ("../unsafe.txt", b"safe data", "text/plain")},
        )
        assert unsafe_response.status_code == 400
        assert unsafe_response.json()["code"] == "unsafe_filename"
        assert "D:\\" not in unsafe_response.text

        malformed_response = await client.post(
            f"/corpora/{corpus_id}/sources",
            data={"logical_name": "Broken PDF", "declared_format": "pdf"},
            files={"file": ("broken.pdf", b"%PDF-1.7\nbroken", "application/pdf")},
        )
        assert malformed_response.status_code == 422
        assert malformed_response.json()["code"] == "malformed_pdf"
        assert malformed_response.json()["action"]

        unsupported_response = await client.post(
            f"/corpora/{corpus_id}/sources",
            data={"logical_name": "Spreadsheet", "declared_format": "xlsx"},
            files={
                "file": (
                    "sheet.xlsx",
                    b"not a spreadsheet",
                    "application/octet-stream",
                )
            },
        )
        assert unsupported_response.status_code == 422
        assert unsupported_response.json()["code"] == "request_validation_error"
        assert unsupported_response.json()["action"]

        punctuation_search = await client.post(
            f"/corpora/{corpus_id}/search",
            json={"query": "---"},
        )
        assert punctuation_search.status_code == 400
        assert punctuation_search.json()["code"] == "empty_search_terms"
        assert list(storage.staging_root.iterdir()) == []


@pytest.mark.integration
async def test_http_request_guard_and_streamed_file_bound(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
) -> None:
    service, storage = phase02_service
    storage.max_upload_bytes = 4
    application = create_app(
        settings=Settings(max_upload_bytes=4),
        phase02_service=service,
    )
    transport = httpx.ASGITransport(app=application)
    async with (
        application.router.lifespan_context(application),
        httpx.AsyncClient(transport=transport, base_url="http://test") as client,
    ):
        corpus_response = await client.post(
            "/corpora",
            json={
                "name": "Upload bounds",
                "domain": "software-project-assurance",
                "declared_formats": ["txt"],
            },
        )
        corpus_id = corpus_response.json()["id"]
        upload_path = f"/corpora/{corpus_id}/sources"

        allowed = await client.post(
            upload_path,
            data={"logical_name": "Allowed", "declared_format": "txt"},
            files={"file": ("allowed.txt", b"safe", "text/plain")},
        )
        assert allowed.status_code == 201

        streamed_oversize = await client.post(
            upload_path,
            data={"logical_name": "Streamed oversize", "declared_format": "txt"},
            files={"file": ("oversize.txt", b"large", "text/plain")},
        )
        assert streamed_oversize.status_code == 413
        assert streamed_oversize.json()["code"] == "upload_too_large"

        request_oversize = await client.post(
            upload_path,
            content=b"",
            headers={
                "content-length": str(4 + MULTIPART_OVERHEAD_BYTES + 1),
                "content-type": "multipart/form-data; boundary=unused",
            },
        )
        assert request_oversize.status_code == 413
        assert request_oversize.json()["code"] == "request_too_large"
        assert request_oversize.json()["action"]
