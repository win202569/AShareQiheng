# Seven-dimension feature foundation — final whole-branch rereview v3

## Review metadata and materials

- Review date: 2026-08-31.
- Worktree: `D:\Projects\AShareQiheng\.worktrees\seven-dimension-foundation`.
- Authoritative range: `e361fbd..ee1a5d78e4e1d123ddd002c54c80bda8f41fd133` (33 commits).
- Frozen complete package: `.superpowers/sdd/2026-08-29-seven-dimension-feature-foundation/review-e361fbd..ee1a5d7.diff`. It was loaded exactly once and treated as the complete range. No Git log, diff, range, status, or other Git-derived replacement was run.
- Review mode: independent, read-only whole-branch architecture and production-readiness review. No network call, runtime/tracked database access, operational acceptance run, broad/full test run, or product-file mutation was performed. Current files were read only to clarify the frozen package. This private report is the only file written.
- Required instructions read and applied: `using-superpowers`, `requesting-code-review`, its linked `code-reviewer.md`, and the linked Codex tool guidance.
- Binding materials read in full:
  - `docs/superpowers/specs/2026-08-29-seven-dimension-feature-foundation-design.md`
  - `docs/superpowers/plans/2026-08-29-seven-dimension-feature-foundation.md`
  - tracked `progress.md`
  - private `.superpowers/sdd/2026-08-29-seven-dimension-feature-foundation/progress.md`
  - prior `.superpowers/sdd/2026-08-29-seven-dimension-feature-foundation/final-branch-rereview.md`
  - current `final-pit-unclassified-fix-brief.md`, `final-pit-unclassified-fix-report.md`, and `final-pit-unclassified-rereview.md`
- The relevant production and test bodies in the frozen package were inspected directly. Implementer command transcripts and counts were treated as claims and cross-checked against the named test bodies and production paths; they were not treated as independent reviewer execution.

## Executive verdict

| Severity | Count | Disposition |
|---|---:|---|
| Critical | 0 | None found |
| Important | 2 | Open; both are in the full feature/file/DB/progress trust boundary |
| Minor | 4 | Deferred; none independently blocks integration |

**Exact verdict: FINDINGS REMAIN OPEN.**

The two latest Important findings are closed: parsed-aware point-in-time cutoff now applies to every evidence item with equality accepted, and `unclassified` is forced to `blocked` with zero coverage and `industry_template_unclassified`. The original six areas are also closed except for the broad trust-boundary area, where two additional whole-branch issues remain: canonical evidence does not authenticate derived financial values/formulas, and progress does not compare persisted `feature_value` rows with the verified canonical file.

The formal-score gate, seven-dimension gate, formal score publication, waiting-price pool, and strong-attention pool remain hard closed.

**Ready to integrate: No** — this is strictly the code/test branch-readiness verdict. Live bounded-network smoke and exact operational `120/114` acceptance remain separate, unperformed operational work and are not counted as code findings.

## Important findings

### Important 1 — Canonical evidence authenticates raw facts but not derived financial values or the derived feature set

**Locations**

- Binding semantics: `docs/superpowers/specs/2026-08-29-seven-dimension-feature-foundation-design.md:244-252` and `:351-359`, with byte-identical rebuild acceptance at `:385-387`.
- Generic value validation: `ashare_pipeline/feature_contract.py:150-174`.
- Ready validation checks the registered raw-slot Cartesian product but ignores non-raw derived keys: `ashare_pipeline/feature_contract.py:465-533`.
- Approved production formulas: `ashare_pipeline/financial_features.py:701-847`.
- DB validation explicitly skips every value whose status is not `observed`, then performs fact/value checks only for raw observed descriptors: `ashare_pipeline/state_store.py:868-899`.
- Progress trusts the parsed file after header and evidence checks: `ashare_pipeline/orchestrator.py:1066-1082`.
- Builder formula tests exercise the honest producer, for example `tests/test_financial_features.py:833-953`, but there is no adversarial file/DB/progress test for a changed derived value, formula version, missing derived output, or unknown added derived key.

**Problem and impact**

`FeatureValue` requires a finite value, non-empty formula version, and evidence for a derived value, but it does not bind the key, unit, formula version, evidence operands, or numeric result to the approved derived-formula registry. The `financial_ready` branch proves that every registered *raw* slot/period is present and canonical, but it neither requires the exact derived-output set nor validates any derived result. StateStore then resolves the cited facts and verifies their public evidence metadata, but line 870 skips derived values before the only value/formula/metric checks.

