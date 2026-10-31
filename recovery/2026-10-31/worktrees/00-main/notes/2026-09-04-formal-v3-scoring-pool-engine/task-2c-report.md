# Task 2C implementation report

Status: review fix round 1 implemented and source frozen for parent re-review. The original implementation/testing record below is historical; the final section supersedes its sequential-closure and provider assumptions. No Git writes, network, user data changes, progress edits, or nested agents. Parent owns final regressions, independent review and code-only commit. Base supplied by parent: `dbf075dd5764c4dcd0ed3cba5074cc6ec330f49a`.

## Changed files

- `ashare_pipeline/formal_metric_engine.py` — new complete-population input factory, sealed input/batch/context/score proofs, qualified metric selection, cohort reuse and deterministic Decimal percentiles.
- `ashare_pipeline/formal_feature_repository.py` — additive authenticated absence-state endpoint; private read-only authenticity validator exposed from the existing dependency closure. Existing present projection payload/hash remains unchanged.
- `tests/test_formal_metric_engine.py` — 18 focused arithmetic, real complete-universe, correction/absence, provenance, status-independence and cache-sharing tests.
- `tests/test_formal_metric_features.py` — six new absence tests; source tamper test captures a valid provider snapshot before damaging raw bytes so the endpoint itself must reject the corruption.
- `tests/formal_metric_feature_fixtures.py` — new same-store, member-specific leased financial-source/feature fixture.
- `tests/formal_metric_fixtures.py` — optional `tempdir=None` argument only; existing `tempfile.TemporaryDirectory()` default and original three-member defaults remain intact.
- This report. Other SDD artifacts and pre-existing `tmpj4zv9_fq/` remain intact.

Frozen production SHA-256:

```text
formal_feature_repository.py  88879938273FDF8C002DE267401C44117E80E9CD3FC8809F99237407DC548030
formal_metric_engine.py       724AFB3B98F641D372902F61EABE0DE8ABE8168672B0BC68C01A9421AEE397FB
```

## APIs for Task 3

```python
repository = FormalMetricInputRepository(
    feature_repository, context_repository,
    registry_signature_verifier=verifier,
)
batch = repository.build_batch(frozen_input_hash,
    scoring_registry=scoring_registry, metric_ids=None)
row = batch.input_for(security_id, "M.return_persistence")
eligible = metric_peer_eligible(row)
context = build_metric_peer_context(batch,
    metric_id="M.return_persistence", security_id=security_id)
score = score_metric_percentile(batch, context)
```

The constructor accepts exact `FormalFeatureRepository` and underlying exact `FormalContextRepository`, checks their shared `StateStore` and verifier, authenticates the feature repository initialization, and constructs its own genuine `FormalMetricContextRepository`. Constructor/dependency identity records are closure-private. Copied wrappers, fake initialized-looking objects, changed dependencies and replaced repository readers cannot mint a batch, including an all-invalid-template population.

Missing frozen universe returns `None`. Invalid/corrupt/unauthenticated inputs raise; absence never catches these failures. A batch enumerates the entire stored frozen ordinary-A universe, including BJ. There is no security subset, caller value, classification, score, rank, pool or veto override parameter.

All public metric IDs are uniformly `<dimension>.<registered metric_id>`, per the parent's explicit ruling. Bare aliases are rejected, even when currently unique. `M.return_persistence` and `CA.return_persistence` remain separate signed definitions. `metric_ids` is either omitted (all 25 slots) or an exact nonempty sorted unique tuple of known qualified IDs. Original signed `MetricDefinition` fields are unchanged.

`MetricInput`, `MetricInputBatch`, `MetricPeerContext`, and `MetricScore` expose `require_verified()`, `canonical_bytes()`, and detached `to_dict()`. They have no public constructor, mint, from-dict or verified flag. Their state is immutable and held outside writable instance fields. Copy/deepcopy, low-level uninitialized objects and low-level attribute mutation are rejected. JSON wire Decimal values are decimal strings; live attributes are `Decimal`.

Batch attributes include `security_ids`, `metric_ids`, `inputs` (shared immutable tuple of genuine row proofs), `definitions`, `feature_states`, `batch_hash`, and common root/freeze/universe/component identities. `input_for(security_id, qualified_metric_id)` returns the genuine row, rejecting IDs outside the batch. `definitions[template_id][qualified_metric_id]` contains the signed definition snapshot and definition hash.

Input fields include security, qualified metric ID, template and industries, raw Decimal or None, direction/unit, signed definition hash, per-metric `verified_feature_refs`, `invalid_reason`, `status`, full selected `projection_hash` when applicable, `feature_state_hash`, `input_hash`, and `batch_hash`. Here `input_hash` is the metric-row hash; the V6 input/bundle hashes remain in `batch.feature_states[security_id]`.

