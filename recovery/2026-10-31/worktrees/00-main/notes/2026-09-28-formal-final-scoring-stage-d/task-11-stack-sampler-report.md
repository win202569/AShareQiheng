# Task 11 bounded dynamic diagnostic, 2026-10-04

Observed root cause of this reproduction: fixture creation loops in Windows
`tempfile.mkdtemp` after denied writes to the hardcoded worktree test temp root.
The count=20 reproduction never reached population or `run_preview`; these
samples do not confirm the proposed `_scope` / Path.resolve / inspect.signature
production hotspot.

## Evidence

- Worktree: `C:\Users\Lenovo\.codex\worktrees\formal-final-stage-d\AShareQiheng`.
- HEAD before and after: `b618191115b79a282de42cc6c27b124384cc5196`.
- `task-11-stack-sampler.stdout.log:5`: fixture:start at 0.297 seconds, PID 6372;
  no subsequent fixture milestone.
- `task-11-stack-sampler.stderr.log:3`: 30-second sample in tempfile.py:384,
  immediately inside the PermissionError retry condition.
- `task-11-stack-sampler.stderr.log:14`: 60-second sample in tempfile.py:380,
  immediately entering the PermissionError handler.
- Both stacks lead through tests/test_formal_feature_store.py:32,
  formal_metric_feature_fixtures.py:55, formal_policy_runtime_fixtures.py:167,
  formal_valuation_fixtures.py:42, formal_final_scoring_fixtures.py:133.
- `task-11-stack-sampler.temp-probe.log:1`: helper root is worktree
  `.tmp/formal-feature-store-tests`; tempfile.TMP_MAX is 2147483647.
- `task-11-stack-sampler.temp-probe.log:2`: one real mkdir attempt returned
  PermissionError, errno 13, WinError 5; parent_isdir=true and
  parent_access_W_OK=true. The diagnostic wrapper then raised RuntimeError
  to stop after this single observed failure, preserving the original error
  as its cause.
- Python runtime tempfile.py:375-386 loops through TMP_MAX candidates. On
  Windows, PermissionError is swallowed and retried if the parent passes
  isdir and access(W_OK). The probe observed every condition of that branch.

This explains the repeated directory operations, high kernel CPU, and lack
of data I/O in this sandbox. Attribution of the earlier 7h56 run remains an
inference because that already-terminated process was not stack-sampled;
its symptoms and test entry point match this newly reproduced failure.

## Process control and isolation

The diagnostic supervisor launched venv redirector PID 2832. The actual Python
child self-reported PID 6372 and PPID 2832. Get-Process independently confirmed
PID 6372, runtime path
`C:\Users\Lenovo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`,
and start time `2026-10-04 15:02:34` immediately before exact-PID termination.
At termination it had 65.03125 seconds CPU, 53.453125 seconds privileged CPU,
and 11.578125 seconds user CPU (82.2% of CPU time in kernel).

The process was stopped after two stack samples. Supervisor reported
elapsed_seconds=69.438, child_exit_code=4294967295 and
test_temp_root_removed=true. Get-Process subsequently found none of actual
child PID 6372, redirector PID 2832, or supervisor PID 27380. The diagnostic
supervisor's own TemporaryDirectory no longer exists. The fixture did not
create its SQLite database or data products; mkdir was denied first. The
single-attempt permission probe exited immediately.

All new diagnostic files are inside this ignored scratch directory.
`git check-ignore` confirms `.superpowers/sdd/.gitignore:1:*`. Production and
tests were not edited; worktree status matches the initial status. Nothing
was staged, committed, or pushed. No repository data warehouse or user data
was touched. No production fix was proposed or implemented.
