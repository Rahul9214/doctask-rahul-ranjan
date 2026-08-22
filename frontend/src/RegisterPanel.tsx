import { useState, type FormEvent } from "react";

interface ApiError {
  code: string;
  detail: string;
  action?: string;
}

interface RegisterCitation {
  source_logical_name: string | null;
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

interface RegisterItem {
  id: string;
  rule_id: string;
  rule_version: string;
  title: string;
  outcome: string;
  severity: string;
  message: string;
  review_status: string;
  content_origin: string;
  system_grounded: boolean;
  reviewer_authored: boolean;
  reviewer_authored_content: string | null;
  reviewer_authored_acknowledged: boolean;
  grounded_facts: RegisterFact[];
  citations: RegisterCitation[];
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
  completion_allowed: boolean;
}

async function readError(response: Response): Promise<ApiError> {
  try {
    const body = (await response.json()) as ApiError;
    return {
      code: body.code || "request_failed",
      detail: body.detail || "The register request failed.",
      action: body.action,
    };
  } catch {
    return {
      code: "request_failed",
      detail: "The register request failed.",
      action: "Retry the register operation.",
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

export default function RegisterPanel() {
  const [corpusId, setCorpusId] = useState("");
  const [reviewSessionId, setReviewSessionId] = useState("");
  const [review, setReview] = useState<ReviewSession | null>(null);
  const [register, setRegister] = useState<PublishedRegister | null>(null);
  const [loading, setLoading] = useState(false);
  const [pendingAction, setPendingAction] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  const busy = loading || pendingAction !== null;
  const canPublish = review?.status === "completed";

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
          ),
        );
      }
      try {
        setRegister(
          await requestJson<PublishedRegister>(
            `/api/corpora/${corpusId}/register`,
          ),
        );
      } catch (caught) {
        const apiError = caught as ApiError;
        if (apiError.code !== "publication_not_found") {
          throw caught;
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
        {
          method: "POST",
          body: JSON.stringify({
            actor: "reviewer",
            publication_source: "ui",
          }),
        },
      );
      setRegister(published);
      setReview(
        await requestJson<ReviewSession>(
          `/api/corpora/${corpusId}/review-sessions/${reviewSessionId}`,
        ),
      );
    } catch (caught) {
      setError(caught as ApiError);
    } finally {
      setPendingAction(null);
    }
  }

  return (
    <section className="register-panel" aria-labelledby="register-title">
      <h2 id="register-title">Published register</h2>
      <p>
        Publication is an explicit action after completed review. Workflow
        completion is not publication. Approved and edited items are applied;
        rejected items are omitted.
      </p>
      <form
        className="review-open"
        onSubmit={(event) => void loadRegister(event)}
      >
        <label htmlFor="register-corpus-id">Register corpus ID</label>
        <input
          id="register-corpus-id"
          value={corpusId}
          onChange={(event) => setCorpusId(event.target.value)}
          required
          disabled={busy}
        />
        <label htmlFor="register-session-id">Review session ID</label>
        <input
          id="register-session-id"
          value={reviewSessionId}
          onChange={(event) => setReviewSessionId(event.target.value)}
          disabled={busy}
        />
        <button type="submit" disabled={busy}>
          {loading ? "Loading register…" : "Load register"}
        </button>
      </form>
      {error && (
        <div className="review-banner review-banner--error" role="alert">
          <p>{error.detail}</p>
          {error.action && <p>Next action: {error.action}</p>}
        </div>
      )}
      {review && (
        <p>
          Review status: {review.status}.{" "}
          {review.status === "completed"
            ? "The session is ready for explicit publication."
            : "Complete required decisions before publishing."}
        </p>
      )}
      {canPublish && (
        <button
          type="button"
          onClick={() => void publishRegister()}
          disabled={busy}
        >
          Publish register
        </button>
      )}
      {register && (
        <div className="workflow-summary">
          <dl className="version-grid">
            <div>
              <dt>Publication</dt>
              <dd>{register.version_identity}</dd>
            </div>
            <div>
              <dt>Register status</dt>
              <dd>{register.register_status}</dd>
            </div>
            <div>
              <dt>Current</dt>
              <dd>{register.is_current ? "yes" : "no"}</dd>
            </div>
            <div>
              <dt>Applied / omitted rejected</dt>
              <dd>
                {register.applied_count} / {register.rejected_omitted_count}
              </dd>
            </div>
          </dl>
          <ul className="review-items">
            {register.items.map((item) => (
              <li key={item.id} className="review-item">
                <h3>{item.title}</h3>
                <p>
                  {item.rule_id} · {item.outcome} · {item.review_status}
                </p>
                <section
                  aria-label={`SYSTEM-GROUNDED ORIGINAL ${item.rule_id}`}
                >
                  <h4>
                    {item.reviewer_authored
                      ? "SYSTEM-GROUNDED ORIGINAL"
                      : "SYSTEM-GROUNDED"}
                  </h4>
                  <p>{item.message}</p>
                  {item.grounded_facts.length > 0 && (
                    <ul>
                      {item.grounded_facts.map((fact) => (
                        <li key={fact.id}>
                          {fact.category}/{fact.subject_key}:{" "}
                          {fact.normalized_value} ({fact.support_status})
                        </li>
                      ))}
                    </ul>
                  )}
                  {item.citations.map((citation) => (
                    <blockquote
                      key={`${citation.native_locator}-${citation.exact_quote}`}
                    >
                      <p>{citation.exact_quote}</p>
                      <footer>
                        {citation.source_logical_name ?? "source"} ·{" "}
                        {citation.native_locator}
                      </footer>
                    </blockquote>
                  ))}
                </section>
                {item.reviewer_authored_content && (
                  <section
                    aria-label={`REVIEWER-AUTHORED EDIT ${item.rule_id}`}
                  >
                    <h4>REVIEWER-AUTHORED EDIT</h4>
                    <p>{item.reviewer_authored_content}</p>
                    <p>
                      {item.reviewer_authored_acknowledged
                        ? "Acknowledged reviewer-authored content; not system-grounded."
                        : "Reviewer-authored content; not system-grounded."}
                    </p>
                  </section>
                )}
              </li>
            ))}
          </ul>
          {register.items.length === 0 && (
            <p>No approved or edited items were applied to this register.</p>
          )}
        </div>
      )}
    </section>
  );
}