`metric_peer_eligible` consumes only genuine row proofs and their metric-local invalid reason. It does not inspect seven-dimension completeness, `formal_scored`, pool eligibility or veto flags. A complete selected metric survives absent sibling slots and incomplete history. Missing/blocked selected slots preserve projection reasons such as `formula_fact_missing`, denominator errors and unit errors. An absent current receipt yields `pending_evidence/current_receipt_absent`; it never supplies a value. Missing signed membership yields `invalid_template`; industry reasons come from authenticated 2B entries.

`build_metric_peer_context` consumes a genuine complete batch plus focal security/qualified metric ID. It selects same template+secondary when N >= 20, otherwise same template+primary when N >= 20. Below threshold it returns a genuine context with `reason="peer_count_below_20"`, no scope, and the final primary candidate count/IDs. Invalid focal rows receive their own pending reason and cannot be scored using peers. IDs are sorted and unique; IDs do not break numerical ties. Contexts bind exact cohort IDs, count, scope, direction, definitions and batch hash.

`score_metric_percentile(batch, context)` returns a sealed `MetricScore`, or `None` for an explicitly pending context. Inspect `context.reason` for pending outcomes. A context from another batch is rejected, even if its wire happens to match. There is no direction/focal-value/peer override. Score fields include raw value, average rank, percentile, peer count, genuine `peer_context`, row/definition/batch/root/freeze/universe bindings and `score_hash`.

`percentile_rank(raw_value, values, *, direction)` is a separate pure helper returning `(average_rank, percentile)`. It accepts an exact nonempty tuple of finite Decimal values containing the focal Decimal, and higher/lower direction. It can demonstrate N=2/4 arithmetic but cannot mint any official proof. Official scoring always enforces N >= 20 through a genuine context.

Group membership tuples and sorted-rank lookup maps are reused within one batch's private cache. All scored outputs use the captured immutable batch; scoring performs no repository reads and does not re-sort an identical cohort for every focal stock. No mutable global cohort cache exists.

## Canonical payloads and hash identities

Encoding is sorted-key, compact UTF-8 JSON with `ensure_ascii=False`, no NaN/Infinity, tuples as arrays and Decimal as strings. Hashes are SHA-256 over those bytes. A hash field is added after hashing its payload; it does not include itself.

- Absence payload: request `security_id/as_of_utc/template_id/registry_manifest_hash`; signed `feature_registry_hash`; expected V6 `input_hash/bundle_hash`; sorted `required_feature_keys`; complete canonical `fact_snapshot_hash/issue_snapshot_hash`; stable logical `batch_id`; `status="current_receipt_absent"`; `algorithm_version="formal-metric-feature-absence-v1"`; `absence_hash`.
- Present projection canonical payload, algorithm version and `projection_hash` are the existing unchanged 2A format. The additive state endpoint returns the existing proof type for present receipts.
- Definition payload: template ID, qualified engine metric ID, full signed original definition (including original dimension and leaf metric ID), root hash, scoring hash, feature hash, then `definition_hash`.
- Common metric bindings: root, frozen input, universe, population, UTC cutoff, full nine-role registry hash mapping, industry batch hash and SHA-256 of the canonical universe proof.
- Input payload: common bindings plus security/qualified metric/template/industries, definition hash, signed direction/unit, raw value, evidence fact refs, pending reason/status, projection/state hashes, then `input_hash`.
- Batch `schema_version="formal-metric-input-batch-v1"`: common bindings, requested IDs, complete sorted population, definition payloads, ordered metric rows and complete present/absence marker payloads, then `batch_hash`. Batch wire rows omit their parent batch hash to avoid a circular identity; live genuine row proofs additionally bind that batch hash.
- Context `schema_version="formal-metric-peer-context-v1"`: batch/root/freeze/universe, focal identity, definition, direction, scope, peer IDs/count and reason. `cohort_hash` hashes batch, metric, definition, direction, scope and peer IDs; it excludes focal ID so identical cohorts share rank computation. `context_hash` then hashes the full context payload including `cohort_hash`.
- Score `schema_version="formal-metric-score-v1"`: batch/root/freeze/universe, focal metric/security, definition/row hashes, raw value, average rank, percentile, peer count and complete context payload, then `score_hash`.

The factory resolves one authenticated 2B industry batch, reads the union of requested signed V6 keys once per classified security, and matches values by slot ID. Aggregate projection blockers do not exclude valid sibling metrics. It preserves the complete selected marker and per-metric refs. A final per-member pass re-reads each genuine present/absence marker and compares full canonical bytes; then it invokes mandatory 2B `recheck_batch` for root/universe/industry closure. Present->absent, absent->present, changed-still-absent facts, issues and provider generations fail the whole batch. Unclassified members have explicit pending rows and no fabricated feature template/marker; they remain bound to the authenticated population and signed membership absence.

