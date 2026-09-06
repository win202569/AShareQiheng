# Task 5B implementation report

Status: base implementation committed as `251815f1f12f0fcb6f55c5410af6aa415c68740b`; post-commit review found P1 historical-calendar and Critical writer-lifecycle defects. Fix-round design is pending coordinator ruling; only the real P1 regression test has been added, with no production repair yet.

## Scope and environment

- Worktree: `D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation`.
- Branch: `codex/formal-v3-implementation`.
- Verified starting HEAD: `e2b85fef97fb8ba144b8d38a5a2daaa1a603aebd`.
- Only five authorized tracked paths are changed: `ashare_pipeline/formal_context_schema.py`,
  `ashare_pipeline/formal_context_repository.py`, `ashare_pipeline/state_store.py`,
  `tests/test_formal_context_schema.py`, and `tests/test_formal_context_repository.py`.
- This report is ignored and is not part of the commit. All edits used `apply_patch`.
- No network, production fetch, production endpoint/parser/mapping/default, score,
  source/time/registry/legacy edit, root-worktree modification, or merge was performed.
- The worktree has no `.venv\Scripts\python.exe`. The first literal prescribed
  command failed before running tests with PowerShell's command-not-found error.
  Subsequent commands use the existing project interpreter:
  `D:\Projects\AShareQiheng\.venv\Scripts\python.exe`, with this worktree as cwd.
  The environment error was not counted as RED.

## Binding rulings received during implementation

The complete brief was read initially and reread after amendments. The parent
confirmed these concrete rulings and incorporated them into the binding brief:

1. The scoring child is exactly the signed canonical wrapper with
   `registry_role="scoring"`, `schema_version="formal-context-registry-v1"`,
   and `descriptors`. Its wrapper and root binding signatures are the trust boundary.
2. There is no production semantic normalizer. An explicit injected
   `FormalContextNormalizer` with the exact descriptor version receives a sealed
   request, a freshly verified source reference, and detached raw bytes. Only a
   closure-sealed `FormalContextNormalization` receipt can authorize a put.
   Publicly created Fact tuples cannot bypass this write gate.
3. A static descriptor upstream generation made same-root corrections impossible.
   The descriptor therefore provides `generation_namespace`; the resolver requires
   explicit keyword-only `upstream_generation` with no default. It is included in
   the request, refresh hash, normalization receipt, and Fact evidence. Task 6 owns
   proving that external generation's authority against its collection payload.
4. The explicit signed `request_version` is carried in the request and hash input.
   Resolver uses `context_kind`; repository getter uses `kind`.
5. Evidence contains deterministic `normalization_input_hash`, computed over
   `formal-context-normalization-input-v1`, descriptor ID, normalizer version,
   complete request wire, verified snapshot manifest/content hashes, and the Fact's
   scientific wire. Fact `id` and `evidence.normalization_input_hash` itself are
   excluded to avoid self-reference; all other evidence remains covered.
6. Historical reads do not rerun the normalizer or source adapter. They reverify
   original bytes, manifest, snapshot, receipt, task, request/configuration, value,
   cutoff, and normalization-input consistency. Calendar lookup does not recurse
   through unrelated date-only Context rows.
7. Within one synchronous operation, a freshly resolved sealed request may supply
   its descriptor to a private checker. The descriptor bytes and seal tables remain
   in the closure; callers cannot mint the corresponding capability. This removes
   repeated full-root reads for the same fact while preserving fresh root verification
   at public operations and all source-lineage checks. Forged/mutated-request tests
   exercise this private path directly.

## Implemented design

`FormalContextFact` and `FormalContextIssue` retain only detached canonical bytes.
Closure-held weak-reference seals reject direct construction, object forgery, and
post-construction byte substitution. Their outward JSON projections are freshly
allocated, JSON-native trees. Canonical validation rejects aliases/cycles, unsupported
leaves, non-finite numbers, extra/missing keys, and noncanonical stored JSON. IDs cover
all scientific fields; StateStore alone supplies the first creation timestamp.

The seven Context kinds have closed value schemas. Market values require explicit
exchange state, volume/turnover, positive valid close, and effective/stale price rules.
Calendar dates are explicit, ordered, unique sessions; no weekday inference exists.
Industry uses SW2021. Regulatory/event entries must pass the signed descriptor's
allowlists. Consensus distinguishes explicit verified no coverage from unavailable
or failed source evidence. Publication, effective time, and source update are each
inclusive at the as-of cutoff; verified late capture is allowed.

The resolver reloads a full nine-role official bundle, selects one exact descriptor,
reselects its signed source configuration, derives the Shanghai freeze date/security
exchange, resolves a fresh date-only binding when required, and hashes the explicit
generation inputs. No raw blob or user-constructed request grants trust.

StateStore adds only `put_formal_context_facts` and `list_formal_context_facts`.
The V6 DDL and indexes are untouched. Put runs in one immediate transaction, checks
the normalization capability and every linked snapshot/raw/receipt/verified
`formal_context` producer/generation, and inserts append-only records. Identical
scientific replay preserves the first audit timestamp; one logical key (including
embedded calendar exchange) and generation cannot acquire a conflicting ID.
List parses canonical rows before filtering and replays every returned row's source
chain; it returns detached Facts in deterministic ID order.

Repository reads validate candidate source references through both
`get_verified_by_manifest` and `read_verified_raw`, repeat cutoff and evidence checks,
use `formal_version_sort_key` verbatim, reject equal leading versions, and compare
candidate snapshots before/after verification to reject correction races. Calendar
bindings include the exact snapshot/manifest/exchange/freeze/root/selector/task.
Effective-time resolution validates that complete binding afresh and selects the
first explicit calendar session strictly after disclosure at 15:00 Shanghai time.

