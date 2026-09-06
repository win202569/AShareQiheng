# V6 Task 2 report

Base: `352223b7d3f89891aef5f429a811dc6f29bcff43`

## RED

`D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_formal_financial_schema -v`

Expected failure: `ModuleNotFoundError: No module named 'ashare_pipeline.formal_financial_schema'`.

## GREEN

`D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_formal_financial_schema -v`

Result: 15 tests passed.

`D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_formal_financial_schema tests.test_financial_schema tests.test_financial_features -v`

Result: 88 tests passed.

`D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m py_compile ashare_pipeline\formal_financial_schema.py`

Result: passed. `git diff --check` passed before staging.

## Review-remediation RED/GREEN

Independent review reproduced four contract gaps in `97f6666`: Unicode decimal acceptance, a malformed recognizable duplicate `ITEM` not blocking a valid fact, equality-spoofed registry mutation, and non-serializable immutable issue details. It also found a deterministic audit-order gap while remediating the duplicate path.

RED:

`D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_formal_financial_schema.FormalFinancialSchemaTests.test_malformed_duplicate_row_indices_preserve_source_order -v`

Result: failed as expected with `row_indices` `(1, 0)` rather than source order `(0, 1)`.

GREEN:

`D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_formal_financial_schema -v`

Result: 18 tests passed.

`D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_formal_financial_schema tests.test_financial_schema tests.test_financial_features -v`

Result: 91 tests passed.

`D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m py_compile ashare_pipeline\formal_financial_schema.py`

Result: passed. Working-tree `git diff --check` passed. Only the two permitted Task 2 tracked files are changed; this report and the SDD ledger remain ignored and unstaged.

## Final mutation-seal remediation RED/GREEN

Fresh re-review found that Python equality treated a sealed `120.0` fact value and a hostile replacement `120` as equal. The old tuple/dict comparisons therefore allowed `to_dict()` to emit a record whose retained ID no longer matched its canonical scientific payload.

RED:

`D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_formal_financial_schema.FormalFinancialSchemaTests.test_fact_seal_rejects_type_equivalent_numeric_mutation -v`

Result: failed as expected because `object.__setattr__(fact, "value", int(fact.value))` did not raise during serialization.

GREEN:

The fact seal now fingerprints exact field kinds and IEEE-754 bytes for floats, so type-equivalent and signed-zero changes cannot normalize away.

`D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_formal_financial_schema.FormalFinancialSchemaTests.test_fact_seal_rejects_type_equivalent_numeric_mutation -v`

Result: passed.

`D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_formal_financial_schema -v`

Result: 19 tests passed.

`D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_formal_financial_schema tests.test_financial_schema tests.test_financial_features -v`

Result: 92 tests passed. Compilation and working-tree `git diff --check` passed.

## Canonical-deserialization and issue-seal remediation RED/GREEN

Fresh final review found three remaining boundaries: `from_dict` accepted noncanonical int/float/signed-zero wire values after normalization; two recognizable malformed rows for the same signed field did not report a duplicate conflict; and a low-level replacement of `FormalFactIssue` fields could still serialize. The reviewer also exposed that fact `to_dict()` returned a mappingproxy rather than a JSON-native detached record.

RED:

`D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_formal_financial_schema.FormalFinancialSchemaTests.test_all_malformed_duplicate_mapped_items_are_a_conflict_not_missing tests.test_formal_financial_schema.FormalFinancialSchemaTests.test_fact_serialization_recomputes_identity_and_rejects_direct_or_mutated_objects tests.test_formal_financial_schema.FormalFinancialSchemaTests.test_issue_serialization_rejects_low_level_field_mutation -v`

Result: all three failed as expected: all-malformed duplicates were recorded as missing, fact serialization was a mappingproxy and accepted noncanonical values, and a replaced issue detail serialized.

GREEN:

- `from_dict` now requires an exact type-sensitive serialization fingerprint to equal normalized fields; `to_dict()` returns a detached plain JSON-native dictionary.
- Any two or more recognizable occurrences, valid or malformed, are a deterministic duplicate conflict; one malformed occurrence retains the pre-existing missing-plus-invalid-shape behavior.
- `FormalFactIssue` now has a closure-private weak-reference seal over validated code/lineage and canonical deep-frozen details.

