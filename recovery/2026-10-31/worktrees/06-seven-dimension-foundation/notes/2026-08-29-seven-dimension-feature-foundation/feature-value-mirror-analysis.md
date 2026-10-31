# Important 2 analysis — persisted `feature_value` exact-mirror validation

## Finding verdict

**CONFIRMED — Important, open in the current code.**

The current first-write transaction inserts the `feature_set` header and every `feature_value` child atomically, and the idempotent existing-row path already rejects an exact header/value mismatch. However, progress verifies only the canonical file, the DB header derived from that file, and the file bundle's canonical financial evidence. It does not compare any persisted `feature_value` row with the verified artifact. A later deletion, valid in-range update, or syntactically valid extra child row therefore remains counted as the latest ready feature set.

This violates the binding schema-v3 requirement that the feature package be represented in both `feature_set` and `feature_value` and written as the same package to file and DB (`docs/superpowers/specs/2026-08-29-seven-dimension-feature-foundation-design.md`, sections 5.3, 6, 9, and acceptance criteria 5–7). No network or runtime database access is required to establish the defect; it follows directly from the current read and comparison paths.

## Root cause and data flow

### Canonical producer and file write

1. `financial_features.build_feature_bundle()` produces a validated `FeatureBundle`.
2. `deep_worker._write_and_store_feature_bundle()` calls `write_feature_bundle()` and then `StateStore.put_feature_bundle()`.
3. `deep_worker.write_feature_bundle()` serializes `bundle.canonical_bytes()`, computes `bundle.bundle_hash()`, writes and fsyncs a temporary part, reparses it, proves byte/canonical/object equality, and installs it with no-clobber hard-link semantics. Reuse requires existing bytes to equal the new payload. The verified reader later rechecks path containment, SHA-256, duplicate JSON object keys, public contract parsing, canonical bytes, and canonical hash (`ashare_pipeline/deep_worker.py:686-803`).

The file is therefore a suitable expected representation for progress after `read_verified_feature_bundle()` returns.

### DB materialization and first insert

`StateStore.put_feature_bundle()` validates the bundle and caller hash, validates the project-relative feature path, and calls `StateStore._feature_bundle_content()` (`ashare_pipeline/state_store.py:901-913`, `:1144-1196`). `_feature_bundle_content()` deterministically produces:

- canonical `feature_set` content columns, including canonical JSON strings for dimension status, confidence inputs, blockers, and missing summaries; and
- one child mapping per feature value, including canonical `evidence_json`.

Inside one `BEGIN IMMEDIATE` transaction, the method validates canonical evidence, finds the unique feature-set identity, and either handles reuse or inserts the header and every child (`state_store.py:914-960`). A child insert failure rolls back both tables. This makes the honest first insert atomic, but after insertion there is no shared exact-mirror assertion; correctness currently depends on the insert loop continuing to match `_feature_bundle_content()`.

### Existing-row idempotency comparison

The exact existing comparator is `StateStore._stored_feature_content_matches()` (`state_store.py:1199-1220`). It:

1. compares every column in `_FEATURE_SET_CONTENT_COLUMNS` against the expected header;
2. selects all child content columns scoped by `feature_set_id`, ordered by `(dimension, feature_key, period_key)`;
3. sorts the expected child tuples by the same key; and
4. requires exact tuple-list equality.

`put_feature_bundle()` invokes this helper before returning idempotent success (`state_store.py:926-931`). Thus an idempotent re-put already detects missing, updated, and extra children, although there are no focused regressions for all three corruption shapes.

### Public feature-set reads

`get_feature_bundle_row()` and `latest_feature_set()` select only `feature_set` and return `_feature_set_public(row)` (`state_store.py:963-996`). `_feature_set_public()` only JSON-decodes four header summary columns (`state_store.py:1223-1232`); it never selects or reconstructs `feature_value`. This header-only API is used by workers for metadata/status and cleanup decisions. It is not itself a verified package read and should remain backward compatible, but callers must not treat it as proof that the child table mirrors the artifact.

