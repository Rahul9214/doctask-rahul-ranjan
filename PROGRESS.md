# Progress and Decision Log

## Current state

- **Current phase:** Phase 07 — Incremental Updates — original independent verification FAIL /
  NO-GO retained; first correction then first re-verification NO-GO; local final correction
  PASS then independent re-verification NO-GO (unsafe populated `0007` downgrade); local
  `0007` downgrade correction PASS then mixed-ownership test proof was vacuous; local mixed-ownership
  regression test correction PASS. Do not mark independent PASS. Phase 06 historical independent FAIL / NO-GO and exclusive retry-allowlist correction
  remain below.
- **Implementation status:** grounded Understand is committed on `main`. Grounded Examine and
  Phase 05 human review remain historically independently FAIL / NO-GO; those corrections were
  implemented locally and are on the ancestry of this branch. Phase 06 durable resume had an
  initial local PASS on `feat/phase-06-durable-resume`, then independent verification FAIL /
  NO-GO; exclusive retry-allowlist correction is implemented locally and is not independently
  re-verified. Phase 07 focused incremental updates and stable-file watching are implemented
  locally on `feat/phase-07-incremental-updates`. Independent Phase 07 verification was FAIL /
  NO-GO; a first correction pass followed; independent re-verification remained NO-GO. This record
  is a local final correction pass (local PASS). Independent re-verification of that pass was
  NO-GO on populated `0007` downgrade. A local downgrade-order correction followed; migration
  implementation passed inspection, but the mixed-ownership regression proof was vacuous. A local
  mixed-ownership test correction follows. Independent re-verification of that correction is
  not complete.
- **Application capabilities implemented:** liveness, dependency readiness, version/phase metadata,
  corpus/source/version/block schema, streamed ingestion, four parsers, exact citation resolution,
  deterministic pgvector retrieval, configurable model boundary with a keyless deterministic adapter,
  LangGraph Understand (classify/extract/ground/contradict/unknowns), inspectable analysis-run APIs,
  versioned `software-project-assurance.v1` Examine ruleset, LangGraph Examine
  (load/select/evaluate/validate/summarize/finalize), inspectable examination-run APIs,
  explicit review sessions/items/decisions, a minimal React review panel, durable workflow runs with
  PostgreSQL LangGraph checkpoints, a session-level same-run execution lock, an expensive-operation
  ledger, real process-kill resume, same-corpus run isolation, focused incremental corpus revisions,
  provenance impact analysis, canonical unchanged-byte proof, executed-versus-reused operation
  evidence, conservative fresh review, stale-baseline concurrency, stable-file inbox watching,
  local Compose stack, tests, and CI definition
- **Dependencies installed by this work:** locked Python and npm dependencies recorded below;
  httpx 0.28.1 is now a main backend dependency for the live OpenAI-compatible adapter;
  psycopg[binary] 3.3.4 is a main backend dependency for LangGraph PostgreSQL checkpointing
- **Application or test commands available:** exact verified commands are recorded below and in
  `README.md`
