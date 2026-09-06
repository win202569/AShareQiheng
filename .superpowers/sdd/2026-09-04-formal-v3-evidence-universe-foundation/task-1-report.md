# Task 1 Report — Official Evidence Contract and Source Policy

## Implementation

Added `ashare_pipeline/formal_evidence.py` as a transport-free, immutable official-evidence boundary.  It provides:

- canonical request JSON and a SHA-256 request fingerprint;
- byte-preserving `OfficialFetch` values and content hashes;
- immutable verification, calendar-binding, and snapshot-reference types;
- closed HTTPS host policies for CNInfo, SSE, SZSE, BSE, and CSRC; and
- deterministic `verify_official_fetch` rejection for non-authoritative sources, non-HTTPS/off-list URLs, invalid SH/SZ/BJ identities, identity mismatches, empty/non-byte payloads, naive or malformed timestamps, impossible effective times, missing parser metadata, and invalid timestamp/date-only calendar combinations.

Verification returns a sorted tuple of reasons and never raises a third-party source into a verified result.  Date-only evidence needs a typed, structurally valid `VerifiedCalendarBinding` whose manifest and resolved exchange agree with the fetch.  Timestamp evidence rejects both a calendar binding and an effective-time evidence hash.  No network or legacy source adapter is imported.

## Files Changed

- `ashare_pipeline/formal_evidence.py` (new)
- `tests/test_formal_evidence.py` (new)

No legacy data or `data/status/pipeline_status.json` was read or changed.

## TDD Evidence

### Initial RED

The prescribed worktree-local command could not start because `.venv` is absent from this linked worktree:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_formal_evidence -v
```

It failed with `The term '.\.venv\Scripts\python.exe' is not recognized`.

Using the project-root virtual environment against the unchanged test-only addition produced the intended feature-missing RED:

```powershell
..\..\.venv\Scripts\python.exe -m unittest tests.test_formal_evidence -v
```

Result: `ModuleNotFoundError: No module named 'ashare_pipeline.formal_evidence'` (1 loader error; exit 1).

### Additional RED

During self-review, the focused missing-capture-time regression test exposed an edge case before its correction:

```powershell
..\..\.venv\Scripts\python.exe -m unittest tests.test_formal_evidence.FormalEvidenceTests.test_rejects_missing_required_capture_timestamp -v
```

Result: expected `rejected`, received `verified` (1 failure; exit 1).

### GREEN and Regression Results

```powershell
..\..\.venv\Scripts\python.exe -m unittest tests.test_formal_evidence -v
```

Result: 7 tests passed.

```powershell
..\..\.venv\Scripts\python.exe -m unittest tests.test_formal_evidence tests.test_sources -v
```

Result: 24 tests passed; existing `FetchBatch` behavior remained green.

```powershell
..\..\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

Result: exit 0.  The suite emits two expected argparse usage messages from its own CLI-boundary tests; it has no test failures or errors.

## Self-Review

- Confirmed all Task 1 public types use frozen dataclasses and raw bytes remain unmodified.
- Confirmed request hashing is calculated from canonical JSON on access, rather than accepting a caller-supplied fingerprint.
- Confirmed both third-party source identity and URL authority are independently checked; AkShare/BaoStock cannot become verified through an official policy.
- Confirmed date-only validation requires the full binding type, not a bare digest, and timestamp validation forbids calendar material.
- Ran `git diff --check`; no whitespace errors.  The only intended code/test changes are the two Task 1 files listed above.

## Concerns

None for the contract implementation.  The isolated worktree does not contain its own `.venv`; all test commands after the prescribed RED used the existing project-root virtual environment at `..\..\.venv`.

## Fix Round 1 — Closed Authority and ASCII Identity

### Findings Addressed

1. A caller-created `SourcePolicy("akshare", ...)` could previously verify an AkShare fetch when its URL was self-allowlisted.
2. The `\d{6}` security-ID expression accepted Unicode decimal digits.

### Files Changed

- `ashare_pipeline/formal_evidence.py`
- `tests/test_formal_evidence.py`

### RED

The two new behavioral tests ran against the pre-fix implementation:

```powershell
..\..\.venv\Scripts\python.exe -m unittest tests.test_formal_evidence.FormalEvidenceTests.test_custom_akshare_policy_cannot_verify_formal_evidence tests.test_formal_evidence.FormalEvidenceTests.test_rejects_unicode_decimal_digits_in_security_identity -v
```

Result: 2 failures (exit 1).  Each result was `verified` where the test required `rejected`.

### Fix

- Added the closed source-to-host authority registry.  A policy may only verify when its source and normalized host set exactly match a registered official policy; any custom AkShare/BaoStock policy is rejected with `source_not_authoritative`.
- Replaced `\d{6}` with `[0-9]{6}`, so only ASCII digits satisfy a formal security identifier.

### GREEN

```powershell
..\..\.venv\Scripts\python.exe -m unittest tests.test_formal_evidence.FormalEvidenceTests.test_custom_akshare_policy_cannot_verify_formal_evidence tests.test_formal_evidence.FormalEvidenceTests.test_rejects_unicode_decimal_digits_in_security_identity -v
```

Result: 2 tests passed.

```powershell
..\..\.venv\Scripts\python.exe -m unittest tests.test_formal_evidence tests.test_sources -v
```

Result: 26 tests passed.

### Self-Review

- The verifier, rather than constructor exceptions, returns an `EvidenceVerification` rejection for custom/non-authoritative policies.
- The registered source set excludes AkShare and BaoStock; a custom policy for either cannot acquire formal verified status.
- The Unicode-digit test supplies matching declared and requested IDs, so rejection proves the ASCII identity boundary rather than a declaration mismatch.
- No legacy source/data/status files changed.
