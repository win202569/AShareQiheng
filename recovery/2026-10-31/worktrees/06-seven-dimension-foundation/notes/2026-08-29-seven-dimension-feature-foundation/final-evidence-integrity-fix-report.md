# Final evidence-integrity fix report

Commit: `dd1e3322dfa73c7c53ca7c0944544c895b781789`

## Scope and baseline

- Exact implementation baseline:
  `c799531f8a8a2173c5557db4d1d9afaf6ebd464e`.
- Scope remained limited to DB-backed feature evidence validation at
  persistence/progress, real-path regressions, and correcting tests that had
  persisted evidence-bearing bundles without their facts/snapshots.
- Public `FeatureBundle` parsing remains context-free. No migration, runtime
  data, network, scoring, pool, or deferred-Minor code was changed.

## Independent root-cause reproduction

Before writing tests or production code, an isolated worktree-local temporary
database was initialized and a production-built `general_nonfinancial` ready
bundle was passed directly to real `StateStore.put_feature_bundle()`.

Observed probe output:

```text
before 0 0
put ('b0b697a3b1f367d5519bb194fefc898adc6d0ba01f9c64b56b8c3128f2099f07', True)
after 1 363
```

The two `before` values are `source_snapshot` and `financial_fact`; the two
`after` values are `feature_set` and `feature_value`. The defect was therefore
not the public parser or canonical file/hash layer: `put_feature_bundle()`
entered its immediate transaction, checked only for an idempotent/conflicting
feature row, and inserted the header/values without resolving any evidence.
Progress later verified file/hash/parser/header consistency but did not resolve
evidence either.

## TDD RED evidence

StateStore RED command:

```powershell
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m unittest tests.test_state_store.StateStoreTestCase.test_put_feature_bundle_rejects_ready_bundle_when_evidence_database_is_empty tests.test_state_store.StateStoreTestCase.test_put_feature_bundle_rejects_missing_or_mismatched_evidence_rows tests.test_state_store.StateStoreTestCase.test_put_feature_bundle_rejects_raw_observed_fact_mismatches tests.test_state_store.StateStoreTestCase.test_put_feature_bundle_revalidates_evidence_before_idempotent_success -v
```

Observed before production changes:

- `Ran 4 tests in 1.286s`
- `FAILED (failures=15)`
- Empty DB, missing fact, missing snapshot, five public-evidence metadata
  mismatches, wrong security, raw fact metric/period/value/unit/mapping
  mismatches, and the idempotent existing-row bypass all failed because
  `ValueError` was not raised.

Real progress/file-boundary RED command:

```powershell
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m unittest tests.test_orchestrator.OrchestratorTestCase.test_general_ready_round_trips_through_verified_storage_and_progress tests.test_orchestrator.OrchestratorTestCase.test_progress_excludes_newest_bundle_after_evidence_snapshot_loss_without_fallback tests.test_deep_worker.DeepWorkerTestCase.test_evidence_rejection_removes_only_new_feature_file -v
```

Observed before production changes:

- `Ran 3 tests in 0.479s`
- `FAILED (failures=2)`
- The legitimate fact/snapshot-backed positive path was already green.
- After the newest bundle's source snapshot was deleted, progress still
  reported `financial_ready=1` instead of zero and did not add the expected
  unknown failure.
- The real `_write_and_store_feature_bundle` path did not reject an empty
  evidence database, so the new-file cleanup assertion could not be reached.

## Minimal implementation

### Shared validator

`StateStore.validate_feature_bundle_evidence()` and its transaction-aware
private implementation are the single DB-backed authority used by both
persistence and progress.

The validator:

1. walks every observed/derived `EvidenceRef`, deduplicating identical fact IDs
   and rejecting conflicting metadata for one ID;
2. resolves unique fact IDs with fixed-size (256-ID), set-based `IN` reads;
3. reconstructs every returned row through canonical
   `FinancialFact.from_record()`, rejecting missing, duplicate, or malformed
   rows;
4. resolves the facts' unique snapshot IDs with the same bounded set-based
   reads and rejects missing/duplicate/malformed identity rows;
