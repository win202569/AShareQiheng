# Task R3 implementation report

## Current checkpoint

Fix round 2 completed 2026-09-19; **no active test session**. Fresh focused RED
`20206`: 2 tests /14.954s, FAILED (errors=5), exit 1, exactly the expected
typed-error regression. Scoped GREEN `52942`: **32 tests /686.364s, OK, exit 0**,
all 31 Source cases plus parent-correction fetch integrity regression. The minimal
source-only change was committed as `3c3b3c12a6a5f8f6c98d054131e4a097cad710c4`.
Root independently checked all six hashes and accepted the scoped task gate after
clean fix2 re-review; see `task-R3-fix2-review-3c3b3c1.md`. No active R3 work remains.
Tests and other code were unchanged by fix2; final project acceptance remains later.
Former full session
`18573` COMPLETED: **272 tests /3109.739s, FAILED (errors=5), exit 1**. Its five
errors are ValueError leaks from `request_record(request).previous` in two Source
tests (four mutated fields, one forged request); 270 tests emitted OK, including
all 30 Store and all 211 StateStore tests. Complete output is retained below.
Fix1 scoped review remains clean; original Minor coverage is deferred by controller.
This round changes only the source lookup's exception conversion, preserving parent
integrity errors and valid execution order. Only scoped RED then Source+parent-race
GREEN are authorized now; no new full272/project-wide completion claim or run.
Pre-fix2 HEAD `8385ff6529cd27749fd9f4cc1a36cbd58dd397f3` is external/user-owned
(docs/tmp SQLite), untouched; the six R3 files were unchanged from `ca71683`.
Earlier "still running" entries below are historical progress snapshots.

Base: `c7fb672bfe47d2831bb4c1e850d6397407b9464b` on `codex/formal-v3-implementation`.
Workspace: `D:/Projects/AShareQiheng/.worktrees/formal-v3-implementation`.
Only the six authorized implementation/test files are edited, plus this task report.
No Git writes, dependency installs, real network, production data/DB/signatures, scoring,
merge or push. All test data uses owned TemporaryDirectory instances; existing
`tmpj4zv9_fq/` is preserved.

## Instructions and authority rulings

Read the complete TDD skill and writing-good-tests reference, implementer-prompt,
R3 brief, and the R2 handoff/fix-round material before implementation.
Root approved the paired eager source/store initialization: source owns the closed
RangeObservation authority; store owns persistence. Source invokes the store builder
once with private captured anchors, captures exact Store/private reread functions,
publishes the paired types, and removes builder/mint names. Both import orders are tested.

Root approved retaining unresolved and structurally valid date-only effective-time
claims as source assertions. R3 current status authenticates persisted source evidence
and source-version selection; it does not certify freeze visibility or effective-time
proof. W1 must authenticate the actual time basis or produce `visibility_unproven`.
No old single-day Context bootstrap dependency is introduced.

Root approved lease-result augmentation with genuine in-memory `request` and `binding`
handles. These are never persisted as serialized capabilities. Parent continuations
must preserve exact StateStore identity and resolved raw root; reopening a range store
over those same dependencies is allowed. History remains auditable but not executable.

## TDD evidence

### Initial RED

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_range_store tests.test_state_store.FormalV7RangePersistenceTests -v
```

Exit 1; tool wall time 0.6516964s; unittest `Ran 3 tests in 0.024s`;
`FAILED (failures=3)`.

All three failures were expected assertions before production changes:

```text
test_verified_replay_retains_one_producer ... FAIL
AssertionError: False is not true : the genuine enqueue/lease/fetch/persist fixture is absent
test_all_continuous_entrances_and_reopen ... FAIL
AssertionError: 6 != 7
test_partial_and_premature_v7_objects_preserve_old_rows ... FAIL
AssertionError: False is not true
Ran 3 tests in 0.024s
FAILED (failures=3)
```

The expanded initial store regression module was then run with:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_range_store -v
```

Exit 1; tool wall 0.4944203s; `Ran 10 tests in 0.101s`;
`FAILED (failures=12)`. All failures were the intentionally missing real RangeStoreFixture,
covering requested lease/retry/current/history/immutability/receipt behaviors before store implementation.

### Focused GREEN and additional regression RED

Migration command:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_state_store.FormalV7RangePersistenceTests -v
```

Initial two cases: exit 0, `Ran 2 tests in 0.523s`, `OK` (tool wall 1.1695808s).
After explicit preexisting table/index-name collision and legacy-row preservation coverage:
exit 0, `Ran 3 tests in 0.556s`, `OK` (tool wall 1.3941468s).

First genuine producer/replay command:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_range_store.FormalRangeStoreTests.test_verified_replay_retains_one_producer -v
```

Exit 0; `Ran 1 test in 78.882s`, `OK`.

Pre-import public StateStore alias substitution command:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_range_store.FormalRangeStoreTests.test_public_state_store_alias_before_import_does_not_replace_genuine_type -v
```

RED exit 1, `Ran 1 test in 0.196s`, `FAILED (failures=1)`: replacing the
public alias before range import caused `AttributeError: type object 'Fake' has no
attribute '_transaction'`. Fixed by a StateStore-owned closure capturing its exact
original class and transaction/connect/insert/schema anchors at module completion.
GREEN exit 0, `Ran 1 test in 0.311s`, `OK` (tool wall 0.8404787s).

Both-import-orders command:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_range_store.FormalRangeStoreTests.test_both_import_orders_and_no_exposed_authority_builder -v
```

Exit 0; `Ran 1 test in 0.376s`, `OK` (tool wall 0.8824018s).
Standalone fresh store-first/source-first imports also exited 0 in 0.3532403s/0.3455434s.

Worker handoff command:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_range_store.FormalRangeStoreTests.test_lease_supplies_authenticated_request_and_binding_to_worker -v
```

RED exit 1, `Ran 1 test in 32.609s`, `FAILED (failures=1)`;
`AssertionError: 'request' not found in ...`. Root-approved fix prepares genuine execution
request/binding outside the writer transaction, then rereads/CASes the unchanged candidate
inside the short transaction and returns those handles with the lease.

Exact bool/int attempt payload command:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_range_store.FormalRangeStoreTests.test_attempt_payload_boolean_does_not_equal_integer -v
```

RED exit 1, `Ran 1 test in 112.372s`, `FAILED (failures=1)`;
expected `ValueError` was absent after replacing canonical attempt_no 1 with true
and recomputing its payload hash. Fixed using canonical byte comparisons against
the exact producer payload, rather than Python bool/int equality.

Missing raw bytes on enqueue replay command:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_range_store.FormalRangeStoreTests.test_raw_file_removed_after_commit_is_not_reusable -v
```

RED exit 1, `Ran 1 test in 111.428s`, `FAILED (failures=1)`;
history correctly rejected the missing raw file, but enqueue replay returned a verified
task without rereading its receipt. Fixed by a captured authenticated reread before
returning any existing verified enqueue result.

## Final compatibility evidence

Pending final frozen run. Complete output, counts, exit, elapsed time and six file hashes
will be appended when validation completes.

## API handoff and self-review

### R4 worker API

`FormalRangeStore(state_store, *, root, signature_verifier, source_factory)` captures
the exact initialized StateStore, resolved snapshot filesystem root, verifier method,
and `source_factory(binding) -> FormalRangeSource`. It reloads the actual signed
bundle/feature/scoring/policy/range binding from that StateStore. Factory output must
be the exact genuine Source on that exact loaded binding. No arbitrary request restore
or observation mint API is published.

`enqueue(request, *, refresh_generation)` returns the detached task dictionary.
`lease_next(worker_id, *, lease_seconds)` returns that dictionary or None. Its exact
keys are `id`, `request_fingerprint`, `registry_manifest_hash`, `range_config_id`,
`refresh_generation`, `payload_hash`, `status`, `worker_id`, `lease_expires_at`,
`attempt_no`, `next_retry_at`, `result_json`, `error_json`, `created_at`, `updated_at`,
`payload`, `attempt_id`, plus **lease-only in-memory handles** `request` and `binding`.
`request` is the exact genuine FormalRangeRequestV1; `binding` is the genuine
RangeBinding reloaded for its task. These handles must not be serialized as proof.
Other task result methods omit these two handles. enqueue has attempt_id None;
lease/renew/fail and an observation's task identify the actual attempt.

Task `payload` has exactly `schema_version='formal-range-task-v1'`, `request`,
`config`, `source_registry_hash`, `binding_hash`, `parent`, `refresh_generation`.
`request` retains the R2 wire fields: schema_version, kind, source, dataset,
security_id, exchange, as_of_utc, start_date, end_date, anchor_descriptor_id,
calendar_descriptor_id, range_config_id, registry_manifest_hash, page_index,
calendar_coverage_hash. `config` is the full signed RangeConfig dictionary. `parent`
is None for the first calendar request, otherwise exactly task_id, observation_hash,
mode (`next_page` or `previous_calendar`). Raw wire, ordinal, payload and task status
alone never authorize a request. Execution reconstruction authenticates current
parent receipts; historical reconstruction is non-executing.

Worker usage is `lease = range_store.lease_next(worker_id, lease_seconds=...)`, then
`source = source_factory(lease['binding'])`,
`fetch = source.fetch_verified(lease['request'])`, then
`range_store.persist(lease['id'], worker_id, lease['attempt_id'], fetch=fetch)`.
Source factory/transport must match the signed implementation versions. The Store
has its own captured source_factory for independent parser replay. Public mutation
of source read/current aliases does not replace the captured operations.

`renew(task_id, worker_id, attempt_id, *, lease_seconds)` and
`fail(task_id, worker_id, attempt_id, *, code, retryable, next_retry_at)` require the
same live, unexpired exact attempt. Expiry equality means takeover is permitted.
Lease duration is a positive exact int (not bool). Failure code is nonempty exact
text. retryable is exact bool; retryable failures require a future aware ISO time,
terminal failures require next_retry_at None. Worker diagnostics do not establish
missing/evidence facts. Existing transport error types are FormalRetryableSourceError,
FormalSourceBlocked, FormalTerminalSourceError from the source transport boundary;
R3 integrity/authority failures remain ValueError and must not be converted into
domain pending by matching exception text. SQLite failures remain SQLite exceptions.

### Persistence and read semantics

`persist` returns a genuine RangeObservation only after content-addressed raw/manifest
files, actual registered parser normalization, producer snapshot/receipt and verified
task state agree. DB failure rolls back snapshot/receipt/completion together, leaving
already-written files intact for diagnosis. An already-verified persist is idempotent
only for the same worker+attempt and exactly the same authenticated fetch manifest;
it rereads original bytes and producer receipt, creates no second producer, and does
not grant another worker ownership. A new refresh generation preserves old rows/files.

`read_verified(task_id)` authenticates receipt/raw/source output and returns an audit
observation; it does not by itself certify latest source version. Call
`observation.require_current()` or `select_current(request_fingerprint)` for current
qualification. `read_history(task_id)` retains the same audit hash/data even after
supersession, but can never require_current or authorize fetch/page/chunk continuation.
`select_current` returns None only when no current verified candidate exists; ambiguity,
tamper, dependency replacement or mid-read correction raises integrity failure.
Refresh/insertion/capture ordering is not source version ordering. Equivalent same
source generation/content versions may coexist and both qualify current. Unequal
version content follows authenticated source_updated/publication ordering, conservatively.

Observation exposes readonly request/document/receipt/snapshot/task/generation views,
observation_hash, detached `to_dict()`, and `require_current() -> None`.
Observation identity excludes mutable task scheduling fields (only task id contributes)
and receipt recorded_at; evidence capture/source/producer/request identities are retained.
`RangeObservation` is owned by source and re-exported as exactly the same type by store.
Current observations qualify only source/request/raw/normalization/receipt/source-version;
they do not certify freeze visibility. Date-only effective/hash pairs are source assertions,
including non-null structurally valid pairs. W1 must independently authenticate effective
time or emit visibility_unproven; no old single-day Context bootstrap is used here.

### Self-review (final verification still pending)

All changes remain in six authorized paths plus this report. No Git writes, network,
production DB/signatures/scoring, dependency installs or data deletion. Temporary fixtures
alone own their cleanup; tmpj4zv9_fq is preserved. Source and Store retain separate
authority/persistence responsibilities with eager paired initialization and no exposed mint.
Historical parent chains cannot confer execution authority; destination continuation
requires the exact originating StateStore identity and resolved filesystem root.
Both import orders and genuine first-request/restart paths have dedicated regressions.

Performance limitation: authentic binding/graph and ancestor rereads are intentionally
not cached as proof. Static inspection found repeated full graph derivations and quadratic
current-chain traversal; historical traversal is linear. No production throughput claim
or graph/caching optimization is made. Root explicitly declined broad performance work
in this correctness task. Root alone owns staging, commits and independent review.

## Recovery continuation (2026-09-12)

Recovered on HEAD `5c40dd86466cc706691ff65784fe88599591ae8f`; task BASE remains
`c7fb672bfe47d2831bb4c1e850d6397407b9464b`. All six dirty task files and earlier
report evidence retained. No prior Python test process remained at recovery.
The controller ledger records pre-race focused GREEN: four tests /659.443s and
later intended race REDs; those results are not final frozen compatibility.
Current code already has candidate identity-set fences, parent persist/fetch fences,
immutable RangeObservation and original source authority tuple. The sealed-fetch
fix is still absent: persist rereads fetch.raw_bytes after its parser callback.
The existing callback mutation regression is retained and being run alone.

Recovery RED command:
```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_range_store.FormalRangeStoreTests.test_fetch_byte_mutation_during_parse_cannot_commit_inconsistent_evidence -v
```
Only active test session: `47857`, initial output (10.001s; still running):
```text
test_fetch_byte_mutation_during_parse_cannot_commit_inconsistent_evidence (tests.test_formal_range_store.FormalRangeStoreTests.test_fetch_byte_mutation_during_parse_cannot_commit_inconsistent_evidence) ...
```
No terminal result yet. Root's recovery instruction is mutation singleton RED,
minimal fix, singleton plus quick authority/import GREEN, then the prescribed
full Store+Source+StateStore compatibility exactly once on frozen files. Existing
long race focus is not repeated separately; the full suite covers it.

Session 47857 completed: exit 1, `Ran 1 test in 65.253s`, `FAILED (errors=1)`.
Complete remaining output:
```text
ERROR

