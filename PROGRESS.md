# Progress and Decision Log

## Current state

- **Current phase:** Phase 02 — PASS_WITH_CHANGES / FOLLOW-UP VERIFIER PENDING
- **Implementation status:** verified foundation plus deterministic ingestion/provenance layer
- **Application capabilities implemented:** liveness, dependency readiness, version/phase metadata,
  corpus/source/version/block schema, streamed ingestion, four parsers, exact citation resolution,
  deterministic pgvector retrieval, React status shell, local Compose stack, tests, and CI definition
- **Dependencies installed by this work:** locked Python and npm dependencies recorded below
- **Application or test commands available:** exact verified commands are recorded below and in
  `README.md`
- **Git write operations performed by the agent:** none
- **Phase 01 status:** COMPLETE — local verification PASS, remote CI PASS, merged to `main`
- **Phase 01 remote CI status:** PASS — attempt 2 backend/frontend and all PR checks passed
- **Merge status:** PR #1 merged to `main` as merge commit `cd9ffa7`
- **Phase 02 independent verification:** PASS_WITH_CHANGES — zero critical findings
- **Phase 02 correction status:** corrections implemented locally; independent follow-up pending
- **Phase 02 remote CI:** NOT RUN — branch has not been pushed
- **Phase 03 status:** NOT AUTHORIZED / NOT STARTED
- **SuperDocs familiarization/docs confirmation:** COMPLETE — manual candidate action outside the repository; recording it here is our process choice, not an assignment-mandated artifact

## Phase 00 record — 2026-08-18

### Files created

- `README.md`
- `TASK.md`
- `PROGRESS.md`
- `docs/architecture.md`

No application code, dependency manifests, backend/frontend directories, migrations, container files, fixtures, or tests were created in Phase 00.

### Manual candidate prerequisite record — 2026-08-19

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

## Phase 01 record — 2026-08-19

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

### Cursor implementation verification — exact commands and final results

Inspection:

- `git branch --show-current` — `feat/phase-01-foundation`
- `git status --short --branch` — clean before implementation
- `git log -5 --oneline --decorate` and `git ls-files` — Phase 00 baseline inspected
- `python --version`, `py -0p`, `uv --version`, `node --version`, `npm --version`,
  `docker --version`, `docker compose version` — host versions captured
- PyPI JSON metadata queries for every direct backend/runtime tool — versions and
  `requires_python` inspected
- npm metadata queries for React/Vite/TypeScript/ESLint/Prettier/Vitest/RTL — versions and Node
  engines inspected
- `uv python list 3.13` — CPython 3.13.14 managed download confirmed
- `docker manifest inspect pgvector/pgvector:0.8.1-pg17-bookworm --verbose` — image/platforms
  confirmed

Backend final gate from `backend/`:

- `uv sync --frozen --all-groups` — PASS; 90 packages resolved, 88 installed/checked
- `uv run ruff format --check .` — PASS; 10 files already formatted
- `uv run ruff check .` — PASS
- `uv run mypy src tests` — PASS; no issues in 8 source files
- `uv run pytest --cov=app --cov-report=term-missing` — PASS; 7 passed, 1 integration test skipped
  without `TEST_DATABASE_URL`, 97.96% total coverage
- `uv build` — PASS; source distribution and wheel built

Real database gate:

- `uv run alembic current` with the running Compose database — PASS;
  `20260819_0001 (head)`
- `uv run pytest tests/test_readiness_integration.py` with `DATABASE_URL` and
  `TEST_DATABASE_URL` set — PASS; 1 passed against PostgreSQL/pgvector

Frontend final gate from `frontend/` during Cursor implementation verification:

- `npm ci` — PASS; 235 packages installed, 0 reported vulnerabilities
- `npm run format:check` — PASS
- `npm run lint` — PASS
- `npm run typecheck` — PASS
- `npm test` — PASS; 1 file and 4 tests passed
- `npm run build` — PASS; Vite production output built

Container/runtime gate from repository root:

