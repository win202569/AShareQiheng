# Task 4D1 report — immutable formal frozen-universe graph

## Scope and result

- Implemented only `ashare_pipeline/state_store.py` and `tests/test_state_store.py`.
- Added `put_formal_universe_snapshot`, `get_formal_universe_snapshot_by_input_hash`, and `list_formal_universe_sources`.
- Added no schema or migration changes and did not implement Task 4D2 finalizer/status-replacement APIs.
- The write path requires the exact `FormalFrozenUniverseInput` type, reruns the Task 3 frozen-universe validator and hashes, revalidates all three persisted source/snapshot/task/receipt lineages inside one `BEGIN IMMEDIATE` transaction, and inserts or exactly recovers the immutable graph.
- Persisted extraction/member JSON recursively thaws `MappingProxyType`, mappings, tuples, and lists into finite canonical plain JSON with string object keys.
- Existing graphs are reconstructed into the typed Task 3 graph and revalidated on getter/idempotent replay. Partial/corrupt children or status coverage fail closed and are never repaired.

## RED / GREEN evidence

- Baseline before test changes: `python -m unittest tests.test_state_store -q` — 158 tests, OK.
- RED focused: the first persistence test failed at the intended missing production API, `AttributeError: 'StateStore' object has no attribute 'put_formal_universe_snapshot'`.
- RED bounded suite after adding all D1 tests: 166 tests ran with 21 expected missing-API errors (including subtests); all failures originated at the absent D1 API surface.
- GREEN focused: Task 3 universe tests plus the eight D1 StateStore tests — 18 tests, OK.
- GREEN bounded: `python -m unittest tests.test_state_store -q` — 166 tests, OK.
- Compilation: `python -m py_compile ashare_pipeline/state_store.py tests/test_state_store.py` — exit 0.

### Review fix round 1

- RED focused: three new regression methods produced 10 expected assertion failures. A valid-shape substituted initial `evidence_hash` was accepted by getter/replay, and verified source tasks with a canonical error, ghost lease worker/expiry, future retry, or reversed canonical lifecycle timestamps were accepted.
- GREEN focused: `python -m unittest -v tests.test_state_store -k formal_universe` — 11 tests, OK.
- GREEN bounded: `python -m unittest tests.test_state_store` — 169 tests, OK.
- Compilation: `python -m py_compile ashare_pipeline/state_store.py tests/test_state_store.py` — exit 0.
- Diff hygiene: `git diff --check` — exit 0; tracked changes remained limited to `ashare_pipeline/state_store.py` and `tests/test_state_store.py`.
- The read/replay path now recomputes the binding initial-status hash whenever and only whenever the exact D1 initial tuple is present. A later non-initial D2 status continues to receive structural validation without the D1 formula being imposed.
- Before any `formal_universe_source` task is trusted as verified, its task UUID and lifecycle timestamps must be canonical, `created_at <= updated_at`, a canonical result must exist, and `error_json`, `lease_worker`, `lease_expires_at`, and `next_retry_at` must all be NULL. These checks apply both before initial persistence and when reloading an existing graph.

## Initial status ruling

Every newly inserted member receives exactly:

- `status = "pending_evidence"`
- `reasons = ("formal_collection_pending",)` (persisted as canonical JSON array)
- `veto_flags = ()` (persisted as canonical JSON array)
- `evidence_hash = SHA256(canonical UTF-8 JSON({"frozen_input_hash", "security_id", "status", "reasons", "veto_flags"}))`

Canonical JSON uses sorted object keys, compact separators, UTF-8, `ensure_ascii=False`, and rejects non-finite values. Idempotent replay validates exact status coverage but does not reset a later valid D2 status update.

## Covered failure modes

- Real verified `formal_universe_source` tasks and exact receipts for BJ/SH/SZ.
- Header/count/order and complete nested frozen raw-row serialization.
- Exact idempotent recovery without status reset.
- Typed-input, freeze, member/source ordering, universe/source-audit/frozen-hash recomputation failures.
- Missing/duplicate/cross-exchange/untrusted/bootstrap source graphs.
- Wrong task kind/status/generation, receipt manifest, missing/duplicate producer receipt graph, task result, and task payload exchange.
- Late child insertion rollback and corrupt existing header/source/member/status graphs.
- Legacy `source_snapshot` isolation.

## Limitations deferred to Task 4D2 or later

- Status replacement/listing and finalizer-task lookup/completion remain intentionally absent.
- Existing non-initial status evidence is structurally validated (coverage, canonical JSON arrays, allowed status, lowercase SHA-256) but its domain-specific evidence semantics belong to the D2 typed status transition.
- No network, operational database, migration, or raw-data smoke was run; tests use hermetic raw-store fixtures.
- Existing Task 2 Windows symlink/TOCTOU limitations remain unchanged and out of this slice.