- **Git write operations performed by the agent:** none
- **Phase 01 status:** COMPLETE — local verification PASS, remote CI PASS, merged to `main`
- **Phase 01 remote CI status:** PASS — attempt 2 backend/frontend and all PR checks passed
- **Phase 01 merge status:** PR #1 merged to `main` as merge commit `cd9ffa7`
- **Phase 02 status:** COMPLETE — implementation PASS, local verification PASS, independent
  verification GO, merged to `main` as merge commit `d0c2f0f` (PR #2)
- **Phase 02 remote CI:** workflow accepted but externally blocked by account Actions
  budget/scheduler state; zero Phase 02 CI jobs materialized; normal and force cancellation
  returned GitHub HTTP 500; no Phase 02 code-related CI failure observed
- **Phase 03 status:** historical independent FAIL (grounding) and follow-up NO-GO retained.
  Independent final follow-up: **GO**. Phase 03 committed. PR #3 merged to `main` as merge commit
  `ceb2bf0`. Remote CI: PASS (2 successful checks).
- **Phase 04 status:** local initial implementation PASS; independent verification FAIL / NO-GO;
  correction implemented locally; independent re-verification of that correction is not complete
- **Phase 05 status:** local initial PASS; independent verification FAIL / NO-GO; correction
  implemented locally; independent re-verification not complete
- **Phase 06 status:** initial local PASS; independent verification FAIL / NO-GO; first correction
  implemented locally; independent re-verification NO-GO; second live-retry correction implemented
  locally; retry-allowlist re-verification NO-GO; exclusive retry-allowlist correction implemented
  locally; independent re-verification of that correction is not complete
- **Phase 07 status:** original independent verification FAIL / NO-GO retained; first correction
  implemented locally; first independent re-verification NO-GO; local final correction PASS;
  independent re-verification of that pass NO-GO (populated `0007` downgrade); local downgrade
  correction PASS; mixed-ownership downgrade regression proof was vacuous; local mixed-ownership
  test correction PASS on `feat/phase-07-incremental-updates`. Do not mark independent PASS.
- **SuperDocs familiarization/docs confirmation:** COMPLETE — manual candidate action outside the repository; recording it here is our process choice, not an assignment-mandated artifact

## Phase 00 record â€” 2026-08-18

### Files created

- `README.md`
- `TASK.md`
- `PROGRESS.md`
- `docs/architecture.md`

No application code, dependency manifests, backend/frontend directories, migrations, container files, fixtures, or tests were created in Phase 00.

### Manual candidate prerequisite record â€” 2026-08-19

The candidate confirmed completing these actions personally outside the repository:

- [x] SuperDocs product familiarization
- [x] Authorized/non-confidential document used
- [x] Warm-up/small instruction performed
- [x] Document uploaded/opened
- [x] Targeted edit performed
- [x] Review Mode used
- [x] Human review decision performed
- [x] Export/download performed
- [x] Export opened and verified
- [x] Relevant SuperDocs documentation reviewed
- [x] REST/API and MCP concepts reviewed
- [x] SuperDocs GitHub organization inspected

Only completion status is recorded; no document, account, credential, contact, or personal details are included.

## Phase 01 record â€” 2026-08-19

### Scope completed

Implemented development foundation only:

- FastAPI application factory/lifespan with `GET /health`, `GET /ready`, and `GET /version`;
- Pydantic v2 environment settings with the database URL held as `SecretStr`;
- async SQLAlchemy engine/session factory and graceful engine disposal;
- Alembic configuration and revision `20260819_0001` enabling `vector`;
- React/TypeScript status shell with loading, ready, dependency-unavailable, version, and phase
  states;
- PostgreSQL/pgvector, backend, and Nginx-served frontend Compose services;
- persistent local database volume and dependency-aware health ordering;
- backend/frontend formatting, lint, typecheck, test, coverage, and build commands;
- PostgreSQL/pgvector integration test; and
- one concise GitHub Actions CI workflow.

No Task 1 business table, ingestion/parser, LangGraph workflow, LLM integration, human review,
MCP business tool, watcher, or incremental update was implemented.

### Runtime and dependency decisions

- CPython **3.13.14** is the exact project runtime. The host's CPython 3.14.4 was not modified.
- uv **0.11.26** manages/downloads Python and locks Python packages.
- Node.js **22.20.0** is the selected frontend runtime baseline. npm **11.12.1** is the candidate
  verification version, not an enforced project-wide exact version. The committed
  `package-lock.json` defines dependency resolution.
- PostgreSQL **17** and pgvector **0.8.1** use
  `pgvector/pgvector:0.8.1-pg17-bookworm`; its amd64/arm64 manifest was inspected before use.
- Backend direct versions: Alembic 1.19.1, asyncpg 0.31.0, FastAPI 0.141.1, LangGraph 1.2.11,
  langgraph-checkpoint-postgres 3.1.2, MCP 2.0.0, pgvector 0.5.0, Pydantic 2.13.4,
  pydantic-settings 2.15.0, SQLAlchemy 2.0.52, and Uvicorn 0.52.3.
- Backend development versions: HTTPX 0.28.1, mypy 2.3.1, pytest 9.1.1,
  pytest-asyncio 1.4.0, pytest-cov 7.1.0, and Ruff 0.16.3.
- Frontend direct baseline: React/React DOM 19.2.8, Vite 8.2.1, TypeScript 6.0.3,
  ESLint 10.8.1, Prettier 3.9.6, Vitest 4.1.11, jsdom 29.1.1, and React Testing Library 16.3.2.
  Exact transitive resolutions are in `package-lock.json`.

Current authoritative PyPI metadata reported Python 3.13 compatibility for all selected backend
packages. Python 3.13 was selected over 3.14 because it is the newer stable line with broader
ecosystem wheel/runtime maturity across the full planned stack.

LangGraph, its PostgreSQL checkpoint package, pgvector's Python integration, and MCP are locked now
for compatibility evidence only. Phase 01 application code does not import or use their business
APIs.

### Cursor implementation verification â€” exact commands and final results

Inspection:

- `git branch --show-current` â€” `feat/phase-01-foundation`
- `git status --short --branch` â€” clean before implementation
- `git log -5 --oneline --decorate` and `git ls-files` â€” Phase 00 baseline inspected
- `python --version`, `py -0p`, `uv --version`, `node --version`, `npm --version`,
  `docker --version`, `docker compose version` â€” host versions captured
- PyPI JSON metadata queries for every direct backend/runtime tool â€” versions and
  `requires_python` inspected
- npm metadata queries for React/Vite/TypeScript/ESLint/Prettier/Vitest/RTL â€” versions and Node
  engines inspected
- `uv python list 3.13` â€” CPython 3.13.14 managed download confirmed
- `docker manifest inspect pgvector/pgvector:0.8.1-pg17-bookworm --verbose` â€” image/platforms
  confirmed

Backend final gate from `backend/`:

- `uv sync --frozen --all-groups` â€” PASS; 90 packages resolved, 88 installed/checked
- `uv run ruff format --check .` â€” PASS; 10 files already formatted
- `uv run ruff check .` â€” PASS
- `uv run mypy src tests` â€” PASS; no issues in 8 source files
- `uv run pytest --cov=app --cov-report=term-missing` â€” PASS; 7 passed, 1 integration test skipped
  without `TEST_DATABASE_URL`, 97.96% total coverage
- `uv build` â€” PASS; source distribution and wheel built

Real database gate:

- `uv run alembic current` with the running Compose database â€” PASS;
  `20260819_0001 (head)`
- `uv run pytest tests/test_readiness_integration.py` with `DATABASE_URL` and
  `TEST_DATABASE_URL` set â€” PASS; 1 passed against PostgreSQL/pgvector

Frontend final gate from `frontend/` during Cursor implementation verification:

- `npm ci` â€” PASS; 235 packages installed, 0 reported vulnerabilities
- `npm run format:check` â€” PASS
- `npm run lint` â€” PASS
- `npm run typecheck` â€” PASS
- `npm test` â€” PASS; 1 file and 4 tests passed
- `npm run build` â€” PASS; Vite production output built

Container/runtime gate from repository root:

- `docker compose config` and final `docker compose config --quiet` â€” PASS
- `docker compose build` â€” PASS for backend and frontend
- `docker compose up --build --detach` â€” PASS as the combined build/start path; all services became
  healthy and readiness/frontend smoke checks passed
- `docker compose up --detach` â€” PASS; database, backend, and frontend started
- `docker compose exec backend alembic current` â€” PASS; migration at head
- `Invoke-RestMethod http://localhost:8000/health` â€” PASS; `alive`
- `Invoke-RestMethod http://localhost:8000/ready` â€” PASS; PostgreSQL and pgvector `ready`,
  pgvector `0.8.1`
- `Invoke-RestMethod http://localhost:8000/version` â€” PASS; version `0.1.0`, Phase 01, truthful
  not-implemented status
- `Invoke-WebRequest -UseBasicParsing http://localhost:5173/` â€” PASS; HTTP 200
- `Invoke-WebRequest -UseBasicParsing http://localhost:5173/api/ready` â€” PASS; HTTP 200 through
  Nginx proxy
- `docker compose ps` â€” PASS; all three services healthy
- Browser accessibility snapshot â€” PASS; rendered `Foundation ready`, version `0.1.0`, current
  Phase 01, and `Task 1 business workflow is not implemented yet.`
- Browser console error check â€” PASS; zero errors/warnings
- `docker compose down` â€” PASS; containers/network removed and persistent volume retained
- final `docker compose ps --all` â€” PASS; no running project containers

### Candidate-side independent verification correction â€” 2026-08-19

The candidate independently confirmed that backend, Docker, PostgreSQL/pgvector, migration,
readiness, HTTP smoke, and real database integration gates passed.

The candidate's initial independent frontend verification produced:

- `npm ci` â€” PASS
- `npm run format:check` â€” **FAIL**; Prettier reported formatting drift/non-canonical formatting in:
  - `.prettierrc.json`
  - `eslint.config.js`
  - `src/App.test.tsx`
  - `src/App.tsx`
  - `src/main.tsx`
  - `src/styles.css`
  - `src/test/setup.ts`
  - `vite.config.ts`

The candidate corrected the defect with:

- `npm run format` â€” PASS; Prettier applied canonical formatting

The candidate then reran the complete affected frontend quality/build gate:

- `npm run format:check` â€” PASS; `All matched files use Prettier code style!`
- `npm run lint` â€” PASS
- `npm run typecheck` â€” PASS
- `npm test` â€” PASS; 1 test file and 4 tests passed
- `npm run build` â€” PASS; Vite production build completed successfully

This candidate-side failure remains part of the evidence history. Phase 01 remains PASS only because
the formatting defect was corrected and every affected frontend gate was rerun successfully.

README command verification after the correction:

- frontend scripts in `README.md` match `frontend/package.json`, including `npm run format`,
  `npm run format:check`, lint, typecheck, tests, and build;
- backend commands match the tools/configuration in `backend/pyproject.toml`; and
- `docker compose config --quiet` passed for the documented Compose commands.

No README command correction was required.

### Independent Phase 01 verification â€” PASS_WITH_CHANGES â€” 2026-08-19

- Independent verifier result: **PASS_WITH_CHANGES**
- Critical findings: **none**
- Remote CI at that verification point: **DEFINED / LOCALLY MIRRORED / REMOTE UNVERIFIED**
- Fresh-clone Behavior 6: **NOT_STARTED**

Minimal corrections applied:

- Hardened `backend/.dockerignore` against environment files, virtual environments, Python
  caches/bytecode, test/type/lint caches, coverage, build output, and logs.
- Hardened `frontend/.dockerignore` against environment files, dependency/build/coverage output,
  TypeScript build metadata, logs, and Git metadata.
- Corrected npm wording: Node.js 22.20.0 is the selected runtime baseline, npm 11.12.1 is the
  candidate verification version, and `package-lock.json` is the committed dependency resolution.
- Clarified that the local Compose `POSTGRES_PASSWORD` must match `[A-Za-z0-9_]+` because the same
  literal value is passed to PostgreSQL and interpolated into `DATABASE_URL`. Percent-encoded or
  arbitrary special-character values are not supported by this simple local Compose path.
- Added root `logs/` ignore coverage while retaining `*.log`.

Correction verification:

- Backend Ruff format check â€” PASS; 10 files formatted
- Backend Ruff lint â€” PASS
- Backend mypy â€” PASS; no issues in 8 source files
- Backend pytest/coverage final rerun â€” PASS; 7 passed, 1 integration test skipped without
  `TEST_DATABASE_URL`, 97.96% coverage
- Backend package build â€” PASS; source distribution and wheel built
- Frontend Prettier check â€” PASS; canonical formatting confirmed
- Frontend ESLint â€” PASS
- Frontend TypeScript typecheck â€” PASS
- Frontend Vitest â€” PASS; 1 test file and 4 tests passed
- Frontend production build â€” PASS
- `docker compose config` â€” PASS
- `docker compose build` â€” PASS; both hardened contexts retained every required Docker build input
- `docker compose up --detach` and `docker compose ps` â€” PASS; database, backend, and frontend all
  healthy
- `/health`, `/ready`, and `/version` â€” PASS
- Frontend `/` and `/api/ready` â€” PASS; HTTP 200
- `docker compose exec backend alembic current` â€” PASS; `20260819_0001 (head)`
- Container startup logs â€” PASS; migration, Uvicorn, and Nginx startup completed without runtime
  package synchronization
- `docker compose down` â€” PASS; containers/network removed and persistent volume retained
- final `docker compose ps --all` â€” PASS; no project containers remained
- `git diff --check` â€” PASS

### Remote GitHub CI attempt 1 â€” backend failure â€” 2026-08-19

- Frontend CI: **PASS**
- Backend CI: **FAIL**
- Backend steps before pytest: checkout, uv setup, Python 3.13.14, frozen sync, migration, Ruff
  format/lint, and mypy all **PASS**
- Backend pytest: 7 passed, 1 failed
- Backend coverage: 94.90%; the 90% threshold was reached
- Failing test:
  `tests/test_api.py::test_ready_returns_actionable_safe_failure_when_database_is_unavailable`
- Failure: Linux/GitHub Actions surfaced `ConnectionRefusedError: [Errno 111] Connect call failed
  ('127.0.0.1', 1)` from the intentional unavailable-database readiness check.

Root cause:

- asyncpg's connection loop catches each `OSError`, retains it as `last_error`, and re-raises that
  OS error when no address connects.
- Linux rejects the loopback port immediately with `ConnectionRefusedError`, which inherits from
  `OSError`/`ConnectionError` but not `SQLAlchemyError`.
- SQLAlchemy's asyncpg connection path allowed that pre-connection OS error to propagate unchanged.
- `check_dependencies` translated only `TimeoutError` and `SQLAlchemyError`. The Windows test had
  reached the bounded timeout path, so local verification did not expose the missing Linux
  classification.

Minimal fix:

- Focused fix commit: `b7f4e5a`
- Translate `OSError` alongside `SQLAlchemyError` at the database dependency boundary.
- Retain the separate bounded `TimeoutError` response.
- Do not catch blanket `Exception`; programming errors continue to propagate.
- Continue returning only controlled cause/remedy text without raw driver details or credentials.

Focused test changes:

- Retained the real unreachable-port API test and strengthened it to reject the complete database
  URL, password, exception class, and raw connection-refusal text.
- Added direct connection-refusal translation coverage.
- Added timeout translation coverage.
- Added a test proving an unexpected `ValueError` is not swallowed.
- Retained the real PostgreSQL/pgvector readiness integration test.

Local fix verification:

- `uv run ruff format --check .` â€” PASS; 10 files formatted
- `uv run ruff check .` â€” PASS
- `uv run mypy src tests` â€” PASS; no issues in 8 source files
- `uv run pytest --cov=app --cov-report=term-missing` â€” PASS; 10 passed, 1 integration test skipped
  without `TEST_DATABASE_URL`, 100% coverage
- `uv build` â€” PASS; source distribution and wheel built
- `docker compose config` â€” PASS
- `docker compose up --build --detach` â€” PASS
- `docker compose ps` â€” PASS; database, backend, and frontend all healthy
- `/health`, `/ready`, and `/version` â€” PASS
- `docker compose exec backend alembic current` â€” PASS; `20260819_0001 (head)`
- real `tests/test_readiness_integration.py` against the Compose database â€” PASS; 1 passed
- `docker compose down` â€” PASS
- `git diff --check` â€” PASS

Remote CI status: **FAILED / FIX PENDING** until the candidate pushes this fix and GitHub Actions
reruns successfully. Attempt 1 remains recorded and is not reclassified as PASS.

### Remote GitHub CI attempt 2 and merge â€” 2026-08-19

- Focused readiness fix commit: `b7f4e5a`
- Backend CI: **PASS**
- Frontend CI: **PASS**
- All PR checks: **PASS**
- Merge conflicts: **none**
- Pull request: **#1**
- Pull request result: **merged into `main`**
- Merge commit: `cd9ffa7`

Phase 01 final result:

- **COMPLETE**
- **LOCAL VERIFICATION: PASS**
- **REMOTE CI: PASS**
- **MERGED TO MAIN: YES**

Attempt 1 remains the historical failed run. Attempt 2 is the successful remote verification after
the focused cross-platform readiness fix.

### Failures encountered and fixes

- Initial `uv sync --all-groups` failed because Hatchling rejects a package `readme` outside the
  backend project root. Removed the invalid `../README.md` package metadata reference; sync and
  builds then passed.
- Initial Ruff lint found two import-order issues and one unused import. Applied Ruff's safe fixes
  and reran format/lint successfully.
- `npm create vite` received its template option incorrectly under the host npm version and created
  a vanilla TypeScript scaffold. The generated placeholder files were removed and the intended
  React/TypeScript configuration was created and tested.
- The first frontend test command entered Vitest watch mode because npm parsed `--run` as npm
  configuration. Changed the repository script to `vitest run`; tests then exited cleanly.
- A parallel `npm ci` and Prettier check raced while `node_modules` was being replaced, producing a
  false â€œprettier not recognizedâ€ failure. Dependency installation and quality checks were rerun in
  the correct sequence and passed.
- Candidate-side independent verification later found genuine formatting drift/non-canonical
  formatting in eight frontend files. The candidate ran `npm run format`, then reran
  `format:check`, lint, typecheck, tests, and build; every rerun passed. This failure is separate from
  Cursor's earlier dependency-install race and is retained as correction evidence.
- The first correction-phase coverage invocation inherited a stale `TEST_DATABASE_URL` from the
  persistent verification shell while Compose was stopped, so the real integration test attempted
  a closed local port and failed. Cleared only the temporary database environment variables and
  reran the requested coverage command; 7 tests passed, 1 integration test skipped as designed,
  and coverage was 97.96%. No application change was required.
- Initial backend coverage was 89.80%, below the configured 90% gate. Added direct tests for actual
  pgvector-ready and extension-missing readiness branches; final coverage is 97.96%.
- Docker build initially failed because Docker Desktop was installed but its daemon was stopped.
  Docker Desktop was started without changing Docker/global configuration.
- One long Docker build attempt was interrupted before completion. The resumed build used visible
  plain progress, completed successfully, and the final cached full build also passed.
- Backend startup logs showed `uv run` synchronizing development packages at container startup.
  Changed the runtime command to invoke installed `alembic` and `uvicorn` executables directly;
  clean startup then performed no package synchronization.
- Frontend container health remained unhealthy because BusyBox `wget` could not connect to
  `localhost` while Nginx listened on IPv4. Changed the health target to `127.0.0.1`; all services
  then reported healthy.
- One PowerShell smoke command placed `-Depth` on `Invoke-RestMethod`, which PowerShell 5 does not
  support. Moved `-Depth` to `ConvertTo-Json`; the readiness smoke check passed.

### Security verification

- No model key, SuperDocs key, GitHub token, personal credential, or real secret was added.
- `.env` and common secret/runtime/build/cache outputs are ignored; only safe local defaults appear
  in `.env.example`.
- The database URL is a Pydantic `SecretStr`.
- Readiness exceptions are mapped to controlled cause/remedy text; raw driver exceptions and URLs
  are not returned.
- A backend test embeds a sentinel password and confirms it is absent from readiness output.
- npm reported zero known vulnerabilities during the recorded install.
- Container logs inspected during verification contained no environment credentials or keys.

### Assumptions and limitations

- The verified deployment is local/container development, not internet-facing production.
- Local database credentials are intentionally low-sensitivity defaults and must be changed for
  any non-local environment.
- Runtime containers currently run with image-default users; non-root hardening is deferred.
- Remote CI attempt 1 failed in the backend while the frontend passed. Focused fix `b7f4e5a` then
  produced a fully passing backend/frontend attempt 2; PR #1 merged to `main` as `cd9ffa7`.
- Major-version GitHub Action references are used; immutable action SHA pinning is not yet applied.
- Docker image tags are version-pinned, while registry content trust/signature enforcement is not
  configured.
- No business capability from Task 1 is present, including business schema, graph, checkpoints,
  review, ingestion, MCP operations, model gateway, or watcher.

### Phase 01 conclusion

Phase 01 is **COMPLETE / FORMALLY CLOSED**. Local verification passed, remote CI attempt 2 passed
for both backend and frontend, all PR checks passed without merge conflicts, and PR #1 merged to
`main` as `cd9ffa7`. Attempt 1 remains recorded as the failed backend run; it is not rewritten as a
pass. Fresh-clone Behavior 6 remains `NOT_STARTED`. Phase 02 may begin only after separate explicit
candidate authorization.

### Approved direction

- Work only on Task 1 and the global assignment rules that affect it.
- Proposed domain: Software Project Assurance.
- Proposed grounded deliverable: Project Assurance Register.
- Assignment requested/preferred: Python/FastAPI, an agent orchestration framework such as LangGraph/LangChain, PostgreSQL with vector search, and React; comparable tools are allowed when justified.
- Our chosen implementation: Python, FastAPI, LangGraph, PostgreSQL/pgvector, React/TypeScript, and MCP as the strongest chosen machine-interface shape.
- Initial architecture: modular monolith with shared application services and separate process roles only where needed.
- Data: synthetic/public only.
- Candidate execution constraint/project planning assumption: 24-hour hard ceiling, with approximately 19.5 hours planned across Phases 01â€“10 and 4.5 hours protected for debugging, verification, evidence, and final audit. This schedule is not stated in the assignment PDF.

## Decisions

### D-001 â€” Domain and corpus

Use fictional software-project assurance documents because overlapping plans, status reports, risks, decisions, and meeting records naturally exercise extraction, contradiction, rules, exact provenance, and focused updates without sensitive data.

### D-002 â€” Deliverable structure

Use stable structured Project Assurance Register items rather than a free-form report. Stable IDs and canonical serialization make item-level review, incremental replacement, and exact unchanged-content proof feasible.

### D-003 â€” Format breadth

Target text-based PDF, DOCX, Markdown, and plain text. Exclude OCR, handwriting, arbitrary formats, and spreadsheet output initially. Consider CSV only after the five-behavior floor and genuine movement evidence are green.

### D-004 â€” Exact provenance

A supported claim/finding requires immutable source version ID and SHA-256, a format-native locator, a span where available, and exact quoted evidence. A page number alone is not sufficient.

### D-005 â€” Human gate

The acceptance demonstration uses a real human decision:

```text
agent proposes
â†’ WAITING_FOR_REVIEW
â†’ human reviews
â†’ human explicitly approves/rejects individual items
â†’ decision is submitted through a UI/API/MCP operation
â†’ workflow resumes
â†’ only approved items are applied
```

MCP/API exposes explicit item-level operations, but the demonstrated path does not let the proposing agent automatically approve its own work. No RBAC or proposer/reviewer identity-separation requirement is added.

### D-006 â€” Machine operation

React and MCP/API will call the same application services. The machine surface exposes, rather than bypasses, the review gate. MCP is our strongest chosen interface shape, not an absolute assignment mandate.

### D-007 â€” Durability and concurrency

Start with the simplest PostgreSQL-backed durable design that proves checkpoint resume, idempotency, concurrent-run isolation, and safe publication. Do not pre-commit to a transactional outbox. Add one only if implementation tests expose a concrete need.

### D-008 â€” Incremental definition

A new source may be fully parsed and indexed, but the existing corpus must not be fully reprocessed by the model. Determine an affected entity/rule set, process only that set, and preserve unaffected register item canonical bytes and hashes.

### D-009 â€” Keyless proof

Behavior 7 is planned as a strong differentiator: use a deterministic model adapter only at the model boundary while exercising real graph transitions, parsers, PostgreSQL/pgvector, process restart, transactions, concurrency, API/MCP transport, and deterministic validators. It may be cut only with explicit rationale if time forces a trade-off.

### D-010 â€” Hosted deployment

Hosted deployment is not explicitly required by Task 1. Our minimum acceptance target is a reproducible local/container deployment. Hosted deployment will be attempted only after all mandatory Task 1 behaviors and evidence are green.

### D-011 â€” Infrastructure restraint

Do not introduce Kubernetes, Terraform, Kafka, Redis, Celery, microservices, or similar infrastructure without a measured blocker. Prefer one codebase and PostgreSQL.

### D-012 â€” Truthful documentation

README must separate **implemented** from **planned**. Capabilities are not marked implemented until executable evidence passes and is recorded here.

### D-013 â€” Git control

The candidate executes all Git writes. Agents may inspect Git read-only and must provide exact manual commands whenever Git work is needed.

### D-014 â€” Command truthfulness

Do not invent scripts, package names, or commands. Phase 01 creates and verifies the command contract. Every later phase must provide exact commands that exist in the repository.

### D-015 â€” Behaviors 6â€“10 classification

Behaviors 1â€“5 are the explicit non-cuttable floor. Each behavior 6â€“10 itemâ€”one-command stranger setup, real keyless tests, document prompt-injection defense, concurrent isolation, and stage timing/costâ€”is a **Strong differentiator â€” may be cut only with explicit rationale if time forces a trade-off.**

### D-016 â€” Movement cut policy

Understand, examine, and stay alive must each remain genuinely represented. Detailed sub-features inside those movements may be cut with explicit rationale; they are not all independently non-cuttable.

### D-017 â€” Deliverable-side provenance

A register-grounded finding uses `register_version_id`, `register_item_id`, `field_path`, `value_hash`, and `exact_value`. Validation resolves the locator against the immutable register version before treating the finding as supported.

### D-018 â€” Costly external-call crash window

Persist operation key and attempt before the call, use provider idempotency when available, persist the structured result before graph advancement, and reuse durable completed results on resume. Retry only when non-completion is known. An unknowable provider outcome becomes an honest ambiguous state for reconciliation/retry; exactly-once behavior is not claimed.

### D-019 â€” Incremental proof

Evidence must compare affected item IDs, preserved item IDs, executed stage IDs, model-operation/idempotency keys, processed source versions, and canonical before/after hashes. Hash equality alone does not prove a full rerun was avoided.

### D-020 â€” Graceful degradation

Demonstrated failure paths should use a working deterministic fallback, bounded retry, safe skip, or human escalation where implemented and tested. If no safe fallback exists, preserve durable state, expose cause/remedy, remain resumable, and never falsely report success. No fallback is currently implemented or claimed.

## Assumptions

### A-001 â€” Meaning of â€œcommitâ€

â€œCommitâ€ in the agentic workflow means applying approved items to a new durable register version. It does not mean a Git commit.

### A-002 â€” Meaning of â€œmixed formatsâ€

The initial declared set of PDF, DOCX, Markdown, and TXT satisfies mixed-format input. PDF support initially requires extractable text.

### A-003 â€” Meaning of â€œexact placeâ€

Exact source provenance means a resolvable immutable source/hash, native locator, span, and quoteâ€”not only a document name or page.

### A-004 â€” Watched location

The minimum watcher is a mounted local inbox using stable-file detection and content-hash deduplication. API uploads may emit the same ingestion event. Sophisticated filesystem infrastructure is unnecessary unless tests prove otherwise.

### A-005 â€” Explicit review

A human can submit decisions through the React UI or invoke an explicit API/MCP decision operation. The important property is conscious item-level human choice, not which adapter carries it. This does not assume RBAC or proposer/reviewer identity separation.

### A-006 â€” Model availability and cost

Runtime model access is provider-configurable. The planned Behavior 7 strong differentiator is a real keyless acceptance suite and demo mode. If pricing is unavailable, report token/usage data and â€œcost unavailableâ€ instead of inventing a currency amount.

### A-007 â€” Retrieval and grounding

pgvector improves retrieval recall but cannot establish evidence. Only deterministic resolution against immutable source content establishes provenance.

### A-008 â€” One-command target

The intended fresh-clone target is a single local/container startup command after the required file is implemented and verified. Phase 00 does not claim that command exists.

### A-009 â€” Authentication scope

Local/demo identity may be sufficient within the time ceiling. Corpus/run scoping remains a planned data-safety baseline; concurrent-run proof is Behavior 9 and therefore a strong differentiator rather than part of the explicit five-behavior floor. Internet-facing production authentication is not claimed unless implemented and tested.

### A-010 â€” SuperDocs familiarization data

Candidate product familiarization may use the candidateâ€™s own non-confidential work outside this repository. Repository fixtures and demonstrations remain synthetic/public.

### A-011 â€” Measurement

Measurement methodology is stated before results. Variance, tail behavior, pricing basis, and limitations are reported. Raw measurement data will be committed to the repository. A success claim requires matching evidence.

## Evidence register

Status values are `NOT_STARTED`, `IN_PROGRESS`, `PASS`, `FAIL`, or `CUT_OPTIONAL`.

### Five-behavior non-cuttable floor

- Visible path-changing stages â€” `NOT_STARTED`
- Exact claim/finding provenance â€” `NOT_STARTED`
- Unsupported-claim honesty â€” `NOT_STARTED`
- Real human mixed approve/reject — `PASS` for the Phase 05 review gate (not register publication)
- Approved-only application — `NOT_STARTED`
- Process kill and durable resume — `NOT_STARTED`
- Machine-interface end-to-end explicit gate operations — `PASS` for API review operations; MCP
  remains `NOT_STARTED`

### Planned movement evidence

- Mixed-format ingestion and declared-format validation â€” `PASS` for Phase 02
- Document classification reasoning â€” `NOT_STARTED` for Phase 03
- Contradiction surfacing â€” `NOT_STARTED`
- Honest no-findings result â€” `NOT_STARTED`
- Configuration-only rule/domain change â€” `NOT_STARTED`
- Focused incremental processing â€” `NOT_STARTED`
- Incremental affected/preserved IDs, stages, operation keys, source versions, and before/after hashes â€” `NOT_STARTED`
- Source-attributed change history â€” `NOT_STARTED`
- Second-corpus fixture creation for ingestion/provenance â€” `PASS` for Phase 02
- Second-corpus agent execution â€” `NOT_STARTED`

Detailed movement items may be cut with explicit rationale while keeping understand, examine, and stay alive genuinely represented.

### Behaviors 6â€“10 strong differentiators

Each is a **Strong differentiator â€” may be cut only with explicit rationale if time forces a trade-off.**

- Fresh-clone local/container command â€” `NOT_STARTED`
- Real keyless tests â€” `NOT_STARTED`
- Document prompt-injection defense â€” `NOT_STARTED`
- Concurrent distinct/same-corpus isolation â€” `NOT_STARTED`
- Stage timing/usage/cost basis â€” `NOT_STARTED`

### Additional prioritized engineering evidence

- Idempotent duplicate source ingestion â€” `PASS` for Phase 02 logical-source/content behavior
- Costly external-call ambiguous-outcome reconciliation â€” `NOT_STARTED`
- Cause/remedy dependency failures and resumability â€” `NOT_STARTED`
- Working fallback/retry/skip/escalation paths, without unproven fallback claims â€” `NOT_STARTED`
- Streamed bounded upload/SHA computation â€” `PASS` for Phase 02
- Phase 01 lint/format/typecheck/test/build/smoke/cleanup command proof â€” `PASS`

## Candidate execution constraint and project planning assumption

This schedule is not stated in the assignment PDF. Phases 01â€“10 total approximately 19.5 planned hours:

- Phase 01: 1.25h
- Phase 02: 2h
- Phase 03: 2.25h
- Phase 04: 1.5h
- Phase 05: 1.5h
- Phase 06: 1.75h
- Phase 07: 2h
- Phase 08: 2.25h
- Phase 09: 2.5h
- Phase 10: 2.5h

The remaining 4.5h is protected buffer for debugging, verification, evidence repair, and final auditâ€”not additional feature scope.

If cuts are required:

1. UI polish;
2. hosted deployment;
3. CSV;
4. multiple model providers;
5. elaborate observability UI;
6. sophisticated watcher implementation; and
7. extra format breadth.

Never cut the five explicit floor behaviors: visible path-changing stages, durable resume, item-level human review, machine-driven flow, or no-bluffing. Understand, examine, and stay alive must each remain represented at genuine minimum depth; detailed sub-features may be cut with explicit rationale. Behaviors 6â€“10 remain prioritized strong differentiators and may be cut only with explicit rationale if time forces a trade-off.

## Known limitations

- The repository contains verified Phase 01 foundation and Phase 02 deterministic
  ingestion/provenance capabilities only.
- Foundation and grounded-data architecture have executable evidence; all agent/review/incremental
  workflow architecture remains planned.
- CPython 3.13.14 is pinned and verified through uv/containers; the host's Python 3.14.4 remains
  installed but is not the project runtime.
- PDF/DOCX locator and citation round-trip fidelity is proven for declared Phase 02 primitives;
  complex layouts and OCR remain excluded.
- LangGraph PostgreSQL checkpoint/interrupt behavior is not yet proven.
- Same-corpus publication locking and idempotency are not yet designed at schema level.
- The incremental impact algorithm is not implemented or measured.
- MCP 2.0.0 install/runtime compatibility is verified; no MCP server, business operation, or
  protocol behavior is implemented or tested.
- No live model provider is selected.
- No deterministic fallback, retry, safe-skip, escalation, or ambiguous-provider-outcome reconciliation path is implemented or tested.
- No hosted deployment is promised.
- No internet-facing authentication, authorization, TLS termination, non-root container hardening,
  image signature enforcement, or production deployment is implemented.
- Remote CI attempt 1 failed in the backend and passed in the frontend; attempt 2 passed both jobs
  and all PR checks before PR #1 merged to `main`.
- SuperDocs familiarization and documentation prerequisites are complete by manual candidate confirmation; no repository artifact or runtime proof is claimed.

## Phase 01 entry criteria

Before Phase 01 implementation begins:

- [x] Candidate explicitly authorizes Phase 01.
- [x] Candidate confirms genuine SuperDocs use: authorized/non-confidential document, warm-up instruction, upload/open, targeted edit, Review Mode, human decision, export/download, and opened/verified export.
- [x] Candidate confirms reviewing relevant SuperDocs documentation, REST/API and MCP concepts, and the SuperDocs GitHub organization.
- [x] Phase 00 files have been reread and cross-checked against the approved Task 1 checklist.
- [x] README, TASK, PROGRESS, and architecture use `planned` versus `implemented` truthfully.
- [x] The real-human gate and no-self-approval rule are consistent in all files.
- [x] The PostgreSQL durability design does not prematurely require a transactional outbox.
- [x] The 19.5h plan plus 4.5h reserve and cut order are consistent in all files.
- [x] Data/security and Git/command rules are consistent in all files.
- [x] Behaviors 1â€“5 versus 6â€“10, movement cut policy, stack choice, MCP status, provenance, failure, crash-window, and incremental-proof terminology are consistent in all files.

Phase 01 execution requirements after authorization:

- Begin with repository and package compatibility inspection before choosing dependencies.
- Supply exact Phase 01 commands before requesting any manual prerequisite action.

**Historical entry result: PASS. Phase 01 implementation and verification completed.**

## Verification log

Phase 00 verification status: **PASS â€” authoritative assignment comparison completed; independent verifier findings incorporated at documentation level.**

Phase 01 verification status: **COMPLETE â€” local quality, real PostgreSQL/pgvector integration,
container startup/migration/readiness, rendered frontend, cleanup, remote backend/frontend CI, and
merge gates completed.**

The Phase 00 result remains documentation-level evidence. The Phase 01 result is executable
foundation evidence only and does not prove any Task 1 business behavior.

All four files were reread after the final correction pass. Incorporated findings include:

- behaviors 1â€“5 are the explicit non-cuttable floor; behaviors 6â€“10 are prioritized strong differentiators that may be cut only with explicit rationale;
- all three movements remain represented while detailed internal cuts are allowed with rationale;
- assignment-preferred, allowed-comparable, and chosen stack wording is separated, with MCP identified as our strongest chosen machine-interface shape;
- README records current assumptions and latency, cost, simplicity, and growth trade-offs without fabricated results;
- raw measurement data is planned to be committed to the repository;
- failure handling distinguishes proven fallback/retry/skip/escalation from honest durable resumable failure;
- source and deliverable-side provenance contracts are explicit;
- costly external-call ambiguous outcomes do not claim exactly-once behavior;
- incremental proof uses IDs, stages, operation keys, source versions, and hashes;
- human review requires a real human decision without adding RBAC as an assignment requirement;
- the 24-hour schedule is labeled a candidate execution constraint/project planning assumption; and
- SuperDocs confirmation logging is labeled our process choice rather than an assignment-mandated artifact.

Only the Phase 01 foundation capabilities listed in this record are implemented.

## Next safe step

Phase 01 is formally closed. Await explicit candidate authorization before beginning Phase 02 or
any Task 1 business logic.

## Phase 02 record â€” 2026-08-19

### Authorization and scope

The candidate explicitly authorized Phase 02 only: corpus, ingestion, immutable source versions,
parsers, exact provenance, and pgvector indexing. No Phase 03 agent workflow, LangGraph business
graph, model gateway, fact/contradiction reasoning, Examine rules, review workflow, durable resume,
MCP business operations, watcher, incremental update, or production deployment was implemented.

The branch was verified as `feat/phase-02-ingestion-provenance`. The pre-existing uncommitted
Phase 01 closure update in this file was inspected first and preserved. The agent executed no Git
write operation.

### Implemented schema and migration

Alembic revision `20260819_0002` follows `20260819_0001` and creates only:

- `corpora`;
- `sources`;
- `source_versions`; and
- `source_blocks`.

UUID primary keys, corpus-scoped composite foreign keys, source logical-name uniqueness,
source/hash version deduplication, version/block locator uniqueness, span checks, JSONB
configuration/metadata, `vector(64)`, corpus/version indexes, and an HNSW cosine vector index are
present. No future-phase business table was added.

Migration evidence against PostgreSQL 17/pgvector 0.8.1:

- `uv run alembic upgrade head` â€” PASS from Phase 01; reached `20260819_0002`;
- `uv run alembic downgrade 20260819_0001` â€” PASS;
- `uv run alembic upgrade head` â€” PASS after downgrade; and
- `uv run alembic current` â€” PASS, `20260819_0002 (head)`.

### Dependency decisions

Added and locked:

- `pypdf==6.16.1` â€” BSD-3-Clause, Python >=3.9, selected for text-based PDF parsing instead of
  AGPL PyMuPDF to avoid imposing AGPL server/application obligations;
- `python-docx==1.2.0` â€” MIT, Python >=3.9, release-tested on Python 3.13; and
- `python-multipart==0.0.32` â€” direct FastAPI upload dependency, Python >=3.10, already present
  transitively but made explicit.

`lxml==6.1.1` is the locked python-docx transitive dependency. No Markdown framework, OCR package,
document framework, external model package, or fixture-only PDF generator dependency was added.

### Storage and ingestion decisions

- Uploads are read in 1 MiB chunks, bounded by configurable `MAX_UPLOAD_BYTES` (10 MiB default),
  and SHA-256 is calculated during the streamed write.
- Staging filenames and durable keys are server-generated. Durable keys contain corpus/source UUID,
  SHA-256, version UUID, and server-selected extension; client names never construct paths.
- Path separators, drive separators, traversal components, extension/media mismatches, invalid
  UTF-8, unsupported declarations, and supported/common malformed cases exercised by tests fail
  with controlled cause/remedy output. Exhaustive malformed-input containment is not claimed.
- New files are atomically promoted before the metadata transaction commits. In-process failures
  attempt best-effort promoted/staged cleanup; crash and cancellation windows remain.
- Repeated bytes for the same logical source return the existing version after re-verifying stored
  bytes. Changed bytes create a distinct application-immutable version. The same bytes in another
  corpus use a distinct version and storage key.
- Compose mounts a named `source_files` volume at `/data/source-files`.

### Parser and locator decisions

- PDF: pypdf text extraction, `page[n]/block[n]`; no extractable text produces `textless_pdf` with
  an explicit text-based-PDF remedy and no OCR.
- DOCX: normal body paragraphs plus table-cell paragraphs in deterministic document order;
  `paragraph[n]` or `table[n]/row[n]/cell[n]/paragraph[n]`.
- Markdown: deterministic heading/list/paragraph blocks with
  `lines[start-end]/block[n]`.
- TXT: blank-line paragraph blocks with `lines[start-end]/block[n]`.

Normalization converts CRLF/CR to LF, applies Unicode NFC, replaces NBSP with a regular space,
removes trailing whitespace per line, and removes blank boundary lines while retaining interior
line structure. Stored block spans are `[0, len(normalized_text))`; citation spans are half-open
offsets inside the normalized block.

DOCX validation limits archive entries to 1,000, each expanded entry to 20 MiB, total expanded
content to 50 MiB, and compression ratio to 200:1.

### Exact provenance and tamper evidence

The resolver performs, in order:

1. source-version lookup scoped to corpus;
2. SHA-256 recalculation from stored application-immutable bytes;
3. citation SHA and declared-format comparison;
4. deterministic fresh parsing from the original stored bytes;
5. native-locator lookup in the fresh parse;
6. persisted-block integrity comparison;
7. a second source hash check after parsing;
8. half-open fresh normalized-span bounds validation; and
9. exact quote comparison against freshly derived text.

Real PostgreSQL integration tests prove:

- valid source-file â†’ ingestion â†’ immutable version/hash â†’ parser â†’ block â†’ citation â†’ resolver
  round-trip for PDF, DOCX, Markdown, and TXT â€” PASS;
- wrong source SHA â€” rejected with `source_sha_mismatch`;
- wrong native locator â€” rejected with `native_locator_mismatch`;
- out-of-range normalized span â€” rejected with `normalized_span_mismatch`;
- wrong exact quote â€” rejected with `exact_quote_mismatch`;
- persisted normalized-text tampering â€” rejected with `source_block_integrity_mismatch`;
- persisted native-locator tampering â€” rejected with `source_block_integrity_mismatch`;
- citation format disagreement â€” rejected with `source_format_mismatch`;
- source bytes changed after registration â€” rejected with `source_bytes_tampered`;
- missing version â€” rejected with `source_version_not_found`; and
- cross-corpus version/citation lookup â€” not found.

The container API smoke ingested the synthetic TXT decision log, persisted three blocks, and
validated an exact citation. Recorded smoke SHA-256:
`300c45a3506df6e7f531628ef29f780c28261e9b6c8aa26e109fec5c60cd5363`.

### Deterministic embeddings and pgvector

The keyless adapter uses case-folded tokens, SHA-256 feature hashing, signed accumulation into 64
dimensions, and L2 normalization. Tests prove same text gives the same vector, dimensions are fixed,
vectors persist in PostgreSQL, cosine retrieval works, format filters work, and returned blocks
remain corpus-scoped. Empty/non-token queries are rejected. This is lexical local/test retrieval,
not model-quality semantic embedding and never provenance.

### Synthetic corpora

`backend/scripts/generate_synthetic_corpora.py` reproducibly creates:

- Aurora Control Hub: charter PDF, status DOCX including a table, risk Markdown, decision TXT; and
- Harbor Ledger Modernization: delivery-plan PDF, quality DOCX including a table, risk Markdown,
  governance TXT.

The projects use different fictional people, dates, milestones, risks, and status. Aurora contains
a future production-readiness date conflict and unassigned security owner; Harbor contains separate
recovery-evidence and archive-approval gaps. All data is synthetic.

### API implemented

- `POST /corpora`
- `GET /corpora/{corpus_id}`
- `POST /corpora/{corpus_id}/sources`
- `GET /corpora/{corpus_id}/sources`
- `GET /corpora/{corpus_id}/sources/{source_id}`
- `GET /corpora/{corpus_id}/source-versions/{version_id}`
- `GET /corpora/{corpus_id}/source-versions/{version_id}/blocks`
- `POST /corpora/{corpus_id}/citations/validate`
- `POST /corpora/{corpus_id}/search`

Request/response models are typed. Domain errors expose safe code/detail/action payloads. Generic
request validation does not echo uploaded content or internal paths.

### Exact commands and final results

Dependency/fixture:

- `uv add "pypdf==6.16.1" "python-docx==1.2.0" "python-multipart==0.0.32"` â€” PASS;
- `uv lock` â€” PASS;
- `uv run python scripts/generate_synthetic_corpora.py` â€” PASS; and
- `uv sync --frozen --all-groups` â€” PASS.

Backend final gate:

- `uv run ruff format --check .` â€” PASS; 27 files formatted;
- `uv run ruff check .` â€” PASS;
- `uv run mypy src tests` â€” PASS; no issues in 21 source files;
- `uv run pytest --cov=app --cov-report=term-missing` with real PostgreSQL/pgvector â€” PASS;
  31 tests, 90.86% coverage; and
- `uv build` â€” PASS; sdist and wheel for `project_assurance_register-0.2.0`.

Focused integration:

- `uv run pytest -m integration` â€” PASS; 9 tests against PostgreSQL/pgvector;
- PDF/DOCX/Markdown/TXT citation parameterization â€” PASS;
- duplicate/changed/cross-corpus version behavior â€” PASS;
- all required provenance/tamper failures â€” PASS; and
- pgvector persistence, similarity, filter, and corpus isolation â€” PASS.

Frontend:

- `npm ci` â€” PASS; 235 packages, 0 reported vulnerabilities;
- initial `npm run format:check` â€” FAIL on 11 committed files due non-canonical working-tree
  line endings/format;
- `npm run format` â€” PASS;
- rerun `npm run format:check` â€” PASS;
- `npm run lint` â€” PASS;
- `npm run typecheck` â€” PASS;
- `npm test` â€” PASS; 1 file, 4 tests;
- `npm run build` â€” PASS.

Docker/runtime:

- `docker compose config --quiet` â€” PASS;
- `docker compose build` â€” PASS;
- `docker compose up --build --detach` â€” PASS;
- all three services healthy â€” PASS;
- `docker compose exec backend alembic current` â€” PASS, `20260819_0002 (head)`;
- `/health`, `/ready`, `/version`, frontend `/`, and proxy `/api/ready` â€” PASS;
- container TXT ingestion and exact citation validation â€” PASS;
- backend logs contained route/migration metadata but no source text, credentials, or stack traces;
- `docker compose down` â€” PASS; named data volumes retained; and
- `docker compose ps --all` â€” PASS; no project containers remained.

### Failures encountered and fixes

- A first combined shell command used `&&`, unsupported by the host PowerShell 5 parser. Commands
  were rerun with PowerShell-compatible explicit exit checks.
- Initial Ruff/mypy passes found import ordering, long lines, a pathlib/python-docx annotation, and
  test UploadFile typing. Applied focused corrections; final gates pass.
- The first real integration run had 8 failures because SQLAlchemy had no ORM relationship to order
  pending `SourceVersion` before pending `SourceBlock` inserts. Added an explicit version flush
  before block insertion; focused integration then passed 9/9 and full coverage passed 31/31.
- An initial parallel frontend gate was interrupted. The sequential rerun exposed 11
  non-canonical files; `npm run format` corrected them, root `.gitattributes` now enforces LF for
  text and marks DOCX/PDF fixtures binary, and the complete affected gate passed.
- The frontend files shown modified by Git were inspected with
  `git diff --ignore-space-at-eol -- frontend` plus word-diff and blob comparison. No semantic
  frontend Phase 02 changes exist; no Phase 02 frontend functionality was added. The new root
  `.gitattributes` establishes `* text=auto eol=lf`, `*.docx binary`, and `*.pdf binary`.
- One compound `docker compose down; ...` wrapper transiently reported `docker: unknown command:
  docker compose`. Running the exact commands separately succeeded; cleanup was verified empty.

### Security verification

- No key, credential, personal information, resume, employer/NDA data, or private source was added.
- Uploads are bounded and streamed; client filenames are metadata only; path traversal is rejected.
- Supported/common malformed PDF, DOCX, Markdown, TXT, and request cases exercised by tests return
  controlled cause/remedy output without source content. Exhaustive parser containment is deferred.
- Textless PDF is rejected honestly; no OCR fallback exists.
- DOCX ZIP expansion limits are enforced before python-docx parsing.
- Duplicate ingestion re-verifies stored bytes before returning the durable version.
- Cross-corpus metadata/provenance access is not found.
- Source text is treated as data and is not logged by application code.
- Runtime upload storage and build context exclusions cover `backend/var/`.
- Destructive integration cleanup requires the exact disposable database
  `project_assurance_test`, a different application database name, and
  `ALLOW_DESTRUCTIVE_TEST_DATABASE=true`.

### Phase 02 limitations

- `SourceVersion` and `SourceBlock` immutability is enforced by application/API behavior, not
  database UPDATE/DELETE triggers or restricted mutation roles.
- pypdf runs in-process under the upload bound; no separate parser sandbox or parse-time timeout.
- Supported/common malformed classes are controlled; exhaustive malformed-input containment is not
  proven.
- PDF text block granularity depends on deterministic pypdf extraction and is not layout/OCR
  reconstruction.
- DOCX headers, footers, drawings, comments, nested/merged table fidelity, and arbitrary embedded
  objects are not claimed.
- Markdown parsing is deliberately not a full renderer.
- Local mounted storage is not replicated object storage or malware scanning.
- A crash after file promotion but before database commit can leave an orphan; cancellation requires
  later reconciliation, and cleanup failures are best-effort.
- The HTTP request-size guard depends on usable Content-Length; absent/chunked requests rely on the
  authoritative streamed file-content bound.
- Deterministic embeddings are lexical test/local support, not semantic model embeddings.
- No internet-facing authentication/authorization or production hardening is claimed.
- Phase 03 and all later-phase functionality remains absent.

## Independent Phase 02 verification corrections â€” 2026-08-19

### Verifier result and scope

- Independent verifier: **PASS_WITH_CHANGES**
- Critical findings: **none**
- Current status: **PASS_WITH_CHANGES â€” corrections implemented locally, follow-up verifier
  pending**
- Phase 02 remote CI: **not run** because this branch has not been pushed.

Only the requested Phase 02 corrections were applied. Phase 03 and unrelated hardening remain
untouched.

### Corrected findings

- Destructive integration setup now fails before `TRUNCATE` unless `TEST_DATABASE_URL` names exactly
  `project_assurance_test`, differs from the application database name, and
  `ALLOW_DESTRUCTIVE_TEST_DATABASE=true`. Unit tests prove application DB denial, dedicated DB
  acceptance, missing-opt-in denial, and same-DB denial.
- `scripts/ensure_test_database.py` reproducibly creates the fixed disposable database from the
  application connection. README and CI use separate application/test URLs; the unsafe
  `TEST_DATABASE_URL = DATABASE_URL` instruction was removed.
- Citation validation now re-hashes source bytes, deterministically reparses the registered format,
  resolves the locator and quote from the fresh parse, compares persisted block content/metadata,
  and re-hashes after parsing. Database normalized-text/native-locator tampering now fails closed.
- Uploads now have an HTTP Content-Length request-size guard with 1 MiB multipart allowance plus the
  authoritative streamed file-content bound. Missing/chunked Content-Length relies on streaming.
- Added explicit DOCX table-cell citation round-trip, wrong citation format, mixed-format negative
  format filtering, block-type filtering, database-block tamper, request-bound, streamed-bound, and
  destructive-database guard tests.
- Documentation now distinguishes application-contract immutability from database enforcement,
  narrows malformed-input claims, separates mixed-format ingestion from Phase 03 classification,
  distinguishes second-corpus fixtures from second-corpus agent execution, and records active
  pgvector use.
- Storage crash-after-promotion orphaning, cancellation reconciliation, and best-effort cleanup are
  explicitly deferred limitations.

### Correction verification evidence

Backend from `backend/` with
`DATABASE_URL=.../project_assurance`,
`TEST_DATABASE_URL=.../project_assurance_test`, and
`ALLOW_DESTRUCTIVE_TEST_DATABASE=true`:

- `uv sync --frozen --all-groups` â€” PASS
- `uv run ruff format --check .` â€” PASS; 31 files already formatted
- `uv run ruff check .` â€” PASS
- Initial `uv run mypy src tests` â€” FAIL; one redundant cast after citation-format narrowing.
  Removed that cast.
- Final `uv run mypy src tests` â€” PASS; no issues in 24 source files
- Dedicated test-database Alembic `upgrade head` â†’ `downgrade 20260819_0001` â†’ `upgrade head` â†’
  `current` â€” PASS; `20260819_0002 (head)`
- `uv run pytest -m integration` â€” PASS; 12 passed, 26 deselected
- `uv run pytest --cov=app --cov-report=term-missing` â€” PASS; 38 passed, 91.45% coverage
- `uv build` â€” PASS; sdist and wheel for `project_assurance_register-0.2.0`
- `uv run pytest -m "not integration"` â€” PASS; 26 passed, 12 deselected

Frontend from `frontend/`:

- `npm ci` â€” PASS; 235 packages, 0 reported vulnerabilities
- `npm run format:check` â€” PASS
- `npm run lint` â€” PASS
- `npm run typecheck` â€” PASS
- initial `npm test` in parallel with the backend coverage run â€” FAIL; Vitest forks worker timeout,
  0 tests executed (host load, no frontend source change)
- sequential rerun `npm test` â€” PASS; 1 file, 4 tests
- `npm run build` â€” PASS

Docker from repository root:

- `docker compose config` â€” PASS
- `docker compose build` â€” PASS
- `docker compose up --build --detach` â€” PASS
- all three services healthy â€” PASS
- `/health` alive, `/ready` ready with pgvector 0.8.1, `/version` 0.2.0 Phase 02 â€” PASS
- frontend HTTP 200 and `/api/ready` 200 â€” PASS
- `docker compose exec backend alembic current` â€” PASS; `20260819_0002 (head)`
- a concurrent host-side integration rerun while the full stack was up failed with `MemoryError`;
  after `docker compose down` and db-only restart, `uv run pytest -m integration` â€” PASS; 12/12
- `docker compose down` â€” PASS
- `git diff --check` â€” PASS (CRLF/LF conversion warnings only; no whitespace errors)

### Phase 02 closure â€” 2026-08-19

- Implementation: **PASS**
- Local verification: **PASS**
- Independent verification: **GO** (PASS_WITH_CHANGES, zero critical findings; requested
  corrections implemented and re-verified locally)
- Merged to `main` as `d0c2f0f` (`Merge pull request #2 from Rahul9214/feat/phase-02-ingestion-provenance`)

Remote GitHub Actions: the workflow was accepted but externally blocked by account Actions
budget/scheduler state. Zero Phase 02 CI jobs materialized. Normal and force cancellation
returned GitHub HTTP 500. No Phase 02 code-related CI failure was observed. GitHub billing was
not treated as an implementation defect.

## Phase 03 record â€” 2026-08-19

### Scope completed

Implemented grounded Understand only:

- Alembic revision `20260819_0003` for `analysis_runs`, `facts`, `contradictions`, and
  `stage_events`, all corpus-scoped;
- taxonomy `software-project-assurance.v1` as configuration, not corpus-filename special-casing;
- model boundary: `MODEL_PROVIDER=deterministic` by default (keyless) plus one OpenAI-compatible
  live adapter selected by environment, with bounded timeout/retry and safe `ModelError`
  translation;
- LangGraph Understand workflow with real conditional skips:
  load â†’ retrieve â†’ classify â†’ extract â†’ validate provenance â†’ detect contradictions â†’ finalize;
- every supported fact bound to a Phase 02 citation that already passed exact provenance
  validation; retrieval IDs recorded but not treated as evidence;
- unknown inspection fields persisted as `support_status=unknown` /
  `normalized_value=INSUFFICIENT_EVIDENCE`;
- deterministic contradictions for the same category and subject key with incompatible values;
- document prompt-injection classified as `untrusted_instruction` and not followed as policy;
- inspectable analysis-run APIs; and
- application version `0.3.0`, phase `Phase 03 â€” Understand`.

Examine, item-level human review, durable kill/resume, MCP business operations, watching,
incremental updates, register publication, and production deployment were not implemented.

### Runtime and dependency decisions

- Default `MODEL_PROVIDER=deterministic` requires no API key. The live path is OpenAI-compatible
  chat completions via `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_BASE_URL`, timeout, and retries.
  No secrets were committed.
- httpx **0.28.1** moved from a development-only dependency to a main dependency for the live
  adapter. The deterministic adapter remains the executable-evidence path.
- LangGraph **1.2.11** now executes the Understand graph. The PostgreSQL checkpointer remains
  locked and unused. Human interrupt/resume is not implemented.
- Frontend was not modified. Version/phase text continues to come from the API.

### Cursor implementation verification â€” exact commands and final results

Inspection:

- `git branch --show-current` â€” `feat/phase-03-understand`
- Read-only `git status` / `git log` â€” Phase 02 is on `main` as `d0c2f0f`; Phase 03 work remains
  uncommitted on this branch
- Agent Git write operations: none

Backend final gate from `backend/` with
`DATABASE_URL=.../project_assurance`,
`TEST_DATABASE_URL=.../project_assurance_test`, and
`ALLOW_DESTRUCTIVE_TEST_DATABASE=true`:

- `uv sync --frozen --all-groups` â€” PASS; 91 packages
- `uv run ruff format --check .` â€” PASS
- `uv run ruff check .` â€” PASS
- `uv run mypy src tests` â€” PASS; 33 files
- dedicated test-database Alembic `upgrade head` â†’ `downgrade 20260819_0002` â†’ `upgrade head` â†’
  `current` â€” PASS; `20260819_0003 (head)`
- `uv run pytest -m integration` â€” PASS; 20 passed
- `uv run pytest --cov=app --cov-report=term-missing` â€” PASS; 61 passed, **92.76%** (gate 90%)
- `uv build` â€” PASS; sdist and wheel for `project_assurance_register-0.3.0`

Frontend from `frontend/` (no source changes):

- `npm ci` â€” PASS; 235 packages, 0 reported vulnerabilities
- `npm run format:check` â€” PASS
- `npm run lint` â€” PASS
- `npm run typecheck` â€” PASS
- initial `npm test` after the backend coverage run â€” FAIL; Vitest forks worker exited
  unexpectedly, 0 tests executed (host load, no frontend source change)
- sequential rerun `npx vitest run` â€” PASS; 1 file, 4 tests
- `npm run build` â€” PASS

Docker from repository root:

- `docker compose config` â€” PASS
- first combined `docker compose build` â€” FAIL; Docker credential helper
  `Not enough memory resources are available to complete this operation`
- sequential `docker compose build backend` then `docker compose build frontend` â€” PASS;
  backend image installed `project-assurance-register==0.3.0`
- cached rerun `docker compose build` â€” PASS
- `docker compose up --build --detach` â€” PASS; all three services healthy
- `/health` alive, `/ready` ready with pgvector 0.8.1, `/version` 0.3.0 Phase 03 â€” PASS
- frontend HTTP 200 and `/api/ready` 200 â€” PASS
- `docker compose exec backend alembic current` â€” PASS; `20260819_0003 (head)`
- Aurora ingest + `POST /analysis-runs` â€” PASS; status `completed`, findings `populated`,
  production-readiness contradiction `2026-10-30` vs `2026-11-14` with both citations,
  `budget_owner` unknown, injection classified `untrusted_instruction`, stage cost `$0` /
  `zero_deterministic`
- Harbor ingest + Understand â€” PASS; different people/dates (`Tomas Reed`,
  `legacy_retirement=2026-12-04`); `production_readiness` unknown; no Aurora leakage
- Harbor corpus + Aurora run id â€” HTTP 404 `analysis_run_not_found`
- empty corpus Understand â€” PASS; `findings_status=no_findings`, `no_findings=true`;
  retrieve/classify/extract skipped
- `docker compose down` â€” PASS
- `git diff --check` â€” PASS (CRLF/LF conversion warnings only; no whitespace errors)

### Understand evidence

- Classification uses taxonomy categories plus `untrusted_instruction`. Aurora Docker smoke
  classified 23 blocks including `untrusted_instruction`; Harbor did not.
- Supported facts require a validated Phase 02 citation. Tests reject malformed/unsupported
  model citations instead of promoting them.
- Aurora contradiction: `conflicting_dates` for `production_readiness` `2026-10-30` vs
  `2026-11-14`, both cited. Matching repeated `2026-10-30` values are not labeled a
  contradiction.
- Unknown inspection fields include `budget_owner` on both corpora, `legacy_retirement` on
  Aurora, and `production_readiness` on Harbor.
- Prompt-injection paragraph in Aurora `decision-log.txt` is classified not-relevant and does
  not produce a supported compliant/approval fact.
- Harbor is a different result set without Aurora names/dates and without corpus-filename
  branching.
- Stage events persist per executed/skipped stage with duration, model-operation count, and
  honest deterministic cost basis.

### Failures encountered

- PowerShell does not accept `&&`; commands were run sequentially.
- Docker Desktop was initially stopped; `docker compose up -d db` was used after a `--detach`
  / host-memory failure.
- Full `pytest -m integration` once hit host `MemoryError` during failure reporting; isolated
  reruns and the later official coverage run passed 61/61.
- Accidental overwrite of `understand_service.py` with test content was restored before the
  recorded gates.
- mypy required `cast` around LangGraph `ainvoke` and numeric conversions.
- Ruff E501 on the injection fixture string was wrapped across two source lines (still one TXT
  paragraph).
- Combined frontend `npm test` under load hit the same Vitest worker-exit class as Phase 02;
  sequential rerun passed.
- Combined `docker compose build` failed once on credential-helper OOM; sequential then cached
  combined build passed.

### Security verification

- No key, credential, personal information, resume, employer/NDA data, or private source was
  added. `.env.example` documents `OPENAI_API_KEY` as uncommitted.
- Model errors do not include the API key. Default tests/Compose use `MODEL_PROVIDER=deterministic`.
- Source text is wrapped as untrusted evidence and cannot redefine provenance or approve
  compliance.
- Cross-corpus analysis-run lookups return not found without traceback.
- Destructive integration cleanup still requires the exact disposable database
  `project_assurance_test`, a different application database name, and
  `ALLOW_DESTRUCTIVE_TEST_DATABASE=true`.

### Phase 03 limitations

- Understand runs synchronously in the API process. There is no worker queue, PostgreSQL
  checkpointer, or kill/resume.
- The live OpenAI-compatible adapter is implemented but is not the executable-evidence path.
- Taxonomy inspection fields and extraction patterns are generic; they are not a full
  rules-as-data Examine engine.
- Contradiction detection is deterministic same-key incompatibility, not model-judged
  semantic conflict.
- No-findings is an Understand-level empty/unknown result, not an Examine clean-corpus
  finding over versioned rules.
- Frontend remains the Phase 01 status shell.
- Database-level mutation-prevention triggers or restricted roles are still not implemented.
- No internet-facing authentication/authorization or production hardening is claimed.

Independent verification of Phase 03 found FAIL. Corrections and local re-verification follow.
Do not begin Phase 04 without separate explicit authorization. Candidate owns Git writes.

## Independent Phase 03 verification â€” FAIL â€” 2026-08-19

Independent verification: **FAIL**

Critical finding: a valid-but-unrelated citation could previously support a fabricated assertion.
Citation resolution proved only that quoted text exists. It did not prove that the proposed
category, subject_key, and normalized_value were supported by that quote.

Related gaps: retrieval IDs were recorded but classification used all loaded blocks; injection
exclusion depended on the adapter/model; skipped stages were not always persisted; fact/contradiction
integrity and logical-vs-attempt model counts were incomplete; the deterministic adapter was easy
to over-claim as general extraction.

This FAIL record is retained. Corrections follow; they do not replace this result.

### Root cause

`validate_provenance` persisted `SUPPORTED` after `Phase02Service.validate_citation` succeeded,
copying the model's category/subject/value unchanged. A live model could attach any valid citation
to an invented assertion.

### Exact fix

- Shared taxonomy `derive_assertions` / extraction rules drive both the deterministic adapter and
  `app.grounding.validate_assertion`.
- Pipeline: proposal â†’ citation resolver â†’ resolved quote â†’ assertion-to-evidence check â†’
  `SUPPORTED` only on match. Failures become rejected assertions with safe reason codes.
- Injection text is forced to `untrusted_instruction` after classify, excluded from extract, and
  rejected if still proposed.
- Classification uses retrieved candidate IDs; empty retrieval on a non-empty corpus records
  `retrieval_mode=fallback_full_corpus`.
- Migration `20260819_0003` adds fact/source-block corpus FK, supported-provenance check,
  contradiction run/corpus FKs, canonical pair uniqueness, `skip_reason`, and `model_attempt_count`.
- Canonical stages are always recorded; skipped stages have zero model operations and zero cost.

### Local re-verification of FAIL corrections â€” PASS â€” 2026-08-19

Inspection: `feat/phase-03-understand`; no agent Git writes.

Backend from `backend/` with `DATABASE_URL=.../project_assurance`,
`TEST_DATABASE_URL=.../project_assurance_test`, `ALLOW_DESTRUCTIVE_TEST_DATABASE=true`:

- `uv run ruff format --check .` / `uv run ruff check .` / `uv run mypy src tests` â€” PASS
- test-database Alembic: stamp `20260819_0002` after leftover 0003 objects, then
  `0002 â†’ 0003 â†’ 0002 â†’ 0003`, `current = 20260819_0003 (head)` â€” PASS
- `uv run pytest -m integration` â€” PASS; 25 passed
- `uv run pytest --cov=app --cov-report=term-missing` â€” PASS; 71 passed, **92.93%** (gate 90%)
- `uv build` â€” PASS; sdist and wheel for `project_assurance_register-0.3.0`

Frontend from `frontend/` (no source changes for this correction):

- `npm run format:check` / `lint` / `typecheck` â€” PASS
- `npm test` â€” PASS; 4 tests
- `npm run build` â€” PASS via `cmd /c` after a paging-file failure; `dist/` produced

Docker from repository root:

- `docker compose config` â€” PASS
- sequential `docker compose build backend` then `docker compose build frontend` â€” PASS
  (combined frontend build previously crashed Docker/Go with `signal 0xc0000005` / paging file)
- `docker compose up --build --detach` â€” PASS; database, backend, and frontend healthy
- `/health` alive, `/ready` ready with pgvector 0.8.1, `/version` 0.3.0 Phase 03 â€” PASS
- frontend HTTP 200 and `/api/ready` 200 â€” PASS
- first `docker compose exec backend alembic current` â€” `20260819_0003 (head)` while the persistent
  volume still had the **old** 0003 columns (same revision ID edited in place)
- recovery: drop leftover `analysis_runs`/`facts`/`contradictions`/`stage_events`,
  `alembic stamp 20260819_0002`, `alembic upgrade head` â€” PASS; `model_attempt_count`,
  `skip_reason`, `ck_facts_supported_requires_provenance`, `uq_source_blocks_id_corpus`,
  `fk_facts_source_block_corpus` present; `current = 20260819_0003 (head)`
- Aurora Understand on already-ingested corpus â€” PASS; `completed`/`populated`;
  `production_readiness` `2026-10-30` vs `2026-11-14` `conflicting_dates`; `Elena Marlow`;
  `budget_owner` unknown; injection `untrusted_instruction` / not relevant; no supported
  compliant/approval fact; all seven canonical stages; `retrieval_mode=retrieved`; cost `$0`
- Harbor Understand â€” PASS; `Tomas Reed`, `legacy_retirement=2026-12-04`; no Aurora leakage;
  `production_readiness` unknown
- Harbor corpus + Aurora run id â€” HTTP 404 `analysis_run_not_found`
- empty corpus Understand â€” PASS; `findings_status=no_findings`; skipped load/retrieve/classify/
  extract with `skip_reason=empty_corpus` and zero ops/cost
- blank weather TXT Understand â€” PASS; `no_findings`; extract skipped `no_relevant_blocks`
- `docker compose down` â€” PASS; named volumes retained
- `docker compose ps --all` â€” PASS; no project containers
- `git diff --check` â€” PASS (CRLF/LF conversion warnings only; no whitespace errors)

### Failures encountered during local re-verification

- PowerShell does not accept `&&`; host CLR `80004005` and paging-file OOM required `cmd /c`
  and sequential Docker builds.
- Combined `uv run python` Docker smoke hung without reaching the API; curl against already
  ingested corpora was used instead.
- Persistent Compose volume remained on the pre-correction 0003 schema because the revision ID
  was not bumped. `alembic current` reported head while `model_attempt_count` was missing.
  Stamp-to-0002 plus drop leftover Phase 03 tables, then upgrade, restored the new schema
  without re-ingesting PDFs.

## Independent Phase 03 follow-up â€” NO-GO â€” 2026-08-19

Independent follow-up: **NO-GO**

The earlier grounding FAIL and its local re-verification remain. This follow-up does not replace
that history and is not independent verification PASS.

Blockers:

- Failed retry paths recorded `model_attempt_count=1` in the graph instead of the provider attempts
  actually made. Successful retry accounting was already correct.
- Grounding trimmed and case-folded values, but contradiction grouping only case-folded them, so
  equivalent grounded values such as `"green"` and `" green "` could be treated as contradictory.

Fixes:

- `ModelError.attempt_count` carries the actual provider attempts; the graph records that value
  instead of hardcoding 1. `model_operation_count` remains 1 for one logical operation.
- Shared `comparison_key` / `values_equivalent` in `taxonomy.py` (strip + casefold) used for
  grounding, contradiction grouping, and repeated-value deduplication. Dates are not rewritten.
- README documents skip reasons: `empty_corpus`, `no_relevant_blocks`,
  `retrieval_empty_fallback`, `prior_stage_failed`.

Local backend re-verification of this follow-up (not independent PASS):

- `uv run ruff format --check .` / `uv run ruff check .` / `uv run mypy src tests` â€” PASS
- `uv run pytest tests/test_model_boundary.py tests/test_grounding.py tests/test_understand_integration.py`
  â€” PASS; 36 passed
- `uv run pytest --cov=app --cov-report=term-missing` â€” PASS; 76 passed, **93.03%** (gate 90%)
- `git diff --check` â€” PASS (CRLF/LF conversion warnings only; no whitespace errors)
- Frontend/Docker full-stack gates were not rerun; these corrections do not touch those areas.

## Independent Phase 03 final follow-up â€” GO â€” 2026-08-19

Independent final follow-up: **GO**

The original independent FAIL (grounding) and the subsequent correction NO-GO remain historical
record. They are not erased. After the later fixes, independent final follow-up verified Phase 03
as GO.

- Phase 03 committed
- PR #3 merged to `main`
- merge commit `ceb2bf0`
- remote CI: PASS (2 successful checks)

This GO is the current Phase 03 verification status. It does not authorize Phase 05.

## Phase 04 record â€” 2026-08-19

### Scope completed

Implemented grounded Examine only:

- Alembic revision `20260819_0004` for `examination_runs`, `findings`, and
  `examination_stage_events`, all corpus-scoped, without editing migration `20260819_0003`;
- ruleset `software-project-assurance.v1` as nine named-evaluator rules (not corpus-name
  special-casing and not a generic expression engine);
- LangGraph Examine workflow with real skips: load understanding â†’ select rules â†’ evaluate
  rules â†’ validate evidence â†’ summarize findings â†’ finalize;
- findings consume only Phase 03 supported facts and grounded contradictions; retrieval hits,
  rejected assertions, and raw source text cannot satisfy a rule;
- outcomes `pass` / `fail` / `warning` / `unknown`; missing evidence is never converted to pass;
- inspectable examination-run APIs; and
- application version `0.4.0`, phase `Phase 04 â€” Examine`.

Human review, durable kill/resume, MCP business operations, watching, incremental updates,
register publication, and production deployment were not implemented.

### Cursor implementation verification â€” exact commands and final results

Inspection: `feat/phase-04-examine`; agent Git write operations: none.

Backend from `backend/` with `DATABASE_URL=.../project_assurance`,
`TEST_DATABASE_URL=.../project_assurance_test`, `ALLOW_DESTRUCTIVE_TEST_DATABASE=true`:

- `uv sync --frozen --all-groups` â€” PASS
- `uv run ruff format --check .` â€” PASS after `uv run ruff format .`
- `uv run ruff check .` â€” PASS
- `uv run mypy src tests` â€” PASS; 41 source files
- dedicated test-database Alembic `upgrade head` â†’ `downgrade 20260819_0003` â†’ `upgrade head` â†’
  `current` â€” PASS; `20260819_0004 (head)`
- `uv run pytest -m integration` â€” PASS; 33 passed
- `uv run pytest --cov=app --cov-report=term-missing` â€” PASS; 98 passed, **91.96%** (gate 90%)
- `uv build` â€” PASS; sdist and wheel for `project_assurance_register-0.4.0`

Frontend from `frontend/` (no source changes):

- `npm ci` â€” PASS; 235 packages, 0 reported vulnerabilities
- `npm run format:check` / `lint` / `typecheck` â€” PASS
- `npm test` â€” PASS; 1 file, 4 tests
- `npm run build` â€” PASS

Docker from repository root:

- `docker compose config --quiet` â€” PASS
- sequential `docker compose build backend` then `docker compose build frontend` â€” PASS;
  backend image installed `project-assurance-register==0.4.0`
- `docker compose up --build --detach` â€” PASS; database, backend, and frontend healthy
- `/health` alive, `/ready` ready with pgvector 0.8.1, `/version` 0.4.0 Phase 04 â€” PASS
- frontend HTTP 200 and `/api/ready` 200 â€” PASS
- `docker compose exec backend alembic current` â€” PASS; `20260819_0004 (head)`
- first container ingest attempt used an incomplete file walk and hid curl failures; rerun used
  fixture manifests
- Aurora Understand + Examine â€” PASS; `completed`/`populated`; findings
  `spa.milestone.production-readiness=fail` (2026-10-30 vs 2026-11-14, both citations),
  `spa.contradiction.open=fail`, `spa.status.clarity=warning` (amber),
  `spa.ownership.sponsor=pass`, `spa.ownership.budget=unknown`,
  `spa.ownership.security-signoff=fail` (unassigned); counts pass=4 fail=3 warn=1 unknown=1;
  stage cost `$0`
- Harbor Understand + Examine â€” PASS; different profile with no FAIL/WARNING:
  `spa.contradiction.open=pass`, `spa.status.clarity=pass` (green),
  `spa.milestone.production-readiness=unknown`, `spa.dependency.evidence=unknown`;
  counts pass=5 fail=0 warn=0 unknown=4; no Aurora names/dates
- Harbor corpus + Aurora examination id â€” HTTP 404 `examination_run_not_found`
- empty corpus Examine â€” PASS; `findings_status=no_findings`, evaluated_rule_count=0
- `docker compose down` â€” PASS; named volumes retained
- `docker compose ps --all` â€” PASS; no project containers

### Examine evidence

- Ruleset IDs/version are stable and configuration-driven. Changing `value_outcomes` for amber
  status changes WARNING to FAIL without rewriting the evaluator.
- PASS requires supported facts plus copied Phase 02 citations.
- FAIL for production-readiness consumes the Phase 03 contradiction record and both fact citations.
- WARNING is grounded amber status.
- UNKNOWN is missing required supported evidence and is never converted to PASS.
- Unrelated facts, unsupported/rejected facts, and retrieval-only context cannot satisfy a rule.
- Injection text cannot add or override a rule.
- Harbor executes the same ruleset without corpus-name branching and yields a different profile.

### Failures encountered

- PowerShell 5 does not accept `&&` or `Invoke-WebRequest -SkipHttpErrorCheck`.
- Combined first Docker smoke ingested files without the fixture manifest and discarded curl
  output, producing false no-findings. Manifest-based ingest then produced the expected Aurora
  mix and Harbor profile.
- mypy required typed helpers around LangGraph Examine state payloads.

### Security verification

- No key, credential, personal information, resume, employer/NDA data, or private source was
  added.
- Cross-corpus examination lookups return not found without traceback.
- Prompt-injection source text cannot define or override examination rules.
- Destructive integration cleanup still requires the exact disposable database
  `project_assurance_test`, a different application database name, and
  `ALLOW_DESTRUCTIVE_TEST_DATABASE=true`.

### Phase 04 limitations

- Examine runs synchronously in the API process. There is no worker queue, PostgreSQL
  checkpointer, or kill/resume.
- Rules are centrally versioned Python data plus named evaluators. There is no user-upload rule
  editor or generic expression engine.
- Register-state examination is not implemented because no published register exists yet.
- Frontend remains the Phase 01 status shell.
- Database-level mutation-prevention triggers or restricted roles are still not implemented.
- No internet-facing authentication/authorization or production hardening is claimed.

Independent verification of Phase 04 has not been requested. Do not begin Phase 05 without
separate explicit authorization. Candidate owns Git writes.

## Independent Phase 04 verification â€” FAIL / NO-GO â€” 2026-08-19

Independent verification: **FAIL / NO-GO**

Local initial implementation PASS remains. This independent result is not PASS.

Verified blockers (correction in progress; do not begin Phase 05):

- Subject-specific rules matched `subject_key` without requiring the rule's category, so an
  unrelated SUPPORTED fact could satisfy production-readiness.
- A contradiction could satisfy a subject/category rule when only one grounded side matched.
- `spa.contradiction.open` treated zero contradictions as PASS and attached arbitrary supported
  facts as evidence, violating silence-is-not-compliance.
- The same Aurora production-readiness contradiction was counted by both the specific rule and
  the generic open-contradiction rule.
- Finding `fact_ids` / `contradiction_ids` / `citations` were unconstrained JSON, so random UUIDs
  could persist as evidence. The weak CHECK test failed on blank `rule_id`, not the evidence
  reference.
- UNKNOWN findings were not prevented from carrying evidence by a meaningful contract.
- Examine compared copied citation dictionaries instead of rerunning Phase 02 exact provenance
  and Phase 03 assertion grounding.
- `rule_evaluation_count=9` was recorded on stages that do not evaluate rules.
- Phase 03 current status still described independent verification as FAIL/NO-GO after the later
  GO, PR #3 merge `ceb2bf0`, and remote CI PASS.

## Phase 04 correction pass â€” in progress â€” 2026-08-19

Correction is in progress against the FAIL / NO-GO blockers above. Uncommitted migration
`20260819_0004` was edited in place. Alembic does not reapply the same revision against a
database already stamped at the old 0004 JSON-evidence schema.

Local recovery used on the disposable test database and the local Compose application database
(Phase 04 examination objects only; corpora/facts retained on the application database):

1. Drop leftover Phase 04 objects: `finding_fact_evidence`, `finding_contradiction_evidence`,
   `examination_stage_events`, `findings`, `examination_runs`, and
   `uq_contradictions_id_run_corpus` if present.
2. `alembic stamp 20260819_0003`
3. `alembic upgrade head` to the corrected `20260819_0004`

Do not run that recovery against non-test data silently.

### Local correction verification

Inspection: `feat/phase-04-examine`; agent Git write operations: none. Frontend source was not
changed and frontend gates were not rerun.

Backend from `backend/` with `DATABASE_URL=.../project_assurance`,
`TEST_DATABASE_URL=.../project_assurance_test`, `ALLOW_DESTRUCTIVE_TEST_DATABASE=true`:

- focused `uv run pytest tests/test_ruleset.py tests/test_examine_integration.py tests/test_examine_api.py tests/test_grounding.py`
  â€” PASS; 42 passed
- `uv run ruff format --check .` â€” PASS
- `uv run ruff check .` â€” PASS
- `uv run mypy src tests` â€” PASS; 41 source files
- test-database recovery then Alembic `0003 â†’ 0004 â†’ 0003 â†’ 0004`,
  `current = 20260819_0004 (head)` â€” PASS
- `uv run pytest -m integration` â€” PASS; 38 passed
- `uv run pytest --cov=app --cov-report=term-missing` â€” PASS; 112 passed, **91.80%** (gate 90%)
- `uv build` â€” PASS; sdist and wheel for `project_assurance_register-0.4.0`

Docker from repository root:

- `docker compose config --quiet` â€” PASS
- `docker compose build backend` â€” PASS; image installed `project-assurance-register==0.4.0`
- frontend image reused; no frontend rebuild
- `docker compose up --detach` â€” PASS; database, backend, and frontend healthy
- `/health` alive, `/ready` ready with pgvector 0.8.1, `/version` 0.4.0 Phase 04 â€” PASS
- frontend HTTP 200 â€” PASS
- `docker compose exec backend alembic current` â€” PASS; `20260819_0004 (head)`
- Aurora Understand + Examine â€” PASS; `spa.milestone.production-readiness=fail` with both
  citations; `spa.contradiction.open=pass` via process attestation with no facts; counts
  pass=5 fail=2 warn=1 unknown=1 (the Aurora date conflict is not counted twice)
- Harbor Understand + Examine â€” PASS; `spa.contradiction.open=pass` with empty fact evidence;
  `production_readiness` unknown; no Aurora leakage; counts pass=5 fail=0 warn=0 unknown=4
- Harbor corpus + Aurora examination id â€” HTTP 404 `examination_run_not_found`
- empty corpus Examine â€” PASS; `findings_status=no_findings`
- `docker compose down` â€” PASS; named volumes retained
- `docker compose ps --all` â€” PASS; no project containers

Independent re-verification of this correction is not complete. Do not begin Phase 05.

## Phase 05 record — 2026-08-19

### Scope completed

Implemented the explicit human-review gate over Phase 04 Examine findings only:

- Alembic revision `20260819_0005` for `review_sessions`, `review_items`, and `review_decisions`,
  all corpus-scoped, without editing migration `20260819_0004`;
- one review session per completed examination run, idempotent create, status
  `waiting_for_review` until an explicit complete call;
- one review item per finding; FAIL/WARNING/UNKNOWN are review-required; PASS items are visible
  and optional;
- explicit item-level `approve`, `reject`, and `edit`; append-only decision history; latest valid
  state is current;
- EDIT requires non-blank reviewer-authored text, retains the original proposal and grounded
  citations, and does not mutate Phase 03/04 records;
- completion blocked while required items remain pending;
- inspectable review APIs plus a minimal React review panel; and
- application version `0.5.0`, phase `Phase 05 — Human Review`.

Register publication, durable kill/resume, MCP business operations, watching, incremental updates,
and production deployment were not implemented.

### Cursor implementation verification — exact commands and final results

Inspection: `feat/phase-05-human-review`; agent Git write operations: none.

Backend from `backend/` with `DATABASE_URL=.../project_assurance`,
`TEST_DATABASE_URL=.../project_assurance_test`, `ALLOW_DESTRUCTIVE_TEST_DATABASE=true`:

- `uv sync --frozen --all-groups` — PASS
- `uv run ruff format --check .` — PASS
- `uv run ruff check .` — PASS
- `uv run mypy src tests` — PASS; 44 source files
- dedicated test-database Alembic `0004 → 0005 → 0004 → 0005`,
  `current = 20260819_0005 (head)` — PASS
- `uv run pytest -m integration` — PASS; 45 passed
- `uv run pytest --cov=app --cov-report=term-missing` — PASS; 120 passed, **91.99%** (gate 90%)
- `uv build` — PASS; sdist and wheel for `project_assurance_register-0.5.0`

Frontend from `frontend/`:

- `npm run format:check` / `lint` / `typecheck` — PASS
- `npm test` — PASS; 2 files, 7 tests
- `npm run build` — PASS

Docker from repository root:

- `docker compose config --quiet` — PASS
- sequential `docker compose build backend` then `docker compose build frontend` — PASS;
  backend image installed `project-assurance-register==0.5.0`
- first `docker compose up --detach` started; later daemon reconnect after Docker Desktop was
  stopped; `Start-Process` Docker Desktop then `docker compose up --detach` — PASS; db/backend/
  frontend healthy
- `/health` alive, `/ready` ready with pgvector 0.8.1, `/version` 0.5.0 Phase 05 — PASS
- frontend HTTP 200 and `/api/ready` HTTP 200 — PASS
- `docker compose exec backend alembic current` — PASS; `20260819_0005 (head)`
- Aurora ingest → Understand → Examine → review session create 201 / idempotent 200 —
  required FAIL/WARNING/UNKNOWN: `spa.milestone.production-readiness=fail` (2 citations),
  `spa.ownership.security-signoff=fail`, `spa.status.clarity=warning`,
  `spa.ownership.budget=unknown`; pending complete → HTTP 400 `review_session_incomplete`
- Aurora UI: complete disabled while pending; explicit reject / reviewer-authored edit /
  two approves; complete enabled at pending=0; session `completed` with
  approved=2 rejected=1 edited=1; edit banner states the text is not system-grounded
- Harbor ingest → Understand → Examine → review: required UNKNOWN profile
  (`dependency.evidence`, `production-readiness`, `budget`, `security-signoff`); no Aurora
  names; API approve/reject/edit; mid-complete 400 `review_session_incomplete`; complete
  after remaining required approves → `completed` approved=2 rejected=1 edited=1
- Harbor corpus + Aurora session/exam → HTTP 404 `review_session_not_found` /
  `examination_run_not_found`; Harbor item under Aurora session → 404 `review_item_not_found`

First session create failed because SQLAlchemy inserted `review_items` before `review_sessions`.
Flushing the session row before items fixed the FK order. Focused integration then passed.

### Failures encountered

- PowerShell 5 does not accept `&&`.
- Combined frontend `npm run format` hit JavaScript heap OOM; formatting `src/` with a larger
  heap then passed.
- Review session create hit `fk_review_items_session_corpus_examination_analysis` until the
  parent session was flushed before item insert.
- Frontend edit test matched both the textarea label and the stored edit banner; the assertion
  was narrowed to the reviewer-authored disclaimer.
- Docker Desktop was stopped between image build and runtime smoke
  (`npipe:////./pipe/dockerDesktopLinuxEngine`); starting Docker Desktop restored the daemon
  and the Compose stack came up healthy without rebuilding.

### Security verification

- No key, credential, personal information, resume, employer/NDA data, or private source was
  added.
- Cross-corpus session/item lookups and wrong-session item decisions return not found without
  traceback.
- Reviewer-authored edits are stored as data and marked not system-grounded.
- Phase 03/04 finding records are not mutated by review decisions.
- Destructive integration cleanup still requires the exact disposable database
  `project_assurance_test`, a different application database name, and
  `ALLOW_DESTRUCTIVE_TEST_DATABASE=true`.

### Phase 05 limitations

- Review does not publish a register version or apply approved items to a durable register.
- There is no RBAC or proposer/reviewer identity separation; actor/source are audit fields.
- Review runs in the API process. There is no worker queue, PostgreSQL checkpointer, or
  kill/resume.
- MCP is not implemented. Machine-driven review uses the HTTP API.
- Frontend is a minimal review panel, not a polished dashboard.
- Database-level mutation-prevention triggers or restricted roles are still not implemented.
- No internet-facing authentication/authorization or production hardening is claimed.

Independent verification of the initial Phase 05 implementation returned FAIL / NO-GO.

Verified blockers:

- review mutations were not serialized with row locks
- completion could trust stale cached `pending_count`
- decision versus completion races were undefined
- same-item decision history could record inaccurate `previous_status`
- edit acknowledgement existed in the UI only and was not enforced or persisted by the API

### Phase 05 correction — 2026-08-19

Corrected only those blockers:

- decision transactions `SELECT` the review session `FOR UPDATE`, re-check corpus/session/
  `waiting_for_review`/proposal version, then lock the target item, derive `previous_status`
  from the locked row, append the decision, and recompute counts from item rows before commit
- completion transactions lock the session, recompute counts from item rows, and do not use
  cached `pending_count` as the completion decision
- `reviewer_authored_acknowledged` is required and persisted for EDIT; approve/reject cannot
  smuggle edited content
- focused concurrency, acknowledgement, and production-readiness citation tests were added
- uncommitted migration `20260819_0005` was updated in place for the acknowledgement column

Correction verification:

- backend `ruff format --check`, `ruff check`, `mypy src tests` — PASS
- test-database Alembic `0004 → 0005 → 0004 → 0005`, `current = 20260819_0005 (head)` — PASS
- focused `pytest tests/test_review_integration.py tests/test_review_api.py` — PASS; 14 passed
- `pytest -m integration` — PASS; 51 passed (backend/frontend Compose services stopped during this run to avoid host MemoryError)
- `pytest --cov=app --cov-report=term-missing` — PASS; 126 passed, **92.42%** (gate 90%)
- `uv build` — PASS; `project_assurance_register-0.5.0`
- frontend `format:check` / `lint` / `typecheck` / `npm test` (7 passed) / `build` — PASS
- Docker rebuild `project-assurance-register==0.5.0`; `/health` `/ready` `/version` 0.5.0 Phase 05; alembic `20260819_0005 (head)`
- Aurora review: production-readiness exposes both citations; pending complete 400 `review_session_incomplete`; approve/reject smuggle 400 `edit_content_not_allowed`; edit without acknowledgement 400; edit with acknowledgement persisted; complete approved=2 rejected=1 edited=1; later decision 400 `review_session_already_completed`
- Harbor session create 201; Harbor corpus + Aurora session 404 `review_session_not_found`
- frontend HTTP 200 and `/api/ready` 200

Independent re-verification of this correction is not complete. Do not begin Phase 06 without
separate explicit authorization. Candidate owns Git writes.

## Phase 06 record — 2026-08-20

### Scope completed

Implemented durable execution only. No publication, watcher, MCP, or incremental processing.

- `WorkflowRun` / `DurableOperation` / `WorkflowRunEvent` with corpus FKs, status checks, unique
  operation keys, and unique checkpoint thread ids
- Alembic `20260819_0006` after committed `20260819_0005`, including LangGraph checkpoint tables
- Outer LangGraph graph: Understand → Examine → open review → `interrupt()` human gate → finalize
- `AsyncPostgresSaver` with `durability="sync"`; thread id equals workflow run id
- Costly-call ledger: intent before provider call, result after, `ambiguous` crash window
- Deterministic keyless proof of one logical operation vs provider attempts
- Real subprocess kill after Understand barrier, new process resumes the same run
- Same-corpus concurrent runs stay isolated; advisory locks serialize run claim and operation keys
- Typed corpus-scoped start/inspect/resume/events API
- Resume of `waiting_for_review` does not auto-approve or create decisions
- Failed model calls persist safe cause/remedy; resume retries without duplicating completed stages
- Application version `0.6.0`, phase `Phase 06 — Durable Resume`

TASK.md Phase 06 one-liner mentioned publication. Publication is explicitly deferred: the durable
contract stops at the human-review gate. Concurrent publication remains the Behavior 9 remainder.

### Cursor implementation verification — exact commands and final results

Inspection: `feat/phase-06-durable-resume`; agent Git write operations: none.

Backend from `backend/` with `DATABASE_URL=.../project_assurance`,
`TEST_DATABASE_URL=.../project_assurance_test`, `ALLOW_DESTRUCTIVE_TEST_DATABASE=true`
(Compose db only; backend/frontend were stopped during pytest for host memory):

- `uv sync --frozen --all-groups` — PASS
- `uv run ruff format --check .` — PASS
- `uv run ruff check .` — PASS
- `uv run mypy src tests` — PASS; 53 source files
- dedicated test-database Alembic `0005 → 0006 → 0005 → 0006`,
  `current = 20260819_0006 (head)` — PASS
- `uv run pytest -m integration` — PASS; 57 passed, 80 deselected in 99.43s
- `uv run pytest --cov=app --cov-report=term-missing` — PASS; 137 passed, **92.28%** (gate 90%)
- `uv build` — PASS; sdist and wheel for `project_assurance_register-0.6.0`
- dedicated real process-kill command:
  `uv run pytest tests/test_process_kill_resume.py::test_real_process_kill_then_new_process_resumes_same_run`
  — PASS in 13.13s

Process-kill contract proven by that test:

1. `scripts/durable_workflow_worker.py start --hold-after understand` in process A
2. barrier file written after the Understand checkpoint
3. PostgreSQL checkpoint row and completed ledger ops exist
4. process A is forcibly killed (`Popen.kill()`)
5. process B: `scripts/durable_workflow_worker.py resume` for the same run/thread
6. Understand `stage_completed` remains count 1; logical operation count unchanged
7. status `waiting_for_review`; zero `ReviewDecision` rows

Frontend from `frontend/`:

- `npm ci` — PASS
- `npm run format:check` / `lint` / `typecheck` — PASS
- `npm test` — PASS; 2 files, 7 tests
- `npm run build` — PASS

Docker from repository root:

- `docker compose config --quiet` — PASS
- `docker compose build backend` — PASS; image installed `project-assurance-register==0.6.0`
  including `psycopg-binary==3.3.4`
- `docker compose up --build --detach` — PASS; db/backend/frontend healthy
- `/health` alive, `/ready` ready with pgvector 0.8.1, `/version` 0.6.0 Phase 06 — PASS
- frontend HTTP 200 and `/api/ready` HTTP 200 — PASS
- `docker compose exec backend alembic current` — PASS; `20260819_0006 (head)`
- Aurora ingest → `POST /workflow-runs` → `waiting_for_review`; thread id equals run id;
  events include `stage_completed` and `waiting_for_review`; 24 checkpoint rows; classify/extract
  ledger rows `completed` with logical_operation_count=1
- Harbor corpus + Aurora run → HTTP 404 `workflow_run_not_found`
- `docker compose restart backend` then GET run still `waiting_for_review`; POST resume still
  `waiting_for_review`; review session `pending_count=4`, `approved_count=0`

### Failures encountered

- PowerShell 5 does not accept `&&` or `Join-String`.
- Windows: psycopg async cannot use ProactorEventLoop, while SelectorEventLoop cannot
  `create_subprocess_exec`. Fix: `WindowsSelectorEventLoopPolicy` for the app/checkpointer, and
  threaded `subprocess.Popen`/`run` in the kill/resume test.
- `pg_advisory_lock` cannot share the ORM session connection; a dedicated engine connection holds
  the lock.
- LangGraph `Command(goto=failed_node)` does not re-run a node that left ERROR pending writes
  because resume marks those channel versions already-seen. Failed resume now deletes that
  thread's checkpoints and restarts the same thread; completed stages skip from durable rows.
- Understand inner graph swallows `ModelError` into a failed analysis run; the outer graph then
  marks the workflow failed and raises so Examine does not run on a failed understanding.
- Host memory pressure: backend/frontend Compose services were stopped during pytest.

### Security verification

- No key, credential, personal information, resume, employer/NDA data, or private source was
  added.
- Cross-corpus workflow-run lookups return not found without traceback.
- API error payloads use code/detail/action only.
- Review resume does not create decisions or approve items.
- Destructive integration cleanup still requires the exact disposable database
  `project_assurance_test`, a different application database name, and
  `ALLOW_DESTRUCTIVE_TEST_DATABASE=true`.

### Phase 06 limitations

- Workflow `completed` means the durable graph finished after explicit Phase 05 review completion.
  It is not a published register version.
- No Redis/Celery/Kafka/worker fleet. The API process runs the graph; the subprocess worker is
  for kill/resume proof.
- Inner Understand/Examine graphs are not separately checkpointed.
- Live providers are not guaranteed exactly-once; crash-after-response is `ambiguous`.
- Deterministic mode may reconcile `ambiguous`; live mode requires an explicit retry policy.
- Same-corpus concurrent runs are isolated; concurrent publication is not implemented.
- MCP, watching, incremental processing, and production hardening are not implemented.
- Frontend is a status/review shell, not a run-operations console.

### Independent verification — FAIL / NO-GO

Independent verification of the initial Phase 06 implementation returned FAIL / NO-GO. Blockers
recorded:

- same-run graph execution was not serialized across LangGraph invoke (advisory/row locks ended
  before graph execution)
- live uncertain timeout was silently retryable (`httpx.TimeoutException` treated as retryable)
- attempt intent was not durable before the provider call (`provider_attempt_count=0` then invoke)
- operation identity omitted taxonomy / Understand graph / prompt-config versions
- resume of a pending/running run with no checkpoint could pass unsafe `None` state
- durable operation CHECK constraints were too weak for lifecycle/count integrity

Do not mark independent PASS. Do not begin Phase 07 without separate explicit authorization.
Candidate owns Git writes.

## Phase 06 correction record — 2026-08-20

### Scope

Correction pass only. No Phase 06 redesign. No Phase 07 work. No Git writes by the agent.

- Session-level PostgreSQL advisory lock on `workflow-run:{run_id}` spans claim through graph
  invoke and final state update
- No-checkpoint resume re-enters the same run/thread from canonical initial state
- Live `ReadTimeout` / `WriteTimeout` / unknown timeout → `operation_ambiguous`, not retried
- `ConnectTimeout` / `PoolTimeout` remain retryable as pre-execution failures
- Ledger increments and commits `provider_attempt_count` before each ledger-invoked provider call
- Canonical operation identity includes taxonomy, Understand graph, prompt/config, outer workflow
  graph, provider, model, source-input version, and request hash
- Migration `20260819_0006` CHECK constraints tightened in place (0005 untouched)
- Failed checkpoint reset remains same-run/thread restart and is serialized under the session lock
- `resume_count` counts actual executions after the lock
- `Command(resume=...)` is sent only after the Phase 05 session is completed, so two serialized
  waiting resumes cannot consume both interrupt sites and finalize without a human decision

### Cursor correction verification — exact commands and final results

Inspection: `feat/phase-06-durable-resume`; agent Git write operations: none.

Backend from `backend/` with `DATABASE_URL=.../project_assurance`,
`TEST_DATABASE_URL=.../project_assurance_test`, `ALLOW_DESTRUCTIVE_TEST_DATABASE=true`
(Compose db only during pytest; backend/frontend stopped for host memory):

- `uv run ruff format --check .` — PASS; 67 files already formatted
- `uv run ruff check .` — PASS
- `uv run mypy src tests` — PASS; 55 source files
- dedicated test-database Alembic `0006 → 0005 → 0006`,
  `current = 20260819_0006 (head)` — PASS
- focused Phase 06 tests (ledger, workflow unit/integration/API, concurrency, timeouts,
  process-kill) — PASS after dropping an extra full-corpus checkpoint-deletion test that
  MemoryError'd; no-checkpoint resume now deletes checkpoint rows on the same run and resumes
- `uv run pytest -m integration` — PASS; 66 passed, 83 deselected in 141.64s
- `uv run pytest --cov=app --cov-report=term-missing` — PASS; 149 passed, **92.60%** (gate 90%)
- `uv build` — PASS; sdist and wheel for `project_assurance_register-0.6.0`
- dedicated real process-kill command after the review-gate resume fix:
  `uv run pytest tests/test_process_kill_resume.py::test_real_process_kill_then_new_process_resumes_same_run`
  — PASS in 11.72s

Frontend from `frontend/` (no Phase 06 UI expansion; API `implementation_status` text only):

- `npm test` — PASS; 2 files, 7 tests

Docker from repository root (sequential):

- `docker compose config --quiet` — PASS
- `docker compose build backend` — PASS; image installed `project-assurance-register==0.6.0`
- `docker compose up --build --detach` — PASS; db/backend/frontend healthy
- `/health` alive, `/ready` ready, `/version` 0.6.0 Phase 06 — PASS
- frontend HTTP 200 and `/api/ready` HTTP 200 — PASS
- `docker compose exec backend alembic current` — PASS; `20260819_0006 (head)`
- Aurora ingest → `POST /workflow-runs` → `waiting_for_review`; thread id equals run id;
  24 checkpoint rows; classify/extract ledger rows `completed` with logical_operation_count=1
- two concurrent `POST .../resume` of that same run → both `waiting_for_review`;
  understand `stage_completed` remains 1; `resume_count=2`; no `workflow_completed`
- Harbor corpus + Aurora run → HTTP 404
- `docker compose restart backend` then GET run still `waiting_for_review`; POST resume still
  `waiting_for_review`; review session `pending_count=4`, `approved_count=0`
- backend/frontend stopped afterward; db left running

### Correction limitations

- Independent re-verification of this correction is not complete. Do not mark independent PASS.
- Live HTTP 429 and 503 remain adapter-retryable as explicit provider backpressure responses.
  HTTP 408, HTTP 504, uncertain timeouts, and unclassified HTTPX transport errors are not.
- Ledger commits attempt intent once per `execute()` invocation before `fn()`. Inner adapter
  retries of known pre-execution failures are reflected on success via `usage.attempt_count`.
- Failed-stage recovery is still a same-run/thread restart, not in-place LangGraph node
  continuation.
- No Phase 07 work.

Do not begin Phase 07 without separate explicit authorization. Candidate owns Git writes.

## Phase 06 final live-retry correction — 2026-08-20

Independent re-verification of the first correction was NO-GO: HTTP 408, HTTP 504, and unclassified
`httpx.HTTPError` / post-send transport failures were still automatically retried.

### Policy now implemented

Automatically retryable:

- `ConnectTimeout`, `PoolTimeout`, `ConnectError` (request not sent)
- HTTP 429 and HTTP 503 as explicit provider backpressure responses, not unknown transport cuts

Ambiguous / no automatic retry:

- `ReadTimeout`, `WriteTimeout`, unknown `TimeoutException`
- HTTP 408, HTTP 504
- `RemoteProtocolError` and other unclassified `httpx.HTTPError`

Uncertain classification fails closed to `operation_ambiguous`. Provider exactly-once is not claimed.

### Cursor verification — exact commands and final results

Backend from `backend/` with `DATABASE_URL=.../project_assurance`,
`TEST_DATABASE_URL=.../project_assurance_test`, `ALLOW_DESTRUCTIVE_TEST_DATABASE=true`
(Compose db only):

- `uv run pytest tests/test_model_boundary.py tests/test_operation_ledger.py` — PASS
- `uv run ruff format --check .` — PASS
- `uv run ruff check .` — PASS
- `uv run mypy src tests` — PASS; 55 source files
- `uv run pytest --cov=app --cov-report=term-missing` — PASS; 155 passed, **92.50%** (gate 90%)
- `git diff --check` — PASS

Process-kill and Docker proofs were not rerun; this change does not touch workflow/checkpoint code.

Independent re-verification of this final correction is not complete. Do not mark independent
PASS. Do not begin Phase 07 without separate explicit authorization. Candidate owns Git writes.

## Phase 06 exclusive retry-allowlist correction — 2026-08-20

Independent re-verification of the second live-retry correction was NO-GO: malformed HTTP 200
output was still `retryable=True`, so the live loop could issue multiple expensive requests.

### Policy now implemented

The live request loop retries only `LiveRetryDisposition.SAFE_RETRY`, which is set exclusively for:

- `ConnectTimeout`
- `PoolTimeout`
- `ConnectError`
- HTTP 429
- HTTP 503

Malformed/unusable HTTP 200 output is `TERMINAL` (`model_output_invalid`) with one provider
attempt. Generic `ModelError.retryable` no longer controls the live loop.

### Cursor verification — exact commands and final results

Backend from `backend/` with `DATABASE_URL=.../project_assurance`,
`TEST_DATABASE_URL=.../project_assurance_test`, `ALLOW_DESTRUCTIVE_TEST_DATABASE=true`
(Compose db only):

- `uv run pytest tests/test_model_boundary.py tests/test_operation_ledger.py` — PASS; 34 passed
- `uv run ruff format --check .` — PASS; 67 files already formatted
- `uv run ruff check .` — PASS
- `uv run mypy src tests` — PASS; 55 source files
- `uv run pytest --cov=app --cov-report=term-missing` — PASS; 158 passed,
  **92.61%** (gate 90%). An earlier invocation of the same command had 5 host
  `MemoryError` failures during DOCX/zip ingest in existing workflow tests;
  those five tests passed in isolation, and this later full invocation passed
  all 158.
- `git diff --check` — PASS

Process-kill and Docker proofs were not rerun; this change does not touch workflow/checkpoint
logic.

Independent re-verification of this exclusive retry-allowlist correction is not complete. Do
not mark independent PASS. Candidate owns Git writes.

## Phase 07 record — 2026-08-20

### Scope completed

Implemented focused incremental updates and the minimum stable-file watcher. No MCP, no register
publication, no Phase 08 UI/MCP work, no deployment/final submission work.

- Alembic `20260819_0007` after committed `20260819_0006`: `corpus_revisions`, `incremental_runs`,
  `incremental_artifact_evidence`, `watcher_files`
- Change identity: logical source + SHA-256; new immutable SourceVersion on changed bytes
- Impact from Phase 03/04 provenance citations, not vector similarity
- Incremental Understand/Examine reuse unaffected artifacts; classify/extract only changed sources
- Canonical serialization `incremental-artifact.v1`; unchanged hashes identical before/after reuse
- Durable executed-versus-reused operation/source-version evidence; final-output equality is not
  accepted as no-full-rerun proof
- New review session; prior session immutable; no implicit approval; changed evidence requires
  fresh review
- Same-corpus `pg_advisory_lock`; stale explicit baseline persists `stale_baseline` / HTTP 409
- Watcher: `{WATCH_INPUT_PATH}/{corpus_id}/{logical_name}.{ext}`, hash+size stability, restart
  suppression, malformed/empty/oversized/missing handling
- Application version `0.7.0`, phase `Phase 07 — Incremental Updates`

### Cursor implementation verification — exact commands and final results

Inspection: `feat/phase-07-incremental-updates`; agent Git write operations: none.

Backend from `backend/` with `DATABASE_URL=.../project_assurance`,
`TEST_DATABASE_URL=.../project_assurance_test`, `ALLOW_DESTRUCTIVE_TEST_DATABASE=true`
(Compose db only during pytest):

- `uv sync --frozen --all-groups` — PASS
- `uv run ruff format --check .` — PASS
- `uv run ruff check .` — PASS
- `uv run mypy src tests` — PASS; 64 source files
- dedicated test-database Alembic `0006 → 0007 → 0006 → 0007`,
  `current = 20260819_0007 (head)` — PASS
- `uv run pytest -m integration` — PASS; 73 passed, 97 deselected in 322.18s
- `uv run pytest --cov=app --cov-report=term-missing` — PASS; 170 passed, **91.28%** (gate 90%).
  After that run, watcher malformed/empty/missing tests were added. Isolated
  `tests/test_watcher.py` later PASS (2 passed). One earlier isolated watcher run hit host
  `MemoryError` during SHA-256 of stored bytes; the same test passed on retry.
- `uv build` — PASS; sdist and wheel for `project_assurance_register-0.7.0`

Frontend from `frontend/`:

- `npm ci` — PASS
- `npm run format:check` — PASS after Prettier rewrite of `src/App.tsx`
- `npm run lint` — PASS
- `npm run typecheck` — PASS
- `npm test` — PASS; 2 files, 7 tests
- `npm run build` — PASS

Docker:

- `docker compose config` — PASS; `APP_VERSION=0.7.0`, watch inbox volume `/data/watch-inbox`
- `docker compose build backend` — PASS
- `docker compose up --build --detach` — PASS; db/backend/frontend healthy
- `/health` alive, `/ready` ready with pgvector 0.8.1, `/version` 0.7.0 Phase 07 — PASS
- container `alembic current` = `20260819_0007 (head)` — PASS
- frontend `http://localhost:5173/` and `/api/ready` HTTP 200 — PASS
- Docker HTTP Aurora baseline + one-source Decision Log change + incremental run
  `c54d27d4-08f8-4473-8d67-9f39b748f5d3`: `full_rerun=false`, stale baseline HTTP 409 — PASS

Harbor incremental, watcher polling, and PostgreSQL stale-baseline concurrency were proven by
pytest, not repeated as a second Docker HTTP corpus.

Independent re-verification is not complete. Do not mark independent PASS. Do not begin Phase 08.
Candidate owns Git writes.

## Independent Phase 07 verification — FAIL / NO-GO

Independent Phase 07 verification: **FAIL / NO-GO**

Critical areas found:

- post-extraction impact gap
- Phase 04 validation bypass
- synthetic/non-ledger operation proof
- incomplete canonical proof
- watcher lost-update window
- non-atomic revision finalization

This FAIL / NO-GO record is retained. Later local corrections do not replace it.

## Phase 07 first correction — local

First correction addressed the FAIL areas above: post-extraction impact replanning, Phase 04
revalidation on incremental Examine, ledger-backed classify/extract for changed sources, skipped
(not fabricated reused) unchanged classify keys, persisted-row canonical proof for facts/
contradictions/findings, atomic revision finalization, watcher pending-incremental recovery, and
`corpus_revision_sources` membership.

## Independent Phase 07 first re-verification — NO-GO

Independent re-verification of that first correction: **NO-GO**

Remaining blockers:

- unchanged extract suppression not durably evidenced per source version
- reused review items lacked persisted canonical before/after byte proof
- `corpus_revision_sources` did not DB-enforce source_version belongs to source and SHA equality
- Aurora contradiction behavior asserted mainly by counts
- Harbor second-run assertions incomplete (facts/rules/contradictions/classify+extract)
- persisted reused contradiction/finding canonical byte equality not tested
- orphan pre-finalization AnalysisRun/ExaminationRun/ReviewSession rows not documented
- original independent Phase 07 FAIL / NO-GO not explicitly preserved in PROGRESS

## Phase 07 local final correction

Local final correction for the remaining re-verification blockers. Local status: **PASS**.
Do not mark independent PASS. Do not begin Phase 08. Candidate owns Git writes.

Inspection: `feat/phase-07-incremental-updates`; agent Git write operations: none.

Backend from `backend/` with `DATABASE_URL=.../project_assurance`,
`TEST_DATABASE_URL=.../project_assurance_test`, `ALLOW_DESTRUCTIVE_TEST_DATABASE=true`:

- focused `uv run pytest tests/test_incremental_unit.py tests/test_incremental_integration.py tests/test_watcher.py` — PASS; 18 passed (8 unit + 7 integration + 3 watcher)
- `uv run ruff format --check .` — PASS
- `uv run ruff check .` — PASS
- `uv run mypy src tests` — PASS; 64 source files
- `uv run pytest -m integration` — PASS; 78 passed, 100 deselected in 170.57s
- `uv run pytest --cov=app --cov-report=term-missing` — PASS; 178 passed, **92.08%** (gate 90%)
- `uv build` — PASS; sdist and wheel for `project_assurance_register-0.7.0`
- dedicated test-database Alembic `0006 → 0007 → 0006 → 0007`,
  `current = 20260819_0007 (head)` — PASS

Frontend: no shared-contract or UI changes in this pass; regression not re-run.

Docker after backend PASS:

- `docker compose build backend` and recreate healthy backend — PASS
- container `alembic` after clearing leftover incremental ledger rows with null `workflow_run_id`,
  then `0006 → 0007`, `current = 20260819_0007 (head)` — PASS
- HTTP `/version` 0.7.0 Phase 07, `/ready` — PASS
- HTTP Aurora incremental: `full_rerun=false`, unchanged classify **and** extract skipped,
  changed classify+extract executed, reused review items with `canonical_bytes_equal=true` — PASS
- HTTP Harbor incremental + classify/extract skip, no Aurora names required — PASS
- HTTP stale baseline 409 — PASS
- HTTP cross-corpus incremental lookup 404 — PASS
- HTTP `POST /watcher/poll` — PASS
- Watcher pending-incremental recovery without a new SourceVersion remains pytest-proven
  (`test_watcher_retries_incremental_after_ingest_without_new_version`)

Independent re-verification is not complete. Do not mark independent PASS. Do not begin Phase 08.

## Independent Phase 07 re-verification of local final correction — NO-GO

Independent re-verification of the local final correction: **NO-GO** / **PHASE 07 COMMIT VERDICT: NO-GO**

Previous blockers (classify/extract suppression, canonical proof, revision membership, Aurora,
Harbor, documentation/history) were resolved. New blocker:

- `20260819_0007` downgrade dropped `incremental_run_id` and restored `workflow_run_id` NOT NULL
  before removing incremental ledger rows. Incremental `DurableOperation` rows have
  `workflow_run_id = NULL`, so a populated `0007` database could not downgrade without manual
  deletion. Schema-only `0006 → 0007 → 0006 → 0007` did not prove downgrade safety with normal
  Phase 07 data. The local Docker record itself reported clearing those rows first.

This NO-GO record is retained. Later local corrections do not replace it.

## Phase 07 0007 downgrade correction — local

Local correction of the populated-downgrade defect. Local status: **PASS**.
Do not mark independent PASS. Do not begin Phase 08. Candidate owns Git writes.

Inspection: `feat/phase-07-incremental-updates`; agent Git write operations: none.

Downgrade now drops watcher/evidence tables, deletes incremental-owned `durable_operations`
(`incremental_run_id IS NOT NULL` or `workflow_run_id IS NULL`), then restores
`workflow_run_id` NOT NULL. Workflow-owned ledger rows remain. Phase 07 revision/run/evidence
data is discarded by that downgrade.

Backend from `backend/` with `DATABASE_URL=.../project_assurance`,
`TEST_DATABASE_URL=.../project_assurance_test`, `ALLOW_DESTRUCTIVE_TEST_DATABASE=true`:

- `uv run pytest tests/test_incremental_migration.py` — PASS; Harbor incremental ledger rows
  present, `0007 → 0006` without manual deletion, remaining `durable_operations.workflow_run_id`
  NOT NULL, `incremental_runs` gone, restore `0007` head
- `uv run ruff format --check .` — PASS
- `uv run ruff check .` — PASS
- `uv run mypy src tests` — PASS; 65 source files
- `uv run pytest -m integration` — PASS; 79 passed, 100 deselected
- `uv run pytest --cov=app --cov-report=term-missing` — PASS; 179 passed, **92.11%** (gate 90%)
- `uv build` — PASS; sdist and wheel for `project_assurance_register-0.7.0`
- dedicated test-database schema round-trip `0006 → 0007 → 0006 → 0007`,
  `current = 20260819_0007 (head)` — PASS (schema-only; populated proof is the pytest above)

Frontend: no UI/contract change in this pass; not re-run.

Docker after backend PASS, **without** manually deleting incremental ledger rows:

- Before downgrade: 4 workflow-owned and 4 incremental-owned `durable_operations`, 3 incremental runs
- `docker compose build backend` and recreate — PASS
- `alembic downgrade 20260819_0006` — PASS; 4 remaining ops, 0 null `workflow_run_id`,
  `workflow_run_id` `is_nullable=NO`, `incremental_runs` absent
- `alembic upgrade 20260819_0007`, `current = 20260819_0007 (head)` — PASS

Independent re-verification of this correction is not complete. Do not mark independent PASS.
Do not begin Phase 08.

## Phase 07 mixed-ownership downgrade test correction — local

Migration `0007` downgrade-order implementation passed inspection. Remaining blocker: the
populated round-trip test was vacuous for Phase 06 preservation because `workflow_owned_ids`
was never asserted non-empty, so `remaining_ids == workflow_owned_ids` could pass with both
sets empty.

Corrected `tests/test_incremental_migration.py`: real Phase 06 `WorkflowService.create_run`
(Aurora, waiting_for_review, no auto-completed review) plus real Phase 07 Harbor incremental
run; both ownership classes asserted non-empty with exclusive `workflow_run_id` /
`incremental_run_id` shapes; exact IDs compared after `0007 → 0006` with no manual cleanup;
workflow rows and Phase 06 tables survive; incremental IDs and Phase 07 tables disappear;
upgrade returns `20260819_0007 (head)` with the same workflow-owned rows valid.

Verification:

- `uv run pytest tests/test_incremental_migration.py -v` — PASS
- `uv run ruff format --check .` — PASS
- `uv run ruff check .` — PASS
- `uv run mypy src tests` — PASS; 65 source files
- `uv run pytest -m integration` — PASS; 79 passed, 100 deselected
- `uv run pytest --cov=app --cov-report=term-missing` — PASS; 179 passed, **92.06%** (gate 90%)
- dedicated test-database schema round-trip `0006 → 0007 → 0006 → 0007`,
  `current = 20260819_0007 (head)` — PASS
- Docker not re-run; populated Docker downgrade already passed and this test did not expose a
  migration defect

Do not mark independent PASS. Do not begin Phase 08.