- `docker compose config` and final `docker compose config --quiet` — PASS
- `docker compose build` — PASS for backend and frontend
- `docker compose up --build --detach` — PASS as the combined build/start path; all services became
  healthy and readiness/frontend smoke checks passed
- `docker compose up --detach` — PASS; database, backend, and frontend started
- `docker compose exec backend alembic current` — PASS; migration at head
- `Invoke-RestMethod http://localhost:8000/health` — PASS; `alive`
- `Invoke-RestMethod http://localhost:8000/ready` — PASS; PostgreSQL and pgvector `ready`,
  pgvector `0.8.1`
- `Invoke-RestMethod http://localhost:8000/version` — PASS; version `0.1.0`, Phase 01, truthful
  not-implemented status
- `Invoke-WebRequest -UseBasicParsing http://localhost:5173/` — PASS; HTTP 200
- `Invoke-WebRequest -UseBasicParsing http://localhost:5173/api/ready` — PASS; HTTP 200 through
  Nginx proxy
- `docker compose ps` — PASS; all three services healthy
- Browser accessibility snapshot — PASS; rendered `Foundation ready`, version `0.1.0`, current
  Phase 01, and `Task 1 business workflow is not implemented yet.`
- Browser console error check — PASS; zero errors/warnings
- `docker compose down` — PASS; containers/network removed and persistent volume retained
- final `docker compose ps --all` — PASS; no running project containers

### Candidate-side independent verification correction — 2026-08-19

The candidate independently confirmed that backend, Docker, PostgreSQL/pgvector, migration,
readiness, HTTP smoke, and real database integration gates passed.

The candidate's initial independent frontend verification produced:

- `npm ci` — PASS
- `npm run format:check` — **FAIL**; Prettier reported formatting drift/non-canonical formatting in:
  - `.prettierrc.json`
  - `eslint.config.js`
  - `src/App.test.tsx`
  - `src/App.tsx`
  - `src/main.tsx`
  - `src/styles.css`
  - `src/test/setup.ts`
  - `vite.config.ts`

The candidate corrected the defect with:

- `npm run format` — PASS; Prettier applied canonical formatting

The candidate then reran the complete affected frontend quality/build gate:

- `npm run format:check` — PASS; `All matched files use Prettier code style!`
- `npm run lint` — PASS
- `npm run typecheck` — PASS
- `npm test` — PASS; 1 test file and 4 tests passed
- `npm run build` — PASS; Vite production build completed successfully

This candidate-side failure remains part of the evidence history. Phase 01 remains PASS only because
the formatting defect was corrected and every affected frontend gate was rerun successfully.

README command verification after the correction:

- frontend scripts in `README.md` match `frontend/package.json`, including `npm run format`,
  `npm run format:check`, lint, typecheck, tests, and build;
- backend commands match the tools/configuration in `backend/pyproject.toml`; and
- `docker compose config --quiet` passed for the documented Compose commands.

No README command correction was required.

### Independent Phase 01 verification — PASS_WITH_CHANGES — 2026-08-19

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

- Backend Ruff format check — PASS; 10 files formatted
- Backend Ruff lint — PASS
- Backend mypy — PASS; no issues in 8 source files
- Backend pytest/coverage final rerun — PASS; 7 passed, 1 integration test skipped without
  `TEST_DATABASE_URL`, 97.96% coverage
- Backend package build — PASS; source distribution and wheel built
- Frontend Prettier check — PASS; canonical formatting confirmed
- Frontend ESLint — PASS
- Frontend TypeScript typecheck — PASS
- Frontend Vitest — PASS; 1 test file and 4 tests passed
- Frontend production build — PASS
- `docker compose config` — PASS
- `docker compose build` — PASS; both hardened contexts retained every required Docker build input
- `docker compose up --detach` and `docker compose ps` — PASS; database, backend, and frontend all
  healthy
