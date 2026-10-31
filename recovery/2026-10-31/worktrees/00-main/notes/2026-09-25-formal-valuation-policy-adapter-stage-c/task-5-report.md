# Task 5 implementer report

Status: DONE_WITH_CONCERNS — implementation and focused verification are ready
for independent review; the controller intentionally withheld the producer-backed
23-member acceptance and the Step 6/7 long suites.

## Implemented

- Added capability-bound `PolicyAdjustedValuationPeerContext` and
  `PolicyAdjustedValuationScore` proofs.
- Added strict valuation eligibility, secondary-to-primary cohort fallback,
  average-rank Decimal percentiles, direction reversal, cohort/context/score
  hashes, and cross-batch rejection.
- Added batch-private one-time group index, one immutable rank map per cohort,
  context/score caches, actual boundary-validation counters, and noncanonical
  phased timing/status/cohort diagnostics bound to the owning repository.
- Added a default-preserving signed-fixture `cyclic_ids` option so one genuine
  23-member universe can cover secondary 20, secondary 19 to primary fallback,
  primary 19, pending affected/unaffected, and full-cohort reranking.
- Added ranking and integration acceptance modules. They share the expensive
  genuine batch in one Python process and close it at process exit.
- Added plan evidence without claiming the withheld long acceptance.

## TDD evidence

- Initial ranking import failed because the requested peer API did not exist.
- Rank-kernel tests failed because `_rank_valuation_values` did not exist.
- Signed fixture test failed because `cyclic_ids` did not exist.
- Peer identity and diagnostic tests failed on missing template/industry and
  phased diagnostic fields.
- Repository ownership test failed because a foreign repository could report
  another repository's batch.
- All failures above were repaired by the minimal corresponding production or
  fixture changes before continuing.

## Focused GREEN

- 7 small genuine ranking/diagnostic and kernel tests: PASS, 126.715s.
- final diagnostic/repository ownership pair: PASS, 61.810s.
- expanded 5-test Decimal/fixture/proof kernel: PASS, 4.397s.
- valuation adapter plus two selected C4 guard regressions: 15 PASS, 48.635s.
- `py_compile` and `git diff --check`: PASS (line-ending notices only).

## Files

- `ashare_pipeline/formal_valuation_engine.py`
- `tests/formal_valuation_fixtures.py` (necessary default-preserving fixture option)
- `tests/test_formal_valuation_ranking.py`
- `tests/test_formal_valuation_integration.py`
- `docs/superpowers/plans/2026-09-25-formal-valuation-policy-adapter-stage-c.md`

## Design decisions

- Ranking consumes only genuine published adjusted inputs and shares their
  publication capability; no detached rows, caller-provided peers, directions,
  percentiles, or eligibility flags are accepted.
- Cohort hashes bind batch, metric definition, adapter registry, direction,
  template, selected industry scope/ID, and ordered peer IDs.
- Diagnostics are excluded from canonical proof bytes, but are immutable,
  batch-hash bound, and rejected by a repository other than the batch owner.
- No G/M cap, Sc/B/R, eligibility decision, or pool field is produced.

## Remaining controller-owned verification

- Independent task review.
- One authorized producer-backed 23-member ranking/integration run. This is the
  same risk class as the known long C4 acceptance and was not started here.
- Step 6 and Step 7 long suites, diagnostic capture, and final root fresh run.
- Any review findings must return through the fix loop before completion.

No push, merge, Stage D work, production data, SQLite, WAL/SHM, or progress file
was included.

## Independent-review fix round 1

The initial task review was NOT CLEAN. The fix captures and guards the weakref
module, `ref`, and `ReferenceType`; proof verification now recloses exact batch,
context, input, registry, definition, direction, scope, ordered peers, hashes,
public proof identity and shared publication capability on every access.

Ranking is no longer lazy. The build prepares one group index, all focal
secondary/primary decisions, one Decimal rank map per unique formal cohort, and
the deterministic summary before hashing or publication. It then mints every
context and available score under the still-closed capability, validates the
entire graph, and opens once. Public ranking APIs only select and revalidate
prepared proofs.

The canonical batch summary now owns deterministic state, pending, eligible,
context, cohort, scope, below-20, sort and validation counts. Diagnostic queries
cross-check the private immutable cache against that summary; only timing stays
noncanonical.

RED evidence:

- weakref retargeting was accepted;
- query-before diagnostic showed zero group builds;
- derived-proof failure injection did not run during build;
- the synthetic precompute audit interface was absent.

GREEN evidence:

- weakref/precompute/diagnostic/independent-rebuild trio: 3 PASS, 129.456s;
- derived-proof atomic revocation: PASS, 292.131s;
- complete small ranking and kernel set: 14 PASS, 279.549s;
- adapter plus selected C4 signed/Decimal/publication guards: 17 PASS, 519.148s;
- compile and diff checks: PASS.

The independent 23-member batch+score rebuild comparison is authored but was
not run, per controller instruction. Step 6/7 remain pending.

## Controller long acceptance

The authorized shared 23-member ranking/integration acceptance completed with
21 tests passing in 5890.490s. The first genuine 23-member batch completed in
about 49 minutes in the later Step 6 run; the independent replay batch completed
in about 36 minutes. Full-cohort reranking, primary 19, secondary 20,
secondary-19-to-primary fallback, pending affected/unaffected handling, one sort
per cohort, and independent canonical batch/score replay all passed.

Step 6 completed normally at `c7215d8`: 88 tests passed in 12770.011s, with no
failures, errors, or skips and exit code 0. Its C4 20-member batch took about 61
minutes, the first ranking 23-member batch about 49 minutes, and the independent
replay batch about 36 minutes. The worktree remained clean.

Step 7 was requested as one 21-module command but is **INCOMPLETE / NOT PASS**.
It was stopped after the first error instead of spending additional hours on a
known-failing suite, so it has no valid unittest total, five-stage timing, or
final diagnostic cohort/sort/pending counts. The failing test was
`FormalPolicyIntegrationTests.test_complete_universe_all_templates_pending_and_veto`.
An isolated read-only rerun reproduced it in 344.763s with exit code 1:
`RangeBinding.require_current()` rejected a range binding lease as
`cross-thread, cross-binding, or stale`.

The trace shows a pre-existing policy/range identity conflict. Calendar requests
from distinct signed rule bindings intentionally share one request fingerprint
and one persisted task/snapshot, while that persisted task retains the first
binding hash. During a later rule's outer market lease, nested calendar lookup
reloads the shared task's original binding. The lease identity includes the
binding hash, so the original binding cannot authenticate as the later active
binding. This is not caused by Task C5: `237b907..c7215d8` has no changes to the
policy integration test, runtime fixture, policy market, range store, or range
contract, and the exact rejecting guard is already present at `237b907`.

### Step 7 retry after lease repair

After the independently reviewed lease repair at `7c02cf4`, the complete
21-module Step 7 command was restarted once from the beginning. The former
policy-integration lease failure passed, as did the rest of policy integration,
metric context, metric features, and the visible metric-engine tests. The run
was intentionally stopped at its first later failure, so this retry is also
**INCOMPLETE / NOT PASS** and has no valid suite total or final diagnostics.

The isolated failure is baseline test debt rather than a production regression:
`MetricBatchReviewTests.test_canonical_preparation_does_not_hold_the_writer_reservation`
failed at line 147 with `observed == 0` (`Ran 1 test in 0.676s`). Its profiler
at lines 129-130 looks only for frame `co_name == "_canonical"`, while the real
sealed closure in `formal_metric_engine.py` lines 82-84 is named `canonical`;
the public module binding is `_canonical`, but the function code object's
`co_name` and `__name__` are both `canonical`. The production canonicalization
did execute; the profiler simply did not observe it. The relevant production
and test files are identical between `237b907` and `7c02cf4`, and the closure
rename commit `a83668c` is already an ancestor of `237b907`. The minimal repair
is test-only: change that expected frame name from `_canonical` to `canonical`;
no production locking, performance, or writer-reservation semantics should be
changed.

### Final Step 7 acceptance

After the test-only observer correction in `7dd8139`, the original 21-module
Step 7 command was run once from the beginning and completed normally:

- 390 tests ran in 15190.396s (about 4h13m10s);
- failures: 0; errors: 0; skips: 0; exit code: 0;
- the C4 20-member batch completed in about 43 minutes;
- the first genuine ranking 23-member batch completed in about 47 minutes;
- the independent replay 23-member batch completed in about 34 minutes;
- the previously failing policy-integration lease case and metric canonical
  writer-reservation observer both passed in the same combined process.

The acceptance output and assertions verify 23 securities, 69 valuation rows,
one group-index build, one sort per unique cohort, secondary-20 selection,
secondary-19 fallback to a 20-member primary cohort, a primary 19-member
unscored cohort, pending-affected exclusion, pending-unaffected retention, and
independent canonical replay. The diagnostic API's verified phase set is
`input_registry_validation`, `identity_closure`, `row_adjustment`,
`peer_grouping`, `peer_sorting`, `final_verification`, and `publication`.
Exact wall-clock values for those internal phases and exact aggregate
`cohort_count`, `sort_count`, and pending-reason counts were not printed by the
unittest command and were not reconstructed after fixture teardown; no values
are inferred here.
