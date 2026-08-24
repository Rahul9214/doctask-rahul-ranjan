import type { CorpusSummary, StatusState } from "./App";
import type { SourceSummary } from "./corpus";
import IncrementalPanel from "./IncrementalPanel";
import { MCP_TOOL_COUNT, MCP_TOOL_GROUPS } from "./mcpTools";

function checkStatus(status: StatusState, check: string): string {
  if (status.kind === "loading") {
    return "Checking";
  }
  const reported = status.checks?.[check]?.status;
  if (!reported) {
    return "Not reported";
  }
  return reported === "ready" ? "Ready" : "Unavailable";
}

function apiStatus(status: StatusState): string {
  if (status.kind === "loading") {
    return "Checking";
  }
  if (status.kind === "ready") {
    return "Ready";
  }
  if (status.applicationAlive) {
    return "Ready";
  }
  return "Unavailable";
}

function reportedVersion(status: StatusState): string {
  if (status.kind === "loading") {
    return "Checking";
  }
  const version =
    status.kind === "ready" || status.kind === "unavailable"
      ? status.version?.app_version
      : undefined;
  return version?.trim() ? version : "Unavailable";
}

function pgvectorDetail(status: StatusState): string {
  if (status.kind !== "ready" && status.kind !== "unavailable") {
    return "Grounded retrieval";
  }
  const version = status.checks?.pgvector?.version;
  return version ? `Version ${version}` : "Not reported";
}

function McpOperations() {
  return (
    <>
      <details className="tool-list">
        <summary>View {MCP_TOOL_COUNT} operations</summary>
        <div className="tool-groups">
          {MCP_TOOL_GROUPS.map((group) => (
            <section key={group.label}>
              <h3>
                {group.label}{" "}
                <span className="tool-count">{group.tools.length}</span>
              </h3>
              <ul>
                {group.tools.map((tool) => (
                  <li key={tool}>
                    <code>{tool}</code>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      </details>
      <details className="audit-details">
        <summary>Operation bounds</summary>
        <p className="helper-text">
          Only the application’s bounded assurance operations are exposed.
          Arbitrary shell and file execution are unavailable.
        </p>
      </details>
    </>
  );
}

export default function SystemPanel({
  status,
  corpora,
  sourcesByCorpus = {},
  focusMcp = false,
  onOpenMcp,
}: {
  status: StatusState;
  corpora: CorpusSummary[];
  corporaLoading: boolean;
  sourcesByCorpus?: Record<string, SourceSummary[]>;
  focusMcp?: boolean;
  onOpenMcp?: () => void;
}) {
  if (focusMcp) {
    return (
      <div className="page page--mcp">
        <header className="page-header">
          <div>
            <p className="eyebrow">Machine interface</p>
            <h1>MCP</h1>
            <p>
              Machine clients can drive the same bounded workflow, review, and
              publication operations.
            </p>
          </div>
        </header>

        <section
          className="machine-interface"
          aria-labelledby="mcp-facts-title"
        >
          <h2 id="mcp-facts-title" className="visually-hidden">
            Interface facts
          </h2>
          <dl className="machine-facts">
            <div>
              <dt>Transport</dt>
              <dd>Standard input/output (stdio)</dd>
            </div>
            <div>
              <dt>Operations</dt>
              <dd>{MCP_TOOL_COUNT}</dd>
            </div>
            <div>
              <dt>Human decisions</dt>
              <dd>Explicit</dd>
            </div>
            <div>
              <dt>Auto approval</dt>
              <dd>Disabled</dd>
            </div>
            <div>
              <dt>Auto publish</dt>
              <dd>Disabled</dd>
            </div>
          </dl>
          <McpOperations />
        </section>
      </div>
    );
  }

  return (
    <div className="page page--system">
      <header className="page-header">
        <div>
          <p className="eyebrow">Runtime and machine operation</p>
          <h1>System</h1>
          <p>
            Runtime health, machine interface, ruleset, and incremental-update
            status.
          </p>
        </div>
      </header>

      {status.kind === "unavailable" && (
        <div className="review-banner review-banner--error" role="alert">
          <strong>Dependency unavailable</strong>
          <p>{status.message}</p>
          {status.action && <p>Next action: {status.action}</p>}
        </div>
      )}

      <section className="system-grid" aria-label="System components">
        <article>
          <span>Application</span>
          {/* Source: GET /api/version app_version */}
          <strong>{reportedVersion(status)}</strong>
          <small>Project Assurance Register</small>
        </article>
        <article>
          <span>API</span>
          {/* Source: GET /api/health via loadStatus applicationAlive */}
          <strong>{apiStatus(status)}</strong>
          <small>Business service</small>
        </article>
        <article>
          <span>PostgreSQL</span>
          {/* Source: GET /api/ready checks.database.status */}
          <strong>{checkStatus(status, "database")}</strong>
          <small>Durable persistence</small>
        </article>
        <article>
          <span>pgvector</span>
          {/* Source: GET /api/ready checks.pgvector.status|version */}
          <strong>{checkStatus(status, "pgvector")}</strong>
          <small>{pgvectorDetail(status)}</small>
        </article>
        <article className="system-card--muted">
          <span>Ruleset</span>
          {/* No ruleset endpoint is exposed to the frontend. */}
          <strong>Not reported</strong>
        </article>
        <article className="system-card--muted">
          <span>Environment</span>
          {/* No environment-name field is exposed to the frontend. */}
          <strong>Not reported</strong>
        </article>
      </section>

      <section className="mcp-summary-card" aria-labelledby="mcp-summary-title">
        <div className="card-heading">
          <div>
            <p className="section-kicker">Machine interface</p>
            <h2 id="mcp-summary-title">MCP</h2>
            <p>
              The same bounded assurance operations are available to machine
              clients.
            </p>
          </div>
        </div>
        <dl className="mcp-summary-facts">
          <div>
            <dt>Operations</dt>
            <dd>{MCP_TOOL_COUNT}</dd>
          </div>
          <div>
            <dt>Human decisions</dt>
            <dd>Explicit</dd>
          </div>
          <div>
            <dt>Auto approval</dt>
            <dd>Disabled</dd>
          </div>
          <div>
            <dt>Auto publish</dt>
            <dd>Disabled</dd>
          </div>
        </dl>
        <button
          className="button button--quiet"
          type="button"
          onClick={onOpenMcp}
        >
          Open machine interface
        </button>
      </section>

      <IncrementalPanel corpora={corpora} sourcesByCorpus={sourcesByCorpus} />
    </div>
  );
}
