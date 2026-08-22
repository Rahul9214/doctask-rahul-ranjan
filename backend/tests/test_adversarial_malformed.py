import zipfile
from pathlib import Path

import httpx
import pytest
from pypdf import PdfWriter

from app.config import Settings
from app.errors import ParserError, ValidationError
from app.main import create_app
from app.parsers import (
    MAX_DOCX_COMPRESSION_RATIO,
    parse_file,
    validate_declared_file,
)
from app.services import Phase02Service
from app.storage import LocalFileStorage


def _write_docx_zip(path: Path, entries: dict[str, bytes], *, compress: bool = True) -> None:
    compression = zipfile.ZIP_DEFLATED if compress else zipfile.ZIP_STORED
    with zipfile.ZipFile(path, "w", compression=compression) as archive:
        for name, data in entries.items():
            archive.writestr(name, data)


def _minimal_docx_entries(**extra: bytes) -> dict[str, bytes]:
    document = (
        b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        b"<w:body><w:p><w:r><w:t>Safe paragraph</w:t></w:r></w:p></w:body></w:document>"
    )
    types = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        b'<Default Extension="xml" ContentType="application/xml"/>'
        b'<Override PartName="/word/document.xml" ContentType='
        b'"application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        b"</Types>"
    )
    return {"[Content_Types].xml": types, "word/document.xml": document, **extra}


def test_encrypted_pdf_is_rejected_without_ocr(tmp_path: Path) -> None:
    path = tmp_path / "locked.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.encrypt("not-a-real-secret")
    with path.open("wb") as output:
        writer.write(output)

    with pytest.raises(ParserError) as raised:
        parse_file(path, "pdf")
    assert raised.value.code == "encrypted_pdf"
    assert "traceback" not in raised.value.detail.casefold()
    assert "not-a-real-secret" not in raised.value.detail


def test_pdf_page_limit_is_enforced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.parsers.MAX_PDF_PAGES", 1)
    path = tmp_path / "many.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.add_blank_page(width=612, height=792)
    with path.open("wb") as output:
        writer.write(output)

    with pytest.raises(ParserError) as raised:
        parse_file(path, "pdf")
    assert raised.value.code == "pdf_resource_limit"


