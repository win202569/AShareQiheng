# Seven-dimension feature foundation — final whole-branch rereview

## Review metadata

- Review boundary: `e361fbd..dd1e3322dfa73c7c53ca7c0944544c895b781789` (32 commits).
- Frozen review package: `review-e361fbd..dd1e332.diff`, opened exactly once and treated as the complete commit/diff boundary.
- Worktree: `D:\Projects\AShareQiheng\.worktrees\seven-dimension-foundation`.
- Review mode: independent, read-only code review except for this private report. No Git command, network call, tracked runtime database, operational acceptance, or broad/full test suite was run.
- Required skills/instructions read in full: `using-superpowers`, `requesting-code-review/SKILL.md`, and `code-reviewer.md`.
- Binding materials read in full: the design specification, implementation plan, public `progress.md`, private preflight/progress ledger, the prior whole-branch/fix/residual reports and rereviews, and the final evidence-integrity brief/report named in the assignment.
- Current-file context was read only where needed to interpret the frozen package. Reported suite counts in prior reports were not accepted as proof; the relevant production paths and test bodies were inspected directly.

## Executive verdict

| Severity | Count |
|---|---:|
| Critical | 0 |
| Important | 2 |
| Minor | 4 |

**Findings remain open.**

**Ready to integrate: No.** `dd1e332` correctly closes the exact empty/missing/dangling database-reference cases in its brief, but the broader feature/file/DB/progress trust boundary remains open in two independently reproducible ways: future-effective canonical facts can be persisted and counted ready for an earlier `as_of`, and an `unclassified` bundle can be relabelled `partial` without its mandatory blocker and be counted as partial. Both cross the canonical file, database, and progress boundary.

The formal-score gate, seven-dimension gate, waiting-price pool, and strong-attention pool remain closed in code and in both isolated probes.

## Blocking findings

### Important 1 — DB-backed evidence validation does not enforce the bundle's point-in-time visibility boundary

**Locations**

- Binding specification: `docs/superpowers/specs/2026-08-29-seven-dimension-feature-foundation-design.md:56`.
- Normal builder selection: `ashare_pipeline/financial_features.py:426-436` and `ashare_pipeline/deep_worker.py:1289-1297`.
- Persistence validator: `ashare_pipeline/state_store.py:803-899`, especially `853-863`.
- Persistence transaction: `ashare_pipeline/state_store.py:901-960`.
- Progress consumer: `ashare_pipeline/orchestrator.py:1052-1089`.
- Existing evidence tests: `tests/test_state_store.py:660-879` and `tests/test_orchestrator.py:1204-1303`; none exercises `fact.effective_at_utc > bundle.as_of_utc`.

**Problem**

The ordinary deep-worker path correctly applies `effective_at_utc <= as_of_utc` before building a bundle. The new DB validator then resolves every cited fact and compares evidence metadata to that fact, but never compares the canonical fact/evidence effective time with `bundle.as_of_utc`. Therefore a canonical, existing, snapshot-backed future fact can be used in a ready bundle for an earlier replay date. The file hash, DB header, fact IDs, snapshot IDs, raw values, and evidence metadata can all be internally consistent, so progress accepts the row and reports it ready.

This is not the already-fixed “invented fact ID” case. All facts and snapshots exist and all new `dd1e332` equality checks succeed; the missing invariant is temporal referential integrity.

**Isolated reproduction**

Using only a `TemporaryDirectory`, a new test-local StateStore, production bundle/file/persistence/progress functions, and no network:

1. Install the normal 273 canonical facts and their three snapshot rows.
2. Rebuild those facts with `effective_at_utc=2026-08-21T07:00:00+00:00` and insert them canonically.
3. Build a complete general bundle with `as_of_utc=2026-07-01T00:00:00+00:00` from those future facts.
4. Write the canonical feature file, call `put_feature_bundle`, then call the real status/progress path.

Observed result:

```text
bundle_status=financial_ready
future_evidence_count=273
bundle_as_of=2026-07-01T00:00:00+00:00
future_effective=2026-08-21T07:00:00+00:00
db_created=True
progress_counts={'partial': 0, 'financial_ready': 1, 'blocked': 0}
unknown_failure_count=0
formal_score_ready=False
seven_dimension_ready=False
pool_counts={'waiting_price': 0, 'strong_attention': 0}
```

