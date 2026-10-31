# Task 6C — date-only bootstrap fixture repair

## Scope

Modify only `tests/test_formal_deep_worker.py`.  Do not modify production
code, source tests, Context schema/repository, StateStore, data, SQLite,
network, staging, or commits.

## Confirmed root cause

The user-authorized source preflight repair now allows the sealed fixed-SZ
calendar request.  The worker's `date_only_context_fixture()` still creates
a bootstrap calendar source config by inheriting the generic fixture request
template with `{period_or_date}` and `{security_id}` placeholders even though
the signed calendar request has both values null.  The adapter correctly
fails before transport.  Once that template is corrected in-memory, the
fixture document then correctly fails because it lacks
`bootstrap_calendar=True` while its signed config requires it.

The correct production contract is unchanged: null placeholders must remain
rejected and the parser bootstrap flag must match the signed config.

## Required test-first repair

The existing test
`FormalContextWorkerExecutionTests.test_context_bootstrap_calendar_executes_signed_exchange_request`
is the RED reproduction.  Run it before editing and record its terminal
failure.  Then make the smallest fixture-only changes:

1. give the bootstrap-calendar fixture a valid request template that binds
   its explicit exchange but not null security/period values;
2. mark its timestamp fixture document `bootstrap_calendar=True`.

Strengthen the same end-to-end test enough to prove the signed `SZ` request
is actually transported, parsed, persisted, and normalized into exactly one
verified `trading_calendar` Context fact, without a date-only binding.

Run the repaired bootstrap test and the existing
`test_context_date_only_dependent_requires_exact_binding_and_raw_bridge`,
then the full `tests.test_formal_deep_worker` module.  No weakening or
skipping of the source adapter's null-placeholder or parser-bootstrap checks.

## Ruling

This is a fixture defect, not a worker or source-runtime defect.  Cost if
wrong: altering production checks would accept malformed signed source work;
an under-specified fixture would continue to mask the calendar dispatch path.