- `/health`, `/ready`, and `/version` — PASS
- Frontend `/` and `/api/ready` — PASS; HTTP 200
- `docker compose exec backend alembic current` — PASS; `20260819_0001 (head)`
- Container startup logs — PASS; migration, Uvicorn, and Nginx startup completed without runtime
  package synchronization
- `docker compose down` — PASS; containers/network removed and persistent volume retained
- final `docker compose ps --all` — PASS; no project containers remained
- `git diff --check` — PASS

### Remote GitHub CI attempt 1 — backend failure — 2026-08-19

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

- `uv run ruff format --check .` — PASS; 10 files formatted
- `uv run ruff check .` — PASS
- `uv run mypy src tests` — PASS; no issues in 8 source files
- `uv run pytest --cov=app --cov-report=term-missing` — PASS; 10 passed, 1 integration test skipped
  without `TEST_DATABASE_URL`, 100% coverage
- `uv build` — PASS; source distribution and wheel built
- `docker compose config` — PASS
- `docker compose up --build --detach` — PASS
- `docker compose ps` — PASS; database, backend, and frontend all healthy
- `/health`, `/ready`, and `/version` — PASS
- `docker compose exec backend alembic current` — PASS; `20260819_0001 (head)`
- real `tests/test_readiness_integration.py` against the Compose database — PASS; 1 passed
- `docker compose down` — PASS
- `git diff --check` — PASS

Remote CI status: **FAILED / FIX PENDING** until the candidate pushes this fix and GitHub Actions
reruns successfully. Attempt 1 remains recorded and is not reclassified as PASS.

### Remote GitHub CI attempt 2 and merge — 2026-08-19

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
  false “prettier not recognized” failure. Dependency installation and quality checks were rerun in
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
- Candidate execution constraint/project planning assumption: 24-hour hard ceiling, with approximately 19.5 hours planned across Phases 01–10 and 4.5 hours protected for debugging, verification, evidence, and final audit. This schedule is not stated in the assignment PDF.

## Decisions

### D-001 — Domain and corpus

Use fictional software-project assurance documents because overlapping plans, status reports, risks, decisions, and meeting records naturally exercise extraction, contradiction, rules, exact provenance, and focused updates without sensitive data.

### D-002 — Deliverable structure

Use stable structured Project Assurance Register items rather than a free-form report. Stable IDs and canonical serialization make item-level review, incremental replacement, and exact unchanged-content proof feasible.

### D-003 — Format breadth

Target text-based PDF, DOCX, Markdown, and plain text. Exclude OCR, handwriting, arbitrary formats, and spreadsheet output initially. Consider CSV only after the five-behavior floor and genuine movement evidence are green.

### D-004 — Exact provenance

A supported claim/finding requires immutable source version ID and SHA-256, a format-native locator, a span where available, and exact quoted evidence. A page number alone is not sufficient.

### D-005 — Human gate

The acceptance demonstration uses a real human decision:

```text
agent proposes
→ WAITING_FOR_REVIEW
→ human reviews
→ human explicitly approves/rejects individual items
→ decision is submitted through a UI/API/MCP operation
→ workflow resumes
→ only approved items are applied
```

MCP/API exposes explicit item-level operations, but the demonstrated path does not let the proposing agent automatically approve its own work. No RBAC or proposer/reviewer identity-separation requirement is added.

### D-006 — Machine operation

React and MCP/API will call the same application services. The machine surface exposes, rather than bypasses, the review gate. MCP is our strongest chosen interface shape, not an absolute assignment mandate.

### D-007 — Durability and concurrency

Start with the simplest PostgreSQL-backed durable design that proves checkpoint resume, idempotency, concurrent-run isolation, and safe publication. Do not pre-commit to a transactional outbox. Add one only if implementation tests expose a concrete need.

### D-008 — Incremental definition

A new source may be fully parsed and indexed, but the existing corpus must not be fully reprocessed by the model. Determine an affected entity/rule set, process only that set, and preserve unaffected register item canonical bytes and hashes.

### D-009 — Keyless proof