## RED/GREEN evidence recorded so far

All commands below ran in the designated worktree using the absolute interpreter
specified above. There was no implementation before the first real RED.

1. Initial RED:
   `python -m unittest tests.test_formal_context_schema tests.test_formal_context_repository -v`
   exited 1: `Ran 9 tests in 0.062s`, `FAILED (failures=9)`.
   Every failure was an explicit assertion that the required Context module was
   absent, rather than an import typo or missing environment dependency.
2. Schema GREEN after its minimum implementation:
   `python -m unittest tests.test_formal_context_schema -v`
   reported `Ran 8 tests in 2.978s`, `OK`.
3. Expanded integration RED before repository implementation:
   `python -m unittest tests.test_formal_context_repository -v`
   exited 1: `Ran 11 tests in 0.052s`, `FAILED (failures=11)`.
4. First integration run after implementation:
   both Context modules reported `Ran 19 tests in 109.994s`, `FAILED (errors=1)`.
   Eighteen passed. The sole error was a hermetic fixture reusing the same task key
   for different raw responses, so the second response had no current lease.
   The fixture key was corrected to include raw response identity and task kind.
5. Generation/history/calendar amendment RED:
   both Context modules reported `Ran 26 tests in 48.905s`, `FAILED (errors=37)`.
   The expected incompatible old API rejected `upstream_generation`, and the old
   closed descriptor/evidence schemas rejected the newly required fields.
6. Normalization-hash regression was run before the matching implementation and
   failed on the still-missing required generation API (`Ran 1 test`, exit 1).
7. Public request-version/interface RED:
   `test_public_resolver_requires_signed_request_version_and_exact_context_kind`
   reported `Ran 1 test in 1.791s`, `FAILED (errors=1)` because the old resolver
   rejected the required `context_kind` keyword.
8. Private seal-path RED:
   `test_private_fact_check_cannot_use_forged_or_mutated_request`
   reported `Ran 1 test in 1.285s`, `FAILED (failures=1)` because the required
   private checker did not yet exist.
9. An intermediate all-Context run passed its schema cases and the full SH/SZ/BJ
   calendar substitution case, but the calendar case exposed excessive repeated
   full-root verification. That old run was deliberately interrupted at the next
   test and is not counted as GREEN. The current run follows the authorized private
   descriptor deduplication, and still checks all raw/snapshot/receipt/task lineage.

10. Full amended Context run: `Ran 35 tests in 351.514s`, `FAILED (errors=1)`.
    All other 34 tests passed. Complete sole traceback (worktree paths abbreviated):

    ```text
    ERROR: test_date_only_uses_calendar_provenance_without_recursive_self_lookup
    Traceback (most recent call last):
      tests/test_formal_context_repository.py:377, test_date_only_uses_calendar_provenance_without_recursive_self_lookup
        fact, _, _ = self.put(request=request, published="2026-08-19T16:00:00+00:00")
      tests/test_formal_context_repository.py:148, put
        request, ref, raw = self.produce(**kwargs)
      tests/test_formal_context_repository.py:139, produce
        ref = self.snapshots.persist_verified(fetch, verification, producing_task_id=task, worker_id=worker)
      ashare_pipeline/formal_snapshot_repository.py:106, persist_verified
        stored = self._raw_store.write_verified(
      ashare_pipeline/formal_snapshot_store.py:127, write_verified
        calendar_binding = self._resolve_calendar_binding(
      ashare_pipeline/formal_snapshot_store.py:425, _resolve_calendar_binding
        raise ValueError("date-only evidence requires a trusted calendar binding resolver")
    ValueError: date-only evidence requires a trusted calendar binding resolver
    ```

    Confirmed fixture wiring omission, not permission to alter accepted source/store.
    Tests now inject a narrow callback retaining only sealed request inputs (not a
    cached binding), check exact OfficialRequest identity, then freshly resolve the
    descriptor selector/exchange/root/as-of through the real Context repository.
    Timestamp bootstrap calendars are persisted first. Root/exchange request and
    wrong-selector negative cases guard the bridge.

11. Date-only bridge GREEN: `test_date_only_uses_calendar_provenance_without_recursive_self_lookup`
    completed `Ran 1 test in 305.292s`, `OK`, exit 0. This exercises the real signed
    bootstrap calendar and date-only persistence/read path plus root, selector,
    exchange, dataset, and seal-mutation negative cases. No production source/store
    module was changed. While running, Python remained responsive and its CPU time
    advanced from 62.92s to 142.19s; the test was not cancelled.
12. Signed event quantity RED: two new tests completed `Ran 2 tests in 5.467s`,
    `FAILED (errors=2)`, exit 1. Both failures were exactly:

    ```text
    test_event_quantity_is_signed_but_market_volume_is_nonnegative
      tests/test_formal_context_schema.py:118 -> FormalContextFact.create
      formal_context_schema.py:303 -> validate(_load(raw))
      formal_context_schema.py:275 -> _validate_value
      formal_context_schema.py:216 -> _decimal(entry["quantified_value"])
      formal_context_schema.py:126 -> ValueError: Context quantity is not finite or in range
    test_signed_event_allowlist_preserves_negative_quantified_evidence
      tests/test_formal_context_repository.py:451 -> put
      tests/test_formal_context_repository.py:165 -> normalize
      tests/test_formal_context_repository.py:161 -> registry.normalize_verified
      formal_context_schema.py:612 -> normalizer.normalize
      tests/test_formal_context_repository.py:64 -> FormalContextFact.create
      formal_context_schema.py:303 -> validate(_load(raw))
      formal_context_schema.py:275 -> _validate_value
      formal_context_schema.py:216 -> _decimal(entry["quantified_value"])
      formal_context_schema.py:126 -> ValueError: Context quantity is not finite or in range
    ```

