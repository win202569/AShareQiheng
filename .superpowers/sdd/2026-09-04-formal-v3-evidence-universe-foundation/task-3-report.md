# Task 3 Report — Formal Time and Full-Universe Pure Contract

## Status and scope

Implemented the pure formal-time and full-universe contract. No legacy pipeline behavior or real data was changed, and `data/status/pipeline_status.json` was not touched. The final commit is scoped to the four planned Task 3 files.

## Files

- `ashare_pipeline/formal_time.py` — exact Shanghai close, caller-injected verified date-only effective close, fail-closed visibility, deterministic formal version ordering.
- `ashare_pipeline/formal_universe.py` — ASCII canonical identity, frozen domain records, status priority, deterministic extraction/audits/hashes, three-exchange snapshot construction, verified visible official-document ingress.
- `tests/test_formal_time.py` — time, precision, visibility, malformed-input, and version-order contract tests.
- `tests/test_formal_universe.py` — BJ/ASCII identity, status priority, recognized exclusions, content-sensitive audits, malformed-row rejection, three-exchange union, and ingress provenance tests.

## TDD evidence

### Initial RED

Command:

```powershell
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m unittest tests.test_formal_time tests.test_formal_universe -v
```

Output:

```text
test_formal_time (unittest.loader._FailedTest.test_formal_time) ... ERROR
test_formal_universe (unittest.loader._FailedTest.test_formal_universe) ... ERROR

ERROR: test_formal_time (unittest.loader._FailedTest.test_formal_time)
ModuleNotFoundError: No module named 'ashare_pipeline.formal_time'

ERROR: test_formal_universe (unittest.loader._FailedTest.test_formal_universe)
ModuleNotFoundError: No module named 'ashare_pipeline.formal_universe'

Ran 2 tests in 0.003s
FAILED (errors=2)
EXIT_CODE=1
```

This was the expected missing-production-module failure.

### Audit-driven RED

After the minimal implementation, two additional fail-closed expectations were added before their production changes.

Command:

```powershell
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m unittest tests.test_formal_time tests.test_formal_universe -v
```

Output:

```text
test_date_only_requires_verified_next_close_and_respects_freeze_visibility ... FAIL
test_formal_market_close_is_exactly_the_shanghai_close ... ok
test_timestamp_precision_uses_validated_timestamp_directly ... ok
test_version_order_is_published_desc_updated_desc_captured_desc_hash_asc ... ok
test_visibility_rejects_malformed_or_naive_times ... ok
test_bj_identity_uses_ascii_digits_and_status_priority ... ok
test_build_snapshot_requires_three_extractions_and_is_order_independent ... ok
test_extraction_fails_closed_for_bad_rows_and_zero_ordinary_a ... FAIL
test_ingestor_requires_three_verified_visible_exchange_scoped_documents ... ok
test_official_listing_extraction_keeps_ordinary_a_and_audits_excluded_row_content ... ok

AssertionError: ValueError not raised
AssertionError: ValueError not raised

Ran 10 tests in 0.003s
FAILED (failures=2)
EXIT_CODE=1
```

The missing behaviors were rejection of a claimed next close not exactly 15:00:00 Asia/Shanghai and rejection of a direct extraction whose snapshot exchange disagreed with its document exchange.

### Focused GREEN plus required legacy regression

Command:

```powershell
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m unittest tests.test_formal_time tests.test_formal_universe tests.test_curation -v
```

Output:

```text
test_date_only_requires_verified_next_close_and_respects_freeze_visibility ... ok
test_formal_market_close_is_exactly_the_shanghai_close ... ok
test_timestamp_precision_uses_validated_timestamp_directly ... ok
test_version_order_is_published_desc_updated_desc_captured_desc_hash_asc ... ok
test_visibility_rejects_malformed_or_naive_times ... ok
test_bj_identity_uses_ascii_digits_and_status_priority ... ok
test_build_snapshot_requires_three_extractions_and_is_order_independent ... ok
test_extraction_fails_closed_for_bad_rows_and_zero_ordinary_a ... ok
test_ingestor_requires_three_verified_visible_exchange_scoped_documents ... ok
test_official_listing_extraction_keeps_ordinary_a_and_audits_excluded_row_content ... ok
test_date_only_announcement_on_as_of_date_is_not_treated_as_future ... ok
test_final_cutoff_filters_september_revision_before_latest_version_dedupe ... ok
test_performance_preserves_leading_zero_filters_outside_and_deduplicates_stably ... ok
test_quality_gate_accepts_exactly_ninety_five_percent_completeness_after_cutoff ... ok
test_quality_gate_blocks_missing_and_unparseable_announcement_timestamps ... ok
test_quality_gate_is_partial_before_cutoff_and_flags_future_announcements ... ok
test_quality_gate_rejects_duplicate_codes_after_cutoff ... ok
test_quality_gate_rejects_duplicate_universe_codes_after_cutoff ... ok
test_quality_gate_requires_ninety_five_percent_disclosed_universe_coverage ... ok
test_universe_keeps_only_active_shenzhen_shanghai_a_shares_and_labels_st ... ok

Ran 20 tests in 0.004s
OK
EXIT_CODE=0
```

## Full-suite verification

The first observable complete run used the default Windows temp location and produced one unrelated environment error because an existing test called `os.path.relpath` between its C: temp directory and the D: repository:

```text
ValueError: path is on mount 'C:', start on mount 'D:'
Ran 507 tests in 69.497s
FAILED (errors=1, skipped=2)
```

The suite was then rerun hermetically with TEMP/TMP on the repository volume.

Command:

```powershell
$testTemp = 'D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\.test-tmp'
New-Item -ItemType Directory -Force -Path $testTemp | Out-Null
$env:TEMP = $testTemp
$env:TMP = $testTemp
$testModules = Get-ChildItem -File tests/test_*.py | Sort-Object Name | ForEach-Object { "tests.$($_.BaseName)" }
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m unittest $testModules
```

Output:

```text
.......................................................................................................................................................................................................................................ss........................usage: python.exe -m unittest deep [-h] [--online] [--limit LIMIT]
python.exe -m unittest deep: error: argument --limit: value must be between 1 and 360
usage: python.exe -m unittest deep [-h] [--online] [--limit LIMIT]
python.exe -m unittest deep: error: argument --limit: value must be between 1 and 360
..........................................................................................................................................................................................................................................................
----------------------------------------------------------------------
Ran 507 tests in 54.358s

OK (skipped=2)
EXIT_CODE=0
```

The two skips are the pre-existing Windows environment symlink-privilege skips. The CLI usage lines are expected output from existing argument-validation tests. The `.test-tmp` directory was confirmed to resolve under the designated worktree and removed after the run.

## Self-review

- Identity uses `^(?:SH|SZ|BJ)[0-9]{6}$`; Unicode decimal digits are rejected.
- Formal freeze ingress is exactly `2026-08-31T15:00:00+08:00`.
- `date_only` never guesses a weekday/session: callers must supply the verified next exchange close, which must be a timezone-aware 15:00:00 Shanghai instant strictly after publication-day 23:59:59.
- Timestamp precision is validated and retained directly; calendar material is rejected for that branch.
- Version order is published descending, non-null source-updated descending (null last), captured descending, hash ascending.
- Extraction has a closed type/status registry, rejects missing/unknown/malformed rows, duplicate IDs, prefix mismatches, parser/snapshot mismatches, and zero ordinary-A results.
- Non-A exclusions retain deterministic type counts plus hashes of canonical excluded row content; accepted raw JSON and row hashes are part of audit and universe hashes.
- Production ingress requires exactly one verified, global, matching-parser, matching-exchange, freeze-visible `OfficialSnapshotRef` for SH, SZ, and BJ.
- All three source audit identities feed the universe, source-audit, and frozen-input hashes; order is canonical.
- No imports or calls touch legacy curation, state, filesystem persistence, network, or pipeline status.

Mutation review: changing the close, guessing a date-only session, using `\d`, changing any status-priority branch, accepting unknown types/missing status/duplicates/wrong prefixes, dropping excluded content from hashes, allowing fewer than three exchanges, accepting future/global/parser-mismatched sources, changing ordering, or removing audit hashes causes at least one focused test to fail.

## Concerns

- The recognized listing-status vocabulary is deliberately closed to `listed`, `suspended`, and `delisted`; adding an official status requires an explicit registry change and tests rather than silent acceptance.
- The recognized non-A security-type vocabulary is likewise closed. This is intentional fail-closed behavior.
- `unittest discover` cannot import this repository's namespace-style `tests` directory, so the full run explicitly enumerates every `tests/test_*.py` module.

