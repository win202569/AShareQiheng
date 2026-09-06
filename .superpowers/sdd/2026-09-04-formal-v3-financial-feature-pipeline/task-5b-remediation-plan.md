# Task 5B Provenance Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Every production change follows a separately observed RED → GREEN cycle.

**Goal:** Repair the post-commit Task 5B provenance defects without weakening public fail-closed reads: lease-bound writers must be able to persist Context facts before task completion, historical date-only facts must validate against their original verified calendar binding, and incremental writes must not revalidate unrelated Context rows.

**Architecture:** Writer authorization and public-read provenance are deliberately distinct. A sealed normalization receipt carries a current lease-bound writer proof; only a verified task can make stored facts visible to public repository reads. Historical Context validation creates a sealed, target-bound read capability only after it proves the original calendar Context fact and source chain; that capability travels through the already-configured raw-store boundary and cannot be used for writes or a different request, manifest, content hash, or raw-store instance.

**Tech Stack:** Python 3, SQLite V6 (no DDL/migration change), `unittest`, existing signed registry, StateStore, FormalSnapshotStore, and FormalSnapshotRepository contracts.

**Spec:** `docs/superpowers/specs/2026-09-04-formal-scoring-release-contract-design.md`; binding supplement `task-5b-brief.md`; worker ordering is plan lines 1615–1622.

## Global Constraints

- No network, data, SQLite/WAL/SHM, progress, report, or artifact files may be staged.
- Do not change V6 DDL, source adapters, parsers, normalizers, release policy, or score logic.
- Default/current snapshot reads and every write path retain their current behavior unless an exact sealed capability is supplied.
- A public `list`, repository lookup, calendar binding lookup, or effective-time resolver accepts only a verified producer task with exact receipt/result lineage.
- A writer accepts only an exact `formal_context` task under the current unexpired owner lease, exact source receipt, and exact refresh generation; it must recheck that condition at the end of its immediate transaction.
- Historical date-only validation must not rerun an adapter or normalizer, must not construct a second raw store, and must prove the historical B1 calendar fact/root/selector/exchange/freeze/snapshot/raw/receipt/task before use.
- A write validates incoming facts and pre-existing candidates with the same logical generation only. Public reads retain complete stored-fact revalidation.

---

### Task R1: Lease-bound Context writer receipt

**Files:**

- Modify: `ashare_pipeline/formal_context_schema.py`
- Modify: `ashare_pipeline/formal_context_repository.py`
- Modify: `ashare_pipeline/state_store.py`
- Modify: `tests/test_formal_context_repository.py`

**Interfaces:**

- `FormalContextRegistry.normalize_verified(..., *, task_id: str, worker_id: str)` mints a sealed `FormalContextNormalization` whose canonical wire contains `writer.task_id`, `writer.worker_id`, `writer.refresh_generation`, and the exact source-receipt wire.
- `StateStore.put_formal_context_facts(normalization)` remains receipt-only; it never accepts a raw fact tuple, task ID, or worker ID from its caller.
- Private writer validation proves: exact source snapshot/receipt, `formal_context` kind, task ID/generation match, `leased` status, current `worker_id`, and unexpired lease. Private public-read validation continues to require `verified`, result, and receipt.

- [ ] **Step 1: Write failing writer tests**

```python
def test_leased_context_writer_persists_before_completion_but_public_read_waits_for_verified(self):
    task_id, worker_id, request, snapshot, raw = self.leased_context_receipt()
    normalization = self.registry.normalize_verified(
        request, snapshot, raw, self.normalizer,
        task_id=task_id, worker_id=worker_id,
    )
    self.store.put_formal_context_facts(normalization)
    with self.assertRaisesRegex(ValueError, "verified formal_context producer"):
        self.repository.get_verified("security_state", "state", "SZ000001", AS_OF, self.root_hash)
    self.store.complete_formal_task(task_id, worker_id, self.context_result(snapshot))
    self.assertEqual(self.repository.get_verified("security_state", "state", "SZ000001", AS_OF, self.root_hash).source_snapshot_id, snapshot.snapshot_id)
```

Add independent tests for wrong worker rejection, expired lease rejection, post-insert lease-expiry rollback, new-owner recovery with the same receipt and idempotent fact, and rejection of the old sealed receipt after ownership changes.

