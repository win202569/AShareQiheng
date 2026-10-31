# R3 independent task review — e6c551d

## Spec Compliance

❌ Issues found. R3 implements all six planned files and the principal API, authority, migration, and replay contracts, but two persistence fences remain incomplete: lease mutation uses a timestamp captured before acquiring the writer lock, and child completion does not recheck previously authenticated parent evidence beyond its task-row identities.

⚠️ Final compatibility remains pending. The report records the sealed-fetch regression plus three authority/import tests passing (`4 tests`, `86.584s`, exit `0`). The prescribed Store + Source + StateStore run has no terminal result yet; any fixes will require validation against their resulting frozen version.

## Strengths

- `ashare_pipeline/formal_range_source.py:677` captures the original registered fetch manifest and immutable raw bytes before callbacks. `ashare_pipeline/formal_range_store.py:467` uses this snapshot throughout normalization and persistence, closing the reported mutable-fetch inconsistency.
- `ashare_pipeline/formal_range_source.py:690–758` provides genuine, immutable observations with separate historical/current qualification. The original type/verifier/wire-reader tuple at `:1089` avoids trusting replaced public aliases.
- `ashare_pipeline/formal_range_store.py:156–174` reconstructs requests through the signed binding and authentic parent observations. `ashare_pipeline/formal_range_source.py:773` enforces the same original StateStore and resolved filesystem root for execution.
- `ashare_pipeline/formal_range_store.py:272–338` compares authenticated source versions and checks candidate sets after replay and ancestor traversal, including the empty-candidate case. Refresh strings and insertion order do not establish freshness.
- `ashare_pipeline/formal_range_store.py:497–508` commits snapshot, receipt, and verified completion atomically and checks producer expiry again before completion. `tests/test_formal_range_store.py:181` exercises transaction rollback while preserving raw files.
- `ashare_pipeline/state_store.py:1847` implements the additive V7 migration with schema verification before ledger insertion. Migration coverage at `tests/test_state_store.py:8084–8150` includes continuous entrances, reopening, partial objects, and name collisions. The diff preserves the existing V2–V6 DDL constants and retains legacy migration tests.

## Issues

### Critical

None identified.

### Important

1. **Lease renewal and failure can mutate an already expired attempt after waiting for the writer lock.**

   `ashare_pipeline/formal_range_store.py:439–445` and `:452–461` compute `now` before entering `transaction(..., immediate=True)` and pass that old timestamp to `owner()`. `StateStore._transaction` acquires `BEGIN IMMEDIATE` before yielding (`ashare_pipeline/state_store.py:1631`), so lock contention can carry execution beyond lease expiry while `owner()` still accepts the attempt.

   Consequently, an expired worker can renew its lease or change its task to a failure state if no takeover has happened yet. A retry deadline can also expire during that wait and still be accepted. This violates the required live-attempt fence; `persist()` already demonstrates the stronger pattern with its fresh final check at `:504–505`.

   Sample the time after obtaining the writer lock, calculate renewal expiry and validate retry timing there, and check live ownership at the mutation boundary. Add a focused regression for lock acquisition crossing expiry for both `renew()` and `fail()`; the fixed-clock takeover test at `tests/test_formal_range_store.py:29` does not cover this interval.

2. **The final parent fence detects authenticated corrections, but misses parent evidence tampering during child preparation.**

   `ashare_pipeline/formal_range_store.py:340–353` captures ancestor candidate sets containing only `formal_range_task` rows. `persist()` takes these snapshots at `:474`, authenticates the parent chain, executes the child parser, and checks only those task sets inside the final writer transaction at `:499`.

   A normal authenticated parent correction creates another verified task and is correctly rejected. However, changing an ancestor’s snapshot/receipt/producer row or raw/manifest file after parent authentication leaves the captured task set unchanged. The child can therefore commit as `verified`; only the post-commit `read(self, task_id)` at `:508` discovers the damaged parent and raises. This does not mint a successful observation, but it leaves committed completion that failed the required dependency verification.

   Carry the authenticated ancestor evidence identities through preparation and compare their corresponding database rows and content identities inside the final writer fence, keeping graph reconstruction and parsing outside it. Cover a parent receipt or raw-file change during the child parser callback. The existing regression at `tests/test_formal_range_store.py:340` covers the distinct, correctly fenced authenticated-correction case.

### Minor

- **Several explicitly requested adversarial cases lack their stated regression.** `tests/test_formal_range_store.py:94` tests receipt deletion and producer-worker alteration, despite naming “extra producer”; it never creates multiple verified producers or a naked verified-task INSERT. The natural-key test at `:60` appends noncanonical whitespace rather than testing conflicting canonical payloads under one natural key. Add those cases so the requested invariants remain protected independently of the current implementation.

## Checks and Evidence Boundaries

- Reviewed the complete six-path task diff, BASE `c7fb672bfe47d2831bb4c1e850d6397407b9464b` to HEAD `e6c551d7e36819d38563511fd139ecdaa7a01e58`, against the brief and implementation report.
- Focused outside-diff check: inspected `StateStore._transaction` at `ashare_pipeline/state_store.py:1623` to establish where writer-lock waiting occurs.
- Focused outside-diff check: inspected constructor identity validation at `ashare_pipeline/formal_repository_identity.py:21` for the new store’s original-StateStore identity requirement.
- Read source functions whose relevant bodies were cut by diff hunks: `source_record`, `_parse`, and `parse_verified_snapshot`. Confirmed callback-time implementation/binding checks at `ashare_pipeline/formal_range_source.py:932–940`; the parent persistence finding concerns evidence identities beyond those source checks.
- Ran no additional tests, Git commands, writes, production operations, or network requests. Root independently owns the six frozen hashes, ten legacy-DDL baseline comparisons, and final compatibility gate.

## Assessment

**Task quality: Needs fixes.**

The authority separation, sealed-fetch handling, and authenticated replay are well constructed. The two remaining mutation windows must close before R3 can satisfy its producer-expiry and parent-evidence completion guarantees.
