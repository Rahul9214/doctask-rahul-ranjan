# Project Assurance Register

## Current status

**Phase 00: documentation only.**

Implemented:

- The Task 1 engineering contract is recorded in `TASK.md`.
- Decisions, assumptions, progress, and limitations are recorded in `PROGRESS.md`.
- The proposed architecture is recorded in `docs/architecture.md`.

Not implemented:

- No application code, dependency manifest, database schema, migration, backend, frontend, MCP server, watcher, model integration, container definition, test, measurement, build, or deployment exists yet.
- FastAPI, LangGraph, PostgreSQL/pgvector, React/TypeScript, MCP, durable resume, concurrency controls, incremental processing, human review, and all evidence scenarios are **planned capabilities**, not current capabilities.
- There is currently no application command to run, test, lint, typecheck, build, deploy, smoke-test, or clean up.

This distinction must remain truthful as development proceeds. A capability moves from **planned** to **implemented** only after executable evidence passes and the result is recorded in `PROGRESS.md`.

## Pre-build assignment prerequisites

Before Phase 01 implementation, the candidate must complete:

- use SuperDocs on authorized non-confidential work, including the initial warm-up instruction, upload, targeted edit request, human review, and export; and
- read `docs.superdocs.app` and the relevant API/MCP documentation.

These are assignment prerequisites outside this repository. Recording their confirmation here is our process choice, not an assignment-mandated artifact. They are not currently recorded as complete.

## Task 1 objective

Build an agentic system that owns a related document pile through three movements:

1. **Understand:** classify mixed-format documents, extract important facts, identify disagreements, and propose a grounded Project Assurance Register whose claims resolve to exact source locations.
2. **Examine:** evaluate sources and the proposed register against user-supplied assurance rules in visible stages, producing grounded findings or an explicit, honest no-findings result.
3. **Stay alive:** detect arriving source versions, process only affected register items, preserve unaffected items exactly, surface new conflicts, and retain an attributable change history.

The explicit non-cuttable floor is: visible path-changing stages, durable process-kill recovery, a real item-level human review gate, complete machine operation, and no unsupported claims presented as facts. MCP is our chosen strongest machine-interface shape, not the only interface the assignment allows.

Understand, examine, and stay alive must each remain genuinely represented. A defended cut inside a movement is allowed; every detailed sub-feature is not individually non-cuttable.

## Proposed domain and deliverable

The proposed domain is **Software Project Assurance**.

The synthetic corpus will represent fictional software projects using documents such as:

- project charters;
- delivery plans;
- architecture decision records;
- weekly status reports;
- RAID logs; and
- meeting minutes.

The grounded deliverable will be a **Project Assurance Register** with stable item IDs and fields for assurance area, status/claim, evidence, exact source locators, confidence, contradictions or gaps, rule findings, review state, and change attribution.

The planned initial format contract is text-based PDF, DOCX, Markdown, and plain text. Scanned-image OCR, handwriting, spreadsheet output, and arbitrary document formats are not in the initial scope. CSV is considered only after the five non-cuttable behaviors and core movement evidence are green.

## Planned technology and architecture

Assignment requested/preferred:

- Python and FastAPI;
- an agent orchestration framework such as LangGraph or LangChain;
- PostgreSQL with vector search; and
- React.

The assignment allows comparable orchestration/tools when justified.

Our chosen implementation:

- Python;
- FastAPI;
- LangGraph;
- PostgreSQL with pgvector;
- React with TypeScript; and
- MCP as the strongest chosen machine-interface shape.

The proposed shape is a modular monolith with API, worker, watcher, MCP, and frontend process roles sharing one application core and PostgreSQL source of truth. It deliberately excludes Kubernetes, Terraform, Kafka, Redis, Celery, and microservices.

The first concurrency design will use the simplest PostgreSQL-backed durable mechanism that proves checkpoint resume, idempotency, run isolation, and safe publication. A full transactional-outbox pattern is not committed to and will be introduced only if implementation evidence shows it is necessary.

See `docs/architecture.md` for the planned graph, trust boundaries, provenance model, human gate, durability approach, and incremental-update algorithm.

## Current assumptions and architectural trade-offs

These are current planning decisions, not measured implementation results:

- **Grounding:** source claims use immutable source/hash plus native locator, span, and quote. Deliverable-grounded findings use `register_version_id`, `register_item_id`, `field_path`, `value_hash`, and `exact_value`, resolved against the immutable register version before support is accepted.
- **Durability:** start with PostgreSQL checkpoints, durable operation records, idempotency keys, and short publication locks. This favors simplicity now while leaving room for a transactional outbox only if evidence later requires one.
- **Incremental work:** stable register item IDs and affected-set planning reduce expected model work and latency for updates, at the cost of conservative dependency tracking and more validation logic.
- **Retrieval:** pgvector improves recall, while deterministic locator validation remains authoritative. This adds database setup but prevents semantic similarity from being mistaken for evidence.
- **Model boundary:** one provider-neutral gateway and deterministic test adapter control cost and enable keyless evidence. Multiple provider integrations are deferred to avoid complexity.
- **Deployment:** local/container reproducibility minimizes money and setup variance. Hosted deployment is deferred until the mandatory floor and evidence are green.
- **Watcher:** simple stable-file polling buys implementation speed and debuggability; it may add update latency compared with event-driven infrastructure but can later be replaced behind the same ingestion operation.
- **Growth:** a modular monolith keeps current operational cost and cognitive load low while preserving service boundaries that can be separated only when measured load or reliability needs justify it.

For costly external calls, the planned crash-window protocol persists an operation key and attempt before the call, uses provider idempotency when available, persists the structured result before graph advancement, and reuses durable completed results on resume. It retries only when non-completion is known. An unknowable provider outcome becomes an honest ambiguous state for reconciliation/retry; exactly-once behavior is not claimed.

For model or external-dependency failures, planned demonstrated paths will use a working deterministic fallback, bounded retry, safe skip, or human escalation where implemented and tested. If no safe fallback exists, the system will preserve durable state, expose cause and remedy, remain resumable, and not falsely report success. No fallback is currently implemented or claimed.

## Required human review flow

The demonstrated acceptance path must be:

```text
agent proposes
→ WAITING_FOR_REVIEW
→ human reviews
→ human explicitly approves/rejects individual items
→ decision is submitted through a UI/API/MCP operation
→ workflow resumes
→ only approved items are applied
```

MCP/API will expose explicit item-level approval and rejection operations. A program can drive the flow, but the acceptance demonstration uses a real human decision. No RBAC or proposer/reviewer identity-separation requirement is added; the demonstrated path simply does not let the proposing agent automatically approve its own proposals.

## Evidence target

The five non-cuttable behaviors require executable evidence for:

- visible conditional retry, skip, and escalation stages;
- unsupported claims that remain explicitly unsupported;
- mixed item-level approval and rejection;
- process kill followed by durable resume;
- an end-to-end machine-driven flow through our chosen MCP/API surface with an explicit gate operation; and
- exact source/register provenance plus success only for verified durable state.

The current movement evidence plan also targets:

- surfaced contradictions;
- a clean corpus that honestly produces no findings;
- a changed assurance rule/configuration that alters behavior without a code rewrite;
- focused incremental processing;
- an incremental proof comparing affected item IDs, preserved item IDs, executed stage IDs, model-operation/idempotency keys, processed source versions, and canonical before/after hashes; and
- a second run using different documents inside the declared domain and formats.

Understand, examine, and stay alive must each remain genuine, but any cut to these detailed targets is allowed with explicit rationale.

Planned behaviors 6–10 are each classified as: **Strong differentiator — may be cut only with explicit rationale if time forces a trade-off.**

- stranger-to-working-system in minutes with one documented command;
- real tests that run without a live key;
- document prompt-injection resistance;
- concurrent run isolation, including same-corpus races; and
- per-stage timing, usage, retries, and honest cost reporting.

For the planned keyless evidence, a deterministic model adapter may control model-boundary responses, but tests will still exercise real graph transitions, parsers, PostgreSQL/pgvector, process boundaries, API/MCP contracts, transactions, and deterministic validators. Raw measurement data will be committed to the repository.

## Data and security rules

- Use only synthetic or public documents in this repository, its tests, and its demonstrations.
- Never include employer/NDA material, third-party private files, real personal health data, or real prospect documents.
- Treat source documents as untrusted data, never as instructions to the system.
- Keep credentials out of source, Git, logs, shell history, screenshots, test artifacts, and error payloads.
- Stream large uploads to durable storage rather than reading entire files into memory.
- Keep every corpus, source, run, checkpoint, and publication isolated by identity.
- Do not claim certifications, guaranteed redaction, or other unsupported assurances.
- Do not include prompt injection aimed at evaluators or review tools.

