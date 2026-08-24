export function humanize(value: string | null | undefined): string {
  if (!value) {
    return "Not available";
  }
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

export function formatTimestamp(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : new Intl.DateTimeFormat(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(date);
}

export function formatCompactTimestamp(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : new Intl.DateTimeFormat(undefined, {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      }).format(date);
}

export function formatDuration(durationMs: number | null): string {
  if (durationMs === null) {
    return "Not recorded";
  }
  if (durationMs < 1_000) {
    return `${durationMs} ms`;
  }
  return `${(durationMs / 1_000).toFixed(2)} s`;
}

export function outcomeClass(value: string): string {
  const normalized = value.toLowerCase();
  return ["pass", "fail", "warning", "unknown"].includes(normalized)
    ? normalized
    : "neutral";
}

const WORKFLOW_STATUS_LABELS: Record<string, string> = {
  pending: "Queued",
  queued: "Queued",
  running: "Running",
  completed: "Completed",
  waiting_for_review: "Waiting for human review",
  failed: "Failed",
  resumed: "Resumed",
};

const STAGE_LABELS: Record<string, string> = {
  understand: "Understand",
  examine: "Examine",
  "human-gate": "Human Gate",
  human_gate: "Human Gate",
  wait_for_review: "Human Gate",
  finalize: "Finalize",
};

export function workflowStatusLabel(value: string | null | undefined): string {
  if (!value) {
    return "Not available";
  }
  return WORKFLOW_STATUS_LABELS[value] ?? humanize(value);
}

export function stageLabel(value: string | null | undefined): string {
  if (!value) {
    return "Not available";
  }
  return STAGE_LABELS[value] ?? humanize(value);
}

export function workflowStatusTone(value: string | null | undefined): string {
  if (value === "completed") {
    return "pass";
  }
  if (value === "failed") {
    return "fail";
  }
  if (value === "waiting_for_review") {
    return "warning";
  }
  return "neutral";
}

const EVENT_LABELS: Record<string, string> = {
  workflow_started: "Workflow started",
  stage_completed: "Stage completed",
  waiting_for_review: "Waiting for human review",
  checkpoint_recorded: "Checkpoint recorded",
  workflow_resumed: "Workflow resumed",
  workflow_completed: "Workflow completed",
  workflow_failed: "Workflow failed",
};

export type HealthTone =
  "loading" | "ready" | "partial" | "unavailable" | "unknown";

export function healthPresentation(status: {
  kind: "loading" | "ready" | "unavailable";
  applicationAlive?: boolean;
  checks?: Record<string, { status?: string }>;
}): { tone: HealthTone; label: string } {
  if (status.kind === "loading") {
    return { tone: "loading", label: "Checking" };
  }
  if (status.kind === "ready") {
    const reported = Object.values(status.checks ?? {}).filter((check) =>
      Boolean(check.status),
    );
    if (
      reported.length > 0 &&
      reported.some((check) => check.status !== "ready")
    ) {
      return { tone: "partial", label: "System partially ready" };
    }
    return { tone: "ready", label: "System ready" };
  }
  if (!status.applicationAlive) {
    return { tone: "unknown", label: "System status unavailable" };
  }
  return { tone: "unavailable", label: "System not ready" };
}

export function eventLabel(value: string | null | undefined): string {
  if (!value) {
    return "Not available";
  }
  if (EVENT_LABELS[value]) {
    return EVENT_LABELS[value];
  }
  if (value.startsWith("checkpoint_")) {
    return "Checkpoint recorded";
  }
  return humanize(value);
}
