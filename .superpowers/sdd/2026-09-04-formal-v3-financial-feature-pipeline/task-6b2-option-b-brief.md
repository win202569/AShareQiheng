# Task 6B2 — Option B feature execution brief

## Decision

The user selected Option B on 2026-09-06:

- V6 remains free of industry/cyclic-policy inputs.
- Every V6 feature build enforces the non-cyclic baseline: four consecutive FY endpoints and eight consecutive comparable quarters.
- The signed cyclic-industry policy, five-FY gate, and cyclic cap are a separate V7 policy-engine delivery.
- A feature task may access immutable source-task calendar binding only to authenticate a date-only statement raw snapshot during local replay. That evidence is never added to the feature payload, generation, input hash, bundle header, or scoring inputs; it never causes transport.

## Hard invariants

- No fallback from missing history to derived values. History insufficiency creates a persisted blocked bundle.
- No use of a current all-facts view as a replacement for a frozen feature task. Reconstruct every selected statement snapshot from verified raw bytes; re-extract facts and issues; compare full fact identity with V6 facts.
- Never synthesize empty FormalFactIssue values. Reconstructed issues are builder input.
- A date-only source replay uses its original statement payload's sealed binding and exact source freeze, never the feature cutoff or weekday inference.
- Feature payload/input includes no request, calendar/context fact, industry, cyclic policy, market, regulatory, event, or consensus inputs.
- Feature paths perform zero transport and no circuit actions.
- File write, database publication, and task completion each have a live lease fence. All incomplete states are recovery states, not deletion targets.

## Sequential deliveries

### D1 — Universal history gate and semantics version

Allowed files:

- ashare_pipeline/formal_financial_features.py
- tests/test_formal_financial_features.py

Implement require_formal_history(..., cyclic=False) after visible selection and comparable-quarter derivation, before untrustworthy/slot eligibility is finalized. Input wire becomes formal-feature-input-v2 and includes fixed formal-history-gate-noncyclic-v1, observed endpoints/quarters, eligibility, and blockers. Bundle schema remains v1. Insufficient history blocks every slot with no value/evidence and persists the history blockers.

For the universal 4-FY/latest-8-quarter rule, retain every selected fact/snapshot and all annual endpoints as input evidence. Derive comparable quarters only from report years at or after the canonical latest-8 window's start year; this prevents an older FY-only annual endpoint from generating an unrelated quarter-prerequisite blocker. Preserve every observed derived quarter in the bundle/input, but pass exactly the required latest 8 keys to the history gate. A future template that requests an older quarter must fail closed rather than causing implicit broader derivation.

### D2 — Feature task generation version

Allowed files:

- ashare_pipeline/formal_deep_worker.py
- tests/test_formal_deep_worker.py

Add the same fixed history/build semantics version to _feature_refresh_generation so legacy ungated feature tasks cannot be reused. New enqueue supersedes only unfinished prior generation tasks in its existing security/as-of/template scope; verified v1 tasks remain historical artifacts.

### D3 — Reconstruct-and-build formal_feature_build execution

Allowed files:

- ashare_pipeline/formal_deep_worker.py
- tests/test_formal_deep_worker.py

Strictly validate the leased typed feature payload/spec/key/generation/empty edges and exact signed runtime child hashes. For each frozen snapshot ID: establish verified source-task/receipt/request provenance; use the originating statement task's date-only binding only for raw evidence authentication; read verified raw; parse without transport; re-extract facts/issues; compare the complete fact set with V6 persisted facts. Build only from that frozen reconstructed input and enforce D1 history semantics. Non-release and history-blocked bundles are valid completed outputs.

D3 exposes only the deterministic reconstruction/build helper and its tests. It must not add formal_feature_build leasing, task completion, file writes, or database publication. D4 is the first delivery authorized to wire this helper into a leased worker and make blocked bundles completed outputs; this avoids an unsafe unpersisted-complete intermediate path.