`D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_formal_financial_schema -v`

Result: 21 tests passed.

`D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_formal_financial_schema tests.test_financial_schema tests.test_financial_features -v`

Result: 94 tests passed. Compilation and working-tree `git diff --check` passed.

## Streaming malformed-row remediation RED/GREEN

Fresh final review found that `_snapshot_row` discarded safely recognizable
`ITEM` values when a custom `Mapping.items()` stream repeated a key or raised
after yielding part of a row.  The discarded candidate did not enter
`invalid_matches`, so a second valid occurrence could incorrectly create a
fact.

RED:

`D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_formal_financial_schema.FormalFinancialSchemaTests.test_duplicate_key_malformed_row_blocks_a_valid_mapped_fact tests.test_formal_financial_schema.FormalFinancialSchemaTests.test_malformed_item_stream_keeps_late_and_interrupted_candidates tests.test_formal_financial_schema.FormalFinancialSchemaTests.test_repeated_item_inside_one_malformed_row_is_a_conflict -v`

Result: both repeated-key variants and both partial-stream variants emitted a
fact; the single-row repeated-`ITEM` case omitted `duplicate_source_field`.

GREEN:

- `_snapshot_row` now consumes a finite item stream without retaining parser
  values from invalid rows, preserving every canonical exact `ITEM` candidate
  (including repeats) observed before, after, or during a malformed stream.
- Invalid rows contribute each preserved candidate occurrence to
  `invalid_matches`, so valid/malformed and within-row repeats become
  deterministic conflicts.  Issue `row_indices` remains a sorted set of
  physical source rows.
- Regressions cover repeated `ITEM`/`VALUE`, a target `ITEM` after a malformed
  key, interruption after an `ITEM` or otherwise complete row, and a single
  malformed row with a repeated `ITEM`.

`D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_formal_financial_schema -v`

Result: 24 tests passed.

`D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_formal_financial_schema tests.test_financial_schema tests.test_financial_features -v`

Result: 97 tests passed. Compilation and working-tree `git diff --check`
passed.  A separate post-fix adversarial audit found no fact-release or raw
parser-object retention path; the only noted finite-stream availability
boundary pre-existed and is outside the Task 2 contract.

## Exact pair, selection, and pre-row validation remediation RED/GREEN

A subsequent independent final review found three remaining fail-closed
boundaries: tuple/list pair subclasses were ignored rather than safely
snapshotted; public `SignedFinancialMappingRegistry.select()` compared query
objects with loose equality; and several hard extraction checks occurred only
after parser rows had been consumed.

RED:

`D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_formal_financial_schema.FormalFinancialSchemaTests.test_mapping_registry_select_requires_exact_query_values tests.test_formal_financial_schema.FormalFinancialSchemaTests.test_mapping_item_pair_subclasses_remain_exact_duplicate_occurrences -v`

Result: all six equality-spoofed binding selectors incorrectly succeeded, and
both tuple/list subclass rows allowed the adjacent valid fact to be emitted.

`D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_formal_financial_schema.FormalFinancialSchemaTests.test_unverified_registry_fails_before_document_rows_are_consumed -v`

Result: failed as expected because a forged registry raised only after the
probe row's `items()` had been called.

GREEN:

- `select()` now requires exact identifier strings for source/dataset/parser
  ID/version/mapping version and an exact SH/SZ/BJ exchange before comparing a
  signed binding.
- Tuple/list subtypes are read with `tuple.__len__/__getitem__` and
  `list.__len__/__getitem__`; regressions use subclasses whose normal
  `__len__`/`__getitem__` throw, proving only intrinsic storage is observed.
- Document metadata and raw-row snapshotting are separated.  Snapshot lineage,
  registry seal/binding, created time, identity, parser/publication lineage,
  and bootstrap checks now fail before any `row.items()` consumption.

`D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_formal_financial_schema -v`

Result: 28 tests passed.

`D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_formal_financial_schema tests.test_financial_schema tests.test_financial_features -v`

Result: 101 tests passed. Compilation and working-tree `git diff --check`
passed.  This remediation remains limited to the two permitted Task 2 files.
