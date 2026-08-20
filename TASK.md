# Task 1 Persistent Engineering Contract

## Authority and scope

The original SuperDocs engineering assignment is the authoritative source of truth. This file is a concise persistent contract for coding agents working only on **Task 1 — Build an Agentic System**.

Global assignment instructions apply when they affect Task 1, including conduct, data/security, engineering quality, repository/submission rules, and what separates strong submissions.

Do not implement Task 2, Task 3, Task 4, or extra credit. Task 4 video/write-up/diagram deliverables are outside scope; Task 1 must still retain the engineering evidence and repository documentation needed to verify its own claims.

## Current implementation state

Phases 01, 02, 03, 04, and 05 implement and locally verify the development foundation, the
deterministic grounded-data layer, the Understand movement, the Examine movement, and the item-level
human review gate: corpus-scoped source versions/blocks that are immutable by application contract,
streamed SHA-256 ingestion, PDF/DOCX/Markdown/TXT parsers, normalized blocks, exact citation
validation, local file storage, deterministic pgvector retrieval, a configurable model boundary with
a keyless deterministic adapter, a LangGraph Understand workflow, classification, grounded fact
extraction, contradiction detection, unknown/insufficient-evidence representation, inspectable
analysis-run APIs, a versioned assurance ruleset, a LangGraph Examine workflow, inspectable
examination-run APIs, explicit review sessions/items/decisions with row-level transactional locking
and authoritative count recomputation, explicit edit acknowledgement, and a minimal review UI.
Database-level mutation-prevention triggers or restricted roles are not implemented.

MCP business server, watcher, durable workflow resume, incremental processing, register publication,
and a full measurement system are not implemented yet.

Never describe a planned capability as implemented. Update `README.md` and `PROGRESS.md` only after executable evidence proves the capability.

## Operating rules

### Git

The candidate personally controls all Git write operations.

Agents must not execute:

- `git init`;
- `git add`;
- `git commit`;
- `git push` or `git pull`;
- `git checkout` or `git switch`;
- `git merge` or `git rebase`;
- `git reset` or `git stash`;
- `git tag`;
- pull-request creation or merging; or
- remote modifications.

Read-only Git inspection is allowed. Whenever Git work is needed, provide exact commands for the candidate to execute manually and do not execute them.

### Commands

For every implementation phase, give the candidate exact, repository-verified terminal commands for all applicable prerequisites, dependency installation, environment setup, database operations, migrations, backend, frontend, Docker, lint, formatting, Python typecheck, TypeScript typecheck, unit tests, integration tests, E2E tests, production builds, smoke tests, cleanup, and manual Git operations.

Do not invent npm scripts, CLI commands, Make targets, package names, or files. Inspect the repository first and quote only commands that exist and have been verified.

### Documentation discipline

- `TASK.md` remains the persistent contract.
- `PROGRESS.md` records dated assumptions, decisions, exact commands/results, evidence, defects, limitations, and next safe step.
- `README.md` is the reviewer-facing truthful runbook and capability summary.
- `docs/architecture.md` records the actual current design and reasons; change it when implementation evidence changes the design.
- Do not create a proliferation of planning documents.

### Pre-build assignment prerequisites

Before Phase 01, the candidate must complete:

- genuinely use SuperDocs on authorized non-confidential work, including a small warm-up instruction, upload, targeted edit request, human review, and export; and
- read `docs.superdocs.app` and the relevant API/MCP documentation.

These are assignment prerequisites outside the repository. Recording confirmation in `PROGRESS.md` is our process choice, not an assignment-mandated artifact, and must not be marked complete without candidate confirmation.

## Proposed product

### Domain

Software Project Assurance using synthetic fictional project documents only.

### Grounded deliverable

A Project Assurance Register containing stable structured items for project controls, status, evidence, contradictions/gaps, assurance findings, exact citations, human decisions, and source-attributed changes.

### Initial declared formats

- text-based PDF;
- DOCX;
- Markdown; and
- plain text.

