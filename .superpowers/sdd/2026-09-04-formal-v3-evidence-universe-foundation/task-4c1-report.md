# Task 4C1 report — formal raw snapshot receipt validation

## Base, commit, and scope

- Started from reviewed commit `f60705c` in `D:/Projects/AShareQiheng/.worktrees/formal-v3-implementation`.
- Implemented commit `b4fc8ff` (`feat: validate formal raw snapshot receipts`).
- The commit contains only `ashare_pipeline/formal_snapshot_store.py` and `tests/test_formal_snapshot_store.py`.
- No StateStore, schema/migration, queue, universe, legacy, data/SQLite, or runtime-artifact changes were made.

## Public helper contract

`FormalSnapshotStore.validate_stored_snapshot(fetch, stored, verification, *, expected_producing_task_id)` accepts exact `OfficialFetch`, `FormalStoredSnapshot`, and `EvidenceVerification` instances plus an explicitly expected nonempty task ID or `None` for bootstrap evidence. It returns a frozen `ValidatedFormalSnapshot` only after re-reading and validating the canonical manifest and raw bytes.

The returned projection is built from the validated manifest and resolved store paths. It contains source, dataset, canonical `request_json`, recomputed `request_fingerprint`, request identity fields, content/manifest hashes and paths, URL and all evidence timestamps, precision/effective-time evidence, refresh generation, producer, parser/mapping versions, and canonical `verification_json`. It does not return a caller-owned mapping or trust unvalidated caller metadata.

Validation fails closed on wrong input types/status/producer, non-lowercase or malformed SHA-256 values, any fetch/stored/manifest/verification/raw mismatch, missing/extra or type-confused manifest fields, duplicate-key or noncanonical/nonfinite JSON, hash-derived filename mismatch, relative/non-normalized/traversing/cross-directory paths, unsafe source/dataset components, root escape, and raw-byte tampering. Existing Task 2 byte-preserving writes remain readable.

## TDD evidence

### RED

1. Initial helper slice:
   - Command: `D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest -v tests.test_formal_snapshot_store`
   - Result: module import `ERROR` because `ValidatedFormalSnapshot` did not exist. This was the expected missing-feature failure before production implementation.
2. SHA hardening slice:
   - Command: `D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest -v tests.test_formal_snapshot_store.FormalSnapshotStoreTests.test_validate_stored_snapshot_rejects_non_lowercase_effective_evidence_hash`
   - Result: `Ran 1 test` — `FAILED (failures=1)` because a self-consistent uppercase effective-time evidence hash was accepted.

### GREEN

- SHA hardening test after the minimal check: `Ran 1 test` — `OK`.
- Required bounded suite:
  - Command: `D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest -v tests.test_formal_snapshot_store tests.test_formal_evidence`
  - Result: `Ran 28 tests in 0.474s` — `OK (skipped=3)`.
  - The three skips are only file-symlink escape cases because this Windows account lacks symlink creation privilege (`WinError 1314`); the tests execute on a symlink-capable host.
- `python -m py_compile ashare_pipeline\formal_snapshot_store.py tests\test_formal_snapshot_store.py`: exit 0.
- `git diff --check`: exit 0; Git emitted only the repository's LF-to-CRLF checkout warnings.

## Coverage and self-review

- Success for both bootstrap and task-produced snapshots, frozen/canonical return projection, and byte-preserving non-UTF-8 raw data.
- Exact input types, verified status, explicit nullable producer rules, and mismatch rejection.
- Stored/fetch/manifest/verification hash agreement, lowercase 64-hex enforcement, forged filenames, self-consistent manifest rehash attacks, and tampered raw bytes.
- Every request identity field and every persisted fetch/verification/generation/parser/mapping field is covered by rehashed mismatch cases.
- Duplicate/noncanonical manifest bytes, relative/traversing/different-directory paths, unsafe source/dataset components, and available symlink escape tests.
- Mutation review confirms each validation branch has an observable rejection test; no mock-based assertions were introduced.

## Limitations