The new `select_current_verified_metric_feature_state` shares the original genuine read/validation path with the old projection-or-None endpoint. For absence, it additionally reloads the registry graph, resolves the provider again, compares logical generation plus complete facts/issues, revalidates persisted source facts and confirms the exact expected receipt remains absent. It mints only after those checks. It does not turn raw-source, signature, provider or receipt corruption into absence.

Parent-approved private `_require_authentic_metric_feature_repository` is the existing dependency-validation closure, exposed read-only; it adds no mint authority or validation bypass. The engine captures it and uses it at construction and subsequent/final dependency checks, so no feature calls are needed to establish repository authenticity for entirely unclassified populations.

## Decimal contract

Every arithmetic operation uses an explicitly constructed local `Context(prec=50, rounding=ROUND_HALF_EVEN, Emin=-999999, Emax=999999, capitals=1, clamp=0, flags=[], traps=[InvalidOperation, DivisionByZero, Overflow])`. Neither mutable process context nor mutable `DefaultContext` supplies defaults. Global state is not changed.

V6 values become `Decimal(str(value))`: this preserves only the already available V6 float precision, not recovered source precision. Negative/zero raw values remain valid when the verified formula permits them. Ties use average ascending ranks. Percentile is `100 * (rank - 0.5) / N`, with `100 - percentile` for lower direction. Recurring division keeps 50 deterministic significant digits; it is not claimed to be mathematically exact. No display quantization is applied to persisted comparisons.

## Real fixture behavior and limits

The original 2B three-member fixture remains the default. New `FinancialFixture(population=True)` supplies 22 ordinary members through exactly three genuine exchange producer/receipt chains: one BJ, twenty SH and one SZ. All industry and feature inputs share the original root, store and verifier.

Signed feature ASTs are authored before sealing the graph and read metric-specific FY2025 leaves, in CNY, from one member-specific annual JSON statement. The annual source is a genuine leased `formal_statement` task, official request/declared security/exchange, raw file, producer receipt and persisted fact set. Content, raw-leaf and lineage hashes are derived from that source, not placeholder references. Bundles are persisted unchanged with other dimensions/history pending. The provider exposes stable per-security logical generation IDs and actual stored facts/issues.

The 22-member fixture requests four G metrics (88 input rows). It independently controls valid leaves: first has exactly 20 eligible secondary peers; second has 19 secondary but 20 primary; third has only 19 primary; fourth reverses direction. SZ has an identical industry label but a different template and must not join the general_nonfinancial cohort. BJ participates in qualifying groups. Hand-checked first-rank score is 2.5, reversed score 97.5. Separate real status writes prove a pool-vetoed company with incomplete features still contributes its valid zero-valued metric.

Fixture setup corrections observed during GREEN integration:

1. A provisional task kind `formal_financial_source` was rejected by the real store with `ValueError: formal snapshot task is not held by the current unexpired source-task lease owner`. The fixture now uses existing supported kind `formal_statement` and the corresponding lease. No production task-kind change.
2. Default OS TemporaryDirectory on Windows was rejected by secure feature storage with `PermissionError: [WinError 5]` / `ValueError: formal feature directory handle acquisition failed` at `_SecureDirectory._pin_windows_chain`. New financial fixtures now pass the existing `project_temporary_directory()` helper through the optional shared-fixture `tempdir=None` parameter. This runs inside the writable worktree and keeps secure production directory checks intact. It does not change production path handling or the old fixture default. Each fixture owns a fresh temporary directory and cleanup uses that TemporaryDirectory's own cleanup operation; it never enumerates/removes unrelated worktree paths. Existing `tmpj4zv9_fq/` was not touched.

The fixture uses explicit test signing keys and genuine byte-sensitive HMAC verification to author synthetic official-wire graphs. It does not turn a purpose=test registry into an official registry and does not fabricate successful repository/proof objects. No network or live production financial data is involved.

## Exact RED/GREEN execution evidence

All commands below ran from `D:/Projects/AShareQiheng/.worktrees/formal-v3-implementation`. Output blocks give the exact decisive test result lines and failure text, with repeated unittest stack frames omitted. The full TDD skill and `writing-good-tests.md` were read before edits.

### Absence prerequisite RED

```text
D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_metric_features.MetricProjectionTests.test_still_unpersisted_inputs_need_distinct_authenticated_markers -v
AssertionError: False is not true : authenticated absence endpoint is missing
Ran 1 test in 0.763s
FAILED (failures=1)
```

This test first observes old bare None for corrected unpersisted inputs, then requires a genuine marker that distinguishes another still-unpersisted correction.