Consequently, a canonical, snapshot-backed, evidence-complete bundle can carry a false `m.gross_profit.FY2021`, ROIC, accruals, margin, or other derived result and still be stored and counted `financial_ready`. It can also omit an approved derived output or add an unknown one while retaining all raw slots. The evidence remains real, but it does not prove that the advertised versioned calculation was performed. This breaks the core audit promise of the feature foundation and can contaminate later scoring even though the formal publication gates are currently closed.

**Reproduction reasoning**

1. Construct the existing positive general-ready bundle with the installed canonical facts/snapshot rows used by `installed_ready_bundle`.
2. In its public dictionary, change only `m.gross_profit.FY2021.value` to another finite number and change `formula_version` to any other non-empty string; retain the original canonical fact evidence.
3. `FeatureBundle.from_dict()` accepts it because the generic derived-value rules pass and the raw-slot Cartesian product is unchanged.
4. Write the resulting canonical bytes and recomputed hash. `put_feature_bundle()` resolves all cited facts/snapshots and accepts the evidence, because the altered value is `derived` and is skipped at `state_store.py:870`.
5. Verified file read and progress accept the same canonical bundle and report one `financial_ready` feature set.

Removing an approved derived item entirely follows the same path: readiness is based on raw registered slots, so the omission is not detected.

**Minimum repair**

Create one contract-versioned authority for the exact approved derived keys by dimension/period, unit, formula version, and operand rules. Public parsing should reject missing, duplicate, unknown, wrongly placed, or wrongly versioned derived financial outputs. The shared StateStore validator used by first persistence, idempotent reuse, and progress should recompute each derived value from the resolved canonical facts (with the approved finite/zero-denominator rules) or compare the whole financial portion with a deterministic rebuild. Add negative real-boundary tests for numeric mutation, formula-version mutation, operand substitution, derived omission, and unknown addition, plus the existing positive builder round-trip.

### Important 2 — Verified progress ignores corruption or loss in the persisted `feature_value` rows

**Locations**

- The binding schema requires `feature_set` and `feature_value`, with the feature package written atomically to file and DB: `docs/superpowers/specs/2026-08-29-seven-dimension-feature-foundation-design.md:280-290`.
- Full header-and-value comparison already exists for the idempotent persistence path: `ashare_pipeline/state_store.py:1199-1220`.
- Progress reads `feature_set` rows, computes `expected_header, _values`, discards `_values`, compares only header columns, and then validates file evidence: `ashare_pipeline/orchestrator.py:1052-1082`, especially `:1073-1078`.
- Existing later-loss coverage deletes a canonical source-snapshot row, not a `feature_value` row: `tests/test_orchestrator.py:1460-1511`. Header corruption is separately covered at `tests/test_orchestrator.py:1559-1588`.

**Problem and impact**

Initial persistence is atomic, and an idempotent re-put compares every stored value row. Progress does not. After a legitimate bundle is persisted, deletion, mutation, or insertion of DB `feature_value` rows leaves the verified file and `feature_set` header unchanged. Progress therefore reports the latest bundle as ready even though the schema-v3 DB representation is incomplete or inconsistent with the signed artifact.

This is a real later-DB-loss hole in the advertised file/DB/progress trust boundary. It can conceal an incomplete durable audit record after corruption or an interrupted external maintenance operation, and a downstream DB consumer will observe data different from the artifact that progress declared valid.

**Reproduction reasoning**

1. Persist the existing positive canonical general-ready bundle through `write_feature_bundle()` and `put_feature_bundle()`.
2. Delete one child row, for example `g.revenue.FY2021`, directly from `feature_value` while leaving `feature_set`, facts, snapshots, and the feature file intact. Deleting a child row is permitted by the schema.
3. Run the real status path. `_feature_set_public()` reads only the header JSON fields; the verified file/header comparison succeeds; evidence validation uses the file bundle and canonical financial facts, not the persisted `feature_value` table.
4. The candidate is still counted `financial_ready` with no unknown failure.

An in-range value/status mutation or an extra syntactically valid row produces the same mismatch and is likewise invisible to progress.

**Minimum repair**

