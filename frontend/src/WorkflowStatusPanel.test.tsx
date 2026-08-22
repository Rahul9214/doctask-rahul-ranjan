import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import WorkflowStatusPanel from "./WorkflowStatusPanel";

const run = {
  id: "run-1",
  corpus_id: "corpus-1",
  status: "waiting_for_review",
  current_stage: "wait_for_review",
  resume_count: 1,
  analysis_run_id: "analysis-1",
  examination_run_id: "exam-1",
  review_session_id: "session-1",
  error_code: null,
  error_detail: null,
  error_action: null,
};

const events = [
  {
    id: "event-1",
    event_type: "waiting_for_review",
    stage_name: "wait_for_review",
    created_at: "2026-08-21T00:00:00Z",
  },
];

const session = {
  id: "session-1",
  status: "waiting_for_review",
  pending_count: 2,
  completion_allowed: false,
};

const revision = {
  id: "revision-1",
  revision_number: 2,
  is_current: true,
  analysis_run_id: "analysis-1",
  examination_run_id: "exam-1",
};

function jsonResponse(body: unknown, ok = true, status = 200): Response {
  return {
    ok,
    status,
    json: async () => body,
  } as Response;
}

function stubStatus(overrides?: {
  run?: Partial<typeof run>;
  session?: Partial<typeof session>;
  resume?: typeof run | null;
}) {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path.endsWith("/resume")) {
        expect(init?.method).toBe("POST");
        return Promise.resolve(
          jsonResponse(overrides?.resume ?? { ...run, status: "completed" }),
        );
      }
      if (path.endsWith("/workflow-runs/run-1") && !path.endsWith("/resume")) {
        return Promise.resolve(jsonResponse({ ...run, ...overrides?.run }));
      }
      if (path.endsWith("/events")) {
        return Promise.resolve(jsonResponse(events));
      }
      if (path.endsWith("/review-sessions/session-1")) {
        return Promise.resolve(
          jsonResponse({ ...session, ...overrides?.session }),
        );
      }
      if (path.endsWith("/revisions/current")) {
        return Promise.resolve(jsonResponse(revision));
      }
      return Promise.resolve(jsonResponse({ code: "not_found" }, false, 404));
    }),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

async function loadStatus(runId = "run-1") {
  const user = userEvent.setup();
  render(<WorkflowStatusPanel />);
  await user.type(screen.getByLabelText("Workflow corpus ID"), "corpus-1");
  await user.type(screen.getByLabelText("Workflow run ID"), runId);
  await user.click(
    screen.getByRole("button", { name: "Load workflow status" }),
  );
  return user;
}

