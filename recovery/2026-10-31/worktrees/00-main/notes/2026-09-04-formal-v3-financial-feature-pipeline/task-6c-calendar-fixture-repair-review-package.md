# Task 6C calendar-fixture repair review package

Base before fixture repair: the current worktree already contains the
source-bootstrap repair in `formal_sources.py` and `test_formal_sources.py`.

## Requirements

Read `task-6c-calendar-fixture-repair-brief.md` and
`task-6c-calendar-fixture-repair-report.md`.  The fixture repair must change
only `tests/test_formal_deep_worker.py`; it must preserve production
null-placeholder and parser-bootstrap exact checks.  It must configure a
valid signed fixed-SZ bootstrap calendar request, mark the parser document as
bootstrap, and prove actual adapter/worker/raw-snapshot/normalization/fact
execution with no calendar binding.

## Candidate test change

- calendar fixture config overrides only the request template to query its
  explicit `{exchange}`; it does not use null security/period placeholders;
- timestamp fixture document sets `bootstrap_calendar=True`;
- existing bootstrap worker test asserts the signed SZ request, exact URL,
  two parses (fetch plus raw replay), verified receipt/snapshot/raw lineage,
  a single persisted trading-calendar fact, and task-result lineage.

Read the live uncommitted diff for exact code.  Return spec-compliance and
task-quality verdicts, then concrete Critical/Important/Minor findings with
file:line references.  Treat only real acceptance blockers as gaps.