Promote the existing exact header/value comparison to a shared read validator and call it from progress while the relevant DB connection is open. Compare the verified file's complete canonical value set with the exact `feature_value` rows before evidence validation and counting. Preserve current newest-only/no-fallback behavior and the bounded one-unknown-per-candidate rule. Add delete, update, and extra-row regressions plus a positive exact-match case.

## Minor findings

### Minor 1 — Lease heartbeat does not span the whole leased statement or feature execution

- **Locations:** feature jobs execute without a heartbeat at `ashare_pipeline/deep_worker.py:1337-1367`; the statement heartbeat wraps only the remote source call at `:1577-1601`; snapshot persistence and normalization occur after it stops at `:1712-1723`. The existing blocking-call test is `tests/test_deep_worker.py:933-961`.
- **Impact:** with a deliberately short lease or unusually slow local verification/persistence/normalization/feature build, another worker can recover the job while the old worker continues idempotent side effects. Ownership-checked terminal transitions and content-addressed/no-clobber writes prevent a silent overwrite, so the residual risk is duplicate work and stale side effects rather than release-gate opening or material data loss.
- **Reproduction reasoning:** delay `SnapshotRepository.persist`, `_normalize_statement_snapshot`, or `_execute_feature_job` beyond `lease_seconds` after the source call has returned; the heartbeat thread has stopped or never existed, allowing lease recovery by a second worker.
- **Minimum repair:** keep heartbeat/ownership protection active from lease acquisition through the final owned transition, or revalidate ownership before every side effect. Add slow post-fetch and slow feature-build regressions.

### Minor 2 — Absolute legacy snapshot paths bypass project data-root containment

- **Location:** `ashare_pipeline/snapshot_repository.py:142-147`; the behavior is intentionally exercised by `tests/test_snapshot_repository.py:253-269`.
- **Impact:** a legacy/corrupt DB row can direct verified snapshot reading outside the project data root. Hash and payload-metadata checks still apply, and all new relative writes are contained, so this remains a compatibility hardening issue rather than a current write-path escape.
- **Reproduction reasoning:** place a valid snapshot payload outside the project, seed a test-local `source_snapshot` row with its absolute path and matching hash/metadata, and call `read_verified()`; the absolute branch returns before any `relative_to(data_root)` check.
- **Minimum repair:** migrate legacy absolute rows to canonical project-relative paths, or accept an absolute compatibility path only when its resolved target is within an explicitly permitted data root.

### Minor 3 — The implementation plan names two v2 tables incorrectly

- **Location:** `docs/superpowers/plans/2026-08-29-seven-dimension-feature-foundation.md:476`; the real table names used by the migration regression are shown at `tests/test_state_store.py:276-284`.
- **Impact:** a future implementer following the plan literally will query nonexistent `snapshot` and `export_artifact` tables even though production code/tests correctly use `source_snapshot` and `artifact`.
- **Reproduction reasoning:** execute the plan's literal seven-table preservation list against the v2 fixture; the two named queries fail.
- **Minimum repair:** replace `snapshot` with `source_snapshot` and `export_artifact` with `artifact`.

### Minor 4 — The unclassified negative real-boundary test can pass on an unrelated earlier exception

- **Location:** `tests/test_orchestrator.py:1369-1418`, especially the broad `except (OSError, ValueError)` around write, persistence, and read at `:1388-1399`.
- **Impact:** an unrelated file-system, hash, path, or DB validation error before the intended unclassified invariant would leave `crossed=False` and satisfy this one regression without showing which production boundary rejected the artifact.
- **Reproduction reasoning:** make `write_feature_bundle()` raise an unrelated `OSError`; the test still reaches the same `crossed=False` assertion and passes.
- **Why it does not upgrade:** the genuine RED record says this same path crossed all boundaries before the production fix; the focused public-parser matrix asserts the `unclassified` error at `tests/test_feature_contract.py:398-429`; and the adjacent positive test exercises build/write/persist/read/progress at `tests/test_orchestrator.py:1420-1458`.
- **Minimum repair:** split the sequence into stage-specific `assertRaisesRegex` assertions and verify file/DB side effects after each. If direct read/progress corruption behavior is desired, seed that invalid artifact explicitly in a separate test.

## Original six Important areas and the two latest findings

