# Task 11 suite6 temporary-root hang fix brief

## Context and root cause

Task 11 suite6 was stopped after about 7h56 with no completed tests. Dynamic
faulthandler sampling and a one-shot permission probe proved the run never
entered D1: it was looping in `tempfile.mkdtemp` from
`tests/test_formal_feature_store.py::project_temporary_directory`.

The helper hard-codes the checkout-local root
`.tmp/formal-feature-store-tests`. In the managed Codex worktree that existing
directory grants `CodexSandboxUsers` read/execute only. An actual child mkdir
returns errno 13 / WinError 5, while `os.access(parent, W_OK)` returns true.
Python 3.12 `tempfile` therefore retries new random names up to `TMP_MAX`
(2,147,483,647), producing a hot kernel loop instead of a prompt error.

Evidence is in:

- `D:/Projects/AShareQiheng/.superpowers/sdd/2026-09-28-formal-final-scoring-stage-d/task-11-stack-sampler-report.md`
- adjacent `task-11-stack-sampler.stderr.log`
- adjacent `task-11-stack-sampler.temp-probe.log`

The earlier `_scope`/`Path.resolve` performance hypothesis was disproved for
this run: the fixture had not reached that code. Do not change production code.

## Required change

Use strict TDD. Modify only `tests/test_formal_feature_store.py` plus the
ignored Task 11 report/progress files named below. Do not modify production
code, other tests, the plan, `.gitignore`, runner files, data, SQLite, WAL/SHM,
or evidence artifacts.

1. Add a minimal behavior regression test in a class that does not inherit the
   existing `FormalFeatureStoreTests.setUp`. It must independently require the
   helper's stable parent to be under the current OS/user temporary directory,
   then call the real helper, create/read/delete a small probe file, and verify
   the returned unique directory's parent is the declared stable root. The test
   must not inspect source text or assert on a mock.
2. Run only that new test against the current code first. It must fail quickly
   on the root-location assertion, before calling the currently hanging helper.
   Record the exact RED command/output.
3. Make the smallest implementation change to the test helper: place its stable
   project-specific root below `Path(tempfile.gettempdir()).resolve()`, preserving
   a dedicated AShareQiheng/formal-feature-store name and the existing unique
   `TemporaryDirectory(dir=...)` behavior. Do not silently fall back after a
   permission failure and do not hard-code a machine path.
4. Re-run the new test, then the complete `tests.test_formal_feature_store`
   module. Verify pristine success.
5. Run a short real smoke that constructs and closes
   `FinalScoringFixture(peer_count=3, purpose="test")`, with a bounded external
   timeout, proving fixture construction no longer loops. Do not run D1 or the
   full Task 11 suite in this fix step.
6. Run `git diff --check` and read-only syntax/AST validation for the changed
   test file.

## Safety and submission

- Keep all signature, evidence, owner, scoring, and production behavior
  unchanged.
- Preserve user-owned worktree changes. The only tracked file for this commit
  is `tests/test_formal_feature_store.py`.
- Append a concise diagnosis/TDD/test report to
  `C:/Users/Lenovo/.codex/worktrees/formal-final-stage-d/AShareQiheng/.superpowers/sdd/2026-09-28-formal-final-scoring-stage-d/task-11-report.md`
  and progress note to the sibling `progress.md`; both are ignored and must not
  be staged.
- Commit only the tracked test file with message
  `test: use writable formal feature temp root`.
- Do not push.
- Return status, commit SHA, exact files, RED/GREEN results, smoke result, and
  any concern. Do not spawn subagents.