def test_docx_resource_and_package_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.parsers.MAX_DOCX_ENTRIES", 2)
    too_many = tmp_path / "entries.docx"
    _write_docx_zip(
        too_many,
        _minimal_docx_entries(**{f"word/extra{index}.xml": b"<x/>" for index in range(3)}),
    )
    with pytest.raises(ValidationError) as entries:
        validate_declared_file(
            too_many,
            declared_format="docx",
            original_filename="entries.docx",
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    assert entries.value.code == "docx_resource_limit"
    monkeypatch.setattr("app.parsers.MAX_DOCX_ENTRIES", 1_000)

    bloated = tmp_path / "ratio.docx"
    zeros = b" " * 50_000
    _write_docx_zip(bloated, _minimal_docx_entries(**{"word/padding.xml": zeros}))
    with pytest.raises(ValidationError) as ratio:
        validate_declared_file(
            bloated,
            declared_format="docx",
            original_filename="ratio.docx",
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    assert ratio.value.code == "docx_resource_limit"
    assert MAX_DOCX_COMPRESSION_RATIO >= 200

    monkeypatch.setattr("app.parsers.MAX_DOCX_ENTRY_BYTES", 32)
    oversized_entry = tmp_path / "entry-size.docx"
    _write_docx_zip(
        oversized_entry,
        _minimal_docx_entries(**{"word/padding.xml": b"safe-entry-bytes-xxxxxxxxxxxxxxxx"}),
        compress=False,
    )
    with pytest.raises(ValidationError) as entry_size:
        validate_declared_file(
            oversized_entry,
            declared_format="docx",
            original_filename="entry-size.docx",
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    assert entry_size.value.code == "docx_resource_limit"
    assert "traceback" not in entry_size.value.detail.casefold()

    monkeypatch.setattr("app.parsers.MAX_DOCX_ENTRY_BYTES", 20 * 1024 * 1024)
    monkeypatch.setattr("app.parsers.MAX_DOCX_UNCOMPRESSED_BYTES", 80)
    oversized_total = tmp_path / "aggregate.docx"
    _write_docx_zip(
        oversized_total,
        _minimal_docx_entries(
            **{
                "word/a.xml": b"aaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "word/b.xml": b"bbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            }
        ),
        compress=False,
    )
    with pytest.raises(ValidationError) as aggregate:
        validate_declared_file(
            oversized_total,
            declared_format="docx",
            original_filename="aggregate.docx",
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    assert aggregate.value.code == "docx_resource_limit"
    assert "traceback" not in aggregate.value.detail.casefold()
    monkeypatch.setattr("app.parsers.MAX_DOCX_UNCOMPRESSED_BYTES", 50 * 1024 * 1024)

    broken_xml = tmp_path / "broken-xml.docx"
    _write_docx_zip(
        broken_xml,
        {
            "[Content_Types].xml": _minimal_docx_entries()["[Content_Types].xml"],
            "word/document.xml": b"<w:document><not-closed>",
        },
    )
    with pytest.raises((ValidationError, ParserError)) as xml_error:
        parse_file(broken_xml, "docx")
    assert xml_error.value.code in {"malformed_docx", "content_signature_mismatch"}
    assert "<w:document>" not in xml_error.value.detail


def test_nul_bytes_and_empty_text_are_rejected(tmp_path: Path) -> None:
    nul = tmp_path / "nul.txt"
    nul.write_bytes(b"safe\x00text")
    with pytest.raises(ValidationError) as nul_error:
        validate_declared_file(
            nul,
            declared_format="txt",
            original_filename="nul.txt",
            media_type="text/plain",
        )
    assert nul_error.value.code == "invalid_text_encoding"
    assert "\\x00" not in nul_error.value.detail


@pytest.mark.integration
@pytest.mark.adversarial
async def test_http_upload_malformed_and_empty_fail_closed(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
) -> None:
    phase02, storage = phase02_service
    application = create_app(
        settings=Settings(max_upload_bytes=64),
        phase02_service=phase02,
    )
    storage.max_upload_bytes = 64
    transport = httpx.ASGITransport(app=application)
    async with (
        application.router.lifespan_context(application),
        httpx.AsyncClient(transport=transport, base_url="http://test") as client,
    ):
        corpus = await client.post(
            "/corpora",
            json={
                "name": "Malformed Uploads",
                "domain": "software-project-assurance",
                "declared_formats": ["pdf", "docx", "txt"],
            },
        )
        corpus_id = corpus.json()["id"]
        upload = f"/corpora/{corpus_id}/sources"

        empty = await client.post(
            upload,
            data={"logical_name": "Empty", "declared_format": "txt"},
            files={"file": ("empty.txt", b"", "text/plain")},
        )
        assert empty.status_code == 400
        assert empty.json()["code"] == "empty_upload"
        assert "traceback" not in empty.text.casefold()

        mismatch = await client.post(
            upload,
            data={"logical_name": "Mismatch", "declared_format": "pdf"},
            files={"file": ("notes.pdf", b"not a pdf body", "application/pdf")},
        )
        assert mismatch.status_code in {400, 422}
        assert mismatch.json()["code"] in {"content_signature_mismatch", "malformed_pdf"}
        assert b"not a pdf body" not in mismatch.content

        traversal = await client.post(
            upload,
            data={"logical_name": "Traversal", "declared_format": "txt"},
            files={"file": ("..\\secret.txt", b"safe", "text/plain")},
        )
        assert traversal.status_code == 400
        assert traversal.json()["code"] == "unsafe_filename"

        oversize = await client.post(
            upload,
            data={"logical_name": "Oversize", "declared_format": "txt"},
            files={"file": ("big.txt", b"x" * 80, "text/plain")},
        )
        assert oversize.status_code == 413
        assert oversize.json()["code"] == "upload_too_large"
        assert list(storage.staging_root.iterdir()) == []