======================================================================
ERROR: test_fetch_byte_mutation_during_parse_cannot_commit_inconsistent_evidence (tests.test_formal_range_store.FormalRangeStoreTests.test_fetch_byte_mutation_during_parse_cannot_commit_inconsistent_evidence)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\tests\test_formal_range_store.py", line 505, in test_fetch_byte_mutation_during_parse_cannot_commit_inconsistent_evidence
    fixture.range_store.persist(task["id"], "worker", lease["attempt_id"], fetch=fetch)
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\ashare_pipeline\formal_range_store.py", line 508, in persist
    return read(self, task_id)
           ^^^^^^^^^^^^^^^^^^^
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\ashare_pipeline\formal_range_store.py", line 245, in read
    document = source_parse(source, request, raw_bytes=raw, manifest=manifest["fetch"]).to_dict()
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\ashare_pipeline\formal_range_source.py", line 1054, in parse_verified_snapshot
    raise FormalTerminalSourceError("range manifest identity or content hash is invalid")
ashare_pipeline.formal_sources.FormalTerminalSourceError: range manifest identity or content hash is invalid

----------------------------------------------------------------------
Ran 1 test in 65.253s

FAILED (errors=1)
```
This exposed the expected post-commit inconsistency but its typed source error
escaped the test's ValueError catch. Test now also catches FormalTerminalSourceError
to inspect persisted DB/raw state and fail an explicit integrity assertion.
No production change yet; rerunning identical singleton command.

Only active test session `22662`: identical RED command, initial pending line
matches session 47857; first wait 10.014s. No other test process launched.

Session 22662 terminal RED: exit 1, `Ran 1 test in 46.809s`, expected assertion
failure proving wrong bytes were committed into a verified snapshot. Full remainder:
```text
FAIL

======================================================================
FAIL: test_fetch_byte_mutation_during_parse_cannot_commit_inconsistent_evidence (tests.test_formal_range_store.FormalRangeStoreTests.test_fetch_byte_mutation_during_parse_cannot_commit_inconsistent_evidence)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\tests\test_formal_range_store.py", line 513, in test_fetch_byte_mutation_during_parse_cannot_commit_inconsistent_evidence
    self.assertEqual(snapshots[0][0], original_hash)
AssertionError: '884183c0fbf65da31fc41bbff66610c39b8fd0df35e61c7df64573756c95781d' != 'c35ad74f77ccf6857bea93e0fa2859cd7a47c063584f35af6be20e00dc54dbb6'
- 884183c0fbf65da31fc41bbff66610c39b8fd0df35e61c7df64573756c95781d
+ c35ad74f77ccf6857bea93e0fa2859cd7a47c063584f35af6be20e00dc54dbb6


----------------------------------------------------------------------
Ran 1 test in 46.809s

FAILED (failures=1)
```

Minimal fix now applied: source-owned original registration checker captures the
registered manifest as immutable canonical bytes and the original exact raw bytes
in one snapshot. Store derives its detached manifest from those bytes and uses only
that snapshot for replay, file writes, hashes, receipt and producer comparison.
No fetch slots or public fetch checker/manifest dispatch occur after capture.
Existing source/config/parent fences retained, no graph cache/performance rewrite.

Recovery focused GREEN command (only active session `69941`, first wait 10.001s):
```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_range_store.FormalRangeStoreTests.test_fetch_byte_mutation_during_parse_cannot_commit_inconsistent_evidence tests.test_formal_range_store.FormalRangeStoreTests.test_observation_proof_methods_and_lookup_cannot_be_shadowed tests.test_formal_range_store.FormalRangeStoreTests.test_original_observation_authority_survives_public_alias_replacement tests.test_formal_range_store.FormalRangeStoreTests.test_both_import_orders_and_no_exposed_authority_builder -v
```
Initial output:
```text
test_fetch_byte_mutation_during_parse_cannot_commit_inconsistent_evidence (tests.test_formal_range_store.FormalRangeStoreTests.test_fetch_byte_mutation_during_parse_cannot_commit_inconsistent_evidence) ...
```

Focused run progress at 20:16:53 +04:00: approximately 70s elapsed, still in
mutation case; test worker PID 12140 consumed 61.44 CPU seconds. No failure or
terminal output yet. This is active computation, not evidence of a hang.

Focused session 69941 completed: exit 0, `Ran 4 tests in 86.584s`, `OK`.
Complete remaining output:
```text
ok
test_observation_proof_methods_and_lookup_cannot_be_shadowed (tests.test_formal_range_store.FormalRangeStoreTests.test_observation_proof_methods_and_lookup_cannot_be_shadowed) ... ok
test_original_observation_authority_survives_public_alias_replacement (tests.test_formal_range_store.FormalRangeStoreTests.test_original_observation_authority_survives_public_alias_replacement) ... ok
test_both_import_orders_and_no_exposed_authority_builder (tests.test_formal_range_store.FormalRangeStoreTests.test_both_import_orders_and_no_exposed_authority_builder) ... ok

----------------------------------------------------------------------
Ran 4 tests in 86.584s

OK
```

## Frozen recovery compatibility

Code/test files frozen after focused GREEN. SHA-256 values:
```text
9ea048b62153321cdb5d44f0364aa60b9a4fb67ec1a074b19c7012bb35897d04  ashare_pipeline/state_store.py
45282d4b6431f58a6ac51f209adaaeb9b1b85543dff15552c32cb5b18b35e77c  ashare_pipeline/formal_range_store.py
ed4ea27bf7af4f6afcd7f547797400c6879747f065f73d1c6e4da9f694a24b80  ashare_pipeline/formal_range_source.py
a7dc237578729956adfccef30dc28a1e0c53ddff17eda02f08c376b55ed9ee2b  tests/test_state_store.py
9605db1958609316fdaba2d87bae38f7237b95ca118c02ffe262670d3f7f9e77  tests/test_formal_range_store.py
a37a15e48174cafecf3d0fe70825fc7c2389a6e1bd73508dac8e5532302d602d  tests/formal_range_fixtures.py
```
`git diff --check` exit 0; only Git's existing LF-to-CRLF advisory warnings, no
whitespace errors. The unrelated one-line B1 plan working change belongs to root
and is not part of R3 six-file implementation. F3 files untouched.

Prescribed final command:
```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_range_store tests.test_formal_range_source tests.test_state_store -v
```
Full output and terminal result are appended below incrementally; no completion
claim until its terminal result and post-run file/legacy-DDL hashes agree.

Only active compatibility session `54286`, started about 20:17:40 +04:00.
Initial output at 10.012s:
```text
test_attempt_payload_boolean_does_not_equal_integer (tests.test_formal_range_store.FormalRangeStoreTests.test_attempt_payload_boolean_does_not_equal_integer) ...
```

Pre-run legacy DDL verification: read-only AST/literal extraction of Assign and
AnnAssign nodes, canonical JSON as baseline, exact dict equality against
`legacy-ddl-before-v7.md`; command exit 0 /0.317191s, no module import or DB access.
Complete ten results (objects, SHA256):
```text
_V2_INDEX_DDL 1 b6cc73d2f81e507f96afb9acc9813c4347c21438f16ee76520eeb8ff7cd0f5c9
_V2_TABLE_DDL 7 d6f24dfa4b6049da28dccc6f7fae6064bcd69b211c9e174ce26d403835fa078e
_V3_INDEX_DDL 3 cad6e0659a696bb6196574b5791df78ad46261c86f309216e14f58bb36c5640c
_V3_TABLE_DDL 3 bb2a9b5ddbeeea7d882997f448c4b71c28ede7201e4933d5e68ae9639403900c
_V4_INDEX_DDL 0 44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a
_V4_TABLE_DDL 1 389fac8d111b1829b4edf203a6b9a8421aa9e202c8fb51afc628abaaf948534c
_V5_INDEX_DDL 2 927875bb0dafaa3ba358407ad4ea9daa50afa0279c60e4d5123c8b4d62193983
_V5_TABLE_DDL 8 706343d045efa145f9aacc4075a7b19a7b3eaf126b6504ed627be608ed4d18e3
_V6_INDEX_DDL 3 9552130df6575dca64c5cb51b99bb05c64fba347c38372e298269674a46a24fa
_V6_TABLE_DDL 8 7f37c76c4d0c45574e4ea351a5432b63b91f24e741f2aedc05e7d346f1874cd7
All ten legacy DDL constants match baseline exactly.
```

Compatibility output chunk 1:
```text
ok
test_both_import_orders_and_no_exposed_authority_builder (tests.test_formal_range_store.FormalRangeStoreTests.test_both_import_orders_and_no_exposed_authority_builder) ... ok
test_concurrent_leasing_has_one_winner (tests.test_formal_range_store.FormalRangeStoreTests.test_concurrent_leasing_has_one_winner) ...
```

Compatibility output chunk 2:
```text
ok
test_continuation_cannot_be_enqueued_under_a_different_raw_root (tests.test_formal_range_store.FormalRangeStoreTests.test_continuation_cannot_be_enqueued_under_a_different_raw_root) ...
```

Compatibility output chunk 3:
```text
ok
test_correction_during_selection_is_integrity_failure (tests.test_formal_range_store.FormalRangeStoreTests.test_correction_during_selection_is_integrity_failure) ...
```

Compatibility output chunk 4:
```text
ok
test_current_source_correction_invalidates_old_observation_and_continuation (tests.test_formal_range_store.FormalRangeStoreTests.test_current_source_correction_invalidates_old_observation_and_continuation) ...
```

Compatibility output chunk 5:
```text
ok
test_enqueue_replay_and_noncanonical_payload_tamper (tests.test_formal_range_store.FormalRangeStoreTests.test_enqueue_replay_and_noncanonical_payload_tamper) ... ok
test_fetch_byte_mutation_during_parse_cannot_commit_inconsistent_evidence (tests.test_formal_range_store.FormalRangeStoreTests.test_fetch_byte_mutation_during_parse_cannot_commit_inconsistent_evidence) ... ok
test_fetch_verifier_alias_cannot_authorize_an_unregistered_clone (tests.test_formal_range_store.FormalRangeStoreTests.test_fetch_verifier_alias_cannot_authorize_an_unregistered_clone) ...
```

Compatibility logging checkpoint: 5

Controller review heads-up received while session 54286 is running: possible
Important findings concern renew/fail reading time before acquiring the writer
lock, and parent raw/receipt integrity changes during child parser callbacks.
Root explicitly instructed preserving the six-file freeze and current output
until the formal review/fix dispatch. No fix or new test process started.
At 20:22:45 +04:00 about 305s elapsed, worker PID 42628 CPU 287.64s;
five emitted OK results, current source-correction case still running.

## Fix round 1 (FIX_BASE e6c551d)

Read full `task-R3-review-e6c551d.md`. Controller authorized fixing its two
Important findings; Minor additional adversarial coverage is recorded but not
expanded into this round. Complete current compatibility output was preserved
above (8 emitted OK tests). Sole superseded session 54286 was interrupted with
Ctrl-C by controller instruction; exit 1, no additional output or terminal
unittest summary. It is partial diagnostic evidence, never final acceptance.
Read-only Get-Process confirmed no Python process remains. No other process was
terminated. Six files now unfreeze only for the authorized fix, anticipated store
and its tests; no DDL/source changes planned. Full compatibility will restart only
after focused fix GREEN and clean controller-owned scoped re-review.

Read complete receiving-code-review skill and verified both findings directly:
StateStore._transaction executes BEGIN IMMEDIATE before yielding, whereas current
renew/fail sample now before that call; persist's final ancestor fence compares
task sets only and does not retain authenticated parent raw/receipt identities.

Fix-round RED command (sole session 74945, first wait 10.001s):
```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_range_store.FormalRangeStoreTests.test_writer_lock_wait_cannot_extend_expired_lease_or_retry_deadline tests.test_formal_range_store.FormalRangeStoreTests.test_parent_raw_mutation_during_child_parse_cannot_commit_child -v
```
Initial output:
```text
test_writer_lock_wait_cannot_extend_expired_lease_or_retry_deadline (tests.test_formal_range_store.FormalRangeStoreTests.test_writer_lock_wait_cannot_extend_expired_lease_or_retry_deadline) ...
```
Three real lock-held cases cover expired renew, expired terminal failure and a
retry deadline crossed while the lease is still live; no transaction mock.
The parent test changes the actual parent raw file from the child parser callback
and inspects task/snapshot/receipt/attempt state even after an integrity exception.
Controller approved collecting only evidence authenticated by read, recursively
through ancestors, then checking detached row/content identities inside the final
writer without graph reconstruction or parser callbacks. No public proof API.

Fix RED output chunk 1:
```text

  test_writer_lock_wait_cannot_extend_expired_lease_or_retry_deadline (tests.test_formal_range_store.FormalRangeStoreTests.test_writer_lock_wait_cannot_extend_expired_lease_or_retry_deadline) (operation='renew') ... FAIL
  test_writer_lock_wait_cannot_extend_expired_lease_or_retry_deadline (tests.test_formal_range_store.FormalRangeStoreTests.test_writer_lock_wait_cannot_extend_expired_lease_or_retry_deadline) (operation='fail') ... FAIL
  test_writer_lock_wait_cannot_extend_expired_lease_or_retry_deadline (tests.test_formal_range_store.FormalRangeStoreTests.test_writer_lock_wait_cannot_extend_expired_lease_or_retry_deadline) (operation='retry_deadline') ... FAIL
test_parent_raw_mutation_during_child_parse_cannot_commit_child (tests.test_formal_range_store.FormalRangeStoreTests.test_parent_raw_mutation_during_child_parse_cannot_commit_child) ...
```

Fix RED output chunk 2:
```text
FAIL

======================================================================
FAIL: test_writer_lock_wait_cannot_extend_expired_lease_or_retry_deadline (tests.test_formal_range_store.FormalRangeStoreTests.test_writer_lock_wait_cannot_extend_expired_lease_or_retry_deadline) (operation='renew')
----------------------------------------------------------------------
Traceback (most recent call last):
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\tests\test_formal_range_store.py", line 54, in test_writer_lock_wait_cannot_extend_expired_lease_or_retry_deadline
    with self.assertRaises(ValueError):
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: ValueError not raised

======================================================================
FAIL: test_writer_lock_wait_cannot_extend_expired_lease_or_retry_deadline (tests.test_formal_range_store.FormalRangeStoreTests.test_writer_lock_wait_cannot_extend_expired_lease_or_retry_deadline) (operation='fail')
----------------------------------------------------------------------
Traceback (most recent call last):
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\tests\test_formal_range_store.py", line 54, in test_writer_lock_wait_cannot_extend_expired_lease_or_retry_deadline
    with self.assertRaises(ValueError):
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: ValueError not raised

