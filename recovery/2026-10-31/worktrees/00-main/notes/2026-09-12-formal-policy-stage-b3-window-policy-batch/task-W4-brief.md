# W4 task brief — five-template integration, recovery, and compatibility

Plan: `docs/superpowers/plans/2026-09-12-formal-policy-stage-b3-window-policy-batch.md`

BASE: `fd648b97125c7d381347605b820b6099ba39c4e4`
(`docs: record accepted W3 policy batch milestone`)

## Scope and ownership

Create exactly:

- `tests/test_formal_policy_integration.py`

Modify only when needed for genuine composite fixtures:

- `tests/formal_policy_runtime_fixtures.py`

Do not edit production code merely to make the integration tests convenient.
If a new test exposes a genuine defect, preserve the failing output and stop
with `NEEDS_CONTEXT`, naming the smallest production and test path expansion
required; the controller must approve that expansion before any fix. Do not
edit any other tracked path, dispatch subagents, write Git, install dependencies,
touch production/network data, or create final scores/pools.

## Required integration scenarios

Use genuine signed synthetic graphs, real temporary StateStore/range raw files,
and in-memory transports only. Every database and raw path must remain under a
fixture `TemporaryDirectory`; add a test assertion for this isolation. Reject any
attempt to contact real HTTP.

1. **Complete-universe, all-template policy batch.** Construct the frozen
   universe and all signed mappings before signing. Use at least five explicit
   canonical security IDs and cover all five templates:
   `general_nonfinancial`, `bank`, `broker`, `insurance`, `real_estate`. Also
   include a second security with the same template but non-cyclic industry,
   one security whose authenticated hard veto coexists with another missing
   input, and one frozen-universe member with unknown industry/template
   membership. Seven small securities are preferable so these identities do
   not accidentally collapse into one another. Assert exact frozen-universe
   order and count in the batch; pending and vetoed members remain present;
   unknown membership has no fabricated five-template decisions; the
   non-cyclic member does not demand the cyclic five-year series. Do not filter
   by score, eligibility, seven-dimension completeness, or prospective pool.

   The final wire must explicitly prove this stage did not create downstream
   products:

   ```python
   wire = fixture.build_policy_batch().to_dict()
   self.assertNotIn("strong_pool", wire)
   self.assertNotIn("wait_pool", wire)
   self.assertNotIn("final_scores", wire)
   for result in wire["results"]:
       self.assertNotIn("eligible", result)
       self.assertNotIn("final_score", result)
   ```

2. **Deterministic rebuild and append-only correction.** Populate genuine
   evidence, build twice without a new input generation, and assert identical
   `canonical_bytes()` and `batch_hash`. Then add a legitimate new source/task
   generation that corrects one observation and republish a complete genuine
   provider generation when that evidence class requires it. Build again and
   assert the new batch identity changes, prior raw bytes/snapshot rows still
   exist unchanged, and the prior selection/history proof cannot be consumed as
   current for the new attempt. Do not overwrite or delete the old generation.

3. **Crash/restart recovery without duplicate transport.** Use the real R4
   worker/store/source path and a countable in-memory transport. Interrupt after
   a page has been authenticated/persisted but before its successor task is
   durably enqueued, recreate `StateStore`, `FormalRangeStore`, and worker on the
   same temporary DB/raw root, then resume. The persisted page must be reverified
   and reused with no duplicate HTTP/transport call; the remaining work finishes.
   Compare the final canonical observation/result with an uninterrupted control
   run and assert historical rows/raw bytes remain present.

The integration file should use focused helpers rather than duplicating producer
logic. Fixture extensions must default to existing W3 behavior, accept only raw
inputs/generations (never caller-supplied stale/veto/eligible), and remain test
only.

## Test discipline

W4 is an integration-coverage task. Do not damage production code to manufacture
a RED. Run the new integration module first. If a scenario already passes, record
that as new coverage of existing behavior. If it reveals a real defect, capture
the exact RED before requesting scope expansion, then use RED → minimal fix →
GREEN after approval.

First command:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_integration -v
```

After the integration module is green and the implementation is frozen, run the
following complete affected regression exactly once, alone, without importing
the same TestCase twice:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_range_contract tests.test_formal_range_source tests.test_formal_range_store tests.test_formal_range_worker tests.test_formal_policy_values tests.test_formal_policy_financial tests.test_formal_policy_state tests.test_formal_policy_market tests.test_formal_policy_evaluator tests.test_formal_policy_repository tests.test_formal_policy_batch_guards tests.test_formal_policy_integration tests.test_formal_policy_contract tests.test_formal_policy_registry tests.test_formal_policy_registry_guards tests.test_formal_sources tests.test_formal_context_schema tests.test_formal_context_repository tests.test_formal_feature_repository tests.test_formal_feature_store tests.test_formal_metric_context tests.test_formal_metric_features tests.test_formal_metric_batch_guard tests.test_formal_metric_engine tests.test_state_store -v
```

Preserve incremental output/session evidence for the long run. Do not restart a
CPU-active run. Record exact test count, failures/errors/skips, elapsed time and
exit code. Also run `git diff --check`, enumerate every changed tracked path,
verify no V2–V6 DDL/schema alteration, and prove no data, SQLite, WAL/SHM,
outputs, or progress file entered the index. Do not run a production crawl,
scoring pass, or pool selection.

## Global constraints

Freeze remains `2026-08-31T07:00:00+00:00`; universe is SH/SZ/BJ ordinary A
shares. Five templates, seven dimensions, strict exclusions/evidence gates,
strong/wait maxima 20/50 and industry maxima 4/10 remain unchanged, but this
stage publishes no scores, levels, eligibility or pools. Preserve old V2–V6 DDL,
descriptors, single-day requests, snapshot behavior, V6 arithmetic and pre-policy
behavior. Missing authenticated domain evidence is pending; contract, integrity,
forgery, ambiguity and currentness failures revoke the batch. Retain every raw
snapshot, receipt, task attempt and historical generation.

## Report contract

Write the full report to
`.superpowers/sdd/2026-09-12-formal-policy-stage-b3-window-policy-batch/task-W4-report.md`.
Include scenario design, first integration outcome, any RED/fix/approval cycle,
both commands and complete terminal summaries, changed files with SHA-256,
isolation/network assertions, compatibility/scope audit, self-review, and
concerns. Return under 15 lines: Status, tests, changed paths, concerns, report.
Do not commit or push.
