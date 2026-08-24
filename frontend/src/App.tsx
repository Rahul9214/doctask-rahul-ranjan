import { useEffect, useRef, useState } from "react";

import OverviewPanel from "./OverviewPanel";
import RegisterPanel from "./RegisterPanel";
import ReviewPanel from "./ReviewPanel";
import SystemPanel from "./SystemPanel";
import WorkflowStatusPanel from "./WorkflowStatusPanel";
import { asSourceList, type SourceSummary } from "./corpus";
import type { CorpusSummary } from "./types";
import { healthPresentation } from "./ui";
import { emptyWorkspace, type Workspace } from "./workspace";

export type { CorpusSummary } from "./types";

export interface VersionInfo {
  app_version: string;
  current_phase: string;
  implementation_status: string;
}

interface ReadinessPayload {
  checks?: Record<
    string,
    { status?: string; detail?: string; action?: string; version?: string }
  >;
}

export type StatusState =
  | { kind: "loading" }
  | {
      kind: "ready";
      version: VersionInfo;
      checks: ReadinessPayload["checks"];
    }
  | {
      kind: "unavailable";
      applicationAlive: boolean;
      message: string;
      action?: string;
      version?: VersionInfo;
      checks?: ReadinessPayload["checks"];
    };

export type Section =
  "overview" | "agent-run" | "human-review" | "register" | "system" | "mcp";

type NavIcon = "overview" | "run" | "review" | "register" | "system" | "mcp";

const navigation: Array<{
  id: Section;
  label: string;
  icon: NavIcon;
}> = [
  { id: "overview", label: "Overview", icon: "overview" },
  { id: "agent-run", label: "Agent Run", icon: "run" },
  { id: "human-review", label: "Human Review", icon: "review" },
  { id: "register", label: "Register", icon: "register" },
  { id: "system", label: "System", icon: "system" },
];

const mobileNavigation: Array<{
  id: Section;
  label: string;
  icon: NavIcon;
}> = [...navigation, { id: "mcp", label: "MCP", icon: "mcp" }];

const SIDEBAR_STORAGE_KEY = "par.sidebar-collapsed";

function sectionFromHash(): Section {
  const candidate = window.location.hash.slice(1);
  if (candidate === "mcp") {
    return "mcp";
  }
  return navigation.some((item) => item.id === candidate)
    ? (candidate as Section)
    : "overview";
}

function readSidebarCollapsed(): boolean {
  try {
    return window.localStorage.getItem(SIDEBAR_STORAGE_KEY) === "true";
  } catch {
    return false;
  }
}

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
    const readiness = (await readinessResponse.json()) as ReadinessPayload;

    if (!readinessResponse.ok) {
      const databaseFailure = readiness.checks?.database;
      const vectorFailure = readiness.checks?.pgvector;
      return {
        kind: "unavailable",
        applicationAlive: true,
        message:
          databaseFailure?.detail ??
          vectorFailure?.detail ??
          "A required backend dependency is unavailable.",
        action: databaseFailure?.action ?? vectorFailure?.action,
        version,
        checks: readiness.checks,
      };
    }

    return { kind: "ready", version, checks: readiness.checks };
  } catch {
    return {
      kind: "unavailable",
      applicationAlive: false,
      message: "The backend application could not be reached.",
      action: "Start the backend and retry.",
    };
  }
}

