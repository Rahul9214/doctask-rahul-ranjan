import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import ReviewPanel from "./ReviewPanel";

const session = {
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
};

const pendingItem = {
  id: "item-1",
  finding_id: "finding-1",
  rule_id: "spa.milestone.production-readiness",
  title: "Production readiness date must be consistent",
  outcome: "fail",
  severity: "high",
  message: "Cited dates conflict.",
  structured_reason: {
    category: "milestone_date",
    subject_key: "production_readiness",
  },
  evidence_kind: "grounded_facts",
  review_required: true,
  review_status: "pending",
  proposed_content: { rule_id: "spa.milestone.production-readiness" },
  edited_content: null,
  edited_content_is_reviewer_authored: false,
  citations: [
    {
      source_version_id: "version-1",
      source_sha256: "a".repeat(64),
      format: "txt",
      native_locator: "lines[1-2]/block[0]",
      normalized_start: 0,
      normalized_end: 12,
      exact_quote: "Ready 2026-10-30",
      source_logical_name: "Decision Log",
      source_block_id: "block-1",
    },
    {
      source_version_id: "version-2",
      source_sha256: "b".repeat(64),
      format: "docx",
      native_locator: "paragraph[4]",
      normalized_start: 0,
      normalized_end: 12,
      exact_quote: "Ready 2026-11-14",
      source_logical_name: "Weekly Status Report",
      source_block_id: "block-2",
    },
  ],
  grounded_facts: [
    {
      id: "fact-1",
      category: "milestone_date",
      subject_key: "production_readiness",
      normalized_value: "2026-10-30",
      support_status: "supported",
    },
    {
      id: "fact-2",
      category: "milestone_date",
      subject_key: "production_readiness",
      normalized_value: "2026-11-14",
      support_status: "supported",
    },
  ],
  contradictions: [
    {
      id: "contradiction-1",
      contradiction_type: "conflicting_values",
      reason: "Two grounded sources give different readiness dates.",
      status: "open",
      fact_a: {
        id: "fact-1",
        category: "milestone_date",
        subject_key: "production_readiness",
        normalized_value: "2026-10-30",
        support_status: "supported",
      },
      fact_b: {
        id: "fact-2",
        category: "milestone_date",
        subject_key: "production_readiness",
        normalized_value: "2026-11-14",
        support_status: "supported",
      },
    },
  ],
  decisions: [],
};

