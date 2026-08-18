# Progress and Decision Log

## Current state

- **Current phase:** Phase 00 — complete
- **Implementation status:** documentation only
- **Application capabilities implemented:** none
- **Dependencies installed by this work:** none
- **Application or test commands available:** none
- **Git write operations performed by the agent:** none
- **Phase 01 readiness:** READY, pending only explicit candidate authorization to begin implementation
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
- Lint/format/typecheck/test/build/smoke/cleanup command proof — `NOT_STARTED`

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

- The repository currently contains documentation only.
- No proposed architecture has been validated against code or runtime behavior.
- No exact package versions or project scripts have been selected or verified.
- The host currently has Python 3.14, which may not be supported by all planned packages; a supported container version must be selected from actual compatibility evidence.
- PDF/DOCX locator fidelity is not yet proven.
- LangGraph PostgreSQL checkpoint/interrupt behavior is not yet proven.
- Same-corpus publication locking and idempotency are not yet designed at schema level.
- The incremental impact algorithm is not implemented or measured.
- The MCP package/protocol choice is not verified.
- No live model provider is selected.
- No deterministic fallback, retry, safe-skip, escalation, or ambiguous-provider-outcome reconciliation path is implemented or tested.
- No hosted deployment is promised.
- SuperDocs familiarization and documentation prerequisites are complete by manual candidate confirmation; no repository artifact or runtime proof is claimed.

## Phase 01 entry criteria

Before Phase 01 implementation begins:

- [ ] Candidate explicitly authorizes Phase 01.
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

**Readiness: READY — pending only explicit candidate authorization to begin implementation.**

## Verification log

Phase 00 verification status: **PASS — authoritative assignment comparison completed; independent verifier findings incorporated at documentation level.**

This is documentation-level verification only. No runtime implementation verification is claimed.

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

No implemented application capability is claimed.

## Next safe step

Await explicit candidate authorization for Phase 01. Do not create application code, install dependencies, create backend/frontend directories, or execute Git writes without that authorization.