export function ProductIcon({
  name,
}: {
  name:
    | "overview"
    | "run"
    | "review"
    | "register"
    | "system"
    | "collapse"
    | "expand"
    | "mcp"
    | "menu"
    | "close";
}) {
  const paths = {
    overview: (
      <>
        <rect x="3.5" y="3.5" width="7" height="7" rx="1.2" />
        <rect x="13.5" y="3.5" width="7" height="7" rx="1.2" />
        <rect x="3.5" y="13.5" width="7" height="7" rx="1.2" />
        <rect x="13.5" y="13.5" width="7" height="7" rx="1.2" />
      </>
    ),
    run: (
      <>
        <circle cx="5" cy="12" r="2.2" />
        <circle cx="12" cy="5.5" r="2.2" />
        <circle cx="19" cy="12" r="2.2" />
        <circle cx="12" cy="18.5" r="2.2" />
        <path d="M7.1 10.7 10.1 7.5M13.9 7.5 16.9 10.7M16.9 13.3 13.9 16.5M10.1 16.5 7.1 13.3" />
      </>
    ),
    review: (
      <>
        <circle cx="9" cy="7.8" r="2.5" />
        <path d="M4.8 17.2c.7-2.4 2.2-3.6 4.2-3.6s3.5 1.2 4.2 3.6" />
        <path d="m14.2 11.2 2.1 2.1 4.1-4.3" />
      </>
    ),
    register: (
      <>
        <path d="M6.5 4h11.2a1 1 0 0 1 1 1v14.2a1 1 0 0 1-1 1H6.5A1.8 1.8 0 0 1 4.7 18.4V5.8A1.8 1.8 0 0 1 6.5 4z" />
        <path d="M7.4 4.2v16.2" />
        <path d="M10.4 8.4h5.4M10.4 12h5.4M10.4 15.6h3.6" />
      </>
    ),
    system: (
      <>
        <circle cx="12" cy="12" r="3.1" />
        <path d="M12 3.2v2.4M12 18.4v2.4M4.7 6.2l1.7 1.7M17.6 16.1l1.7 1.7M3.2 12h2.4M18.4 12h2.4M4.7 17.8l1.7-1.7M17.6 7.9l1.7-1.7" />
      </>
    ),
    collapse: <path d="m14.2 6.2-5.8 5.8 5.8 5.8" />,
    expand: <path d="m9.8 6.2 5.8 5.8-5.8 5.8" />,
    mcp: (
      <>
        <rect x="2.8" y="7.6" width="6" height="8.8" rx="1.1" />
        <rect x="15.2" y="7.6" width="6" height="8.8" rx="1.1" />
        <circle cx="12" cy="10.2" r="1.25" />
        <circle cx="12" cy="13.8" r="1.25" />
        <path d="M8.8 10.2H10.7M8.8 13.8H10.7M13.3 10.2H15.2M13.3 13.8H15.2" />
      </>
    ),
    menu: <path d="M4 7h16M4 12h16M4 17h16" />,
    close: <path d="m6 6 12 12M18 6 6 18" />,
  };
  return (
    <svg
      className="product-icon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name]}
    </svg>
  );
}

