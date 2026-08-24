import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";

import type { CorpusSummary } from "./App";
import CorpusSelect from "./CorpusSelect";
import { requestJson, type ApiError } from "./api";
import type { SourceSummary } from "./corpus";
import {
  formatTimestamp,
  humanize,
  outcomeClass,
  workflowStatusLabel,
} from "./ui";
import type { Workspace } from "./workspace";

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

interface ReviewFact {
  id: string;
  category: string;
  subject_key: string;
  normalized_value: string;
  support_status: string;
}

interface ReviewContradiction {
  id: string;
  contradiction_type: string;
  reason: string;
  status: string;
  fact_a: ReviewFact;
  fact_b: ReviewFact;
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
  structured_reason: Record<string, unknown>;
  proposed_content: Record<string, unknown>;
  edited_content: string | null;
  edited_content_is_reviewer_authored: boolean;
  citations: ReviewCitation[];
  grounded_facts: ReviewFact[];
  contradictions: ReviewContradiction[];
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

const reviewErrorCopy = {
  detail: "The review request failed.",
  action: "Retry the review operation.",
};

function reasonEntries(reason: Record<string, unknown>) {
  return Object.entries(reason).filter(
    ([, value]) =>
      typeof value === "string" ||
      typeof value === "number" ||
      typeof value === "boolean",
  );
}

function citationForFact(
  item: ReviewItem,
  fact: ReviewFact,
  fallbackIndex: number,
) {
  return (
    item.citations.find((citation) =>
      citation.exact_quote.includes(fact.normalized_value),
    ) ?? item.citations[fallbackIndex]
  );
}

export default function ReviewPanel({
  corpora = [],
  corporaLoading = false,
  sourcesByCorpus = {},
  workspace,
  onWorkspaceChange,
  onReturnToWorkflow,
  active = true,
}: {
  corpora?: CorpusSummary[];
  corporaLoading?: boolean;
  sourcesByCorpus?: Record<string, SourceSummary[]>;
  workspace?: Workspace;
  onWorkspaceChange?: (workspace: Workspace) => void;
  onReturnToWorkflow?: () => void;
  active?: boolean;
}) {
  const [corpusId, setCorpusId] = useState(workspace?.corpusId ?? "");
  const [examinationRunId, setExaminationRunId] = useState(
    workspace?.examinationRunId ?? "",
  );
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
  const [editingItems, setEditingItems] = useState<Record<string, boolean>>({});
  const [detailItems, setDetailItems] = useState<Record<string, boolean>>({});

  const busy = loading || pendingAction !== null;
  const pendingRequired = useMemo(
    () =>
      items.filter(
        (item) => item.review_required && item.review_status === "pending",
      ).length,
    [items],
  );

  const lastOpenedKey = useRef("");
  const [syncedWorkspaceKey, setSyncedWorkspaceKey] = useState(
    `${workspace?.corpusId ?? ""}:${workspace?.examinationRunId ?? ""}`,
  );
  const incomingWorkspaceKey = `${workspace?.corpusId ?? ""}:${workspace?.examinationRunId ?? ""}`;
  if (incomingWorkspaceKey !== syncedWorkspaceKey) {
    setSyncedWorkspaceKey(incomingWorkspaceKey);
    if (workspace?.corpusId) {
      setCorpusId(workspace.corpusId);
    }
    if (workspace?.examinationRunId) {
      setExaminationRunId(workspace.examinationRunId);
    }
  }

  async function openSessionFor(
    nextCorpusId: string,
    nextExaminationId: string,
  ) {
    setError(null);
    setNotice(null);
    setLoading(true);
    try {
      const opened = await requestJson<ReviewSession>(
        `/api/corpora/${nextCorpusId}/examination-runs/${nextExaminationId}/review-sessions`,
        reviewErrorCopy,
        { method: "POST" },
      );
      const listed = await requestJson<ReviewItem[]>(
        `/api/corpora/${opened.corpus_id}/review-sessions/${opened.id}/items`,
        reviewErrorCopy,
      );
      setSession(opened);
      setItems(listed);
      onWorkspaceChange?.({
        corpusId: opened.corpus_id,
        workflowRunId: workspace?.workflowRunId ?? "",
        examinationRunId: opened.examination_run_id,
        reviewSessionId: opened.id,
        workflowStatus: workspace?.workflowStatus ?? null,
        reviewStatus: opened.status,
      });
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

  async function openSession(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    lastOpenedKey.current = `${corpusId}:${examinationRunId}`;
    await openSessionFor(corpusId, examinationRunId);
  }

  useEffect(() => {
    if (!active || !workspace?.corpusId || !workspace.examinationRunId) {
      return;
    }
    const key = `${workspace.corpusId}:${workspace.examinationRunId}`;
    if (lastOpenedKey.current === key) {
      return;
    }
    lastOpenedKey.current = key;
    void openSessionFor(workspace.corpusId, workspace.examinationRunId);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- keyed by corpus/examination identity
  }, [active, workspace?.corpusId, workspace?.examinationRunId]);

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
        reviewErrorCopy,
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
        reviewErrorCopy,
        { method: "POST" },
      );
      setSession(completed);
      onWorkspaceChange?.({
        corpusId: completed.corpus_id,
        workflowRunId: workspace?.workflowRunId ?? "",
        examinationRunId: completed.examination_run_id,
        reviewSessionId: completed.id,
        workflowStatus: workspace?.workflowStatus ?? null,
        reviewStatus: completed.status,
      });
      setNotice("Review session completed after explicit decisions.");
    } catch (caught) {
      setError(caught as ApiError);
    } finally {
      setPendingAction(null);
    }
  }