======================================================================
FAIL: test_writer_lock_wait_cannot_extend_expired_lease_or_retry_deadline (tests.test_formal_range_store.FormalRangeStoreTests.test_writer_lock_wait_cannot_extend_expired_lease_or_retry_deadline) (operation='retry_deadline')
----------------------------------------------------------------------
Traceback (most recent call last):
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\tests\test_formal_range_store.py", line 54, in test_writer_lock_wait_cannot_extend_expired_lease_or_retry_deadline
    with self.assertRaises(ValueError):
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: ValueError not raised

======================================================================
FAIL: test_parent_raw_mutation_during_child_parse_cannot_commit_child (tests.test_formal_range_store.FormalRangeStoreTests.test_parent_raw_mutation_during_child_parse_cannot_commit_child)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\tests\test_formal_range_store.py", line 460, in test_parent_raw_mutation_during_child_parse_cannot_commit_child
    self.assertEqual(connection.execute("SELECT status FROM formal_range_task WHERE id=?", (task["id"],)).fetchone()[0], "leased")
AssertionError: 'verified' != 'leased'
- verified
+ leased


----------------------------------------------------------------------
Ran 2 tests in 107.935s

FAILED (failures=4)
```

Fix logging checkpoint: 2

Fix RED session 74945 terminal: exit 1, 2 tests /107.935s, four expected assertion
failures (three lock-wait cases accepted, child state verified after parent raw
damage). No setup/signature/import failure. Only after these failures, applied:
- renew/fail sample now after writer acquisition; renewal expiry and retry deadline
  are calculated/checked there before live owner validation and mutation.
- factored read's existing exact DB/producer/content recheck into a private helper;
  read optionally accumulates its authenticated detached identities and recursively
  passes that list into ancestor reads. persist requests this internal list, then
  checks each tuple inside its final writer together with original candidate sets.
  No parsing/binding reconstruction in writer, no public proof/mint, no new cache.
- clock test copies its time value before signaling the test thread, making the
  deliberate lock-wait schedule deterministic even with an immediate thread switch.

Fix focused GREEN command:
```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_range_store.FormalRangeStoreTests.test_writer_lock_wait_cannot_extend_expired_lease_or_retry_deadline tests.test_formal_range_store.FormalRangeStoreTests.test_parent_raw_mutation_during_child_parse_cannot_commit_child -v
```

Sole active GREEN session 9694; initial wait 10.008s, initial output:
```text
test_writer_lock_wait_cannot_extend_expired_lease_or_retry_deadline (tests.test_formal_range_store.FormalRangeStoreTests.test_writer_lock_wait_cannot_extend_expired_lease_or_retry_deadline) ...
```

Fix GREEN output chunk 1:
```text
ok
test_parent_raw_mutation_during_child_parse_cannot_commit_child (tests.test_formal_range_store.FormalRangeStoreTests.test_parent_raw_mutation_during_child_parse_cannot_commit_child) ...
```

Fix GREEN output chunk 2:
```text
ok

----------------------------------------------------------------------
Ran 2 tests in 108.098s

OK
```

Fix GREEN logging checkpoint: 2

Fix session 9694 terminal GREEN: 2 tests /108.098s, OK, exit 0; covers all three
real lock-wait subcases and parent raw mutation rollback. Frozen for scoped
controller review, not final R3 acceptance. No full compatibility rerun started.
Self-review: inspected complete store+test diff against FIX_BASE; captured evidence
is appended only after source replay, producer/receipt checks and final read
consistency checks. Ancestor recursion carries the same private evidence list;
final writer compares exact DB rows, producer uniqueness, content-addressed path
constraints, hashes and bytes. Candidate-set correction fences and source-owned
fetch snapshot are retained. renew/fail acquire writer before time sampling.
`git diff --check` exit 0 (only Git LF-to-CRLF advisory warnings); no DDL/source or
F3 edits. Review Minor coverage remains explicitly deferred per controller.

Fix-round frozen SHA-256 (20:29:37 +04:00):
```text
9ea048b62153321cdb5d44f0364aa60b9a4fb67ec1a074b19c7012bb35897d04  ashare_pipeline/state_store.py
9a82c014ab4bdc7c1dc122963db5a0190a09ea99519d8f93bc9d6c723986d4f0  ashare_pipeline/formal_range_store.py
ed4ea27bf7af4f6afcd7f547797400c6879747f065f73d1c6e4da9f694a24b80  ashare_pipeline/formal_range_source.py
a7dc237578729956adfccef30dc28a1e0c53ddff17eda02f08c376b55ed9ee2b  tests/test_state_store.py
dbc9b3befec3ff5ffdc08e1983bf9ab51f180998ae6c3b8019ee0b7129f1fc90  tests/test_formal_range_store.py
a37a15e48174cafecf3d0fe70825fc7c2389a6e1bd73508dac8e5532302d602d  tests/formal_range_fixtures.py
```
Four unaffected hashes remain exactly the pre-review freeze. StateStore bytes
unchanged, so the ten verified legacy DDL hashes above remain unchanged as well.

## Final compatibility after clean fix1 re-review

Root confirmed CLEAN scoped re-review: both Important findings ADDRESSED, no new
Critical/Important. Root checkpoint `ca71683561c96dea1d1eb3f1e6e34624fb4e2284`;
same six fix-round frozen hashes. Original Minor regression-coverage item remains
recorded for final branch review, not a hidden acceptance claim.

Exact command (sole test session 18573):
```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_range_store tests.test_formal_range_source tests.test_state_store -v
```
Initial output, first wait 10.016s:
```text
test_attempt_payload_boolean_does_not_equal_integer (tests.test_formal_range_store.FormalRangeStoreTests.test_attempt_payload_boolean_does_not_equal_integer) ...
```

Final compatibility output chunk 1:
```text
ok
test_both_import_orders_and_no_exposed_authority_builder (tests.test_formal_range_store.FormalRangeStoreTests.test_both_import_orders_and_no_exposed_authority_builder) ... ok
test_concurrent_leasing_has_one_winner (tests.test_formal_range_store.FormalRangeStoreTests.test_concurrent_leasing_has_one_winner) ... ok
test_continuation_cannot_be_enqueued_under_a_different_raw_root (tests.test_formal_range_store.FormalRangeStoreTests.test_continuation_cannot_be_enqueued_under_a_different_raw_root) ... ok
test_correction_during_selection_is_integrity_failure (tests.test_formal_range_store.FormalRangeStoreTests.test_correction_during_selection_is_integrity_failure) ...
```

Final compatibility output chunk 2:
```text
ok
test_current_source_correction_invalidates_old_observation_and_continuation (tests.test_formal_range_store.FormalRangeStoreTests.test_current_source_correction_invalidates_old_observation_and_continuation) ...
```

Final compatibility output chunk 3:
```text
ok
test_enqueue_replay_and_noncanonical_payload_tamper (tests.test_formal_range_store.FormalRangeStoreTests.test_enqueue_replay_and_noncanonical_payload_tamper) ... ok
test_fetch_byte_mutation_during_parse_cannot_commit_inconsistent_evidence (tests.test_formal_range_store.FormalRangeStoreTests.test_fetch_byte_mutation_during_parse_cannot_commit_inconsistent_evidence) ...
```

Final compatibility output chunk 4:
```text
ok
test_fetch_verifier_alias_cannot_authorize_an_unregistered_clone (tests.test_formal_range_store.FormalRangeStoreTests.test_fetch_verifier_alias_cannot_authorize_an_unregistered_clone) ... ok
test_later_refresh_same_content_coexists_without_lexical_generation_order (tests.test_formal_range_store.FormalRangeStoreTests.test_later_refresh_same_content_coexists_without_lexical_generation_order) ...
```

Final compatibility output chunk 5:
```text
ok
test_lease_exact_expiry_replaces_attempt_even_for_same_worker (tests.test_formal_range_store.FormalRangeStoreTests.test_lease_exact_expiry_replaces_attempt_even_for_same_worker) ... ok
test_lease_supplies_authenticated_request_and_binding_to_worker (tests.test_formal_range_store.FormalRangeStoreTests.test_lease_supplies_authenticated_request_and_binding_to_worker) ...
```

Final compatibility output chunk 6:
```text
ok
test_observation_is_immutable_and_cannot_be_forged_or_copied (tests.test_formal_range_store.FormalRangeStoreTests.test_observation_is_immutable_and_cannot_be_forged_or_copied) ... ok
test_observation_proof_methods_and_lookup_cannot_be_shadowed (tests.test_formal_range_store.FormalRangeStoreTests.test_observation_proof_methods_and_lookup_cannot_be_shadowed) ... ok
test_original_observation_authority_survives_public_alias_replacement (tests.test_formal_range_store.FormalRangeStoreTests.test_original_observation_authority_survives_public_alias_replacement) ... ok
test_orphan_receipt_and_extra_producer_fail_closed (tests.test_formal_range_store.FormalRangeStoreTests.test_orphan_receipt_and_extra_producer_fail_closed) ...
```

Final compatibility output chunk 7:
```text
ok
test_parent_correction_during_fetch_rejects_standalone_continuation (tests.test_formal_range_store.FormalRangeStoreTests.test_parent_correction_during_fetch_rejects_standalone_continuation) ...
```

Final compatibility output chunk 8:
```text
ok
test_parent_correction_during_persist_rolls_back_child_receipt (tests.test_formal_range_store.FormalRangeStoreTests.test_parent_correction_during_persist_rolls_back_child_receipt) ...
```

Final compatibility active-process chunk 9:
```text

ElapsedSeconds    CPU   PID
--------------    ---   ---
        599.00 588.31 27004
```

Final compatibility output chunk 10:
```text
ok
test_parent_correction_revokes_child_current_but_preserves_history (tests.test_formal_range_store.FormalRangeStoreTests.test_parent_correction_revokes_child_current_but_preserves_history) ...
```

Final compatibility active-process chunk 11:
```text

ElapsedSeconds    CPU   PID
--------------    ---   ---
        725.40 712.45 27004
```

Final compatibility output chunk 12:
```text
ok
test_parent_raw_mutation_during_child_parse_cannot_commit_child (tests.test_formal_range_store.FormalRangeStoreTests.test_parent_raw_mutation_during_child_parse_cannot_commit_child) ...
```

Final compatibility active-process chunk 13:
```text

ElapsedSeconds    CPU   PID
--------------    ---   ---
        902.00 885.41 27004
```

Final compatibility active-process chunk 14:
```text

ElapsedSeconds    CPU   PID
--------------    ---   ---
        990.00 969.83 27004
```

Final compatibility output chunk 15:
```text
ok
test_public_state_store_alias_before_import_does_not_replace_genuine_type (tests.test_formal_range_store.FormalRangeStoreTests.test_public_state_store_alias_before_import_does_not_replace_genuine_type) ... ok
test_raw_bytes_and_manifest_tamper_invalidate_reads (tests.test_formal_range_store.FormalRangeStoreTests.test_raw_bytes_and_manifest_tamper_invalidate_reads) ...
```

Final compatibility active-process chunk 16:
```text

ElapsedSeconds     CPU   PID PrivateMB
--------------     ---   --- ---------
       1158.00 1131.95 27004    147.40
```

Final compatibility output chunk 17:
```text
ok
test_raw_file_removed_after_commit_is_not_reusable (tests.test_formal_range_store.FormalRangeStoreTests.test_raw_file_removed_after_commit_is_not_reusable) ...
```

Final compatibility active-process chunk 18:
```text

ElapsedSeconds     CPU   PID
--------------     ---   ---
       1294.40 1266.03 27004
```

Final compatibility output chunk 19:
```text
ok
test_receipt_failure_rolls_back_snapshot_and_completion_but_keeps_files (tests.test_formal_range_store.FormalRangeStoreTests.test_receipt_failure_rolls_back_snapshot_and_completion_but_keeps_files) ...
```

Final compatibility output chunk 20:
```text
ok
test_reopen_replays_authenticated_page_chain_and_history_cannot_continue (tests.test_formal_range_store.FormalRangeStoreTests.test_reopen_replays_authenticated_page_chain_and_history_cannot_continue) ...
```

Final compatibility active-process chunk 21:
```text

ElapsedSeconds     CPU   PID
--------------     ---   ---
       1493.40 1461.31 27004
```

Final compatibility active-process chunk 22:
```text

ElapsedSeconds     CPU   PID
--------------     ---   ---
       1562.80 1529.31 27004
```

Final compatibility active-process chunk 23:
```text

ElapsedSeconds     CPU   PID
--------------     ---   ---
       1630.30 1595.50 27004
```

Final compatibility active-process chunk 24:
```text

ElapsedSeconds     CPU   PID
--------------     ---   ---
       1699.30 1663.19 27004
```

Final compatibility output chunk 25:
```text
ok
test_retry_and_terminal_failure_never_create_evidence (tests.test_formal_range_store.FormalRangeStoreTests.test_retry_and_terminal_failure_never_create_evidence) ...
```

Final compatibility output chunk 26:
```text
ok
test_same_leading_version_different_content_is_ambiguous (tests.test_formal_range_store.FormalRangeStoreTests.test_same_leading_version_different_content_is_ambiguous) ...
```

Final compatibility active-process chunk 27:
```text

ElapsedSeconds     CPU   PID
--------------     ---   ---
       1911.40 1870.44 27004
```

Final compatibility output chunk 28:
```text
ok
test_uninitialized_copied_and_redirected_state_store_are_rejected (tests.test_formal_range_store.FormalRangeStoreTests.test_uninitialized_copied_and_redirected_state_store_are_rejected) ...
```

Final compatibility output chunk 29:
```text
ok
test_verified_replay_retains_one_producer (tests.test_formal_range_store.FormalRangeStoreTests.test_verified_replay_retains_one_producer) ...
```

Final compatibility output chunk 30:
```text
ok
test_writer_lock_wait_cannot_extend_expired_lease_or_retry_deadline (tests.test_formal_range_store.FormalRangeStoreTests.test_writer_lock_wait_cannot_extend_expired_lease_or_retry_deadline) ...
```

Final compatibility output chunk 31:
```text
ok
test_backward_interval_is_inclusive_and_stops_at_iso_floor (tests.test_formal_range_source.FormalRangeSourceTests.test_backward_interval_is_inclusive_and_stops_at_iso_floor) ... ok
test_empty_response_does_not_claim_complete_coverage (tests.test_formal_range_source.FormalRangeSourceTests.test_empty_response_does_not_claim_complete_coverage) ...
```

Final compatibility output chunk 32:
```text
ok
test_fetch_and_snapshot_parse_bind_content_and_manifest (tests.test_formal_range_source.FormalRangeSourceTests.test_fetch_and_snapshot_parse_bind_content_and_manifest) ... ok
test_first_calendar_request_needs_no_existing_calendar (tests.test_formal_range_source.FormalRangeSourceTests.test_first_calendar_request_needs_no_existing_calendar) ... ok
test_genuine_request_seal_rejects_every_out_of_contract_bound (tests.test_formal_range_source.FormalRangeSourceTests.test_genuine_request_seal_rejects_every_out_of_contract_bound) ... 
  test_genuine_request_seal_rejects_every_out_of_contract_bound (tests.test_formal_range_source.FormalRangeSourceTests.test_genuine_request_seal_rejects_every_out_of_contract_bound) (field='page_index') ... ERROR
