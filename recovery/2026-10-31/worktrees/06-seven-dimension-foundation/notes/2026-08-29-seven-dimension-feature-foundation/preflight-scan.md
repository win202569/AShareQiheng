# Seven-Dimension Feature Foundation — SDD Pre-flight Scan

- Plan: `docs/superpowers/plans/2026-08-29-seven-dimension-feature-foundation.md`
- Binding spec: `docs/superpowers/specs/2026-08-29-seven-dimension-feature-foundation-design.md`
- Scan scope: Tasks 1–13, shared files, public interfaces, Global Constraints, and review-rubric test hygiene
- Authority rule: the design spec is binding; where the design contains two requirements that cannot both be literal, the smallest ruling preserving its safety properties is recorded below.
- Result: **7 findings — 5 Important, 2 Minor, 0 Critical**. The plan is executable after applying the rulings below.

## 1. Per-task internal consistency

| Task | Tests vs. implementation | Files and ordering | Result |
|---|---|---|---|
| 1 — Contract and hashing | RED/GREEN tests directly cover exact dimensions, non-formal gate, null/zero/non-finite handling, canonical ordering, evidence sensitivity, validation, and round-trip; implementation exposes the tested immutable types and serializers. | Both files are created in the task; no later-created helper is required. | **Consistent.** |
| 2 — Fact catalog, periods, registry | Period/fact identity/registry tests match the proposed contracts and safety rules; the candidate-industry fixture checks the production registry against tracked curated data. | All listed files are created together, but the module owning `TEMPLATE_VERSION` is not named even though schema and template code are separate. | **Minor finding F6.** Put `TEMPLATE_VERSION` in `industry_templates.py`; consumers import it there. |
| 3 — SQLite v2→v3 | DDL and constraint tests match the implementation, but the concrete migration regression seeds and compares only `run`, while the spec requires all pre-existing run/job/snapshot/score data to remain row-for-row unchanged. | `state_store.py`, its tests, and a literal v2 fixture are sufficient and correctly ordered. | **Important finding F3.** Expand the migration regression to seed/assert every existing v2 table. |
| 4 — Persistence | Idempotent facts, retained revisions, deterministic bundle conflict, transactional rollback, exact filters, path safety, and canonical issue JSON all exercise the stated APIs. | Correctly consumes Tasks 1–3 and modifies only the shared state-store/test files. | **Consistent**, conditional on F3's migration ruling. |
| 5 — Leases/follow-ups | Renewal ownership, wrong-owner transitions, atomic success/failure follow-ups, rollback, and idempotent insertion match the proposed transactional APIs; legacy delegates remain covered. | Correctly layers on the existing job table and the same Task 3/4 files. | **Consistent.** The plan relies on owner change after lease recovery to reject stale workers; no assertionless lease test is requested. |
| 6 — Snapshot repository | Exact request matching, revision ordering, tamper detection, reuse, ID lookup, and legacy/new path behavior match the public repository/read APIs. | New repository and tests plus the public `SnapshotStore` read method are self-contained. | **Consistent.** |
| 7 — Point-in-time facts | Normalization tests match most implementation rules, but selector precedence differs from the binding spec, and Task 13 retroactively requires Task 7 fixture-structure rejection without supplying the later helper. | Production/test/fixtures are created here; `tests/feature_fixture_helpers.py` is not available until Task 13 and imports Task 10. | **Important findings F1 and F4.** Apply both rulings before Task 7 dispatch. |
| 8 — Derived inputs/bundles | Formula, coverage, blocker propagation, template, seven-container, non-formal, and hash-sensitivity tests match construction, except the prose says an omitted statement key differs from explicit null while the required code normalizes both to the same explicit-null map. | Correctly extends Task 7's production/test files and consumes Tasks 1–2. | **Important finding F2.** Follow the spec and required code: all three keys are materialized; omission normalizes to explicit null. |
| 9 — One-statement source | One-call dispatch, unknown-dataset prevalidation, empty-result retry, and compatibility-wrapper tests directly match the implementation and preserve pilot callers. | Existing source/pilot files only; no premature worker dependency. | **Consistent.** |
| 10 — Candidate context/parent expansion | 1→3 and 120→360 expansion, idempotency, supersession, rollback, candidate-hash content, and no-network planning match the stated functions. | Creates `deep_worker.py` and its tests after all consumed constants/job APIs exist. | **Consistent.** |
| 11 — Worker/frozen builds | Remote-limit, partial success, frozen IDs/hashes, heartbeat, recovery, reuse, circuit, error taxonomy, retention, bounded output, offline builds, no-overwrite, and orphan cleanup tests align with the executor and file/DB protocol. | Correctly modifies Task 10 files and consumes Tasks 4–10. | **Consistent.** Frozen builds must filter facts by the frozen snapshot IDs supplied by Task 4, as implied by the spec and payload contract. |
| 12 — CLI/calendar/progress | Parser, dependency construction, cache verification, incremental enqueue, bounded remote calls, scoping, coverage/error taxonomy, formal gates, and reporting match the proposed interfaces. The two-candidate unit test expects denominator 2, while the production design/acceptance requires 120. | Orchestrator/reporting files are sufficient; calendar production is intentionally added after the parser/normalizer that consumes it. | **Minor finding F7.** Use current context size generically and enforce 120 in operational acceptance. |
| 13 — Hermetic replay/regression | E2E assertions verify determinism, traceability, offline behavior, blockers, all dimensions, no formal scores/pools, and full regression; helper implementations provide deterministic documents and direct DB inspection. | Correctly consumes all prior tasks, but fixture-structure validation is retroactively assigned to Task 7, and root `progress.md` is called an execution ledger despite SDD owning a different private ledger. | **Important findings F4 and F5.** Distinguish the two ledgers and carry Task 7's local fixture validator forward. |

