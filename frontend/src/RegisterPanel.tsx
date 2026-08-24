import { useState, type FormEvent } from "react";

import type { CorpusSummary } from "./App";
import CorpusSelect from "./CorpusSelect";
import { requestJson, type ApiError } from "./api";
import type { SourceSummary } from "./corpus";
import { formatTimestamp, humanize, outcomeClass } from "./ui";
import type { Workspace } from "./workspace";

interface RegisterCitation {
  source_logical_name: string | null;
  source_version_id: string;
  native_locator: string;
  exact_quote: string;
  source_sha256: string;
}

interface RegisterFact {
  id: string;
  category: string;
  subject_key: string;
  normalized_value: string;
  support_status: string;
}

interface RegisterContradiction {
  id: string;
  contradiction_type: string;
  reason: string;
  status: string;
  fact_a: RegisterFact;
  fact_b: RegisterFact;
}

interface RegisterItem {
  id: string;
  rule_id: string;
  rule_version: string;
  title: string;
  outcome: string;
  severity: string;
  message: string;
  structured_reason: Record<string, unknown>;
  evidence_kind: string;
  review_status: string;
  content_origin: string;
  system_grounded: boolean;
  reviewer_authored: boolean;
  reviewer_authored_content: string | null;
  reviewer_authored_acknowledged: boolean;
  grounded_facts: RegisterFact[];
  citations: RegisterCitation[];
  contradictions: RegisterContradiction[];
}

interface PublishedRegister {
  id: string;
  corpus_id: string;
  publication_number: number;
  is_current: boolean;
  review_session_id: string;
  status: string;
  register_status: string;
  version_identity: string;
  published_at: string;
  applied_count: number;
  rejected_omitted_count: number;
  omitted_rejected_rule_ids: string[];
  items: RegisterItem[];
}

interface ReviewSession {
  id: string;
  status: string;
  pending_count: number;
  approved_count?: number;
  rejected_count?: number;
  edited_count?: number;
  completion_allowed: boolean;
}

const registerErrorCopy = {
  detail: "The register request failed.",
  action: "Retry the register operation.",
};