| Area | Final verdict | Evidence and reasoning |
|---|---|---|
| 1. Calendar-fact isolation | **ADDRESSED** | Feature execution resolves the exact frozen statement refs, normalizes them using the feature job's frozen calendar into a local list, and selects only that list (`deep_worker.py:1230-1297`). Old-fact and null-calendar tests are non-vacuous (`tests/test_deep_worker.py:544-605`). |
| 2. Exact BaoStock calendar identity | **ADDRESSED** | Frozen ID/hash, source `baostock`, dataset `trade_dates`, semantic request, and request fingerprint are bound and reverified against repository and payload (`deep_worker.py:465-547`, `:958-1019`). Full natural-date coverage and strict 0/1 flags are enforced (`financial_features.py:125-179`). Swap/hole/range tests cover real failure paths (`tests/test_deep_worker.py:645-768`; `tests/test_financial_features.py:613-654`). |
| 3. Specialized-template readiness | **ADDRESSED** | Specialized templates remain blocked with `specialized_financial_inputs_missing` (`feature_contract.py:454-464`; `financial_features.py:1059-1063`). Parser and builder tests cover bank, real-estate, and resource cases (`tests/test_feature_contract.py:343-353`; `tests/test_financial_features.py:1073-1100`). |
| 4. Negative nonzero denominators | **ADDRESSED** | Gross margin, average assets, and average invested capital reject only non-finite/zero denominators (`financial_features.py:792-847`). Tests assert hand-calculated values `1.6`, `0.2`, and `-2/3`, not only status (`tests/test_financial_features.py:917-953`). |
| 5. Missing-reason producer/consumer alignment | **ADDRESSED** | Persistence emits the public key `reason` from `missing_reason` (`state_store.py:1153-1177`) and progress consumes `reason` (`orchestrator.py:1091-1093`). The test persists a real bundle before aggregation (`tests/test_orchestrator.py:1059-1089`). |
| 6. Full feature bundle/file/DB/progress trust boundary | **NOT CLOSED** | All enumerated prior repairs are present, but Important 1 permits false/missing/unknown derived outputs to cross canonical file/DB/progress and Important 2 permits later `feature_value` loss/corruption to remain counted ready. |
| Latest A. Parsed-aware PIT cutoff for every evidence item | **ADDRESSED** | `FeatureBundle.validate()` normalizes `as_of_utc`, parses every evidence instant, rejects only strict future, and accepts equality (`feature_contract.py:417-434`). The same validator runs on first and idempotent persistence before existing-row success (`state_store.py:908-931`), on file parse/read, and therefore on progress. Tests cover different offsets, equality, idempotent bypass, newest invalid/no fallback, and positive ready (`tests/test_feature_contract.py:355-396`; `tests/test_state_store.py:712-747`; `tests/test_orchestrator.py:1249-1367`). |
| Latest B. Exact unclassified blocked semantics | **ADDRESSED** | `unclassified` requires `blocked`, coverage `0.0`, and `industry_template_unclassified` (`feature_contract.py:445-453`); the builder emits it (`financial_features.py:1057-1063`). Parser and positive real-boundary tests cover the invariant (`tests/test_feature_contract.py:398-429`; `tests/test_orchestrator.py:1420-1458`). The broad negative boundary test remains only Minor 4. |

## Explicit trust-boundary repair-class assessment