### Progress and the precise discard

`build_deep_progress()` selects all in-scope `feature_set` rows ordered newest first and closes the DB connection immediately after `fetchall()` (`ashare_pipeline/orchestrator.py:1052-1059`). It marks each security as seen before validation, which correctly establishes newest-only/no-fallback behavior (`:1060-1066`). For that selected latest row it then:

1. converts the header with `_feature_set_public()`;
2. reads and verifies the canonical artifact using the stored path and hash;
3. calls `_feature_bundle_content(bundle, bundle.bundle_hash())` as `expected_header, _values`;
4. compares only `expected_header` with the selected `feature_set` row; and
5. calls public `validate_feature_bundle_evidence(bundle)`, which opens a separate DB transaction and validates the **file bundle's** evidence against `financial_fact` and `source_snapshot` (`orchestrator.py:1066-1081`; `state_store.py:796-899`).

The `_values` name at `orchestrator.py:1073` is the exact loss point: the complete expected child representation is computed and deliberately discarded. Evidence validation cannot compensate because it traverses values in the verified in-memory file bundle, not rows in `feature_value`. `_feature_set_public()` also supplies only header summaries. Consequently, child loss or corruption is invisible to progress.

There is also a consistency gap: feature-set selection, child/evidence reads, and counting do not share a DB read snapshot. The initial connection closes before verification, and public evidence validation opens a new transaction. A repair that merely adds a new separately connected child query would detect steady corruption but retain race windows between header, children, and evidence.

## Minimal shared validator API and transaction placement

### Location and API

The validator should live in `StateStore`, beside `_feature_bundle_content()` and the current comparator, because this module owns the schema columns, canonical DB JSON encoding, SQLite row types, and transaction lifecycle. Do not duplicate column lists or tuple construction in `orchestrator.py`.

Recommended private API:

```python
@staticmethod
def _validate_stored_feature_bundle_content(
    connection: sqlite3.Connection,
    feature_set_row: sqlite3.Row,
    bundle: FeatureBundle,
) -> None:
    """Raise ValueError unless feature_set + feature_value exactly mirror bundle."""
```

The helper should compute `expected_header, expected_values` internally with `_feature_bundle_content(bundle, bundle.bundle_hash())`. Callers should not pass precomputed headers/values, because doing so recreates the policy-splitting that caused progress to drop `_values`. It should raise a stable `ValueError` such as `"stored feature bundle content mismatch"`; callers need only fail closed, not expose the exact corrupted value in bounded status output.

Replace `_stored_feature_content_matches()` with this assertion helper, or retain a tiny boolean wrapper only if an existing external caller is discovered. Current repository usage is private and confined to `put_feature_bundle()`, so a direct rename/conversion is the smaller policy surface.

The expected hash must come from `bundle.bundle_hash()`, not independently trusted DB input. `put_feature_bundle()` already proves the caller-supplied hash equals it, and the verified file reader proves the returned bundle's bytes equal the DB hash before progress calls the validator.

### First insert

Keep `BEGIN IMMEDIATE`. After inserting the header and all children, reselect the inserted `feature_set` row by `id` and invoke `_validate_stored_feature_bundle_content(connection, inserted_row, bundle)` before commit. If the materializer, insert column order, trigger behavior, or future schema edit diverges, the same assertion used by readers fails and the transaction rolls back. This makes first insert, not just idempotent reuse, exercise the shared policy.

### Idempotent existing row

Within the same current `BEGIN IMMEDIATE` transaction, continue evidence validation first and then invoke `_validate_stored_feature_bundle_content(connection, existing, bundle)`. Return `(existing_id, False)` only after it succeeds. This preserves the current rule that missing canonical evidence cannot be bypassed through idempotency and retains writer exclusion throughout comparison.

### Progress

Use one explicit SQLite read transaction for feature-set selection, exact-mirror validation, and canonical evidence validation:

