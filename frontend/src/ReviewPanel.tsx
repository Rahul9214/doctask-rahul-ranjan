import { useMemo, useState, type FormEvent } from "react";

interface ApiError {
  code: string;
  detail: string;
  action?: string;
}

interface ReviewCitation {
  source_version_id: string;
  source_sha256: string;
  format: string;
  native_locator: string;
  normalized_start: number;
  normalized_end: number;
  exact_quote: string;
  source_logical_name: string | null;
  source_block_id: string | null;
}

interface ReviewDecision {
  id: string;
  action: string;
  previous_status: string;
  new_status: string;
  edited_content: string | null;
  edited_content_is_reviewer_authored: boolean;
  reviewer_authored_acknowledged: boolean;
  comment: string | null;
  actor: string;
  decision_source: string;
  decided_at: string;
}

interface ReviewItem {
  id: string;
  finding_id: string;
  rule_id: string;
  title: string;
  outcome: string;
  severity: string;
  message: string;
  evidence_kind: string;
  review_required: boolean;
  review_status: string;
  proposed_content: Record<string, unknown>;
  edited_content: string | null;
  edited_content_is_reviewer_authored: boolean;
  citations: ReviewCitation[];
  decisions: ReviewDecision[];
}

interface ReviewSession {
  id: string;
  corpus_id: string;
  examination_run_id: string;
  status: string;
  pending_count: number;
  approved_count: number;
  rejected_count: number;
  edited_count: number;
  required_item_count: number;
  optional_item_count: number;
  completion_allowed: boolean;
  completed_at: string | null;
}

interface DecisionResult {
  session: ReviewSession;
  item: ReviewItem;
}