describe("WorkflowStatusPanel", () => {
  it("shows run status, review, revision, and events without resume while review is pending", async () => {
    stubStatus();
    await loadStatus();

    expect(screen.getAllByText("waiting_for_review").length).toBeGreaterThan(0);
    expect(screen.getAllByText("wait_for_review").length).toBeGreaterThan(0);
    expect(screen.getByText("revision 2")).toBeInTheDocument();
    expect(
      screen.getByText(/waiting_for_review · wait_for_review/),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Resume workflow" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText(
        "Resume is available after the linked review session is completed.",
      ),
    ).toBeInTheDocument();
  });

  it("enables resume for a failed workflow", async () => {
    stubStatus({ run: { status: "failed", current_stage: "examine" } });
    await loadStatus();
    expect(
      screen.getByRole("button", { name: "Resume workflow" }),
    ).toBeEnabled();
  });

  it("enables resume when waiting_for_review and the review session is completed", async () => {
    stubStatus({
      session: {
        status: "completed",
        pending_count: 0,
        completion_allowed: true,
      },
    });
    await loadStatus();
    expect(
      screen.getByRole("button", { name: "Resume workflow" }),
    ).toBeEnabled();
  });

  it("hides resume after completion and shows a completed notice", async () => {
    stubStatus({
      run: { status: "completed", current_stage: "finalize" },
      session: { status: "completed", pending_count: 0 },
    });
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const path = String(input);
        if (path.endsWith("/workflow-runs/run-1")) {
          return Promise.resolve(
            jsonResponse({
              ...run,
              status: "completed",
              current_stage: "finalize",
            }),
          );
        }
        if (path.endsWith("/events")) {
          return Promise.resolve(jsonResponse(events));
        }
        if (path.endsWith("/review-sessions/session-1")) {
          return Promise.resolve(
            jsonResponse({ ...session, status: "completed", pending_count: 0 }),
          );
        }
        if (path.endsWith("/revisions/current")) {
          return Promise.resolve(
            jsonResponse(
              { code: "corpus_revision_not_found", detail: "None" },
              false,
              404,
            ),
          );
        }
        return Promise.resolve(jsonResponse({}, false, 404));
      }),
    );

    await loadStatus();

    expect(screen.getAllByText("completed").length).toBeGreaterThan(0);
    expect(screen.getByText("none")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Resume workflow" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText("Completed workflows cannot be resumed."),
    ).toBeInTheDocument();
  });

  it("resumes a waiting run after review completion through the existing API", async () => {
    stubStatus({
      session: { status: "completed", pending_count: 0 },
      resume: { ...run, status: "completed", resume_count: 2 },
    });
    const user = await loadStatus();
    await user.click(screen.getByRole("button", { name: "Resume workflow" }));
    expect(
      await screen.findByText("Completed workflows cannot be resumed."),
    ).toBeInTheDocument();
  });

  it("disables resume while a request is in flight", async () => {
    let finishResume: ((value: Response) => void) | undefined;
    const resumePromise = new Promise<Response>((resolve) => {
      finishResume = resolve;
    });
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input);
        if (path.endsWith("/resume")) {
          expect(init?.method).toBe("POST");
          return resumePromise;
        }
        if (path.endsWith("/workflow-runs/run-1")) {
          return Promise.resolve(
            jsonResponse({
              ...run,
              status: "failed",
              current_stage: "examine",
            }),
          );
        }
        if (path.endsWith("/events")) {
          return Promise.resolve(jsonResponse(events));
        }
        if (path.endsWith("/review-sessions/session-1")) {
          return Promise.resolve(jsonResponse(session));
        }
        if (path.endsWith("/revisions/current")) {
          return Promise.resolve(jsonResponse(revision));
        }
        return Promise.resolve(jsonResponse({}, false, 404));
      }),
    );

    const user = await loadStatus();
    const resume = screen.getByRole("button", { name: "Resume workflow" });
    await user.click(resume);
    expect(resume).toBeDisabled();
    finishResume?.(jsonResponse({ ...run, status: "failed", resume_count: 2 }));
    expect(
      await screen.findByRole("button", { name: "Resume workflow" }),
    ).toBeEnabled();
  });

  it("clears a previously loaded run when a replacement lookup fails", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const path = String(input);
      if (path.endsWith("/workflow-runs/run-1")) {
        return Promise.resolve(jsonResponse({ ...run, status: "failed" }));
      }
      if (path.endsWith("/workflow-runs/run-2")) {
        return Promise.resolve(
          jsonResponse(
            {
              code: "workflow_run_not_found",
              detail: "The workflow run was not found.",
              action: "Use a workflow run identifier from this corpus.",
            },
            false,
            404,
          ),
        );
      }
      if (path.endsWith("/events")) {
        return Promise.resolve(jsonResponse(events));
      }
      if (path.endsWith("/review-sessions/session-1")) {
        return Promise.resolve(jsonResponse(session));
      }
      if (path.endsWith("/revisions/current")) {
        return Promise.resolve(jsonResponse(revision));
      }
      return Promise.resolve(jsonResponse({}, false, 404));
    });
    vi.stubGlobal("fetch", fetchMock);

    const user = await loadStatus();
    expect(
      screen.getByRole("button", { name: "Resume workflow" }),
    ).toBeInTheDocument();
    const runInput = screen.getByLabelText("Workflow run ID");
    await user.clear(runInput);
    await user.type(runInput, "run-2");
    await user.click(
      screen.getByRole("button", { name: "Load workflow status" }),
    );
    expect(
      await screen.findByText("The workflow run was not found."),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Resume workflow" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("run-1")).not.toBeInTheDocument();
  });

  it("shows a loading label and keeps native controls labeled", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise<Response>(() => undefined)),
    );
    const user = userEvent.setup();
    render(<WorkflowStatusPanel />);
    expect(screen.getByLabelText("Workflow corpus ID")).toBeEnabled();
    expect(screen.getByLabelText("Workflow run ID")).toBeEnabled();
    await user.type(screen.getByLabelText("Workflow corpus ID"), "corpus-1");
    await user.type(screen.getByLabelText("Workflow run ID"), "run-1");
    await user.click(
      screen.getByRole("button", { name: "Load workflow status" }),
    );
    expect(
      screen.getByRole("button", { name: "Loading status…" }),
    ).toBeDisabled();
    expect(screen.queryByText(/traceback/i)).not.toBeInTheDocument();
  });
});