Scanned-image OCR, handwriting, spreadsheet output, and arbitrary formats are excluded initially. CSV is optional only after the five-behavior floor and genuine movement evidence are green.

## The three required movements

### 1. Understand

The system must:

- ingest related documents in the declared mixed formats;
- determine each document’s type;
- extract material facts;
- identify disagreements among sources;
- propose one grounded Project Assurance Register; and
- make every supported claim resolve to an exact immutable source location.

### 2. Examine

The system must:

- accept user-supplied assurance rules as versioned data/configuration;
- check both the sources and proposed register in visible stages;
- produce findings with exact source or deliverable locations;
- distinguish violated, satisfied, not-applicable, and unsupported rules honestly; and
- produce an explicit no-findings result only after the applicable rule set was actually evaluated.

### 3. Stay alive

The system must:

- watch a location for new document/source versions;
- deduplicate arrivals;
- identify affected register entities and rules;
- process only affected work rather than disguising a full rerun as an update;
- preserve unaffected register items exactly and prove that with canonical bytes/hashes;
- surface new contradictions without silently choosing a winner;
- retain what changed, when, and because of which source; and
- put proposed updates through the same human gate before publication.

All three movements must remain represented at genuine minimum depth. The assignment permits defended cuts inside the movements, so every detailed sub-feature above is not independently non-cuttable.

## Five non-cuttable behaviors

### 1. Observable, path-changing agency

Stages and decisions must be visible. Real conditional edges must support bounded retry, safe skip, and escalation to review. One model call wrapped in UI and a fixed script with stage labels are unacceptable.

### 2. Durable interruption recovery

Killing a process mid-run and restarting it must continue from the last completed durable checkpoint. Finished work and review state must survive. Durable completed operation results must be reused; unknowable external-call outcomes must enter honest reconciliation rather than being described as exactly-once.

### 3. Real item-level human gate

The demonstrated acceptance path is:

```text
agent proposes
→ WAITING_FOR_REVIEW
→ human reviews
→ human explicitly approves/rejects individual items
→ decision is submitted through a UI/API/MCP operation
→ workflow resumes
→ only approved items are applied
```

One review may mix approvals and rejections. Rejecting one item must not discard approved siblings. No RBAC or proposer/reviewer identity separation is added as an assignment requirement; the demonstrated path must not let the proposing agent automatically approve its own work.

### 4. Machine-driven end-to-end flow

Machine-interface operations must let another program create and inspect a run, obtain pending review items, submit explicit item-level decisions, resume processing, and verify the published result without UI clicks. MCP is our strongest chosen interface shape.

The machine interface exposes the gate; it never bypasses it. Although a program may submit decisions when explicitly directed, the demonstrated acceptance flow must use a real human review decision.

### 5. No bluffing

Unsupported claims must be labeled unsupported or withheld. Every supported claim/finding must pass provenance validation. Success is emitted only after the asserted durable state is verified.

These five behaviors are the explicit non-cuttable floor. Understand, examine, and stay alive must all remain represented, but defended cuts are allowed inside those movements.

## Stack classification

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
- MCP as the strongest chosen machine-interface shape, not an absolute assignment mandate.

Use a modular monolith with multiple process roles from one codebase. Do not introduce Kubernetes, Terraform, Kafka, Redis, Celery, microservices, or similar infrastructure unless a measured implementation blocker proves it necessary.

Hosted deployment is not explicitly required by Task 1. Our minimum acceptance target is a reproducible local/container deployment. Hosted deployment will be attempted only after all mandatory Task 1 behaviors and evidence are green.

## Architecture constraints