- Direct symlink execution remains environment-dependent and was skipped under this Windows account; existing and new escape tests are present for symlink-capable CI.
- As recorded for Task 2, resolve-before-read checks do not eliminate every local concurrent-filesystem TOCTOU race. Descriptor-relative hardening remains outside this scoped helper slice.
- This helper validates evidence for later persistence but deliberately performs no StateStore write, lease check, receipt insert, task completion, or universe operation; those remain Task 4C2+ responsibilities.

## Review fix round 1

- Commit: `4b77b24` (`fix: harden formal snapshot validation`).
- Closed the verification-trust bypass: the helper now selects the project's closed canonical `SourcePolicy` from the formal request source and recomputes `EvidenceVerification` through `verify_official_fetch`. A public, handcrafted object cannot promote an HTTP/off-host/invalid-time fetch or invent verified reasons/effective time.
- Superseded by review fix round 2: the temporary fetch-derived structural binding was removed because it could not establish trusted calendar provenance.
- Added runtime validation for source/dataset types and components, ASCII SH/SZ/BJ security identity, ISO date period/date, exchange agreement, declared identity types, nonempty refresh generation, and ASCII parser/mapping identifiers. Numeric, empty, Unicode-identity, or path-like malformed values cannot appear in `ValidatedFormalSnapshot`.

### Fix-round TDD evidence

- RED command: two focused regressions for recomputed verification and invalid nested values.
- RED result: `Ran 2 tests` — `FAILED (failures=12)`; every adversarial subcase was accepted before the fix.
- GREEN focused result: `Ran 2 tests` — `OK`.
- Required bounded suite after the fix:
  - Command: `D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest -v tests.test_formal_snapshot_store tests.test_formal_evidence`
  - Result: `Ran 31 tests in 0.512s` — `OK (skipped=3)`.
- `python -m py_compile ashare_pipeline\formal_snapshot_store.py tests\test_formal_snapshot_store.py`: exit 0.
- `git diff --check`: exit 0 with only the repository's LF-to-CRLF checkout warnings.

## Review fix round 2

- Commit: `206afd5` (`fix: require trusted calendar binding`).
- Removed `_structural_calendar_binding`; no date-only binding or provenance field is synthesized from an `OfficialFetch`.
- Added the optional keyword-only `FormalSnapshotStore(..., calendar_binding_resolver=...)` capability. The resolver receives only the immutable `OfficialRequest`, preventing the raw store from handing it fetch-controlled effective hash/time as resolution inputs.
- A date-only write fails before creating raw or manifest files when no resolver is configured, resolution fails, or the returned binding is invalid/mismatched. Timestamp writes remain backward-compatible without a resolver.
- The exact resolver result must be a `VerifiedCalendarBinding` with nonempty snapshot/task identity, SH/SZ/BJ exchange, aware freeze timestamp, and lowercase 64-hex manifest/root/selector hashes. Its exchange and manifest must match the request and effective-time evidence hash.
- The same resolver and checks run for `write_verified`, `validate_stored_snapshot`, and `read_verified_raw`, so a changed/missing binding fails closed on later re-read.
- Earlier adversarial tests were strengthened: invalid source verification and malformed nested values are rejected before writes, then independently canonicalized forged manifests are also rejected by validation.

### Fix-round TDD evidence

- RED command: five focused date-only resolver/self-forgery/timestamp regressions.
- RED result: `Ran 5 tests` — `FAILED (failures=1, errors=3)`; the absent-resolver write was accepted and the resolver capability did not exist. The timestamp compatibility case was already green.
- GREEN focused result: `Ran 5 tests` — `OK`.
- Required bounded suite after final self-review:
  - Command: `D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest -v tests.test_formal_snapshot_store tests.test_formal_evidence`
  - Result: `Ran 36 tests in 0.650s` — `OK (skipped=3)`.
- `python -m py_compile ashare_pipeline\formal_snapshot_store.py tests\test_formal_snapshot_store.py`: exit 0.
- `git diff --check`: exit 0 with only the repository's LF-to-CRLF checkout warnings.
