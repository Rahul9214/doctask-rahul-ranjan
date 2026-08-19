import re
import unicodedata
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from docx import Document
from docx.text.paragraph import Paragraph
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.errors import ParserError, ValidationError

SourceFormat = Literal["pdf", "docx", "markdown", "txt"]
SUPPORTED_FORMATS: tuple[SourceFormat, ...] = ("pdf", "docx", "markdown", "txt")

FORMAT_EXTENSIONS: dict[SourceFormat, frozenset[str]] = {
    "pdf": frozenset({".pdf"}),
    "docx": frozenset({".docx"}),
    "markdown": frozenset({".md", ".markdown"}),
    "txt": frozenset({".txt"}),
}
FORMAT_MEDIA_TYPES: dict[SourceFormat, frozenset[str]] = {
    "pdf": frozenset({"application/pdf", "application/octet-stream"}),
    "docx": frozenset(
        {
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/octet-stream",
        }
    ),
    "markdown": frozenset({"text/markdown", "text/plain", "application/octet-stream"}),
    "txt": frozenset({"text/plain", "application/octet-stream"}),
}

MAX_DOCX_ENTRIES = 1_000
MAX_DOCX_ENTRY_BYTES = 20 * 1024 * 1024
MAX_DOCX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
MAX_DOCX_COMPRESSION_RATIO = 200


@dataclass(frozen=True, slots=True)
class ParsedBlock:
    block_index: int
    block_type: str
    native_locator: str
    normalized_text: str
    normalized_start: int = 0
    normalized_end: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


def normalize_block_text(text: str) -> str:
    """Normalize conservatively while retaining locator-level source identity."""

    normalized = unicodedata.normalize("NFC", text.replace("\r\n", "\n").replace("\r", "\n"))
    normalized = normalized.replace("\u00a0", " ")
    lines = [line.rstrip() for line in normalized.split("\n")]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def validate_declared_file(
    path: Path,
    *,
    declared_format: SourceFormat,
    original_filename: str,
    media_type: str | None,
) -> None:
    if not original_filename or original_filename in {".", ".."}:
        raise ValidationError(
            "unsafe_filename",
            "The upload filename is missing or unsafe.",
            "Supply a simple filename with the declared format extension.",
        )
    if any(character in original_filename for character in ("/", "\\", ":")):
        raise ValidationError(
            "unsafe_filename",
            "Path components are not allowed in upload filenames.",
            "Supply only a base filename such as status-report.pdf.",
        )

    extension = Path(original_filename).suffix.casefold()
    if extension not in FORMAT_EXTENSIONS[declared_format]:
        expected = ", ".join(sorted(FORMAT_EXTENSIONS[declared_format]))
        raise ValidationError(
            "format_extension_mismatch",
            f"The filename extension does not match declared format {declared_format}.",
            f"Use one of these extensions: {expected}.",
        )

    normalized_media_type = (media_type or "application/octet-stream").split(";", 1)[0].strip()
    if normalized_media_type not in FORMAT_MEDIA_TYPES[declared_format]:
        raise ValidationError(
            "media_type_mismatch",
            f"The media type does not match declared format {declared_format}.",
            "Send the format's standard media type or application/octet-stream.",
        )

    with path.open("rb") as source:
        prefix = source.read(8)
    if declared_format == "pdf" and not prefix.startswith(b"%PDF-"):
        raise ValidationError(
            "content_signature_mismatch",
            "The file content is not a PDF despite its declaration.",
            "Upload a valid text-based PDF and declare it as pdf.",
        )
    if declared_format == "docx":
        _validate_docx_archive(path)
    if declared_format in {"markdown", "txt"}:
        _decode_utf8(path)


def parse_file(path: Path, declared_format: SourceFormat) -> list[ParsedBlock]:
    if declared_format == "pdf":
        return _parse_pdf(path)
    if declared_format == "docx":
        return _parse_docx(path)
    if declared_format == "markdown":
        return _parse_markdown(path)
    return _parse_txt(path)


