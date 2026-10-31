# Binding wire assembly performance fix

Baseline: `a3984ed9035c1f346c47ae0d3c41ae7845125c25`.

Scope: only `formal_policy_market.select_calendar` and `select` reuse the one
immutable binding view obtained during each successful wire assembly. No view
or validity conclusion is cached across functions, recursive rechecks, journal
phases, or builds.

## TDD evidence

- RED command: `python -m unittest tests.test_formal_policy_market.MarketRepositoryTests.test_successful_wire_assembly_reads_each_owned_binding_once -v`
- RED observed each `select_calendar` assembly calling `_read_binding` 6 times;
  the preceding aggregate probe observed `select` calling it 7 times.
- GREEN: the same real successful calendar and market path observes 1 call in
  every individual `select_calendar` and `select` assembly. After replacing the
  global profiler with Python 3.12 local `sys.monitoring` events, it passed in
  45.739 seconds.

## Regression evidence

- Four source/configuration mutation cases passed in 194.485 seconds: stale
  proof recheck despite method shadowing, present market raw-byte replacement,
  source raw-byte replacement without a database version change, and signed
  source configuration replacement.
- Eleven focused policy/market behavior cases passed in 238.365 seconds.
- Full `tests.test_formal_policy_market` passed 26/26 in 1109.342 seconds.
- No 20-member valuation module was run.

## Low-overhead three-member measurement

The probe used the same 0.1-second daemon sampler of `sys._current_frames()` as
the baseline diagnosis, plus Python 3.12 local `PY_START` monitoring restricted
to the two exact code objects for counts. It did not use global `sys.setprofile`.

- First timing-only run: 223.191 seconds, so it did not show a stable whole-build
  improvement under current machine noise.
- Counted run: 209.692 seconds versus the 211.926-second diagnostic baseline.
- Counted-run boundaries: metric preparation 24.370s; metric checkpoint 6.072s;
  policy preparation segments 134.303s total; policy checkpoints 27.703s total;
  final checkpoint 16.656s.
- Current whole-build counts: `_read_binding` 1425 and
  `_capture_graph_snapshot` 1577.

The focused real selection improved from 108.938 seconds in RED to 45.739
seconds with low-overhead monitoring, but the two full build timings bracket the
baseline. Therefore this report does not claim a stable whole-build speedup.
The remaining dominant repeated work is outside this patch: repeated
`_binding_identity` reads across mint/owner seal/ticket issuance/scope/recheck,
plus other current-binding checks that capture the signed graph. Those are only
recorded as a possible later Phase 1 investigation; they were not changed here.
