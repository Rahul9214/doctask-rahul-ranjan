import { useState, type FormEvent } from "react";

import type { CorpusSummary } from "./App";
import CorpusSelect from "./CorpusSelect";
import { requestJson, type ApiError } from "./api";
import type { SourceSummary } from "./corpus";
import {
  eventLabel,
  formatDuration,
  formatTimestamp,
  humanize,
  stageLabel,
  workflowStatusLabel,
  workflowStatusTone,
} from "./ui";
import { workspaceFromRun, type Workspace } from "./workspace";

interface WorkflowRun {
  id: string;
  corpus_id: string;
  status: string;
  current_stage: string;
  resume_count: number;
  analysis_run_id: string | null;
  examination_run_id: string | null;
  review_session_id: string | null;
  error_code: string | null;
  error_detail: string | null;
  error_action: string | null;
}

interface WorkflowEvent {
  id: string;
  event_type: string;
  stage_name: string | null;
  duration_ms?: number | null;
  created_at: string;
}

interface ReviewSession {
  id: string;
  status: string;
  pending_count: number;
  completion_allowed: boolean;
}

interface CorpusRevision {
  id: string;
  revision_number: number;
  is_current: boolean;
  analysis_run_id: string;
  examination_run_id: string;
}

interface StageUsage {
  graph: string;
  stage_name: string;
  status: string;
  duration_ms: number | null;
  model_operation_count: number;
  model_attempt_count: number;
  estimated_cost_usd: number | null;
  cost_basis: string;
  skip_reason?: string | null;
}

interface RunUsage {
  total_duration_ms: number;
  duration_basis: "outer_workflow_events";
  total_model_operation_count: number;
  total_model_attempt_count: number;
  estimated_cost_usd: number | null;
  cost_basis: string;
  pricing_basis: string;
  stages: StageUsage[];
}

type SupplementalResource = "events" | "usage" | "review" | "revision";

const supplementalFailureLabels: Record<SupplementalResource, string> = {
  events: "Events unavailable",
  usage: "Usage unavailable",
  review: "Review status unavailable",
  revision: "Revision unavailable",
};

const workflowErrorCopy = {
  detail: "The workflow request failed.",
  action: "Retry the workflow operation.",
};

type MajorStage = "understand" | "examine" | "human-gate" | "finalize";

const majorStageLabels: Record<MajorStage, string> = {
  understand: "Understand",
  examine: "Examine",
  "human-gate": "Human Gate",
  finalize: "Finalize",
};

function stageState(
  stage: MajorStage,
  run: WorkflowRun,
  usage: RunUsage | null,
  review: ReviewSession | null,
): { status: string; detail: string; duration: number | null } {
  if (stage === "human-gate") {
    if (review?.status === "completed") {
      return {
        status: "completed",
        detail: "Review completed",
        duration: null,
      };
    }
    if (run.status === "waiting_for_review") {
      return {
        status: "waiting",
        detail: "Waiting for review",
        duration: null,
      };
    }
    if (
      run.current_stage === "wait_for_review" ||
      run.current_stage === "human_gate"
    ) {
      return { status: "running", detail: "Human gate", duration: null };
    }
    return { status: "pending", detail: "Not reached", duration: null };
  }

  const graph = stage === "finalize" ? "workflow" : stage;
  const matching = usage?.stages?.filter((item) => item.graph === graph) ?? [];
  const duration = matching.reduce(
    (total, item) => total + (item.duration_ms ?? 0),
    0,
  );
  const hasDuration = matching.some((item) => item.duration_ms !== null);
  const failed = matching.some((item) => item.status === "failed");
  const retrying = matching.some((item) => item.status === "retrying");
  const allSkipped =
    matching.length > 0 && matching.every((item) => item.status === "skipped");
  const completed =
    matching.length > 0 &&
    matching.every((item) => ["completed", "skipped"].includes(item.status));

  if (failed) {
    return {
      status: "failed",
      detail: "Safe failure",
      duration: hasDuration ? duration : null,
    };
  }
  if (retrying) {
    return {
      status: "retrying",
      detail: "Retrying",
      duration: hasDuration ? duration : null,
    };
  }
  if (allSkipped) {
    return {
      status: "skipped",
      detail: "Skipped",
      duration: hasDuration ? duration : null,
    };
  }
  if (completed) {
    return {
      status: "completed",
      detail: "Completed",
      duration: hasDuration ? duration : null,
    };
  }
  if (
    run.current_stage === stage ||
    (stage === "finalize" && run.current_stage === "finalize")
  ) {
    return { status: "running", detail: "In progress", duration: null };
  }
  if (stage === "finalize" && run.status === "completed") {
    return { status: "completed", detail: "Completed", duration: null };
  }
  return { status: "pending", detail: "Not started", duration: null };
}

