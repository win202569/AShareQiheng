APPROVED

# Task 12 fix round 2 final scoped re-review

## Finding verdicts

### Important — A succeeded long-calendar job bypasses snapshot verification on cache reuse — ADDRESSED

Evidence: `ashare_pipeline/orchestrator.py:311-323` resolves the current exact calendar ref, read-verifies its bytes and database metadata, and revalidates the exact source/dataset/request batch. At lines 329-341, every public storage-result field is derived from the verified `SnapshotRef` and `FetchBatch`: source, dataset, request, row count, payload hash/path, source version, and semantic hash. Lines 342-355 require the persisted prior item to have exactly the derived key set, require native field types, and compare every verifiable value. Missing, extra, malformed, or mismatched prior data raises before any source call or replacement.

The historic `created` value is deliberately not trusted as current publication state: its prior value must be a native boolean, while the reconstructed public cached result always emits `created=False`, `cached=True`, and `status="succeeded"` at lines 356-364. This preserves valid same-request cached reuse without refetching and prevents stale `created=True` or any unverified prior value from leaking into current output.

The focused tests in `tests/test_orchestrator.py` cover missing/tampered files and refs, missing/wrong result metadata, wrong rows/source version/semantic hash, extra keys, non-boolean `created`, and a fully valid cached reuse whose exact public output is compared with the verified ref/batch. The appended fix report records the covering focused run, orchestrator/reporting run, related Task 10/11 suites, full regression, `py_compile`, and `git diff --check` as passing.

### Important — Deep job progress is not slot-scoped and is polluted by historical/duplicate jobs — REMAINS ADDRESSED

The round-2 diff does not touch current-parent or statement-slot aggregation. The canonical parent and statement slot maps, bounded counts, explicit noncanonical-corruption handling, list-order independence, first-enqueue candidate audit behavior, and Task 13 legacy-parent execution compatibility verified in round 1 remain intact. The duplicate canonical fail-closed guards remain at `ashare_pipeline/orchestrator.py:910` and `ashare_pipeline/orchestrator.py:937`, and the single canonical statement map remains the source of `current_jobs` at line 939.

## New breakage in the fix diff

None.

## Out-of-scope observations

None.

## Verdict

Fix round 2: all findings addressed, no new Critical/Important breakage. Task 12 spec compliance and task quality are approved.