```python
with store._transaction() as connection:
    rows = connection.execute(latest_rows_query, parameters).fetchall()
    for row in rows:
        # preserve seen-before-try newest-only selection
        bundle = read_verified_feature_bundle(...)
        store._validate_stored_feature_bundle_content(connection, row, bundle)
        store._validate_feature_bundle_evidence(connection, bundle)
        # only then expose public header for aggregation
```

The loop must remain inside the transaction. Call the connection-aware private evidence validator, not public `validate_feature_bundle_evidence()`, so header rows, children, facts, and snapshot identities come from one SQLite snapshot. Reading the content-addressed file while that read transaction is open is acceptable: WAL mode allows writer commits, while the progress run sees one stable DB snapshot. It may retain WAL pages until the bounded progress scan completes; that operational risk is addressed below.

Build `public = _feature_set_public(row)` only after all validation succeeds, or ensure parsing failures remain inside the same `try`. No aggregate should consume DB summaries before the exact mirror passes.

### Newest-only, no fallback, and bounded unknowns

Preserve `seen_feature_securities.add(security_id)` **before** the validation `try`. If the newest row is invalid, increment `unknown_failures` once and continue to the next security; do not examine an older row for that security. All mirror defects for one selected candidate collapse into the existing single caught exception and therefore one bounded unknown, without leaking raw feature values or per-row diagnostics into progress.

Do not move `seen` after successful validation and do not query `LIMIT 1` separately per security unless ordering and tie-breakers remain byte-for-byte equivalent to the existing `(security_id, as_of_utc DESC, created_at DESC, id DESC)` policy.

## Exact comparison semantics

The validator should preserve and make explicit the current comparator's semantics:

1. **Header scope:** compare exactly all `_FEATURE_SET_CONTENT_COLUMNS`: security, report period, normalized as-of, candidate hash, template identity/version, contract version, input hash, status, coverage, canonical dimension/confidence/blocker JSON, bundle hash, and canonical missing summary JSON.
2. **Non-content metadata:** do not newly compare `id`, `created_at`, or `bundle_path` as artifact payload fields. They are not produced by `_feature_bundle_content()`. Progress separately authenticates `bundle_path` through safe-path verified reading and authenticates `bundle_hash` through both the file reader and header comparison. `put_feature_bundle()` retains path validation. Broadening path/ID semantics is unnecessary for this finding and could create compatibility policy outside the binding payload.
3. **Complete child projection:** compare exactly `_FEATURE_VALUE_CONTENT_COLUMNS` for every row scoped by the selected `feature_set_id`: dimension, feature key, period key, numeric value, unit, status, formula version, evidence JSON, and missing reason. The foreign key itself is established by query scope.
4. **Deterministic relational order:** order stored rows lexicographically by `(dimension, feature_key, period_key)` and sort expected tuples by the same triple. DB insertion order and the contract's presentation order are not semantic. Lexical ordering matches the existing primary-key/index prefix and current comparator.
5. **Duplicates:** the public contract rejects duplicate `(feature_key, period_key)` within a dimension; the DB primary key rejects duplicate `(feature_set_id, dimension, feature_key, period_key)`. The ordered tuple equality is still defensive: any distinct extra key is an extra row, and malformed duplicate-like variants in another dimension remain distinct and must be rejected unless present in the bundle.
6. **JSON representation:** compare stored JSON **text** with `_json()` output, not decoded semantic objects. `_json()` uses sorted keys, compact separators, UTF-8-compatible text, and `allow_nan=False`. This enforces the representation actually written by the canonical materializer and detects semantically equivalent but noncanonical rewrites of header or evidence JSON.
7. **Numbers and nulls:** use the SQLite-returned numeric/null values and expected canonical Python values exactly as the current tuple comparison does. All bundle numbers are finite and SQLite `REAL`-compatible. Do not introduce epsilon comparisons: a changed persisted value must not mirror a signed artifact merely because it is numerically close. Python equality between SQLite numeric values and the canonical finite value is the existing compatibility behavior.
8. **Missing row:** fewer ordered rows than expected, or a different key at any position, fails.
9. **Updated row:** any changed projected column fails, including status/value pairs that still satisfy schema checks, evidence JSON, formula version, or missing reason.
10. **Extra row:** any additional distinct key fails, even if syntactically valid and backed by real evidence.
11. **Bounded DB output:** fetch at most `len(expected_values) + 1` ordered rows. Equality detects missing/update cases, and the one extra slot proves there is at least one unexpected row without materializing an arbitrarily large corrupted child set. The expected length is already bounded by the verified artifact being processed. Do not add an arbitrary artifact-size policy in this focused repair: the binding contract supplies no compatible byte limit, and `read_verified_feature_bundle()` already necessarily reads the artifact to authenticate it.

