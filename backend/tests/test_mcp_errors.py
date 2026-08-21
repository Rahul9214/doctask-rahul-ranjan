from uuid import uuid4

import pytest

from app.errors import NotFoundError
from app.mcp_errors import (
    APPLICATION_ERROR_PREFIX,
    ApplicationToolError,
    execute_mcp_tool,
    parse_application_error_text,
)


def test_parse_application_error_extracts_code_detail_action() -> None:
    error = ApplicationToolError(
        NotFoundError("corpus_not_found", "The corpus was not found.", "Use a corpus identifier.")
    )
    wrapped = f"Error executing tool get_corpus: {error}"
    parsed = parse_application_error_text(wrapped)
    assert parsed == {
        "code": "corpus_not_found",
        "detail": "The corpus was not found.",
        "action": "Use a corpus identifier.",
    }
    assert APPLICATION_ERROR_PREFIX in str(error)
    assert "traceback" not in str(error).casefold()


def test_parse_application_error_rejects_unstructured_text() -> None:
    assert parse_application_error_text("plain failure") is None
    assert parse_application_error_text("APPLICATION_ERROR not-json") is None


def test_require_application_error_retains_raw_mcp_content() -> None:
    from types import SimpleNamespace

    from mcp.types import TextContent
    from mcp_helpers import require_application_error

    prefix = "Error executing tool list_corpora: SENTINEL_BEFORE_MARKER "
    payload = (
        APPLICATION_ERROR_PREFIX
        + '{"code":"internal_error","detail":"The operation could not be completed safely.",'
        + '"action":"Retry or inspect server health."}'
    )
    result = SimpleNamespace(
        is_error=True,
        content=[TextContent(type="text", text=prefix + payload)],
        structured_content={"note": "RAW_STRUCTURED_SHOULD_BE_KEPT"},
        meta={"trace": "RAW_META_SHOULD_BE_KEPT"},
    )
    parsed = require_application_error(result)
    assert "SENTINEL_BEFORE_MARKER" in parsed["raw_text"]
    assert "RAW_STRUCTURED_SHOULD_BE_KEPT" in parsed["raw_text"]
    assert "RAW_META_SHOULD_BE_KEPT" in parsed["raw_text"]
    assert parsed["code"] == "internal_error"
    assert parsed["detail"] == "The operation could not be completed safely."
    assert parsed["action"] == "Retry or inspect server health."
    assert parsed["raw_text"] != parsed["detail"]


async def test_execute_mcp_tool_wraps_phase02_and_unexpected_errors(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def missing() -> None:
        raise NotFoundError(
            "workflow_run_not_found",
            "The workflow run was not found in this corpus.",
            "Use a workflow run identifier returned for the same corpus.",
        )

    try:
        await execute_mcp_tool("get_workflow_status", missing)
    except ApplicationToolError as error:
        assert error.code == "workflow_run_not_found"
        assert error.action
    else:
        raise AssertionError("expected ApplicationToolError")

    secret = f"secret={uuid4()} TRACEBACK-LIKE"

    async def boom() -> None:
        raise RuntimeError(secret)

    caplog.set_level("WARNING", logger="app.mcp")
    try:
        await execute_mcp_tool("list_corpora", boom)
    except ApplicationToolError as error:
        assert error.code == "internal_error"
        assert "secret=" not in error.detail
        assert "TRACEBACK-LIKE" not in error.detail
        assert "RuntimeError" not in error.detail
        assert "safely" in error.detail
    else:
        raise AssertionError("expected ApplicationToolError")

    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert secret not in logged
    assert "TRACEBACK-LIKE" not in logged
    assert "Traceback" not in logged
