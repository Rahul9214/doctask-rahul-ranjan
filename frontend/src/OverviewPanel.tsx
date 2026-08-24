import { useMemo, useState } from "react";

import type { CorpusSummary, StatusState } from "./App";
import {
  corpusDisplayName,
  corpusMetaLabel,
  corpusPrimaryLabel,
  nameCounts,
  type SourceSummary,
} from "./corpus";
import { workflowStatusLabel, workflowStatusTone } from "./ui";
import type { Workspace } from "./workspace";

interface OverviewPanelProps {
  status: StatusState;
  corpora: CorpusSummary[];
  corporaLoading: boolean;
  sourcesByCorpus: Record<string, SourceSummary[]>;
  workspace: Workspace;
  onOpenWorkflow: () => void;
}

export default function OverviewPanel({
  corpora,
  corporaLoading,
  sourcesByCorpus,
  workspace,
  onOpenWorkflow,
}: OverviewPanelProps) {
  const [expandedSources, setExpandedSources] = useState<
    Record<string, boolean>
  >({});
  const [showAllCorpora, setShowAllCorpora] = useState(false);

  const documentCountFromSources = Object.values(sourcesByCorpus).reduce(
    (total, sources) => total + sources.length,
    0,
  );
  const loading =
    corporaLoading ||
    !corpora.every((corpus) =>
      Object.prototype.hasOwnProperty.call(sourcesByCorpus, corpus.id),
    );
  const selectedCorpus = corpora.find(
    (corpus) => corpus.id === workspace.corpusId,
  );
  const duplicates = nameCounts(corpora);
  const visibleCorpora = useMemo(() => {
    const list = selectedCorpus
      ? [
          selectedCorpus,
          ...corpora.filter((corpus) => corpus.id !== selectedCorpus.id),
        ]
      : corpora;
    return showAllCorpora ? list : list.slice(0, 6);
  }, [corpora, selectedCorpus, showAllCorpora]);

  return (
    <div className="page page--overview">
      <section className="overview-hero" aria-labelledby="overview-title">
        <p className="eyebrow">Evidence-led project assurance</p>
        <h1 id="overview-title">Project Assurance Register</h1>
        <p className="product-statement">
          The analyst that never sleeps — with a human at the gate.
        </p>
        <p className="supporting-copy">
          Evidence-led assurance across evolving project documents. The agent
          understands sources, examines them against configurable rules,
          surfaces contradictions, routes consequential decisions through human
          review, and publishes only approved grounded outcomes.
        </p>
      </section>

      <section
        className="kpi-grid"
        aria-label="Current assurance state"
        aria-busy={loading}
      >
        <article className="kpi-card">
          <span>Loaded corpora</span>
          {corporaLoading ? (
            <span className="skeleton skeleton--number" aria-label="Loading" />
          ) : (
            <strong>{corpora.length}</strong>
          )}
          <small>Available in this workspace</small>
        </article>
        <article className="kpi-card">
          <span>Source documents</span>
          {loading ? (
            <span className="skeleton skeleton--number" aria-label="Loading" />
          ) : (
            <strong>{documentCountFromSources}</strong>
          )}
          <small>Across loaded corpora</small>
        </article>
        <article className="kpi-card">
          <span>Current registers</span>
          <strong className="kpi-status">On demand</strong>
          <small>Open Register to inspect published output</small>
        </article>
        <article className="kpi-card">
          <span>Selected workflow</span>
          <strong className="kpi-status">
            {workspace.workflowStatus
              ? workflowStatusLabel(workspace.workflowStatus)
              : "None selected"}
          </strong>
          <small>
            {workspace.workflowStatus
              ? "Status of the open agent run"
              : "Open a corpus run to inspect status"}
          </small>
        </article>
      </section>

      <section className="overview-grid">
        <article className="current-workflow-card">
          <div className="card-heading">
            <div>
              <p className="section-kicker">Current workflow</p>
              <h2>
                {workspace.workflowStatus
                  ? workflowStatusLabel(workspace.workflowStatus)
                  : "No workflow selected"}
              </h2>
            </div>
            <span
              className={`status-chip status-chip--${workflowStatusTone(
                workspace.workflowStatus,
              )}`}
            >
              {workspace.workflowStatus
                ? workflowStatusLabel(workspace.workflowStatus)
                : "Not loaded"}
            </span>
          </div>
          <p>
            {workspace.workflowStatus
              ? "Inspect the durable agent run, complete human review when required, then publish explicitly."
              : "Select a corpus and run to inspect agent execution."}
          </p>
          <ol className="mini-stage-track" aria-label="Agent workflow stages">
            {["Understand", "Examine", "Human Gate", "Finalize"].map(
              (stage, index) => (
                <li key={stage}>
                  <span aria-hidden="true">{index + 1}</span>
                  {stage}
                </li>
              ),
            )}
          </ol>
          <p className="helper-text">
            Workflow completion does not publish. Publication remains an
            explicit action.
          </p>
          <button
            className="button button--primary"
            type="button"
            onClick={onOpenWorkflow}
          >
            Open workflow
          </button>
        </article>

        <article className="assurance-principles">
          <p className="section-kicker">Control boundary</p>
          <h2>Human control is structural</h2>
          <ul>
            <li>
              <span className="principle-icon principle-icon--evidence">E</span>
              <div>
                <strong>Grounded evidence</strong>
                <small>Source-attributed claims</small>
              </div>
            </li>
            <li>
              <span className="principle-icon principle-icon--human">H</span>
              <div>
                <strong>Human approval required</strong>
                <small>No automatic decisions</small>
              </div>
            </li>
            <li>
              <span className="principle-icon principle-icon--publish">P</span>
              <div>
                <strong>Explicit publication</strong>
                <small>Workflow complete ≠ published</small>
              </div>
            </li>
            <li>
              <span className="principle-icon principle-icon--mcp">M</span>
              <div>
                <strong>MCP available</strong>
                <small>Machine operations available</small>
              </div>
            </li>
          </ul>
        </article>
      </section>

      <section
        className="corpus-source-summary"
        aria-labelledby="corpus-summary-title"
      >
        <div className="card-heading">
          <div>
            <p className="section-kicker">Document pile</p>
            <h2 id="corpus-summary-title">Corpora and source documents</h2>
          </div>
        </div>
        {corporaLoading ? (
          <div className="skeleton-grid" aria-label="Loading corpora">
            <span className="skeleton skeleton--card" />
            <span className="skeleton skeleton--card" />
          </div>
        ) : corpora.length === 0 ? (
          <p className="empty-state empty-state--compact">
            No corpora are loaded yet.
          </p>
        ) : (
          <>
            <ul className="corpus-row-list">
              {visibleCorpora.map((corpus) => {
                const sources = sourcesByCorpus[corpus.id] ?? [];
                const namedSources = sources.filter((source) =>
                  Boolean(source.logical_name),
                );
                const duplicate =
                  (duplicates.get(corpusDisplayName(corpus)) ?? 0) > 1;
                const preview = namedSources.slice(0, 4);
                const expanded = Boolean(expandedSources[corpus.id]);
                return (
                  <li key={corpus.id} className="corpus-row">
                    <div>
                      <h3 title={corpus.id}>
                        {corpusPrimaryLabel(corpus, duplicate)}
                      </h3>
                      <p>
                        {corpusMetaLabel(corpus, sources) || "No documents"}
                      </p>
                      {preview.length > 0 && (
                        <p className="corpus-row__preview">
                          {preview
                            .map((source) => source.logical_name)
                            .join(" · ")}
                          {namedSources.length > 4
                            ? ` · +${namedSources.length - 4}`
                            : ""}
                        </p>
                      )}
                    </div>
                    {namedSources.length > 0 && (
                      <button
                        className="button button--quiet"
                        type="button"
                        aria-expanded={expanded}
                        onClick={() =>
                          setExpandedSources((current) => ({
                            ...current,
                            [corpus.id]: !current[corpus.id],
                          }))
                        }
                      >
                        {expanded ? "Hide sources" : "View sources"}
                      </button>
                    )}
                    {expanded && (
                      <ul className="corpus-row__sources">
                        {namedSources.map((source) => (
                          <li key={source.id}>{source.logical_name}</li>
                        ))}
                      </ul>
                    )}
                  </li>
                );
              })}
            </ul>
            {corpora.length > 6 && (
              <button
                className="button button--quiet"
                type="button"
                onClick={() => setShowAllCorpora((current) => !current)}
              >
                {showAllCorpora ? "Show fewer" : "View all corpora"}
              </button>
            )}
          </>
        )}
      </section>
    </div>
  );
}