The result is exact set equality under the schema's composite identity, with deterministic comparison order and canonical scalar/JSON representations.

## Real isolated RED test matrix

All progress regressions belong in `tests/test_orchestrator.py` and must cross real boundaries: build/install canonical facts and snapshots, write the canonical artifact with `write_feature_bundle()`, persist with `put_feature_bundle()`, mutate only the test-local SQLite child table, prove the file still verifies, then execute the real `status` path. Do not mock the validator or seed only an isolated header.

For each negative, persist an older valid ready bundle and a newer valid ready bundle for the same security, candidate set, report period, and contract (different `as_of_utc` and frozen snapshot tags/input hashes). Mutate only the newer `feature_set_id`. This makes `0 ready` rather than `1 ready` a direct no-fallback assertion.

| Case | Test-local mutation after valid persistence | Preconditions/non-vacuity | Expected fixed behavior | Current RED behavior |
|---|---|---|---|---|
| Positive exact match | None | Verified file equals built canonical bytes; DB contains expected child count | `feature_set_counts == {partial: 0, financial_ready: 1, blocked: 0}`; `unknown_failure_count == 0`; formal and seven-dimension gates false; both official pools remain zero | Already passes; existing `test_general_ready_round_trips_through_verified_storage_and_progress` can be retained/strengthened as the positive case |
| Deleted child | `DELETE` the newer `G / g.revenue.FY2021 / FY2021` row and assert affected row count is one | Newer file still verifies; older valid ready row remains present | all feature counts zero; templates/missing summaries exclude the candidate; unknown exactly one; no fallback to older; formal/seven-dimension gates false and pools zero | Counts the newer bundle ready and reports no mirror unknown |
| Updated child | For the same newer observed row, `UPDATE value = value + 1.0`; assert one row changed and schema-valid status/evidence remain | File's corresponding value is unchanged and file still verifies | same fail-closed counts/gates/no-fallback/one-unknown assertions | Counts ready because evidence validation uses the file's unmodified value, not the DB child |
| Extra child | `INSERT ... SELECT` a copy of the newer observed row under a unique syntactically valid key such as `g.unregistered_extra.FY2021`; assert child count increased by one | Insert satisfies dimension/status/value/evidence checks and does not alter header/file | same fail-closed counts/gates/no-fallback/one-unknown assertions | Counts ready because progress never enumerates children |

Use four separate test methods (or a helper that provisions a fresh database per case), not cumulative mutations in one database. Each negative must assert the mutation itself occurred. The ready bundle is preferable to the seven-row partial helper because it proves the defect can cross the advertised `financial_ready` count. Reuse the established `installed_ready_bundle()`, `write_candidate_documents()`, and real `run_command(..., "status")` setup patterns from the adjacent later-evidence-loss/no-fallback tests.

Add focused `tests/test_state_store.py` coverage for the shared policy:

- exact persisted content is accepted on first insert and idempotent reuse;
- after a test-local child delete/update/extra, an idempotent re-put raises the stable mirror-conflict `ValueError` and does not repair or partially rewrite the row;
- the new first-insert post-write assertion remains inside the transaction (the existing trigger rollback test continues to prove atomic rollback).

