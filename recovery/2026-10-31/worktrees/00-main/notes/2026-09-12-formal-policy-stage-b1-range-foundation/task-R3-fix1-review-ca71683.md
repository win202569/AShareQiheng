# R3 fix round 1 scoped review — ca71683

- **Lease renewal/failure can use a timestamp captured before writer-lock acquisition — ADDRESSED.** `ashare_pipeline/formal_range_store.py:448–451` now acquires the writer lock before sampling time, calculating renewal expiry, and validating ownership. Failure handling similarly samples time and validates the retry deadline inside the writer transaction at `:462–466`. The real SQLite lock regression at `tests/test_formal_range_store.py:19` covers expired renewal, expired terminal failure, and a retry deadline crossed while the lease remains live; it verifies task and attempt state remain unchanged.
- **Child completion fails to fence authenticated parent evidence beyond task rows — ADDRESSED.** `ashare_pipeline/formal_range_store.py:158–166` and `:260` propagate a private evidence accumulator through ancestor reconstruction. Each read appends detached task/snapshot/receipt/producer rows and raw/manifest bytes only after normalization, receipt validation, and its consistency recheck (`:271–275`). Before inserting child evidence, `persist()` rechecks every accumulated ancestor inside the writer transaction (`:490–511`). The shared checker at `:198–212` compares exact database rows, producer uniqueness, content-addressed paths, hashes, and bytes. Existing candidate-set checks remain in place for authenticated source corrections; graph reconstruction and parser callbacks remain outside the writer. The regression at `tests/test_formal_range_store.py:424` mutates the actual parent raw file during child parsing and verifies no child snapshot, receipt, or completed attempt survives.

## New Breakage in the Fix Diff

None identified. The extracted evidence checker preserves the previous read consistency checks, and the accumulator is optional and private; public interfaces and ordinary reads retain their existing behavior.

## Out-of-Scope Observations

None newly identified. The original Minor adversarial-test coverage finding remains deferred to final branch review as directed.

## Evidence Checked

- Reviewed the complete two-file fix diff from `e6c551d7e36819d38563511fd139ecdaa7a01e58` to `ca71683561c96dea1d1eb3f1e6e34624fb4e2284`.
- The appended report names both covering tests and includes terminal RED evidence: `2 tests`, `107.935s`, four expected assertion failures, exit `1`; and GREEN evidence: `2 tests`, `108.098s`, `OK`, exit `0`. The test implementations exercise the reported failure windows and assert persisted outcomes.
- No additional tests, outside-diff code inspections, Git commands, writes, or network operations were performed.
- Full Store + Source + StateStore compatibility remains pending. The interrupted previous run is partial diagnostic evidence and does not establish final acceptance.

## Verdict

**Fix round: All findings addressed, no new Critical/Important breakage.**
