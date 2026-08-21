from __future__ import annotations

import json
import os
import sys
import tempfile
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, TextIO, TypedDict, cast
from uuid import UUID

from helpers import make_incremental, make_workflow
from mcp import Client
from mcp.client.stdio import StdioServerParameters, stdio_client
from sqlalchemy.ext.asyncio import AsyncEngine

from app.config import Settings
from app.mcp_errors import parse_application_error_text
from app.mcp_server import create_mcp_server
from app.runtime import ApplicationServices
from app.services import Phase02Service
from app.storage import LocalFileStorage

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def application_services_from_phase02(phase02: Phase02Service) -> ApplicationServices:
    workflow = make_workflow(phase02)
    incremental = make_incremental(phase02, review=workflow.review)
    engine = cast(AsyncEngine, phase02.session_factory.kw["bind"])
    return ApplicationServices(
        settings=Settings(),
        engine=engine,
        session_factory=phase02.session_factory,
        phase02=phase02,
        understand=workflow.examine.understand,
        examine=workflow.examine,
        review=workflow.review,
        workflow=workflow,
        incremental=incremental,
        watcher=None,
        model_adapter=workflow.adapter,
    )


class ApplicationErrorCall(TypedDict):
    raw_text: str
    code: str
    detail: str
    action: str


def mapping(value: object) -> dict[str, Any]:
    assert isinstance(value, dict)
    return value


def mappings(value: object) -> list[dict[str, Any]]:
    assert isinstance(value, list)
    return [mapping(item) for item in value]


def json_arguments(arguments: Mapping[str, object]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, value in arguments.items():
        if isinstance(value, UUID):
            payload[key] = str(value)
        else:
            payload[key] = value
    return payload


def tool_content_text(result: Any) -> str:
    chunks: list[str] = []
    blocks = getattr(result, "content", []) or []
    for block in blocks:
        text = getattr(block, "text", None)
        if isinstance(text, str):
            chunks.append(text)
        else:
            chunks.append(repr(block))
    return "\n".join(chunks)


def tool_result_raw_text(result: Any) -> str:
    """Complete MCP SDK returned payload for leak assertions, not parsed fields only."""

    chunks = [tool_content_text(result)]
    structured = getattr(result, "structured_content", None)
    if structured is not None:
        chunks.append(json.dumps(structured, default=str))
    meta = getattr(result, "meta", None)
    if meta is not None:
        chunks.append(repr(meta))
    return "\n".join(chunks)


def tool_error_text(result: Any) -> str:
    return tool_result_raw_text(result)


def require_application_error(result: Any) -> ApplicationErrorCall:
    assert result.is_error is True
    parsed = parse_application_error_text(tool_content_text(result))
    assert parsed is not None
    raw_text = tool_result_raw_text(result)
    lowered = raw_text.casefold()
    assert "traceback" not in lowered
    assert "password" not in lowered
    return {
        "raw_text": raw_text,
        "code": parsed["code"],
        "detail": parsed["detail"],
        "action": parsed["action"],
    }


async def call_ok(
    client: Client, name: str, arguments: Mapping[str, object] | None = None
) -> dict[str, Any]:
    result = await client.call_tool(name, json_arguments(arguments or {}))
    if result.is_error:
        raise AssertionError(f"{name} failed: {tool_error_text(result)}")
    return mapping(result.structured_content)


async def call_err(
    client: Client, name: str, arguments: Mapping[str, object] | None = None
) -> ApplicationErrorCall:
    result = await client.call_tool(name, json_arguments(arguments or {}))
    return require_application_error(result)


@asynccontextmanager
async def in_memory_mcp(
    phase02: Phase02Service,
) -> AsyncIterator[tuple[Client, ApplicationServices]]:
    services = application_services_from_phase02(phase02)
    server = create_mcp_server(services)
    async with Client(server) as client:
        yield client, services


def stdio_server_parameters(
    storage: LocalFileStorage,
    extra_env: Mapping[str, str] | None = None,
) -> StdioServerParameters:
    env = {key: value for key, value in os.environ.items()}
    env["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
    env["SOURCE_STORAGE_PATH"] = str(storage.root)
    env["MODEL_PROVIDER"] = "deterministic"
    env["PYTHONUNBUFFERED"] = "1"
    env.pop("WATCH_INPUT_PATH", None)
    if extra_env:
        env.update(extra_env)
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "app.mcp_server"],
        env=env,
        cwd=str(BACKEND_ROOT),
    )


@asynccontextmanager
async def stdio_mcp(
    storage: LocalFileStorage,
    extra_env: Mapping[str, str] | None = None,
    errlog: TextIO | None = None,
) -> AsyncIterator[Client]:
    params = stdio_server_parameters(storage, extra_env=extra_env)
    transport = stdio_client(params) if errlog is None else stdio_client(params, errlog=errlog)
    async with Client(transport) as client:
        yield client


@asynccontextmanager
async def stdio_mcp_capturing_stderr(
    storage: LocalFileStorage,
    extra_env: Mapping[str, str] | None = None,
) -> AsyncIterator[tuple[Client, Path]]:
    with tempfile.NamedTemporaryFile("w+", encoding="utf-8", delete=False) as handle:
        path = Path(handle.name)
        captured_errlog: TextIO = cast(TextIO, handle)
        async with stdio_mcp(storage, extra_env=extra_env, errlog=captured_errlog) as client:
            yield client, path
        handle.flush()