async function loadCurrentRevision(corpusId: string): Promise<{
  revision: CorpusRevision | null;
  missing: boolean;
}> {
  try {
    return {
      revision: await requestJson<CorpusRevision>(
        `/api/corpora/${corpusId}/revisions/current`,
        workflowErrorCopy,
      ),
      missing: false,
    };
  } catch (caught) {
    const apiError = caught as ApiError;
    if (apiError.code === "corpus_revision_not_found") {
      return { revision: null, missing: true };
    }
    throw caught;
  }
}

function providerPricedUsage(usage: RunUsage): boolean {
  const basis = usage.pricing_basis?.trim();
  if (!basis || basis === "none") {
    return false;
  }
  const lowered = basis.toLowerCase();
  return !(
    lowered.includes("adapter") ||
    lowered.includes("deterministic") ||
    lowered.includes("zero_")
  );
}

function stageMarker(status: string): string {
  if (status === "completed") {
    return "✓";
  }
  if (
    status === "pending" ||
    status === "skipped" ||
    status === "not-started"
  ) {
    return "○";
  }
  return "●";
}

function stageCaption(
  stage: MajorStage,
  details: StageUsage[],
  state: { status: string; detail: string },
): string {
  if (stage === "human-gate" || stage === "finalize") {
    return state.detail;
  }
  const named = details
    .filter((item) => item.status === "completed" || item.status === "skipped")
    .map((item) => humanize(item.stage_name));
  return named.length > 0 ? named.slice(0, 4).join(" · ") : state.detail;
}