Behavior 7 is planned as a strong differentiator: use a deterministic model adapter only at the model boundary while exercising real graph transitions, parsers, PostgreSQL/pgvector, process restart, transactions, concurrency, API/MCP transport, and deterministic validators. It may be cut only with explicit rationale if time forces a trade-off.

### D-010 — Hosted deployment

Hosted deployment is not explicitly required by Task 1. Our minimum acceptance target is a reproducible local/container deployment. Hosted deployment will be attempted only after all mandatory Task 1 behaviors and evidence are green.

### D-011 — Infrastructure restraint

Do not introduce Kubernetes, Terraform, Kafka, Redis, Celery, microservices, or similar infrastructure without a measured blocker. Prefer one codebase and PostgreSQL.

### D-012 — Truthful documentation

README must separate **implemented** from **planned**. Capabilities are not marked implemented until executable evidence passes and is recorded here.

### D-013 — Git control

The candidate executes all Git writes. Agents may inspect Git read-only and must provide exact manual commands whenever Git work is needed.

### D-014 — Command truthfulness

Do not invent scripts, package names, or commands. Phase 01 creates and verifies the command contract. Every later phase must provide exact commands that exist in the repository.

### D-015 — Behaviors 6–10 classification

Behaviors 1–5 are the explicit non-cuttable floor. Each behavior 6–10 item—one-command stranger setup, real keyless tests, document prompt-injection defense, concurrent isolation, and stage timing/cost—is a **Strong differentiator — may be cut only with explicit rationale if time forces a trade-off.**

### D-016 — Movement cut policy

Understand, examine, and stay alive must each remain genuinely represented. Detailed sub-features inside those movements may be cut with explicit rationale; they are not all independently non-cuttable.

### D-017 — Deliverable-side provenance

A register-grounded finding uses `register_version_id`, `register_item_id`, `field_path`, `value_hash`, and `exact_value`. Validation resolves the locator against the immutable register version before treating the finding as supported.

### D-018 — Costly external-call crash window

Persist operation key and attempt before the call, use provider idempotency when available, persist the structured result before graph advancement, and reuse durable completed results on resume. Retry only when non-completion is known. An unknowable provider outcome becomes an honest ambiguous state for reconciliation/retry; exactly-once behavior is not claimed.

### D-019 — Incremental proof

Evidence must compare affected item IDs, preserved item IDs, executed stage IDs, model-operation/idempotency keys, processed source versions, and canonical before/after hashes. Hash equality alone does not prove a full rerun was avoided.

### D-020 — Graceful degradation

Demonstrated failure paths should use a working deterministic fallback, bounded retry, safe skip, or human escalation where implemented and tested. If no safe fallback exists, preserve durable state, expose cause/remedy, remain resumable, and never falsely report success. No fallback is currently implemented or claimed.

## Assumptions

### A-001 — Meaning of “commit”

“Commit” in the agentic workflow means applying approved items to a new durable register version. It does not mean a Git commit.

### A-002 — Meaning of “mixed formats”

The initial declared set of PDF, DOCX, Markdown, and TXT satisfies mixed-format input. PDF support initially requires extractable text.

### A-003 — Meaning of “exact place”

Exact source provenance means a resolvable immutable source/hash, native locator, span, and quote—not only a document name or page.

### A-004 — Watched location

The minimum watcher is a mounted local inbox using stable-file detection and content-hash deduplication. API uploads may emit the same ingestion event. Sophisticated filesystem infrastructure is unnecessary unless tests prove otherwise.

### A-005 — Explicit review

A human can submit decisions through the React UI or invoke an explicit API/MCP decision operation. The important property is conscious item-level human choice, not which adapter carries it. This does not assume RBAC or proposer/reviewer identity separation.

### A-006 — Model availability and cost

Runtime model access is provider-configurable. The planned Behavior 7 strong differentiator is a real keyless acceptance suite and demo mode. If pricing is unavailable, report token/usage data and “cost unavailable” instead of inventing a currency amount.

