# Final six-Minor cleanup report

## Scope, base, and delivery

- Requirements authority: `final-minor-cleanup-brief.md`.
- Worktree/branch: `D:\Projects\AShareQiheng\.worktrees\seven-dimension-foundation`, `feature/seven-dimension-foundation`.
- Exact clean pre-edit base: `56b0343ce1781e5138fb5de66cb1db8e1e6c5596`.
- Final commit: `3ce5a903d9eafb2573c493960c0d8e180f33834e` (`fix final minor trust boundaries`).
- Python: `D:\Projects\AShareQiheng\.venv\Scripts\python.exe`; all test TEMP/TMP/TMPDIR paths were short worktree-local children of `.m6`.
- No subagents/reviewers, network, runtime/tracked data or DB, migration execution, formal scoring, stock-pool publication, or operational `120/114` acceptance were used.

## Root-cause verification and genuine RED

Production findings 1, 2, 5, and 6 received real production-path regressions before any production edit. Finding 3 was corrected as prose and finding 4 as test-quality work without fabricated RED.

Corrected exact RED command (an earlier command with a mistyped snapshot test class was discarded and is not used as evidence):

```powershell
$env:TEMP='D:\Projects\AShareQiheng\.worktrees\seven-dimension-foundation\.m6\red2'; $env:TMP=$env:TEMP; $env:TMPDIR=$env:TEMP; New-Item -ItemType Directory -Force -Path $env:TEMP | Out-Null; & 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m unittest tests.test_deep_worker.DeepWorkerTestCase.test_statement_job_renews_lease_during_local_normalization tests.test_deep_worker.DeepWorkerTestCase.test_feature_job_renews_lease_during_feature_construction tests.test_deep_worker.DeepWorkerTestCase.test_feature_heartbeat_loss_before_publish_prevents_later_side_effects tests.test_deep_worker.DeepWorkerTestCase.test_feature_keyboard_interrupt_propagates_without_retry_transition tests.test_deep_worker.DeepWorkerTestCase.test_feature_system_exit_propagates_without_retry_transition tests.test_deep_worker.DeepWorkerTestCase.test_feature_ordinary_exception_remains_a_retryable_failure tests.test_snapshot_repository.SnapshotRepositoryTestCase.test_read_verified_accepts_a_contained_absolute_legacy_path tests.test_snapshot_repository.SnapshotRepositoryTestCase.test_read_verified_rejects_an_absolute_legacy_path_outside_data_root tests.test_orchestrator.OrchestratorTestCase.test_zero_slot_specialized_templates_keep_imbalanced_facts_auditable_without_balance_marker
```

Retained exact output summary:

```text
FFFFF..FFFF
Ran 9 tests in 2.642s
FAILED (failures=9)
```

The nine expected failures were: statement heartbeat absent during local normalization; feature heartbeat absent during construction; feature lease loss not preventing later publish/transition; `KeyboardInterrupt` swallowed; `SystemExit` swallowed; outside-root absolute legacy snapshot accepted; and bank, insurance, and broker each advertising the inapplicable balance marker. The ordinary-`Exception` retry method and contained absolute-legacy method were the two passing positive controls.

Source inspection confirmed the causes: the statement heartbeat context ended immediately after fetch; feature execution had no heartbeat and caught `BaseException`; absolute legacy paths returned without containment; the builder applied the balance equation before considering zero-slot templates; migration prose named `snapshot`/`export_artifact`; and the forged-unclassified test used one broad multi-stage catch.

## Changed files and design

- `ashare_pipeline/deep_worker.py`: one heartbeat now spans each complete leased feature/statement lifecycle. Ownership guards run before later durable normalization, issue, file, DB, and transition effects. Periodic renewal and the final owned transition share a lock so a successful terminal transition cannot be misclassified as lease loss. Feature handlers catch only `Exception`; `KeyboardInterrupt` and `SystemExit` propagate after heartbeat cleanup without an ordinary failure item/transition.
- `ashare_pipeline/snapshot_repository.py`: resolved absolute legacy paths must remain under resolved `data_root`; outside-root, cross-drive, traversal, and symlink escapes fail closed while contained absolute and canonical relative paths remain valid.
- `ashare_pipeline/financial_features.py`: templates with no financial slots discard `balance_equation_mismatch`, including a caller-supplied marker; represented common templates retain shared recomputation. StateStore's evidence-empty forged-marker rejection remains unchanged.
- `tests/test_deep_worker.py`, `tests/test_snapshot_repository.py`, `tests/test_orchestrator.py`: add deterministic lifecycle, process-control, containment, and bank/insurance/broker regressions; pin forged-unclassified rejection to exact public-write, persistence, verified-read, and progress boundaries with cardinality checks.
- `docs/superpowers/plans/2026-08-29-seven-dimension-feature-foundation.md`: replace nonexistent v2 names with `source_snapshot` and `artifact`.
- `progress.md`: record only actual 9/329/407 verification counts and keep every operational/formal/pool gate closed.

During GREEN, one existing periodic-heartbeat fixture was armed only after the source entered because the new whole-lifecycle heartbeat can legitimately renew before the source call. A first full run then exposed a renewal/final-transition race; the final design serialized those operations. The exact failing E2E plus the nine focused methods subsequently ran 10/10 in 10.886s before broad verification resumed.

## GREEN and verification

Final focused proof used the RED command above plus the exact E2E race regression; result: `Ran 10 tests in 10.886s`, `OK`. The nine brief-focused methods within it were 9/9 GREEN.

Affected command:

```powershell
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m unittest tests.test_deep_worker tests.test_snapshot_repository tests.test_snapshot_store tests.test_financial_features tests.test_financial_formulas tests.test_feature_contract tests.test_state_store tests.test_orchestrator tests.test_feature_foundation_e2e
```

Final affected result: `Ran 329 tests in 436.738s`, `OK`, exit 0.

Complete offline command:

```powershell
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m unittest discover -s 'D:\Projects\AShareQiheng\.worktrees\seven-dimension-foundation\tests' -p 'test_*.py'
```

- Fresh full result under `.m6\f2`: `Ran 407 tests in 421.038s`, `OK`, exit 0.
- After path-specific staging, staged-tree full result under `.m6\s`: `Ran 407 tests in 775.884s`, `OK`, exit 0.
- Working/staged/commit `git diff --check` exited 0. The long wall times reflected host I/O slowness; progress continued and the successful runs completed normally.

## Scope and status checks

The commit contains exactly these eight paths:

```text
ashare_pipeline/deep_worker.py
ashare_pipeline/financial_features.py
ashare_pipeline/snapshot_repository.py
docs/superpowers/plans/2026-08-29-seven-dimension-feature-foundation.md
progress.md
tests/test_deep_worker.py
tests/test_orchestrator.py
tests/test_snapshot_repository.py
```

Tracked status was clean after commit. `.superpowers`, `.m6`, controller/temp directories, `data`, DBs, and unrelated files were not staged. `formal_score_ready=false`, `seven_dimension_ready=false`, formal scores remain unpublished, and both official pools remain closed and empty.

## Concerns

No concern remains within the authorized six-Minor scope. Live bounded network smoke, exact operational `120/114`, scoped re-review, and controller verification remain intentionally separate/unperformed gates.
