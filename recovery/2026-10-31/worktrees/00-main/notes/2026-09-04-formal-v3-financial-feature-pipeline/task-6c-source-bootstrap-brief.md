# Task 6C extension — signed bootstrap-calendar exchange identity

## User-authorized scope extension

Modify only:

- `ashare_pipeline/formal_sources.py`
- `tests/test_formal_sources.py`

No network, data collection, SQLite/state artifacts, registry schema changes,
worker workarounds, staging, or commits by the implementer.

## Root cause and binding rule

`SignedContextRequestResolver` correctly mints a fixed-exchange calendar
request (for example `SZ`) so a normalized `trading_calendar` fact remains
exchange-isolated.  `FormalOfficialSourceAdapter._preflight` incorrectly
rejects every bootstrap-calendar request carrying an exchange.  Passing
`exchange=None` from the worker is forbidden: it changes the sealed request
fingerprint and violates fact/request exchange binding.

Keep a bootstrap source configuration globally unbound (`exchange_scope=None`)
and continue to forbid `security_id`.  Change only request preflight so that
an exact signed `OfficialRequest.exchange` is permitted for a bootstrap
calendar.  Do not introduce a config exchange scope, a worker special case,
or a default exchange.

## TDD requirements

Before production code is edited, add and run a focused RED test showing a
bootstrap trading-calendar request with `exchange="SZ"`, `security_id=None`
is rejected solely by the current preflight.  Record its command and expected
failure in the implementer report.

Then implement the smallest preflight change and add focused GREEN coverage:

1. bootstrap request with no security and `exchange="SZ"` can fetch and
   verify a timestamp calendar;
2. bootstrap request with no security and `exchange="SH"` independently
   succeeds under the same globally-unbound config;
3. a bootstrap request with `security_id` remains terminal before transport;
4. the config remains invalid if it carries `exchange_scope`; no default or
   cross-request mutable state is added.

The tests must exercise actual adapter behavior (not merely inspect a branch).
They must retain existing global/no-exchange bootstrap behavior unless a test
demonstrates that it is intentionally invalid.  The test file may reuse its
existing hermetic adapter/transport fixtures.  Preserve request/fetch
fingerprints so different exchanges do not share a snapshot identity.

## Verification

Run the narrow source tests first, then all `tests.test_formal_sources`, and
report exact commands/results.  Do not commit or stage.

## Ruling

The source adapter, not the sealed Context resolver or worker, owns the
correction: a signed request exchange is identity evidence, while a source
configuration exchange scope governs registry selection.  Cost if wrong:
allowing an unsigned/default exchange would blur calendar isolation; keeping
the old rejection leaves all date-only Context execution impossible.
