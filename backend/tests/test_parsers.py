from pathlib import Path

import pytest
from pypdf import PdfWriter

from app.errors import ParserError, ValidationError
from app.parsers import parse_file, validate_declared_file


def test_pdf_parser_preserves_page_and_block_locator(corpus_fixtures: Path) -> None:
    blocks = parse_file(
        corpus_fixtures / "aurora-control-hub" / "project-charter.pdf",
        "pdf",
    )

    assert blocks[0].native_locator == "page[1]/block[0]"
    assert blocks[0].metadata == {"page_number": 1, "parser_block_index": 0}
    assert "Aurora Control Hub" in blocks[0].normalized_text
    assert blocks[0].normalized_end == len(blocks[0].normalized_text)


def test_docx_parser_preserves_paragraphs_and_table_cells(corpus_fixtures: Path) -> None:
    blocks = parse_file(
        corpus_fixtures / "aurora-control-hub" / "status-report.docx",
        "docx",
    )

    assert blocks[0].native_locator == "paragraph[0]"
    table_block = next(block for block in blocks if block.block_type == "docx_table_cell")
    assert table_block.native_locator == "table[0]/row[0]/cell[0]/paragraph[0]"
    assert table_block.normalized_text == "Milestone"


def test_markdown_parser_uses_line_ranges_and_block_types(corpus_fixtures: Path) -> None:
    blocks = parse_file(
        corpus_fixtures / "aurora-control-hub" / "risk-register.md",
        "markdown",
    )

    assert blocks[0].block_type == "heading"
    assert blocks[0].native_locator == "lines[1-1]/block[0]"
    assert any(block.block_type == "list" for block in blocks)


def test_txt_parser_uses_stable_line_ranges(corpus_fixtures: Path) -> None:
    blocks = parse_file(
        corpus_fixtures / "aurora-control-hub" / "decision-log.txt",
        "txt",
    )

    assert blocks[0].native_locator == "lines[1-1]/block[0]"
    assert blocks[1].native_locator.startswith("lines[3-")
    assert "Decision D-008" in blocks[1].normalized_text


def test_textless_pdf_is_rejected_without_ocr(tmp_path: Path) -> None:
    path = tmp_path / "scan.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    with path.open("wb") as output:
        writer.write(output)

    with pytest.raises(ParserError) as raised:
        parse_file(path, "pdf")

    assert raised.value.code == "textless_pdf"
    assert "OCR" in raised.value.action


def test_malformed_pdf_is_rejected_safely(tmp_path: Path) -> None:
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"%PDF-1.7\nnot a valid PDF")

    with pytest.raises(ParserError) as raised:
        parse_file(path, "pdf")

    assert raised.value.code == "malformed_pdf"
    assert "not a valid PDF" not in raised.value.detail


def test_declared_format_mismatch_and_path_traversal_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "document.txt"
    path.write_text("safe text", encoding="utf-8")

    with pytest.raises(ValidationError, match="extension"):
        validate_declared_file(
            path,
            declared_format="pdf",
            original_filename="document.txt",
            media_type="text/plain",
        )
    with pytest.raises(ValidationError) as traversal:
        validate_declared_file(
            path,
            declared_format="txt",
            original_filename="../document.txt",
            media_type="text/plain",
        )

    assert traversal.value.code == "unsafe_filename"


def test_malformed_docx_and_invalid_utf8_are_rejected(tmp_path: Path) -> None:
    invalid_docx = tmp_path / "broken.docx"
    invalid_docx.write_bytes(b"PK malformed")
    with pytest.raises(ValidationError) as docx_error:
        validate_declared_file(
            invalid_docx,
            declared_format="docx",
            original_filename="broken.docx",
            media_type=("application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        )

    invalid_text = tmp_path / "broken.txt"
    invalid_text.write_bytes(b"\xff\x00")
    with pytest.raises(ValidationError) as text_error:
        validate_declared_file(
            invalid_text,
            declared_format="txt",
            original_filename="broken.txt",
            media_type="text/plain",
        )

    assert docx_error.value.code == "malformed_docx"
    assert text_error.value.code == "invalid_text_encoding"
