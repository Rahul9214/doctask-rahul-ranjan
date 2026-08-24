import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import SystemPanel from "./SystemPanel";
import { MCP_TOOL_COUNT } from "./mcpTools";

const readyStatus = {
  kind: "ready" as const,
  version: {
    app_version: "0.1.0",
    current_phase: "Phase 10 — Final Delivery",
    implementation_status: "hidden",
  },
  checks: {
    database: { status: "ready" },
    pgvector: { status: "ready", version: "0.8.1" },
  },
};

describe("SystemPanel", () => {
  it("uses runtime checks and a compact MCP summary on System", () => {
    render(
      <SystemPanel
        status={readyStatus}
        corpora={[]}
        corporaLoading={false}
        onOpenMcp={vi.fn()}
      />,
    );

    expect(screen.getByText("0.1.0")).toBeInTheDocument();
    expect(screen.getByText("Version 0.8.1")).toBeInTheDocument();
    expect(screen.getAllByText("Ready").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Not reported").length).toBeGreaterThan(0);
    expect(screen.getByText("Operations")).toBeInTheDocument();
    expect(screen.getByText(String(MCP_TOOL_COUNT))).toBeInTheDocument();
    expect(screen.getByText("Auto approval")).toBeInTheDocument();
    expect(screen.getByText("Auto publish")).toBeInTheDocument();
    expect(screen.getAllByText("Disabled").length).toBeGreaterThan(1);
    expect(
      screen.queryByText("View 20 business tools"),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("View 20 operations")).not.toBeInTheDocument();
    expect(
      screen.queryByText("Phase 10 — Final Delivery"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "MCP", level: 1 }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText(/^\d+ (corpus|corpora)$/),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("Action needed")).not.toBeInTheDocument();
  });

  it("fails closed when dependency checks are absent", () => {
    render(
      <SystemPanel
        status={{
          kind: "unavailable",
          applicationAlive: false,
          message: "The backend application could not be reached.",
        }}
        corpora={[]}
        corporaLoading={false}
      />,
    );

    expect(screen.getAllByText("Unavailable").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Not reported").length).toBeGreaterThan(1);
    expect(screen.queryByText("1.0.0")).not.toBeInTheDocument();
  });

  it("keeps the MCP page to a single heading and runtime tool count", async () => {
    const user = userEvent.setup();
    render(
      <SystemPanel
        status={readyStatus}
        corpora={[]}
        corporaLoading={false}
        focusMcp
      />,
    );

    expect(screen.getAllByRole("heading", { name: "MCP" })).toHaveLength(1);
    expect(
      screen.getByText("Standard input/output (stdio)"),
    ).toBeInTheDocument();
    expect(screen.getByText(String(MCP_TOOL_COUNT))).toBeInTheDocument();
    expect(screen.getByText("Auto approval")).toBeInTheDocument();
    expect(screen.getAllByText("Disabled").length).toBeGreaterThan(1);
    await user.click(screen.getByText(`View ${MCP_TOOL_COUNT} operations`));
    expect(screen.getByText("approve_review_item")).toBeInTheDocument();
    expect(screen.getByText("publish_register")).toBeInTheDocument();
  });
});
