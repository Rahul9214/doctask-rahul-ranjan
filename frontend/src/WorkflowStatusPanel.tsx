import { useState, type FormEvent } from "react";

interface ApiError {
  code: string;
  detail: string;
  action?: string;
}

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

async function readError(response: Response): Promise<ApiError> {
  try {
    const body = (await response.json()) as ApiError;
    return {
      code: body.code || "request_failed",
      detail: body.detail || "The workflow request failed.",
      action: body.action,
    };
  } catch {
    return {
      code: "request_failed",
      detail: "The workflow request failed.",
      action: "Retry the workflow operation.",
    };
  }
}

async function requestJson<T>(input: string, init?: RequestInit): Promise<T> {
  const response = await fetch(input, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    throw await readError(response);
  }
  return (await response.json()) as T;
}

export default function WorkflowStatusPanel() {
  const [corpusId, setCorpusId] = useState("");
  const [workflowRunId, setWorkflowRunId] = useState("");
  const [run, setRun] = useState<WorkflowRun | null>(null);
  const [events, setEvents] = useState<WorkflowEvent[]>([]);
  const [review, setReview] = useState<ReviewSession | null>(null);
  const [revision, setRevision] = useState<CorpusRevision | null>(null);
  const [revisionMissing, setRevisionMissing] = useState(false);
  const [loading, setLoading] = useState(false);
  const [pendingAction, setPendingAction] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  const busy = loading || pendingAction !== null;
  const canResume =
    run !== null &&
    (run.status === "failed" ||
      (run.status === "waiting_for_review" && review?.status === "completed"));

  async function loadStatus(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    setError(null);
    setRun(null);
    setEvents([]);
    setReview(null);
    setRevision(null);
    setRevisionMissing(false);
    setLoading(true);
    try {
      const loaded = await requestJson<WorkflowRun>(
        `/api/corpora/${corpusId}/workflow-runs/${workflowRunId}`,
      );
      const loadedEvents = await requestJson<WorkflowEvent[]>(
        `/api/corpora/${corpusId}/workflow-runs/${workflowRunId}/events`,
      );
      setRun(loaded);
      setEvents(loadedEvents);
      if (loaded.review_session_id) {
        setReview(
          await requestJson<ReviewSession>(
            `/api/corpora/${loaded.corpus_id}/review-sessions/${loaded.review_session_id}`,
          ),
        );
      } else {
        setReview(null);
      }
      try {
        const current = await requestJson<CorpusRevision>(
          `/api/corpora/${loaded.corpus_id}/revisions/current`,
        );
        setRevision(current);
        setRevisionMissing(false);
      } catch (caught) {
        const apiError = caught as ApiError;
        if (apiError.code === "corpus_revision_not_found") {
          setRevision(null);
          setRevisionMissing(true);
        } else {
          throw caught;
        }
      }
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
        { method: "POST" },
      );
      setRun(resumed);
      const loadedEvents = await requestJson<WorkflowEvent[]>(
        `/api/corpora/${run.corpus_id}/workflow-runs/${run.id}/events`,
      );
      setEvents(loadedEvents);
      if (resumed.review_session_id) {
        setReview(
          await requestJson<ReviewSession>(
            `/api/corpora/${resumed.corpus_id}/review-sessions/${resumed.review_session_id}`,
          ),
        );
      }
    } catch (caught) {
      setError(caught as ApiError);
    } finally {
      setPendingAction(null);
    }
  }

  return (
    <section
      className="workflow-panel"
      aria-labelledby="workflow-title"
      aria-busy={busy}
    >
      <h2 id="workflow-title">Workflow status</h2>
      <p>
        Inspect a durable workflow run, recent events, review state, and the
        current corpus revision. Resume does not create review decisions.
      </p>

      <form
        className="review-open"
        onSubmit={(event) => void loadStatus(event)}
      >
        <label htmlFor="workflow-corpus-id">Workflow corpus ID</label>
        <input
          id="workflow-corpus-id"
          name="workflowCorpusId"
          value={corpusId}
          onChange={(event) => setCorpusId(event.target.value)}
          required
          disabled={busy}
        />
        <label htmlFor="workflow-run-id">Workflow run ID</label>
        <input
          id="workflow-run-id"
          name="workflowRunId"
          value={workflowRunId}
          onChange={(event) => setWorkflowRunId(event.target.value)}
          required
          disabled={busy}
        />
        <button type="submit" disabled={busy}>
          {loading ? "Loading status…" : "Load workflow status"}
        </button>
      </form>

      {error && (
        <div className="review-banner review-banner--error" role="alert">
          <p>{error.detail}</p>
          {error.action && <p>Next action: {error.action}</p>}
        </div>
      )}

      {run && (
        <div className="workflow-summary">
          <dl className="version-grid">
            <div>
              <dt>Workflow run</dt>
              <dd>{run.id}</dd>
            </div>
            <div>
              <dt>Status</dt>
              <dd>{run.status}</dd>
            </div>
            <div>
              <dt>Current stage</dt>
              <dd>{run.current_stage}</dd>
            </div>
            <div>
              <dt>Resume count</dt>
              <dd>{run.resume_count}</dd>
            </div>
            <div>
              <dt>Review status</dt>
              <dd>{review?.status ?? "not opened"}</dd>
            </div>
            <div>
              <dt>Current corpus revision</dt>
              <dd>
                {revision
                  ? `revision ${revision.revision_number}`
                  : revisionMissing
                    ? "none"
                    : "unknown"}
              </dd>
            </div>
          </dl>
          {canResume && (
            <button
              type="button"
              onClick={() => void resumeRun()}
              disabled={busy}
            >
              Resume workflow
            </button>
          )}
          {run.status === "waiting_for_review" &&
            review?.status !== "completed" && (
              <p>
                Resume is available after the linked review session is
                completed.
              </p>
            )}
          {run.status === "completed" && (
            <p>Completed workflows cannot be resumed.</p>
          )}
          {(run.status === "pending" || run.status === "running") && (
            <p>
              A running or pending workflow cannot be resumed from this panel.
            </p>
          )}
          {run.error_detail && (
            <p>
              {run.error_detail}
              {run.error_action ? ` Next action: ${run.error_action}` : ""}
            </p>
          )}
          <h3>Recent events</h3>
          {events.length === 0 ? (
            <p>No workflow events are recorded yet.</p>
          ) : (
            <ol className="workflow-events">
              {events.map((item) => (
                <li key={item.id}>
                  {item.event_type}
                  {item.stage_name ? ` · ${item.stage_name}` : ""}
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
    </section>
  );
}