- PostgreSQL is the planned durable source of truth for runs, checkpoints, jobs, idempotency, source metadata, facts, findings, reviews, versions, and audit history.
- Begin with the simplest PostgreSQL-backed durable mechanism that proves resume, idempotency, concurrent-run isolation, and safe publication.
- Do not commit to a full transactional-outbox pattern. Add one only if implementation evidence proves the simpler design insufficient.
- Stream large uploads to durable file storage and reference immutable content hashes.
- Use pgvector to improve retrieval recall, never as provenance.
- Keep deterministic validators around grounding, schema validity, review authorization, and publication.
- Treat documents as untrusted data. Document text cannot alter system instructions, call tools, approve proposals, or exfiltrate secrets.
- Keep corpus/source/run/version identity in every storage operation.
- Use stable item IDs and canonical serialization so unchanged-content claims can be proven exactly.
- Keep MCP and React as adapters over the same application services and authorization/gate rules.
- Prefer a simple stable-file polling watcher over sophisticated filesystem infrastructure unless evidence requires more.
- For a costly external call, persist the operation key and attempt before calling, use provider idempotency when available, persist the returned structured result before graph advancement, and reuse durable completed results on resume.
- Retry a costly external call only when non-completion is known. If the provider outcome is unknowable, record an honest ambiguous state and reconcile/retry rather than claiming exactly-once behavior.

## Exact provenance contracts

A valid source citation must contain:

- immutable source version ID;
- source SHA-256;
- format-native locator such as page/block, paragraph, or table cell;
- normalized character span where available; and
- exact quoted evidence.

Publication validation must resolve the locator against the immutable source version and confirm the quote/span. A page number alone is not exact provenance.

A valid deliverable-side citation for a register-grounded finding must contain:

- `register_version_id`;
- `register_item_id`;
- `field_path`;
- `value_hash`; and
- `exact_value`.

Validation must resolve this locator against the immutable register version before a deliverable-grounded finding is treated as supported.

## Behaviors 6–10 — strong differentiators

Each item below is classified: **Strong differentiator — may be cut only with explicit rationale if time forces a trade-off.**

- **Behavior 6:** a stranger can go from fresh clone to working local/container system in minutes with one documented, verified command.
- **Behavior 7:** keyless tests prove real system behavior rather than only model mocks.
- **Behavior 8:** prompt injection inside documents is treated as data and tested adversarially.
- **Behavior 9:** concurrent distinct and same-corpus runs remain isolated.
- **Behavior 10:** runs report per-stage elapsed time, attempts, model/token usage, and honest estimated cost with pricing basis.

These remain planned and prioritized; they are not part of the explicit non-cuttable floor.

Additional qualities to retain where possible:

- Architecture favors honesty, surgical precision, configuration over code, proof over assertion, and graceful re-entry.

## Global engineering standards

- Errors state the cause and an actionable fix.
- Costly operations are idempotent.
- Large files use streamed upload paths rather than whole-file memory loading.
- Model/external dependency failures must use a working deterministic fallback, bounded retry, safe skip, or human escalation where that path is implemented and tested.
- If no safe fallback exists, preserve durable state, expose cause and remedy, remain resumable, and do not falsely report success. No fallback is claimed before executable proof exists.
- Record trade-offs in latency, cost, simplicity, and room to grow.
- Investigate before fixing and close the defect class, including sibling cases.
- Do not delete a capability to hide a bug or defer a failure and call it fixed.
- Deterministic hard defenses are valid alongside model reasoning.
- Safety must not gain correctness by wrongly refusing valid work.
- Measurements state method before result, report variance and tail behavior, and admit limitations. Raw measurement data will be committed to the repository.
- Verify a second run on different documents inside the declared domain/format set.

## Data, security, and conduct

- Repository, fixtures, screenshots, and demonstrations use synthetic/public data only.
- Never use confidential/NDA employer material, third-party private files, real health data, or real prospect documents.
- The service location and privacy implications must be considered before any external upload.
- Never place keys in code, Git, logs, shell history, screenshots, test artifacts, or error payloads.
- Redaction, if added, remains human-reviewed and is never presented as audited or guaranteed.
- Do not claim certifications that are not held.
- Do not build prompt injection aimed at evaluators or review tools.
- Disclose automation honestly; no fake users, reviews, engagement, or identity.

## Repository and submission constraints