**Impact**

Historical/replay output can contain information that was not yet visible at its declared `as_of`, while all current evidence-integrity checks and progress reporting claim success. This violates the binding PIT rule and can contaminate every derived value in the ready bundle.

**Minimum repair**

Reject every observed/derived evidence reference whose effective time is later than the bundle `as_of`. The smallest non-duplicative repair is a context-level check in `FeatureBundle.validate()` over all evidence, with the StateStore equality check continuing to bind that timestamp to the canonical fact; alternatively enforce it directly in the shared StateStore validator used by persistence and progress. Compare parsed aware instants, not untrusted strings.

Add focused regressions for public parse, first persistence, the existing-row/idempotent path, and progress/no-fallback. Retain a positive case where `effective_at_utc == as_of_utc` and the existing later-corruption checks.

### Important 2 — `unclassified` is only forbidden from `financial_ready`; it is not required to remain blocked

**Locations**

- Binding specification: `docs/superpowers/specs/2026-08-29-seven-dimension-feature-foundation-design.md:190` and `240-242`.
- Contract validation: `ashare_pipeline/feature_contract.py:437-457`.
- Evidence-empty early return: `ashare_pipeline/state_store.py:807-816`.
- Progress counting: `ashare_pipeline/orchestrator.py:1052-1089`.
- Builder's correct behavior: `ashare_pipeline/financial_features.py:1057-1063`.
- Existing tests cover builder behavior at `tests/test_financial_features.py:1102-1106` and specialized public parsing at `tests/test_feature_contract.py:336-346`, but there is no public-parser/persistence/progress regression for `unclassified -> partial`.

**Problem**

The builder correctly emits `blocked` plus `industry_template_unclassified`. The public contract, however, explicitly excludes `unclassified` from `specialized_inputs_pending` and only rejects it inside the `financial_ready` branch. A caller can change a canonical unclassified bundle to `partial`, remove `industry_template_unclassified`, and pass public parsing. With no evidence references, the DB-backed validator returns immediately; persistence and progress then trust the declared `partial` status.

The specification is explicit that unmapped industries enter `unclassified` and block template features, and that a template with no applicable slots has coverage 0 and status `blocked`. This path hides that hard block as ordinary incompleteness.

**Isolated reproduction**

Using a test-local candidate context with industry `不存在行业`, an empty temporary StateStore, and real file/DB/progress functions:

1. Build the normal production bundle (`blocked`, `industry_template_unclassified`).
2. Change only `financial_status` to `partial` and remove that blocker.
3. Parse through `FeatureBundle.from_dict`, write the canonical file, persist it, and run status.

Observed result:

```text
baseline_status=blocked
forged_status=partial
template=unclassified
evidence_refs=0
db_created=True
progress_counts={'partial': 1, 'financial_ready': 0, 'blocked': 0}
unknown_failure_count=0
formal_score_ready=False
seven_dimension_ready=False
pool_counts={'waiting_price': 0, 'strong_attention': 0}
```

**Impact**

Canonical file/DB/progress output can conceal an explicitly blocking template-classification failure. It does not open the formal gates, but it makes the feature status and operational progress semantically false at the same public trust boundary that the prior Important finding required to fail closed.

**Minimum repair**

In `FeatureBundle.validate()`, require `template_id == "unclassified"` to have `financial_status == "blocked"` and the exact `industry_template_unclassified` financial blocker. Add a public parse test plus a real write/persist/read/progress regression. More generally, keep all non-ready status/coverage/blocker relationships derived rather than caller-asserted; at minimum the explicit unclassified invariant must be enforced.

## Original six Important findings — final verdicts