```

Final compatibility output chunk 33:
```text
  test_genuine_request_seal_rejects_every_out_of_contract_bound (tests.test_formal_range_source.FormalRangeSourceTests.test_genuine_request_seal_rejects_every_out_of_contract_bound) (field='as_of_utc') ... ERROR
  test_genuine_request_seal_rejects_every_out_of_contract_bound (tests.test_formal_range_source.FormalRangeSourceTests.test_genuine_request_seal_rejects_every_out_of_contract_bound) (field='start_date') ... ERROR
  test_genuine_request_seal_rejects_every_out_of_contract_bound (tests.test_formal_range_source.FormalRangeSourceTests.test_genuine_request_seal_rejects_every_out_of_contract_bound) (field='end_date') ... ERROR
test_identical_source_blob_can_be_reused_by_a_different_manifest_root (tests.test_formal_range_source.FormalRangeSourceTests.test_identical_source_blob_can_be_reused_by_a_different_manifest_root) ... ok
test_implementation_key_and_method_identities_are_sealed (tests.test_formal_range_source.FormalRangeSourceTests.test_implementation_key_and_method_identities_are_sealed) ... ok
test_import_orders_have_no_registration_hook_or_partial_cycle (tests.test_formal_range_source.FormalRangeSourceTests.test_import_orders_have_no_registration_hook_or_partial_cycle) ... ok
test_instance_parse_shadow_cannot_bypass_registered_fetch_implementation (tests.test_formal_range_source.FormalRangeSourceTests.test_instance_parse_shadow_cannot_bypass_registered_fetch_implementation) ...
```

Final compatibility output chunk 34:
```text
ok
test_instance_parse_shadow_cannot_bypass_registered_replay_implementation (tests.test_formal_range_source.FormalRangeSourceTests.test_instance_parse_shadow_cannot_bypass_registered_replay_implementation) ... ok
test_late_capture_and_late_publication_are_preserved_as_observations (tests.test_formal_range_source.FormalRangeSourceTests.test_late_capture_and_late_publication_are_preserved_as_observations) ...
```

Final compatibility output chunk 35:
```text
ok
test_module_private_mint_cannot_authorize_arbitrary_bounds_or_boolean_page (tests.test_formal_range_source.FormalRangeSourceTests.test_module_private_mint_cannot_authorize_arbitrary_bounds_or_boolean_page) ... ok
test_old_and_new_request_placeholders_cannot_cross (tests.test_formal_range_source.FormalRangeSourceTests.test_old_and_new_request_placeholders_cannot_cross) ... ok
test_page_successor_requires_source_backed_exact_page_identity (tests.test_formal_range_source.FormalRangeSourceTests.test_page_successor_requires_source_backed_exact_page_identity) ... ok
test_parser_cannot_mutate_config_or_request_during_execution (tests.test_formal_range_source.FormalRangeSourceTests.test_parser_cannot_mutate_config_or_request_during_execution) ... ok
test_parser_output_identity_page_and_counts_must_match (tests.test_formal_range_source.FormalRangeSourceTests.test_parser_output_identity_page_and_counts_must_match) ...
```

Final compatibility active-process chunk 36:
```text

ElapsedSeconds     CPU   PID
--------------     ---   ---
       2560.00 2499.59 27004
