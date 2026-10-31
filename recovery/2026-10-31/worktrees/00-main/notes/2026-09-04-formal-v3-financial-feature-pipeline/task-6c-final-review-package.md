# Task 6C final review package

## Review range and live files

- Context execution checkpoint: `ee85a76..9e6e992` (only
  `ashare_pipeline/formal_deep_worker.py` and `tests/test_formal_deep_worker.py`).
- Current uncommitted source/fixture delta: `ashare_pipeline/formal_sources.py`,
  `tests/test_formal_sources.py`, and `tests/test_formal_deep_worker.py`.

Use `git diff ee85a76..9e6e992` and the live `git diff` to inspect exact
changes.  No other tracked files are in scope.

## Binding requirements

Read these documents first:

- `task-6c-context-execution-brief.md`
- `task-6c-source-bootstrap-brief.md`
- `task-6c-calendar-fixture-repair-brief.md`
- the associated two implementer reports

Context task execution must freshly re-resolve and compare sealed requests;
use exact StateStore/verifier/runtime/snapshot boundaries; require exactly
one version-matched normalizer fact; fence every externally mutable stage and
never convert lost ownership to terminal/retry; dispatch statement → context
→ feature; keep V6 feature inputs context-free; use a closed result map.

The source extension only allows a validated explicit request exchange for
an otherwise globally unbound bootstrap calendar, still rejects security IDs,
preserves request/snapshot fingerprint identity, and adds no default or
mutable exchange state.  The fixture must exercise the actual signed
fixed-SZ calendar dispatch rather than bypass it.

## Evidence already collected

- Source task review: pass, no findings.
- Fixture task review: pass, no findings.
- Fresh root tests: `test_formal_sources` + `test_formal_deep_worker` = 122
  passed; `test_state_store` = 208 passed; context schema/repository = 49
  passed.
- `py_compile` of all four affected Python files and `git diff --check` pass.

This reviewer independently evaluates design, capability boundaries, recovery
and lease behavior, failure mappings, task/circuit ordering, cross-exchange
isolation, and test adequacy.  Report explicit overall verdict and only
concrete Critical/Important/Minor findings with file:line evidence.
