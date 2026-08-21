from __future__ import annotations

import json
import os
import sys

from mcp import Client
from mcp.client.stdio import StdioServerParameters, stdio_client

from app.mcp_server import BUSINESS_TOOL_NAMES


async def probe() -> dict[str, object]:
    env = {key: value for key, value in os.environ.items()}
    env["PYTHONUNBUFFERED"] = "1"
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "app.mcp_server"],
        env=env,
    )
    async with Client(stdio_client(params)) as client:
        listed = await client.list_tools()
        names = [tool.name for tool in listed.tools]
        return {
            "transport": "stdio",
            "tool_count": len(names),
            "tools": names,
            "expected_present": all(name in names for name in BUSINESS_TOOL_NAMES),
        }


def main() -> None:
    from anyio import run

    result = run(probe)
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    if not result["expected_present"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