```

Final compatibility output chunk 37:
```text
ok
test_range_fetch_cannot_be_externally_minted (tests.test_formal_range_source.FormalRangeSourceTests.test_range_fetch_cannot_be_externally_minted) ... ok
test_range_fetch_seal_distinguishes_boolean_from_every_integer_manifest_field (tests.test_formal_range_source.FormalRangeSourceTests.test_range_fetch_seal_distinguishes_boolean_from_every_integer_manifest_field) ...
```

Final compatibility output chunk 38:
```text
ok
test_redirect_challenge_and_blocking_statuses_are_not_evidence (tests.test_formal_range_source.FormalRangeSourceTests.test_redirect_challenge_and_blocking_statuses_are_not_evidence) ... ok
test_request_cannot_be_constructed_copied_or_mutated_into_authority (tests.test_formal_range_source.FormalRangeSourceTests.test_request_cannot_be_constructed_copied_or_mutated_into_authority) ... ERROR
test_request_dates_and_freeze_are_closed (tests.test_formal_range_source.FormalRangeSourceTests.test_request_dates_and_freeze_are_closed) ...
```

Final compatibility output chunk 39:
```text
ok
test_rows_require_visibility_fields_and_forbid_policy_conclusions (tests.test_formal_range_source.FormalRangeSourceTests.test_rows_require_visibility_fields_and_forbid_policy_conclusions) ... ok
test_select_range_accepts_only_matching_genuine_request (tests.test_formal_range_source.FormalRangeSourceTests.test_select_range_accepts_only_matching_genuine_request) ... ok
test_select_range_rejects_changed_source_blob_even_when_entry_is_identical (tests.test_formal_range_source.FormalRangeSourceTests.test_select_range_rejects_changed_source_blob_even_when_entry_is_identical) ...
```

Final compatibility output chunk 40:
```text
ok
test_select_range_rejects_different_config_and_root_identity (tests.test_formal_range_source.FormalRangeSourceTests.test_select_range_rejects_different_config_and_root_identity) ... ok
test_source_initialization_uses_genuine_registry_and_binding_anchors (tests.test_formal_range_source.FormalRangeSourceTests.test_source_initialization_uses_genuine_registry_and_binding_anchors) ... ok
test_source_instance_rejects_other_complete_source_blob_with_same_selected_entry (tests.test_formal_range_source.FormalRangeSourceTests.test_source_instance_rejects_other_complete_source_blob_with_same_selected_entry) ...
```

Final compatibility output chunk 41:
```text
ok
test_source_instance_rejects_other_manifest_root_even_for_shared_source_blob (tests.test_formal_range_source.FormalRangeSourceTests.test_source_instance_rejects_other_manifest_root_even_for_shared_source_blob) ... ok
test_transport_request_uses_only_new_placeholders_and_signed_bounds (tests.test_formal_range_source.FormalRangeSourceTests.test_transport_request_uses_only_new_placeholders_and_signed_bounds) ...
```

Final compatibility output chunk 42:
```text
ok
test_unproven_date_only_effective_time_stays_explicitly_unresolved (tests.test_formal_range_source.FormalRangeSourceTests.test_unproven_date_only_effective_time_stays_explicitly_unresolved) ... ok
test_unregistered_or_self_reported_implementation_is_rejected (tests.test_formal_range_source.FormalRangeSourceTests.test_unregistered_or_self_reported_implementation_is_rejected) ... ok
test_bundle_blocked_audit_input_hash_conflicts_and_receipt_tamper (tests.test_state_store.FormalV6PersistenceTests.test_bundle_blocked_audit_input_hash_conflicts_and_receipt_tamper) ... ok
test_bundle_evidence_cutoff_excludes_source_update_but_allows_late_capture (tests.test_state_store.FormalV6PersistenceTests.test_bundle_evidence_cutoff_excludes_source_update_but_allows_late_capture) ... ok
test_bundle_evidence_rejects_future_source_update (tests.test_state_store.FormalV6PersistenceTests.test_bundle_evidence_rejects_future_source_update) ... ok
test_bundle_live_receipt_and_append_only_metadata (tests.test_state_store.FormalV6PersistenceTests.test_bundle_live_receipt_and_append_only_metadata) ... ok
test_bundle_missing_evidence_and_missing_live_store_fail_closed (tests.test_state_store.FormalV6PersistenceTests.test_bundle_missing_evidence_and_missing_live_store_fail_closed) ... ok
test_bundle_rejects_feature_child_bound_to_wrong_source_role_hash (tests.test_state_store.FormalV6PersistenceTests.test_bundle_rejects_feature_child_bound_to_wrong_source_role_hash) ... ok
test_bundle_rejects_signed_slot_unit_formula_and_foreign_evidence (tests.test_state_store.FormalV6PersistenceTests.test_bundle_rejects_signed_slot_unit_formula_and_foreign_evidence) ... ok
test_fact_receipt_and_task_corruption_reject_replay_and_listing (tests.test_state_store.FormalV6PersistenceTests.test_fact_receipt_and_task_corruption_reject_replay_and_listing) ... ok
test_formal_fact_publication_lineage_and_legacy_ids_are_rejected (tests.test_state_store.FormalV6PersistenceTests.test_formal_fact_publication_lineage_and_legacy_ids_are_rejected) ... ok
test_formal_fact_reads_revalidate_raw_files_rows_and_seals (tests.test_state_store.FormalV6PersistenceTests.test_formal_fact_reads_revalidate_raw_files_rows_and_seals) ... ok
test_formal_facts_lineage_mismatch_rolls_back_whole_batch (tests.test_state_store.FormalV6PersistenceTests.test_formal_facts_lineage_mismatch_rolls_back_whole_batch) ... ok
test_formal_facts_replay_preserves_first_created_time_and_lists_detached (tests.test_state_store.FormalV6PersistenceTests.test_formal_facts_replay_preserves_first_created_time_and_lists_detached) ... ok
test_quarter_cumulative_arithmetic_and_historical_lineage_coexist (tests.test_state_store.FormalV6PersistenceTests.test_quarter_cumulative_arithmetic_and_historical_lineage_coexist) ... ok
test_quarter_rederivation_rejects_canonical_wrong_arithmetic (tests.test_state_store.FormalV6PersistenceTests.test_quarter_rederivation_rejects_canonical_wrong_arithmetic) ... ok
test_receipt_getter_rejects_non_source_producer (tests.test_state_store.FormalV6PersistenceTests.test_receipt_getter_rejects_non_source_producer) ... ok
test_receipt_insert_and_replay_resample_lease_expiry (tests.test_state_store.FormalV6PersistenceTests.test_receipt_insert_and_replay_resample_lease_expiry) ... ok
test_receipt_insert_tail_rolls_back_when_graph_validation_crosses_expiry (tests.test_state_store.FormalV6PersistenceTests.test_receipt_insert_tail_rolls_back_when_graph_validation_crosses_expiry) ... ok
test_registry_all_roles_reject_raw_hash_role_signature_binding_tamper (tests.test_state_store.FormalV6PersistenceTests.test_registry_all_roles_reject_raw_hash_role_signature_binding_tamper) ... ok
test_registry_persistence_verifies_all_children_and_survives_restart (tests.test_state_store.FormalV6PersistenceTests.test_registry_persistence_verifies_all_children_and_survives_restart) ... ok
test_registry_root_forgery_column_tamper_and_binding_reuse_conflict (tests.test_state_store.FormalV6PersistenceTests.test_registry_root_forgery_column_tamper_and_binding_reuse_conflict) ... ok
test_source_circuit_invalid_shapes_tamper_and_task_isolation (tests.test_state_store.FormalV6PersistenceTests.test_source_circuit_invalid_shapes_tamper_and_task_isolation) ... ok
test_source_circuit_replay_is_noop_and_open_closed_rules (tests.test_state_store.FormalV6PersistenceTests.test_source_circuit_replay_is_noop_and_open_closed_rules) ... ok
test_task_listing_empty_filters_and_corrupt_missing_dependency (tests.test_state_store.FormalV6PersistenceTests.test_task_listing_empty_filters_and_corrupt_missing_dependency) ... ok
test_task_listing_validates_filters_detaches_and_orders (tests.test_state_store.FormalV6PersistenceTests.test_task_listing_validates_filters_detaches_and_orders) ... ok
test_v6_migration_all_continuous_entrances_and_reopen (tests.test_state_store.FormalV6PersistenceTests.test_v6_migration_all_continuous_entrances_and_reopen) ... ok
test_v6_migration_rejects_partial_tampered_and_premature_objects (tests.test_state_store.FormalV6PersistenceTests.test_v6_migration_rejects_partial_tampered_and_premature_objects) ... ok
test_all_continuous_entrances_and_reopen (tests.test_state_store.FormalV7RangePersistenceTests.test_all_continuous_entrances_and_reopen) ... ok
test_partial_and_premature_v7_objects_preserve_old_rows (tests.test_state_store.FormalV7RangePersistenceTests.test_partial_and_premature_v7_objects_preserve_old_rows) ... ok
test_v7_name_collision_rolls_back_preserving_legacy_rows (tests.test_state_store.FormalV7RangePersistenceTests.test_v7_name_collision_rolls_back_preserving_legacy_rows) ... ok
test_balance_equation_accepts_exact_tolerance_and_missing_triplet (tests.test_state_store.StateStoreTestCase.test_balance_equation_accepts_exact_tolerance_and_missing_triplet) ... ok
test_balance_equation_is_reauthenticated_before_idempotent_success (tests.test_state_store.StateStoreTestCase.test_balance_equation_is_reauthenticated_before_idempotent_success) ... ok
test_balance_equation_semantics_reject_forged_ready_partial_and_blocked (tests.test_state_store.StateStoreTestCase.test_balance_equation_semantics_reject_forged_ready_partial_and_blocked) ... ok
test_complete_formal_source_task_rejects_invalid_receipt_graph_without_mutation (tests.test_state_store.StateStoreTestCase.test_complete_formal_source_task_rejects_invalid_receipt_graph_without_mutation) ... ok
test_complete_formal_source_task_requires_one_valid_exact_receipt (tests.test_state_store.StateStoreTestCase.test_complete_formal_source_task_requires_one_valid_exact_receipt) ... ok
test_complete_formal_task_canonicalizes_result_and_clears_transition_fields (tests.test_state_store.StateStoreTestCase.test_complete_formal_task_canonicalizes_result_and_clears_transition_fields) ... ok
test_complete_formal_task_fails_closed_for_finalizer_and_rolls_back_update_failure (tests.test_state_store.StateStoreTestCase.test_complete_formal_task_fails_closed_for_finalizer_and_rolls_back_update_failure) ... ok
test_complete_formal_task_resamples_time_after_receipt_validation (tests.test_state_store.StateStoreTestCase.test_complete_formal_task_resamples_time_after_receipt_validation) ... ok
test_complete_formal_task_samples_time_after_result_serialization (tests.test_state_store.StateStoreTestCase.test_complete_formal_task_samples_time_after_result_serialization) ... ok
test_complete_formal_task_validates_result_and_fences_final_mutation (tests.test_state_store.StateStoreTestCase.test_complete_formal_task_validates_result_and_fences_final_mutation) ... ok
test_complete_resamples_after_result_serialization (tests.test_state_store.StateStoreTestCase.test_complete_resamples_after_result_serialization) ... ok
test_completed_job_remains_completed_after_reopen (tests.test_state_store.StateStoreTestCase.test_completed_job_remains_completed_after_reopen) ... ok
test_concurrent_workers_claim_only_one_job_after_barrier (tests.test_state_store.StateStoreTestCase.test_concurrent_workers_claim_only_one_job_after_barrier) ... ok
test_conflicting_followup_idempotency_key_fails_closed_and_rolls_back (tests.test_state_store.StateStoreTestCase.test_conflicting_followup_idempotency_key_fails_closed_and_rolls_back) ... ok
test_ddl_normalization_preserves_escaped_single_quoted_literals (tests.test_state_store.StateStoreTestCase.test_ddl_normalization_preserves_escaped_single_quoted_literals) ... ok
test_duplicate_enqueue_returns_original_job_without_second_row (tests.test_state_store.StateStoreTestCase.test_duplicate_enqueue_returns_original_job_without_second_row) ...
```

Final compatibility output chunk 43:
```text
ok
test_equal_offset_time_blocks_but_later_absolute_time_finalizes (tests.test_state_store.StateStoreTestCase.test_equal_offset_time_blocks_but_later_absolute_time_finalizes) ... ok
test_evidence_authority_rejects_financial_formula_aliases_in_v_and_t (tests.test_state_store.StateStoreTestCase.test_evidence_authority_rejects_financial_formula_aliases_in_v_and_t) ... ok
test_expired_and_completed_jobs_cannot_renew (tests.test_state_store.StateStoreTestCase.test_expired_and_completed_jobs_cannot_renew) ... ok
test_expired_formal_owner_is_fenced_after_distinct_worker_takeover (tests.test_state_store.StateStoreTestCase.test_expired_formal_owner_is_fenced_after_distinct_worker_takeover) ... ok
test_expired_lease_is_recovered_with_audit_error (tests.test_state_store.StateStoreTestCase.test_expired_lease_is_recovered_with_audit_error) ... ok
test_expired_worker_cannot_complete_or_fail_owned_job (tests.test_state_store.StateStoreTestCase.test_expired_worker_cannot_complete_or_fail_owned_job) ... ok
test_fail_formal_task_retries_at_boundary_and_terminal_failure_is_permanent (tests.test_state_store.StateStoreTestCase.test_fail_formal_task_retries_at_boundary_and_terminal_failure_is_permanent) ... ok
test_fail_formal_task_samples_time_after_error_serialization (tests.test_state_store.StateStoreTestCase.test_fail_formal_task_samples_time_after_error_serialization) ... ok
test_fail_formal_task_validates_inputs_and_fences_owner_at_final_update (tests.test_state_store.StateStoreTestCase.test_fail_formal_task_validates_inputs_and_fences_owner_at_final_update) ... ok
test_fail_resamples_after_error_serialization (tests.test_state_store.StateStoreTestCase.test_fail_resamples_after_error_serialization) ... ok
test_final_run_cannot_be_modified_and_new_input_creates_new_run (tests.test_state_store.StateStoreTestCase.test_final_run_cannot_be_modified_and_new_input_creates_new_run) ... ok
test_final_transitions_resample_after_followup_preparation (tests.test_state_store.StateStoreTestCase.test_final_transitions_resample_after_followup_preparation) ... ok
test_final_transitions_sample_time_after_writer_lock_wait (tests.test_state_store.StateStoreTestCase.test_final_transitions_sample_time_after_writer_lock_wait) ... ok
test_finalization_persists_utc_gate_and_evidence (tests.test_state_store.StateStoreTestCase.test_finalization_persists_utc_gate_and_evidence) ... ok
test_finalization_promotes_only_ready_items_and_is_idempotent (tests.test_state_store.StateStoreTestCase.test_finalization_promotes_only_ready_items_and_is_idempotent) ... ok
test_finalize_blocks_at_cutoff_including_timezone_boundary (tests.test_state_store.StateStoreTestCase.test_finalize_blocks_at_cutoff_including_timezone_boundary) ... ok
test_finalize_requires_market_and_quality_gates (tests.test_state_store.StateStoreTestCase.test_finalize_requires_market_and_quality_gates) ... ok
test_find_quality_issue_ids_is_exact_canonical_and_stably_sorted (tests.test_state_store.StateStoreTestCase.test_find_quality_issue_ids_is_exact_canonical_and_stably_sorted) ... ok
test_first_insert_mirror_validation_rolls_back_materialization_drift (tests.test_state_store.StateStoreTestCase.test_first_insert_mirror_validation_rolls_back_materialization_drift) ... ok
test_first_persistence_rejects_financial_formula_copy_in_t (tests.test_state_store.StateStoreTestCase.test_first_persistence_rejects_financial_formula_copy_in_t) ... ok
test_formal_bootstrap_new_generation_shares_binary_but_keeps_distinct_lineage (tests.test_state_store.StateStoreTestCase.test_formal_bootstrap_new_generation_shares_binary_but_keeps_distinct_lineage) ... ok
test_formal_bootstrap_rejections_leave_database_empty (tests.test_state_store.StateStoreTestCase.test_formal_bootstrap_rejections_leave_database_empty) ... ok
test_formal_lease_blocks_until_every_prerequisite_is_verified (tests.test_state_store.StateStoreTestCase.test_formal_lease_blocks_until_every_prerequisite_is_verified) ... ok
test_formal_lease_cas_rechecks_dependency_after_candidate_selection (tests.test_state_store.StateStoreTestCase.test_formal_lease_cas_rechecks_dependency_after_candidate_selection) ... ok
test_formal_lease_orders_all_ready_states_and_honors_exact_boundaries (tests.test_state_store.StateStoreTestCase.test_formal_lease_orders_all_ready_states_and_honors_exact_boundaries) ... ok
test_formal_lease_rejects_invalid_inputs_and_rolls_back_tampered_payload (tests.test_state_store.StateStoreTestCase.test_formal_lease_rejects_invalid_inputs_and_rolls_back_tampered_payload) ... ok
test_formal_lease_samples_implicit_time_after_writer_lock (tests.test_state_store.StateStoreTestCase.test_formal_lease_samples_implicit_time_after_writer_lock) ... ok
test_formal_receipt_getter_reads_one_consistent_database_snapshot (tests.test_state_store.StateStoreTestCase.test_formal_receipt_getter_reads_one_consistent_database_snapshot) ... ok
test_formal_receipt_getter_rejects_deleted_receipt_orphan (tests.test_state_store.StateStoreTestCase.test_formal_receipt_getter_rejects_deleted_receipt_orphan) ... ok
test_formal_receipt_getter_rejects_every_cross_lineage_mismatch (tests.test_state_store.StateStoreTestCase.test_formal_receipt_getter_rejects_every_cross_lineage_mismatch) ... ok
test_formal_receipt_getter_rejects_extra_producer_snapshot (tests.test_state_store.StateStoreTestCase.test_formal_receipt_getter_rejects_extra_producer_snapshot) ... ok
test_formal_receipt_getter_revalidates_task_snapshot_lineage_and_survives_failure (tests.test_state_store.StateStoreTestCase.test_formal_receipt_getter_revalidates_task_snapshot_lineage_and_survives_failure) ... ok
test_formal_snapshot_getter_rejects_malformed_ids_and_stored_tamper (tests.test_state_store.StateStoreTestCase.test_formal_snapshot_getter_rejects_malformed_ids_and_stored_tamper) ... ok
test_formal_snapshot_lookup_never_reads_legacy_source_snapshot (tests.test_state_store.StateStoreTestCase.test_formal_snapshot_lookup_never_reads_legacy_source_snapshot) ... ok
test_formal_snapshot_manifest_and_lineage_conflicts_never_repair_rows (tests.test_state_store.StateStoreTestCase.test_formal_snapshot_manifest_and_lineage_conflicts_never_repair_rows) ... ok
test_formal_snapshot_store_injection_is_optional_but_formal_apis_fail_closed (tests.test_state_store.StateStoreTestCase.test_formal_snapshot_store_injection_is_optional_but_formal_apis_fail_closed) ... ok
test_formal_task_contract_exact_replay_and_initial_public_row (tests.test_state_store.StateStoreTestCase.test_formal_task_contract_exact_replay_and_initial_public_row) ... ok
test_formal_task_idempotency_conflicts_roll_back_without_mutation (tests.test_state_store.StateStoreTestCase.test_formal_task_idempotency_conflicts_roll_back_without_mutation) ... ok
test_formal_task_operations_leave_legacy_queue_contract_untouched (tests.test_state_store.StateStoreTestCase.test_formal_task_operations_leave_legacy_queue_contract_untouched) ... ok
test_formal_task_rejects_missing_duplicate_self_and_cyclic_prerequisites (tests.test_state_store.StateStoreTestCase.test_formal_task_rejects_missing_duplicate_self_and_cyclic_prerequisites) ... ok
test_formal_task_replay_ignores_prerequisite_order_and_getter_sorts (tests.test_state_store.StateStoreTestCase.test_formal_task_replay_ignores_prerequisite_order_and_getter_sorts) ... ok
test_formal_task_snapshots_caller_payload_and_rejects_invalid_inputs (tests.test_state_store.StateStoreTestCase.test_formal_task_snapshots_caller_payload_and_rejects_invalid_inputs) ... ok
test_formal_universe_finalizer_and_getter_reject_status_timestamp_tamper_without_mutation (tests.test_state_store.StateStoreTestCase.test_formal_universe_finalizer_and_getter_reject_status_timestamp_tamper_without_mutation) ... ok
test_formal_universe_finalizer_completion_and_getter_require_exact_bound_proof (tests.test_state_store.StateStoreTestCase.test_formal_universe_finalizer_completion_and_getter_require_exact_bound_proof) ... ok
test_formal_universe_finalizer_getter_rejects_impossible_verified_state (tests.test_state_store.StateStoreTestCase.test_formal_universe_finalizer_getter_rejects_impossible_verified_state) ... ok
test_formal_universe_finalizer_rejects_payload_dependency_and_graph_tampering (tests.test_state_store.StateStoreTestCase.test_formal_universe_finalizer_rejects_payload_dependency_and_graph_tampering) ... ok
test_formal_universe_finalizer_rejects_result_tampering_without_mutation (tests.test_state_store.StateStoreTestCase.test_formal_universe_finalizer_rejects_result_tampering_without_mutation) ... ok
test_formal_universe_getter_and_replay_reject_corrupt_verified_source_task_state (tests.test_state_store.StateStoreTestCase.test_formal_universe_getter_and_replay_reject_corrupt_verified_source_task_state) ... ok
test_formal_universe_getters_and_replay_fail_closed_for_corrupt_existing_graph (tests.test_state_store.StateStoreTestCase.test_formal_universe_getters_and_replay_fail_closed_for_corrupt_existing_graph) ... ok
test_formal_universe_initial_status_recomputes_evidence_hash_on_read_and_replay (tests.test_state_store.StateStoreTestCase.test_formal_universe_initial_status_recomputes_evidence_hash_on_read_and_replay) ... ok
test_formal_universe_persisted_padded_status_tokens_fail_closed_for_list_finalizer_and_getter (tests.test_state_store.StateStoreTestCase.test_formal_universe_persisted_padded_status_tokens_fail_closed_for_list_finalizer_and_getter) ... ok
test_formal_universe_persistence_does_not_read_or_modify_legacy_snapshots (tests.test_state_store.StateStoreTestCase.test_formal_universe_persistence_does_not_read_or_modify_legacy_snapshots) ... ok
test_formal_universe_replace_tail_rejects_triggered_padded_tokens_without_mutation (tests.test_state_store.StateStoreTestCase.test_formal_universe_replace_tail_rejects_triggered_padded_tokens_without_mutation) ... ok
test_formal_universe_snapshot_persists_complete_canonical_graph_and_initial_statuses (tests.test_state_store.StateStoreTestCase.test_formal_universe_snapshot_persists_complete_canonical_graph_and_initial_statuses) ... ok
test_formal_universe_snapshot_rejects_impossible_verified_source_task_state (tests.test_state_store.StateStoreTestCase.test_formal_universe_snapshot_rejects_impossible_verified_source_task_state) ... ok
test_formal_universe_snapshot_rejects_missing_duplicate_cross_exchange_and_untrusted_source_graphs (tests.test_state_store.StateStoreTestCase.test_formal_universe_snapshot_rejects_missing_duplicate_cross_exchange_and_untrusted_source_graphs) ... ok
test_formal_universe_snapshot_replay_is_exact_and_never_resets_statuses (tests.test_state_store.StateStoreTestCase.test_formal_universe_snapshot_replay_is_exact_and_never_resets_statuses) ... ok
test_formal_universe_snapshot_requires_exact_typed_recomputed_input (tests.test_state_store.StateStoreTestCase.test_formal_universe_snapshot_requires_exact_typed_recomputed_input) ... ok
test_formal_universe_snapshot_revalidates_task_receipt_and_result_lineage (tests.test_state_store.StateStoreTestCase.test_formal_universe_snapshot_revalidates_task_receipt_and_result_lineage) ... ok
test_formal_universe_snapshot_rolls_back_late_child_failure (tests.test_state_store.StateStoreTestCase.test_formal_universe_snapshot_rolls_back_late_child_failure) ... ok
test_formal_universe_status_reader_rejects_mixed_and_precreation_timestamps_without_mutation (tests.test_state_store.StateStoreTestCase.test_formal_universe_status_reader_rejects_mixed_and_precreation_timestamps_without_mutation) ... ok
test_formal_universe_status_replacement_rejects_blank_reason_or_veto_without_mutation (tests.test_state_store.StateStoreTestCase.test_formal_universe_status_replacement_rejects_blank_reason_or_veto_without_mutation) ...
```

Final compatibility output chunk 44:
```text
ok
test_formal_universe_status_replacement_rejects_invalid_or_incomplete_input_without_mutation (tests.test_state_store.StateStoreTestCase.test_formal_universe_status_replacement_rejects_invalid_or_incomplete_input_without_mutation) ... ok
test_formal_universe_status_replacement_rejects_padded_reason_or_veto_without_mutation (tests.test_state_store.StateStoreTestCase.test_formal_universe_status_replacement_rejects_padded_reason_or_veto_without_mutation) ... ok
test_formal_universe_status_replacement_rolls_back_late_failure_and_revalidates_graph (tests.test_state_store.StateStoreTestCase.test_formal_universe_status_replacement_rolls_back_late_failure_and_revalidates_graph) ... ok
test_formal_universe_statuses_replace_complete_typed_ledger_and_list_canonically (tests.test_state_store.StateStoreTestCase.test_formal_universe_statuses_replace_complete_typed_ledger_and_list_canonically) ... ok
test_get_formal_task_rejects_payload_hash_and_noncanonical_json_tampering (tests.test_state_store.StateStoreTestCase.test_get_formal_task_rejects_payload_hash_and_noncanonical_json_tampering) ... ok
test_get_job_returns_public_status_result_error_and_retry_fields (tests.test_state_store.StateStoreTestCase.test_get_job_returns_public_status_result_error_and_retry_fields) ... ok
test_idempotent_put_reauthenticates_derived_numeric_projection (tests.test_state_store.StateStoreTestCase.test_idempotent_put_reauthenticates_derived_numeric_projection) ... ok
test_idempotent_put_rejects_exact_child_mirror_corruption_without_repair (tests.test_state_store.StateStoreTestCase.test_idempotent_put_rejects_exact_child_mirror_corruption_without_repair) ... ok
test_illegal_state_is_rejected (tests.test_state_store.StateStoreTestCase.test_illegal_state_is_rejected) ... ok
test_initialize_applies_v3_through_v5_when_migration_ledger_contains_only_v2 (tests.test_state_store.StateStoreTestCase.test_initialize_applies_v3_through_v5_when_migration_ledger_contains_only_v2) ... ok
test_initialize_migrates_complete_v3_database_to_v5_preserving_issues (tests.test_state_store.StateStoreTestCase.test_initialize_migrates_complete_v3_database_to_v5_preserving_issues) ... ok
test_initialize_migrates_literal_v2_database_to_v5_without_changing_existing_rows (tests.test_state_store.StateStoreTestCase.test_initialize_migrates_literal_v2_database_to_v5_without_changing_existing_rows) ... ok
test_initialize_migrates_literal_v4_database_to_v5_without_changing_legacy_rows (tests.test_state_store.StateStoreTestCase.test_initialize_migrates_literal_v4_database_to_v5_without_changing_legacy_rows) ... ok
test_initialize_rejects_migration_ledgers_outside_contiguous_v2_to_v5 (tests.test_state_store.StateStoreTestCase.test_initialize_rejects_migration_ledgers_outside_contiguous_v2_to_v5) ... ok
test_initialize_rejects_partial_v2_database_without_creating_ledger (tests.test_state_store.StateStoreTestCase.test_initialize_rejects_partial_v2_database_without_creating_ledger) ... ok
test_initialize_rejects_v2_check_with_changed_string_literal_case (tests.test_state_store.StateStoreTestCase.test_initialize_rejects_v2_check_with_changed_string_literal_case) ... ok
test_initialize_rolls_back_v3_when_approved_index_name_is_preoccupied (tests.test_state_store.StateStoreTestCase.test_initialize_rolls_back_v3_when_approved_index_name_is_preoccupied) ... ok
test_initialize_twice_keeps_one_complete_v5_schema_and_ledger (tests.test_state_store.StateStoreTestCase.test_initialize_twice_keeps_one_complete_v5_schema_and_ledger) ... ok
test_insert_financial_facts_is_idempotent_and_preserves_revision (tests.test_state_store.StateStoreTestCase.test_insert_financial_facts_is_idempotent_and_preserves_revision) ... ok
test_job_spec_is_frozen (tests.test_state_store.StateStoreTestCase.test_job_spec_is_frozen) ... ok
test_job_spec_payload_is_a_stable_construction_snapshot (tests.test_state_store.StateStoreTestCase.test_job_spec_payload_is_a_stable_construction_snapshot) ... ok
test_latest_feature_set_breaks_as_of_ties_by_created_at_then_id (tests.test_state_store.StateStoreTestCase.test_latest_feature_set_breaks_as_of_ties_by_created_at_then_id) ... ok
test_latest_feature_set_filters_exactly_orders_and_parses_json (tests.test_state_store.StateStoreTestCase.test_latest_feature_set_filters_exactly_orders_and_parses_json) ... ok
test_leasing_claims_one_pending_job_exclusively (tests.test_state_store.StateStoreTestCase.test_leasing_claims_one_pending_job_exclusively) ... ok
test_legacy_completion_and_failure_without_worker_remain_compatible (tests.test_state_store.StateStoreTestCase.test_legacy_completion_and_failure_without_worker_remain_compatible) ... ok
test_legacy_success_clears_recovered_failure_fields (tests.test_state_store.StateStoreTestCase.test_legacy_success_clears_recovered_failure_fields) ... ok
test_list_financial_facts_applies_exact_snapshot_and_effective_filters (tests.test_state_store.StateStoreTestCase.test_list_financial_facts_applies_exact_snapshot_and_effective_filters) ... ok
test_list_financial_facts_preserves_known_v1_and_v2_history (tests.test_state_store.StateStoreTestCase.test_list_financial_facts_preserves_known_v1_and_v2_history) ... ok
test_list_jobs_filters_by_parameter_and_orders_created_at_then_id (tests.test_state_store.StateStoreTestCase.test_list_jobs_filters_by_parameter_and_orders_created_at_then_id) ... ok
test_malformed_statement_reconciliation_commits_verified_recovery_once (tests.test_state_store.StateStoreTestCase.test_malformed_statement_reconciliation_commits_verified_recovery_once) ... ok
test_malformed_statement_reconciliation_rejects_historical_mapping_facts (tests.test_state_store.StateStoreTestCase.test_malformed_statement_reconciliation_rejects_historical_mapping_facts) ... ok
test_malformed_statement_reconciliation_rejects_identity_mismatches_without_writes (tests.test_state_store.StateStoreTestCase.test_malformed_statement_reconciliation_rejects_identity_mismatches_without_writes) ... ok
test_malformed_statement_reconciliation_rejects_nonexact_result_without_writes (tests.test_state_store.StateStoreTestCase.test_malformed_statement_reconciliation_rejects_nonexact_result_without_writes) ... ok
test_malformed_statement_reconciliation_rejects_same_id_fact_conflict (tests.test_state_store.StateStoreTestCase.test_malformed_statement_reconciliation_rejects_same_id_fact_conflict) ... ok
test_malformed_statement_reconciliation_rejects_unbound_facts_and_followup_without_writes (tests.test_state_store.StateStoreTestCase.test_malformed_statement_reconciliation_rejects_unbound_facts_and_followup_without_writes) ... ok
test_malformed_statement_reconciliation_rejects_unbound_feature_followup (tests.test_state_store.StateStoreTestCase.test_malformed_statement_reconciliation_rejects_unbound_feature_followup) ... ok
test_malformed_statement_reconciliation_rolls_back_cas_trigger_side_effect (tests.test_state_store.StateStoreTestCase.test_malformed_statement_reconciliation_rolls_back_cas_trigger_side_effect) ... ok
test_malformed_statement_reconciliation_rolls_back_followup_conflict (tests.test_state_store.StateStoreTestCase.test_malformed_statement_reconciliation_rolls_back_followup_conflict) ... ok
test_malformed_statement_reconciliation_rolls_back_trigger_failure (tests.test_state_store.StateStoreTestCase.test_malformed_statement_reconciliation_rolls_back_trigger_failure) ... ok
test_nonfinite_followup_payload_rolls_back_parent_transition (tests.test_state_store.StateStoreTestCase.test_nonfinite_followup_payload_rolls_back_parent_transition) ... ok
test_owned_job_transaction_fences_wrong_expired_and_valid_owners (tests.test_state_store.StateStoreTestCase.test_owned_job_transaction_fences_wrong_expired_and_valid_owners) ... ok
test_owned_kinds_reject_ownerless_legacy_transitions_after_release (tests.test_state_store.StateStoreTestCase.test_owned_kinds_reject_ownerless_legacy_transitions_after_release) ... ok
test_owned_quality_issue_and_snapshot_binding_commit_together (tests.test_state_store.StateStoreTestCase.test_owned_quality_issue_and_snapshot_binding_commit_together) ... ok
test_owned_quality_issue_invalid_snapshot_rolls_back_issue (tests.test_state_store.StateStoreTestCase.test_owned_quality_issue_invalid_snapshot_rolls_back_issue) ... ok
test_progress_snapshot_has_counts_recent_run_update_and_no_payloads (tests.test_state_store.StateStoreTestCase.test_progress_snapshot_has_counts_recent_run_update_and_no_payloads) ... ok
test_progress_updated_at_includes_finished_run_artifact_and_quality_issue (tests.test_state_store.StateStoreTestCase.test_progress_updated_at_includes_finished_run_artifact_and_quality_issue) ... ok
test_provisional_run_cannot_directly_write_final_score_item (tests.test_state_store.StateStoreTestCase.test_provisional_run_cannot_directly_write_final_score_item) ... ok
test_put_feature_bundle_authenticates_derived_values_and_operands (tests.test_state_store.StateStoreTestCase.test_put_feature_bundle_authenticates_derived_values_and_operands) ... ok
test_put_feature_bundle_is_atomic_and_rejects_nondeterministic_conflict (tests.test_state_store.StateStoreTestCase.test_put_feature_bundle_is_atomic_and_rejects_nondeterministic_conflict) ... ok
test_put_feature_bundle_rejects_future_fact_on_idempotent_success_path (tests.test_state_store.StateStoreTestCase.test_put_feature_bundle_rejects_future_fact_on_idempotent_success_path) ... ok
test_put_feature_bundle_rejects_hash_mismatch_and_unsafe_paths (tests.test_state_store.StateStoreTestCase.test_put_feature_bundle_rejects_hash_mismatch_and_unsafe_paths) ... ok
test_put_feature_bundle_rejects_missing_or_mismatched_evidence_rows (tests.test_state_store.StateStoreTestCase.test_put_feature_bundle_rejects_missing_or_mismatched_evidence_rows) ... ok
test_put_feature_bundle_rejects_raw_observed_fact_mismatches (tests.test_state_store.StateStoreTestCase.test_put_feature_bundle_rejects_raw_observed_fact_mismatches) ... ok
test_put_feature_bundle_rejects_ready_bundle_when_evidence_database_is_empty (tests.test_state_store.StateStoreTestCase.test_put_feature_bundle_rejects_ready_bundle_when_evidence_database_is_empty) ... ok
test_put_feature_bundle_revalidates_evidence_before_idempotent_success (tests.test_state_store.StateStoreTestCase.test_put_feature_bundle_revalidates_evidence_before_idempotent_success) ... ok
test_put_feature_bundle_rolls_back_header_and_values_when_one_value_aborts (tests.test_state_store.StateStoreTestCase.test_put_feature_bundle_rolls_back_header_and_values_when_one_value_aborts) ... ok
test_put_formal_bootstrap_snapshot_returns_revalidated_ref_without_receipt (tests.test_state_store.StateStoreTestCase.test_put_formal_bootstrap_snapshot_returns_revalidated_ref_without_receipt) ... ok
test_put_formal_snapshot_for_leased_task_accepts_only_source_fetch_kinds (tests.test_state_store.StateStoreTestCase.test_put_formal_snapshot_for_leased_task_accepts_only_source_fetch_kinds) ... ok
test_put_formal_snapshot_for_leased_task_is_atomic_replayable_and_durable_after_failure (tests.test_state_store.StateStoreTestCase.test_put_formal_snapshot_for_leased_task_is_atomic_replayable_and_durable_after_failure) ... ok
test_put_formal_snapshot_for_leased_task_rejects_fencing_and_evidence_mismatches_without_rows (tests.test_state_store.StateStoreTestCase.test_put_formal_snapshot_for_leased_task_rejects_fencing_and_evidence_mismatches_without_rows) ... ok
test_put_formal_snapshot_for_leased_task_rejects_replacement_and_cross_task_attachment (tests.test_state_store.StateStoreTestCase.test_put_formal_snapshot_for_leased_task_rejects_replacement_and_cross_task_attachment) ... ok
test_put_formal_snapshot_for_leased_task_rolls_back_snapshot_when_receipt_insert_fails (tests.test_state_store.StateStoreTestCase.test_put_formal_snapshot_for_leased_task_rolls_back_snapshot_when_receipt_insert_fails) ... ok
test_reconciliation_allows_short_cross_midnight_snapshot_within_job_lifetime (tests.test_state_store.StateStoreTestCase.test_reconciliation_allows_short_cross_midnight_snapshot_within_job_lifetime) ... ok
test_reconciliation_rejects_ambiguous_unbound_legacy_issue_or_job (tests.test_state_store.StateStoreTestCase.test_reconciliation_rejects_ambiguous_unbound_legacy_issue_or_job) ... ok
test_reconciliation_rejects_cross_midnight_evidence_out_of_order_without_writes (tests.test_state_store.StateStoreTestCase.test_reconciliation_rejects_cross_midnight_evidence_out_of_order_without_writes) ... ok
test_reconciliation_rejects_cross_midnight_job_started_too_early_without_writes (tests.test_state_store.StateStoreTestCase.test_reconciliation_rejects_cross_midnight_job_started_too_early_without_writes) ... ok
test_reconciliation_rejects_cross_midnight_snapshot_outside_grace_without_writes (tests.test_state_store.StateStoreTestCase.test_reconciliation_rejects_cross_midnight_snapshot_outside_grace_without_writes) ... ok
test_reconciliation_rejects_legacy_issue_outside_current_job_lifetime (tests.test_state_store.StateStoreTestCase.test_reconciliation_rejects_legacy_issue_outside_current_job_lifetime) ... ok
test_reconciliation_rejects_legacy_issue_with_conflicting_bound_provenance (tests.test_state_store.StateStoreTestCase.test_reconciliation_rejects_legacy_issue_with_conflicting_bound_provenance) ... ok
test_reconciliation_rejects_missing_or_mismatched_calendar_snapshot (tests.test_state_store.StateStoreTestCase.test_reconciliation_rejects_missing_or_mismatched_calendar_snapshot) ... ok
test_reconciliation_rejects_primary_wrong_refresh_or_future_as_of (tests.test_state_store.StateStoreTestCase.test_reconciliation_rejects_primary_wrong_refresh_or_future_as_of) ... ok
test_reconciliation_rejects_unbound_or_mismatched_sibling_snapshot (tests.test_state_store.StateStoreTestCase.test_reconciliation_rejects_unbound_or_mismatched_sibling_snapshot) ... ok
test_reconciliation_requires_exact_issue_binding_and_fact_row_hash (tests.test_state_store.StateStoreTestCase.test_reconciliation_requires_exact_issue_binding_and_fact_row_hash) ... ok
test_reconciliation_uniquely_binds_legacy_issue (tests.test_state_store.StateStoreTestCase.test_reconciliation_uniquely_binds_legacy_issue) ... ok
test_record_quality_issue_rejects_nonfinite_details_without_rows (tests.test_state_store.StateStoreTestCase.test_record_quality_issue_rejects_nonfinite_details_without_rows) ... ok
test_record_quality_issue_stores_canonical_details_json (tests.test_state_store.StateStoreTestCase.test_record_quality_issue_stores_canonical_details_json) ... ok
test_renew_formal_lease_fences_wrong_owner_and_exact_expiry_without_mutation (tests.test_state_store.StateStoreTestCase.test_renew_formal_lease_fences_wrong_owner_and_exact_expiry_without_mutation) ... ok
test_renew_formal_lease_uses_current_time_and_preserves_task_content (tests.test_state_store.StateStoreTestCase.test_renew_formal_lease_uses_current_time_and_preserves_task_content) ... ok
test_renew_job_lease_rejects_nonpositive_duration (tests.test_state_store.StateStoreTestCase.test_renew_job_lease_rejects_nonpositive_duration) ... ok
test_renew_job_lease_requires_current_unexpired_owner (tests.test_state_store.StateStoreTestCase.test_renew_job_lease_requires_current_unexpired_owner) ... ok
test_renew_samples_default_time_after_writer_lock_wait (tests.test_state_store.StateStoreTestCase.test_renew_samples_default_time_after_writer_lock_wait) ... ok
test_repeated_identical_followups_are_idempotent_and_canonical (tests.test_state_store.StateStoreTestCase.test_repeated_identical_followups_are_idempotent_and_canonical) ... ok
test_resolve_formal_task_dependencies_cascades_terminal_and_superseded (tests.test_state_store.StateStoreTestCase.test_resolve_formal_task_dependencies_cascades_terminal_and_superseded) ... ok
test_resolve_formal_task_dependencies_does_not_rewrite_leased_child (tests.test_state_store.StateStoreTestCase.test_resolve_formal_task_dependencies_does_not_rewrite_leased_child) ... ok
test_resolve_formal_task_dependencies_sorts_blockers_and_clears_retry_state (tests.test_state_store.StateStoreTestCase.test_resolve_formal_task_dependencies_sorts_blockers_and_clears_retry_state) ... ok
test_resolve_formal_task_dependencies_terminalizes_exactly_expired_lease (tests.test_state_store.StateStoreTestCase.test_resolve_formal_task_dependencies_terminalizes_exactly_expired_lease) ... ok
test_resolve_reconciliation_issue_prioritizes_exact_current_provenance (tests.test_state_store.StateStoreTestCase.test_resolve_reconciliation_issue_prioritizes_exact_current_provenance) ... ok
test_retryable_failure_waits_until_retry_time (tests.test_state_store.StateStoreTestCase.test_retryable_failure_waits_until_retry_time) ... ok
test_run_as_of_rejects_naive_time_and_persists_utc (tests.test_state_store.StateStoreTestCase.test_run_as_of_rejects_naive_time_and_persists_utc) ... ok
test_score_item_rejects_invalid_coverage_and_does_not_default_missing_scores (tests.test_state_store.StateStoreTestCase.test_score_item_rejects_invalid_coverage_and_does_not_default_missing_scores) ... ok
test_snapshot_deduplicates_same_content_and_versions_new_hash (tests.test_state_store.StateStoreTestCase.test_snapshot_deduplicates_same_content_and_versions_new_hash) ... ok
test_statement_completion_and_feature_followup_are_one_transaction (tests.test_state_store.StateStoreTestCase.test_statement_completion_and_feature_followup_are_one_transaction) ... ok
test_statement_failure_and_feature_followup_are_one_transaction (tests.test_state_store.StateStoreTestCase.test_statement_failure_and_feature_followup_are_one_transaction) ... ok
test_strict_success_clears_recovered_failure_fields (tests.test_state_store.StateStoreTestCase.test_strict_success_clears_recovered_failure_fields) ... ok
test_supersede_formal_tasks_matches_exact_scope_and_preserves_audit_rows (tests.test_state_store.StateStoreTestCase.test_supersede_formal_tasks_matches_exact_scope_and_preserves_audit_rows) ... ok
test_supersede_formal_tasks_rolls_back_when_candidate_changes_before_cas (tests.test_state_store.StateStoreTestCase.test_supersede_formal_tasks_rolls_back_when_candidate_changes_before_cas) ... ok
test_supersede_formal_tasks_validates_scope_and_immediately_fences_owner (tests.test_state_store.StateStoreTestCase.test_supersede_formal_tasks_validates_scope_and_immediately_fences_owner) ... ok
test_terminal_failure_is_never_automatically_released (tests.test_state_store.StateStoreTestCase.test_terminal_failure_is_never_automatically_released) ... ok
test_two_connections_cannot_lease_same_job (tests.test_state_store.StateStoreTestCase.test_two_connections_cannot_lease_same_job) ... ok
test_two_stores_lease_one_formal_task_and_distinct_worker_takes_over (tests.test_state_store.StateStoreTestCase.test_two_stores_lease_one_formal_task_and_distinct_worker_takes_over) ... ok
test_v3_foreign_keys_reject_missing_snapshot_and_feature_set (tests.test_state_store.StateStoreTestCase.test_v3_foreign_keys_reject_missing_snapshot_and_feature_set) ... ok
test_v3_rejects_feature_coverage_outside_closed_unit_interval (tests.test_state_store.StateStoreTestCase.test_v3_rejects_feature_coverage_outside_closed_unit_interval) ... ok
test_v3_rejects_invalid_feature_status_and_dimension (tests.test_state_store.StateStoreTestCase.test_v3_rejects_invalid_feature_status_and_dimension) ... ok
test_wrong_worker_cannot_complete_or_fail_owned_job (tests.test_state_store.StateStoreTestCase.test_wrong_worker_cannot_complete_or_fail_owned_job) ... ok