| Original finding | Final verdict | Evidence |
|---|---|---|
| 1. Calendar facts isolation | **ADDRESSED** | Feature execution normalizes only the exact frozen statement refs into a local `normalized_facts` list and selects only that list with the current frozen calendar (`deep_worker.py:1226-1297`). It no longer rereads all historical facts. Both current-calendar and null-calendar old-fact regressions are non-vacuous (`tests/test_deep_worker.py:544-605`). |
| 2. Exact BaoStock calendar identity | **ADDRESSED** | The frozen payload binds snapshot ID/hash, source `baostock`, dataset `trade_dates`, exact request, and request fingerprint (`deep_worker.py:465-547`); enqueue/public validation and execution re-resolve and verify repository and payload identity (`deep_worker.py:958-1019`). Tests exercise source/dataset/request swaps (`tests/test_deep_worker.py:645-768`). |
| 3. Specialized readiness | **ADDRESSED** | Registry metadata requires specialized templates (bank/insurance/broker/real-estate/resource) to remain blocked with `specialized_financial_inputs_missing` (`feature_contract.py:437-448`; builder at `financial_features.py:1059-1063`). Public parser and real builder tests cover the path (`tests/test_feature_contract.py:336-346`; `tests/test_financial_features.py:1073-1100`). The separate unclassified gap is Important 2 above. |
| 4. Negative nonzero denominators | **ADDRESSED** | Gross margin, total accruals, and ROIC reject only non-finite/zero denominators (`financial_features.py:792-847`). Hand-calculated negative-denominator tests assert the actual numeric outputs (`tests/test_financial_features.py:917-953`). |
| 5. Missing-reason producer/consumer | **ADDRESSED** | Persistence emits `reason` (`state_store.py:1168-1194`) and progress consumes the same key (`orchestrator.py:1091-1093`). The test persists a real bundle before aggregation (`tests/test_orchestrator.py:1058-1088`). |
| 6. Feature bundle/file/DB/progress trust boundary | **NOT CLOSED / PARTIALLY ADDRESSED** | Ready bundles now reject missing/blocked financial values, specialized bypasses, registered raw-slot omissions, and derived/observed retag substitutions (`feature_contract.py:449-517`; tests `270-346`). File canonicality/hash and DB header checks are present; `dd1e332` resolves fact/snapshot rows and binds shared evidence plus raw observed facts (`state_store.py:803-899`). Empty/missing/dangling evidence, idempotent bypass, later DB reference loss, raw-slot mismatches, newest-only/no-fallback, bounded unknown, positive ready, and new-orphan cleanup are covered. However Important 1 leaves PIT DB referential integrity open, and Important 2 leaves the unclassified blocked/status invariant open. |

## `dd1e332` evidence-integrity fix assessment

The following parts are correct:

- **Empty and dangling evidence:** a ready bundle cannot pass when its referenced facts are absent; every resolved fact's snapshot row must exist (`state_store.py:818-851`).
- **Field/content agreement:** bundle security and all public evidence fields match the canonical fact (`state_store.py:853-863`); descriptor-decidable raw observed slots also bind dimension/key/status, metric, period, value, unit, mapping/formula version, source field, and single evidence (`865-899`).
- **Transactionality:** `BEGIN IMMEDIATE` encloses validation, existing-row detection, header insertion, and all feature values (`state_store.py:914-960`). A failed validation cannot leave a header/value subset.
- **Idempotency:** validation occurs before the existing-row success path (`914-931`), so deleting/corrupting referenced rows cannot be hidden by idempotent reuse.
- **Later DB corruption:** progress calls the same validator after verified-file and DB-header checks (`orchestrator.py:1066-1080`).
- **No fallback:** the newest candidate security is marked seen before validation (`orchestrator.py:1060-1065`), so invalid newest evidence cannot fall back to an older row.
- **Bounded reads and bounded unknown:** fact/snapshot IDs are deduplicated, sorted, and read in 256-ID batches (`state_store.py:818-850`); progress adds at most one bundle-corruption unknown for that candidate.
- **Normal positive path:** the real builder's snapshot/fact-backed bundle round-trips through file, DB, read, and progress (`tests/test_orchestrator.py:1204-1246`).
- **Cleanup/no-clobber:** evidence rejection removes only a newly created, still matching, unreferenced feature file; a pre-existing canonical file is preserved (`deep_worker.py:1165-1198`; `tests/test_deep_worker.py:1491-1525`).

The exact empty/missing/dangling problem is therefore fixed. The overall evidence/progress trust boundary is **not** fully fixed because a real canonical fact can still be temporally ineligible (Important 1), and a no-evidence unclassified bundle can bypass its mandatory blocker/status (Important 2).

