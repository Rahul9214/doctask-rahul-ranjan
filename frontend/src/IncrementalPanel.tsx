import { useState, type FormEvent } from "react";

import type { CorpusSummary } from "./App";
import CorpusSelect from "./CorpusSelect";
import { requestJson, type ApiError } from "./api";
import type { SourceSummary } from "./corpus";
import { formatDuration, humanize } from "./ui";

interface IncrementalEvidence {
  run_id: string;
  status: string;
  change_kind: string;
  evidence: Record<string, unknown>;
  measurement: Record<string, unknown>;
  artifacts: Array<Record<string, unknown>>;
}

const incrementalErrorCopy = {
  detail: "The incremental evidence request failed.",
  action: "Check the technical identifiers and retry.",
};

function numericValue(
  record: Record<string, unknown>,
  key: string,
): number | null {
  return typeof record[key] === "number" ? record[key] : null;
}

function listLength(
  record: Record<string, unknown>,
  key: string,
): number | null {
  return Array.isArray(record[key]) ? record[key].length : null;
}

export default function IncrementalPanel({
  corpora,
  sourcesByCorpus = {},
}: {
  corpora: CorpusSummary[];
  sourcesByCorpus?: Record<string, SourceSummary[]>;
}) {
  const [corpusId, setCorpusId] = useState("");
  const [runId, setRunId] = useState("");
  const [result, setResult] = useState<IncrementalEvidence | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  async function loadEvidence(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setResult(null);
    setError(null);
    setLoading(true);
    try {
      setResult(
        await requestJson<IncrementalEvidence>(
          `/api/corpora/${corpusId}/incremental-runs/${runId}/evidence`,
          incrementalErrorCopy,
        ),
      );
    } catch (caught) {
      setError(caught as ApiError);
    } finally {
      setLoading(false);
    }
  }

  const measurements = result?.measurement ?? {};
  const evidence = result?.evidence ?? {};
  const changedSources = numericValue(measurements, "changed_source_count");
  const unchangedSources = listLength(
    evidence,
    "classify_skipped_source_version_ids",
  );
  const factsRecomputed = numericValue(measurements, "affected_fact_count");
  const factsReused = numericValue(measurements, "reused_fact_count");
  const contradictionsRecomputed = numericValue(
    measurements,
    "affected_contradiction_count",
  );
  const modelOperations = numericValue(
    measurements,
    "incremental_understand_model_operations",
  );
  const operationsAvoided = numericValue(
    measurements,
    "avoided_model_operations",
  );
  const duration = numericValue(measurements, "duration_ms");
  const fullRerun =
    typeof evidence.full_rerun === "boolean" ? evidence.full_rerun : null;

  return (
    <section className="incremental-card" aria-labelledby="incremental-title">
      <div className="card-heading">
        <div>
          <p className="section-kicker">Focused processing</p>
          <h2 id="incremental-title">Incremental update evidence</h2>
          <p>Focused updates reuse unaffected work.</p>
        </div>
        {result && (
          <span className="status-chip status-chip--pass">
            {humanize(result.status)}
          </span>
        )}
      </div>

      <details className="technical-lookup">
        <summary>Technical lookup</summary>
        <form
          className="form-grid form-grid--stacked"
          onSubmit={(event) => void loadEvidence(event)}
        >
          <div className="field">
            <label htmlFor="incremental-corpus-id">Corpus</label>
            <CorpusSelect
              id="incremental-corpus-id"
              corpora={corpora}
              sourcesByCorpus={sourcesByCorpus}
              value={corpusId}
              onChange={setCorpusId}
              disabled={loading}
            />
          </div>
          <div className="field">
            <label htmlFor="incremental-run-id">Incremental run ID</label>
            <input
              id="incremental-run-id"
              value={runId}
              onChange={(event) => setRunId(event.target.value)}
              required
              disabled={loading}
              autoComplete="off"
            />
          </div>
          <button
            className="button button--secondary"
            type="submit"
            disabled={loading}
          >
            {loading ? "Loading evidence…" : "Load update evidence"}
          </button>
        </form>
      </details>

      {error && (
        <div className="review-banner review-banner--error" role="alert">
          <p>{error.detail}</p>
          {error.action && <p>Next action: {error.action}</p>}
        </div>
      )}

      {loading && (
        <div
          className="skeleton-grid"
          aria-label="Loading incremental evidence"
        >
          {Array.from({ length: 4 }).map((_, index) => (
            <span className="skeleton skeleton--card" key={index} />
          ))}
        </div>
      )}

      {result && (
        <>
          <div className="incremental-heading">
            <div>
              <strong>{humanize(result.change_kind)}</strong>
              <span>
                {duration === null
                  ? "Duration not recorded"
                  : formatDuration(duration)}
              </span>
            </div>
            <code>{result.run_id}</code>
          </div>
          <dl className="metric-grid metric-grid--incremental">
            <div>
              <dt>Changed sources</dt>
              <dd>{changedSources ?? "—"}</dd>
            </div>
            <div>
              <dt>Unchanged sources skipped</dt>
              <dd>{unchangedSources ?? "—"}</dd>
            </div>
            <div>
              <dt>Facts recomputed</dt>
              <dd>{factsRecomputed ?? "—"}</dd>
            </div>
            <div>
              <dt>Facts reused</dt>
              <dd>{factsReused ?? "—"}</dd>
            </div>
            <div>
              <dt>Contradictions recomputed</dt>
              <dd>{contradictionsRecomputed ?? "—"}</dd>
            </div>
            <div>
              <dt>Full rerun</dt>
              <dd>{fullRerun === null ? "—" : fullRerun ? "Yes" : "No"}</dd>
            </div>
            <div>
              <dt>Model operations executed</dt>
              <dd>{modelOperations ?? "—"}</dd>
            </div>
            <div>
              <dt>Operations avoided</dt>
              <dd>{operationsAvoided ?? "—"}</dd>
            </div>
          </dl>
          <details className="audit-details">
            <summary>
              View impact evidence ({result.artifacts.length} artifacts)
            </summary>
            <dl className="technical-grid">
              {Object.entries(evidence).map(([key, value]) => (
                <div key={key}>
                  <dt>{humanize(key)}</dt>
                  <dd>
                    <code>
                      {typeof value === "string"
                        ? value
                        : JSON.stringify(value)}
                    </code>
                  </dd>
                </div>
              ))}
            </dl>
          </details>
        </>
      )}

      {!result && !loading && !error && (
        <div className="empty-state empty-state--compact">
          <strong>No incremental update</strong>
          <p>No focused update has been recorded for this corpus.</p>
        </div>
      )}
    </section>
  );
}