======================================================================
ERROR: test_genuine_request_seal_rejects_every_out_of_contract_bound (tests.test_formal_range_source.FormalRangeSourceTests.test_genuine_request_seal_rejects_every_out_of_contract_bound) (field='page_index')
----------------------------------------------------------------------
Traceback (most recent call last):
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\tests\test_formal_range_source.py", line 181, in test_genuine_request_seal_rejects_every_out_of_contract_bound
    fixture.source.fetch_verified(request)
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\ashare_pipeline\formal_range_source.py", line 975, in fetch_verified
    previous = request_record(request).previous
               ^^^^^^^^^^^^^^^^^^^^^^^
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\ashare_pipeline\formal_range_source.py", line 229, in request_record
    raise ValueError("formal range request fields changed")
ValueError: formal range request fields changed

======================================================================
ERROR: test_genuine_request_seal_rejects_every_out_of_contract_bound (tests.test_formal_range_source.FormalRangeSourceTests.test_genuine_request_seal_rejects_every_out_of_contract_bound) (field='as_of_utc')
----------------------------------------------------------------------
Traceback (most recent call last):
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\tests\test_formal_range_source.py", line 181, in test_genuine_request_seal_rejects_every_out_of_contract_bound
    fixture.source.fetch_verified(request)
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\ashare_pipeline\formal_range_source.py", line 975, in fetch_verified
    previous = request_record(request).previous
               ^^^^^^^^^^^^^^^^^^^^^^^
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\ashare_pipeline\formal_range_source.py", line 229, in request_record
    raise ValueError("formal range request fields changed")
