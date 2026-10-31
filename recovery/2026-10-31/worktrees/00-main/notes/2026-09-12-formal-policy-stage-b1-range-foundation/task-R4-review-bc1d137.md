### Spec Compliance

- ❌ Issues found: retryable and blocked acquisition paths do not consistently reauthenticate callback-sensitive authority before the worker records an operational failure. See Important finding below.
- ✅ The four-file scope matches the approved whitelist. Single-task execution, signed attempt limits, bounded retry scheduling, receipt-first pagination, and exact-generation recovery are implemented in `ashare_pipeline/formal_range_worker.py:48–96`.
- ⚠️ Full 97-test compatibility remains explicitly PENDING under the controller’s execution-order ruling. This review is not R4 acceptance.
- ⚠️ Unchanged policy rules, historical data preservation, and whole-branch compatibility cannot be established from this four-file package.

### Strengths

- `ashare_pipeline/formal_range_worker.py:69–80`: persistence and continuation remain outside the operational exception handlers, preserving hard failures from those operations.
- `ashare_pipeline/formal_range_worker.py:64–66`: attempts exceeding the signed budget terminate before transport, including attempts consumed by expired leases.
- `ashare_pipeline/formal_range_worker.py:84–96`: recovery authenticates the exact request/generation through the store, derives successors from current observations, and bounds traversal using signed `max_pages`.
- `ashare_pipeline/formal_range_source.py:342–351`: the binding accessor captures the original request validator and exposes authenticated read access without minting authority.
- `ashare_pipeline/formal_range_source.py:961–964,1035–1044`: parser-originated acquisition exceptions are stripped of live-only classification during replay; terminal response failures recheck source/request authority again after parent callbacks.

### Issues

#### Critical (Must Fix)

- None identified.

#### Important (Should Fix)

- **Callback integrity failures can still become ordinary retry diagnostics.** `ashare_pipeline/formal_range_worker.py:71–74`, together with `ashare_pipeline/formal_range_source.py:1018–1027,1035–1044`: the new authority rechecks run only when response handling raises `FormalTerminalSourceError`. A transport callback can change the live source’s `_binding` and then raise `TimeoutError`; transport handling converts that exception into `FormalRetryableSourceError` before reaching `source_record(self)`, and the worker records `retryable_failed`. Similarly, a callback can invalidate the original request or parent and return a blocked/retryable response; response classification exits before their rechecks. `ashare_pipeline/formal_range_store.py:456–470` confirms `fail()` checks store/lease ownership but does not authenticate those original acquisition dependencies. This violates the required separation between callback-time integrity failures and operational acquisition failures. Recheck original source, request/binding, and current parent authority before propagating any retryable/blocked acquisition classification, including transport exceptions; recheck source/request after parent callbacks. Keep those authentication failures outside operational conversion and preserve lease fencing. Add focused regressions for callback mutation followed by timeout and blocked response.

#### Minor (Nice to Have)

- None identified.

### Assessment

**Task quality:** Needs fixes.

**Reasoning:** The worker is compact and its persistence/recovery boundaries are clear, but the operational exception boundary remains incomplete for retryable and blocked failures. The terminal-path safeguards do not protect all paths now consumed by the worker.

### Checks and Cannot-Verify Items

- Read the binding brief, reviewer template, implementation report, and complete four-file review package. Initial combined tool output was truncated; retrieved omitted package/report sections to complete the review.
- Read the complete `_parse` and `fetch_verified` functions because their diff hunks cut off required function context.
- Focused authority check: inspected `request_record()` at `ashare_pipeline/formal_range_source.py:214–243` to establish what the new accessor authenticates.
- Focused failure-recording check: inspected `FormalRangeStore.fail()` at `ashare_pipeline/formal_range_store.py:456–470` to determine whether it compensates for skipped acquisition authentication; it does not.
- Focused malformed-response check: inspected response helper aliases and `ashare_pipeline/formal_sources.py:227–250,1493–1540`; malformed URL validation already becomes a terminal source error, so no separate finding.
- Read `task-R4-focused-final.log`: three named tests completed successfully in 521.178 seconds with `OK` and no visible warnings. Other historical run results remain report claims, not independently inspected evidence.
- No tests, suites, Git writes, file mutations, or subagents were launched. The new failure-path finding is based on static control-flow evidence; it has not been dynamically reproduced in this review.
- Default real-time lease adequacy and production throughput remain unverified; fixed-clock tests do not establish either.