async function readError(response: Response): Promise<ApiError> {
  try {
    const body = (await response.json()) as ApiError;
    return {
      code: body.code || "request_failed",
      detail: body.detail || "The review request failed.",
      action: body.action,
    };
  } catch {
    return {
      code: "request_failed",
      detail: "The review request failed.",
      action: "Retry the review operation.",
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

export default function ReviewPanel() {
  const [corpusId, setCorpusId] = useState("");
  const [examinationRunId, setExaminationRunId] = useState("");
  const [session, setSession] = useState<ReviewSession | null>(null);
  const [items, setItems] = useState<ReviewItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [pendingAction, setPendingAction] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [editDrafts, setEditDrafts] = useState<Record<string, string>>({});
  const [editConfirmed, setEditConfirmed] = useState<Record<string, boolean>>(
    {},
  );

  const busy = loading || pendingAction !== null;
  const pendingRequired = useMemo(
    () =>
      items.filter(
        (item) => item.review_required && item.review_status === "pending",
      ).length,
    [items],
  );

  async function openSession(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setNotice(null);
    setLoading(true);
    try {
      const opened = await requestJson<ReviewSession>(
        `/api/corpora/${corpusId}/examination-runs/${examinationRunId}/review-sessions`,
        { method: "POST" },
      );
      const listed = await requestJson<ReviewItem[]>(
        `/api/corpora/${opened.corpus_id}/review-sessions/${opened.id}/items`,
      );
      setSession(opened);
      setItems(listed);
      setNotice(
        opened.status === "completed"
          ? "Loaded a completed review session."
          : "Review session is waiting for explicit item-level decisions.",
      );
    } catch (caught) {
      setSession(null);
      setItems([]);
      setError(caught as ApiError);
    } finally {
      setLoading(false);
    }
  }

  async function decide(
    item: ReviewItem,
    action: "approve" | "reject" | "edit",
  ) {
    if (!session) {
      return;
    }
    setError(null);
    setNotice(null);
    setPendingAction(`${action}:${item.id}`);
    try {
      const payload: {
        action: "approve" | "reject" | "edit";
        decision_source: "ui";
        actor: string;
        edited_content?: string;
        reviewer_authored_acknowledged?: boolean;
      } = {
        action,
        decision_source: "ui",
        actor: "reviewer",
      };
      if (action === "edit") {
        payload.edited_content = editDrafts[item.id]?.trim() ?? "";
        payload.reviewer_authored_acknowledged = Boolean(
          editConfirmed[item.id],
        );
      }
      const result = await requestJson<DecisionResult>(
        `/api/corpora/${session.corpus_id}/review-sessions/${session.id}/items/${item.id}/decisions`,
        { method: "POST", body: JSON.stringify(payload) },
      );
      setSession(result.session);
      setItems((current) =>
        current.map((entry) =>
          entry.id === result.item.id ? result.item : entry,
        ),
      );
      setNotice(`${action} recorded for ${item.title}.`);
    } catch (caught) {
      setError(caught as ApiError);
    } finally {
      setPendingAction(null);
    }
  }

  async function completeSession() {
    if (!session) {
      return;
    }
    setError(null);
    setNotice(null);
    setPendingAction("complete");
    try {
      const completed = await requestJson<ReviewSession>(
        `/api/corpora/${session.corpus_id}/review-sessions/${session.id}/complete`,
        { method: "POST" },
      );
      setSession(completed);
      setNotice("Review session completed after explicit decisions.");
    } catch (caught) {
      setError(caught as ApiError);
    } finally {
      setPendingAction(null);
    }
  }

  return (
    <section className="review-panel" aria-labelledby="review-title">
      <h2 id="review-title">Human review</h2>
      <p>
        Findings stay pending until an explicit approve, reject, or
        reviewer-authored edit is submitted. Completion is blocked while
        required items are pending.
      </p>

      <form
        className="review-open"
        onSubmit={(event) => void openSession(event)}
      >
        <label htmlFor="corpus-id">Corpus ID</label>
        <input
          id="corpus-id"
          name="corpusId"
          value={corpusId}
          onChange={(event) => setCorpusId(event.target.value)}
          required
          disabled={busy}
        />
        <label htmlFor="examination-run-id">Examination run ID</label>
        <input
          id="examination-run-id"
          name="examinationRunId"
          value={examinationRunId}
          onChange={(event) => setExaminationRunId(event.target.value)}
          required
          disabled={busy}
        />
        <button type="submit" disabled={busy}>
          {loading ? "Opening review…" : "Open review session"}
        </button>
      </form>

      {error && (
        <div className="review-banner review-banner--error" role="alert">
          <p>{error.detail}</p>
          {error.action && <p>Next action: {error.action}</p>}
        </div>
      )}
      {notice && (
        <div className="review-banner review-banner--ok" role="status">
          {notice}
        </div>
      )}

      {session && (
        <div className="review-summary">
          <p>
            Status: {session.status}. Pending required: {session.pending_count}.
            Approved: {session.approved_count}. Rejected:{" "}
            {session.rejected_count}. Edited: {session.edited_count}.
          </p>
          <button
            type="button"
            onClick={() => void completeSession()}
            disabled={
              busy ||
              session.status === "completed" ||
              !session.completion_allowed ||
              pendingRequired > 0
            }
          >
            Complete review session
          </button>
          {pendingRequired > 0 && (
            <p>
              Completion stays disabled until every required item has an
              explicit decision.
            </p>
          )}
        </div>
      )}

      <ul className="review-items">
        {items.map((item) => (
          <li key={item.id} className="review-item">
            <h3>{item.title}</h3>
            <p>
              {item.rule_id} · outcome {item.outcome} · severity {item.severity}{" "}
              · {item.review_required ? "review required" : "optional"} ·{" "}
              {item.review_status}
            </p>
            <p>{item.message}</p>
            {item.edited_content && (
              <p>
                Reviewer-authored edit: {item.edited_content}
                {item.edited_content_is_reviewer_authored
                  ? " This text is not system-grounded evidence."
                  : ""}
              </p>
            )}
            {item.citations.length > 0 ? (
              <ul>
                {item.citations.map((citation) => (
                  <li
                    key={`${citation.source_version_id}-${citation.native_locator}`}
                  >
                    {citation.source_logical_name ?? "Source"} ·{" "}
                    {citation.native_locator}: “{citation.exact_quote}”
                  </li>
                ))}
              </ul>
            ) : (
              <p>No grounded source citations are attached to this finding.</p>
            )}
            <div className="review-actions">
              <button
                type="button"
                aria-label={`Approve ${item.title}`}
                disabled={busy || session?.status === "completed"}
                onClick={() => void decide(item, "approve")}
              >
                Approve
              </button>
              <button
                type="button"
                aria-label={`Reject ${item.title}`}
                disabled={busy || session?.status === "completed"}
                onClick={() => void decide(item, "reject")}
              >
                Reject
              </button>
              <label htmlFor={`edit-${item.id}`}>Reviewer-authored edit</label>
              <textarea
                id={`edit-${item.id}`}
                value={editDrafts[item.id] ?? ""}
                disabled={busy || session?.status === "completed"}
                onChange={(event) =>
                  setEditDrafts((current) => ({
                    ...current,
                    [item.id]: event.target.value,
                  }))
                }
              />
              <label>
                <input
                  type="checkbox"
                  checked={Boolean(editConfirmed[item.id])}
                  disabled={busy || session?.status === "completed"}
                  onChange={(event) =>
                    setEditConfirmed((current) => ({
                      ...current,
                      [item.id]: event.target.checked,
                    }))
                  }
                />{" "}
                I confirm this edit is reviewer-authored and not system-grounded
                evidence.
              </label>
              <button
                type="button"
                aria-label={`Edit ${item.title}`}
                disabled={
                  busy ||
                  session?.status === "completed" ||
                  !editConfirmed[item.id] ||
                  !(editDrafts[item.id] ?? "").trim()
                }
                onClick={() => void decide(item, "edit")}
              >
                Submit edit
              </button>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