### Absence/projection GREEN

```text
D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_metric_features -v
Ran 28 tests in 128.470s
OK
```

Includes all previous projection regressions plus initial five absence regressions. The later signature regression and improved endpoint-level raw-tamper check are included in final focused integration GREEN below.

### Arithmetic RED then GREEN

```text
D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_metric_engine -v
AssertionError: unexpectedly None : metric engine is missing
Ran 4 tests in 0.003s
FAILED (failures=4)
```

```text
D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_metric_engine -v
Ran 4 tests in 0.004s
OK
```

At these points the module contained only the four arithmetic tests. Covers hand-derived ties, lower reversal, zero/negative/all-equal values, invalid/nonfinite/empty inputs, focal-value substitution and mutated global Decimal context/default traps.

### Complete factory/cohort RED then GREEN

```text
D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_metric_engine.CompleteMetricBatchTests -v
AssertionError: False is not true : complete metric factory is missing
Ran 5 tests in 0.001s
FAILED (failures=5)
```

Intermediate fixture setup failures were the two real task-kind/directory errors described above; they were not treated as intended RED behavior.

```text
D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_metric_engine.CompleteMetricBatchTests -v
Ran 5 tests in 172.079s
OK
```

### Complete correction/missing-state integration GREEN

```text
D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_metric_engine.MetricClosureTests -v
Ran 5 tests in 152.243s
OK
```

This run included cross-member still-absent fact/issue/provider and receipt appearance corrections; present->absent correction; stable complete absent population; omitted metric selection and distinct return_persistence definitions; copied/replaced-reader/definition/root checks. Additional later tests are listed below rather than attributed to this earlier five-test invocation.

### Shared cohort tuple RED

```text
D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_metric_engine.MetricClosureTests.test_identical_cohorts_share_the_immutable_membership_tuple -v
AssertionError: ('SH600000', 'SZ000001') is not ('SH600000', 'SZ000001')
Ran 1 test in 20.299s
FAILED (failures=1)
```

The fix preserves already immutable tuple identity while freezing values, keeping canonical output unchanged.

### All-pending copied-repository RED

```text
D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_metric_engine.AllPendingRepositoryTests -v
AssertionError: ValueError not raised
Ran 1 test in 0.939s
FAILED (failures=1)
```

Genuine construction first yields three `invalid_template` rows from an entirely missing signed membership population. A copied feature repository was then wrongly accepted at construction. Parent approved exposing the read-only feature authenticity closure, and the engine now calls it even with no applicable feature reads.

### Final seal/tuple/reader GREEN (frozen production source)

```text
D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_metric_engine.AllPendingRepositoryTests tests.test_formal_metric_engine.MetricClosureTests.test_identical_cohorts_share_the_immutable_membership_tuple tests.test_formal_metric_engine.MetricClosureTests.test_replaced_reader_copied_repository_wrong_root_or_definition_cannot_mint -v
Ran 3 tests in 22.083s
OK
```

### Final status/industry/signature/raw-source GREEN (frozen production source)

```text
D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_metric_engine.MetricClosureTests.test_vetoed_unscored_company_still_supplies_a_complete_metric tests.test_formal_metric_engine.MetricClosureTests.test_industry_correction_during_feature_reads_is_rechecked_for_the_whole_population tests.test_formal_metric_features.MetricProjectionTests.test_absence_does_not_hide_invalid_provider_or_raw_source tests.test_formal_metric_features.MetricProjectionTests.test_absence_rejects_invalid_child_signature -v
Ran 4 tests in 78.816s
OK
```

### Parent compatibility evidence

Parent independently reported:

```text
tests.test_formal_feature_repository + tests.test_formal_financial_features + tests.test_formal_feature_contract
85 tests / 61.122s / OK
```

That run had unchanged pre/post feature repository SHA-256 `45130EF88E7A3F504E78F2CA84C8FB3853080C2F2D503DFCC6DB618BD31E868A`. The subsequent approved private validator export changed this source hash to the frozen hash above. No existing projection payload or selection calculation changed in that last edit. Do not label the parent's earlier 85 tests as an exact final-source run; parent was notified of the hash transition and owns final regression verification.

`git diff --check` completed with exit code 0. Git emitted existing workspace LF->CRLF conversion warnings for the three tracked changed files; no whitespace error was reported. No commit/stage/checkout command was run.

## Self-review and handoff concerns