### Binding rulings / verification ledger

17. Event quantity: event_calendar.quantified_value accepts a canonical finite signed decimal; market_close.volume and market_close.turnover remain canonical finite non-negative decimals.

The negative event restriction was identified during self-review and explicitly
resolved by the coordinator before production changes. The minimal correction adds
an `allow_negative` parameter to the existing canonical finite-decimal check and
enables it only for the event quantified-value call. Market quantity/positive-close
checks remain unchanged. The two tests cover signed Fact creation, descriptor
allowlist authorization, real sealed normalization and persistence/read-back, and
continued rejection of negative market volume. Completed GREEN results follow below.

13. Final two-Context-module GREEN on the frozen implementation:

    ```powershell
    & 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m unittest tests.test_formal_context_schema tests.test_formal_context_repository -v
    ```

    ```text
    Ran 37 tests in 687.637s
    OK
    exit_code: 0
    ```

    All 10 schema and 27 repository tests passed, including the two signed-event
    regressions and the complete date-only bridge case. No test was skipped or
    cancelled in this final directed run.
14. Standalone five-file compilation after the event correction:

    ```powershell
    & 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m py_compile ashare_pipeline/formal_context_schema.py ashare_pipeline/formal_context_repository.py ashare_pipeline/state_store.py tests/test_formal_context_schema.py tests/test_formal_context_repository.py
    ```

    No output, `exit_code: 0`. Initial unstaged `git diff --check` also exited 0;
    Git only emitted its existing LF-to-CRLF informational warning for StateStore.
    The final staged whitespace/scope check below will also include the new files.

15. Required four-module regression GREEN on the same frozen implementation:

    ```powershell
    & 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m unittest tests.test_formal_context_schema tests.test_formal_context_repository tests.test_formal_sources tests.test_formal_time -v
    ```

    ```text
    Ran 78 tests in 593.952s
    OK
    exit_code: 0
    ```

    Every Context test, all 36 existing source tests, and all 5 existing time tests
    passed. No skipped/cancelled test is counted as GREEN.
16. Final post-regression preflight reran the five-file `py_compile` command from
    entry 14 and `git diff --check` with explicit nonzero-exit guards: exit 0.
    `git diff --cached --name-only` was empty before staging. `git status --short`
    showed only the four authorized new files and modified StateStore. Branch and
    HEAD remained `codex/formal-v3-implementation` and
    `e2b85fef97fb8ba144b8d38a5a2daaa1a603aebd`. `git check-ignore` confirmed both this
    report and the binding brief are ignored.
17. Precise staging command (no wildcard or force-add):

    ```powershell
    git add -- ashare_pipeline/formal_context_schema.py ashare_pipeline/formal_context_repository.py ashare_pipeline/state_store.py tests/test_formal_context_schema.py tests/test_formal_context_repository.py
    ```

    The default sandbox attempt failed only on permission to create
    `.git/worktrees/formal-v3-implementation/index.lock`; the same authorized command
    was retried with reviewed Git-metadata write permission and exited 0. Git emitted
    only LF-to-CRLF informational warnings. No data, report, brief, database, or
    snapshot was staged.
18. Final staged checks:

    ```powershell
    git diff --cached --check
    git diff --cached --stat
    git diff --cached --name-only
    git diff --name-only
    git status --short
    ```

    Whitespace check exited 0; there were no unstaged tracked differences. Exactly:

    ```text
     ashare_pipeline/formal_context_repository.py | 249 +++++++++
     ashare_pipeline/formal_context_schema.py     | 736 +++++++++++++++++++++++++++
     ashare_pipeline/state_store.py               |  18 +
     tests/test_formal_context_repository.py      | 510 +++++++++++++++++++
     tests/test_formal_context_schema.py          | 142 ++++++
     5 files changed, 1655 insertions(+)
    ```

    Self-review read the new production modules/tests and the 18-line StateStore
    diff against the binding brief. Existing source/time/registry/root/feature and
    legacy modules, V6 DDL/indexes, and production assets are unchanged. The only
    late semantic correction was the explicitly ruled, RED-tested signed event
    quantity. No scoring, worker, network transport, or production default was added.

19. Authorized commit and post-commit proof:

    ```powershell
    git commit -m "feat: add verified formal market and policy context"
    git rev-parse HEAD
    git show --stat --oneline --summary HEAD
    git status --short
    git diff --check
    git diff --cached --check
    git log -1 --format=%P
    ```

    Commit succeeded with reviewed Git-metadata write permission, exit 0:
    `251815f1f12f0fcb6f55c5410af6aa415c68740b`, subject exactly
    `feat: add verified formal market and policy context`. `show --stat` confirmed
    the same five-file / 1655-insertion scope above. Post-commit status and both
    diff checks produced no output; the verification command group exited 0.
    The sole parent is the authorized baseline
    `e2b85fef97fb8ba144b8d38a5a2daaa1a603aebd`. No merge, push, worktree cleanup,
    external fetch, production asset, or ignored artifact was included.

## Explicit trust limitation

