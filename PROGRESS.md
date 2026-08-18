# Progress and Decision Log

## Current state

- **Current phase:** Phase 01 — complete
- **Implementation status:** verified development foundation only
- **Application capabilities implemented:** liveness, dependency readiness, version/phase metadata,
  async database/session foundation, pgvector migration, React status shell, local Compose stack,
  tests, quality tooling, and CI definition
- **Dependencies installed by this work:** locked Python and npm dependencies recorded below
- **Application or test commands available:** exact verified commands are recorded below and in
  `README.md`
- **Git write operations performed by the agent:** none
- **Phase 01 status:** PASS — local and container exit gates verified
- **Remote CI status:** FAILED / FIX PENDING — attempt 1 frontend passed; backend readiness test
  exposed a Linux connection-refusal translation defect; local fix verified but not pushed/rerun
- **Phase 02 readiness:** NOT AUTHORIZED; do not begin Task 1 business logic
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
- Remote CI attempt 1 is **FAILED / FIX PENDING**. Frontend passed; the backend Linux readiness
  defect is fixed and locally verified but requires a candidate push and successful GitHub rerun.
- Major-version GitHub Action references are used; immutable action SHA pinning is not yet applied.
- Docker image tags are version-pinned, while registry content trust/signature enforcement is not
  configured.
- No business capability from Task 1 is present, including business schema, graph, checkpoints,
  review, ingestion, MCP operations, model gateway, or watcher.

### Phase 01 conclusion

Phase 01 local/container exit gate: **PASS** after applying and verifying the independent verifier's
`PASS_WITH_CHANGES` corrections, with zero critical findings. This status includes the
candidate-side formatting failure and remains PASS only because canonical formatting was applied
and the full affected frontend gate passed on rerun. Remote CI attempt 1 is
**FAILED / FIX PENDING** until the locally verified backend fix is pushed and rerun; fresh-clone
Behavior 6 remains `NOT_STARTED`, and Phase 02 must not begin without separate candidate
authorization.

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

- Mixed-format ingestion/classification — `NOT_STARTED`
- Contradiction surfacing — `NOT_STARTED`
- Honest no-findings result — `NOT_STARTED`
- Configuration-only rule/domain change — `NOT_STARTED`
- Focused incremental processing — `NOT_STARTED`
- Incremental affected/preserved IDs, stages, operation keys, source versions, and before/after hashes — `NOT_STARTED`
- Source-attributed change history — `NOT_STARTED`
- Second different corpus — `NOT_STARTED`

Detailed movement items may be cut with explicit rationale while keeping understand, examine, and stay alive genuinely represented.

### Behaviors 6–10 strong differentiators

Each is a **Strong differentiator — may be cut only with explicit rationale if time forces a trade-off.**

- Fresh-clone local/container command — `NOT_STARTED`
- Real keyless tests — `NOT_STARTED`
- Document prompt-injection defense — `NOT_STARTED`
- Concurrent distinct/same-corpus isolation — `NOT_STARTED`
- Stage timing/usage/cost basis — `NOT_STARTED`

### Additional prioritized engineering evidence

- Idempotent duplicate operations — `NOT_STARTED`
- Costly external-call ambiguous-outcome reconciliation — `NOT_STARTED`
- Cause/remedy dependency failures and resumability — `NOT_STARTED`
- Working fallback/retry/skip/escalation paths, without unproven fallback claims — `NOT_STARTED`
- Streamed large-file upload — `NOT_STARTED`
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

- The repository contains a verified Phase 01 development foundation only.
- Only foundation architecture has been validated against runtime behavior; all Task 1 business
  architecture remains planned.
- CPython 3.13.14 is pinned and verified through uv/containers; the host's Python 3.14.4 remains
  installed but is not the project runtime.
- PDF/DOCX locator fidelity is not yet proven.
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
- Remote CI attempt 1 is **FAILED / FIX PENDING**; frontend passed, while the backend fix remains
  candidate-controlled and has not yet been pushed/rerun.
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

Phase 01 verification status: **PASS — local quality, real PostgreSQL/pgvector integration,
container startup/migration/readiness, rendered frontend, and cleanup gates completed.**

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

The candidate reviews the focused backend fix, performs Git writes personally, and reruns GitHub
CI. Remote status remains **FAILED / FIX PENDING** until the backend job passes. Do not begin Phase
02 or Task 1 business logic without separate explicit authorization.