- Independent signed root, frozen universe, full population, industry absence and feature present/absence identities remain bound end to end. No caller subset, raw score, override or fake official proof path was added.
- Missing sibling metrics never control a valid metric's peer eligibility. The real fixture proves BJ membership, template separation, exact 19/20 boundaries, negative/zero values and veto/unscored independence.
- Capture closures, exact types and immutable proof state reject copy/substitution; no public structural serialization can mint an official proof. Final batch freshness is a captured verified-read result, not an indefinite latest-state guarantee; corrections require a new batch/hash.
- No V6 formula, V6 storage bytes/schema, old complete-feature contract, legacy score, policy, collection, V7, pool or production configuration changes were made.
- No missing T/no_coverage evidence is converted to neutral 50. The parent explicitly reserved the future signed exception/linkage work for Task 3.
- Formal scores are in-memory sealed artifacts in this slice; persistence/use by later score modules remains Task 3 scope. Consumers must preserve the qualified metric IDs and proof APIs described here.
- Full authenticated source/receipt fixtures are relatively slow. The complete 22-member run took 172.079s and the correction integration run 152.243s. Arithmetic and score reuse themselves avoid rereads/resorts; no broad repository/calendar suite was repeatedly run.
- Focused tests are accurately separated by source stage above. This agent did not run the final combined 18-test engine module or the final combined 29-test projection module after the last private-validator edit; parent owns combined regression and independent review. All specifically changed final-seal/tuple paths and final additional integration cases were GREEN on the frozen source.
- No active test process remains from this agent at report time. All created fixture directories were owned temporary fixtures with their registered cleanup path; no user directories were selected for cleanup.

## Review fix round 1 — final handoff

Parent independently confirmed three Important findings: sequential final rereads missed earlier-member changes during a later final reread; selector string subclasses could spoof lookup identity; and a strong context->batch reference combined with the batch context cache rooted both proofs indefinitely. All three were reproduced with focused RED tests and addressed in this round. The original six-file reviewed baseline was staged by the parent before this round. All round-1 edits remain unstaged; no index/commit operation was performed.

Final source SHA-256 for re-review:

```text
ashare_pipeline/formal_metric_engine.py       F9F26193CF82B31073EB6FE2AE999871CA1BCC2F59184522BA6EB1A05FD64EC2
ashare_pipeline/formal_metric_batch_guard.py  13EE31FB3742337F985AB852599FA4A9A42253879232FBC6388DA66B7E141B1A
ashare_pipeline/formal_feature_repository.py  88879938273FDF8C002DE267401C44117E80E9CD3FC8809F99237407DC548030
```

Round-1 file changes: existing `formal_metric_engine.py`, existing `tests/formal_metric_feature_fixtures.py`, existing `tests/test_formal_metric_engine.py`, new `ashare_pipeline/formal_metric_batch_guard.py`, new `tests/test_formal_metric_batch_guard.py`, and this report. No StateStore changes. The feature repository, existing projection tests and original shared metric fixture are unchanged in this round.

Read-only unittest discovery confirms final method counts: engine 18; new batch-guard/review module 13; metric features 29. No duplicate TestCase imports/inheritance were introduced. This agent has no remaining background test process. Parent reported pre-fix combined verification of 114 tests / 171.617s / OK and 38 tests / 306.670s / OK; those are explicitly pre-fix evidence, not post-fix claims.

### Approved coherence boundary and new provider API

Parent approved one minimal new owned-provider/guard module and explicitly rejected a full-duration SQLite writer lock, further sequential sweeps, a database-only epoch, arbitrary provider-field introspection, or duck-typed claims of a stable/verified generation.

```python
from ashare_pipeline.formal_metric_batch_guard import FormalMetricCurrentInputProvider

provider = FormalMetricCurrentInputProvider(store)
provider.publish(explicit_complete_formal_feature_current_input)
# Repeat publication for each exact security/cutoff/template/root request.
features = FormalFeatureRepository(store, bundle_store,
    registry_signature_verifier=verifier, current_input_provider=provider)
# FormalMetricInputRepository constructor/build_batch API remains unchanged.
```

The trusted completeness owner publishes exact `FormalFeatureCurrentInput` values, including the complete facts/issues tuple and logical batch ID. The provider validates the existing exact current-input boundary, detaches all facts/issues into canonical bytes, and returns freshly reconstructed records on each read. Its records, lock, initialization identity and monotonically increasing publication epoch are closure-private; no mutable records are exposed. Unknown requests fail rather than defaulting to an empty complete input. The provider itself does not certify financial facts: all normal feature reads continue to authenticate published facts against actual persisted facts, source/raw receipts and the signed graph. There are no caller-selected official score or classification fields.

All publication paths go through `publish`; every accepted publication advances the whole-provider epoch, even if its content is unchanged. Reentrant publication during finalization is rejected and advances the epoch so a caller cannot swallow that rejection and obtain a completed capability. Other-thread publications are excluded by the short finalization lock. Constructor copying, fake exact-looking provider objects and replaced provider methods are rejected. A provider is bound to the exact initialized StateStore and captured database path/read dependency.