The normalization receipt is an in-process write capability, not a persisted
signature. After process restart, reads rederive public deterministic consistency
hashes and verify raw/configuration/structural provenance. They do not semantically
reparse the bytes. A coordinated direct-SQL rewrite that recomputes every public
deterministic field is not cryptographically prevented by this design. Approved
production normalizers/parsers and any stronger external attestation remain a
future release boundary. No report or API here claims release authorization.

## Known performance limitation

The date-only end-to-end test took 305.292 seconds in this environment. The
coordinator's read-only performance audit found no visible infinite recursion:
timestamp bootstrap-calendar evidence terminates the chain. The cost comes from
multiple layers of complete root/raw/snapshot/receipt/task revalidation. In
particular, `_put_context_facts` revalidates the entire existing Context table on
each append, making incremental bulk writes O(N²) in the number of facts. This is
not acceptable for a future full-A-share incremental collection workload.

This known performance issue does not relax Task 5B correctness or authorize an
optimization in this patch. Production code remains unchanged by this audit. Safe
follow-up work needs a separate design: reuse freshly verified root/descriptor
state only inside one synchronous operation through sealed private capabilities,
and separately design a scalable `_put` validation/collision strategy. Any such
change must preserve fresh public-entry official-bundle verification, request
sealing, raw/snapshot/receipt/task lineage, calendar freshness, correction-race
checks, and rejection of tampered leading evidence. Cross-call trust/binding
caches, skipped lineage validation, and weekday/default fallbacks are not proposed.

## Post-commit review / fix round 1 — in progress

### P1: historical calendar correction

The real regression creates signed bootstrap C1, normalizes/persists date-only D1
with B1/G1, then appends corrected signed C2 and derives current B2/G2 for D2.
Its final assertions require both D1/D2 to remain available for audit, formal
version ordering to select D2, and deletion of historical C1 to fail closed rather
than being hidden by D2. No old row is mocked or skipped.

RED command:

```powershell
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m unittest tests.test_formal_context_repository.ContextIntegrationTests.test_calendar_revision_preserves_date_only_history_and_rejects_missing_anchor -v
```

Result: `Ran 1 test in 18.887s`, `FAILED (errors=1)`, exit 1. C1, D1, C2,
current B2/G2 resolution, and D2 snapshot/normalization all succeeded. The first
failure was at D2 put while revalidating the existing D1:

```text
Traceback (most recent call last):
  tests/test_formal_context_repository.py:438, test_calendar_revision_preserves_date_only_history_and_rejects_missing_anchor
    d2, _, _ = self.put(request=r2, published="2026-08-19T16:00:00+00:00",
  tests/test_formal_context_repository.py:166, put
    self.store.put_formal_context_facts(receipt)
  ashare_pipeline/state_store.py:1914, put_formal_context_facts
    _put_context_facts(self, connection, normalization)
  ashare_pipeline/formal_context_repository.py:80, _put_context_facts
    _validate_stored_fact(store, connection, fact, verifier)
  ashare_pipeline/formal_context_repository.py:44, _validate_stored_fact
    ref = store._formal_verified_snapshot_ref_from_connection(connection, row)
  ashare_pipeline/state_store.py:2449, _formal_verified_snapshot_ref_from_connection
    ref = self._formal_snapshot_row_to_ref(row)
  ashare_pipeline/state_store.py:2597, _formal_snapshot_row_to_ref
    raw_bytes = raw_store.read_verified_raw(stored)
  ashare_pipeline/formal_snapshot_store.py:196, read_verified_raw
    self._resolve_calendar_binding(
  ashare_pipeline/formal_snapshot_store.py:442, _resolve_calendar_binding
    raise ValueError("trusted calendar binding manifest mismatch")
ValueError: trusted calendar binding manifest mismatch
```

RCA: Context rebuilds historical requests with the current leading calendar, and
the trusted raw-store callback also only receives OfficialRequest and resolves
current B2. Therefore the real failure is B1-to-B2 substitution at the raw boundary,
before the later Context generation/hash mismatch. Fixing only sorting or skipping
the old D1 is unsound. Historical revalidation must preserve B1 and freshly prove
its complete calendar Fact/source/root lineage. The existing configured raw-store
instance must be retained; its StateStore access contract expressly prohibits
constructing a second store/view. An initial second-store proposal was withdrawn
before any production patch.

### Critical: writer and published-reader provenance are conflated

Coordinator reproduced the worker-order defect separately. Local read-only tracing
confirms `normalize_verified` and put/list share `_require_context_producer`, which
requires task status `verified` and completed result state. The original fixture
completes its task before normalizing, concealing the intended sequence: leased
owner persists snapshot receipt, normalizes/persists facts, then completes task.
Writer provenance needs exact live-lease ownership bound into a sealed receipt;
public reads must continue to demand verified task/result/receipt. API and expanded
raw-read capability scope were subsequently approved in task-5b-remediation-plan.md.

### R1 independent RED and first GREEN

The initial test-only worker sequence used the old API and left the source task
leased. It failed at the exact production deadlock, not fixture setup:

```text
Command: root .venv Python -m unittest tests.test_formal_context_repository.ContextIntegrationTests.test_context_writer_persists_before_completion_without_publishing_leased_facts -v
Ran 1 test in 4.205s
FAILED (errors=1)
test_formal_context_repository.py:196 -> normalize helper:163
formal_context_schema.py:611 -> _require_context_producer
formal_context_repository.py:25
ValueError: Context evidence requires a verified formal_context producer and exact generation
```