## 2. Shared-file and public-interface producer → consumer checks

Each task pair below appears once. “Compatible” means the producer's declared shape is sufficient for the consumer; findings point to Section 3.

| Pair | Producer → consumer contract | Check |
|---|---|---|
| 1 → 2 | `canonical_sha256` → fact identity and registry/version artifacts | Compatible; both require canonical sorted JSON with NaN forbidden. |
| 1 → 3 | contract dimensions/states/units → `feature_set`/`feature_value` DDL checks | Compatible; SQL enums mirror Task 1 exactly. |
| 1 → 4 | `FeatureBundle`/canonical content → deterministic persistence | Compatible; logical key conflict is checked against canonical bundle hash/content. |
| 1 → 6 | `canonical_sha256` → request fingerprints and snapshot identity | Compatible. |
| 1 → 8 | bundle dataclasses/constants → seven-dimension bundle construction | Compatible; formal readiness remains hard-false. |
| 1 → 10 | canonical hashing → candidate-set and job keys | Compatible. |
| 1 → 11 | `FeatureBundle` serialization → atomic bundle write/read | Compatible; canonical bytes are the no-overwrite comparison unit. |
| 1 → 13 | contract types/hash helpers → fixture documents and E2E bundle checks | Compatible. |
| 2 → 3 | `FinancialFact` fields/enums → `financial_fact` DDL | Compatible; `FY/H1/Q1/Q3/OTHER`, nature, units, and snapshot FK align. |
| 2 → 4 | `FinancialFact` records → insert/list APIs | Compatible; revision identity and exact snapshot filtering are preserved. |
| 2 → 7 | mapping rules/period classification → fact normalization | Compatible except version ordering is governed by F1. |
| 2 → 8 | template registry/version → applicable slots, blockers, coverage, input hash | Compatible after F6 assigns `TEMPLATE_VERSION` to the registry module. |
| 2 → 9 | statement dataset names/request version → isolated AKShare method dispatch | Compatible; exactly the same three dataset strings are used. |
| 2 → 10 | request/mapping constants → child payloads and keys | Compatible. |
| 2 → 11 | fact/request versions → normalization and frozen-build execution | Compatible; frozen payload hashes versions through Task 8. |
| 2 → 12 | `FINANCIAL_REQUEST_VERSION` → daily-job scoping/progress | Compatible; first-enqueue candidate hash is audit-only, request version is the scope key. |
| 2 → 13 | registry/fact semantics → bank/industrial/real-estate fixtures | Compatible if Task 7's structural validator enforces all required periods/fields (F4). |
| 3 → 4 | v3 tables → fact/bundle persistence methods | Compatible after F3 proves migration preservation. Shared `state_store.py` and `tests/test_state_store.py` edits are sequential. |
| 3 → 5 | v2 job table retained through v3 → owned lease/follow-up methods | Compatible; migration is additive. Shared files are sequential. |
| 3 → 11 | v3 fact/feature tables → worker persistence | Compatible through Task 4 APIs. |
| 3 → 12 | v3 job/feature tables → scoped status queries | Compatible; status must not use historical score rows as current progress. |
| 3 → 13 | `feature_set` schema → test helper's direct latest-row query | Compatible for the fresh hermetic DB; helper is inspection-only. |
| 4 → 5 | shared `StateStore` transaction machinery → atomic job transitions | Compatible; follow-up transitions do not overlap feature persistence semantics. |
| 4 → 11 | insert/list facts, put/get/latest bundles, quality issues → worker | Compatible; worker must list facts with exact frozen snapshot IDs. |
| 4 → 12 | feature rows/quality/job data → progress and reporting | Compatible; scope by current candidate hash/contract/request version. |
| 4 → 13 | fact lookup and feature rows → evidence traceability assertions | Compatible. |
| 5 → 10 | `JobSpec` and atomic completion → legacy-parent expansion | Compatible; succeeded parent cannot coexist with a partial child set. |
| 5 → 11 | renewal and success/failure-with-followups → heartbeating statement worker | Compatible; one state transition and its feature follow-up share a transaction. |
| 6 → 7 | verified `FetchBatch`/snapshot IDs → normalization evidence | Compatible; Task 7 remains pure and receives the verified batch externally. |
| 6 → 11 | exact `SnapshotRef`/verified read → frozen statement/calendar execution | Compatible; enqueued builds use `get(id)` plus frozen hash, never `find_exact()`. |
| 6 → 12 | exact repository/cache verification → CLI dependencies and progress | Compatible; tampered exact cache fails closed. |
| 6 → 13 | repository persist/get/read → hermetic evidence traversal | Compatible. |
| 7 → 8 | selected facts and blockers → derived features/status | Compatible after F1; blockers flow verbatim and only FY/H1 are consumed. |
| 7 → 11 | normalization/calendar parser → statement execution and fact persistence | Compatible after F1/F4. |
| 7 ↔ 12 | Task 12 long calendar `FetchBatch` → Task 7 `trading_days_from_batch()` | Compatible if the calendar request spans the mandated interval and is verified; no weekday synthesis. |
| 7 → 13 | fixed financial/calendar fixtures → hermetic replay | Compatible after Task 7 owns structural rejection locally (F4). |
| 8 → 11 | `feature_input_hash`/`build_feature_bundle` → frozen feature jobs | Compatible after F2; every dependency is frozen, all statement keys explicit. |
| 8 → 12 | feature statuses/blockers/version → scoped progress | Compatible; financial readiness is not formal seven-dimension readiness. |
| 8 → 13 | deterministic bundles → byte equality/non-formal E2E assertions | Compatible. |
| 9 → 11 | `FinancialStatementSource`/one-table fetch/error taxonomy → remote executor | Compatible; one leased statement produces at most one remote statement request. |
| 9 → 12 | default/injected AKShare source → `deep --online` dependencies | Compatible; construction is confined to the online dependency helper. |
| 9 → 13 | `FetchBatch`, terminal source error, source protocol → in-memory fixture source | Compatible; no real network path is imported or constructed. |
| 10 → 11 | candidate context, keys, planner, datasets → executor | Compatible; shared `deep_worker.py`/test edits are sequential. |
| 10 → 12 | context/keys/datasets → daily enqueue and progress scoping | Compatible; same dated child keys deduplicate legacy expansion and incremental enqueue. |
| 10 → 13 | datasets/context loader/legacy parents → fixture helpers/harness | Compatible; helper creation stays in Task 13, not Task 7 (F4). |
| 11 → 12 | `run_deep`, summaries, bundle verification → CLI/status | Compatible; only remote statement attempts consume `limit`. |
| 11 → 13 | enqueue/run/read bundle APIs → online-fake and offline-frozen replay | Compatible; second identical run should reuse rows/bytes. |
| 12 → 13 | `status` output contract → E2E formal-gate and pool assertions | Compatible after F7; hermetic denominator follows fixture context, production acceptance enforces 120. |