export default function App() {
  const [status, setStatus] = useState<StatusState>({ kind: "loading" });
  const [corpora, setCorpora] = useState<CorpusSummary[]>([]);
  const [corporaLoading, setCorporaLoading] = useState(true);
  const [sourcesByCorpus, setSourcesByCorpus] = useState<
    Record<string, SourceSummary[]>
  >({});
  const [section, setSection] = useState<Section>(sectionFromHash);
  const [sidebarCollapsed, setSidebarCollapsed] =
    useState(readSidebarCollapsed);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [workspace, setWorkspace] = useState<Workspace>(emptyWorkspace);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const drawerRef = useRef<HTMLElement>(null);

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

  useEffect(() => {
    let active = true;
    void fetch("/api/corpora")
      .then(async (response) => {
        if (!response.ok) {
          return [];
        }
        const body = (await response.json()) as unknown;
        return Array.isArray(body) ? (body as CorpusSummary[]) : [];
      })
      .catch(() => [])
      .then((loaded) => {
        if (active) {
          setCorpora(loaded);
          setCorporaLoading(false);
          if (loaded.length === 0) {
            setSourcesByCorpus({});
          }
        }
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (corpora.length === 0) {
      return;
    }
    let active = true;
    void Promise.all(
      corpora.map(async (corpus) => {
        try {
          const response = await fetch(`/api/corpora/${corpus.id}/sources`);
          if (!response.ok) {
            return [corpus.id, [] as SourceSummary[]] as const;
          }
          return [corpus.id, asSourceList(await response.json())] as const;
        } catch {
          return [corpus.id, [] as SourceSummary[]] as const;
        }
      }),
    ).then((entries) => {
      if (active) {
        setSourcesByCorpus(Object.fromEntries(entries));
      }
    });
    return () => {
      active = false;
    };
  }, [corpora]);

  useEffect(() => {
    const onHashChange = () => setSection(sectionFromHash());
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  useEffect(() => {
    try {
      window.localStorage.setItem(
        SIDEBAR_STORAGE_KEY,
        sidebarCollapsed ? "true" : "false",
      );
    } catch {
      /* session-only fallback */
    }
  }, [sidebarCollapsed]);

  useEffect(() => {
    if (!mobileNavOpen) {
      return;
    }
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const firstItem = drawerRef.current?.querySelector<HTMLElement>("button");
    firstItem?.focus();

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        setMobileNavOpen(false);
        menuButtonRef.current?.focus();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [mobileNavOpen]);

  function closeMobileNav(restoreFocus = false) {
    setMobileNavOpen(false);
    if (restoreFocus) {
      menuButtonRef.current?.focus();
    }
  }

  function navigate(next: Section) {
    setSection(next);
    closeMobileNav();
    window.history.replaceState(null, "", `#${next}`);
    document.querySelector<HTMLElement>("#main-workspace")?.focus();
  }

  const activeLabel =
    section === "mcp"
      ? "MCP"
      : (navigation.find((item) => item.id === section)?.label ?? "Overview");
  const health = healthPresentation(status);

  return (
    <div
      className={`app-shell ${sidebarCollapsed ? "app-shell--collapsed" : ""} ${
        mobileNavOpen ? "app-shell--nav-open" : ""
      }`}
    >
      <aside className="sidebar sidebar--fixed" aria-label="Primary navigation">
        <div className="sidebar__brand">
          <span className="brand-mark" aria-hidden="true">
            PAR
          </span>
          <span className="sidebar__brand-name">
            Project Assurance Register
          </span>
        </div>
        <nav className="sidebar__nav">
          {navigation.map((item) => (
            <button
              key={item.id}
              className={`nav-item ${section === item.id ? "nav-item--active" : ""}`}
              type="button"
              aria-current={section === item.id ? "page" : undefined}
              aria-label={item.label}
              aria-describedby={
                sidebarCollapsed ? `nav-tooltip-${item.id}` : undefined
              }
              onClick={() => navigate(item.id)}
            >
              <ProductIcon name={item.icon} />
              <span className="nav-item-label">{item.label}</span>
              <span
                className="nav-tooltip"
                id={`nav-tooltip-${item.id}`}
                role="tooltip"
              >
                {item.label}
              </span>
            </button>
          ))}
        </nav>
        <div className="sidebar__secondary">
          <button
            className={`nav-item ${section === "mcp" ? "nav-item--active" : ""}`}
            type="button"
            aria-current={section === "mcp" ? "page" : undefined}
            aria-label="MCP machine interface"
            aria-describedby={sidebarCollapsed ? "nav-tooltip-mcp" : undefined}
            onClick={() => navigate("mcp")}
          >
            <ProductIcon name="mcp" />
            <span className="nav-item-label">MCP</span>
            <span className="nav-tooltip" id="nav-tooltip-mcp" role="tooltip">
              MCP
            </span>
          </button>
        </div>
        <button
          className="sidebar-toggle"
          type="button"
          aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
          aria-expanded={!sidebarCollapsed}
          onClick={() => setSidebarCollapsed((current) => !current)}
        >
          <ProductIcon name={sidebarCollapsed ? "expand" : "collapse"} />
        </button>
      </aside>

      {mobileNavOpen && (
        <button
          className="nav-backdrop"
          type="button"
          aria-label="Dismiss navigation"
          onClick={() => closeMobileNav(true)}
        />
      )}
      <nav
        id="mobile-navigation"
        className={`mobile-drawer ${mobileNavOpen ? "mobile-drawer--open" : ""}`}
        aria-label="Primary navigation"
        aria-hidden={!mobileNavOpen}
        ref={drawerRef}
        inert={!mobileNavOpen || undefined}
      >
        <div className="mobile-drawer__brand">
          <span className="brand-mark" aria-hidden="true">
            PAR
          </span>
          <strong>Project Assurance Register</strong>
        </div>
        {mobileNavigation.map((item) => (
          <button
            key={item.id}
            className={`nav-item ${section === item.id ? "nav-item--active" : ""}`}
            type="button"
            aria-current={section === item.id ? "page" : undefined}
            aria-label={
              item.label === "MCP" ? "MCP machine interface" : item.label
            }
            onClick={() => navigate(item.id)}
          >
            <ProductIcon name={item.icon} />
            <span className="nav-item-label">{item.label}</span>
          </button>
        ))}
      </nav>

      <div
        className="app-frame"
        {...(mobileNavOpen ? { inert: true, "aria-hidden": true } : {})}
      >
        <header className="app-bar">
          <div className="app-bar__start">
            <button
              ref={menuButtonRef}
              className="menu-toggle"
              type="button"
              aria-expanded={mobileNavOpen}
              aria-controls="mobile-navigation"
              aria-label={
                mobileNavOpen ? "Close navigation" : "Open navigation"
              }
              onClick={() =>
                setMobileNavOpen((current) => {
                  if (current) {
                    menuButtonRef.current?.focus();
                  }
                  return !current;
                })
              }
            >
              <ProductIcon name={mobileNavOpen ? "close" : "menu"} />
            </button>
            <div className="app-bar__identity">
              <span className="brand-mark app-bar__mark" aria-hidden="true">
                PAR
              </span>
              <div>
                <span className="app-bar__context">
                  Project Assurance Register
                </span>
                <strong className="app-bar__section">{activeLabel}</strong>
                <strong className="app-bar__product">
                  Project Assurance Register
                </strong>
              </div>
            </div>
          </div>
          <div className="app-bar__actions">
            <span
              className={`health-pill health-pill--${health.tone}`}
              aria-live="polite"
            >
              <span className="health-pill__dot" aria-hidden="true" />
              <span className="health-pill__label">{health.label}</span>
            </span>
          </div>
        </header>

        <main
          id="main-workspace"
          className="main-content"
          tabIndex={-1}
          aria-label={`${activeLabel} workspace`}
        >
          {section === "overview" && (
            <OverviewPanel
              status={status}
              corpora={corpora}
              corporaLoading={corporaLoading}
              sourcesByCorpus={sourcesByCorpus}
              workspace={workspace}
              onOpenWorkflow={() => navigate("agent-run")}
            />
          )}
          <div
            {...(section === "agent-run"
              ? {}
              : { hidden: true, inert: true, "aria-hidden": true })}
          >
            <WorkflowStatusPanel
              corpora={corpora}
              corporaLoading={corporaLoading}
              sourcesByCorpus={sourcesByCorpus}
              workspace={workspace}
              onWorkspaceChange={setWorkspace}
              onOpenReview={() => navigate("human-review")}
              onOpenRegister={() => navigate("register")}
            />
          </div>
          <div
            {...(section === "human-review"
              ? {}
              : { hidden: true, inert: true, "aria-hidden": true })}
          >
            <ReviewPanel
              corpora={corpora}
              corporaLoading={corporaLoading}
              sourcesByCorpus={sourcesByCorpus}
              workspace={workspace}
              onWorkspaceChange={setWorkspace}
              onReturnToWorkflow={() => navigate("agent-run")}
              active={section === "human-review"}
            />
          </div>
          <div
            {...(section === "register"
              ? {}
              : { hidden: true, inert: true, "aria-hidden": true })}
          >
            <RegisterPanel
              corpora={corpora}
              corporaLoading={corporaLoading}
              sourcesByCorpus={sourcesByCorpus}
              workspace={workspace}
              onWorkspaceChange={setWorkspace}
            />
          </div>
          {(section === "system" || section === "mcp") && (
            <SystemPanel
              status={status}
              corpora={corpora}
              corporaLoading={corporaLoading}
              sourcesByCorpus={sourcesByCorpus}
              focusMcp={section === "mcp"}
              onOpenMcp={() => navigate("mcp")}
            />
          )}
        </main>
      </div>
    </div>
  );
}