| Repair class required by this review | Verdict | Evidence |
|---|---|---|
| Forged `financial_ready` with missing/blocked values | **PASS** | `feature_contract.py:465-488`; all five financial dimensions attacked at `tests/test_feature_contract.py:277-314`. |
| Registered raw-slot omission | **PASS** | Exact slot/period Cartesian product at `feature_contract.py:489-533`; omission test at `tests/test_feature_contract.py:316-325`; real write/DB/progress negative at `tests/test_orchestrator.py:1091-1147`. |
| Derived/observed retag substitution for a raw slot | **PASS** | Descriptor-owned dimension/status/formula/unit/source-field/single-evidence checks at `feature_contract.py:510-522` and `state_store.py:868-899`; five parser variants at `tests/test_feature_contract.py:327-341`; real boundary at `tests/test_orchestrator.py:1149-1203`. This does not cover alteration of a legitimate derived output, which is Important 1. |
| Feature file hash, canonical parse, header, and safe relative path | **PASS, with Minor 2 for legacy snapshot paths** | `deep_worker.py:686-728`, `:739-808`; DB header match at `orchestrator.py:1068-1077`; deletion/tamper/header tests at `tests/test_orchestrator.py:1513-1588`. |
| Canonical source-snapshot and financial-fact existence/field equality | **PASS for the specified DB evidence model** | Batched canonical fact reconstruction, snapshot-row existence, shared evidence equality, and raw observed fact equality at `state_store.py:818-899`; attacks at `tests/test_state_store.py:749-914`. Frozen source payloads are independently verified before fact construction at `deep_worker.py:975-1047` and `snapshot_repository.py:113-131`. |
| Transaction and idempotent bypass | **PASS** | `BEGIN IMMEDIATE` surrounds validation, existing-row detection, header, and all values (`state_store.py:914-960`); rollback/idempotent-loss/PIT tests at `tests/test_state_store.py:615-747`. |
| Later DB loss | **PARTIAL / FAIL** | Later canonical fact/snapshot loss is detected and newest-only progress refuses fallback (`tests/test_orchestrator.py:1460-1511`), but later `feature_value` loss is invisible (Important 2). |
| Newest-invalid/no-fallback | **PASS** | Security is marked seen before validation (`orchestrator.py:1060-1081`); future-evidence and later-snapshot-loss tests prove no fallback (`tests/test_orchestrator.py:1291-1367`, `:1460-1511`). |
| Bounded unknown | **PASS** | Progress catches only the explicit corruption classes and increments one unknown for the selected latest candidate (`orchestrator.py:1079-1081`). |
| Positive ready and unclassified paths | **PASS** | General ready and equality paths traverse parse/file/DB/read/progress (`tests/test_orchestrator.py:1205-1289`); valid unclassified traverses the same path and counts blocked (`:1420-1458`). |
| Orphan cleanup | **PASS** | Only a newly created, hash-matching, unreferenced file is removed after DB failure (`deep_worker.py:1165-1198`); tests distinguish new from pre-existing files (`tests/test_deep_worker.py:1450-1525`). |
| No-clobber behavior | **PASS** | Existing/racing content is compared and never overwritten (`deep_worker.py:779-803`); conflict, link-race, and revised-snapshot tests are at `tests/test_deep_worker.py:1245-1285`, `:1412-1448`. |

## DB evidence integrity assessment

The latest evidence-integrity repair is correct within its stated referential scope:

- It reconstructs canonical `FinancialFact` objects from DB rows in bounded batches and requires the exact cited ID set (`state_store.py:818-835`).
- Every fact's `source_snapshot_id` must reference an existing canonical DB row (`:837-851`).
- Bundle security and all duplicated public evidence fields must equal the canonical fact (`:853-863`).
- Raw observed registered slots additionally bind descriptor, dimension, key, status, period, value, unit, mapping/formula version, source field, and exactly one evidence reference (`:865-899`).
- The shared validator runs before first insert and before idempotent success inside one immediate transaction (`:901-960`) and is reused after verified-file/header checks by progress (`orchestrator.py:1066-1079`).

That closes invented IDs, missing facts/snapshots, field substitution, raw value substitution, idempotent bypass, and later evidence-row loss. It does not close the two broader representation problems above: legitimate facts can evidence an unauthenticated derived computation, and the DB's own persisted feature-value mirror is not verified by progress.

## Formal gates, score publication, and official pools

- `FeatureBundle` rejects any non-null formal confidence or `is_formal_score_ready != False` (`feature_contract.py:420-424`) and always serializes the flag as false (`:535-542`). The builder also sets false explicitly (`financial_features.py:1016-1025`).
- Status hardcodes `formal_score_ready=false`, `seven_dimension_ready=false`, and both official pool counts to zero (`orchestrator.py:1151-1167`).
- `finalize` continues to fail closed after cutoff/market evidence on `formal_v2_scores_unavailable`, without publishing a formal result (`tests/test_orchestrator.py:2083-2115`).
- End-to-end and trust-boundary positives repeatedly assert both gates false and both pools empty (`tests/test_feature_foundation_e2e.py:219-297`; `tests/test_orchestrator.py:1205-1458`).

**Verdict: hard closed as required.** Neither Important finding creates a formal score, opens seven-dimension readiness, or populates the waiting-price or strong-attention pool.

## Data, network, migration, determinism, compatibility, and concurrency

### Tracked/runtime data and dependencies