Before any production repair, the six writer methods (seven cases including the
wrong-worker/wrong-task subtests) all ran with the approved new owner keywords:
`Ran 6 tests in 18.042s`, `FAILED (errors=7)`, each at the missing required API,
`TypeError: ...normalize_verified() got an unexpected keyword argument 'task_id'`.
This expanded RED establishes the desired interface, not separate proof that each
safety branch was reached on the baseline. The first core RED proves the root cause.

R1 production changes are confined to Context schema/repository. Normalization
requires explicit task_id/worker_id, verifies exact formal_context live lease,
snapshot producer/generation, and unique exact source receipt before/after the
normalizer, and seals the complete writer/receipt wire. Put accepts only that seal,
checks its live owner at entry and at the end of the existing immediate transaction,
and permits same-source idempotent recovery only for the current owner. Public
read checks remain verified-only. Whole-table writer validation remains until R3.

First GREEN command: root .venv Python `-m unittest` with these fully qualified
ContextIntegrationTests methods, followed by `-v`:

- test_context_writer_persists_before_completion_without_publishing_leased_facts
- test_context_writer_rejects_wrong_worker_and_task
- test_context_writer_rejects_expired_lease_at_normalize_and_put
- test_context_writer_rechecks_lease_after_normalizer_callback
- test_context_writer_new_owner_recovers_same_receipt_and_rejects_old_capability
- test_context_writer_rolls_back_when_lease_expires_after_insert

Result: `Ran 6 tests in 58.288s`, `OK`, exit 0. The post-insert test uses a
disposable test-database trigger to expire the lease after Fact insertion and
checks both insertion and trigger mutation roll back. This is not production DDL.
Assertions are then tightened to exact error messages to independently demonstrate
lease, task-identity, and public verified-only branch attribution.

R1 exact-message rerun: same six-method command, `Ran 6 tests in 53.195s`,
`OK`, exit 0. All expiry/owner failures match `lease expired or ownership changed`;
wrong task matches `task does not match snapshot producer`; public leased reads
match `verified formal_context producer`. The sealed writer wire is asserted equal
to the complete actual source receipt, task, owner, and generation.

### R2 independently observed RED after R1 GREEN

Command (root interpreter, worktree cwd):

```powershell
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m unittest tests.test_formal_context_repository.ContextIntegrationTests.test_calendar_revision_preserves_date_only_history_and_rejects_missing_anchor tests.test_formal_context_repository.ContextIntegrationTests.test_historical_read_capability_is_target_bound_and_unforgeable tests.test_formal_context_repository.ContextIntegrationTests.test_historical_calendar_anchor_tamper_invalidates_existing_capability -v
```

`Ran 3 tests in 1183.067s`, `FAILED (failures=2, errors=1)`, exit 1.
The existing full three-exchange fixture was retained throughout this RED.
The session was not cancelled; PID 22128 continued consuming CPU (83.61s,
224.89s, 461.53s, 691.69s and 942.34s samples). The first test completed in
roughly nine minutes; unittest emitted complete tracebacks at final summary.
No lease or fixture failure masked the defect:

```text
ERROR: test_calendar_revision_preserves_date_only_history_and_rejects_missing_anchor
test_formal_context_repository.py:525 -> d2 = self.put(...)
test_formal_context_repository.py:169 -> store.put_formal_context_facts(receipt)
state_store.py:1914 -> _put_context_facts
formal_context_repository.py:122 -> _validate_stored_fact(old D1)
formal_context_repository.py:75 -> _formal_verified_snapshot_ref_from_connection
state_store.py:2449 -> _formal_snapshot_row_to_ref
state_store.py:2597 -> raw_store.read_verified_raw(stored)
formal_snapshot_store.py:196 -> _resolve_calendar_binding
formal_snapshot_store.py:442
ValueError: trusted calendar binding manifest mismatch

FAIL: test_historical_read_capability_is_target_bound_and_unforgeable
test_formal_context_repository.py:544 -> capture_historical_read
test_formal_context_repository.py:602
AssertionError: [] is not true : historical Context must use a sealed historical raw read

FAIL: test_historical_calendar_anchor_tamper_invalidates_existing_capability
test_formal_context_repository.py:566 -> capture_historical_read
test_formal_context_repository.py:602
AssertionError: [] is not true : historical Context must use a sealed historical raw read
```

The latter two failures occur after a successful real public Context read. A
test wrapper observes the capability passed to the real configured raw store;
there is no test-only mint or exported mint helper. Their forgery/tamper branches
are intentionally not claimed as reached on the baseline, which has no capability.

R2 design: only stored date-only Fact validation mints a closure-sealed historical
read after rebuilding its request against the exact persisted calendar binding.
The anchor is required to have a signed `bootstrap_calendar=True` descriptor,
timestamp evidence, exact root/selector/exchange/freeze, one matching calendar
Fact, and freshly verified source snapshot/raw/receipt/verified producer. Each
capability use rechecks its seal, full request, configured raw-store object identity,
target snapshot ID/manifest/content, persisted Fact and original anchor chain.
The selected-row, manifest lookup and read paths explicitly thread that capability;
public Context selection before/after checks use the same historical validation.
Neither a normalizer nor a new write accepts a historical capability. Raw
`write_verified` is unchanged. No parser or normalizer is rerun on historical reads.
Checkers do not expose the internal seal record; no mint or capability class is
exported. The public `__all__` remains unchanged.

The first R2 patch failed whole-patch verification because its final fixture hunk
omitted an existing keyword-only `*`; read-only diff confirmed no partial R2 edit.
The corrected single retry completed successfully and touched only the six approved
code/test files. The coordinator then approved two explicit closure/anchor guards.
For subsequent GREEN runs only the three new R2 tests install the SZ calendar;
the real C1/D1/C2/D2 chain is unchanged, and existing SH/SZ/BJ isolation tests retain
all three exchanges. This removes irrelevant fixture setup, not provenance checks.