def _block(
    blocks: list[ParsedBlock],
    *,
    block_type: str,
    locator: str,
    text: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    normalized = normalize_block_text(text)
    if not normalized:
        return
    blocks.append(
        ParsedBlock(
            block_index=len(blocks),
            block_type=block_type,
            native_locator=locator,
            normalized_text=normalized,
            normalized_end=len(normalized),
            metadata=metadata or {},
        )
    )


def _parse_pdf(path: Path) -> list[ParsedBlock]:
    try:
        reader = PdfReader(path, strict=True)
        if reader.is_encrypted:
            raise ParserError(
                "encrypted_pdf",
                "Encrypted PDFs are not supported.",
                "Remove encryption and upload a text-based PDF.",
            )
        blocks: list[ParsedBlock] = []
        for page_index, page in enumerate(reader.pages):
            extracted = page.extract_text() or ""
            page_parts = re.split(r"\n[ \t]*\n+", extracted)
            for page_block_index, part in enumerate(page_parts):
                _block(
                    blocks,
                    block_type="pdf_text",
                    locator=f"page[{page_index + 1}]/block[{page_block_index}]",
                    text=part,
                    metadata={
                        "page_number": page_index + 1,
                        "parser_block_index": page_block_index,
                    },
                )
    except ParserError:
        raise
    except (PdfReadError, OSError, ValueError) as error:
        raise ParserError(
            "malformed_pdf",
            "The PDF could not be parsed safely.",
            "Upload a valid, unencrypted, text-based PDF.",
        ) from error

    if not blocks:
        raise ParserError(
            "textless_pdf",
            "The PDF contains no extractable text and may be scanned.",
            "Upload a text-based PDF; OCR is outside the current scope.",
        )
    return blocks


def _validate_docx_archive(path: Path) -> None:
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            names = {entry.filename for entry in entries}
            if len(entries) > MAX_DOCX_ENTRIES:
                raise ValidationError(
                    "docx_resource_limit",
                    "The DOCX contains too many archive entries.",
                    "Reduce document complexity and upload again.",
                )
            if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                raise ValidationError(
                    "content_signature_mismatch",
                    "The file is not a valid DOCX package.",
                    "Upload a valid Microsoft Word DOCX file.",
                )
            total_size = 0
            for entry in entries:
                total_size += entry.file_size
                if entry.file_size > MAX_DOCX_ENTRY_BYTES:
                    raise ValidationError(
                        "docx_resource_limit",
                        "A DOCX archive entry exceeds the safe parser limit.",
                        "Reduce embedded content and upload again.",
                    )
                if entry.compress_size and (
                    entry.file_size / entry.compress_size > MAX_DOCX_COMPRESSION_RATIO
                ):
                    raise ValidationError(
                        "docx_resource_limit",
                        "The DOCX compression ratio exceeds the safe parser limit.",
                        "Re-save the document normally and upload it again.",
                    )
            if total_size > MAX_DOCX_UNCOMPRESSED_BYTES:
                raise ValidationError(
                    "docx_resource_limit",
                    "The expanded DOCX exceeds the safe parser limit.",
                    "Reduce document size and upload again.",
                )
    except ValidationError:
        raise
    except (OSError, zipfile.BadZipFile) as error:
        raise ValidationError(
            "malformed_docx",
            "The DOCX archive is malformed.",
            "Re-save the document as a valid DOCX and upload again.",
        ) from error


def _parse_docx(path: Path) -> list[ParsedBlock]:
    _validate_docx_archive(path)
    try:
        document = Document(str(path))
        blocks: list[ParsedBlock] = []
        paragraph_index = 0
        table_index = 0
        for item in document.iter_inner_content():
            if isinstance(item, Paragraph):
                _block(
                    blocks,
                    block_type="docx_paragraph",
                    locator=f"paragraph[{paragraph_index}]",
                    text=item.text,
                    metadata={"paragraph_index": paragraph_index},
                )
                paragraph_index += 1
                continue

            table = item
            for row_index, row in enumerate(table.rows):
                for cell_index, cell in enumerate(row.cells):
                    for cell_paragraph_index, paragraph in enumerate(cell.paragraphs):
                        _block(
                            blocks,
                            block_type="docx_table_cell",
                            locator=(
                                f"table[{table_index}]/row[{row_index}]/cell[{cell_index}]"
                                f"/paragraph[{cell_paragraph_index}]"
                            ),
                            text=paragraph.text,
                            metadata={
                                "table_index": table_index,
                                "row_index": row_index,
                                "cell_index": cell_index,
                                "paragraph_index": cell_paragraph_index,
                            },
                        )
            table_index += 1
    except (KeyError, OSError, ValueError, zipfile.BadZipFile) as error:
        raise ParserError(
            "malformed_docx",
            "The DOCX document structure could not be parsed.",
            "Re-save the document as a valid DOCX and upload again.",
        ) from error

    if not blocks:
        raise ParserError(
            "empty_document",
            "The DOCX contains no supported paragraph or table-cell text.",
            "Add text to normal paragraphs or table cells and upload again.",
        )
    return blocks


def _decode_utf8(path: Path) -> str:
    try:
        data = path.read_bytes()
        if b"\x00" in data:
            raise UnicodeError("NUL byte")
        return data.decode("utf-8-sig")
    except (OSError, UnicodeError) as error:
        raise ValidationError(
            "invalid_text_encoding",
            "Text and Markdown uploads must be valid UTF-8 without NUL bytes.",
            "Save the file as UTF-8 text and upload it again.",
        ) from error


def _line_blocks(text: str, *, markdown: bool) -> list[ParsedBlock]:
    source = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = source.split("\n")
    blocks: list[ParsedBlock] = []
    current: list[str] = []
    current_start = 0
    current_type = "paragraph"

    def flush(end_index: int) -> None:
        nonlocal current
        if not current:
            return
        block_number = len(blocks)
        _block(
            blocks,
            block_type=current_type,
            locator=f"lines[{current_start + 1}-{end_index}]/block[{block_number}]",
            text="\n".join(current),
            metadata={"line_start": current_start + 1, "line_end": end_index},
        )
        current = []

    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            flush(index)
            continue

        line_type = "paragraph"
        if markdown and re.match(r"^#{1,6}\s+", stripped):
            line_type = "heading"
        elif markdown and re.match(r"^(?:[-*+]|\d+[.)])\s+", stripped):
            line_type = "list"

        if not current:
            current_start = index
            current_type = line_type
        elif line_type != current_type or line_type == "heading":
            flush(index)
            current_start = index
            current_type = line_type
        current.append(line)
    flush(len(lines))
    return blocks


def _parse_markdown(path: Path) -> list[ParsedBlock]:
    blocks = _line_blocks(_decode_utf8(path), markdown=True)
    if not blocks:
        raise ParserError(
            "empty_document",
            "The Markdown file contains no text blocks.",
            "Add headings, paragraphs, or lists and upload again.",
        )
    return blocks


def _parse_txt(path: Path) -> list[ParsedBlock]:
    blocks = _line_blocks(_decode_utf8(path), markdown=False)
    if not blocks:
        raise ParserError(
            "empty_document",
            "The text file contains no text blocks.",
            "Add plain text and upload again.",
        )
    return blocks