Legacy arbitrary `FormalFeatureCurrentInputProvider` implementations remain supported by the old single-feature APIs. They now fail closed for `build_batch`, including all-pending/entirely unclassified universes and before missing-universe success could bypass the provider requirement. Tests demonstrate a generic provider still returns the old genuine projection-or-None result while the new complete-batch path rejects it. Existing feature projection/absence canonical bytes and existing batch/row/context/score payload schemas/hashes are unchanged by this guard; publication epochs are operational coherence checks, not nondeterministic persisted identities.

The fixture now uses this exact owned provider and explicitly publishes initial complete snapshots, subsequent financial corrections, issue corrections and logical-generation changes. Its helper `publish_current`, `set_issues` and `set_generation` are test-owned publication operations. Optional `put_financial(..., publish=False)` creates an actual authenticated DB correction without updating provider memory, allowing the DB half of the final barrier to be independently tested. No production provider-private-field introspection was added.

### Read interval, final fence and publication point

Before any universe, context or feature reads, the repository opens one observer connection through the actual same-store `StateStore._connect`, captures its SQLite `PRAGMA data_version`, and captures the owned provider epoch under its publication lock. The observer never commits data writes. The same observer remains open throughout the complete interval, so commits from any other connection are detected. This is intentionally conservative: even unrelated progress commits invalidate the attempt. There is no internal infinite retry loop; callers receive a failure and may schedule a fresh bounded attempt.

The existing genuine repository paths still perform the initial per-member reads, final feature present/absence rechecks and the 2B full-population closure. The optimistic barrier additionally catches changes that occur after an earlier member's final reread, including memory-only issue/generation publications and actual later financial DB commits.

At finalization, the provider publication lock is held, then the same observer obtains a short `BEGIN IMMEDIATE` writer reservation and compares the current observer `data_version` and captured provider epoch. These checks cover the full read/preparation interval. The parent consulted SQLite's authoritative data_version and transaction documentation before approving this design; this agent made no network call.

All expensive deterministic JSON, hashing, freezing, index construction and proof registration occur BEFORE acquiring the writer reservation. Prepared row and batch objects share an unpublished capability held only in the engine's closure-private proof records. Public constructors cannot supply it, it is not a serialized `verified` flag, and every proof/consumer rejects these objects while unpublished. The final callback performs only one capability publication and returns the prepared batch: no large encoding, freezing, per-row loop or repository read occurs under the writer reservation.

For a successful operation, the publication callback is the linearization point while both provider publication exclusion and the SQLite writer fence hold. Finalization checks the provider epoch again after the callback. If finalization fails after the callback—including a final epoch check, rollback or context-manager cleanup failure—the engine revokes the shared private capability, making all prepared row/batch handles unusable. Tests capture such candidate handles through a profiler solely to prove they remain unusable on failed finalization. Those hooks do not create official proofs or replace production readers.

Finalization always rolls back and closes its read observer. Provider `finalizing` state resets in a nested `finally`, even if the real SQLite rollback raises. A fault-injection test closes the actual observer after the publication callback, confirms proof revocation, then successfully republishes and builds again. Another test attempts a second-connection `BEGIN IMMEDIATE` while canonical preparation executes: it succeeds throughout preparation, and a separate test confirms it is rejected during the actual final fence and succeeds after cleanup.

Timeout precision: inherited `StateStore._connect` setup uses its existing 5-second SQLite timeout/busy_timeout. After opening, this guard sets observer busy_timeout to 1,000 ms, bounding final writer-reservation acquisition. This is NOT a total-operation one-second limit and does not bound arbitrary computation. The expensive preparation was moved outside the fence specifically because busy_timeout does not limit lock holding time.

File boundary: existing content-addressed raw/feature receipt files are reauthenticated through the existing readers. Logical corrections must change authenticated DB facts/receipts and therefore invalidate the observer epoch. This is not a whole-filesystem atomic snapshot and does not claim to exclude arbitrary out-of-band OS file tampering through the final publication instruction. No new native filesystem lock subsystem or weakened existing raw-source check was introduced.

### Selector and ownership fixes

`MetricInputBatch.input_for` and `build_metric_peer_context` now require exact `str` types for both security and metric selectors before dictionary lookup. Context/cache/canonical identity comes from the genuine focal row after lookup. Hostile `str` subclasses whose equality and hash impersonate existing keys are rejected for both selectors and both API paths.

Contexts retain only a weak owner reference to their exact batch. The batch still holds its scoped immutable cohort tuples, rank tables and context cache. Dropping a batch therefore releases its input proofs even if a detached context remains live; dropping that context also collects it. A detached historical context cannot score a new batch, including a new batch with equal canonical content. Existing tuple and context reuse remains intact.