### R2 corrective TDD: full record versus scientific wire

Six-file `py_compile` passed, `git diff --check` passed (only CRLF notices), and a
read-only signature check printed `Public write/current APIs and closure-only
historical mint: OK`: raw write/current resolve/normalize expose no historical
parameter; normalization requires both keyword-only owners; Context put remains
receipt-only; the historical class and factory are absent from module exports.

The first individual C1/D1/C2/D2 GREEN attempt failed: `Ran 1 test in 235.471s`,
`FAILED (errors=1)`, exit 1. C2 put was revalidating the stored D1:

```text
test_formal_context_repository.py:518 -> self.put(c2_request)
test_formal_context_repository.py:169 -> put_formal_context_facts
state_store.py:1914 -> _put_context_facts
formal_context_repository.py:237 -> _validate_stored_fact
formal_context_repository.py:176 -> _formal_verified_snapshot_ref_from_connection
state_store.py:2449 -> _formal_snapshot_row_to_ref
state_store.py:2600 -> raw_store.read_verified_raw(... historical_read=...)
formal_snapshot_store.py:196 -> _read_calendar_binding
formal_snapshot_store.py:422 -> _historical_read_binding
formal_context_repository.py:137 -> FormalContextFact.from_dict(_load(fact_bytes))
formal_context_schema.py:327
ValueError: Context record ID is missing
```

The agent stopped and reported the complete traceback before further production
changes. Read-only inspection confirmed `_record_type`'s contract: canonical_bytes
is the scientific wire without ID, `to_dict` adds the derived ID, and `from_dict`
requires and rechecks that ID. This was an implementation serialization error,
not calendar substitution, lease expiry, or a reason to relax lineage verification.

A new minimal real regression was written and actually run before the corrective
patch:

```powershell
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m unittest tests.test_formal_context_repository.ContextIntegrationTests.test_historical_capability_roundtrips_full_fact_record_and_rejects_id_changes -v
```

Result: `Ran 1 test in 259.964s`, `FAILED (errors=1)`, exit 1. Its complete-record
roundtrip, expected missing-ID scientific-wire rejection, and swapped-ID rejection
all passed first. It then failed through the real public path at the same boundary:

```text
test_formal_context_repository.py:575 -> capture_historical_read
test_formal_context_repository.py:626 -> self.get()
formal_context_repository.py:344 -> _select
formal_context_repository.py:320 -> _candidates
formal_context_repository.py:310 -> list_formal_context_facts
state_store.py:1923 -> _list_context_facts
formal_context_repository.py:291 -> _validate_stored_fact
formal_context_repository.py:176 -> _formal_verified_snapshot_ref_from_connection
state_store.py:2449 -> _formal_snapshot_row_to_ref
state_store.py:2600 -> real raw-read observer
test_formal_context_repository.py:622 -> original_read(... historical_read=...)
formal_snapshot_store.py:196 -> _read_calendar_binding
formal_snapshot_store.py:422 -> _historical_read_binding
formal_context_repository.py:137 -> FormalContextFact.from_dict(_load(fact_bytes))
formal_context_schema.py:327
ValueError: Context record ID is missing
```

The smallest correction stores two immutable byte strings in the closure: canonical
`fact.to_dict()` including ID for reconstruction/full-record comparison, and the
original `fact.canonical_bytes()` for the separate scientific comparison. Both are
rechecked against the persisted Fact. Target tuple positions are unchanged. The
new regression also requires an existing capability to reject changed/cleared DB
IDs and to work again only after exact restoration. No schema, raw verification,
normalization hash, or public visibility rule is weakened.

Corrective GREEN: the same minimal full-record/ID regression completed with
`Ran 1 test in 221.085s`, `OK`, exit 0. It exercised successful real-capability
reads, swapped/cleared persisted ID rejection, and exact-restoration recovery.
Six-file `py_compile` and `git diff --check` also exited 0 after the dual-wire patch.
The three original R2 integration/security tests are then run separately from R3.

The three-test R2 GREEN batch completed with `Ran 3 tests in 847.552s`,
`FAILED (errors=1)`, exit 1. Both capability target/forgery/raw-instance tests and
historical-anchor Fact/task/receipt/source/raw tamper tests passed. The C1/D1/C2/D2
test failed before C2: its disposable fixture's 300-second writer lease expired
during D1 verification and the R1 transaction-tail guard correctly rejected it:

```text
test_formal_context_repository.py:515 -> D1 self.put
test_formal_context_repository.py:169 -> put_formal_context_facts
state_store.py:1914 -> _put_context_facts
formal_context_repository.py:268 -> transaction-tail _require_context_writer
formal_context_repository.py:63 -> _require_formal_snapshot_owner
state_store.py:3090
ValueError: formal snapshot task lease expired or ownership changed
```

No production patch followed this failure. The full traceback was reported to the
coordinator for a test-only explicit slow-fixture lease allowance; production lease
checks and R1 expiry/rollback negatives remain unchanged. The test process exited
normally; a simultaneous read-only Get-Process sample found no remaining Python
process (that diagnostic command alone exited 1).

Coordinator-approved test-only correction: `produce` now accepts an optional
`lease_seconds` with its existing default 300 unchanged; only the four R2 historical
correctness/capability tests explicitly pass 3600 to their slow Context writes.
No production default or lease guard, and no R1 expiry/rollback test, is changed.
The 847.552-second batch failure is an expected expired-lease guard, not evidence
of a historical-binding logic failure. C1/D1/C2/D2 is rerun alone first.