- Keep Task 1 in the private repository named `doctask-rahul-ranjan`; do not put “SuperDocs” in the repository name.
- The candidate must verify privacy, invite exact collaborator `o-kadam`, and submit the repository URL through the official form.
- Keep Task 1 solution details out of public/shared candidate channels during the round.
- Use email only for genuine questions/blockers and bug reports; the official form is the submission route.
- The candidate owns the repository and executes every Git write operation.
- Keep secrets and private data out of repository history.

## Executable acceptance evidence

### Non-cuttable floor

The final evidence suite must prove the five explicit floor behaviors:

- [ ] visible stage decisions and conditional retry/skip/escalation paths;
- [x] a real human supplies mixed item-level approve/reject decisions;
- [ ] only approved items are published;
- [ ] a killed real worker process resumes without lost or duplicated completed work;
- [ ] the machine interface drives the full flow and exposes explicit item-level review operations; and
- [ ] unsupported claims remain unsupported, supported claims/findings resolve against immutable source or register locators, and success is reported only for verified durable state.

### Planned movement evidence

Understand, examine, and stay alive must each be genuinely represented. The current plan targets:

- [x] mixed-format ingestion and deterministic declared-format validation;
- [x] document classification reasoning;
- [x] surfaced contradictions with all sides cited;
- [x] a clean, fully evaluated corpus returns an honest no-findings result;
- [ ] changing a rule/domain configuration changes behavior without a code rewrite;
- [ ] new content triggers focused incremental processing;
- [ ] change history answers what changed, when, and because of which source;
- [ ] incremental proof compares affected item IDs, preserved item IDs, executed stage IDs, model-operation/idempotency keys, processed source versions, and canonical before/after hashes; and
- [x] a second different corpus succeeds without corpus-specific code changes.

A cut inside these movement details is allowed only with explicit rationale while preserving a genuine minimum of each movement.

### Planned strong-differentiator evidence

Each item below is a **Strong differentiator — may be cut only with explicit rationale if time forces a trade-off.**

- [ ] Behavior 6: fresh-clone setup reaches a working system in minutes with one verified command.
- [ ] Behavior 7: real keyless tests exercise the system, not only model mocks.
- [ ] Behavior 8: document prompt injection cannot alter policy, call tools, or self-approve.
- [ ] Behavior 9: concurrent distinct and same-corpus runs remain isolated and publish safely.
- [ ] Behavior 10: stage timing, attempts, usage, pricing basis, and honest cost are reported.

For planned keyless evidence, a deterministic model adapter may be used at the model boundary, while tests still exercise real LangGraph transitions, parsers, PostgreSQL/pgvector, subprocess restart, concurrency, API/MCP transport, transactions, and deterministic validators. Raw measurement data will be committed to the repository.

Additional prioritized evidence covers idempotent duplicate operations, graceful dependency failure, streamed large-file upload, exact lint/format/typecheck/test/build/smoke/cleanup commands, and all candidate claims.

## Candidate execution constraint and project planning assumption

The assignment PDF does not state this engineering-hour budget. Our candidate execution constraint is a hard ceiling of 24 hours.

- Planned Phases 01–10: approximately 19.5 hours.
- Protected debugging, verification, evidence, and final-audit buffer: approximately 4.5 hours.

Cut in this order:

1. UI polish;
2. hosted deployment;
3. CSV;
4. multiple model providers;
5. elaborate observability UI;
6. sophisticated watcher implementation; and
7. extra format breadth.

Never cut the five explicit floor behaviors: visible path-changing stages, durable resume, item-level human gate, machine-driven flow, and no-bluffing.

Understand, examine, and stay alive must each remain represented at genuine minimum depth. Detailed sub-features inside them may be cut with explicit rationale. Behaviors 6–10 remain prioritized strong differentiators and may be cut only with explicit rationale if time forces a trade-off.

## Phase plan and gates

### Phase 01 — development foundation (1.25h)

Create verified dependency manifests, environment schema, container topology, health checks, migrations foundation, safe configuration, and the exact command contract.

Target exit is a working local/container skeleton with every documented Phase 01 command verified. If the one-command differentiator is deferred, record explicit rationale without misreporting it as complete.

### Phase 02 — corpus, ingestion, and provenance (2h)

