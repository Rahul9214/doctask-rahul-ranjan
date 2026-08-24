import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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
  window.history.replaceState(null, "", "#overview");
  window.localStorage.clear();
});

function pageNamed(title: string) {
  const heading = screen.getByRole("heading", { name: title, level: 1 });
  const page = heading.closest(".page");
  if (!(page instanceof HTMLElement)) {
    throw new Error(`${title} page was not found`);
  }
  return within(page);
}

describe("App", () => {
  it("shows the product dashboard while backend checks are pending", () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise<Response>(() => undefined)),
    );

    render(<App />);

    expect(
      screen.getByRole("heading", { name: "Project Assurance Register" }),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Checking").length).toBeGreaterThan(0);
    expect(
      screen.getByText(
        "The analyst that never sleeps — with a human at the gate.",
      ),
    ).toBeInTheDocument();
  });

  it("shows real overview state and system metadata", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const path = String(input);
        if (path.endsWith("/corpora")) {
          return Promise.resolve(
            jsonResponse([
              {
                id: "corpus-1",
                name: "Aurora Delivery Assurance",
                domain: "software_delivery",
                declared_formats: ["txt"],
                created_at: "2026-08-20T00:00:00Z",
              },
            ]),
          );
        }
        if (path.endsWith("/sources")) {
          return Promise.resolve(jsonResponse([{ id: "source-1" }]));
        }
        if (path.endsWith("/register")) {
          return Promise.resolve(jsonResponse({ id: "register-1" }));
        }
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

    expect(await screen.findByText("System ready")).toBeInTheDocument();
    expect(
      await screen.findByText("Across loaded corpora"),
    ).toBeInTheDocument();
    expect(screen.getByText("Loaded corpora")).toBeInTheDocument();
    expect(screen.getByText("Source documents")).toBeInTheDocument();
    expect(screen.getByText("Current registers")).toBeInTheDocument();
    expect(screen.getByText("Selected workflow")).toBeInTheDocument();
    expect(screen.queryByText("No list API")).not.toBeInTheDocument();
    expect(screen.queryByText(/Agent runs/)).not.toBeInTheDocument();
    expect(screen.queryByText("View all corpora")).not.toBeInTheDocument();
    await user.click(screen.getAllByRole("button", { name: "System" })[0]);
    expect(
      await screen.findByRole("heading", { name: "System" }),
    ).toBeInTheDocument();
    expect(screen.getByText("0.1.0")).toBeInTheDocument();
    expect(screen.getAllByText("Not reported").length).toBeGreaterThan(0);
    expect(
      screen.queryByText("software-project-assurance.v1"),
    ).not.toBeInTheDocument();
    expect(screen.getByText("Auto approval")).toBeInTheDocument();
    expect(screen.getByText("Auto publish")).toBeInTheDocument();
    expect(screen.getAllByText("Disabled").length).toBeGreaterThan(1);
    expect(screen.queryByText(version.current_phase)).not.toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "MCP", level: 1 }),
    ).not.toBeInTheDocument();
  });

  it("keeps a large corpus list compact on Overview", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const path = String(input);
        if (path.endsWith("/corpora")) {
          return Promise.resolve(
            jsonResponse(
              Array.from({ length: 8 }, (_, index) => ({
                id: `corpus-${index + 1}`,
                name: `Delivery Corpus ${index + 1}`,
                domain: "software_delivery",
                declared_formats: ["txt"],
                created_at: "2026-08-20T00:00:00Z",
              })),
            ),
          );
        }
        if (path.endsWith("/sources")) {
          return Promise.resolve(jsonResponse([{ id: "source-1" }]));
        }
        if (path.endsWith("/register")) {
          return Promise.resolve(jsonResponse({ id: "register-1" }));
        }
        if (path.endsWith("/version")) {
          return Promise.resolve(jsonResponse(version));
        }
        return Promise.resolve(
          jsonResponse({
            status: "ready",
            checks: { database: { status: "ready" } },
          }),
        );
      }),
    );

    render(<App />);
    expect(await screen.findByText("Delivery Corpus 1")).toBeInTheDocument();
    expect(screen.getByText("Delivery Corpus 6")).toBeInTheDocument();
    expect(screen.queryByText("Delivery Corpus 7")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "View all corpora" }));
    expect(screen.getByText("Delivery Corpus 8")).toBeInTheDocument();
  });

  it("shows an actionable dependency-unavailable state", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const path = String(input);
        if (path.endsWith("/corpora")) {
          return Promise.resolve(jsonResponse([]));
        }
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
    await user.click(screen.getAllByRole("button", { name: "System" })[0]);
    expect(
      await screen.findByText("Dependency unavailable"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("PostgreSQL connection failed."),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Verify PostgreSQL is running/),
    ).toBeInTheDocument();
  });

  it("collapses the sidebar and navigates between all product sections", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const path = String(input);
        if (path.endsWith("/corpora")) {
          return Promise.resolve(jsonResponse([]));
        }
        if (path.endsWith("/version")) {
          return Promise.resolve(jsonResponse(version));
        }
        return Promise.resolve(
          jsonResponse({
            status: "ready",
            checks: {
              database: { status: "ready" },
              pgvector: { status: "ready" },
            },
          }),
        );
      }),
    );

    render(<App />);

    expect(document.querySelector(".app-shell")).toBeInTheDocument();
    expect(document.querySelector(".sidebar")).toHaveClass("sidebar--fixed");
    const menuToggle = screen.getByRole("button", {
      name: "Open navigation",
      hidden: true,
    });
    expect(menuToggle).toHaveAttribute("aria-expanded", "false");
    expect(menuToggle).toHaveAttribute("aria-controls", "mobile-navigation");
    const collapse = screen.getByRole("button", { name: "Collapse sidebar" });
    await user.click(collapse);
    expect(document.querySelector(".app-shell")).toHaveClass(
      "app-shell--collapsed",
    );
    const expand = screen.getByRole("button", { name: "Expand sidebar" });
    expect(expand).toHaveAttribute("aria-expanded", "false");
    expect(
      screen.getAllByRole("button", { name: "Overview" })[0],
    ).toHaveAttribute("aria-describedby", "nav-tooltip-overview");

    for (const [button, heading] of [
      ["Agent Run", "Agent Run"],
      ["Human Review", "Human Review"],
      ["Register", "Published Register"],
      ["System", "System"],
      ["Overview", "Project Assurance Register"],
    ]) {
      await user.click(screen.getAllByRole("button", { name: button })[0]);
      expect(
        screen.getByRole("heading", { name: heading, level: 1 }),
      ).toBeInTheDocument();
    }
    await user.click(
      screen.getAllByRole("button", { name: "MCP machine interface" })[0],
    );
    expect(
      screen.getByRole("heading", { name: "MCP", level: 1 }),
    ).toBeInTheDocument();
    expect(screen.getAllByRole("heading", { name: "MCP" })).toHaveLength(1);
    expect(screen.getByText("View 20 operations")).toBeInTheDocument();
    expect(
      screen.getByText("Standard input/output (stdio)"),
    ).toBeInTheDocument();
    expect(screen.getByText("Auto approval")).toBeInTheDocument();
    expect(screen.getAllByText("Disabled").length).toBeGreaterThan(1);
  });

  it("exposes collapsed icon-rail tooltips without duplicating expanded labels", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const path = String(input);
        if (path.endsWith("/corpora")) {
          return Promise.resolve(jsonResponse([]));
        }
        if (path.endsWith("/version")) {
          return Promise.resolve(jsonResponse(version));
        }
        return Promise.resolve(
          jsonResponse({
            status: "ready",
            checks: { database: { status: "ready" } },
          }),
        );
      }),
    );

    render(<App />);
    const navItems: Array<{ name: string; tooltipId: string; label: string }> =
      [
        {
          name: "Overview",
          tooltipId: "nav-tooltip-overview",
          label: "Overview",
        },
        {
          name: "Agent Run",
          tooltipId: "nav-tooltip-agent-run",
          label: "Agent Run",
        },
        {
          name: "Human Review",
          tooltipId: "nav-tooltip-human-review",
          label: "Human Review",
        },
        {
          name: "Register",
          tooltipId: "nav-tooltip-register",
          label: "Register",
        },
        { name: "System", tooltipId: "nav-tooltip-system", label: "System" },
        {
          name: "MCP machine interface",
          tooltipId: "nav-tooltip-mcp",
          label: "MCP",
        },
      ];

    for (const item of navItems) {
      const button = screen.getAllByRole("button", { name: item.name })[0];
      expect(button).not.toHaveAttribute("aria-describedby");
      expect(document.getElementById(item.tooltipId)).toHaveAttribute(
        "role",
        "tooltip",
      );
    }

    await user.click(screen.getByRole("button", { name: "Collapse sidebar" }));
    expect(document.querySelector(".app-shell")).toHaveClass(
      "app-shell--collapsed",
    );

    for (const item of navItems) {
      const button = screen.getAllByRole("button", { name: item.name })[0];
      expect(button).toHaveAttribute("aria-describedby", item.tooltipId);
      const tooltip = document.getElementById(item.tooltipId);
      expect(tooltip).toHaveAttribute("role", "tooltip");
      expect(tooltip).toHaveTextContent(item.label);
      expect(
        document.querySelector(
          `.app-shell--collapsed .sidebar .nav-item-label`,
        ),
      ).toBeTruthy();
      expect(button.querySelector(".nav-item-label")).toHaveTextContent(
        item.label,
      );
    }

    const overview = screen.getAllByRole("button", { name: "Overview" })[0];
    expect(overview).toHaveAttribute("aria-current", "page");
    overview.focus();
    expect(overview).toHaveFocus();
    expect(overview).toHaveAttribute("aria-describedby", "nav-tooltip-overview");

    await user.click(screen.getByRole("button", { name: "Expand sidebar" }));
    expect(
      screen.getAllByRole("button", { name: "Overview" })[0],
    ).not.toHaveAttribute("aria-describedby");
  });

  it("opens and closes the mobile navigation drawer", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const path = String(input);
        if (path.endsWith("/corpora")) {
          return Promise.resolve(jsonResponse([]));
        }
        if (path.endsWith("/version")) {
          return Promise.resolve(jsonResponse(version));
        }
        return Promise.resolve(
          jsonResponse({
            status: "ready",
            checks: { database: { status: "ready" } },
          }),
        );
      }),
    );

    render(<App />);
    const openNav = () =>
      screen.getByRole("button", { name: "Open navigation", hidden: true });
    fireEvent.click(openNav());
    const drawer = document.getElementById("mobile-navigation");
    expect(drawer).toHaveClass("mobile-drawer--open");
    expect(
      screen.getByRole("button", { name: "Close navigation", hidden: true }),
    ).toHaveAttribute("aria-expanded", "true");
    expect(
      within(drawer as HTMLElement).getByRole("button", {
        name: "Overview",
        hidden: true,
      }),
    ).toHaveAttribute("aria-current", "page");
    expect(within(drawer as HTMLElement).getByText("Overview")).toBeVisible();
    expect(
      within(drawer as HTMLElement).getByText("Human Review"),
    ).toBeVisible();
    expect(within(drawer as HTMLElement).getByText("MCP")).toBeVisible();
    fireEvent.click(
      within(drawer as HTMLElement).getByRole("button", {
        name: "Agent Run",
        hidden: true,
      }),
    );
    expect(
      screen.getByRole("heading", { name: "Agent Run", level: 1 }),
    ).toBeInTheDocument();
    expect(document.getElementById("mobile-navigation")).not.toHaveClass(
      "mobile-drawer--open",
    );

    fireEvent.click(openNav());
    fireEvent.click(
      screen.getByRole("button", { name: "Dismiss navigation", hidden: true }),
    );
    expect(document.getElementById("mobile-navigation")).not.toHaveClass(
      "mobile-drawer--open",
    );
    fireEvent.click(openNav());
    await user.keyboard("{Escape}");
    expect(document.getElementById("mobile-navigation")).not.toHaveClass(
      "mobile-drawer--open",
    );
    expect(openNav()).toHaveFocus();
  });

  it("renders corpus options from API data and distinguishes duplicate names", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const path = String(input);
        if (path.endsWith("/corpora")) {
          return Promise.resolve(
            jsonResponse([
              {
                id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaa6e8d",
                name: "Shared Delivery Corpus",
                domain: "software_delivery",
                declared_formats: ["txt"],
                created_at: "2026-08-20T00:00:00Z",
              },
              {
                id: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbb2647",
                name: "Shared Delivery Corpus",
                domain: "software_delivery",
                declared_formats: ["md"],
                created_at: "2026-08-21T00:00:00Z",
              },
            ]),
          );
        }
        if (path.endsWith("/sources")) {
          return Promise.resolve(
            jsonResponse([
              { id: "source-1", logical_name: "Charter" },
              { id: "source-2", logical_name: "Status" },
            ]),
          );
        }
        if (path.endsWith("/version")) {
          return Promise.resolve(jsonResponse(version));
        }
        return Promise.resolve(
          jsonResponse({
            status: "ready",
            checks: { database: { status: "ready" } },
          }),
        );
      }),
    );

    render(<App />);
    await user.click(screen.getAllByRole("button", { name: "Agent Run" })[0]);
    const workflow = pageNamed("Agent Run");
    const corpus = await workflow.findByLabelText("Corpus");
    expect(corpus).toHaveAttribute("aria-haspopup", "listbox");
    await user.click(corpus);
    expect(
      await workflow.findByRole("option", {
        name: /Shared Delivery Corpus · …aaaaaaaa6e8d/,
      }),
    ).toBeInTheDocument();
    expect(
      workflow.getByRole("option", {
        name: /Shared Delivery Corpus · …bbbbbbbb2647/,
      }),
    ).toBeInTheDocument();
    expect(
      workflow.queryByText("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaa6e8d"),
    ).not.toBeInTheDocument();
    expect(corpus).not.toHaveTextContent("Aurora Control Hub");
    expect(corpus).not.toHaveTextContent("Harbor Station");
  });

  it("preserves corpus and examination context from an agent run into human review", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input);
        const method = init?.method ?? "GET";
        if (path.endsWith("/corpora")) {
          return Promise.resolve(
            jsonResponse([
              {
                id: "corpus-1",
                name: "Delivery Corpus",
                domain: "software_delivery",
                declared_formats: ["txt"],
                created_at: "2026-08-20T00:00:00Z",
              },
            ]),
          );
        }
        if (path.endsWith("/sources")) {
          return Promise.resolve(jsonResponse([{ id: "source-1" }]));
        }
        if (path.endsWith("/events")) {
          return Promise.resolve(jsonResponse([]));
        }
        if (path.endsWith("/usage")) {
          return Promise.resolve(
            jsonResponse({
              total_duration_ms: 1,
              total_model_operation_count: 0,
              total_model_attempt_count: 0,
              estimated_cost_usd: 0,
              cost_basis: "zero_deterministic",
              pricing_basis: "none",
              stages: [],
            }),
          );
        }
        if (path.endsWith("/review-sessions/session-1")) {
          return Promise.resolve(
            jsonResponse({
              id: "session-1",
              status: "waiting_for_review",
              pending_count: 1,
              completion_allowed: false,
            }),
          );
        }
        if (path.endsWith("/revisions/current")) {
          return Promise.resolve(
            jsonResponse(
              {
                code: "corpus_revision_not_found",
                detail: "None",
              },
              false,
            ),
          );
        }
        if (
          path.endsWith("/workflow-runs/run-1") &&
          !path.endsWith("/resume")
        ) {
          return Promise.resolve(
            jsonResponse({
              id: "run-1",
              corpus_id: "corpus-1",
              status: "waiting_for_review",
              current_stage: "wait_for_review",
              resume_count: 0,
              analysis_run_id: "analysis-1",
              examination_run_id: "exam-1",
              review_session_id: "session-1",
              error_code: null,
              error_detail: null,
              error_action: null,
            }),
          );
        }
        if (method === "POST" && path.endsWith("/review-sessions")) {
          return Promise.resolve(
            jsonResponse({
              id: "session-1",
              corpus_id: "corpus-1",
              examination_run_id: "exam-1",
              status: "waiting_for_review",
              pending_count: 1,
              approved_count: 0,
              rejected_count: 0,
              edited_count: 0,
              required_item_count: 1,
              optional_item_count: 0,
              completion_allowed: false,
              completed_at: null,
            }),
          );
        }
        if (path.endsWith("/items")) {
          return Promise.resolve(jsonResponse([]));
        }
        if (path.endsWith("/version")) {
          return Promise.resolve(jsonResponse(version));
        }
        return Promise.resolve(
          jsonResponse({
            status: "ready",
            checks: { database: { status: "ready" } },
          }),
        );
      }),
    );

    render(<App />);
    await user.click(screen.getAllByRole("button", { name: "Agent Run" })[0]);
    const workflow = pageNamed("Agent Run");
    await user.click(await workflow.findByLabelText("Corpus"));
    await user.click(
      await workflow.findByRole("option", { name: /Delivery Corpus/ }),
    );
    await user.click(workflow.getByText("Advanced lookup"));
    await user.type(workflow.getByLabelText("Workflow run ID"), "run-1");
    await user.click(workflow.getByRole("button", { name: "Load workflow" }));
    expect(
      await workflow.findByRole("button", { name: "Open human review" }),
    ).toBeInTheDocument();
    await user.click(
      workflow.getByRole("button", { name: "Open human review" }),
    );
    expect(
      await screen.findByRole("heading", { name: "Human Review", level: 1 }),
    ).toBeInTheDocument();
    const review = pageNamed("Human Review");
    expect(review.getByLabelText("Corpus")).toHaveAttribute(
      "data-corpus-id",
      "corpus-1",
    );
    expect(review.getByLabelText("Examination run ID")).toHaveValue("exam-1");
    await user.click(screen.getAllByRole("button", { name: "Register" })[0]);
    expect(
      await screen.findByRole("heading", {
        name: "Published Register",
        level: 1,
      }),
    ).toBeInTheDocument();
    const register = pageNamed("Published Register");
    expect(register.getByLabelText("Corpus")).toHaveAttribute(
      "data-corpus-id",
      "corpus-1",
    );
    expect(register.getByLabelText("Review session")).toHaveValue("session-1");
  });
});
