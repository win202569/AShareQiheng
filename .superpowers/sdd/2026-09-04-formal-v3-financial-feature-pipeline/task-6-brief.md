# Task 6 — Resumable Formal Collection and Per-Security Feature Rebuild Worker

## Authority and scope

The binding specification is `docs/superpowers/plans/2026-09-04-formal-v3-financial-feature-pipeline.md`, Task 6, beginning at line 1242. This brief is a plan-scoped execution aid; it does not widen that specification.

Create exactly two tracked files:

- `ashare_pipeline/formal_deep_worker.py`
- `tests/test_formal_deep_worker.py`

Do not modify existing source, parser, normalizer, DDL, migration, index, cache, global mutable state, data files, SQLite/WAL/SHM, reports, or progress records. Never stage a report or data artifact. No network access is allowed in tests.

## Required public surface

The worker module must provide the Task 6 names and only accept these task kinds at its entry boundary:

`formal_statement`, `formal_context`, `formal_universe_source`, `formal_universe_finalize`, `formal_feature_build`.

It must reject `deep_statement`, `deep_financial`, legacy `feature_build`, generic payloads, and unscoped/aggregate universe imports before transport. Required public names are `CalendarBindingPending`, the five typed task payloads, `FormalTaskSpec`, `FormalRegistryRuntime`, `FormalRegistryRuntimeLoader`, `FormalUniverseSourceResolution`, `SignedUniverseRequestResolver`, `derive_collection_refresh_generation`, `FormalWorkerDependencies`, `FormalCollectionSummary`, the three task-spec builders, `enqueue_frozen_formal_universe`, `enqueue_formal_feature_build`, and `execute_queued_formal_work`.

## Binding constraints

- Use only `FormalRegistryBundleLoader.load`, a matching verified root bundle, and the signed source/mapping/feature child blobs. Do not construct a root or child registry directly.
- The only collection/replay paths are `FormalOfficialSourceAdapter.fetch_verified` and `parse_verified_snapshot`; raw bytes must be re-read through `FormalSnapshotRepository` before replay/normalization.
- The only receipt that may suppress transport is the exact lease-bound receipt from `StateStore.get_formal_task_snapshot_receipt`. A raw file without that receipt is not a replay capability.
- Before any receipt reuse or transport, re-load the runtime, require the payload root to equal it, verify exact relevant role hashes, and recompute the derived generation from the opaque authoritative `upstream_generation`, root, relevant roles, and any date-only selector/binding. Any mismatch is terminal with zero transport.
- A timestamp-only task carries neither a calendar prerequisite edge nor a calendar binding. A date-only task has both; its binding must be revalidated through `FormalContextRepository.resolve_verified_calendar_binding` against the signed selector, exchange, freeze, root, manifest, and exact prerequisite edge. Never infer a weekday or fabricate a binding.
- Statements emit the literal lexical dataset sequence `balance_sheet`, `cash_flow_sheet`, `profit_sheet`. Keys use only the V5 canonical task fields plus derived generation; prerequisite IDs are immutable stored edges, not key material.
- Process statement/context/universe-source work only while the current worker owns a live lease. Recheck/renew before facts/context writes and again before completion. If the lease is lost after a raw receipt, stop; the next owner replays that receipt with zero transport.
- Persist statement facts only through `extract_formal_financial_facts` plus V6. A context task payload is derived only from a resolver-minted sealed `FormalContextRequest` and must retain/equality-check that request's context identity, OfficialRequest, source/request version, root, selected role hashes, upstream/refresh generations, and optional calendar binding/edge; it must not hardcode descriptor dataset names or accept a caller-created context tuple. Context facts write only through the Task 5B normalizer's sealed writer path. Rebuild features from V6 facts and selected verified source snapshots; replay extraction to reconstruct issues and compare it with persisted facts before constructing a bundle. Do not invent empty issues or reuse legacy quality fields.
- Source blocking (HTTP 403/429, CAPTCHA/challenge page, `FormalSourceBlocked`) opens only that signed source circuit and is retryable; timeout/temporary empty/`FormalRetryableSourceError` is retryable under the signed finite delay; malformed/policy/identity/schema/root errors are terminal. Do not sleep in a transaction and continue other leaseable tasks.
- Universe collection is exactly one global signed `universe_listing` request for each of BJ, SH, SZ in lexical order, followed by a zero-transport finalizer with exactly those three verified source-task edges. The finalizer re-reads receipts/raw bytes, reparses under the same runtime/binding, compares immutable source result evidence, calls `FormalUniverseIngestor.build`, stores atomically through `StateStore.put_formal_universe_snapshot`, and then completes. A mismatch creates no partial universe.
- Feature files then V6 bundle rows are an ordered, recoverable two-medium write: build -> content-addressed file receipt -> V6 row -> verified read -> task completion. An identical input hash is recovered, not re-fetched or duplicated.

## Internal delivery sequence

1. **Contract and runtime:** failing tests for closed kinds, canonical payload/generation/key behavior, runtime/root-role validation, and timestamp/date-only edge shape; then minimal typed codec/runtime/spec implementation.
2. **Statements and feature rebuild:** failing tests for same/new generation behavior, per-source circuit isolation, unapproved runtime, receipt-after-lease-loss recovery, and feature input recovery; then source execution, receipt replay, facts, feature enqueue/build.
3. **Context and calendar:** failing tests for unresolved/verified date-only calendar behavior and sealed context normalization/write behavior; then context task execution with no V6 feature enqueue.
4. **Universe:** failing tests for BJ/SH/SZ freeze, parser-row drift rejection, date-only receipt replay, and zero-transport finalization; then signed source specs/finalizer/recovery.

Each delivery follows RED -> minimal GREEN -> scoped regression -> independent review. Commit only pure code/test changes after review; do not merge or push.

## Report contract

Write implementation evidence to `task-6-report.md`: exact RED command/result, changed interface names, GREEN command/result, regression commands, scope/stat checks, and concerns. Return only status, commit SHA(s), short test summary, and concerns to the coordinator.