- The frozen package contains no tracked runtime `data/` change and no ignore-rule change that could conceal one. The added financial/calendar fixtures are under `tests/fixtures`, not runtime state.
- No reviewed production or test reference depends on Tushare.
- StateStore, snapshot repository, worker, and orchestrator tests create DBs beneath `TemporaryDirectory` (`tests/test_state_store.py:129`; `tests/test_snapshot_repository.py:34-36`; `tests/test_deep_worker.py:205-207`; `tests/test_orchestrator.py:270-272`). Literal `data/state.sqlite3` entries in parser tests are argument strings, not opened runtime DBs (`tests/test_orchestrator.py:277-306`).
- This review did not open or change a runtime/tracked database.

### Offline/online isolation

- Offline deep execution returns before requiring a source (`deep_worker.py:1509-1523`), and orchestrator offline paths do not construct default sources (`orchestrator.py:1482-1489`). Tests inject fakes and explicitly guard against source construction/network access.
- BaoStock and AKShare imports are deferred until their online adapters are used (`sources.py:147-149`, `:215-217`).
- Online deep work requires an explicit source, validates `limit` in `[1, 360]`, and bounds the loop by counted remote attempts (`deep_worker.py:1523-1525`, `:1588-1594`, `:1868-1888`). Circuit-breaker and retry taxonomy remain isolated.
- No offline test body requires real network access, and this review made no network call.

**Verdict: code/test isolation is satisfied.** The real bounded network smoke remains operational acceptance, not a code defect and not completed here.

### Additive migration and compatibility

- Schema version 3 is applied under one explicit `BEGIN IMMEDIATE`, with exact v2 preconditions and migration-ledger validation (`state_store.py:289-448`).
- The literal-v2 test seeds and compares every actual v2 table row-for-row before checking v3 additions (`tests/test_state_store.py:273-350`); double initialization, partial/corrupt schema rejection, ledger gaps, and migration rollback are covered (`:353-488`).
- Old job, score-run, score-item, artifact, and snapshot data is preserved; final score-item immutability remains tested.

**Verdict: additive v2-to-v3 compatibility and migration safety are satisfied.** The two plan table-name typos are documentation-only Minor 3.

### Determinism, persistence, and concurrency

- Normal production construction is deterministic: facts and evidence are sorted, input hashes freeze candidate/snapshot/version dependencies, and the end-to-end replay uses independent fresh harnesses (`tests/test_feature_foundation_e2e.py:219-299`).
- Snapshot publication is content-addressed and first-writer-wins under an actual concurrent barrier (`tests/test_snapshot_repository.py:135-188`). Feature publication uses fsynced canonical bytes plus hard-link no-clobber behavior (`deep_worker.py:739-808`).
- StateStore feature header/value insertion is atomic, conflicts fail closed, and repeated identical work is idempotent (`state_store.py:901-960`; `tests/test_state_store.py:584-633`).
- No new silent-overwrite or writer data-loss path was found. Whole-job lease protection remains Minor 1. Deterministic *producer* output is sound, but trust-boundary authentication of derived outputs is incomplete under Important 1, and later DB mirror verification is incomplete under Important 2.

## Deferred-Minor retriage

| Prior/deferred item | Current verdict |
|---|---|
| Whole-job heartbeat coverage | **Still Minor.** It has not expanded past the remote call and feature jobs still lack it, but owner checks and content-addressed/no-clobber side effects keep the impact bounded. |
| Legacy absolute snapshot containment | **Still Minor.** New writes are relative/contained and all payload hashes/metadata remain verified; the compatibility read branch still escapes containment. |
| Two plan v2 table-name typos | **Still Minor.** Production migration and the actual test table list are correct. |
| Tracked public progress drift | **CLOSED.** `progress.md:67-73` records the PIT/unclassified repair, 370-test claim, remaining review gates, unperformed live smoke and exact `120/114`, and closed formal/pool gates. The earlier 337 entry at `:58-65` is clearly the preceding foundation milestone, not the current total. |
| Scoped-review broad unclassified exception catch | **Minor 4 above.** It does not upgrade in the complete matrix because genuine RED, pinpoint parser assertions, shared production validation, and the adjacent positive path independently anchor the behavior. |

None of the three surviving prior Minors upgraded. The repaired public-progress item is no longer counted; the scoped-review test-quality item replaces it, leaving four Minors total.

## Test-body and execution-evidence assessment