export default function RegisterPanel({
  corpora = [],
  corporaLoading = false,
  sourcesByCorpus = {},
  workspace,
  onWorkspaceChange,
}: {
  corpora?: CorpusSummary[];
  corporaLoading?: boolean;
  sourcesByCorpus?: Record<string, SourceSummary[]>;
  workspace?: Workspace;
  onWorkspaceChange?: (workspace: Workspace) => void;
}) {
  const [corpusId, setCorpusId] = useState(workspace?.corpusId ?? "");
  const [reviewSessionId, setReviewSessionId] = useState(
    workspace?.reviewSessionId ?? "",
  );
  const [review, setReview] = useState<ReviewSession | null>(null);
  const [register, setRegister] = useState<PublishedRegister | null>(null);
  const [loading, setLoading] = useState(false);
  const [pendingAction, setPendingAction] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  const busy = loading || pendingAction !== null;
  const canPublish = review?.status === "completed";
  const [syncedCorpusId, setSyncedCorpusId] = useState(
    workspace?.corpusId ?? "",
  );
  const [syncedReviewSessionId, setSyncedReviewSessionId] = useState(
    workspace?.reviewSessionId ?? "",
  );
  if ((workspace?.corpusId ?? "") !== syncedCorpusId) {
    setSyncedCorpusId(workspace?.corpusId ?? "");
    if (workspace?.corpusId) {
      setCorpusId(workspace.corpusId);
    }
  }
  if ((workspace?.reviewSessionId ?? "") !== syncedReviewSessionId) {
    setSyncedReviewSessionId(workspace?.reviewSessionId ?? "");
    if (workspace?.reviewSessionId) {
      setReviewSessionId(workspace.reviewSessionId);
    }
  }

  async function loadRegister(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    setError(null);
    setRegister(null);
    setReview(null);
    setLoading(true);
    try {
      if (reviewSessionId) {
        setReview(
          await requestJson<ReviewSession>(
            `/api/corpora/${corpusId}/review-sessions/${reviewSessionId}`,
            registerErrorCopy,
          ),
        );
      } else {
        try {
          setRegister(
            await requestJson<PublishedRegister>(
              `/api/corpora/${corpusId}/register`,
              registerErrorCopy,
            ),
          );
        } catch (caught) {
          const apiError = caught as ApiError;
          if (apiError.code !== "publication_not_found") {
            throw caught;
          }
        }
      }
    } catch (caught) {
      setError(caught as ApiError);
    } finally {
      setLoading(false);
    }
  }

  async function publishRegister() {
    if (!reviewSessionId) {
      return;
    }
    setError(null);
    setPendingAction("publish");
    try {
      const published = await requestJson<PublishedRegister>(
        `/api/corpora/${corpusId}/review-sessions/${reviewSessionId}/publish`,
        registerErrorCopy,
        {
          method: "POST",
          body: JSON.stringify({
            actor: "reviewer",
            publication_source: "ui",
          }),
        },
      );
      setRegister(published);
      onWorkspaceChange?.({
        corpusId,
        workflowRunId: workspace?.workflowRunId ?? "",
        examinationRunId: workspace?.examinationRunId ?? "",
        reviewSessionId,
        workflowStatus: workspace?.workflowStatus ?? null,
        reviewStatus: review?.status ?? "completed",
      });
      setReview(
        await requestJson<ReviewSession>(
          `/api/corpora/${corpusId}/review-sessions/${reviewSessionId}`,
          registerErrorCopy,
        ),
      );
    } catch (caught) {
      setError(caught as ApiError);
    } finally {
      setPendingAction(null);
    }
  }

  return (
    <div className="page page--register" aria-busy={busy}>
      <header className="page-header">
        <div>
          <p className="eyebrow">Authoritative assurance output</p>
          <h1 id="register-title">Published Register</h1>
          <p>
            Publication is a separate, explicit action after completed review.
            Approved and edited items are applied; rejected items are omitted.
          </p>
        </div>
        <span className="boundary-chip">Workflow complete ≠ published</span>
      </header>
      <section className="register-inspect" aria-labelledby="inspect-title">
        <div className="card-heading">
          <div>
            <p className="section-kicker">Current register</p>
            <h2 id="inspect-title">Inspect published output</h2>
          </div>
        </div>
        <form
          className="register-inspect-form"
          onSubmit={(event) => void loadRegister(event)}
        >
          <div className="field">
            <div className="field-label-row">
              <label htmlFor="register-corpus-id">Corpus</label>
            </div>
            <CorpusSelect
              id="register-corpus-id"
              corpora={corpora}
              sourcesByCorpus={sourcesByCorpus}
              value={corpusId}
              onChange={setCorpusId}
              disabled={busy}
              loading={corporaLoading}
            />
          </div>
          <div className="field">
            <div className="field-label-row field-label-row--inline">
              <label htmlFor="register-session-id">Review session</label>
              <span className="optional-inline">Optional</span>
            </div>
            <input
              id="register-session-id"
              value={reviewSessionId}
              onChange={(event) => setReviewSessionId(event.target.value)}
              disabled={busy}
              autoComplete="off"
              aria-describedby="register-session-help"
            />
            <p id="register-session-help" className="field-help">
              Only needed to check the publication gate.
            </p>
          </div>
          <div className="register-inspect-form__action">
            <button
              className="button button--secondary"
              type="submit"
              disabled={busy}
            >
              {loading ? "Loading register…" : "Load current register"}
            </button>
          </div>
        </form>
      </section>
      {error && (
        <div className="review-banner review-banner--error" role="alert">
          <p>{error.detail}</p>
          {error.action && <p>Next action: {error.action}</p>}
        </div>
      )}
      {loading && (
        <section className="panel skeleton-panel" aria-label="Loading register">
          <span className="skeleton skeleton--line skeleton--wide" />
          <span className="skeleton skeleton--card skeleton--tall" />
        </section>
      )}
      {review && (
        <div
          className={`publication-gate ${
            review.status === "completed"
              ? "publication-gate--ready"
              : "publication-gate--blocked"
          }`}
        >
          <div>
            <span className="section-kicker">Publication gate</span>
            <strong>
              {review.status === "completed"
                ? "Review completed"
                : "Review awaiting decisions"}
            </strong>
            <p>
              {review.status === "completed"
                ? "The session is ready for explicit publication."
                : "Complete required decisions before publishing."}
            </p>
            <dl className="publication-counts">
              <div>
                <dt>Pending required</dt>
                <dd>{review.pending_count}</dd>
              </div>
              <div>
                <dt>Approved</dt>
                <dd>{review.approved_count ?? "—"}</dd>
              </div>
              <div>
                <dt>Rejected</dt>
                <dd>{review.rejected_count ?? "—"}</dd>
              </div>
              <div>
                <dt>Edited</dt>
                <dd>{review.edited_count ?? "—"}</dd>
              </div>
            </dl>
          </div>
          {canPublish && (
            <button
              className="button button--publish"
              type="button"
              onClick={() => void publishRegister()}
              disabled={busy}
            >
              {pendingAction === "publish"
                ? "Publishing register…"
                : "Publish register"}
            </button>
          )}
        </div>
      )}
      {register && (
        <div className="register-output">
          <div className="register-banner">
            <div>
              <span className="status-chip status-chip--pass">
                Explicitly published
              </span>
              <h2>
                {corpora.find((item) => item.id === register.corpus_id)?.name ??
                  "Selected corpus"}
              </h2>
              <p className="register-publication">
                Publication {register.publication_number}
                {register.is_current ? " · Current" : ""}
              </p>
              <p>
                Published {formatTimestamp(register.published_at)} after
                completed human review.
              </p>
            </div>
            <span className="register-status">
              {humanize(register.register_status)}
            </span>
          </div>

          <dl className="metadata-grid publication-metadata">
            <div>
              <dt>Register status</dt>
              <dd>{humanize(register.register_status)}</dd>
            </div>
            <div>
              <dt>Current</dt>
              <dd>{register.is_current ? "Yes" : "No"}</dd>
            </div>
            <div>
              <dt>Applied items</dt>
              <dd>{register.applied_count}</dd>
            </div>
            <div>
              <dt>Rejected items omitted</dt>
              <dd>{register.rejected_omitted_count}</dd>
            </div>
            <div>
              <dt>Publication status</dt>
              <dd>{humanize(register.status)}</dd>
            </div>
          </dl>
          {register.rejected_omitted_count > 0 && (
            <p className="review-banner review-banner--info">
              <strong>
                Rejected items are omitted from the applied register.
              </strong>{" "}
              {register.rejected_omitted_count} rejected rule
              {register.rejected_omitted_count === 1 ? " omitted" : "s omitted"}
              .
            </p>
          )}
          <details className="technical-details">
            <summary>Publication audit details</summary>
            <dl className="technical-grid">
              <div>
                <dt>Version identity</dt>
                <dd>
                  <code>{register.version_identity}</code>
                </dd>
              </div>
              <div>
                <dt>Publication ID</dt>
                <dd>
                  <code>{register.id}</code>
                </dd>
              </div>
              <div>
                <dt>Corpus ID</dt>
                <dd>
                  <code>{register.corpus_id}</code>
                </dd>
              </div>
              <div>
                <dt>Review session ID</dt>
                <dd>
                  <code>{register.review_session_id}</code>
                </dd>
              </div>
              <div>
                <dt>Omitted rule IDs</dt>
                <dd>
                  <code>
                    {register.omitted_rejected_rule_ids.join(", ") || "None"}
                  </code>
                </dd>
              </div>
            </dl>
          </details>

          <ul className="review-items" aria-label="Applied register items">
            {register.items.map((item) => (
              <li
                key={item.id}
                className={`review-item register-item review-item--${outcomeClass(
                  item.outcome,
                )}`}
              >
                <header className="finding-header">
                  <div>
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
                      <span className="review-state-chip">
                        {humanize(item.review_status)}
                      </span>
                      <span className="severity-chip">
                        {humanize(item.severity)} severity
                      </span>
                    </div>
                    <h3>{item.title}</h3>
                  </div>
                </header>
                <section
                  className="authorship-block authorship-block--system"
                  aria-label={`SYSTEM-GROUNDED ORIGINAL ${item.rule_id}`}
                >
                  <span className="authorship-label">
                    {item.reviewer_authored
                      ? "SYSTEM-GROUNDED ORIGINAL"
                      : "SYSTEM-GROUNDED"}
                  </span>
                  <p>{item.message}</p>
                  {(item.grounded_facts ?? []).length > 0 && (
                    <ul className="fact-list">
                      {item.grounded_facts.map((fact) => (
                        <li key={fact.id}>
                          <span>
                            {fact.category}/{fact.subject_key}:{" "}
                            {fact.normalized_value} ({fact.support_status})
                          </span>
                          <small>
                            {humanize(fact.category)} ·{" "}
                            {humanize(fact.subject_key)}
                          </small>
                        </li>
                      ))}
                    </ul>
                  )}

                  {(item.contradictions ?? []).length > 0 && (
                    <div className="contradiction-section">
                      <h4>Contradictory evidence retained</h4>
                      {item.contradictions.map((contradiction) => (
                        <div className="contradiction" key={contradiction.id}>
                          <p>{contradiction.reason}</p>
                          <div className="contradiction-sides">
                            {[contradiction.fact_a, contradiction.fact_b].map(
                              (fact, index) => (
                                <div key={fact.id}>
                                  <span>Evidence side {index + 1}</span>
                                  <strong>{fact.normalized_value}</strong>
                                  <small>{humanize(fact.subject_key)}</small>
                                </div>
                              ),
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}

                  {item.citations.length > 0 ? (
                    <div className="citation-list">
                      {item.citations.map((citation) => (
                        <blockquote
                          className="citation"
                          key={`${citation.native_locator}-${citation.exact_quote}`}
                        >
                          <p>{citation.exact_quote}</p>
                          <footer>
                            <strong>
                              {citation.source_logical_name ?? "Source"}
                            </strong>
                            <span>{citation.native_locator}</span>
                            <code>
                              {citation.source_version_id
                                ? `Source version ${citation.source_version_id} · `
                                : ""}
                              SHA-256 {citation.source_sha256}
                            </code>
                          </footer>
                        </blockquote>
                      ))}
                    </div>
                  ) : (
                    <p className="empty-evidence">
                      {item.outcome === "unknown"
                        ? "No grounded evidence is claimed for this UNKNOWN item."
                        : "No source quote is attached to this applied item."}
                    </p>
                  )}
                </section>
                {item.reviewer_authored_content && (
                  <section
                    className="authorship-block authorship-block--reviewer"
                    aria-label={`REVIEWER-AUTHORED OVERLAY ${item.rule_id}`}
                  >
                    <span className="authorship-label">
                      REVIEWER-AUTHORED OVERLAY
                    </span>
                    <strong>NOT SYSTEM-GROUNDED</strong>
                    <p>{item.reviewer_authored_content}</p>
                    <p>
                      {item.reviewer_authored_acknowledged
                        ? "Acknowledged reviewer-authored content; not system-grounded."
                        : "Reviewer-authored content; not system-grounded."}
                    </p>
                  </section>
                )}
                <details className="technical-details">
                  <summary>Item audit details</summary>
                  <dl className="technical-grid">
                    <div>
                      <dt>Rule ID</dt>
                      <dd>
                        <code>{item.rule_id}</code>
                      </dd>
                    </div>
                    <div>
                      <dt>Register item ID</dt>
                      <dd>
                        <code>{item.id}</code>
                      </dd>
                    </div>
                    <div>
                      <dt>Evidence kind</dt>
                      <dd>
                        <code>{item.evidence_kind}</code>
                      </dd>
                    </div>
                    <div>
                      <dt>Content origin</dt>
                      <dd>
                        <code>{item.content_origin}</code>
                      </dd>
                    </div>
                  </dl>
                </details>
              </li>
            ))}
          </ul>
          {register.items.length === 0 && (
            <div className="empty-state">
              <strong>No applied items</strong>
              <p>
                No approved or edited items were applied to this register. This
                does not imply a PASS.
              </p>
            </div>
          )}
        </div>
      )}
      {!register && !loading && !error && (
        <div className="empty-state">
          <strong>No current register</strong>
          <p>Complete review and explicitly publish an approved register.</p>
        </div>
      )}
    </div>
  );
}