## 3. Findings and binding rulings

| ID | Severity | Conflict | Minimal spec-first ruling |
|---|---|---|---|
| F1 | **Important / load-bearing** | Task 7 ranks a visible revision by `(effective_at, source_updated_at or announced_at, fetched_at)`, while spec §3.3 says announcement time, then source update, then fetch time, then content hash. The proposed `or` drops announcement time whenever update time exists. Separately, spec §8 and the Plan Self-Review Map require an actually reachable equal-rank conflict branch, which literal content-hash tie-breaking would otherwise erase. | Use `effective_at_utc <= as_of_utc` only as the visibility gate. Within a fact group rank by the spec's business fields in order: `announced_at_utc`, `source_updated_at_utc` (with a deterministic missing sentinel), then snapshot fetch time. At the top business rank, block differing value/unit/nature as `conflicting_fact_versions`/`conflicting_fact_units`; use raw/content hash or fact ID only to deterministically deduplicate semantically identical rows. Effective time itself remains the first verified trading close strictly after `max(NOTICE_DATE, UPDATE_DATE)`. Cost if wrong: a future or conflicting revision may be silently selected, corrupting every downstream bundle. |
| F2 | **Important / load-bearing** | Task 8 prose says “omitting a statement key is not equivalent to explicit null,” but the required code materializes all three keys with `.get()`, making omission and explicit null identical. Spec §5.4 requires a missing table to be represented by an explicit null marker. Tests could be written to either contradictory reading. | Always canonicalize exactly three dataset keys; an omitted caller key is converted to the required explicit null marker and therefore hashes the same as an explicitly supplied null. A null changing to a real snapshot hash must change the input hash. Delete/ignore only the contradictory sentence, not the code or spec behavior. Cost if wrong: logically identical missing-input builds can fork hashes, or missing and present inputs can collide. |
| F3 | **Important** | Task 3 claims lossless v2 migration, but its concrete regression preserves only a `run` row. Spec §10 explicitly requires pre-existing run, job, snapshot, and score data to remain row-for-row unchanged. | In the literal-v2 test, insert representative linked rows into every existing v2 table and snapshot each table before initialization; after migration compare every old table row-for-row, then test v3 additions/constraints. No production scope expansion is needed. Cost if wrong: migration could silently mutate or drop durable work while the prescribed test remains green. |
| F4 | **Important** | Task 13 says “Task 7 tests must reject” malformed fixture structure, but Task 7 neither lists nor can safely import `tests/feature_fixture_helpers.py`; that helper is created in Task 13 and imports `deep_worker` from Task 10. | Task 7 adds a small test-local JSON fixture-structure validator in `tests/test_financial_features.py` and rejection tests for missing batches, periods, identity/date fields, and calendar range. Task 13 later creates the shared runtime loaders exactly as planned; it may reuse or reassert the structure but must not move Task 7's RED/GREEN dependency forward. Cost if wrong: malformed fixtures can validate the normalizer with incomplete history, or Task 7 becomes dependent on not-yet-created Task 10 code. |
| F5 | **Important (process safety)** | Task 13 calls repository-root `progress.md` an “execution ledger,” while `subagent-driven-development` owns `.superpowers/sdd/2026-08-29-seven-dimension-feature-foundation/progress.md` as the recovery ledger. Confusing them risks staging the ignored controller ledger or failing to update the committed project status. | Treat root `progress.md` as the project-facing, committed execution/status document listed by Task 13. Treat `.superpowers/sdd/.../progress.md` as the private SDD recovery ledger only; never stage it. Every task completion/ruling goes to the SDD ledger, while Task 13 writes only the specified release facts to root `progress.md`. Cost if wrong: compaction recovery or the committed audit trail becomes incomplete. |
| F6 | **Minor** | Task 2's combined declarations do not identify whether `TEMPLATE_VERSION` belongs to `financial_schema.py` or `industry_templates.py`, inviting duplicate constants or circular imports. | Define it once in `industry_templates.py` beside `TemplateDefinition` and the registry; Tasks 8/12 import it from there. `financial_schema.py` owns only financial mapping/request versions. Cost if wrong: template version hashes may diverge across modules. |
| F7 | **Minor** | Spec/operational acceptance describes a denominator of 120, while Task 12's hermetic unit test explicitly expects 2 for a two-member context. | Implement `denominator = len(context.members)` so isolated tests and future candidate sets remain coherent; the production operational acceptance separately requires that the current deployment context has denominator 120 and coverage ≥114. Cost if wrong: either hermetic tests hard-code production data size or production can appear accepted with a truncated candidate set. |

## 4. Review-rubric hygiene check

| Check | Result | Evidence |
|---|---|---|
| Does the plan require a test with no assertions? | **No.** | Every named/new test is paired with a concrete state, value, exception, count, hash, call-list, path, blocker, or rollback assertion. Baseline/regression commands and operational smoke commands are execution checks, not assertionless unit tests. |
| Does the plan require verbatim duplication of a production logic block inside tests? | **No.** | The test helpers construct fixtures, expected records, fake sources, and direct inspection queries. Copying the candidate-label checklist into a versioned fixture duplicates approved data, not executable production logic. The required fixture loaders do not reimplement selection, formula, worker, or hashing algorithms; they call the production canonical helpers. |

## 5. Execution note

Apply F1–F7 as controller rulings before dispatching Task 1, and carry the relevant ruling into the briefs for Tasks 2, 3, 7, 8, 12, and 13. No finding requires changing the approved feature scope, opening formal-score gates, performing network access, or modifying existing data.