### A-007 — Retrieval and grounding

pgvector improves retrieval recall but cannot establish evidence. Only deterministic resolution against immutable source content establishes provenance.

### A-008 — One-command target

The intended fresh-clone target is a single local/container startup command after the required file is implemented and verified. Phase 00 does not claim that command exists.

### A-009 — Authentication scope

Local/demo identity may be sufficient within the time ceiling. Corpus/run scoping remains a planned data-safety baseline; concurrent-run proof is Behavior 9 and therefore a strong differentiator rather than part of the explicit five-behavior floor. Internet-facing production authentication is not claimed unless implemented and tested.

### A-010 — SuperDocs familiarization data

Candidate product familiarization may use the candidate’s own non-confidential work outside this repository. Repository fixtures and demonstrations remain synthetic/public.

### A-011 — Measurement

Measurement methodology is stated before results. Variance, tail behavior, pricing basis, and limitations are reported. Raw measurement data will be committed to the repository. A success claim requires matching evidence.

## Evidence register

Status values are `NOT_STARTED`, `IN_PROGRESS`, `PASS`, `FAIL`, or `CUT_OPTIONAL`.

### Five-behavior non-cuttable floor

- Visible path-changing stages — `NOT_STARTED`
- Exact claim/finding provenance — `NOT_STARTED`
- Unsupported-claim honesty — `NOT_STARTED`
- Real human mixed approve/reject — `NOT_STARTED`
- Approved-only application — `NOT_STARTED`
- Process kill and durable resume — `NOT_STARTED`
- Machine-interface end-to-end explicit gate operations — `NOT_STARTED`

### Planned movement evidence

- Mixed-format ingestion and declared-format validation — `PASS` for Phase 02
- Document classification reasoning — `NOT_STARTED` for Phase 03
- Contradiction surfacing — `NOT_STARTED`
- Honest no-findings result — `NOT_STARTED`
- Configuration-only rule/domain change — `NOT_STARTED`
- Focused incremental processing — `NOT_STARTED`
- Incremental affected/preserved IDs, stages, operation keys, source versions, and before/after hashes — `NOT_STARTED`
- Source-attributed change history — `NOT_STARTED`
- Second-corpus fixture creation for ingestion/provenance — `PASS` for Phase 02
- Second-corpus agent execution — `NOT_STARTED`

Detailed movement items may be cut with explicit rationale while keeping understand, examine, and stay alive genuinely represented.

### Behaviors 6–10 strong differentiators

Each is a **Strong differentiator — may be cut only with explicit rationale if time forces a trade-off.**

- Fresh-clone local/container command — `NOT_STARTED`
- Real keyless tests — `NOT_STARTED`
- Document prompt-injection defense — `NOT_STARTED`
- Concurrent distinct/same-corpus isolation — `NOT_STARTED`
- Stage timing/usage/cost basis — `NOT_STARTED`

### Additional prioritized engineering evidence

- Idempotent duplicate source ingestion — `PASS` for Phase 02 logical-source/content behavior
- Costly external-call ambiguous-outcome reconciliation — `NOT_STARTED`
- Cause/remedy dependency failures and resumability — `NOT_STARTED`
- Working fallback/retry/skip/escalation paths, without unproven fallback claims — `NOT_STARTED`
- Streamed bounded upload/SHA computation — `PASS` for Phase 02
- Phase 01 lint/format/typecheck/test/build/smoke/cleanup command proof — `PASS`

## Candidate execution constraint and project planning assumption

This schedule is not stated in the assignment PDF. Phases 01–10 total approximately 19.5 planned hours:

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

The remaining 4.5h is protected buffer for debugging, verification, evidence repair, and final audit—not additional feature scope.

If cuts are required:

1. UI polish;
2. hosted deployment;
3. CSV;
4. multiple model providers;
5. elaborate observability UI;
6. sophisticated watcher implementation; and
7. extra format breadth.