The current fix report records the exact seven-test RED command and exit 1 with `Ran 7 tests` / `failures=9` (`final-pit-unclassified-fix-report.md:18-35`). It then records:

| Reported run | Reported result | Reviewer assessment |
|---|---|---|
| Focused regressions | 7/7, OK | Named test bodies exist and hit the intended shared public/store/read/progress paths. |
| Required related modules | 265/265, OK | Module list matches the affected contract, financial, StateStore, worker, orchestrator, and E2E surfaces. |
| Full discovery before staging | 370/370, OK | Command/result transcript inspected; not rerun by this reviewer. |
| Fresh staged full discovery | 370/370, OK | Command/result transcript inspected; not rerun by this reviewer. |

The RED is genuine and specific: public PIT and unclassified mutations, the idempotent future-fact path, newest-invalid progress, and the forged unclassified real boundary failed before the fix, while the equality and valid builder-unclassified positives already passed. The implemented authority is on the production path rather than test-only code.

Non-vacuity checks from actual bodies:

- Calendar identity/isolation uses real persisted frozen refs and explicit source/dataset/request/calendar swaps, not mocks that bypass validation.
- Negative denominators assert exact hand-calculated numeric results.
- Missing-reason aggregation persists through the actual producer and then reads progress.
- Ready/raw-slot/retag attacks exercise all five financial dimensions, a real general-ready fixture, file/store/read/progress, and a positive ready round-trip.
- Evidence-integrity tests cover empty DB, first insert failure, idempotent revalidation, fact/snapshot loss, every shared evidence field, raw security/metric/period/value/unit/mapping/source-field mismatch, and positive evidence.
- Latest PIT tests cover offset-aware instant comparison, equality, future canonical facts, idempotent reuse, verified read, bounded unknown, and newest-only/no-fallback.
- Latest unclassified tests cover parser negatives and a positive build/write/store/read/progress path. The single broad negative boundary catch is Minor 4.
- Cleanup tests distinguish a newly created orphan from a pre-existing canonical file, and race tests assert winner preservation.

The matrix is still missing the exact cases behind the two new Important findings: no test mutates or removes a legitimate derived financial output while retaining canonical evidence, and no progress test deletes/mutates/adds a persisted `feature_value` row while leaving the signed file/header intact.

No broad/full suite was rerun because the assignment prohibited it. No focused probe was necessary: the two residual paths are answered directly by the production control flow and the unused complete-value comparator.

## Tracked progress and operational-acceptance separation

Tracked `progress.md` is truthful about the branch's code/test state:

- The 337/337 statement at `progress.md:58-65` is the historical foundation milestone.
- The current repair entry at `:67-73` records the PIT/unclassified invariants, DB evidence checks, the implementer's 370/370 result, and the still-required independent reviews without predicting their outcome.
- It explicitly states that live bounded-network smoke and exact operational denominator/numerator `120/114` were not performed.
- It keeps `formal_score_ready=false`, says no formal scores were published, and keeps both official pools closed and empty.

The prior tracked-progress Minor is therefore closed. The newly found code issues do not make the tracked statements false: the ledger reports what was implemented and tested, not that fresh whole-branch review would approve it.

The following remain operational acceptance, not code defects and not silently completed:

1. Run a real bounded BaoStock/AKShare smoke with the explicit online switch, observing remote limits, exact calendar identity, retry/circuit behavior, and verified persistence.
2. Against the real current candidate context, prove denominator exactly 120 and verified target-period three-statement numerator at least 114, with exact numerator/denominator evidence and explicit reasons for all incomplete candidates.
3. Keep runtime/tracked data protected while performing that acceptance.

Code/test integration readiness must not be described as production operational acceptance. Conversely, those unperformed operations are not included in the Critical/Important/Minor code counts.

## Final assessment

**Critical: 0. Important: 2. Minor: 4.**

**Findings remain open — do not integrate this frozen branch yet.**

The latest PIT and unclassified repairs are correctly implemented and covered, the original first five Important areas are closed, all enumerated prior evidence repairs work within their stated scope, formal scoring and both pools remain closed, and migration/network/data/no-clobber behavior is otherwise sound. The overall trust-boundary area is not complete until derived values are authenticated against the approved formulas and progress verifies the exact persisted `feature_value` mirror.

**Ready to integrate: No** — code/test branch readiness only. Operational live smoke and exact `120/114` acceptance remain separately pending.