No evidence shows that `dd1e332` introduced a new regression in transactionality, idempotency, cleanup, no-fallback, bounded reads, or the positive path. The two blocking issues are residual invariants that the fix did not close, not newly created data-loss behavior.

## Gates, sources, data safety, and compatibility

### Formal gates and pools

- `FeatureBundle` requires `is_formal_score_ready is False` and `formal_confidence is None` (`feature_contract.py:420-424`).
- Status output hardcodes `formal_score_ready=False`, `seven_dimension_ready=False`, and both official pool counts to zero (`orchestrator.py:1151-1167`).
- Both isolated probes confirmed all four remain closed.
- Verdict: **closed as required**. Neither Important finding opens a formal gate or pool.

### Tracked data and runtime DB

- The frozen package contains no `data/` change and no ignore-rule change that would hide tracked data. The committed financial/calendar fixtures are tests, not runtime state.
- No Tushare production/test reference exists in the reviewed implementation (`rg -ni tushare` outside historical docs/package returned no matches).
- No test body opens the workspace runtime database. StateStore, deep-worker, snapshot, and orchestrator tests construct databases beneath `TemporaryDirectory`; `data/state.sqlite3` occurrences in the orchestrator tests are parser strings only (`tests/test_orchestrator.py:276-305`).
- This review did not open or modify a tracked/runtime DB. The two probes used disposable temporary roots.
- Verdict: **satisfied**.

### Bounded/isolated network behavior

- Offline deep execution returns before requiring or constructing a source (`deep_worker.py:1509-1523`; `orchestrator.py:1482-1489`).
- Online deep execution requires an explicit source and validates `limit` in `[1, 360]`; the loop is bounded by counted remote statement attempts (`deep_worker.py:1525`, `1590-1594`, `1868-1888`).
- The AKShare statement adapter performs one whitelisted table request per call, and the BaoStock feature calendar is a single exact `trade_dates` request/batch.
- Source imports/construction remain isolated to online paths; no real network was used by this review.
- Verdict: **satisfied at code/test level; live smoke remains operational acceptance**.

### Migration, persistence, determinism, and compatibility

- Schema v3 remains an additive, explicit `BEGIN IMMEDIATE` migration with exact v2 preconditions and foreign keys enabled. Existing v2 rows are preserved by the test fixture; malformed/partial legacy schemas fail closed.
- Canonical JSON, content hashes, hard-link first-writer-wins publication, logical-key conflict detection, frozen job payloads, exact statement/calendar identities, and owner-checked job completion remain deterministic and no-clobber.
- No new Critical/Important compatibility or data-loss regression was found beyond the two semantic trust-boundary findings above.

## Deferred and new Minor findings

The three original deferred Minors remain Minor; none has upgraded based on this review.

### Minor 1 — Heartbeat still does not cover the entire leased statement/feature execution

- Locations: `ashare_pipeline/deep_worker.py:1491-1500`, `1562-1600`, `1712-1804`, and feature processing at `1340-1402`.
- Reproduction path: use a short lease and delay verified snapshot persistence/normalization/follow-up or feature construction after the remote call beyond lease expiry; a second worker can recover the lease while the stale worker performs idempotent side effects before its owner-checked terminal transition fails.
- Why it remains Minor: default lease is 900 seconds; writes are content-addressed/idempotent/no-clobber and final job transitions verify ownership, so the main risk is duplicate/stale side effects rather than silent overwrite or release-gate opening.
- Minimum suggestion: keep the heartbeat alive for the full leased execution, or revalidate ownership immediately before each external side effect; add a delayed post-fetch and delayed feature-build regression.

### Minor 2 — Legacy absolute snapshot paths still bypass data-root containment

- Location: `ashare_pipeline/snapshot_repository.py:142-147`.
- Reproduction path: place a valid legacy snapshot payload outside the project data root, insert an absolute payload path plus matching hash in a test-local DB, and call `read_verified`; the absolute branch resolves and accepts it without `relative_to(data_root)`.
- Why it remains Minor: new relative writes are contained and content/hash verification remains active; exploitation requires a legacy/corrupt DB row.
- Minimum suggestion: accept a legacy absolute path only if the resolved path is inside the permitted data root, or migrate and then reject absolute paths.