function jsonResponse(body: unknown, ok = true, status = 200): Response {
  return {
    ok,
    status,
    json: async () => body,
  } as Response;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

async function openReview() {
  const user = userEvent.setup();
  render(<ReviewPanel />);
  await user.type(screen.getByLabelText("Corpus"), "corpus-1");
  expect(
    screen.getByText("Advanced lookup").closest("details"),
  ).not.toHaveAttribute("open");
  await user.click(screen.getByText("Advanced lookup"));
  await user.type(screen.getByLabelText("Examination run ID"), "exam-1");
  await user.click(screen.getByRole("button", { name: "Open review" }));
  return user;
}

describe("ReviewPanel", () => {
  it("renders pending review items with evidence and blocks completion", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const path = String(input);
        if (path.endsWith("/review-sessions") && !path.includes("/items")) {
          return Promise.resolve(jsonResponse(session, true, 201));
        }
        if (path.endsWith("/items")) {
          return Promise.resolve(jsonResponse([pendingItem]));
        }
        return Promise.resolve(
          jsonResponse({ detail: "unexpected" }, false, 500),
        );
      }),
    );

    await openReview();

    expect(
      await screen.findByRole("heading", {
        name: "Production readiness date must be consistent",
      }),
    ).toBeInTheDocument();
    expect(screen.getAllByText(/Ready 2026-10-30/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Decision Log/).length).toBeGreaterThan(0);
    expect(screen.getByText("Weekly Status Report")).toBeInTheDocument();
    expect(screen.getByText("Contradictory evidence")).toBeInTheDocument();
    expect(screen.getByText("2026-10-30")).toBeInTheDocument();
    expect(screen.getByText("2026-11-14")).toBeInTheDocument();
    expect(screen.queryByText(/Ready 2026-11-14/)).not.toBeInTheDocument();
    expect(screen.getByText("FAIL")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Complete review" }),
    ).toBeDisabled();
  });

  it("renders all assurance outcomes and progressively discloses audit details", async () => {
    const items = [
      pendingItem,
      {
        ...pendingItem,
        id: "item-pass",
        finding_id: "finding-pass",
        rule_id: "spa.pass",
        title: "Delivery owner is identified",
        outcome: "pass",
        severity: "low",
        message: "A delivery owner is established.",
        contradictions: [],
        citations: [],
        review_required: false,
      },
      {
        ...pendingItem,
        id: "item-warning",
        finding_id: "finding-warning",
        rule_id: "spa.warning",
        title: "Status requires attention",
        outcome: "warning",
        severity: "medium",
        message: "Delivery status is amber.",
        contradictions: [],
        citations: [],
        review_required: false,
      },
      {
        ...pendingItem,
        id: "item-unknown",
        finding_id: "finding-unknown",
        rule_id: "spa.unknown",
        title: "Budget owner is identified",
        outcome: "unknown",
        severity: "medium",
        message: "No supported source establishes a budget owner.",
        contradictions: [],
        citations: [],
        review_required: false,
      },
    ];
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const path = String(input);
        if (path.endsWith("/review-sessions") && !path.includes("/items")) {
          return Promise.resolve(jsonResponse(session, true, 201));
        }
        if (path.endsWith("/items")) {
          return Promise.resolve(jsonResponse(items));
        }
        return Promise.resolve(
          jsonResponse({ detail: "unexpected" }, false, 500),
        );
      }),
    );

    const user = await openReview();
    expect(await screen.findByText("PASS")).toBeInTheDocument();
    expect(screen.getByText("FAIL")).toBeInTheDocument();
    expect(screen.getByText("WARNING")).toBeInTheDocument();
    expect(screen.getAllByText("UNKNOWN").length).toBeGreaterThan(0);
    expect(screen.getByText("No grounded evidence found")).toBeInTheDocument();
    expect(screen.getByText("No citation claimed.")).toBeInTheDocument();
    expect(
      screen.queryByText("spa.milestone.production-readiness"),
    ).not.toBeInTheDocument();

    await user.click(screen.getAllByRole("button", { name: "Details" })[0]);
    expect(
      screen.getByText("spa.milestone.production-readiness"),
    ).toBeInTheDocument();
  });

  it("records approve, reject, and reviewer-authored edit actions", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      const method = init?.method ?? "GET";
      if (method === "POST" && path.endsWith("/review-sessions")) {
        return Promise.resolve(jsonResponse(session, true, 201));
      }
      if (method === "GET" && path.endsWith("/items")) {
        return Promise.resolve(jsonResponse([pendingItem]));
      }
      if (method === "POST" && path.endsWith("/decisions")) {
        const payload = JSON.parse(String(init?.body)) as { action: string };
        const nextStatus =
          payload.action === "approve"
            ? "approved"
            : payload.action === "reject"
              ? "rejected"
              : "edited";
        return Promise.resolve(
          jsonResponse(
            {
              session: {
                ...session,
                pending_count: 0,
                completion_allowed: true,
                approved_count: payload.action === "approve" ? 1 : 0,
                rejected_count: payload.action === "reject" ? 1 : 0,
                edited_count: payload.action === "edit" ? 1 : 0,
              },
              item: {
                ...pendingItem,
                review_status: nextStatus,
                edited_content:
                  payload.action === "edit"
                    ? "Reviewer restates the gap."
                    : null,
                edited_content_is_reviewer_authored: payload.action === "edit",
              },
            },
            true,
            201,
          ),
        );
      }
      return Promise.resolve(
        jsonResponse({ detail: "unexpected" }, false, 500),
      );
    });
    vi.stubGlobal("fetch", fetchMock);

    const user = await openReview();
    await screen.findByRole("heading", {
      name: "Production readiness date must be consistent",
    });

    await user.click(
      screen.getByRole("button", {
        name: "Approve Production readiness date must be consistent",
      }),
    );
    expect(
      await screen.findByText(
        "approve recorded for Production readiness date must be consistent.",
      ),
    ).toBeInTheDocument();

    await user.click(
      screen.getByRole("button", {
        name: "Reject Production readiness date must be consistent",
      }),
    );
    expect(
      await screen.findByText(
        "reject recorded for Production readiness date must be consistent.",
      ),
    ).toBeInTheDocument();

    expect(
      screen.queryByLabelText("Reviewer-authored edit"),
    ).not.toBeInTheDocument();
    await user.click(
      screen.getByRole("button", {
        name: "Edit Production readiness date must be consistent",
      }),
    );
    const editBox = screen.getByLabelText("Reviewer-authored edit");
    await user.type(editBox, "Reviewer restates the gap.");
    expect(
      screen.getByRole("button", {
        name: "Submit reviewer edit for Production readiness date must be consistent",
      }),
    ).toBeDisabled();
    await user.click(
      screen.getByRole("checkbox", {
        name: /I confirm this edit is reviewer-authored/,
      }),
    );
    await user.click(
      screen.getByRole("button", {
        name: "Submit reviewer edit for Production readiness date must be consistent",
      }),
    );
    expect(
      await screen.findByText(
        "edit recorded for Production readiness date must be consistent.",
      ),
    ).toBeInTheDocument();
    expect(screen.getAllByText("NOT SYSTEM-GROUNDED").length).toBeGreaterThan(
      0,
    );

    const decisionBodies = fetchMock.mock.calls
      .filter(
        ([url, init]) =>
          String(url).endsWith("/decisions") &&
          (init as RequestInit | undefined)?.method === "POST",
      )
      .map(
        ([, init]) =>
          JSON.parse(String((init as RequestInit).body)) as {
            action: string;
            reviewer_authored_acknowledged?: boolean;
          },
      );
    expect(decisionBodies[0]).toEqual({
      action: "approve",
      decision_source: "ui",
      actor: "reviewer",
    });
    expect(decisionBodies[1]).toEqual({
      action: "reject",
      decision_source: "ui",
      actor: "reviewer",
    });
    expect(decisionBodies[2]).toEqual({
      action: "edit",
      decision_source: "ui",
      actor: "reviewer",
      edited_content: "Reviewer restates the gap.",
      reviewer_authored_acknowledged: true,
    });
  });

  it("keeps advanced lookup collapsed when a workspace examination is already selected", () => {
    render(
      <ReviewPanel
        workspace={{
          corpusId: "corpus-1",
          workflowRunId: "run-1",
          examinationRunId: "exam-1",
          reviewSessionId: "session-1",
          workflowStatus: "waiting_for_review",
          reviewStatus: "waiting_for_review",
        }}
        active={false}
      />,
    );

    expect(
      screen.getByRole("button", { name: "Open selected review" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Advanced lookup").closest("details"),
    ).not.toHaveAttribute("open");
  });

  it("shows loading and error states without stack traces", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve(
          jsonResponse(
            {
              code: "examination_run_not_found",
              detail: "The examination run was not found in this corpus.",
              action:
                "Use an examination run identifier returned for the same corpus.",
            },
            false,
            404,
          ),
        ),
      ),
    );

    const user = userEvent.setup();
    render(<ReviewPanel />);
    expect(screen.getByRole("button", { name: "Open review" })).toBeEnabled();
    await user.type(screen.getByLabelText("Corpus"), "corpus-1");
    await user.click(screen.getByText("Advanced lookup"));
    await user.type(screen.getByLabelText("Examination run ID"), "exam-1");
    await user.click(screen.getByRole("button", { name: "Open review" }));

    expect(
      await screen.findByText(
        "The examination run was not found in this corpus.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText(/traceback/i)).not.toBeInTheDocument();
    expect(
      screen.getByText(
        /Use an examination run identifier returned for the same corpus/,
      ),
    ).toBeInTheDocument();
  });

  it("disables controls while a decision is submitting and after completion", async () => {
    let finishApprove: ((value: Response) => void) | undefined;
    const approvePromise = new Promise<Response>((resolve) => {
      finishApprove = resolve;
    });
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      const method = init?.method ?? "GET";
      if (method === "POST" && path.endsWith("/review-sessions")) {
        return Promise.resolve(jsonResponse(session, true, 201));
      }
      if (method === "GET" && path.endsWith("/items")) {
        return Promise.resolve(jsonResponse([pendingItem]));
      }
      if (method === "POST" && path.endsWith("/decisions")) {
        return approvePromise;
      }
      return Promise.resolve(
        jsonResponse({ detail: "unexpected" }, false, 500),
      );
    });
    vi.stubGlobal("fetch", fetchMock);

    const user = await openReview();
    await screen.findByRole("heading", {
      name: "Production readiness date must be consistent",
    });
    await user.click(
      screen.getByRole("button", {
        name: "Approve Production readiness date must be consistent",
      }),
    );
    expect(
      screen.getByRole("button", {
        name: "Approve Production readiness date must be consistent",
      }),
    ).toBeDisabled();
    expect(screen.getByRole("button", { name: "Open review" })).toBeDisabled();
    finishApprove?.(
      jsonResponse(
        {
          session: {
            ...session,
            status: "completed",
            pending_count: 0,
            completion_allowed: false,
            approved_count: 1,
          },
          item: { ...pendingItem, review_status: "approved" },
        },
        true,
        201,
      ),
    );
    expect(
      await screen.findByText(
        "approve recorded for Production readiness date must be consistent.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", {
        name: "Approve Production readiness date must be consistent",
      }),
    ).toBeDisabled();
    expect(
      screen.queryByRole("button", { name: "Complete review" }),
    ).not.toBeInTheDocument();
  });
});
