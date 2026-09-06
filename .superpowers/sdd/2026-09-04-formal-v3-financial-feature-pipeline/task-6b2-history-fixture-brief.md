# Task 6B2 follow-up — StateStore history-complete fixture alignment

## Authority and scope

The user selected V6 Option B: all formal feature bundles require the universal
non-cyclic four consecutive FY endpoints and latest eight comparable quarters.
This follow-up is test-only and may change **only**:

- `tests/test_state_store.py`

Do not change `StateStore`, feature construction, D1 history semantics, data,
SQLite artifacts, dependency files, or git state. Do not stage or commit.

## Proven root cause

Three `FormalV6PersistenceTests` currently fail in a clean process because the
shared bundle fixture supplies only FY2025. D1 correctly turns that bundle into
blocked/no-value/no-evidence. These tests instead intend to exercise a valid,
evidenced bundle against StateStore receipt and evidence validation:

- `test_bundle_live_receipt_and_append_only_metadata`
- `test_bundle_missing_evidence_and_missing_live_store_fail_closed`
- `test_bundle_rejects_signed_slot_unit_formula_and_foreign_evidence`

The tests must retain their assertions. Fix their setup, not production code
and not the assertion semantics.

## Required behavior

Add a narrow test helper in `FormalV6PersistenceTests` that constructs facts
with the same identity/provenance style as `install_fact`, comprising:

- FY 2022 and FY 2023;
- Q1/H1/Q3/FY for 2024 and 2025;
- Q1/H1 for 2026;

For the 2026-08-31 cutoff, this supplies four annual endpoints and the raw
cumulative prerequisites which derive the latest eight comparable quarters
(2024Q3 through 2026Q2). Preserve FY2025's revenue value as 100.0 so the
existing live receipt assertion stays meaningful.

Use this helper in exactly the three affected tests: insert every returned
fact where their StateStore evidence test requires durable facts; do **not**
insert them in the test whose point is missing evidence. Build each bundle
from the complete facts so it is not blocked, has evidence, and exposes the
existing StateStore validation paths. The foreign-security assertion must
continue to be based on a bundle whose evidence points to SZ000001.

## TDD evidence

The existing three named tests are the RED regression: before fixture repair
they independently fail with `None != 100.0` or missing `ValueError` because
the old single-FY fixture is history-blocked. Retain a focused command/output
in the report showing their red state before the patch and green state after.
Run at least the three named tests, then `tests.test_state_store` in full;
run `py_compile tests/test_state_store.py` and `git diff --check`. Do not
claim broader project success if unrelated baseline failures remain.
