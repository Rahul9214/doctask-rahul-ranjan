import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import RegisterPanel from "./RegisterPanel";

const completedSession = {
  id: "session-1",
  status: "completed",
  pending_count: 0,
  completion_allowed: false,
};

const register = {
  id: "pub-1",
  corpus_id: "corpus-1",
  publication_number: 1,
  is_current: true,
  review_session_id: "session-1",
  status: "published",
  register_status: "populated",
  version_identity: "register.v1.1.abc",
  published_at: "2026-08-22T00:00:00Z",
  applied_count: 2,
  rejected_omitted_count: 1,
  omitted_rejected_rule_ids: ["spa.ownership.budget"],
  items: [
    {
      id: "item-1",
      rule_id: "spa.milestone.production-readiness",
      rule_version: "1",
      title: "Production-readiness date is consistent",
      outcome: "fail",
      severity: "high",
      message: "Cited dates conflict.",
      review_status: "approved",
      content_origin: "system_grounded",
      system_grounded: true,
      reviewer_authored: false,
      reviewer_authored_content: null,
      reviewer_authored_acknowledged: false,
      grounded_facts: [
        {
          id: "fact-1",
          category: "delivery_milestone",
          subject_key: "production_readiness",
          normalized_value: "2026-10-30",
          support_status: "supported",
        },
      ],
      citations: [
        {
          source_logical_name: "Project Charter",
          native_locator: "page[1]/block[0]",
          exact_quote: "Ready 2026-10-30",
          source_sha256: "a".repeat(64),
        },
      ],
    },
    {
      id: "item-2",
      rule_id: "spa.status.clarity",
      rule_version: "1",
      title: "Status is clear",
      outcome: "warning",
      severity: "medium",
      message: "Original grounded status is amber.",
      review_status: "edited",
      content_origin: "mixed",
      system_grounded: false,
      reviewer_authored: true,
      reviewer_authored_content: "Reviewer clarifies the delivery status.",
      reviewer_authored_acknowledged: true,
      grounded_facts: [
        {
          id: "fact-2",
          category: "status",
          subject_key: "overall_status",
          normalized_value: "Amber",
          support_status: "supported",
        },
      ],
      citations: [
        {
          source_logical_name: "Weekly Status Report",
          native_locator: "paragraph[2]",
          exact_quote: "Overall status: Amber",
          source_sha256: "b".repeat(64),
        },
      ],
    },
  ],
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

describe("RegisterPanel", () => {
  it("separates edited reviewer text from original grounded evidence", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input);
        if (
          path.endsWith("/review-sessions/session-1") &&
          init?.method !== "POST"
        ) {
          return Promise.resolve(jsonResponse(completedSession));
        }
        if (path.endsWith("/register") && init?.method !== "POST") {
          return Promise.resolve(
            jsonResponse(
              { code: "publication_not_found", detail: "Not published." },
              false,
              404,
            ),
          );
        }
        if (path.endsWith("/publish")) {
          expect(init?.method).toBe("POST");
          return Promise.resolve(jsonResponse(register, true, 201));
        }
        return Promise.resolve(
          jsonResponse({ code: "unexpected" }, false, 500),
        );
      }),
    );

    render(<RegisterPanel />);
    await user.type(screen.getByLabelText("Register corpus ID"), "corpus-1");
    await user.type(screen.getByLabelText("Review session ID"), "session-1");
    await user.click(screen.getByRole("button", { name: "Load register" }));
    expect(
      await screen.findByText(/The session is ready for explicit publication/),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Publish register" }));
    expect(await screen.findByText("SYSTEM-GROUNDED")).toBeInTheDocument();
    expect(screen.getByText("Ready 2026-10-30")).toBeInTheDocument();
    expect(screen.getByText("register.v1.1.abc")).toBeInTheDocument();
    const groundedOriginal = screen.getByRole("region", {
      name: "SYSTEM-GROUNDED ORIGINAL spa.status.clarity",
    });
    expect(
      within(groundedOriginal).getByText("Original grounded status is amber."),
    ).toBeInTheDocument();
    expect(
      within(groundedOriginal).getByText("Overall status: Amber"),
    ).toBeInTheDocument();
    expect(
      within(groundedOriginal).getByText(
        "status/overall_status: Amber (supported)",
      ),
    ).toBeInTheDocument();
    const reviewerEdit = screen.getByRole("region", {
      name: "REVIEWER-AUTHORED EDIT spa.status.clarity",
    });
    expect(
      within(reviewerEdit).getByText("Reviewer clarifies the delivery status."),
    ).toBeInTheDocument();
    expect(
      within(reviewerEdit).getByText(
        "Acknowledged reviewer-authored content; not system-grounded.",
      ),
    ).toBeInTheDocument();
    expect(
      within(reviewerEdit).queryByText("Overall status: Amber"),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("spa.ownership.budget")).not.toBeInTheDocument();
  });
});
