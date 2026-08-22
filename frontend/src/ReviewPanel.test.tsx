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
  await user.type(screen.getByLabelText("Corpus ID"), "corpus-1");
  await user.type(screen.getByLabelText("Examination run ID"), "exam-1");
  await user.click(screen.getByRole("button", { name: "Open review session" }));
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
    expect(screen.getByText(/Ready 2026-10-30/)).toBeInTheDocument();
    expect(screen.getByText(/Decision Log/)).toBeInTheDocument();
    expect(screen.getByText(/outcome fail/)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Complete review session" }),
    ).toBeDisabled();
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

    const editBox = screen.getByLabelText("Reviewer-authored edit");
    await user.type(editBox, "Reviewer restates the gap.");
    expect(
      screen.getByRole("button", {
        name: "Edit Production readiness date must be consistent",
      }),
    ).toBeDisabled();
    await user.click(
      screen.getByRole("checkbox", {
        name: /I confirm this edit is reviewer-authored/,
      }),
    );
    await user.click(
      screen.getByRole("button", {
        name: "Edit Production readiness date must be consistent",
      }),
    );
    expect(
      await screen.findByText(
        "edit recorded for Production readiness date must be consistent.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/This text is not system-grounded evidence/),
    ).toBeInTheDocument();

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
    expect(
      screen.getByRole("button", { name: "Open review session" }),
    ).toBeEnabled();
    await user.type(screen.getByLabelText("Corpus ID"), "corpus-1");
    await user.type(screen.getByLabelText("Examination run ID"), "exam-1");
    await user.click(
      screen.getByRole("button", { name: "Open review session" }),
    );

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
    expect(
      screen.getByRole("button", { name: "Open review session" }),
    ).toBeDisabled();
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
      screen.getByRole("button", { name: "Complete review session" }),
    ).toBeDisabled();
  });
});