R2 C1/D1/C2/D2 individual GREEN after the explicit test lease allowance:
`Ran 1 test in 689.924s`, `OK`, exit 0. This completed both retained generations,
formal-version selection of D2, distinct original B1/B2 evidence, and fail-closed
read after deletion of C1. The original three R2 tests are then rerun as a batch.
The first report-only append failed due to wrapped-line context; after rereading
the exact tail, the append was retried. No code/test file was involved.

R2 complete targeted GREEN: the three original R2 tests completed together with
`Ran 3 tests in 1168.560s`, `OK`, exit 0. They cover retained C1/D1/C2/D2 history,
new-version selection, missing historical anchor, capability forgery and target/raw
instance substitution, and historical Fact/task/receipt/source/raw tampering.
The dual-wire/ID regression was independently GREEN above. Six R1 writer methods
plus the original date-only provenance test are then run as the R1/R2 intersection
before any R3 test or production change.

R1/R2 intersection GREEN: six R1 writer methods plus the original three-exchange
date-only provenance test completed with `Ran 7 tests in 297.287s`, `OK`, exit 0.
The original shared fixture default remains 300 seconds. The coordinator received
this result before authorizing R3 to begin.

### R3 candidate-only writer validation: test-first boundary

The new isolation test first persists a real verified industry Context and corrupts
only its source content hash. It then obtains a complete leased security-state
normalization, requires successful first and identical replay writes, completes the
producer, verifies the scoped security read, and requires the same root-wide public
list to reject the unrelated corrupt source. Restoring the exact hash makes both
Facts readable. Existing nonidentical-generation conflict/idempotence tests and
three-exchange integration remain, plus a pure `_logical_key` exchange-discriminator
assertion. The alternate exchange record in that pure test is never normalized or
persisted; no impossible signed descriptor is invented. Production remains unchanged
until the isolation test has actually failed at full-table writer revalidation.

R3 actual isolated RED: `Ran 1 test in 9.484s`, `FAILED (errors=1)`, exit 1.
The industry producer had completed and incoming security normalization had already
passed its signed source/lease checks. The first put failed exactly here:

```text
test_formal_context_repository.py:371 -> put_formal_context_facts
state_store.py:1914 -> _put_context_facts
formal_context_repository.py:243 -> full-table existing-Fact validation
formal_context_repository.py:182 -> verified source reference
state_store.py:2449/2600 -> raw-store read
formal_snapshot_store.py:179
ValueError: content hash does not match manifest
```

The independent conflict/idempotence/pure-exchange-key/three-exchange integration
baseline then completed `Ran 4 tests in 276.155s`, `OK`, exit 0 before production
changed. The coordinator received exact RED and baseline evidence and approved the
minimal patch. Put now fully verifies each incoming fact first, queries candidates
by exact kind/scope/NULL-safe security/as-of/root/generation, parses each canonical
record before exchange filtering, and fully verifies every matching candidate.
The existing per-call dictionary still detects same-batch duplicates/conflicts;
entry/tail writer receipt and lease checks and public list remain unchanged.
No DDL, index, cross-call cache, raw boundary, or public read policy is changed.

R3 complete target GREEN: isolation, conflict, idempotence, pure exchange key, and
three-exchange integration completed `Ran 5 tests in 274.770s`, `OK`, exit 0.
Seven-file `py_compile` and `git diff --check HEAD` also exited 0 (Git only emitted
its existing LF-to-CRLF notices). The specified four-module regression and the two
additional snapshot boundary modules are then run on the same code state.

Updated performance limitation: R3 removes full-table source-provenance revalidation
from each write, but V6 has no composite index for the candidate predicate. The SQL
lookup may still scan stored Context rows; this is not a claim of O(1) writes or
proven all-A-share throughput. Public reads deliberately retain full matching-row
verification. A separately designed/measured composite index and safe per-call root
reuse remain follow-up work, not changes in this code-only repair.

Additional snapshot boundary regression completed: `tests.test_formal_snapshot_store`
and `tests.test_formal_snapshot_repository`, `Ran 45 tests in 128.733s`,
`OK (skipped=3)`, exit 0. The three existing symlink tests skipped because Windows
returned WinError 1314 (missing symlink privilege); 42 tests passed. No environment
permission changes were attempted. The specified four-module suite remains running.

Coordinator pre-review raised a possible double-hash history-target issue. Read-only
inspection established that schema `_hash` (lines 84-87) validates lowercase 64-hex
and returns the original value. Repository target construction and both stored/source
comparisons therefore use identical original hashes. A read-only Python assertion
`assert _hash('a' * 64) == 'a' * 64` exited 0. This candidate required no code change.
Production changes and submission remain paused while the full suite and review finish.

### Controlled Windows diagnostic isolation (invalid test result)

The interrupted four-module session 31178 never produced a complete unittest
summary. Its buffered tail included a successful historical C1/D1/C2/D2 case, but
the overall suite is not GREEN. Only its authorized test child PID 38100 was stopped.

The following single-case diagnostic session 9590 used the project `.venv` Python,
without changing code, and sampled stacks every 120 seconds with faulthandler.
At the fifth sample (about 10 minutes), it emitted `Windows fatal exception:
access violation` with a top path through `ntpath.realpath`, `pathlib.resolve`, and
the raw-store path-boundary checks. There was no unittest `Ran`, `OK`, or `FAILED`
summary; subsequent polling returned no further output or exit code.