Never cut the five explicit floor behaviors: visible path-changing stages, durable resume, item-level human review, machine-driven flow, or no-bluffing. Understand, examine, and stay alive must each remain represented at genuine minimum depth; detailed sub-features may be cut with explicit rationale. Behaviors 6–10 remain prioritized strong differentiators and may be cut only with explicit rationale if time forces a trade-off.

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
- [x] Behaviors 1–5 versus 6–10, movement cut policy, stack choice, MCP status, provenance, failure, crash-window, and incremental-proof terminology are consistent in all files.

Phase 01 execution requirements after authorization:

- Begin with repository and package compatibility inspection before choosing dependencies.
- Supply exact Phase 01 commands before requesting any manual prerequisite action.

**Historical entry result: PASS. Phase 01 implementation and verification completed.**

## Verification log

Phase 00 verification status: **PASS — authoritative assignment comparison completed; independent verifier findings incorporated at documentation level.**

Phase 01 verification status: **COMPLETE — local quality, real PostgreSQL/pgvector integration,
container startup/migration/readiness, rendered frontend, cleanup, remote backend/frontend CI, and
merge gates completed.**

The Phase 00 result remains documentation-level evidence. The Phase 01 result is executable
foundation evidence only and does not prove any Task 1 business behavior.

All four files were reread after the final correction pass. Incorporated findings include:

- behaviors 1–5 are the explicit non-cuttable floor; behaviors 6–10 are prioritized strong differentiators that may be cut only with explicit rationale;
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

## Phase 02 record — 2026-08-19

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

- `uv run alembic upgrade head` — PASS from Phase 01; reached `20260819_0002`;
- `uv run alembic downgrade 20260819_0001` — PASS;
- `uv run alembic upgrade head` — PASS after downgrade; and
- `uv run alembic current` — PASS, `20260819_0002 (head)`.

### Dependency decisions

Added and locked:

- `pypdf==6.16.1` — BSD-3-Clause, Python >=3.9, selected for text-based PDF parsing instead of
  AGPL PyMuPDF to avoid imposing AGPL server/application obligations;
- `python-docx==1.2.0` — MIT, Python >=3.9, release-tested on Python 3.13; and
- `python-multipart==0.0.32` — direct FastAPI upload dependency, Python >=3.10, already present
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

- valid source-file → ingestion → immutable version/hash → parser → block → citation → resolver
  round-trip for PDF, DOCX, Markdown, and TXT — PASS;
- wrong source SHA — rejected with `source_sha_mismatch`;
- wrong native locator — rejected with `native_locator_mismatch`;
- out-of-range normalized span — rejected with `normalized_span_mismatch`;
- wrong exact quote — rejected with `exact_quote_mismatch`;
- persisted normalized-text tampering — rejected with `source_block_integrity_mismatch`;
- persisted native-locator tampering — rejected with `source_block_integrity_mismatch`;
- citation format disagreement — rejected with `source_format_mismatch`;
- source bytes changed after registration — rejected with `source_bytes_tampered`;
- missing version — rejected with `source_version_not_found`; and
- cross-corpus version/citation lookup — not found.

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

- `uv add "pypdf==6.16.1" "python-docx==1.2.0" "python-multipart==0.0.32"` — PASS;
- `uv lock` — PASS;
- `uv run python scripts/generate_synthetic_corpora.py` — PASS; and
- `uv sync --frozen --all-groups` — PASS.

Backend final gate:

- `uv run ruff format --check .` — PASS; 27 files formatted;
- `uv run ruff check .` — PASS;
- `uv run mypy src tests` — PASS; no issues in 21 source files;
- `uv run pytest --cov=app --cov-report=term-missing` with real PostgreSQL/pgvector — PASS;
  31 tests, 90.86% coverage; and
- `uv build` — PASS; sdist and wheel for `project_assurance_register-0.2.0`.

Focused integration:

- `uv run pytest -m integration` — PASS; 9 tests against PostgreSQL/pgvector;
- PDF/DOCX/Markdown/TXT citation parameterization — PASS;
- duplicate/changed/cross-corpus version behavior — PASS;
- all required provenance/tamper failures — PASS; and
- pgvector persistence, similarity, filter, and corpus isolation — PASS.

Frontend:

- `npm ci` — PASS; 235 packages, 0 reported vulnerabilities;
- initial `npm run format:check` — FAIL on 11 committed files due non-canonical working-tree
  line endings/format;
- `npm run format` — PASS;
- rerun `npm run format:check` — PASS;
- `npm run lint` — PASS;
- `npm run typecheck` — PASS;
- `npm test` — PASS; 1 file, 4 tests;
- `npm run build` — PASS.

Docker/runtime:

- `docker compose config --quiet` — PASS;
- `docker compose build` — PASS;
- `docker compose up --build --detach` — PASS;
- all three services healthy — PASS;
- `docker compose exec backend alembic current` — PASS, `20260819_0002 (head)`;
- `/health`, `/ready`, `/version`, frontend `/`, and proxy `/api/ready` — PASS;
- container TXT ingestion and exact citation validation — PASS;
- backend logs contained route/migration metadata but no source text, credentials, or stack traces;
- `docker compose down` — PASS; named data volumes retained; and
- `docker compose ps --all` — PASS; no project containers remained.

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

## Independent Phase 02 verification corrections — 2026-08-19

### Verifier result and scope

- Independent verifier: **PASS_WITH_CHANGES**
- Critical findings: **none**
- Current status: **PASS_WITH_CHANGES — corrections implemented locally, follow-up verifier
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

- `uv sync --frozen --all-groups` — PASS
- `uv run ruff format --check .` — PASS; 31 files already formatted
- `uv run ruff check .` — PASS
- Initial `uv run mypy src tests` — FAIL; one redundant cast after citation-format narrowing.
  Removed that cast.
- Final `uv run mypy src tests` — PASS; no issues in 24 source files
- Dedicated test-database Alembic `upgrade head` → `downgrade 20260819_0001` → `upgrade head` →
  `current` — PASS; `20260819_0002 (head)`
- `uv run pytest -m integration` — PASS; 12 passed, 26 deselected
- `uv run pytest --cov=app --cov-report=term-missing` — PASS; 38 passed, 91.45% coverage
- `uv build` — PASS; sdist and wheel for `project_assurance_register-0.2.0`
- `uv run pytest -m "not integration"` — PASS; 26 passed, 12 deselected

Frontend from `frontend/`:

- `npm ci` — PASS; 235 packages, 0 reported vulnerabilities
- `npm run format:check` — PASS
- `npm run lint` — PASS
- `npm run typecheck` — PASS
- initial `npm test` in parallel with the backend coverage run — FAIL; Vitest forks worker timeout,
  0 tests executed (host load, no frontend source change)
- sequential rerun `npm test` — PASS; 1 file, 4 tests
- `npm run build` — PASS

Docker from repository root:

- `docker compose config` — PASS
- `docker compose build` — PASS
- `docker compose up --build --detach` — PASS
- all three services healthy — PASS
- `/health` alive, `/ready` ready with pgvector 0.8.1, `/version` 0.2.0 Phase 02 — PASS
- frontend HTTP 200 and `/api/ready` 200 — PASS
- `docker compose exec backend alembic current` — PASS; `20260819_0002 (head)`
- a concurrent host-side integration rerun while the full stack was up failed with `MemoryError`;
  after `docker compose down` and db-only restart, `uv run pytest -m integration` — PASS; 12/12
- `docker compose down` — PASS
- `git diff --check` — PASS (CRLF/LF conversion warnings only; no whitespace errors)

Independent follow-up verification remains pending. Phase 02 remote CI is not claimed because this
branch has not been pushed.

## Current next safe step

Independent follow-up verification of these Phase 02 corrections before any manual Git stage,
commit, push, or pull-request action. Do not begin Phase 03 without separate explicit authorization.