- [ ] **Step 2: Run the writer tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_formal_context_repository.FormalContextRepositoryTests.test_leased_context_writer_persists_before_completion_but_public_read_waits_for_verified -v
```

Expected: FAIL before completion because the current producer check requires `status == "verified"`.

- [ ] **Step 3: Implement the smallest writer/read split**

Implement separate private writer and public-read producer checks. Mint and verify the sealed writer wire during normalization; use it at the start and end of `put_formal_context_facts`. Keep `list_formal_context_facts`, repository selection, calendar lookup, and effective-time lookup on the verified-only check.

- [ ] **Step 4: Run writer tests and verify GREEN**

Run the targeted test plus every new lease/recovery negative test. Expected: writer tests pass; public read fails while leased and passes only after completion.

---

### Task R2: Historical date-only calendar proof and bounded raw read

**Files:**

- Modify: `ashare_pipeline/formal_context_schema.py`
- Modify: `ashare_pipeline/formal_context_repository.py`
- Modify: `ashare_pipeline/state_store.py`
- Modify: `ashare_pipeline/formal_snapshot_store.py`
- Modify: `ashare_pipeline/formal_snapshot_repository.py`
- Modify: `tests/test_formal_context_repository.py`

**Interfaces:**

- An internal sealed historical-read capability binds the configured raw-store object identity, the full sealed Context request, target snapshot ID/manifest/content hash, B1 binding, and B1 effective-time evidence hash.
- It is minted only after Context code freshly proves the exact historical `trading_calendar` fact, signed root/selector/exchange/freeze, calendar source snapshot/raw/receipt/task, and B1 identity.
- `FormalSnapshotStore.read_verified_raw` and `validate_stored_snapshot`, StateStore selected-row verification, and FormalSnapshotRepository manifest/read methods accept the optional internal capability. Their default remains current binding resolution; writes never accept it.

- [ ] **Step 1: Keep and run the observed C1 → D1 → C2 → D2 RED**

```python
def test_calendar_correction_preserves_old_date_only_provenance_and_selects_new_generation(self):
    c1 = self.persist_bootstrap_calendar(generation="calendar-v1")
    d1 = self.persist_date_only_security_state(calendar=c1, generation="context-v1")
    c2 = self.persist_bootstrap_calendar(generation="calendar-v2", later_source_update=True)
    d2 = self.persist_date_only_security_state(calendar=c2, generation="context-v2")
    facts = self.store.list_formal_context_facts(registry_manifest_hash=self.root_hash, context_kind="security_state")
    self.assertEqual({d1.id, d2.id}, {fact.id for fact in facts})
    self.assertEqual(d2.id, self.repository.get_verified("security_state", "state", "SZ000001", AS_OF, self.root_hash).id)
```

- [ ] **Step 2: Verify RED is the historical B1/B2 mismatch**

Run the one test before production changes. Expected: D2 persistence or selection fails while revalidating D1 because the configured current raw resolver returns C2/B2 instead of D1's persisted C1/B1 manifest.

- [ ] **Step 3: Implement the sealed historical path**

For a stored date-only fact, parse its persisted binding; prove the exact C1 calendar record and all source/task evidence; rebuild the fact request with B1; mint the target-bound capability; then use it only for D1's selected snapshot raw validation. Reject missing C1, changed selector/root/exchange/freeze, different raw store, different target manifest/content/request, forged capability, or effective-time evidence mismatch. Do not call a parser or normalizer.

- [ ] **Step 4: Verify GREEN and negative provenance cases**

Run C1/D1/C2/D2 plus missing/tampered historical calendar anchor, forged capability, different raw-store instance, and target manifest substitution tests. Expected: only the exact proven B1 path reads D1; D2 is selected by version ordering; every substitution fails closed.

---

### Task R3: Incremental candidate-only conflict verification

**Files:**

- Modify: `ashare_pipeline/formal_context_repository.py`
- Modify: `tests/test_formal_context_repository.py`

**Interfaces:**

- `_put_context_facts` queries and completely revalidates only an incoming fact and persisted rows with the same logical generation key, including the calendar exchange discriminator.
- `list_formal_context_facts` and all repository public reads still revalidate every matching stored fact and fail closed on unrelated corruption.

- [ ] **Step 1: Write failing isolation test**

```python
def test_put_revalidates_only_incoming_logical_generation_while_public_list_stays_fail_closed(self):
    unrelated = self.persist_verified_context("industry_snapshot", "industry", "SZ000001")
    self.tamper_unrelated_context_source(unrelated)
    incoming = self.leased_context_normalization("security_state", "state", "SZ000001")
    self.store.put_formal_context_facts(incoming)
    with self.assertRaises(ValueError):
        self.store.list_formal_context_facts(registry_manifest_hash=self.root_hash)
```

- [ ] **Step 2: Verify RED**

Run the one test. Expected: current full-table writer validation rejects the incoming write because it revalidates the unrelated tampered fact.

- [ ] **Step 3: Implement candidate-only writer validation**

Use exact SQL predicates for context kind, scope, nullable security ID, as-of instant, root, generation, and trading-calendar exchange after canonical value parsing. Revalidate every candidate in full; reject nonidentical duplicate canonical content. Do not add an index, DDL, cache, or global mutable state.

- [ ] **Step 4: Verify GREEN and complete regression**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_formal_context_schema tests.test_formal_context_repository tests.test_formal_sources tests.test_formal_time -v
.\.venv\Scripts\python.exe -m py_compile ashare_pipeline\formal_context_schema.py ashare_pipeline\formal_context_repository.py ashare_pipeline\formal_snapshot_store.py ashare_pipeline\formal_snapshot_repository.py ashare_pipeline\state_store.py tests\test_formal_context_schema.py tests\test_formal_context_repository.py
git diff --check HEAD
git status --short
```

Expected: all tests pass, no compilation or whitespace errors, and only pure code/tests are staged.

---

## Self-Review

- Spec coverage: R1 restores the mandatory lease → receipt → context → completion worker sequence while preserving verified-only publication. R2 preserves immutable historical context evidence across official calendar corrections. R3 makes incremental all-A-share writes scalable without weakening public evidence verification.
- Placeholder scan: every task names files, interfaces, RED behavior, expected result, and exact verification commands.
- Type consistency: R1 binds task/worker/receipt in `FormalContextNormalization`; R2 passes only the sealed historical read capability across Context, StateStore, repository, and raw store; R3 consumes the same logical key already defined by Context persistence.