The coordinator authorized targeted isolation. Read-only identity checks bound the
diagnostic child 32636 (start 2026-09-06 03:21:20 local, parent 32616) to the project
`.venv` launcher 32616 (start 03:21:19). A guarded stop terminated only child 32636;
the stop command exited 0, and diagnostic session 9590 then exited 1 with no unittest
result. At 03:44:05, read-only checks confirmed neither child 32636 nor launcher
32616 remained. Another Python process was not touched. This is recorded as a
Windows running-environment exception and an invalid diagnostic result, not a
passing test or an application-logic test failure. No immediate rerun followed.

The earlier samples traversed temporary-file `os.open`, SQLite registry connections,
and canonical path checks. These observations distinguish the known cost of strict
raw/path/root revalidation from the separate report-edit tool failure:
`windows sandbox failed: timed out after 15000ms waiting for runner spawn_ready`.
That failed append had no write; a later read-only tail confirmed it was absent.
The tool-layer timeout is not attributed to production logic. No raw atomic-write,
test-core, or provenance semantics were changed to reduce runtime.

Post-isolation `git status --short` exited 0 and still showed only the same six
authorized modified tracked files; no tracked file was added and no code was changed
during diagnosis/isolation. Full four-module verification and the repair commit remain
pending. This report-only append follows the coordinator's controlled resumption.

### Final controlled regression and compatibility correction

Session 9590 remains an invalid Windows environment diagnostic, not a test result:
at about 10 minutes faulthandler emitted `Windows fatal exception: access violation`
without a unittest summary. After the authorized targeted stop of child 32636,
session 9590 exited 1. It is excluded from passing/failing test counts below.

The grouped regression exposed a default-call compatibility regression in Context
source revalidation. The existing correction test's `race(snapshot)` hook rejected
the newly unconditional `historical_read=None` keyword before reaching its real
Fact-deletion/correction check. Group 4 was RED: 6 tests in 56.701s, errors=1,
exit 1, with `TypeError: race() got an unexpected keyword argument 'historical_read'`.
The minimal production correction restores `read_verified_raw(current)` when
`historical_read is None`; only non-None historical capabilities are passed by
keyword. The historical capability path and all provenance validation remain
unchanged. No test or mock was changed. The exact correction regression then
completed GREEN: 1 test in 21.347s, OK, exit 0, and complete Group 4 was rerun.

Final verification uses complete, serial groups with no faulthandler or concurrent
test process. Times below are unittest-reported wall times, not tool dispatch or
polling latency. Context groups 1-3 were rerun after the compatibility correction.

| Final verification group | Tests | unittest seconds | Result |
| --- | ---: | ---: | --- |
| Context schema, sources, time modules | 51 | 6.012 | OK, exit 0 |
| Context groups 1-3: registry/API, normalization/read, writer lifecycle | 16 | 99.447 | OK, exit 0 |
| Context group 4: stored-evidence tamper/correction | 6 | 60.397 | OK, exit 0 |
| Context group 5: generation/time ordering | 5 | 89.808 | OK, exit 0 |
| Context group 6: R3 candidate isolation/keying | 2 | 30.328 | OK, exit 0 |
| Context group 7: calendar baseline/date-only bridge | 3 | 442.434 | OK, exit 0 |
| Context group 8: C1/D1/C2/D2 history and missing anchor | 1 | 829.400 | OK, exit 0 |
| Context group 9: target-bound, unforgeable historical capability | 1 | 158.271 | OK, exit 0 |
| Context group 10: full Fact record and changed-ID rejection | 1 | 158.642 | OK, exit 0 |
| Context group 11: historical-anchor tamper | 1 | 150.751 | OK, exit 0 |
| Context group 12: value/consensus constraints | 3 | 44.322 | OK, exit 0 |
| Snapshot store and snapshot repository modules | 45 | 43.925 | OK, skipped=3, exit 0 |

The complete ContextRepository module coverage totals 39 tests in 2063.800 seconds,
all OK, across the listed disjoint groups. The snapshot modules passed 42 tests;
three existing Windows symlink tests skipped for WinError 1314 (missing privilege).
No privilege or environment configuration was changed to suppress those skips.
Six-file `py_compile` and `git diff --check HEAD` both exited 0. Git emitted only
its existing LF-to-CRLF notices. Status/name-only/stat checks exited 0 and showed
exactly these six unstaged modified tracked files, with no tracked addition:

- `ashare_pipeline/formal_context_repository.py`
- `ashare_pipeline/formal_context_schema.py`
- `ashare_pipeline/formal_snapshot_repository.py`
- `ashare_pipeline/formal_snapshot_store.py`
- `ashare_pipeline/state_store.py`
- `tests/test_formal_context_repository.py`

The diff contains 520 insertions and 68 deletions across those six files. Nothing
has been staged or committed for this repair at the time of this report append.
The completed grouped verification supersedes the earlier pending-regression status;
it does not retroactively turn the interrupted or invalid diagnostic sessions green.

Performance attribution remains limited: strict raw/path/root verification has
observable cost, while Windows native access violation and sandbox runner
`spawn_ready` timeout are distinct environment/tool-layer incidents, not demonstrated
production-logic defects. R3 candidate-only writer validation is implemented as
described above; no claim of constant-time lookup or proven all-A-share throughput
is made. Further measurement, a separately designed composite index, and additional
safe single-call root/descriptor reuse are follow-up candidates outside Task5B and
have not been implemented. Raw atomic-write semantics, production defaults, and
public fail-closed reads were not relaxed to improve test runtime.