These StateStore cases may table-drive corruption shapes only if each shape provisions a fresh store/bundle. They are useful to ensure progress and idempotency do not drift to separate policies; the four real progress boundary cases remain required.

## Performance and concurrency risks

- **Query cost:** one ordered child query per selected candidate is at most 120 queries under the binding candidate set, with roughly the bundle's feature count per candidate. The composite primary key begins with the query/order columns, so lookup and order are indexed. `LIMIT expected + 1` bounds returned corrupt rows.
- **Long read transaction:** keeping file verification and DB evidence validation in one read transaction can delay WAL checkpoint truncation while progress processes up to 120 files. It does not block normal WAL writer commits. Keep work strictly to newest candidates, avoid sleeps/network calls, and retain existing batched evidence reads (`_EVIDENCE_QUERY_BATCH_SIZE = 256`). If later profiling shows checkpoint pressure, a per-candidate explicit read transaction plus an initial immutable selection snapshot could be designed, but it is more complex and must re-prove no-fallback/newest consistency; it is not the minimum safe repair.
- **Writer path:** `BEGIN IMMEDIATE` already serializes competing feature writes. Calling the exact validator before commit does not introduce a race and adds one indexed readback. It also converts future materialization drift into rollback instead of durable mismatch.
- **External DB corruption during progress:** one explicit read transaction yields a coherent pre- or post-corruption SQLite snapshot rather than mixing a header from one instant with children/evidence from another. A mutation after the read snapshot may be observed on the next status run; no cross-filesystem/SQLite atomic snapshot is possible, but content-addressed no-clobber files are immutable in the legitimate workflow.
- **Failure accounting:** one selected candidate produces at most one mirror/evidence unknown because validation is inside a single `try` and older rows remain suppressed. Do not count individual bad child rows; that would make status payloads unbounded and leak financial values.
- **JSON compatibility:** all existing v3 rows written by current `_feature_bundle_content()` use `_json()` and should pass exact text comparison. Hand-edited or externally seeded semantically equivalent JSON will now fail closed, which is intentional corruption detection rather than a migration break.

## Backward compatibility

- No schema migration or DDL/index change is needed.
- Keep `put_feature_bundle()` parameters and `(feature_set_id, created)` return semantics unchanged.
- Keep `get_feature_bundle_row()` and `latest_feature_set()` header-only result shapes unchanged; document internally that they are metadata reads, not package verification.
- Keep public `validate_feature_bundle_evidence(bundle)` for existing callers. Progress should use the connection-aware private implementation only to share its read snapshot.
- Existing canonical v3 data written by the current producer remains valid. Existing file paths, bundle hashes, IDs, and created timestamps are not reinterpreted.
- Preserve current newest ordering and seen-before-validation behavior exactly; this is both backward-compatible progress policy and the required fail-closed no-fallback rule.

## Recommended touched files

1. `ashare_pipeline/state_store.py`
   - replace/promote `_stored_feature_content_matches()` with the connection-aware raising exact-mirror validator;
   - bound the child query to expected count plus one;
   - call it on both existing-row reuse and the newly inserted row before transaction commit.
2. `ashare_pipeline/orchestrator.py`
   - keep feature selection and validation inside one explicit read transaction;
   - replace the header-only `expected_header, _values` block with the shared exact-mirror validator;
   - call `_validate_feature_bundle_evidence(connection, bundle)` on the same snapshot;
   - preserve newest-only seen placement and one-unknown accounting.
3. `tests/test_orchestrator.py`
   - add real isolated delete, update, and extra-child RED regressions with an older valid fallback candidate and exact progress/gate assertions;
   - retain or strengthen the existing real positive exact-match round trip.
4. `tests/test_state_store.py`
   - add focused shared-validator/idempotent corruption cases and retain atomic rollback coverage.

No change is required in `feature_contract.py`, `financial_features.py`, `deep_worker.py`, the schema DDL, or the binding design spec for this finding.
