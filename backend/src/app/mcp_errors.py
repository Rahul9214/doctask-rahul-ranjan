"""Translate application errors into controlled MCP tool errors."""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Awaitable, Callable
from typing import Any

from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import CallToolResult, TextContent
from pydantic import ValidationError as PydanticValidationError

from app.errors import Phase02Error
from app.test_database import TEST_DATABASE_NAME

APPLICATION_ERROR_PREFIX = "APPLICATION_ERROR "
SAFE_INTERNAL = Phase02Error(
    "internal_error",
    "The operation could not be completed safely.",
    "Retry or inspect server health.",
)
INVALID_REQUEST = Phase02Error(
    "invalid_request",
    "The request could not be validated.",
    "Retry with valid identifiers and field lengths.",
)
TEST_INJECT_FAILURE_ENV = "MCP_TEST_INJECT_FAILURE"
TEST_INJECT_TOOL_ENV = "MCP_TEST_INJECT_TOOL"
TEST_INJECT_UNEXPECTED = "unexpected"
TEST_INJECT_RESPONSE_VALIDATION = "response_validation"
TEST_SENTINEL_SECRET = "SECRET_SENTINEL_DO_NOT_LEAK"
TEST_SENTINEL_SOURCE = "SOURCE_TEXT_SENTINEL_DO_NOT_LEAK"
TEST_SENTINEL_DSN = "postgresql://credential-sentinel"
logger = logging.getLogger("app.mcp")


class ApplicationToolError(Exception):
    """Raised from MCP tools so clients receive code/detail/action without tracebacks."""

    def __init__(self, error: Phase02Error) -> None:
        self.code = error.code
        self.detail = error.detail
        self.action = error.action
        super().__init__(
            APPLICATION_ERROR_PREFIX
            + json.dumps(
                {"code": error.code, "detail": error.detail, "action": error.action},
                separators=(",", ":"),
            )
        )


def parse_application_error_text(text: str) -> dict[str, str] | None:
    marker = text.find(APPLICATION_ERROR_PREFIX)
    if marker < 0:
        return None
    payload = text[marker + len(APPLICATION_ERROR_PREFIX) :].strip()
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    code = parsed.get("code")
    detail = parsed.get("detail")
    action = parsed.get("action")
    if not isinstance(code, str) or not isinstance(detail, str) or not isinstance(action, str):
        return None
    return {"code": code, "detail": detail, "action": action}


def log_internal_error(tool_name: str, request_id: str | None = None) -> None:
    extra: dict[str, str] = {"tool": tool_name, "error_category": "internal_error"}
    if request_id:
        extra["request_id"] = request_id
    logger.warning("mcp_internal_error", extra=extra)


def _test_hook_enabled() -> bool:
    if os.environ.get("ALLOW_DESTRUCTIVE_TEST_DATABASE") != "true":
        return False
    database_url = os.environ.get("DATABASE_URL", "")
    return TEST_DATABASE_NAME in database_url


def _requested_test_inject(tool_name: str) -> str | None:
    if not _test_hook_enabled():
        return None
    if os.environ.get(TEST_INJECT_TOOL_ENV) != tool_name:
        return None
    mode = os.environ.get(TEST_INJECT_FAILURE_ENV)
    if mode in {TEST_INJECT_UNEXPECTED, TEST_INJECT_RESPONSE_VALIDATION}:
        return mode
    return None


def _unsafe_response_payload() -> dict[str, object]:
    return {
        "corpora": [
            {
                "id": TEST_SENTINEL_SECRET,
                "name": TEST_SENTINEL_SOURCE,
                "domain": TEST_SENTINEL_DSN,
                "declared_formats": [],
            }
        ]
    }


async def execute_mcp_tool[T](tool_name: str, operation: Callable[[], Awaitable[T]]) -> T:
    """Run the complete tool body inside the controlled application error boundary."""

    try:
        inject = _requested_test_inject(tool_name)
        if inject == TEST_INJECT_UNEXPECTED:
            raise RuntimeError(f"{TEST_SENTINEL_SECRET} {TEST_SENTINEL_SOURCE} {TEST_SENTINEL_DSN}")
        if inject == TEST_INJECT_RESPONSE_VALIDATION:
            return _unsafe_response_payload()  # type: ignore[return-value]
        return await operation()
    except ApplicationToolError:
        raise
    except Phase02Error as error:
        raise ApplicationToolError(error) from None
    except PydanticValidationError:
        raise ApplicationToolError(INVALID_REQUEST) from None
    except Exception:
        log_internal_error(tool_name)
        raise ApplicationToolError(SAFE_INTERNAL) from None


def _application_error_from_tool_error(tool_name: str, error: ToolError) -> ApplicationToolError:
    parsed = parse_application_error_text(str(error))
    if parsed is not None:
        return ApplicationToolError(
            Phase02Error(parsed["code"], parsed["detail"], parsed["action"])
        )
    cause: BaseException | None = error.__cause__
    while cause is not None:
        if isinstance(cause, ApplicationToolError):
            return cause
        if isinstance(cause, Phase02Error):
            return ApplicationToolError(cause)
        if isinstance(cause, PydanticValidationError):
            return ApplicationToolError(INVALID_REQUEST)
        cause = cause.__cause__
    log_internal_error(tool_name)
    return ApplicationToolError(SAFE_INTERNAL)


def _result_error_text(result: object) -> str:
    blocks = getattr(result, "content", []) or []
    texts = [block.text for block in blocks if isinstance(block, TextContent)]
    return "\n".join(texts)


def _sanitize_call_result(tool_name: str, result: object) -> object:
    if not getattr(result, "is_error", False):
        return result
    text = _result_error_text(result)
    if parse_application_error_text(text) is not None:
        return result
    log_internal_error(tool_name)
    controlled = ApplicationToolError(SAFE_INTERNAL)
    return CallToolResult(content=[TextContent(type="text", text=str(controlled))], is_error=True)


def install_mcp_error_boundary(server: Any) -> None:
    """Keep SDK argument/output validation failures from leaking exception text."""

    manager = server._tool_manager
    original_manager_call = manager.call_tool
    original_handle = server._handle_call_tool

    async def call_tool(
        name: str,
        arguments: dict[str, Any],
        context: Any,
        convert_result: bool = False,
    ) -> Any:
        try:
            return await original_manager_call(name, arguments, context, convert_result)
        except ApplicationToolError as error:
            raise ToolError(str(error)) from None
        except ToolError as error:
            raise ToolError(str(_application_error_from_tool_error(name, error))) from None
        except Exception:
            log_internal_error(name)
            raise ToolError(str(ApplicationToolError(SAFE_INTERNAL))) from None

    async def handle_call_tool(ctx: Any, params: Any) -> Any:
        result = await original_handle(ctx, params)
        return _sanitize_call_result(getattr(params, "name", "unknown"), result)

    manager.call_tool = call_tool
    server._handle_call_tool = handle_call_tool