5. compares fact ID resolution, bundle security, snapshot ID, source field,
   raw-row hash, announcement time, and effective time;
6. for descriptor-decidable raw observed values, additionally binds canonical
   dimension/key/status, metric, seven-period mapping, value, unit, active
   mapping/formula version, source field, and exactly one evidence fact.

Derived values are deliberately not recalculated. Their one-or-more operand
facts still receive full canonical row, snapshot, security, and shared evidence
metadata checks.

### Transaction boundary and idempotency

`put_feature_bundle()` calls the shared validator inside its existing
`BEGIN IMMEDIATE` transaction before querying an existing feature row. Thus a
missing/corrupt reference cannot insert a header/value and cannot escape through
the idempotent-success return. Any rejection rolls back before feature writes.

### Progress boundary

Progress retains the established verified bundle-file and DB-header checks,
then calls the same StateStore validator in a consistent read transaction.
Because the candidate security is marked seen before validation, an invalid
newest row adds at most one unknown failure and cannot fall back to an older
feature row. No feature/evidence values are exposed in status output.

### File cleanup and normal producer path

The existing deep-worker cleanup already keys deletion on `file_created` and
hash-verifies the target. A real rejection test proves a newly created orphan is
removed while a pre-existing byte-identical canonical file is preserved, so no
production cleanup change was needed.

Normal deep-worker order remains snapshot persistence, canonical fact
normalization/persistence, feature file publication, and transactional feature
persistence. Historical StateStore tests that had invented evidence IDs were
updated to seed a real snapshot and canonical fact first. The real positive ready
path now seeds all required statement snapshots and canonical facts before file
write, DB persistence, verified read, and progress.

## GREEN evidence

Focused RED commands after the implementation:

- Combined persistence/progress/deep-worker focus: `Ran 7 tests in 1.696s`,
  `OK`.
- Full StateStore module: `Ran 63 tests in 2.261s`, `OK`.
- Full deep-worker plus orchestrator modules: `Ran 178 tests in 63.559s`, `OK`.

Required related modules:

```powershell
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m unittest tests.test_state_store tests.test_deep_worker tests.test_orchestrator tests.test_feature_contract tests.test_financial_features tests.test_feature_foundation_e2e
```

- `Ran 258 tests in 65.915s`
- `OK`

Fresh full discovery:

```powershell
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m unittest discover -s tests
```

- `Ran 363 tests in 80.080s`
- `OK`

Fresh staged full discovery immediately before commit:

- `Ran 363 tests in 55.639s`
- `OK`

Diff verification before commit:

- `git diff --check`: exit 0, no whitespace errors.
- `git diff --cached --check`: exit 0, no whitespace errors.
- `git diff HEAD^ HEAD --check`: exit 0, no whitespace errors.
- Staged paths were exactly `ashare_pipeline/state_store.py`,
  `ashare_pipeline/orchestrator.py`, and the three focused test modules.

The suite's two existing argparse negative-path usage messages remain expected;
there were zero test failures or errors.

## Self-review and mutation check

- Removing the validator from the write transaction breaks the empty/missing/
  mismatch tests; moving it after the existing-row branch breaks the idempotent
  regression.
- Replacing set equality with a partial lookup breaks missing fact/snapshot
  cases. Skipping `FinancialFact.from_record()` breaks corrupted mapping/content
  detection.
- Dropping shared evidence metadata/security comparisons breaks the table-driven
  EvidenceRef and wrong-security cases.
- Dropping descriptor raw-value checks breaks metric/period/value/unit cases.
- Removing progress reuse breaks snapshot-loss/no-fallback and unknown-count
  assertions.
- Deleting unconditionally in the deep helper breaks the pre-existing file
  preservation assertion; never deleting breaks the new-orphan assertion.
- The positive real round-trip still counts exactly one ready bundle while
  `formal_score_ready`, `seven_dimension_ready`, waiting-price pool, and
  strong-attention pool remain closed.

## Concerns

None in the requested scope. The pre-existing untracked `.tmp-tests/` and
inaccessible `.tmp-root-check/` warning remain unrelated and unstaged.
