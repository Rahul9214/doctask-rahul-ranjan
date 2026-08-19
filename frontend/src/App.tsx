import { useEffect, useState } from "react";

import ReviewPanel from "./ReviewPanel";

interface VersionInfo {
  app_version: string;
  current_phase: string;
  implementation_status: string;
}

interface ReadinessFailure {
  checks?: Record<string, { detail?: string; action?: string }>;
}

type StatusState =
  | { kind: "loading" }
  | { kind: "ready"; version: VersionInfo }
  | {
      kind: "unavailable";
      applicationAlive: boolean;
      message: string;
      action?: string;
      version?: VersionInfo;
    };

async function loadStatus(): Promise<StatusState> {
  try {
    const [healthResponse, readinessResponse, versionResponse] =
      await Promise.all([
        fetch("/api/health"),
        fetch("/api/ready"),
        fetch("/api/version"),
      ]);

    if (!healthResponse.ok || !versionResponse.ok) {
      throw new Error("The backend application is unavailable.");
    }

    const version = (await versionResponse.json()) as VersionInfo;

    if (!readinessResponse.ok) {
      const failure = (await readinessResponse.json()) as ReadinessFailure;
      const databaseFailure = failure.checks?.database;
      const vectorFailure = failure.checks?.pgvector;
      return {
        kind: "unavailable",
        applicationAlive: true,
        message:
          databaseFailure?.detail ??
          vectorFailure?.detail ??
          "A required backend dependency is unavailable.",
        action: databaseFailure?.action ?? vectorFailure?.action,
        version,
      };
    }

    return { kind: "ready", version };
  } catch {
    return {
      kind: "unavailable",
      applicationAlive: false,
      message: "The backend application could not be reached.",
      action: "Start the backend and retry.",
    };
  }
}

function VersionDetails({ version }: { version: VersionInfo }) {
  return (
    <dl className="version-grid">
      <div>
        <dt>Application version</dt>
        <dd>{version.app_version}</dd>
      </div>
      <div>
        <dt>Current phase</dt>
        <dd>{version.current_phase}</dd>
      </div>
    </dl>
  );
}

export default function App() {
  const [status, setStatus] = useState<StatusState>({ kind: "loading" });

  useEffect(() => {
    let active = true;

    void loadStatus().then((result) => {
      if (active) {
        setStatus(result);
      }
    });

    return () => {
      active = false;
    };
  }, []);

  return (
    <main className="shell">
      <section className="panel" aria-labelledby="page-title">
        <p className="eyebrow">Human review</p>
        <h1 id="page-title">Project Assurance Register</h1>
        <p className="scope-message">
          Understand, Examine, and item-level human review are implemented.
          Register publication, durable resume, MCP, and watching are not.
        </p>

        <div className="status-card" aria-live="polite">
          {status.kind === "loading" && (
            <>
              <span
                className="status-dot status-dot--loading"
                aria-hidden="true"
              />
              <div>
                <h2>Checking backend status</h2>
                <p>Waiting for liveness and dependency checks.</p>
              </div>
            </>
          )}

          {status.kind === "ready" && (
            <>
              <span
                className="status-dot status-dot--ready"
                aria-hidden="true"
              />
              <div>
                <h2>Foundation ready</h2>
                <p>The backend, PostgreSQL, and pgvector are available.</p>
                <VersionDetails version={status.version} />
              </div>
            </>
          )}

          {status.kind === "unavailable" && (
            <>
              <span
                className="status-dot status-dot--error"
                aria-hidden="true"
              />
              <div>
                <h2>Dependency unavailable</h2>
                <p>
                  Application liveness:{" "}
                  {status.applicationAlive ? "alive" : "unavailable"}
                </p>
                <p>{status.message}</p>
                {status.action && (
                  <p className="action">Next action: {status.action}</p>
                )}
                {status.version && <VersionDetails version={status.version} />}
              </div>
            </>
          )}
        </div>

        {status.kind === "ready" && <ReviewPanel />}
      </section>
    </main>
  );
}