export default function WorkflowStatusPanel({
  corpora = [],
  corporaLoading = false,
  sourcesByCorpus = {},
  workspace,
  onWorkspaceChange,
  onOpenReview,
  onOpenRegister,
}: {
  corpora?: CorpusSummary[];
  corporaLoading?: boolean;
  sourcesByCorpus?: Record<string, SourceSummary[]>;
  workspace?: Workspace;
  onWorkspaceChange?: (workspace: Workspace) => void;
  onOpenReview?: () => void;
  onOpenRegister?: () => void;
}) {
  const [corpusId, setCorpusId] = useState(workspace?.corpusId ?? "");
  const [workflowRunId, setWorkflowRunId] = useState(
    workspace?.workflowRunId ?? "",
  );
  const [run, setRun] = useState<WorkflowRun | null>(null);
  const [events, setEvents] = useState<WorkflowEvent[]>([]);
  const [review, setReview] = useState<ReviewSession | null>(null);
  const [revision, setRevision] = useState<CorpusRevision | null>(null);
  const [revisionMissing, setRevisionMissing] = useState(false);
  const [usage, setUsage] = useState<RunUsage | null>(null);
  const [loading, setLoading] = useState(false);
  const [pendingAction, setPendingAction] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [supplementalFailures, setSupplementalFailures] = useState<
    SupplementalResource[]
  >([]);
  const [expandedStages, setExpandedStages] = useState<
    Partial<Record<MajorStage, boolean>>
  >({});
  const [showAllEvents, setShowAllEvents] = useState(false);

  const busy = loading || pendingAction !== null;
  const canResume =
    run !== null &&
    (run.status === "failed" ||
      (run.status === "waiting_for_review" && review?.status === "completed"));
  const [syncedCorpusId, setSyncedCorpusId] = useState(
    workspace?.corpusId ?? "",
  );
  const [syncedWorkflowRunId, setSyncedWorkflowRunId] = useState(
    workspace?.workflowRunId ?? "",
  );
  const [syncedReviewStatus, setSyncedReviewStatus] = useState(
    workspace?.reviewStatus ?? null,
  );
  if ((workspace?.corpusId ?? "") !== syncedCorpusId) {
    setSyncedCorpusId(workspace?.corpusId ?? "");
    if (workspace?.corpusId) {
      setCorpusId(workspace.corpusId);
    }
  }
  if ((workspace?.workflowRunId ?? "") !== syncedWorkflowRunId) {
    setSyncedWorkflowRunId(workspace?.workflowRunId ?? "");
    if (workspace?.workflowRunId) {
      setWorkflowRunId(workspace.workflowRunId);
    }
  }
  if ((workspace?.reviewStatus ?? null) !== syncedReviewStatus) {
    setSyncedReviewStatus(workspace?.reviewStatus ?? null);
    if (workspace?.reviewStatus) {
      setReview((current) =>
        current
          ? { ...current, status: workspace.reviewStatus ?? current.status }
          : current,
      );
    }
  }
  const majorStages: MajorStage[] = [
    "understand",
    "examine",
    "human-gate",
    "finalize",
  ];

  function clearSupplementalState() {
    setEvents([]);
    setReview(null);
    setRevision(null);
    setRevisionMissing(false);
    setUsage(null);
    setSupplementalFailures([]);
  }

  async function refreshSupplemental(loaded: WorkflowRun) {
    clearSupplementalState();
    const [eventsResult, usageResult, reviewResult, revisionResult] =
      await Promise.allSettled([
        requestJson<WorkflowEvent[]>(
          `/api/corpora/${loaded.corpus_id}/workflow-runs/${loaded.id}/events`,
          workflowErrorCopy,
        ),
        requestJson<RunUsage>(
          `/api/corpora/${loaded.corpus_id}/workflow-runs/${loaded.id}/usage`,
          workflowErrorCopy,
        ),
        loaded.review_session_id
          ? requestJson<ReviewSession>(
              `/api/corpora/${loaded.corpus_id}/review-sessions/${loaded.review_session_id}`,
              workflowErrorCopy,
            )
          : Promise.resolve(null),
        loadCurrentRevision(loaded.corpus_id),
      ]);
    const failures: SupplementalResource[] = [];

    if (eventsResult.status === "fulfilled") {
      setEvents(eventsResult.value);
    } else {
      failures.push("events");
    }
    if (usageResult.status === "fulfilled") {
      setUsage(usageResult.value);
    } else {
      failures.push("usage");
    }
    if (reviewResult.status === "fulfilled") {
      setReview(reviewResult.value);
      if (reviewResult.value) {
        onWorkspaceChange?.({
          ...workspaceFromRun(loaded),
          reviewStatus: reviewResult.value.status,
        });
      }
    } else {
      failures.push("review");
    }
    if (revisionResult.status === "fulfilled") {
      setRevision(revisionResult.value.revision);
      setRevisionMissing(revisionResult.value.missing);
    } else {
      failures.push("revision");
    }
    setSupplementalFailures(failures);
  }

  async function loadStatus(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    setError(null);
    setRun(null);
    clearSupplementalState();
    setLoading(true);
    try {
      const loaded = await requestJson<WorkflowRun>(
        `/api/corpora/${corpusId}/workflow-runs/${workflowRunId}`,
        workflowErrorCopy,
      );
      setRun(loaded);
      await refreshSupplemental(loaded);
      onWorkspaceChange?.({
        ...workspaceFromRun(loaded),
        reviewStatus: null,
      });
    } catch (caught) {
      setError(caught as ApiError);
    } finally {
      setLoading(false);
    }
  }

  async function resumeRun() {
    if (!run) {
      return;
    }
    setError(null);
    setPendingAction("resume");
    try {
      const resumed = await requestJson<WorkflowRun>(
        `/api/corpora/${run.corpus_id}/workflow-runs/${run.id}/resume`,
        workflowErrorCopy,
        { method: "POST" },
      );
      setRun(resumed);
      await refreshSupplemental(resumed);
      onWorkspaceChange?.({
        ...workspaceFromRun(resumed),
        reviewStatus: review?.status ?? null,
      });
    } catch (caught) {
      setError(caught as ApiError);
    } finally {
      setPendingAction(null);
    }
  }

  async function startWorkflow() {
    if (!corpusId) {
      return;
    }
    setError(null);
    setRun(null);
    clearSupplementalState();
    setPendingAction("start");
    try {
      const created = await requestJson<WorkflowRun>(
        `/api/corpora/${corpusId}/workflow-runs`,
        workflowErrorCopy,
        { method: "POST" },
      );
      setWorkflowRunId(created.id);
      setRun(created);
      onWorkspaceChange?.({
        ...workspaceFromRun(created),
        reviewStatus: null,
      });
      await refreshSupplemental(created);
    } catch (caught) {
      setError(caught as ApiError);
    } finally {
      setPendingAction(null);
    }
  }

  return (
    <div className="page page--workflow" aria-busy={busy}>
      <header className="page-header">
        <div>
          <p className="eyebrow">Observable durable execution</p>
          <h1 id="workflow-title">Agent Run</h1>
          <p>
            Watch real workflow state move through Understand, Examine, the
            human gate, and finalization.
          </p>
        </div>
        <span className="boundary-chip">Resume never approves</span>
      </header>

      <section className="picker-panel">
        <div className="form-grid form-grid--action form-grid--primary">
          <div className="field">
            <label htmlFor="workflow-corpus-id">Corpus</label>
            <CorpusSelect
              id="workflow-corpus-id"
              corpora={corpora}
              sourcesByCorpus={sourcesByCorpus}
              value={corpusId}
              onChange={setCorpusId}
              disabled={busy}
              loading={corporaLoading}
            />
          </div>
          <div className="field-action">
            <button
              className="button button--primary"
              type="button"
              disabled={busy || !corpusId}
              onClick={() => void startWorkflow()}
            >
              {pendingAction === "start"
                ? "Starting workflow…"
                : "Start workflow"}
            </button>
          </div>
        </div>
        <form onSubmit={(event) => void loadStatus(event)}>
          <details className="advanced-lookup">
            <summary>Advanced lookup</summary>
            <p className="lookup-lead">Optional technical recovery path</p>
            <div className="form-grid form-grid--action">
              <div className="field">
                <label htmlFor="workflow-run-id">Workflow run ID</label>
                <input
                  id="workflow-run-id"
                  name="workflowRunId"
                  value={workflowRunId}
                  onChange={(event) => setWorkflowRunId(event.target.value)}
                  required
                  disabled={busy}
                  autoComplete="off"
                />
              </div>
              <div className="field-action">
                <button
                  className="button button--secondary"
                  type="submit"
                  disabled={busy}
                >
                  {loading ? "Loading workflow…" : "Load workflow"}
                </button>
              </div>
            </div>
          </details>
        </form>
      </section>

      {error && (
        <div className="review-banner review-banner--error" role="alert">
          <p>{error.detail}</p>
          {error.action && <p>Next action: {error.action}</p>}
        </div>
      )}

      {loading && (
        <section className="panel skeleton-panel" aria-label="Loading workflow">
          <span className="skeleton skeleton--line skeleton--wide" />
          <div className="skeleton-grid">
            {Array.from({ length: 4 }).map((_, index) => (
              <span className="skeleton skeleton--card" key={index} />
            ))}
          </div>
        </section>
      )}

      {run && (
        <div className="workflow-summary">
          {supplementalFailures.length > 0 && (
            <p className="review-banner review-banner--warning" role="status">
              <strong>Some workflow details are unavailable.</strong>{" "}
              {supplementalFailures
                .map((resource) => supplementalFailureLabels[resource])
                .join(" · ")}
              . The authoritative workflow run remains available.
            </p>
          )}

          <section
            className="panel run-summary"
            aria-labelledby="run-summary-title"
          >
            <div className="summary-heading">
              <div>
                <p className="section-kicker">Durable workflow</p>
                <h2 id="run-summary-title">
                  {corpora.find((item) => item.id === run.corpus_id)?.name ??
                    "Selected corpus"}
                </h2>
              </div>
              <span
                className={`status-chip status-chip--${workflowStatusTone(
                  run.status,
                )}`}
              >
                {workflowStatusLabel(run.status)}
              </span>
            </div>
            <dl className="run-facts">
              <div>
                <dt>Status</dt>
                <dd>{workflowStatusLabel(run.status)}</dd>
              </div>
              <div>
                <dt>Current stage</dt>
                <dd>{stageLabel(run.current_stage)}</dd>
              </div>
              <div>
                <dt>Resume count</dt>
                <dd>{run.resume_count}</dd>
              </div>
              <div>
                <dt>Current revision</dt>
                <dd>
                  {revision
                    ? `Revision ${revision.revision_number}`
                    : supplementalFailures.includes("revision")
                      ? "Unavailable"
                      : revisionMissing
                        ? "None"
                        : "Unknown"}
                </dd>
              </div>
            </dl>
            <details className="technical-details">
              <summary>Technical details</summary>
              <dl className="technical-grid">
                <div>
                  <dt>Workflow run ID</dt>
                  <dd>
                    <code>{run.id}</code>
                  </dd>
                </div>
                <div>
                  <dt>Corpus ID</dt>
                  <dd>
                    <code>{run.corpus_id}</code>
                  </dd>
                </div>
                <div>
                  <dt>Analysis run ID</dt>
                  <dd>
                    <code>{run.analysis_run_id ?? "Not available"}</code>
                  </dd>
                </div>
                <div>
                  <dt>Examination run ID</dt>
                  <dd>
                    <code>{run.examination_run_id ?? "Not available"}</code>
                  </dd>
                </div>
                <div>
                  <dt>Review session ID</dt>
                  <dd>
                    <code>{run.review_session_id ?? "Not available"}</code>
                  </dd>
                </div>
              </dl>
            </details>
            {canResume && run.status === "failed" && (
              <button
                className="button button--primary"
                type="button"
                onClick={() => void resumeRun()}
                disabled={busy}
              >
                {pendingAction === "resume"
                  ? "Resuming workflow…"
                  : "Resume workflow"}
              </button>
            )}
          </section>

          {run.status === "waiting_for_review" &&
            review?.status !== "completed" &&
            Boolean(run.examination_run_id) &&
            onOpenReview && (
              <section
                className="workflow-cta"
                aria-labelledby="review-cta-title"
              >
                <div>
                  <h2 id="review-cta-title">Human review required</h2>
                  <p>
                    The workflow is paused until required findings are decided.
                  </p>
                </div>
                <button
                  className="button button--primary"
                  type="button"
                  onClick={onOpenReview}
                >
                  Open human review
                </button>
              </section>
            )}
          {run.status === "waiting_for_review" &&
            review?.status === "completed" && (
              <section
                className="workflow-cta"
                aria-labelledby="resume-cta-title"
              >
                <div>
                  <h2 id="resume-cta-title">Review complete</h2>
                  <p>The workflow may now resume.</p>
                </div>
                <button
                  className="button button--primary"
                  type="button"
                  onClick={() => void resumeRun()}
                  disabled={busy}
                >
                  {pendingAction === "resume"
                    ? "Resuming workflow…"
                    : "Resume workflow"}
                </button>
              </section>
            )}
          {run.status === "completed" && onOpenRegister && (
            <section
              className="workflow-cta"
              aria-labelledby="publish-cta-title"
            >
              <div>
                <h2 id="publish-cta-title">Workflow complete</h2>
                <p>Publication remains explicit.</p>
              </div>
              <button
                className="button button--primary"
                type="button"
                onClick={onOpenRegister}
              >
                Open register
              </button>
            </section>
          )}

          <section className="panel agent-stages" aria-labelledby="stage-title">
            <div className="card-heading">
              <div>
                <p className="section-kicker">Live stage state</p>
                <h2 id="stage-title">Agent execution</h2>
              </div>
              {run.resume_count > 0 && (
                <span className="resume-chip">
                  Durable resume · {run.resume_count}
                </span>
              )}
            </div>
            <ol className="major-stage-track">
              {majorStages.map((stage) => {
                const state = stageState(stage, run, usage, review);
                const details =
                  stage === "understand" || stage === "examine"
                    ? (usage?.stages?.filter((item) => item.graph === stage) ??
                      [])
                    : [];
                const retries = details.reduce(
                  (total, item) =>
                    total +
                    Math.max(
                      0,
                      item.model_attempt_count - item.model_operation_count,
                    ),
                  0,
                );
                return (
                  <li
                    key={stage}
                    className={`major-stage major-stage--${state.status} ${
                      run.current_stage === stage ||
                      (stage === "human-gate" &&
                        run.current_stage === "wait_for_review")
                        ? "major-stage--current"
                        : ""
                    }`}
                  >
                    <div className="major-stage__summary">
                      <span className="stage-number" aria-hidden="true">
                        {stageMarker(state.status)}
                      </span>
                      <div>
                        <strong>{majorStageLabels[stage]}</strong>
                        <span>
                          {state.detail}
                          {state.duration !== null
                            ? ` · ${formatDuration(state.duration)}`
                            : ""}
                        </span>
                        {details.length > 0 && (
                          <span>
                            {details.length}{" "}
                            {details.length === 1 ? "step" : "steps"}
                          </span>
                        )}
                        <span>
                          {stageCaption(stage, details, state)}
                          {retries > 0
                            ? ` · ${retries} ${retries === 1 ? "retry" : "retries"}`
                            : ""}
                        </span>
                      </div>
                      {details.length > 0 && (
                        <button
                          className="disclosure-button"
                          type="button"
                          aria-expanded={Boolean(expandedStages[stage])}
                          aria-controls={`stage-details-${stage}`}
                          onClick={() =>
                            setExpandedStages((current) => ({
                              ...current,
                              [stage]: !current[stage],
                            }))
                          }
                        >
                          {expandedStages[stage] ? "Hide steps" : "View steps"}
                        </button>
                      )}
                    </div>
                    {expandedStages[stage] && details.length > 0 && (
                      <ol
                        id={`stage-details-${stage}`}
                        className="stage-detail-list"
                      >
                        {details.map((item, detailIndex) => (
                          <li
                            key={`${item.stage_name}-${item.status}-${detailIndex}`}
                          >
                            <div>
                              <strong>{humanize(item.stage_name)}</strong>
                              {item.skip_reason && (
                                <span>{item.skip_reason}</span>
                              )}
                            </div>
                            <span
                              className={`stage-state stage-state--${item.status}`}
                            >
                              {humanize(item.status)}
                            </span>
                            <small>
                              {formatDuration(item.duration_ms)} ·{" "}
                              {item.model_attempt_count} provider{" "}
                              {item.model_attempt_count === 1
                                ? "attempt"
                                : "attempts"}
                            </small>
                          </li>
                        ))}
                      </ol>
                    )}
                  </li>
                );
              })}
            </ol>
          </section>

          {run.status === "waiting_for_review" &&
            review?.status !== "completed" &&
            !(run.examination_run_id && onOpenReview) && (
              <p className="review-banner review-banner--warning">
                <strong>Human approval required.</strong> The workflow is
                durably paused. Resume is available after the linked review
                session is completed.
              </p>
            )}
          {run.status === "completed" && (
            <p className="review-banner review-banner--ok">
              <strong>Workflow complete.</strong> Completed workflows cannot be
              resumed. Workflow completion ≠ publication; publication remains an
              explicit action.
            </p>
          )}
          {(run.status === "pending" || run.status === "running") && (
            <p className="review-banner review-banner--info">
              A running or queued workflow cannot be resumed.
            </p>
          )}
          {run.error_detail && (
            <p className="review-banner review-banner--error">
              {run.error_detail}
              {run.error_action ? ` Next action: ${run.error_action}` : ""}
            </p>
          )}

          <section
            className="panel usage-section"
            aria-labelledby="usage-title"
          >
            <div className="card-heading">
              <div>
                <p className="section-kicker">Run usage</p>
                <h2 id="usage-title">Time and cost</h2>
                <p>
                  Stage timing, model operations, provider attempts and
                  estimated cost.
                </p>
              </div>
            </div>
            {usage ? (
              <>
                <dl className="metric-grid">
                  <div>
                    <dt>Duration</dt>
                    <dd>{formatDuration(usage.total_duration_ms)}</dd>
                  </div>
                  <div>
                    <dt>Model operations</dt>
                    <dd>{usage.total_model_operation_count}</dd>
                  </div>
                  <div>
                    <dt>Provider attempts</dt>
                    <dd>{usage.total_model_attempt_count}</dd>
                  </div>
                  <div>
                    <dt>Estimated cost</dt>
                    <dd>
                      {usage.estimated_cost_usd === null
                        ? "Unavailable"
                        : `$${usage.estimated_cost_usd.toFixed(4)}`}
                    </dd>
                  </div>
                </dl>
                <div className="usage-copy">
                  <p>
                    <strong>Cost estimate</strong>
                    {providerPricedUsage(usage)
                      ? usage.pricing_basis
                      : "No provider-priced usage was recorded for this run."}
                  </p>
                  <p>
                    <strong>Timing basis</strong>
                    Calculated from recorded workflow events.
                  </p>
                </div>
                <details className="technical-details">
                  <summary>Technical details</summary>
                  <dl className="technical-grid">
                    <div>
                      <dt>Cost basis</dt>
                      <dd>
                        <code>{usage.cost_basis}</code>
                      </dd>
                    </div>
                    <div>
                      <dt>Duration basis</dt>
                      <dd>
                        <code>{usage.duration_basis}</code>
                      </dd>
                    </div>
                    <div>
                      <dt>Pricing basis</dt>
                      <dd>
                        <code>{usage.pricing_basis}</code>
                      </dd>
                    </div>
                  </dl>
                </details>
              </>
            ) : (
              <p className="empty-state empty-state--compact">
                {supplementalFailures.includes("usage")
                  ? "Usage unavailable."
                  : "No usage summary is loaded yet."}
              </p>
            )}
          </section>

          <section
            className="panel events-section"
            aria-labelledby="events-title"
          >
            <div className="card-heading">
              <div>
                <p className="section-kicker">
                  Durable activity · {events.length} events
                </p>
                <h2 id="events-title">Event history</h2>
              </div>
              {events.length > 5 && (
                <button
                  className="disclosure-button"
                  type="button"
                  aria-expanded={showAllEvents}
                  onClick={() => setShowAllEvents((current) => !current)}
                >
                  {showAllEvents
                    ? "Show recent"
                    : `View all ${events.length} events`}
                </button>
              )}
            </div>
            {events.length === 0 ? (
              <p className="empty-state empty-state--compact">
                {supplementalFailures.includes("events")
                  ? "Events unavailable."
                  : "No workflow events are recorded yet."}
              </p>
            ) : (
              <ol className="workflow-events">
                {events
                  .slice()
                  .reverse()
                  .slice(0, showAllEvents ? events.length : 5)
                  .map((item) => (
                    <li key={item.id}>
                      <span className="event-marker" aria-hidden="true" />
                      <div>
                        <strong title={item.event_type}>
                          {eventLabel(item.event_type)}
                        </strong>
                        <span>
                          {item.stage_name
                            ? stageLabel(item.stage_name)
                            : "Workflow"}
                          {item.duration_ms !== null &&
                          item.duration_ms !== undefined
                            ? ` · ${formatDuration(item.duration_ms)}`
                            : ""}
                        </span>
                      </div>
                      <time dateTime={item.created_at}>
                        {formatTimestamp(item.created_at)}
                      </time>
                    </li>
                  ))}
              </ol>
            )}
          </section>
        </div>
      )}
      {!run && !loading && !error && (
        <div className="empty-state">
          <strong>No workflow selected</strong>
          <p>Select a corpus and run to inspect agent execution.</p>
        </div>
      )}
    </div>
  );
}