ValueError: formal range request fields changed

======================================================================
ERROR: test_genuine_request_seal_rejects_every_out_of_contract_bound (tests.test_formal_range_source.FormalRangeSourceTests.test_genuine_request_seal_rejects_every_out_of_contract_bound) (field='start_date')
----------------------------------------------------------------------
Traceback (most recent call last):
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\tests\test_formal_range_source.py", line 181, in test_genuine_request_seal_rejects_every_out_of_contract_bound
    fixture.source.fetch_verified(request)
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\ashare_pipeline\formal_range_source.py", line 975, in fetch_verified
    previous = request_record(request).previous
               ^^^^^^^^^^^^^^^^^^^^^^^
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\ashare_pipeline\formal_range_source.py", line 229, in request_record
    raise ValueError("formal range request fields changed")
ValueError: formal range request fields changed

======================================================================
ERROR: test_genuine_request_seal_rejects_every_out_of_contract_bound (tests.test_formal_range_source.FormalRangeSourceTests.test_genuine_request_seal_rejects_every_out_of_contract_bound) (field='end_date')
----------------------------------------------------------------------
Traceback (most recent call last):
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\tests\test_formal_range_source.py", line 181, in test_genuine_request_seal_rejects_every_out_of_contract_bound
    fixture.source.fetch_verified(request)
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\ashare_pipeline\formal_range_source.py", line 975, in fetch_verified
    previous = request_record(request).previous
               ^^^^^^^^^^^^^^^^^^^^^^^
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\ashare_pipeline\formal_range_source.py", line 229, in request_record
    raise ValueError("formal range request fields changed")
ValueError: formal range request fields changed

======================================================================
ERROR: test_request_cannot_be_constructed_copied_or_mutated_into_authority (tests.test_formal_range_source.FormalRangeSourceTests.test_request_cannot_be_constructed_copied_or_mutated_into_authority)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\tests\test_formal_range_source.py", line 137, in test_request_cannot_be_constructed_copied_or_mutated_into_authority
    fixture.source.fetch_verified(forged)
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\ashare_pipeline\formal_range_source.py", line 975, in fetch_verified
    previous = request_record(request).previous
               ^^^^^^^^^^^^^^^^^^^^^^^
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\ashare_pipeline\formal_range_source.py", line 217, in request_record
    raise ValueError("formal range request is forged, copied, or unregistered")
ValueError: formal range request is forged, copied, or unregistered

----------------------------------------------------------------------
Ran 272 tests in 3109.739s

FAILED (errors=5)
```

Final compatibility logging checkpoint: 44

Controller checkpoint during unchanged run: root committed the exact frozen six
paths as `e6c551d7e36819d38563511fd139ecdaa7a01e58`. No Git write by implementer.
Root has dispatched its independent reviewer; that review and this suite's final
terminal status remain separate gates. At 20:20:27 +04:00 (about 167s elapsed),
worker PID 42628 had 152.27 CPU seconds; concurrency case passed and cross-root
case was running, later passed in chunk 3. No failure output so far.

Recovery handoff amendment: `_range_observation_authority()` in the original source
module returns a tuple `(original RangeObservation, original require_current,
original to_dict)` captured at module initialization. W1 may eagerly capture these
original functions; no mint or callback registration is exposed. Its own genuine
Store and exact StateStore/root checks remain required. Public observation type
alias replacement cannot change that tuple; proof method/property lookup and
inheritance replacement are rejected. Original private helper implementation is
the trusted Python boundary, not an arbitrary-interpreter-tamper defense.
Fetch ingestion likewise uses the original registered producer snapshot before
callbacks; canonical manifest bytes and raw bytes remain detached together.
The user-selected unchanged-v1 quantified-event consumption gap remains recorded
in F3; R3 adds no policy contract, event selector, or quantified-event capability.

## Fix round 2 — request exception boundary (2026-09-19)

Recovered full-run terminal evidence above; rechecked the existing brief, report,
exact test names and original source flow. No Python test process remained.
Read the current TDD skill/reference. This scoped fix loop follows SDD's specific
fix-loop rule: verify the covering tests for the narrow change, here focused RED
followed by full Source plus one parent race. Whole-project completion is not
being declared; its full verification remains a separate later gate.
No tests need changes: the existing typed-error assertions already cover this bug.
The exact issue is the new request_record lookup preceding the old ValueError to
FormalTerminalSourceError conversion. Parent require_observation must remain outside
that conversion and in its current position. Only formal_range_source.py will change.

Fresh RED command:
```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_range_source.FormalRangeSourceTests.test_genuine_request_seal_rejects_every_out_of_contract_bound tests.test_formal_range_source.FormalRangeSourceTests.test_request_cannot_be_constructed_copied_or_mutated_into_authority -v
```

Sole RED session 20206; initial wait 10.003s. Initial output:
```text
test_genuine_request_seal_rejects_every_out_of_contract_bound (tests.test_formal_range_source.FormalRangeSourceTests.test_genuine_request_seal_rejects_every_out_of_contract_bound) ... 
  test_genuine_request_seal_rejects_every_out_of_contract_bound (tests.test_formal_range_source.FormalRangeSourceTests.test_genuine_request_seal_rejects_every_out_of_contract_bound) (field='page_index') ... ERROR
  test_genuine_request_seal_rejects_every_out_of_contract_bound (tests.test_formal_range_source.FormalRangeSourceTests.test_genuine_request_seal_rejects_every_out_of_contract_bound) (field='as_of_utc') ... ERROR
  test_genuine_request_seal_rejects_every_out_of_contract_bound (tests.test_formal_range_source.FormalRangeSourceTests.test_genuine_request_seal_rejects_every_out_of_contract_bound) (field='start_date') ... ERROR
```

Fix2 RED output chunk 1:
```text
  test_genuine_request_seal_rejects_every_out_of_contract_bound (tests.test_formal_range_source.FormalRangeSourceTests.test_genuine_request_seal_rejects_every_out_of_contract_bound) (field='end_date') ... ERROR
test_request_cannot_be_constructed_copied_or_mutated_into_authority (tests.test_formal_range_source.FormalRangeSourceTests.test_request_cannot_be_constructed_copied_or_mutated_into_authority) ... ERROR

======================================================================
ERROR: test_genuine_request_seal_rejects_every_out_of_contract_bound (tests.test_formal_range_source.FormalRangeSourceTests.test_genuine_request_seal_rejects_every_out_of_contract_bound) (field='page_index')
----------------------------------------------------------------------
Traceback (most recent call last):
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\tests\test_formal_range_source.py", line 181, in test_genuine_request_seal_rejects_every_out_of_contract_bound
    fixture.source.fetch_verified(request)
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\ashare_pipeline\formal_range_source.py", line 975, in fetch_verified
    previous = request_record(request).previous
               ^^^^^^^^^^^^^^^^^^^^^^^
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\ashare_pipeline\formal_range_source.py", line 229, in request_record
    raise ValueError("formal range request fields changed")