## Review fix round 1

### Findings addressed

1. Accepted `raw_row` values are now defensive deep copies represented by read-only `MappingProxyType` objects with JSON arrays recursively frozen as tuples. `FormalUniverseMember.__post_init__` also recomputes `raw_row_hash` and validates canonical identity, exchange, `ordinary_a` type, listing status, and raw-row identity before freezing.
2. `FormalFrozenUniverseInput.__post_init__` now rejects bare-member construction, requires sorted verified SH/SZ/BJ source evidence, validates each source/extraction/audit graph, reconstructs the exact sorted member union, and recomputes/verifies audit, universe, source-audit, and frozen-input hashes.
3. Source evidence is now restricted to the closed `official_security_listing` dataset; a verified snapshot for another dataset cannot enter a frozen universe.

### RED 1 — immutable accepted raw JSON

Command:

```powershell
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m unittest tests.test_formal_universe.FormalUniverseTests.test_accepted_raw_json_is_defensively_copied_and_deeply_immutable -v
```

Output:

```text
test_accepted_raw_json_is_defensively_copied_and_deeply_immutable ... FAIL
AssertionError: TypeError not raised
Ran 1 test in 0.001s
FAILED (failures=1)
EXIT_CODE=1
```

GREEN after recursive defensive freezing and row-hash verification:

```text
test_accepted_raw_json_is_defensively_copied_and_deeply_immutable ... ok
Ran 1 test in 0.001s
OK
EXIT_CODE=0
```

### RED 2 — frozen-input constructor and hash graph

Command:

```powershell
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m unittest tests.test_formal_universe.FormalUniverseTests.test_frozen_input_constructor_rejects_bare_members_and_tampered_hash_graph -v
```

Output:

```text
test_frozen_input_constructor_rejects_bare_members_and_tampered_hash_graph ... FAIL
AssertionError: ValueError not raised
Ran 1 test in 0.000s
FAILED (failures=1)
EXIT_CODE=1
```

GREEN after constructor invariant validation and canonical recomputation:

```text
test_frozen_input_constructor_rejects_bare_members_and_tampered_hash_graph ... ok
Ran 1 test in 0.002s
OK
EXIT_CODE=0
```

### RED 3 — closed listing dataset

Command:

```powershell
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m unittest tests.test_formal_universe.FormalUniverseTests.test_ingestor_rejects_verified_non_listing_dataset -v
```

Output:

```text
test_ingestor_rejects_verified_non_listing_dataset ... FAIL
AssertionError: ValueError not raised
Ran 1 test in 0.001s
FAILED (failures=1)
EXIT_CODE=1
```

GREEN after enforcing `official_security_listing`:

```text
test_ingestor_rejects_verified_non_listing_dataset ... ok
Ran 1 test in 0.001s
OK
EXIT_CODE=0
```

### Additional constructor mutation RED/GREEN

Self-review found that a directly replaced member could still declare `bond` or disagree with its raw-row identity. The test was written first:

```powershell
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m unittest tests.test_formal_universe.FormalUniverseTests.test_member_constructor_rejects_noncanonical_or_non_ordinary_identity -v
```

RED:

```text
test_member_constructor_rejects_noncanonical_or_non_ordinary_identity ... FAIL
AssertionError: ValueError not raised
Ran 1 test in 0.002s
FAILED (failures=1)
EXIT_CODE=1
```

GREEN after member-level canonical validation:

```text
test_member_constructor_rejects_noncanonical_or_non_ordinary_identity ... ok
Ran 1 test in 0.001s
OK
EXIT_CODE=0
```

### Focused Task 3 plus legacy curation GREEN

Command:

```powershell
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m unittest tests.test_formal_time tests.test_formal_universe tests.test_curation -v
```

Output:

```text
Ran 24 tests in 0.008s
OK
EXIT_CODE=0
```

### Full-suite GREEN

Command:

```powershell
$testTemp = 'D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\.test-tmp'
New-Item -ItemType Directory -Force -Path $testTemp | Out-Null
$env:TEMP = $testTemp
$env:TMP = $testTemp
$testModules = Get-ChildItem -File tests/test_*.py | Sort-Object Name | ForEach-Object { "tests.$($_.BaseName)" }
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m unittest $testModules
```

