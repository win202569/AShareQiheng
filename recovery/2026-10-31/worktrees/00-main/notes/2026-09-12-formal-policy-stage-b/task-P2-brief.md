# P2 — diagnose and repair the date-only calendar integration test

User explicitly authorized expanding to the single failing test, diagnosing first
and making necessary test-side repairs, with production rules unchanged.
BASE: 21746b2990b24c79b93521dc75f5d8e7e4a7f176.
Worktree: D:/Projects/AShareQiheng/.worktrees/formal-v3-implementation.
Python: D:/Projects/AShareQiheng/.venv/Scripts/python.exe.

## Ownership and limits

Only tracked editable file: tests/test_formal_context_repository.py.
Preserve all production files, P1's two files, other tests, user data, SQLite/WAL/SHM,
tmpj4zv9_fq, progress/history, and existing controller master-plan edit. Diagnostic
scripts/logs/report may be created under this task's .superpowers/sdd directory
using apply_patch for script/document edits; generated test output is retained.
Controller alone owns Git and master ledger. No subagents, network/crawl/scoring,
production signatures/DB changes, installs, deletion, merge, push or W1 development.
Do not bypass verification/ownership, mock acceptance, change production lease
policy, increase every fixture lease, remove assertions, skip the failed test,
or claim a passing rerun proves the previous cause.

## Existing evidence

Read task-P1-full-suite-triage.md and the terminal verification section of
task-P1-report.md in this directory. Previous sole full suite: 1403 tests,
4508.303s, FAILED(errors=1,skipped=4), exit1. It remains RED.
Failure: test_formal_context_repository.ContextIntegrationTests.
test_date_only_uses_calendar_provenance_without_recursive_self_lookup.
Stack test629->put236->state_store1980->formal_context_repository243/65
->state_store3156; ValueError formal snapshot task lease expired or ownership changed.
The failing test uses default lease_seconds=300; some neighboring date-only tests
pass3600. Owner predicate combines status/worker/expiry; generic error is NOT proof
of expiry. The P1 feature-contract owner is not consumed by this context test.

## Stage 1 — focused diagnosis, no tracked edits yet

Run this single existing test once with temporary forwarding instrumentation.
Keep the original implementation and real clock/validation decisions unchanged.
At final normalization and persistence ownership gates, record exact synthetic
task row (id, kind, status, lease_worker, lease_expires_at, refresh_generation),
expected worker/generation, sampled original now, phase/caller, elapsed wall time,
and the original gate result/error. Use the same connection for read-only row
inspection, and always call the original gate unchanged; do not consume/replace
its clock sample in a way that changes behavior. Avoid expensive full stack walks
at every nested call; narrowly scope diagnostic output to the target context task.
Capture complete output incrementally, unbuffered and WITHOUT PTY/Start-Transcript
to avoid prior ANSI/capture gaps. One test workload at a time; no competing profile.
Record session, launcher/computing PID if observable, start, command and terminal
exit/count. Do not restart a still-running test because it is slow.

Return a diagnosis checkpoint before implementation: what was actually reproduced,
which predicate failed, successful earlier gate vs failing gate, what remains
unknown, and a smallest test-only repair proposal. If the isolated test passes,
do not invent RED or assert the historical failure was proved; report measured
headroom and propose minimal next discrimination. Controller resumes Stage2 after
reviewing evidence. This is an internal evidence gate, not another user approval.

## Stage 2 — on controller resume

Implement only an evidence-supported minimal test-side correction. Preserve every
existing date-only provenance, no-self-recursion, wrong selector/root/mutation
assertion and all production ownership checks. Keep duration changes local to this
test if that is justified; if controlled test scheduling is selected, ensure expiry
tests still exercise actual production rejection and no patched clock leaks.
Demonstrate focused RED/diagnosis then GREEN with actual complete output, and cover
neighboring date-only provenance plus relevant owner-expiry/rollback regressions.
No meta-test that only asserts source text or a constant. No unrelated refactors.
Run the complete owned module once for compatibility; freeze for controller
checkpoint and independent task review before any expensive full-project rerun.
After clean review and controller resume, run the existing full-project command
once: python -m unittest discover -s tests -p "test_*.py" -v. Save full incremental
plain output, exact terminal counts/exit/skips/warnings and fresh hashes. The old
failed1403 is not relabeled GREEN. No production or whole-Stage-B acceptance claim.

## Report

task-P2-report.md in this directory, current checkpoint first. Full original
diagnostic/RED/GREEN outputs in named task-P2-*.log artifacts; distinguish actual
wall clock from any later controlled reproducer. Describe changed file, root cause
with uncertainty, covering tests, self-review, hashes and remaining concerns.
Return short status and artifact paths. Never claim done from a partial run.