  return (
    <div className="page page--review" aria-busy={busy}>
      <header className="page-header">
        <div>
          <p className="eyebrow">Explicit decision gate</p>
          <h1 id="review-title">Human Review</h1>
          <p>
            Inspect grounded evidence and explicitly approve, reject, or author
            a clearly separated reviewer edit.
          </p>
        </div>
        <span className="boundary-chip">No automatic decisions</span>
      </header>

      <section className="picker-panel">
        {workspace?.examinationRunId ? (
          <div className="workflow-cta">
            <div>
              <h2>Review from selected run</h2>
              <p>Open the examination attached to the current agent run.</p>
            </div>
            <button
              className="button button--primary"
              type="button"
              disabled={busy || !corpusId || !examinationRunId}
              onClick={() => void openSessionFor(corpusId, examinationRunId)}
            >
              {loading ? "Opening review…" : "Open selected review"}
            </button>
          </div>
        ) : null}
        <form onSubmit={(event) => void openSession(event)}>
          <div className="form-grid form-grid--primary">
            <div className="field">
              <label htmlFor="corpus-id">Corpus</label>
              <CorpusSelect
                id="corpus-id"
                corpora={corpora}
                sourcesByCorpus={sourcesByCorpus}
                value={corpusId}
                onChange={setCorpusId}
                disabled={busy}
                loading={corporaLoading}
              />
            </div>
          </div>
          <details className="advanced-lookup">
            <summary>Advanced lookup</summary>
            <p className="lookup-lead">Optional technical recovery path</p>
            <div className="form-grid form-grid--action">
              <div className="field">
                <label htmlFor="examination-run-id">Examination run ID</label>
                <input
                  id="examination-run-id"
                  name="examinationRunId"
                  value={examinationRunId}
                  onChange={(event) => setExaminationRunId(event.target.value)}
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
                  {loading ? "Opening review…" : "Open review"}
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
      {notice && (
        <div className="review-banner review-banner--ok" role="status">
          {notice}
        </div>
      )}

      {loading && (
        <section className="panel skeleton-panel" aria-label="Loading review">
          <span className="skeleton skeleton--line skeleton--wide" />
          <span className="skeleton skeleton--card skeleton--tall" />
        </section>
      )}

      {session && (
        <section
          className="panel review-summary"
          aria-labelledby="session-title"
        >
          <div className="summary-heading">
            <div>
              <p className="section-kicker">Review session</p>
              <h2 id="session-title">
                {workflowStatusLabel(session.status)}
                {session.status === "completed" ? " · Immutable" : ""}
              </h2>
            </div>
            <span
              className={`status-chip status-chip--${outcomeClass(
                session.status === "completed" ? "pass" : "warning",
              )}`}
            >
              {workflowStatusLabel(session.status)}
            </span>
          </div>
          <dl className="metric-grid">
            <div>
              <dt>Pending required</dt>
              <dd>{session.pending_count}</dd>
            </div>
            <div>
              <dt>Approved</dt>
              <dd>{session.approved_count}</dd>
            </div>
            <div>
              <dt>Rejected</dt>
              <dd>{session.rejected_count}</dd>
            </div>
            <div>
              <dt>Reviewer edited</dt>
              <dd>{session.edited_count}</dd>
            </div>
          </dl>
          {session.status !== "completed" && (
            <button
              className="button button--primary"
              type="button"
              onClick={() => void completeSession()}
              disabled={
                busy || !session.completion_allowed || pendingRequired > 0
              }
            >
              Complete review
            </button>
          )}
          {session.status !== "completed" &&
            (busy || !session.completion_allowed || pendingRequired > 0) && (
              <p className="helper-text">
                Decide all required findings before completing review.
              </p>
            )}
          {session.status === "completed" && (
            <div className="workflow-cta" aria-labelledby="review-complete-cta">
              <div>
                <h2 id="review-complete-cta">Review complete</h2>
                <p>The workflow may now resume.</p>
              </div>
              {onReturnToWorkflow && (
                <button
                  className="button button--primary"
                  type="button"
                  onClick={onReturnToWorkflow}
                >
                  Return to agent run
                </button>
              )}
            </div>
          )}
          <details className="technical-details">
            <summary>Technical details</summary>
            <dl className="technical-grid">
              <div>
                <dt>Review session ID</dt>
                <dd>
                  <code>{session.id}</code>
                </dd>
              </div>
              <div>
                <dt>Examination run ID</dt>
                <dd>
                  <code>{session.examination_run_id}</code>
                </dd>
              </div>
            </dl>
          </details>
        </section>
      )}

      <ul className="review-items">
        {items.map((item) => {
          const primaryCitation = item.citations[0];
          const unknown = item.outcome === "unknown";
          const detailsOpen = Boolean(detailItems[item.id]);
          const editOpen = Boolean(editingItems[item.id]);
          return (
            <li
              key={item.id}
              className={`review-item review-item--${outcomeClass(item.outcome)} ${
                item.review_required
                  ? "review-item--required"
                  : "review-item--optional"
              }`}
            >
              <article aria-labelledby={`finding-${item.id}`}>
                <header className="finding-header">
                  <div className="chip-row">
                    <span
                      className={`outcome-chip outcome-chip--${outcomeClass(
                        item.outcome,
                      )}`}
                    >
                      <span aria-hidden="true">
                        {item.outcome === "pass"
                          ? "✓"
                          : item.outcome === "fail"
                            ? "×"
                            : item.outcome === "warning"
                              ? "!"
                              : "?"}
                      </span>{" "}
                      {item.outcome.toUpperCase()}
                    </span>
                    <span className="severity-chip">
                      {humanize(item.severity)} severity
                    </span>
                    <span className="review-state-chip">
                      {humanize(item.review_status)}
                    </span>
                    <span
                      className={
                        item.review_required ? "required-chip" : "optional-chip"
                      }
                    >
                      {item.review_required
                        ? "Review required"
                        : "Review optional"}
                    </span>
                  </div>
                  <h2 id={`finding-${item.id}`}>{item.title}</h2>
                </header>

                {unknown ? (
                  <section
                    className="unknown-state"
                    aria-label="Insufficient evidence"
                  >
                    <span>UNKNOWN</span>
                    <strong>No grounded evidence found</strong>
                    <p>{item.message}</p>
                    <small>No citation claimed.</small>
                  </section>
                ) : (
                  <p className="finding-summary">{item.message}</p>
                )}

                {primaryCitation && (
                  <blockquote className="primary-evidence">
                    <span className="authorship-label">SYSTEM-GROUNDED</span>
                    <p>“{primaryCitation.exact_quote}”</p>
                    <footer>
                      <strong>
                        {primaryCitation.source_logical_name ?? "Source"}
                      </strong>
                      <span>{primaryCitation.native_locator}</span>
                    </footer>
                  </blockquote>
                )}

                {(item.contradictions ?? []).length > 0 && (
                  <section
                    className="contradiction-section"
                    aria-label="Contradictory evidence"
                  >
                    <div className="contradiction-heading">
                      <h3>Contradictory evidence</h3>
                      <span>Contradiction retained</span>
                    </div>
                    {item.contradictions.map((contradiction) => (
                      <div className="contradiction" key={contradiction.id}>
                        <p>{contradiction.reason}</p>
                        <div className="contradiction-sides">
                          {[contradiction.fact_a, contradiction.fact_b].map(
                            (fact, index) => {
                              const citation = citationForFact(
                                item,
                                fact,
                                index,
                              );
                              return (
                                <div key={fact.id}>
                                  <span>
                                    Evidence {index === 0 ? "A" : "B"}
                                  </span>
                                  <strong>{fact.normalized_value}</strong>
                                  <small>
                                    {citation?.source_logical_name ?? "Source"}
                                  </small>
                                </div>
                              );
                            },
                          )}
                        </div>
                      </div>
                    ))}
                  </section>
                )}

                {item.edited_content && (
                  <section className="authorship-block authorship-block--reviewer">
                    <span className="authorship-label">
                      REVIEWER-AUTHORED EDIT
                    </span>
                    <strong>NOT SYSTEM-GROUNDED</strong>
                    <p>{item.edited_content}</p>
                  </section>
                )}

                <div className="finding-actions" aria-label="Finding actions">
                  <fieldset disabled={busy || session?.status === "completed"}>
                    <legend className="visually-hidden">
                      Record reviewer decision
                    </legend>
                    <button
                      className="button button--approve"
                      type="button"
                      aria-label={`Approve ${item.title}`}
                      onClick={() => void decide(item, "approve")}
                    >
                      Approve
                    </button>
                    <button
                      className="button button--reject"
                      type="button"
                      aria-label={`Reject ${item.title}`}
                      onClick={() => void decide(item, "reject")}
                    >
                      Reject
                    </button>
                    <button
                      className="button button--secondary"
                      type="button"
                      aria-label={`Edit ${item.title}`}
                      aria-expanded={editOpen}
                      onClick={() =>
                        setEditingItems((current) => ({
                          ...current,
                          [item.id]: !current[item.id],
                        }))
                      }
                    >
                      Edit
                    </button>
                  </fieldset>
                  <button
                    className="button button--quiet"
                    type="button"
                    aria-expanded={detailsOpen}
                    aria-controls={`details-${item.id}`}
                    onClick={() =>
                      setDetailItems((current) => ({
                        ...current,
                        [item.id]: !current[item.id],
                      }))
                    }
                  >
                    {detailsOpen ? "Hide details" : "Details"}
                  </button>
                </div>

                {editOpen && session?.status !== "completed" && (
                  <section className="reviewer-edit" aria-label="Reviewer edit">
                    <div>
                      <span className="authorship-label">
                        REVIEWER-AUTHORED
                      </span>
                      <strong>NOT SYSTEM-GROUNDED</strong>
                    </div>
                    <label htmlFor={`edit-${item.id}`}>
                      Reviewer-authored edit
                    </label>
                    <textarea
                      id={`edit-${item.id}`}
                      value={editDrafts[item.id] ?? ""}
                      rows={4}
                      maxLength={8000}
                      onChange={(event) =>
                        setEditDrafts((current) => ({
                          ...current,
                          [item.id]: event.target.value,
                        }))
                      }
                    />
                    <label className="acknowledgement">
                      <input
                        type="checkbox"
                        checked={Boolean(editConfirmed[item.id])}
                        onChange={(event) =>
                          setEditConfirmed((current) => ({
                            ...current,
                            [item.id]: event.target.checked,
                          }))
                        }
                      />
                      <span>
                        I confirm this edit is reviewer-authored and not
                        system-grounded evidence.
                      </span>
                    </label>
                    <button
                      className="button button--edit"
                      type="button"
                      aria-label={`Submit reviewer edit for ${item.title}`}
                      disabled={
                        busy ||
                        !editConfirmed[item.id] ||
                        !(editDrafts[item.id] ?? "").trim()
                      }
                      onClick={() => void decide(item, "edit")}
                    >
                      Submit reviewer edit
                    </button>
                  </section>
                )}

                {detailsOpen && (
                  <section
                    id={`details-${item.id}`}
                    className="finding-details"
                    aria-label={`Technical details for ${item.title}`}
                  >
                    <h3>Finding details</h3>
                    <dl className="technical-grid">
                      <div>
                        <dt>Rule ID</dt>
                        <dd>
                          <code>{item.rule_id}</code>
                        </dd>
                      </div>
                      <div>
                        <dt>Finding ID</dt>
                        <dd>
                          <code>{item.finding_id}</code>
                        </dd>
                      </div>
                      <div>
                        <dt>Evidence kind</dt>
                        <dd>
                          <code>{item.evidence_kind}</code>
                        </dd>
                      </div>
                      {reasonEntries(item.structured_reason ?? {}).map(
                        ([key, value]) => (
                          <div key={key}>
                            <dt>{humanize(key)}</dt>
                            <dd>{String(value)}</dd>
                          </div>
                        ),
                      )}
                    </dl>
                    {item.citations.length > 0 && (
                      <div className="citation-list">
                        {item.citations.map((citation) => (
                          <blockquote
                            key={`${citation.source_version_id}-${citation.native_locator}`}
                            className="citation"
                          >
                            <p>“{citation.exact_quote}”</p>
                            <footer>
                              <strong>
                                {citation.source_logical_name ?? "Source"}
                              </strong>
                              <span>{citation.native_locator}</span>
                              <code>
                                Source version {citation.source_version_id} ·
                                SHA-256 {citation.source_sha256}
                              </code>
                            </footer>
                          </blockquote>
                        ))}
                      </div>
                    )}
                    {(item.decisions ?? []).length > 0 && (
                      <details className="decision-history">
                        <summary>
                          Decision history ({item.decisions.length})
                        </summary>
                        <ol>
                          {item.decisions.map((decision) => (
                            <li key={decision.id}>
                              <strong>{humanize(decision.action)}</strong> by{" "}
                              {decision.actor} ·{" "}
                              {formatTimestamp(decision.decided_at)}
                              {decision.comment && <p>{decision.comment}</p>}
                            </li>
                          ))}
                        </ol>
                      </details>
                    )}
                  </section>
                )}
              </article>
            </li>
          );
        })}
      </ul>
      {!session && !loading && (
        <div className="empty-state">
          <strong>No review selected</strong>
          <p>Select or open an agent run awaiting review.</p>
        </div>
      )}
    </div>
  );
}