## Hosted deployment position

Hosted deployment is not explicitly required by Task 1. Our minimum acceptance target is a reproducible local/container deployment. Hosted deployment will be attempted only after all mandatory Task 1 behaviors and evidence are green.

## Candidate execution constraint and project planning assumption

The assignment PDF does not impose this engineering-hour schedule. Our candidate execution constraint is a hard ceiling of 24 hours:

- Phases 01–10 target approximately **19.5 hours**.
- The remaining **4.5 hours are protected buffer** for debugging, verification, evidence, and final audit.

If cuts are needed, use this order:

1. UI polish;
2. hosted deployment;
3. CSV;
4. multiple model providers;
5. elaborate observability UI;
6. sophisticated watcher implementation; and
7. extra format breadth.

Never cut the five explicit floor behaviors: visible path-changing stages, durable resume, item-level human gate, machine-driven flow, or no-bluffing. Understand, examine, and stay alive must each remain represented at genuine minimum depth, while detailed sub-features inside them may be cut with explicit rationale. Behaviors 6–10 remain prioritized strong differentiators and may be cut only with explicit rationale if time forces a trade-off.

## Phase plan

- **Phase 01 — development foundation (1.25h):** verified manifests, environment schema, container topology, health checks, command contract, and safe configuration.
- **Phase 02 — corpus, ingestion, and provenance (2h):** two synthetic corpora, streamed ingestion, hashing, parsers, locators, normalization, and pgvector indexing.
- **Phase 03 — understand workflow (2.25h):** visible classification, planning, extraction, validation, contradiction, unsupported-claim, and conditional branch behavior.
- **Phase 04 — examine workflow (1.5h):** rules as data, staged checks, grounded findings, and explicit no-findings semantics.
- **Phase 05 — human review gate (1.5h):** immutable proposals, `WAITING_FOR_REVIEW`, real human mixed decisions, and approved-only publication.
- **Phase 06 — durable resume and concurrency (1.75h):** PostgreSQL checkpoints/jobs, idempotency, kill/resume, run isolation, and safe publication.
- **Phase 07 — incremental watched updates (2h):** simple watched inbox, source versioning, affected-item planning, focused updates, unchanged proof, and change ledger.
- **Phase 08 — React review UI and MCP (2.25h):** essential review/timeline/provenance UI and explicit machine operations over shared services.
- **Phase 09 — hardening, adversarial tests, and measurements (2.5h):** non-cuttable-floor scenarios plus prioritized differentiator scenarios; raw measurement data will be committed to the repository.
- **Phase 10 — local deployment, evidence, and final audit (2.5h):** fresh-clone proof, production builds, second corpus, secrets/log review, runbook, limitations, and acceptance audit.

These phase estimates total 19.5 hours. The 4.5-hour reserve is not preallocated feature time.

## Commands

No repository application commands exist during Phase 00, so none are claimed here.

Phase 01 must create and execute a precise command contract covering:

- prerequisites;
- dependency installation;
- environment setup;
- database and migrations;
- backend and frontend;
- Docker;
- lint and formatting checks;
- Python and TypeScript typechecks;
- unit, integration, and E2E tests;
- production builds;
- smoke tests; and
- cleanup.

Only commands that actually exist in the repository and have been verified may be added here. Git write commands are always supplied for the candidate to run manually and are never executed by a coding agent.

## Repository and submission

- Task 1 stays in the private repository `doctask-rahul-ranjan`.
- The repository name must not contain “SuperDocs”.
- The candidate must verify privacy, invite the exact collaborator `o-kadam`, and submit the repository URL through the official form.
- Task 1 solution details stay out of public/shared candidate channels during the round.
- Task 2, Task 3, Task 4 deliverables, and extra credit are outside this implementation scope.

## Documentation

- `TASK.md` is the persistent contract for future coding agents.
- `PROGRESS.md` is the chronological implementation, assumption, command, evidence, and limitation record.
- `docs/architecture.md` describes the planned architecture and must be updated when evidence changes a design decision.