Output:

```text
.......................................................................................................................................................................................................................................ss........................usage: python.exe -m unittest deep [-h] [--online] [--limit LIMIT]
python.exe -m unittest deep: error: argument --limit: value must be between 1 and 360
usage: python.exe -m unittest deep [-h] [--online] [--limit LIMIT]
python.exe -m unittest deep: error: argument --limit: value must be between 1 and 360
..........................................................................................................................................................................................................................................................
----------------------------------------------------------------------
Ran 511 tests in 55.910s

OK (skipped=2)
EXIT_CODE=0
```

The skips and CLI usage lines are the same pre-existing Windows symlink/argument-validation behavior documented above. The task-local `.test-tmp` was resolved against the worktree path, removed recursively, and final status then contained only the two modified Task 3 files.

### Fix-round self-review

- Source mutation cannot affect accepted content because extraction copies before member construction.
- Member mutation is blocked at every nested mapping/list container; hashes remain stable because the stored representation is immutable.
- Member constructors cannot create non-ordinary, noncanonical, exchange-mismatched, row-mismatched, or hash-mismatched accepted members.
- Frozen-input direct construction requires the same three-source evidence graph as the ingestor and verifies rather than trusts caller-supplied hashes.
- Top-level member rows must be exactly the canonical sorted union of the three validated extractions, preventing a bare-member or partial-member bypass.
- Source audit fields are tied back to snapshot content/parser identity, accepted member contents/counts, row counts, and the audit hash.
- `annual_report` and every other non-listing dataset fail closed even when the snapshot otherwise claims verified status.
- No legacy module, real data, or pipeline-status file changed in this round.

### Final malformed-nested-source audit

After the first full run, the constructor audit was tightened once more so a runtime-malformed `FormalUniverseSourceEvidence.extraction` fails closed with `ValueError` rather than leaking `AttributeError`.

Focused RED command:

```powershell
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m unittest tests.test_formal_universe.FormalUniverseTests.test_frozen_input_constructor_rejects_bare_members_and_tampered_hash_graph -v
```

RED output:

```text
test_frozen_input_constructor_rejects_bare_members_and_tampered_hash_graph ... FAIL
AssertionError: AttributeError("'NoneType' object has no attribute 'exchange'") is not an instance of <class 'ValueError'>
Ran 1 test in 0.002s
FAILED (failures=1)
EXIT_CODE=1
```

GREEN output after explicit extraction/audit type validation:

```text
test_frozen_input_constructor_rejects_bare_members_and_tampered_hash_graph ... ok
Ran 1 test in 0.002s
OK
EXIT_CODE=0
```

Because production code changed after the earlier full run, the final verification was repeated with the same D:-local TEMP/TMP command. Final output:

```text
.......................................................................................................................................................................................................................................ss........................usage: python.exe -m unittest deep [-h] [--online] [--limit LIMIT]
python.exe -m unittest deep: error: argument --limit: value must be between 1 and 360
usage: python.exe -m unittest deep [-h] [--online] [--limit LIMIT]
python.exe -m unittest deep: error: argument --limit: value must be between 1 and 360
..........................................................................................................................................................................................................................................................
----------------------------------------------------------------------
Ran 511 tests in 60.304s

OK (skipped=2)
EXIT_CODE=0
```

The task-local `.test-tmp` was again path-validated and removed; status contained only the two intended Task 3 modifications.

## Review fix round 2 closeout

- Added a RED/GREEN behavioral regression that builds a complete, self-consistent forged source/extraction/audit/hash graph. RED proved the public constructor accepted it; GREEN proves `FormalFrozenUniverseInput` can only be created through the ingestor's internal validated factory while remaining the public typed output.
- Focused Task 3 plus legacy curation verification passed 25/25.
- Final full-suite verification was interrupted after root-cause investigation established a non-causal, pre-existing deep-worker timing flake: its two-second lease can enter `lease_lost` under severe suite resource contention, yielding `retryable_failed == 0`. The exact isolated test passed and Task 3 does not import or mutate the deep-worker path.
- The D:-local `.test-tmp` directory was resolved inside the designated worktree and cleaned. No legacy code, real data, or pipeline-status file changed.