### Minor 3 — The implementation plan still names two v2 tables incorrectly

- Location: `docs/superpowers/plans/2026-08-29-seven-dimension-feature-foundation.md:476`; actual names are `artifact` and `source_snapshot` at `ashare_pipeline/state_store.py:99-119`.
- Reproduction path: follow the plan's literal migration-preservation table list; queries for `snapshot` and `export_artifact` fail even though the implementation uses the correct schema.
- Minimum suggestion: replace the two plan names with `source_snapshot` and `artifact`.

### Minor 4 — The tracked public progress ledger is stale after the final repair waves

- Locations: public `progress.md:58-65`; current private recovery ledger `.superpowers/sdd/2026-08-29-seven-dimension-feature-foundation/progress.md:59-81`.
- Reproduction path: read the public seven-dimension section: it stops at the Task-13 state and a 337-test claim, while the frozen boundary includes the six-finding fix, residual ready/retag fixes, and the `dd1e332` evidence-integrity fix. Only the intentionally private/ignored ledger records those later review/fix states.
- Impact: the integrated tracked audit ledger would not explain why the public contracts and tests differ from the last recorded state. This is evidence traceability/documentation drift, not a runtime defect.
- Minimum suggestion: after the blocking findings are fixed and permitted hermetic verification is rerun, add a concise tracked remediation/review entry to public `progress.md`; preserve the explicit statement that exact 120/114 and live-network acceptance remain unperformed.

## Test-quality and evidence assessment

The relevant tests were inspected rather than accepted by count:

- Calendar isolation/identity tests exercise real frozen refs and swap source, dataset, and request identity.
- Negative-denominator tests assert hand-calculated numeric values, not only statuses.
- Missing-reason aggregation persists a real bundle through the producer before consuming progress.
- Ready-contract tests cover all five financial dimensions, missing/blocked values, raw-slot omission, five derived/observed retag variants, specialized blockers, and a positive general ready round-trip.
- `dd1e332` StateStore tests cover empty DB, first write, idempotent revalidation, missing fact/snapshot, every shared evidence field, wrong fact security, raw metric/period/value/unit/mapping/source-field mismatches, and positive evidence.
- Progress tests cover missing evidence after persistence, newest-only/no-fallback, one bounded unknown, verified feature file/header checks, and the normal positive path.
- Deep-worker cleanup tests distinguish a newly created orphan from a pre-existing canonical file.

The missing regressions correspond exactly to the two Important findings: no future-effective-evidence test exists, and no public/file/DB/progress test forces unclassified to remain blocked.

No broad/full suite was run because the assignment explicitly forbade it. Two successful, narrowly scoped offline probes were run only after static inspection produced concrete falsifiable hypotheses. Initial harness-only failures (`python` absent from PATH, and one diagnostic print calling a nonexistent `list_snapshots` helper after persistence) were corrected; they are not product-test failures and are not counted as evidence.

## Remaining work that is not a code finding

The following are still required operational acceptance and must not be reported as code defects or as already completed:

1. Run the real bounded online smoke against the allowed BaoStock/AKShare paths, observe remote-attempt limits, source circuit behavior, exact calendar identity, and persisted snapshot verification.
2. On the real current candidate context, prove the denominator is exactly 120 and the verified three-statement target-period numerator is at least 114; report the exact `120/114` evidence, not only a percentage.
3. Keep runtime/tracked data protected during that acceptance and preserve explicit retry/terminal reasons for every incomplete candidate.
4. Do not describe code merge-readiness as production operational acceptance. Formal scoring, seven-dimension readiness, and the two official pools remain intentionally unavailable after this foundation phase.

## Final assessment

**Critical: 0. Important: 2. Minor: 4.**

**Findings remain open — DO NOT INTEGRATE.**

Original Important findings 1-5 are addressed. Original finding 6 is only partially addressed: missing/blocked ready inputs, specialized readiness, raw-slot omission, derived/observed retag attacks, feature-file/header verification, and canonical DB fact/snapshot existence/equality are covered, but PIT visibility and the unclassified blocked invariant are still able to cross the canonical file/DB/progress boundary.

