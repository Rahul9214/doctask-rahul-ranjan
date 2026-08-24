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
  events?: typeof events;
  failures?: Array<"events" | "usage" | "review" | "revision">;
  resumeFailures?: Array<"events" | "usage" | "review" | "revision">;
}) {
  let resumed = false;
  const failedResponse = () =>
    jsonResponse(
      {
        code: "supplemental_unavailable",
        detail: "Supplemental workflow data is unavailable.",
      },
      false,
      503,
    );
  const shouldFail = (resource: "events" | "usage" | "review" | "revision") =>
    (resumed ? overrides?.resumeFailures : overrides?.failures)?.includes(
      resource,
    );

  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path.endsWith("/resume")) {
        expect(init?.method).toBe("POST");
        resumed = true;
        return Promise.resolve(
          jsonResponse(overrides?.resume ?? { ...run, status: "completed" }),
        );
      }
      if (path.endsWith("/workflow-runs/run-1") && !path.endsWith("/resume")) {
        return Promise.resolve(jsonResponse({ ...run, ...overrides?.run }));
      }
      if (path.endsWith("/events")) {
        return Promise.resolve(
          shouldFail("events")
            ? failedResponse()
            : jsonResponse(overrides?.events ?? events),
        );
      }
      if (path.endsWith("/usage")) {
        if (shouldFail("usage")) {
          return Promise.resolve(failedResponse());
        }
        return Promise.resolve(
          jsonResponse({
            total_duration_ms: 12,
            total_model_operation_count: 2,
            total_model_attempt_count: 2,
            estimated_cost_usd: 0,
            cost_basis: "zero_deterministic",
            pricing_basis:
              "Deterministic local adapter: estimated_cost_usd is 0.",
            stages: [
              {
                graph: "understand",
                stage_name: "extract",
                status: "completed",
                duration_ms: 8,
                model_operation_count: 1,
                model_attempt_count: 1,
                estimated_cost_usd: 0,
                cost_basis: "zero_deterministic",
              },
            ],
          }),
        );
      }
      if (path.endsWith("/review-sessions/session-1")) {
        if (shouldFail("review")) {
          return Promise.resolve(failedResponse());
        }
        return Promise.resolve(
          jsonResponse({ ...session, ...overrides?.session }),
        );
      }
      if (path.endsWith("/revisions/current")) {
        return Promise.resolve(
          shouldFail("revision") ? failedResponse() : jsonResponse(revision),
        );
      }
      return Promise.resolve(jsonResponse({ code: "not_found" }, false, 404));
    }),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

async function loadStatus(
  runId = "run-1",
  extra: {
    onOpenReview?: () => void;
    onOpenRegister?: () => void;
  } = {},
) {
  const user = userEvent.setup();
  render(
    <WorkflowStatusPanel
      onOpenReview={extra.onOpenReview}
      onOpenRegister={extra.onOpenRegister}
    />,
  );
  await user.type(screen.getByLabelText("Corpus"), "corpus-1");
  expect(
    screen.getByText("Advanced lookup").closest("details"),
  ).not.toHaveAttribute("open");
  await user.click(screen.getByText("Advanced lookup"));
  await user.type(screen.getByLabelText("Workflow run ID"), runId);
  await user.click(screen.getByRole("button", { name: "Load workflow" }));
  return user;
}