Source tasks must already be verified even though the feature task carries no prerequisite edge. A source task that is pending/leased/retryable is a temporary hold condition for D4, not a terminal provenance failure. Validate the source task's canonical result provenance in the helper because StateStore does not impose a statement-result schema.

### D4 — Feature recovery and lease fences

Allowed files:

- ashare_pipeline/formal_deep_worker.py
- tests/test_formal_deep_worker.py

Implement content-addressed recovery:

rebuild deterministic bundle
  -> existing DB row: recover/read verified receipt + exact equality -> lease fence -> complete
  -> no DB row: lease fence -> write/verify file -> lease fence -> put DB row
                -> lease fence -> complete

Persist no task-specific machine path in the result. A file-only orphan is reusable; DB/file content mismatch is terminal; loss of ownership after file or DB publication stops further writes and lets the next owner recover.

When D3 reports a source task not yet verified, D4 records a bounded retry/hold result without transport or circuit changes; it must not terminalize a feature task merely because its source statement has not completed.

#### D4 preflight rulings

- Keep D4 limited to the worker and worker-test files.  `StateStore` does not
  offer an atomic task-lease-plus-feature-row transaction, so follow the
  already accepted statement-worker durable-write pattern: renew immediately
  before and after every irreversible stage, stop on a lost-owner error, and
  leave content-addressed file/DB artifacts for exact recovery.  Do not add a
  StateStore migration or weaken a lost-owner condition into a task failure.
- Do not use `FormalFeatureRepository`: it intentionally requires an official,
  release-eligible registry and would reject the signed non-release/history
  blocked bundles D4 must persist.  Use the exact injected
  `FormalFeatureBundleStore` plus StateStore's existing receipt-validated
  `get_formal_feature_bundle_row` / `put_formal_feature_bundle` APIs.
- Recovery order is fixed.  Rebuild first.  If an input-hash DB row exists,
  recover/read its receipt and require byte-for-byte equality with the rebuilt
  bundle, then renew -> idempotent `put_formal_feature_bundle` (it must return
  the same bundle hash and `inserted=False`) -> renew -> complete.  This
  seemingly redundant put is a required live receipt check against the
  StateStore's configured feature-store root after restart; it neither rewrites
  the immutable DB row nor the content-addressed file.  If no row exists,
  renew -> `write` (which safely reuses a file-only orphan) -> renew ->
  `put_formal_feature_bundle` -> reread/recover/equality check -> renew ->
  complete.  A missing/corrupt or mismatched DB/file receipt is terminal; never
  overwrite or delete evidence.
- The feature completion result is a closed audit map containing only typed
  identity and hashes: kind, security_id, as_of_utc, template_id,
  registry_manifest_hash, feature_registry_hash, refresh_generation,
  input_hash, bundle_hash, and bundle_manifest_hash.  It contains no filesystem
  paths or other machine-local receipt fields.
- `FeatureSourcePending` maps to `retryable_failed` with a finite fixed
  short hold and code `feature_source_pending`; it performs no transport or
  circuit mutation.  All other raw/parser/provenance/persistence failures are
  terminal feature failures because feature replay never fetches remotely.
- Extend the worker's leased kinds only to statement and feature tasks.  A
  successful new feature row increments `feature_bundles_written`; recovered
  DB rows do not.  A feature source hold increments retryable failures; loss of
  ownership increments no failure counter and triggers no follow-up mutation.

## Required test coverage

- four FY/eight quarters succeeds; missing FY or quarter yields blocked bundle and no derived slot;
- version change changes feature input hash and task generation;
- normal feature execution has zero transport;
- substituted/wrong-security snapshot, raw/parser drift, fact-set mismatch, source binding mismatch, and old generation are terminal before writes;
- reconstructed extraction issues remain in builder input;
- non-release/history-blocked output is persisted and task completes;
- DB+file, file-only, and DB-before-complete recovery; corrupt receipt/mismatch terminal;
- lease loss before file, after file, after DB, and before completion;
- no cross-security/template contamination.
