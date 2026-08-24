import { describe, expect, it } from "vitest";

import { MCP_TOOL_COUNT, MCP_TOOL_GROUPS } from "./mcpTools";

describe("mcpTools", () => {
  it("counts tools from the compile-time registry rather than a hardcoded literal", () => {
    const counted = MCP_TOOL_GROUPS.reduce(
      (total, group) => total + group.tools.length,
      0,
    );
    expect(MCP_TOOL_COUNT).toBe(counted);
    expect(MCP_TOOL_COUNT).toBeGreaterThan(0);
    expect(MCP_TOOL_GROUPS.flatMap((group) => [...group.tools])).toEqual(
      expect.arrayContaining(["approve_review_item", "publish_register"]),
    );
  });
});