describe("WorkflowStatusPanel", () => {
  it("shows run status, review, revision, and events without resume while review is pending", async () => {
    stubStatus();
    const user = await loadStatus();

    expect(
      screen.getAllByText("Waiting for human review").length,
    ).toBeGreaterThan(0);
    expect(screen.getAllByText("Human Gate").length).toBeGreaterThan(0);
    expect(screen.getByText("Revision 2")).toBeInTheDocument();
    expect(
      screen.queryByText(/waiting_for_review · wait_for_review/),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Resume workflow" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText(/Resume is available after the linked review session/),
    ).toBeInTheDocument();
    const stageDetails = screen.getByRole("button", { name: "View steps" });
    expect(stageDetails).toHaveAttribute("aria-expanded", "false");
    await user.click(stageDetails);
    expect(stageDetails).toHaveAttribute("aria-expanded", "true");
    expect(screen.getAllByText("Extract").length).toBeGreaterThan(0);
  });

  it("shows five durable events by default and expands the complete history", async () => {
    const manyEvents = Array.from({ length: 6 }, (_, index) => ({
      id: `event-${index}`,
      event_type: index === 0 ? "workflow_started" : `checkpoint_${index}`,
      stage_name: index < 3 ? "understand" : "examine",
      created_at: `2026-08-21T00:0${index}:00Z`,
    }));
    stubStatus({ events: manyEvents });
    const user = await loadStatus();

    expect(screen.queryByText("Workflow started")).not.toBeInTheDocument();
    const showAll = screen.getByRole("button", {
      name: "View all 6 events",
    });
    expect(showAll).toHaveAttribute("aria-expanded", "false");
    await user.click(showAll);
    expect(screen.getByText("Workflow started")).toBeInTheDocument();
    expect(showAll).toHaveAttribute("aria-expanded", "true");
  });

  it("enables resume for a failed workflow", async () => {
    stubStatus({ run: { status: "failed", current_stage: "examine" } });
    await loadStatus();
    expect(
      screen.getByRole("button", { name: "Resume workflow" }),
    ).toBeEnabled();
  });

  it("keeps a failed workflow resumable when events are unavailable", async () => {
    stubStatus({
      run: { status: "failed", current_stage: "examine" },
      failures: ["events"],
    });
    await loadStatus();

    expect(await screen.findByText("Events unavailable.")).toBeInTheDocument();
    expect(screen.getByText("run-1")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Resume workflow" }),
    ).toBeEnabled();
  });

  it("keeps a failed workflow resumable when usage is unavailable", async () => {
    stubStatus({
      run: { status: "failed", current_stage: "examine" },
      failures: ["usage"],
    });
    await loadStatus();

    expect(await screen.findByText("Usage unavailable.")).toBeInTheDocument();
    expect(screen.getByText("run-1")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Resume workflow" }),
    ).toBeEnabled();
  });

  it("keeps the workflow visible when revision is unavailable", async () => {
    stubStatus({ failures: ["revision"] });
    await loadStatus();

    expect(await screen.findByText(/Revision unavailable/)).toBeInTheDocument();
    expect(screen.getByText("run-1")).toBeInTheDocument();
  });

  it("fails closed for waiting-review resume when review status is unavailable", async () => {
    stubStatus({ failures: ["review"] });
    await loadStatus();

    expect(
      await screen.findByText(/Review status unavailable/),
    ).toBeInTheDocument();
    expect(screen.getByText("run-1")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Resume workflow" }),
    ).not.toBeInTheDocument();
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
        if (path.endsWith("/usage")) {
          return Promise.resolve(
            jsonResponse({
              total_duration_ms: 12,
              total_model_operation_count: 2,
              total_model_attempt_count: 2,
              estimated_cost_usd: 0,
              cost_basis: "zero_deterministic",
              pricing_basis:
                "Deterministic local adapter: estimated_cost_usd is 0.",
              stages: [
                {
                  graph: "understand",
                  stage_name: "extract",
                  status: "completed",
                  duration_ms: 8,
                  model_operation_count: 1,
                  model_attempt_count: 1,
                  estimated_cost_usd: 0,
                  cost_basis: "zero_deterministic",
                },
              ],
            }),
          );
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

    expect(screen.getAllByText("Completed").length).toBeGreaterThan(0);
    expect(screen.getByText("None")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Resume workflow" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText(/Completed workflows cannot be resumed/),
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
      await screen.findByText(/Completed workflows cannot be resumed/),
    ).toBeInTheDocument();
  });

  it("keeps the resumed workflow visible when supplemental refresh fails", async () => {
    stubStatus({
      run: { status: "failed", current_stage: "examine" },
      resume: {
        ...run,
        status: "completed",
        current_stage: "finalize",
        resume_count: 2,
      },
      resumeFailures: ["events"],
    });
    const user = await loadStatus();

    await user.click(screen.getByRole("button", { name: "Resume workflow" }));

    expect(await screen.findByText("Events unavailable.")).toBeInTheDocument();
    expect(screen.getByText("run-1")).toBeInTheDocument();
    expect(
      screen.getByText(/Completed workflows cannot be resumed/),
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
        if (path.endsWith("/usage")) {
          return Promise.resolve(
            jsonResponse({
              total_duration_ms: 12,
              total_model_operation_count: 2,
              total_model_attempt_count: 2,
              estimated_cost_usd: 0,
              cost_basis: "zero_deterministic",
              pricing_basis:
                "Deterministic local adapter: estimated_cost_usd is 0.",
              stages: [
                {
                  graph: "understand",
                  stage_name: "extract",
                  status: "completed",
                  duration_ms: 8,
                  model_operation_count: 1,
                  model_attempt_count: 1,
                  estimated_cost_usd: 0,
                  cost_basis: "zero_deterministic",
                },
              ],
            }),
          );
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
      if (path.endsWith("/usage")) {
        return Promise.resolve(
          jsonResponse({
            total_duration_ms: 12,
            total_model_operation_count: 2,
            total_model_attempt_count: 2,
            estimated_cost_usd: 0,
            cost_basis: "zero_deterministic",
            pricing_basis:
              "Deterministic local adapter: estimated_cost_usd is 0.",
            stages: [
              {
                graph: "understand",
                stage_name: "extract",
                status: "completed",
                duration_ms: 8,
                model_operation_count: 1,
                model_attempt_count: 1,
                estimated_cost_usd: 0,
                cost_basis: "zero_deterministic",
              },
            ],
          }),
        );
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
    await user.click(screen.getByRole("button", { name: "Load workflow" }));
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
    expect(screen.getByLabelText("Corpus")).toBeEnabled();
    await user.click(screen.getByText("Advanced lookup"));
    expect(screen.getByLabelText("Workflow run ID")).toBeEnabled();
    await user.type(screen.getByLabelText("Corpus"), "corpus-1");
    await user.type(screen.getByLabelText("Workflow run ID"), "run-1");
    await user.click(screen.getByRole("button", { name: "Load workflow" }));
    expect(
      screen.getByRole("button", { name: "Loading workflow…" }),
    ).toBeDisabled();
    expect(screen.queryByText(/traceback/i)).not.toBeInTheDocument();
  });

  it("offers a human-review CTA while waiting and hides resume", async () => {
    stubStatus();
    const onOpenReview = vi.fn();
    const user = await loadStatus("run-1", { onOpenReview });

    expect(
      screen.getByRole("heading", { name: "Human review required" }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Open human review" }));
    expect(onOpenReview).toHaveBeenCalledTimes(1);
    expect(
      screen.queryByRole("button", { name: "Resume workflow" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getAllByText("Technical details")[0].closest("details"),
    ).not.toHaveAttribute("open");
    expect(screen.queryByText("Usage details")).not.toBeInTheDocument();
    expect(
      screen.getByText("No provider-priced usage was recorded for this run."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Calculated from recorded workflow events."),
    ).toBeInTheDocument();
  });

  it("offers resume after review completion", async () => {
    stubStatus({
      session: {
        status: "completed",
        pending_count: 0,
        completion_allowed: true,
      },
    });
    await loadStatus();
    expect(
      screen.getByRole("heading", { name: "Review complete" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Resume workflow" }),
    ).toBeEnabled();
  });

  it("offers register navigation after workflow completion and hides resume", async () => {
    stubStatus({
      run: { status: "completed", current_stage: "finalize" },
      session: { status: "completed", pending_count: 0 },
    });
    const onOpenRegister = vi.fn();
    const user = await loadStatus("run-1", { onOpenRegister });
    expect(
      await screen.findByRole("heading", { name: "Workflow complete" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Resume workflow" }),
    ).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Open register" }));
    expect(onOpenRegister).toHaveBeenCalledTimes(1);
  });
});