### Exact round-1 RED/GREEN evidence

Commands ran in the same worktree with the same Python path as above. Blocks preserve decisive output lines; repeated traceback frames are omitted.

Baseline review regressions:

```text
D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_metric_batch_guard -v
AssertionError: <...MetricInputBatch object...> is not None
AssertionError: ValueError not raised
Ran 3 tests in 23.322s
FAILED (failures=6)
```

The six failures are one retained-batch failure, one final-sweep provider correction failure, and four hostile-selector subtest failures. Only the three review methods existed when that invocation loaded the module.

Owned guard API RED:

```text
D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_metric_batch_guard.OwnedProviderGuardTests -v
AssertionError: unexpectedly None : owned batch guard is missing
Ran 4 tests in 0.002s
FAILED (failures=4)
```

Initial integration corrections: the first seven-test guard run had six passing methods and one fixture SQL error (`no such column: priority`); the fixture was corrected to update the real `formal_collection_task.updated_at` column for an unrelated committed change. A separate DB-correction recovery assertion initially expected `current_receipt_absent` on the metric row despite that fixture deliberately not publishing industry Context; the test now asserts the authenticated feature state's explicit absence, leaving the independently correct `context_absent` row reason intact. These were fixture/assertion setup corrections, not intended RED proof and not production fixes.

Initial complete guard/review GREEN, before the short-fence refinement:

```text
D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_metric_batch_guard -v
Ran 10 tests in 86.813s
OK
```

This covered memory-only earlier-member correction on the third SH provider read (the final sweep), actual DB-only earlier-member correction during that final sweep, clean rejection followed by success, generic/copy provider rejection including all-pending factory compatibility, exact selectors, GC, explicit detached publication, other-connection epoch detection, writer fencing and swallowed reentrant-publication rejection.

Short writer-fence/prepared-capability RED:

```text
D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_metric_batch_guard.MetricBatchReviewTests.test_canonical_preparation_does_not_hold_the_writer_reservation tests.test_formal_metric_batch_guard.MetricBatchReviewTests.test_prepared_metric_rows_are_unusable_until_the_complete_batch_is_published -v
AssertionError: expensive canonical preparation held the metric writer reservation
AssertionError: ValueError not raised
Ran 2 tests in 7.926s
FAILED (failures=2)
```

Failed-finalization revocation RED:

```text
D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_metric_batch_guard.MetricBatchReviewTests.test_failed_finalization_revokes_prepared_proofs_and_recovers_publication -v
AssertionError: ValueError not raised
Ran 1 test in 2.154s
FAILED (failures=1)
```

Final-source publication/preparation/cleanup GREEN:

```text
D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_metric_batch_guard.MetricBatchReviewTests.test_canonical_preparation_does_not_hold_the_writer_reservation tests.test_formal_metric_batch_guard.MetricBatchReviewTests.test_prepared_metric_rows_are_unusable_until_the_complete_batch_is_published tests.test_formal_metric_batch_guard.MetricBatchReviewTests.test_failed_finalization_revokes_prepared_proofs_and_recovers_publication -v
Ran 3 tests in 25.024s
OK
```

The last test covers both an epoch change after tentative publication and a real closed-observer rollback failure, then confirms publication and a fresh batch recover. The source hashes at the start of this round-1 section were measured after this GREEN run. Parent is responsible for final combined affected verification and independent re-review; no old pre-fix run is being relabeled as post-fix evidence.

## Review fix round 2 — descendant publication revocation

Status: scoped fix implemented and frozen after focused RED/GREEN; awaiting parent independent re-review and proportionate fresh verification. Round 1's original three findings were addressed by the scoped review; this round addresses its new Important finding that derived contexts and scores retained independent authenticated state after the originating batch was revoked. The parent-reported 31 tests / 1248.278s / OK and 46 feature/registry tests are PRE-round-2 evidence, not evidence for this fix.

Only `ashare_pipeline/formal_metric_engine.py`, `tests/test_formal_metric_batch_guard.py`, and this report were edited in round 2. No guard module, interface, schema, StateStore, fixture helper, Git/index, progress, or user data edits were made. Original staged review baseline remains untouched by this agent.

### Implementation and identities

The context mint now receives `publication=record(batch, MetricInputBatch)[4]`; the score mint receives `publication=batch_record[4]`. Both therefore inherit the owning batch's SAME closure-private mutable publication capability instead of minting independent default-true capabilities. Existing failure cleanup already revokes that capability, so revocation reaches input, batch, context, and score proofs together. No public flag, new provider API, schema field, canonical payload, canonical byte calculation, or hash identity was added or changed. The tentative publish/finalization protocol and writer-fence duration are unchanged.

