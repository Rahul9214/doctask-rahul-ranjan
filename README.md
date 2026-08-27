# Project Assurance Register

Project Assurance Register is an evidence-led assurance application for mixed project documents. It builds a source-grounded understanding, evaluates configurable rules, pauses for explicit human decisions, and publishes a reviewed register only when a reviewer requests publication.

[Live Demo](https://heroic-surprise-production-13c1.up.railway.app) · [Backend Health](https://doctask-rahul-ranjan-production.up.railway.app/health) · [Readiness](https://doctask-rahul-ranjan-production.up.railway.app/ready) · [Version](https://doctask-rahul-ranjan-production.up.railway.app/version)

Current application identity: **Project Assurance Register 1.0.0**.

## Overview

The application ingests PDF, DOCX, Markdown, and text project sources into an isolated corpus. It then:

- builds an understanding from claims that retain exact source citations;
- evaluates the understanding against a versioned, configurable assurance ruleset;
- surfaces missing evidence as `UNKNOWN` instead of inventing support;
- keeps contradictory evidence visible rather than silently reconciling it;
- requires explicit approve, reject, or acknowledged reviewer-edit decisions for consequential findings;
- resumes durable execution only after the review gate is complete; and
- creates an authoritative register only through a separate publication action.

This is not an autonomous approval system. Generation cannot approve its own findings, resume does not create decisions, workflow completion does not publish, and publication is never automatic.

## Why this architecture

The control boundary separates evidence gathering and rule evaluation from human authority and authoritative output.

```mermaid
flowchart LR
    A[Project documents] --> B[Understand]
    B --> C[Examine]
    C --> D[Human Review<br/>approve / reject / edit]
    D --> E[Finalize<br/>explicit resume]
    E --> F[Explicit Publish<br/>reviewed register]
```

Human review is mandatory when required items exist. Resume continues a completed review; it never approves an item. Finalization marks the durable workflow complete, while publication remains an independent, explicit operation.

## Core control properties

- **Source-attributed evidence.** Supported facts retain source version, SHA-256, native locator, exact quote, and span. Citations are re-resolved against stored source bytes before consequential findings and publications are persisted.
- **No-bluffing semantics.** Retrieval supplies context, not proof. Unsupported information remains `UNKNOWN` or insufficient evidence; a plausible but unrelated citation cannot make a claim supported.
- **Contradiction visibility.** Conflicting grounded facts retain both source sides for examination and review.
- **Explicit decisions.** Required `FAIL`, `WARNING`, and `UNKNOWN` items must be approved, rejected, or edited with reviewer-authored acknowledgement. Optional `PASS` items do not block completion.
- **Durable gate and resume.** PostgreSQL-backed LangGraph checkpoints, workflow records, and an operation ledger preserve progress across resume and demonstrated process-kill recovery.
- **Immutable completed review.** A completed review session rejects later decision changes.
- **Approved/edited-only publication.** Approved and acknowledged reviewer-edited items are applied; rejected items are recorded as omitted and do not appear in the published item list.
- **Separate publication authority.** A completed workflow can remain unpublished. Publishing is an explicit, corpus-scoped action that creates an immutable register version.
- **Bounded machine operations.** MCP exposes the same assurance services through 20 typed operations, without arbitrary shell or file-execution tools.

These are application control properties, not claims of certification, penetration testing, identity separation, or internet-facing access control.

## Product workflow

1. Create a corpus and ingest source documents as immutable source versions.
2. **Understand** extracts relevant facts, validates citations, records missing evidence, and detects grounded contradictions.
3. **Examine** selects applicable rules from the active ruleset and produces `PASS`, `FAIL`, `WARNING`, or `UNKNOWN` findings.
4. The durable workflow opens a review session and stops at `waiting_for_review`.
5. A reviewer approves, rejects, or edits required findings. Edits require acknowledgement that their text is reviewer-authored and not system-grounded.
6. Completing the review makes its decisions immutable.
7. An explicit resume continues the same workflow without creating or changing decisions.
8. **Finalize** completes the workflow.
9. A separate explicit publish action creates the current register version.

The main records have distinct responsibilities:

| Record | Meaning |
| --- | --- |
| Workflow run | Durable execution state across Understand, Examine, the human gate, resume, and Finalize |
| Examination | Ruleset findings derived from a particular grounded analysis |
| Review session | Item-level human decisions over one examination |
| Published register | Immutable, explicitly published output containing applied decisions and provenance |

## Application surfaces

| Page | Purpose |
| --- | --- |
| Overview | Runtime state, corpora, source-document summary, and workflow entry point |
| Agent Run | Start or inspect durable execution, stage history, review state, resume, timing, and cost |
| Human Review | Inspect evidence and record explicit approve, reject, or reviewer-edit decisions |
| Register | Publish an eligible completed review and inspect the current register |
| System | Health, version, ruleset, MCP summary, and incremental-update evidence |
| MCP | The bounded stdio machine-operation surface and its operation groups |

## Live deployment

Railway hosts the current demonstration deployment:

| Surface | URL |
| --- | --- |
| Public application | <https://heroic-surprise-production-13c1.up.railway.app> |
| Backend | <https://doctask-rahul-ranjan-production.up.railway.app> |
| Liveness | <https://doctask-rahul-ranjan-production.up.railway.app/health> |
| Readiness | <https://doctask-rahul-ranjan-production.up.railway.app/ready> |
| Version | <https://doctask-rahul-ranjan-production.up.railway.app/version> |

The demonstrated topology uses a public frontend, a public FastAPI backend, and Railway PostgreSQL. The current readiness report verifies PostgreSQL and pgvector. Two synthetic demonstration corpora are seeded with eight source documents.

The Aurora Control Hub production acceptance run completed Understand and Examine, stopped at the human gate, resumed only after explicit review, finalized without publishing, and was then explicitly published. The resulting register applied approved and reviewer-edited items, omitted rejected items, and retained the completed review as immutable.

This is a demonstration deployment, not an SLA-backed service or a claim of production authentication, high availability, autoscaling, or multi-region operation.

## Architecture

The repository is one modular application with a small number of process roles, not a microservice fleet.

| Component | Responsibility |
| --- | --- |
| React + TypeScript frontend | Reviewer-facing workflow, review, register, system, and MCP views |
| Nginx | Serves the Vite build and proxies frontend `/api/*` requests |
| FastAPI | Health/readiness plus corpus, evidence, workflow, review, incremental, usage, and publication APIs |
| Application services | Shared business boundary used by both HTTP and MCP |
| LangGraph | Understand/Examine graphs and the outer durable workflow with a human interrupt |
| PostgreSQL + pgvector | Business records, checkpoints, operation evidence, and corpus-scoped retrieval |
| Mounted source store | Original source bytes used for provenance revalidation |
| MCP stdio server | Trusted-client typed adapter over the same application services |
| Alembic | Database schema migrations applied when the backend container starts |

**Local Compose:** Nginx/React frontend, FastAPI backend, and PostgreSQL/pgvector, with named volumes for the database, source files, and watcher inbox.

**Railway:** public Nginx/React frontend → Railway-internal backend route, alongside the public FastAPI backend → Railway PostgreSQL.

pgvector is used for corpus-scoped retrieval. A retrieval result is never treated as evidence until the exact citation and assertion-to-evidence checks pass.

See [docs/architecture.md](docs/architecture.md) for the data model, provenance boundary, durable workflow, incremental processing, and failure semantics.

## Technology stack

| Layer | Implemented technology |
| --- | --- |
| Frontend | React 19, TypeScript 6, Vite 8, Vitest, Testing Library |
| Web serving | Nginx 1.29 |
| Backend | Python 3.13, FastAPI 0.141, Pydantic 2.13, Uvicorn 0.52 |
| Workflow | LangGraph 1.2 with PostgreSQL checkpoints |
| Data | PostgreSQL 17, pgvector 0.8.1 image, SQLAlchemy 2.0, asyncpg, Alembic 1.19 |
| Document handling | pypdf, python-docx, Markdown/text deterministic parsing |
| Machine interface | MCP 2.0 over standard input/output |
| Packaging and delivery | uv, npm, Docker Compose, Railway |

Exact pinned backend versions are in [backend/pyproject.toml](backend/pyproject.toml); frontend versions and scripts are in [frontend/package.json](frontend/package.json) and its lockfile.

## MCP

The MCP server uses **standard input/output (stdio)** and is intended for local or otherwise trusted clients. It is not a public hosted MCP endpoint. Its 20 operations call the same corpus-scoped application services as HTTP:

| Category | Operations |
| --- | ---: |
| Corpus inspection | 3 |
| Workflow and grounded analysis | 5 |
| Human review | 6 |
| Publication | 3 |
| Incremental processing | 3 |

The surface can start and inspect workflows; inspect understanding, examination, review, registers, revisions, and incremental evidence; record explicit review decisions; complete review; resume; and explicitly publish. `complete_review` does not publish, `resume_workflow` does not approve, and no operation provides arbitrary shell or file execution.

Run the server or verify its registered operations from `backend/`:

```powershell
uv run python -m app.mcp_server
uv run python -m app.mcp_probe
```

## Local development

Docker Desktop with Compose is the shortest reproducible path. The default deterministic model adapter requires no model API key.

From the repository root:

```powershell
docker compose up --build
```

Compose supplies local environment defaults, so copying `.env.example` is not required. Create `.env` only when overriding those defaults.

| Local surface | URL |
| --- | --- |
| Frontend | <http://localhost:5173> |
| Backend OpenAPI | <http://localhost:8000/docs> |
| Liveness | <http://localhost:8000/health> |
| Readiness | <http://localhost:8000/ready> |
| Version | <http://localhost:8000/version> |

The backend URLs above address the local service directly. The committed Nginx upstream currently targets Railway, so the built frontend's `/api/*` proxy is not an all-local Compose route; restoring a Compose-specific upstream is a configuration follow-up outside this documentation-only pass.

Verify the running stack:

```powershell
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod http://localhost:8000/ready
Invoke-RestMethod http://localhost:8000/version
docker compose ps
```

Stop the stack without deleting its named volumes:

```powershell
docker compose down
```

The [manual test playbook](docs/manual-test-playbook.md) covers ingestion, the full human gate, resume, explicit publication, MCP, incremental processing, adversarial cases, and restart persistence.

## Configuration

[`.env.example`](.env.example) documents supported settings in these groups:

- PostgreSQL credentials, application/test database URLs, and local ports;
- application identity and version text;
- upload limits, readiness timeout, source storage, and watcher polling;
- deterministic or OpenAI-compatible model selection; and
- optional ruleset override.

Do not commit `.env` or API keys. `TEST_DATABASE_URL` is only for the disposable integration-test database: it must identify `project_assurance_test`, must differ from `DATABASE_URL`, and destructive cleanup also requires `ALLOW_DESTRUCTIVE_TEST_DATABASE=true`. Never point those safeguards at the application database.

## Testing and verification

### Backend

With PostgreSQL/pgvector reachable, set the application and disposable test URLs as shown in `.env.example`, then run from `backend/`:

```powershell
$env:DATABASE_URL = "postgresql+asyncpg://project_assurance:local_only@localhost:5432/project_assurance"
$env:TEST_DATABASE_URL = "postgresql+asyncpg://project_assurance:local_only@localhost:5432/project_assurance_test"
$env:ALLOW_DESTRUCTIVE_TEST_DATABASE = "true"
uv sync --frozen --all-groups
uv run python scripts/ensure_test_database.py
uv run alembic upgrade head
$applicationDatabaseUrl = $env:DATABASE_URL
$env:DATABASE_URL = $env:TEST_DATABASE_URL
uv run alembic upgrade head
$env:DATABASE_URL = $applicationDatabaseUrl
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
uv run pytest --cov=app --cov-report=term-missing
uv build
```

The current recorded Task-1 acceptance result is **249 collected, 249 passed, 0 failed, 91.44% coverage**, with `uv build` passing. This is the latest recorded local verification, not a guarantee for later commits. See [docs/final-acceptance.md](docs/final-acceptance.md) for the exact environment and executable acceptance evidence.

### Frontend

From `frontend/`:

```powershell
npm ci
npm run format:check
npm run lint
npm run typecheck
npm test
npm run build
```

The final Task-1 workspace-scroll verification recorded **52 frontend tests passed**.

CI runs the same backend and frontend quality gates, including the process-kill, MCP stdio, publication, migration, ruleset, secret-pattern, and final-acceptance suites.

## Demonstration corpora

- **Aurora Control Hub** exercises grounded agreement, contradictory milestone evidence, mixed human decisions, resume, and publication.
- **Harbor Ledger Modernization** provides a second isolated corpus and demonstrates insufficient-evidence behavior without corpus-name-specific logic.

Both corpora and all eight fixture documents are synthetic demonstration data, not customer or real-project data. Fixtures live under [`backend/fixtures/corpora`](backend/fixtures/corpora).

The intended demo fixture set is exactly those two corpora. Local databases can accumulate extra rows with the same names because tests and the UI create a new corpus UUID on each ingest; those extra rows are transient test records, not additional fixtures. The frontend corpus list is loaded from the API and is not hard-coded.

A corpus is not workflow-runnable until it has a current durable revision. Ingesting sources does not create that revision. Use one idempotent bootstrap command to create missing demo corpora, ingest fixture sources without duplicating existing versions, create the initial current revision, skip already-correct corpora, and repair incomplete legacy demo corpora:

```powershell
uv run python scripts/bootstrap_demo_corpora.py
```

The same command is `python -m app.demo_bootstrap`. It can be rerun safely. It does not delete data, complete human review, or start a workflow run. If a canonical demo `SourceVersion` row exists but its filesystem object is missing, bootstrap rematerializes the fixture bytes onto the recorded storage key after verifying SHA-256. It does not overwrite bytes that are present but do not match the recorded hash, and it does not repair non-demo corpora.

Source metadata lives in PostgreSQL. Immutable source bytes live on the local filesystem at `SOURCE_STORAGE_PATH`. Local Compose mounts a named volume at `/data/source-files`. There is no object-storage backend. A Railway service without a durable volume on that path will lose files on restart while database rows remain; that is a deployment persistence issue, not a reason to weaken ingest validation.

## Repository structure

```text
backend/                 FastAPI application, workflows, MCP server, migrations, tests, fixtures
frontend/                React/TypeScript application, Nginx configuration, frontend tests
docs/                    Architecture, final acceptance evidence, and manual test playbook
compose.yaml             Local PostgreSQL/backend/frontend topology
.env.example             Documented local and test configuration
README.md                Reviewer-facing project entry point
```

## Limitations and scope

- Internet-facing authentication, authorization, RBAC, and proposer/reviewer identity separation are not implemented.
- MCP is a trusted-client stdio interface, not a hosted or authenticated network service.
- The demonstrated deployment uses the deterministic model adapter by default. It has intentionally narrow extraction coverage and is not general-purpose model reasoning.
- Deterministic runs report zero provider cost. Live-provider cost remains unavailable unless a pricing basis is configured.
- Supported ingestion is PDF, DOCX, Markdown, and text. PDF processing requires extractable text; OCR, handwriting, spreadsheets, and arbitrary binary formats are out of scope.
- Parsers run in process without a separate sandbox or parser timeout.
- Original source bytes must remain available in the configured persistent source store for later provenance validation. A crash after file promotion but before database commit can leave an orphaned stored object.
- Incremental ingestion uses stable-file polling rather than filesystem events or a queue. Some failed pre-finalization incremental artifacts may require later reconciliation.
- The seeded corpora are synthetic fixtures, and the Railway instance is a demonstration service without an SLA or stated availability guarantees.

## Documentation

- [Architecture](docs/architecture.md) — components, data model, trust boundary, durability, and incremental design
- [Manual test playbook](docs/manual-test-playbook.md) — evaluator walkthrough from startup through controlled cleanup
- [Final acceptance](docs/final-acceptance.md) — recorded executable evidence and test results
- [Task contract](TASK.md) — original implementation assignment
- [Progress record](PROGRESS.md) — chronological implementation and verification history

## Status

Task-1 implementation and the deployed acceptance flow are complete. The Railway demonstration exercises the controlled workflow through explicit human review, durable resume, finalization, and separate explicit publication.
