import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "./App";

const version = {
  app_version: "0.1.0",
  current_phase: "Phase 01 — Development Foundation",
  implementation_status: "Task 1 business workflow is not implemented yet.",
};

function jsonResponse(body: unknown, ok = true): Response {
  return {
    ok,
    json: async () => body,
  } as Response;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("App", () => {
  it("shows a loading state while backend checks are pending", () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise<Response>(() => undefined)),
    );

    render(<App />);

    expect(
      screen.getByRole("heading", { name: "Checking backend status" }),
    ).toBeInTheDocument();
  });

  it("shows the ready state and phase metadata", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const path = String(input);
        if (path.endsWith("/version")) {
          return Promise.resolve(jsonResponse(version));
        }
        if (path.endsWith("/ready")) {
          return Promise.resolve(
            jsonResponse({
              status: "ready",
              checks: {
                database: { status: "ready" },
                pgvector: { status: "ready", version: "0.8.1" },
              },
            }),
          );
        }
        return Promise.resolve(jsonResponse({ status: "alive" }));
      }),
    );

    render(<App />);

    expect(
      await screen.findByRole("heading", { name: "Foundation ready" }),
    ).toBeInTheDocument();
    expect(screen.getByText("0.1.0")).toBeInTheDocument();
    expect(
      screen.getByText("Phase 01 — Development Foundation"),
    ).toBeInTheDocument();
  });

  it("shows an actionable dependency-unavailable state", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const path = String(input);
        if (path.endsWith("/version")) {
          return Promise.resolve(jsonResponse(version));
        }
        if (path.endsWith("/ready")) {
          return Promise.resolve(
            jsonResponse(
              {
                status: "unavailable",
                checks: {
                  database: {
                    status: "unavailable",
                    detail: "PostgreSQL connection failed.",
                    action: "Verify PostgreSQL is running.",
                  },
                },
              },
              false,
            ),
          );
        }
        return Promise.resolve(jsonResponse({ status: "alive" }));
      }),
    );

    render(<App />);

    expect(
      await screen.findByRole("heading", { name: "Dependency unavailable" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("PostgreSQL connection failed."),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Verify PostgreSQL is running/),
    ).toBeInTheDocument();
  });

  it("states the current implemented review scope", () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise<Response>(() => undefined)),
    );

    render(<App />);

    expect(
      screen.getByText(
        "Understand, Examine, item-level human review, durable resume, focused incremental updates, MCP business operations, approved-only register publication, and local Compose deployment are implemented. Hosted cloud deployment is not.",
      ),
    ).toBeInTheDocument();
  });
});