ValueError: formal range request fields changed

======================================================================
ERROR: test_genuine_request_seal_rejects_every_out_of_contract_bound (tests.test_formal_range_source.FormalRangeSourceTests.test_genuine_request_seal_rejects_every_out_of_contract_bound) (field='as_of_utc')
----------------------------------------------------------------------
Traceback (most recent call last):
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\tests\test_formal_range_source.py", line 181, in test_genuine_request_seal_rejects_every_out_of_contract_bound
    fixture.source.fetch_verified(request)
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\ashare_pipeline\formal_range_source.py", line 975, in fetch_verified
    previous = request_record(request).previous
               ^^^^^^^^^^^^^^^^^^^^^^^
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\ashare_pipeline\formal_range_source.py", line 229, in request_record
    raise ValueError("formal range request fields changed")
ValueError: formal range request fields changed

======================================================================
ERROR: test_genuine_request_seal_rejects_every_out_of_contract_bound (tests.test_formal_range_source.FormalRangeSourceTests.test_genuine_request_seal_rejects_every_out_of_contract_bound) (field='start_date')
----------------------------------------------------------------------
Traceback (most recent call last):
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\tests\test_formal_range_source.py", line 181, in test_genuine_request_seal_rejects_every_out_of_contract_bound
    fixture.source.fetch_verified(request)
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\ashare_pipeline\formal_range_source.py", line 975, in fetch_verified
    previous = request_record(request).previous
               ^^^^^^^^^^^^^^^^^^^^^^^
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\ashare_pipeline\formal_range_source.py", line 229, in request_record
    raise ValueError("formal range request fields changed")
ValueError: formal range request fields changed

======================================================================
ERROR: test_genuine_request_seal_rejects_every_out_of_contract_bound (tests.test_formal_range_source.FormalRangeSourceTests.test_genuine_request_seal_rejects_every_out_of_contract_bound) (field='end_date')
----------------------------------------------------------------------
Traceback (most recent call last):
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\tests\test_formal_range_source.py", line 181, in test_genuine_request_seal_rejects_every_out_of_contract_bound
    fixture.source.fetch_verified(request)
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\ashare_pipeline\formal_range_source.py", line 975, in fetch_verified
    previous = request_record(request).previous
               ^^^^^^^^^^^^^^^^^^^^^^^
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\ashare_pipeline\formal_range_source.py", line 229, in request_record
    raise ValueError("formal range request fields changed")
ValueError: formal range request fields changed

======================================================================
ERROR: test_request_cannot_be_constructed_copied_or_mutated_into_authority (tests.test_formal_range_source.FormalRangeSourceTests.test_request_cannot_be_constructed_copied_or_mutated_into_authority)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\tests\test_formal_range_source.py", line 137, in test_request_cannot_be_constructed_copied_or_mutated_into_authority
    fixture.source.fetch_verified(forged)
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\ashare_pipeline\formal_range_source.py", line 975, in fetch_verified
    previous = request_record(request).previous
               ^^^^^^^^^^^^^^^^^^^^^^^
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\ashare_pipeline\formal_range_source.py", line 217, in request_record
    raise ValueError("formal range request is forged, copied, or unregistered")
ValueError: formal range request is forged, copied, or unregistered

----------------------------------------------------------------------
Ran 2 tests in 14.954s

FAILED (errors=5)
```

Fix2 RED logging checkpoint: 1

Fresh RED complete: 2 tests /14.954s, `FAILED (errors=5)`, exit 1. All five
tracebacks match the prior full-run failure: request_record raises ValueError for
four mutated fields or a forged request before the existing typed-error boundary.
These are expected behavioral errors in the established exception contract, not
fixture/import/setup failures; existing tests remain unchanged by explicit scope.

Applied only a try/except around `request_record(request).previous`, converting
that lookup's ValueError to FormalTerminalSourceError with the original cause.
`require_observation(previous, current=True)` remains outside this conversion;
its integrity ValueError and original execution order are preserved. No source
transport, parser, signature, graph, DDL, test, or dependency changes.

Scoped GREEN command (full Source module plus existing parent correction race):
```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_range_source tests.test_formal_range_store.FormalRangeStoreTests.test_parent_correction_during_fetch_rejects_standalone_continuation -v
```

Sole scoped GREEN session 52942, initial wait 10.005s. Initial output:
```text
test_backward_interval_is_inclusive_and_stops_at_iso_floor (tests.test_formal_range_source.FormalRangeSourceTests.test_backward_interval_is_inclusive_and_stops_at_iso_floor) ... ok
test_empty_response_does_not_claim_complete_coverage (tests.test_formal_range_source.FormalRangeSourceTests.test_empty_response_does_not_claim_complete_coverage) ...
```

Fix2 GREEN output chunk 1:
```text
ok
test_fetch_and_snapshot_parse_bind_content_and_manifest (tests.test_formal_range_source.FormalRangeSourceTests.test_fetch_and_snapshot_parse_bind_content_and_manifest) ... ok
test_first_calendar_request_needs_no_existing_calendar (tests.test_formal_range_source.FormalRangeSourceTests.test_first_calendar_request_needs_no_existing_calendar) ... ok
test_genuine_request_seal_rejects_every_out_of_contract_bound (tests.test_formal_range_source.FormalRangeSourceTests.test_genuine_request_seal_rejects_every_out_of_contract_bound) ... ok
test_identical_source_blob_can_be_reused_by_a_different_manifest_root (tests.test_formal_range_source.FormalRangeSourceTests.test_identical_source_blob_can_be_reused_by_a_different_manifest_root) ... ok
test_implementation_key_and_method_identities_are_sealed (tests.test_formal_range_source.FormalRangeSourceTests.test_implementation_key_and_method_identities_are_sealed) ...
```

Fix2 GREEN output chunk 2:
```text
ok
test_import_orders_have_no_registration_hook_or_partial_cycle (tests.test_formal_range_source.FormalRangeSourceTests.test_import_orders_have_no_registration_hook_or_partial_cycle) ... ok
test_instance_parse_shadow_cannot_bypass_registered_fetch_implementation (tests.test_formal_range_source.FormalRangeSourceTests.test_instance_parse_shadow_cannot_bypass_registered_fetch_implementation) ... ok
test_instance_parse_shadow_cannot_bypass_registered_replay_implementation (tests.test_formal_range_source.FormalRangeSourceTests.test_instance_parse_shadow_cannot_bypass_registered_replay_implementation) ... ok
test_late_capture_and_late_publication_are_preserved_as_observations (tests.test_formal_range_source.FormalRangeSourceTests.test_late_capture_and_late_publication_are_preserved_as_observations) ...
```

Fix2 GREEN output chunk 3:
```text
ok
test_module_private_mint_cannot_authorize_arbitrary_bounds_or_boolean_page (tests.test_formal_range_source.FormalRangeSourceTests.test_module_private_mint_cannot_authorize_arbitrary_bounds_or_boolean_page) ... ok
test_old_and_new_request_placeholders_cannot_cross (tests.test_formal_range_source.FormalRangeSourceTests.test_old_and_new_request_placeholders_cannot_cross) ... ok
test_page_successor_requires_source_backed_exact_page_identity (tests.test_formal_range_source.FormalRangeSourceTests.test_page_successor_requires_source_backed_exact_page_identity) ... ok
test_parser_cannot_mutate_config_or_request_during_execution (tests.test_formal_range_source.FormalRangeSourceTests.test_parser_cannot_mutate_config_or_request_during_execution) ... ok
test_parser_output_identity_page_and_counts_must_match (tests.test_formal_range_source.FormalRangeSourceTests.test_parser_output_identity_page_and_counts_must_match) ...
```

Fix2 GREEN active-process chunk 4:
```text

ElapsedSeconds    CPU   PID
--------------    ---   ---
        285.30 261.70 25340
```

Fix2 GREEN output chunk 5:
```text
ok
test_range_fetch_cannot_be_externally_minted (tests.test_formal_range_source.FormalRangeSourceTests.test_range_fetch_cannot_be_externally_minted) ... ok
test_range_fetch_seal_distinguishes_boolean_from_every_integer_manifest_field (tests.test_formal_range_source.FormalRangeSourceTests.test_range_fetch_seal_distinguishes_boolean_from_every_integer_manifest_field) ...
```

Fix2 GREEN output chunk 6:
```text
ok
test_redirect_challenge_and_blocking_statuses_are_not_evidence (tests.test_formal_range_source.FormalRangeSourceTests.test_redirect_challenge_and_blocking_statuses_are_not_evidence) ... ok
test_request_cannot_be_constructed_copied_or_mutated_into_authority (tests.test_formal_range_source.FormalRangeSourceTests.test_request_cannot_be_constructed_copied_or_mutated_into_authority) ... ok
test_request_dates_and_freeze_are_closed (tests.test_formal_range_source.FormalRangeSourceTests.test_request_dates_and_freeze_are_closed) ... ok
test_rows_require_visibility_fields_and_forbid_policy_conclusions (tests.test_formal_range_source.FormalRangeSourceTests.test_rows_require_visibility_fields_and_forbid_policy_conclusions) ...
```

Fix2 GREEN output chunk 7:
```text
ok
test_select_range_accepts_only_matching_genuine_request (tests.test_formal_range_source.FormalRangeSourceTests.test_select_range_accepts_only_matching_genuine_request) ... ok
test_select_range_rejects_changed_source_blob_even_when_entry_is_identical (tests.test_formal_range_source.FormalRangeSourceTests.test_select_range_rejects_changed_source_blob_even_when_entry_is_identical) ... ok
test_select_range_rejects_different_config_and_root_identity (tests.test_formal_range_source.FormalRangeSourceTests.test_select_range_rejects_different_config_and_root_identity) ...
```

Fix2 GREEN output chunk 8:
```text
ok
test_source_initialization_uses_genuine_registry_and_binding_anchors (tests.test_formal_range_source.FormalRangeSourceTests.test_source_initialization_uses_genuine_registry_and_binding_anchors) ... ok
test_source_instance_rejects_other_complete_source_blob_with_same_selected_entry (tests.test_formal_range_source.FormalRangeSourceTests.test_source_instance_rejects_other_complete_source_blob_with_same_selected_entry) ... ok
test_source_instance_rejects_other_manifest_root_even_for_shared_source_blob (tests.test_formal_range_source.FormalRangeSourceTests.test_source_instance_rejects_other_manifest_root_even_for_shared_source_blob) ... ok
test_transport_request_uses_only_new_placeholders_and_signed_bounds (tests.test_formal_range_source.FormalRangeSourceTests.test_transport_request_uses_only_new_placeholders_and_signed_bounds) ... ok
test_unproven_date_only_effective_time_stays_explicitly_unresolved (tests.test_formal_range_source.FormalRangeSourceTests.test_unproven_date_only_effective_time_stays_explicitly_unresolved) ... ok
test_unregistered_or_self_reported_implementation_is_rejected (tests.test_formal_range_source.FormalRangeSourceTests.test_unregistered_or_self_reported_implementation_is_rejected) ... ok
test_parent_correction_during_fetch_rejects_standalone_continuation (tests.test_formal_range_store.FormalRangeStoreTests.test_parent_correction_during_fetch_rejects_standalone_continuation) ...
```

Fix2 GREEN active-process chunk 9:
```text

ElapsedSeconds    CPU   PID
--------------    ---   ---
        626.60 575.09 25340
```

Fix2 GREEN output chunk 10:
```text
ok

----------------------------------------------------------------------
Ran 32 tests in 686.364s

OK
```

Fix2 GREEN logging checkpoint: 10

### Fix2 terminal result and frozen handoff

Status: DONE for the scoped fix2 implementation and covering verification.
Session 52942 completed all 32 tests in 686.364s, OK, exit 0. All 32 individual
OK results are preserved above; no test warning/error output. The fresh RED
was 2 tests /14.954s, FAILED(errors=5), exit 1, and reproduced every previously
observed exception leak before the source edit. No duplicate or broad suite ran.

Self-review of the exact 5-line diff: only the new request_record lookup gains
the existing FormalTerminalSourceError conversion. It retains its exception cause;
parent require_observation remains outside the try and at the same point in the
valid execution order. The successful parent-correction regression demonstrates
that integrity ValueError is not converted. Source aliases, sealing, parser
dispatch, genuine store pairing and all persistence code remain unchanged.

Post-run SHA-256 values, identical to the pre-GREEN freeze:
```text
9ea048b62153321cdb5d44f0364aa60b9a4fb67ec1a074b19c7012bb35897d04  ashare_pipeline/state_store.py
9a82c014ab4bdc7c1dc122963db5a0190a09ea99519d8f93bc9d6c723986d4f0  ashare_pipeline/formal_range_store.py
33c586bd62f48ebde290e1bdffc0bdfe31a196104b5f4192e0564a9389e740d0  ashare_pipeline/formal_range_source.py
a7dc237578729956adfccef30dc28a1e0c53ddff17eda02f08c376b55ed9ee2b  tests/test_state_store.py
dbc9b3befec3ff5ffdc08e1983bf9ab51f180998ae6c3b8019ee0b7129f1fc90  tests/test_formal_range_store.py
a37a15e48174cafecf3d0fe70825fc7c2389a6e1bd73508dac8e5532302d602d  tests/formal_range_fixtures.py
```
Only formal_range_source.py differs from the fix1 freeze; all five other hashes
are unchanged, including StateStore and its ten already-verified legacy DDL
constants. `git diff --check` passes; only Git LF-to-CRLF advisory is emitted.
Working diff is solely formal_range_source.py (4 insertions, 1 deletion).
HEAD remains external/user-owned 8385ff6529cd27749fd9f4cc1a36cbd58dd397f3;
no Git writes, external doc/tmp SQLite edits, installs, production data/network,
signature/scoring actions, main merge/push or subagents were used.

Evidence boundary and remaining concerns: the earlier full272 run remains FAILED
(five errors in two Source tests), preserved as historical evidence. This scoped
GREEN covers those errors and parent-integrity behavior but is not a new full272
or project-wide pass, nor a final Stage B completion claim. Root's scoped review
and later full-project gate remain separate. Original review Minor adversarial
coverage item and observed long-suite performance limitation remain recorded;
no performance diagnosis/optimization or policy quantified-event activation is
claimed by this fix. Root alone owns staging, commits and review.