The context's owner remains `weakref.ref(batch)`. Sharing the publication capability does not retain the batch itself: successful detached contexts/scores remain usable historical proofs after batch collection; same-batch context identity caching and cross-focal cohort tuple reuse remain intact. A score still requires a context owned by the same live batch when it is created.

Frozen SHA256 values after the focused GREEN run:

```text
ashare_pipeline/formal_metric_engine.py
49116DC11DA73E2D7ECE843A38FD6B2EC197E47560EBEB7AC1169BDC09206C91
tests/test_formal_metric_batch_guard.py
1AA151CDE32E603B32A232DE4F9A839C5340662105FF02A1F5E7B926DCF20965
ashare_pipeline/formal_metric_batch_guard.py (unchanged from round 1)
13EE31FB3742337F985AB852599FA4A9A42253879232FBC6388DA66B7E141B1A
```

### Real fixture and TDD evidence

The TDD skill and writing-good-tests reference required an observed failure before production changes. A new `DerivedProofPublicationTests` class builds the real signed 22-member same-store financial fixture, persisting industry, source, and feature receipts for each member. It selects one existing qualified metric, `METRICS[0]`, with independently assigned values `index - 1`; BJ430001 has the smallest value, a genuine 20-member secondary-industry cohort, and the literal expected percentile `Decimal("2.5")`. No fake score or synthetic official proof is used. Test-created temporary artifacts use the existing fixture cleanup; no temporary-directory behavior was changed.

At the real tentative-publication callback return, a profile hook derives a genuine context and actual score, then attempts a real reentrant provider publication. The provider rejects that publication, the test swallows the rejection, and the final epoch check rejects the build. All three escaped proofs must reject `require_verified()`, `canonical_bytes()`, and `to_dict()`. Before the fix, the batch rejected correctly but all six context/score method checks failed. The separate success test verifies the literal cohort/score, same-context cache identity, shared peer tuple identity, batch weakref collection, and unchanged usable detached context/score serialization.

Working directory for every command below: `D:/Projects/AShareQiheng/.worktrees/formal-v3-implementation`.

RED command (engine unchanged from round 1):

```text
D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_metric_batch_guard.DerivedProofPublicationTests.test_failed_finalization_revokes_derived_context_and_actual_score -v
(proof='MetricPeerContext', method='require_verified') ... FAIL
(proof='MetricPeerContext', method='canonical_bytes') ... FAIL
(proof='MetricPeerContext', method='to_dict') ... FAIL
(proof='MetricScore', method='require_verified') ... FAIL
(proof='MetricScore', method='canonical_bytes') ... FAIL
(proof='MetricScore', method='to_dict') ... FAIL
AssertionError: ValueError not raised
Ran 1 test in 288.356s
FAILED (failures=6)
```

Each failure was the same expected `ValueError not raised` at the post-revocation method assertion, not fixture/setup failure. Exit code 1. The literal genuine cohort and actual score assertions passed before revocation.

GREEN command after the two mint-argument changes:

```text
D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_metric_batch_guard.DerivedProofPublicationTests -v
test_failed_finalization_revokes_derived_context_and_actual_score (tests.test_formal_metric_batch_guard.DerivedProofPublicationTests.test_failed_finalization_revokes_derived_context_and_actual_score) ... ok
test_successful_detached_context_score_and_cohort_cache_remain_valid (tests.test_formal_metric_batch_guard.DerivedProofPublicationTests.test_successful_detached_context_score_and_cohort_cache_remain_valid) ... ok
Ran 2 tests in 264.880s
OK
```

Exit code 0; no skips or failures. No broad legacy or whole-repository test run was launched in this round. The real profiled batch is expensive; these focused results are intentionally not represented as full-regression evidence.

Additional read-only checks:

```text
git diff --check
exit 0; only existing LF-to-CRLF warnings for engine, financial fixture helper, and engine test files
D:/Projects/AShareQiheng/.venv/Scripts/python.exe -c "import unittest; l=unittest.TestLoader(); print({m:l.loadTestsFromName(m).countTestCases() for m in ['tests.test_formal_metric_engine','tests.test_formal_metric_batch_guard','tests.test_formal_metric_features']})"
{'tests.test_formal_metric_engine': 18, 'tests.test_formal_metric_batch_guard': 15, 'tests.test_formal_metric_features': 29}
```

Self-review: omitting either new publication argument independently restores three failing revocation assertions for that proof type. No canonical content changes are needed because this is runtime provenance state, not financial content. Weak ownership and successful historical proofs are explicitly covered. No remaining implementation blocker identified within round-2 scope; final acceptance remains with parent review/verification. Source is frozen and there are no remaining agent-owned Python test sessions.