Create two realistic synthetic corpora and implement streamed ingestion, immutable hashes, parsers, stable locators, normalized blocks, and pgvector indexing.

Exit only when citation round-trips and tamper failures are executable.

### Phase 03 — understand workflow (2.25h)

Implement visible classification, planning, extraction, grounding validation, contradiction detection, unsupported claims, and conditional paths.

Exit only when the register is grounded and branching evidence is captured.

### Phase 04 — examine workflow (1.5h)

Implement versioned rules-as-data, staged checks, exact finding locators, deduplication, and explicit no-findings semantics.

Exit only when both violation and clean-corpus scenarios pass.

### Phase 05 — human review gate (1.5h)

Implement immutable proposal sets, `WAITING_FOR_REVIEW`, explicit mixed human decisions, and transactionally approved-only publication.

Exit only after a real human-driven acceptance flow has been demonstrated.

### Phase 06 — durable resume and concurrency (1.75h)

Implement PostgreSQL checkpoints/jobs, idempotency, process failpoints, resume, and run isolation using the simplest adequate mechanism.

Required exit is proven kill/resume. Concurrent same-corpus run isolation is implemented for independent workflow runs, checkpoints, and operation keys. Register publication remains later: a resumed run stops at the explicit human-review gate and does not apply approved items to a published register version. Concurrent same-corpus publication proof remains the planned Behavior 9 remainder and may be cut only with explicit rationale.

### Phase 07 — incremental watched updates (2h)

Implement a simple watched inbox, source versioning, affected-item planning, focused reprocessing, unchanged proof, conflict surfacing, and source-attributed ledger.

Exit only when the evidence compares affected/preserved item IDs, executed stage IDs, model-operation/idempotency keys, processed source versions, and canonical before/after hashes. Hash equality alone does not prove a full rerun was avoided.

### Phase 08 — React review UI and MCP (2.25h)

Implement the essential stage timeline, provenance, review controls, status/resume view, and machine operations over shared services.

Exit only when UI supports real human mixed decisions and MCP/API supports explicit gate operations end to end.

### Phase 09 — hardening, adversarial tests, and measurements (2.5h)

Run non-cuttable-floor scenarios and the prioritized race, injection, malformed-file, dependency-failure, duplicate, large-upload, no-findings, unsupported, and incremental scenarios. Raw measurement data will be committed to the repository.

Exit only when the five-behavior floor is green. Any omitted strong differentiator or movement detail must have explicit rationale and an honest limitation.

### Phase 10 — local deployment, evidence, and final audit (2.5h)

Target fresh-clone reproducible local/container deployment, production builds, second corpus, exact runbook, secrets/log safety, architecture consistency, and acceptance coverage. Behavior 6 remains a strong differentiator, not part of the explicit five-behavior floor.

Hosted deployment is attempted only if every mandatory behavior and evidence item is already green.

### Protected reserve (4.5h)

Not feature scope. Use only for debugging, verification, evidence repair, and final audit. If schedule slips, cut optional work in the mandated order before using reserve to add features.

## Minimum definition of done

The non-cuttable Task 1 floor is done only when:

- all five non-cuttable behaviors are implemented;
- understand, examine, and stay alive are each represented at genuine minimum depth, with any internal cuts explicitly defended;
- the real-human review acceptance path is demonstrated;
- every supported claim/finding resolves to exact immutable source or register evidence;
- process death resumes without losing finished work;
- the machine interface drives the flow and exposes explicit item-level approval/rejection operations;
- success messages match verified durable state;
- README distinguishes current capabilities from plans and lists honest limitations;
- architecture and progress records match the code and evidence;
- secrets/data constraints pass audit; and
- any remaining cuts are explicit and do not remove a non-cuttable requirement.

## Prioritized completion target

Behaviors 6–10, second-corpus proof, graceful degradation scenarios, incremental breadth, and the full reproducibility/evidence suite remain planned. Each behavior 6–10 item is a **Strong differentiator — may be cut only with explicit rationale if time forces a trade-off.** Their omission must not be hidden inside the minimum Definition of Done.
