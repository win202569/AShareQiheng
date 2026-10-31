**Invalid or forged requests leak `ValueError` before the typed-error boundary — ADDRESSED.** `ashare_pipeline/formal_range_source.py:975–978` now converts `ValueError` from `request_record(request).previous` into `FormalTerminalSourceError`, preserving the original exception as its cause. The conversion covers only request authentication. Parent verification remains outside it at `:979–980`, so parent-evidence integrity failures retain their `ValueError` behavior. Valid execution order remains source authentication → request authentication → parent verification → request snapshot → configuration checks → transport.

### New Breakage in the Fix Diff

None identified. The complete fix contains only this narrow exception conversion; it neither suppresses failures nor changes successful execution.

### Out-of-Scope Observations

None newly identified. The original Minor adversarial-test coverage item remains deferred to final branch review.

### Evidence Checked

- Reviewed the brief, latest fix-round report, and complete fix package from `8385ff6529cd27749fd9f4cc1a36cbd58dd397f3` to `3c3b3c12a6a5f8f6c98d054131e4a097cad710c4`.
- Fresh RED evidence reproduces all five exception leaks in two existing Source tests: `2 tests`, `14.954s`, `FAILED (errors=5)`, exit `1`.
- Scoped GREEN evidence covers the complete Source module and `test_parent_correction_during_fetch_rejects_standalone_continuation`: `32 tests`, `686.364s`, `OK`, exit `0`, with individual results and no test warnings recorded.
- Ran no additional tests or mutations. The earlier full 272-test run remains **FAILED**; this scoped GREEN does not establish full-project acceptance.

### Verdict

**Fix round: All findings addressed, no new Critical/Important breakage.**
