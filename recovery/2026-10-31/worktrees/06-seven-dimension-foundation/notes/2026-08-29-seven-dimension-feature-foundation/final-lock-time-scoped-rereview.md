# Final lock-time scoped re-review — `4cd2acc..1f155ef`

## Scope and method

- Review base: `4cd2acc0fe777e7e3c3b96d9de8a2752f7ba1f8e`.
- Review head: `1f155ef1a037079939c9a2c7fb1d093bf0b071e9`.
- Scope was limited to the one reported Critical and the supplied three-file fix package: `ashare_pipeline/state_store.py`, `tests/test_state_store.py`, and `progress.md`.
- The supplied package was read once. No Git command or evidenced suite was rerun, and no tree, index, or HEAD mutation was performed. The RED/GREEN counts below are supplied controller evidence.
- One focused serialization-boundary probe was attempted for the concrete doubt described below. Its result collector requested a non-public `updated_at` field and ended with `KeyError`, so it is excluded from test evidence; the verdict relies on direct source/Python evaluation order and the supplied deterministic tests.

## Finding verdict

### Critical — lock-stale lease authorization time: **NOT ADDRESSED**

The fix correctly closes the reported writer-lock wait and follow-up-preparation windows, but both strict terminal paths still perform potentially non-trivial JSON serialization after their final authorization-time sample and before SQLite executes the guarded `UPDATE`:

- `complete_job_with_followups` samples `transition_now` at `ashare_pipeline/state_store.py:595`, then evaluates `_json(result)` while building the parameters at `ashare_pipeline/state_store.py:602`, before the `connection.execute` call can run.
- `fail_job_with_followups` samples `transition_now` at `ashare_pipeline/state_store.py:624`, then evaluates `_json(error)` at `ashare_pipeline/state_store.py:632`, before the guarded statement executes at `ashare_pipeline/state_store.py:625`–639.

Concrete remaining interleaving: the first in-transaction owner check passes at T9 for a lease expiring at T10; follow-up preparation finishes; `transition_now` is sampled at T9; serialization of a sufficiently large `result` or `error` spans T10; the guarded update then compares `lease_expires_at` with the retained T9 value, succeeds, and commits the terminal state and any follow-ups after actual expiry. Thus the requested re-sample is not yet immediately before the guarded update in execution order, and the original authorization invariant remains open on both complete and fail.

Required correction: serialize `result`/`error` before the final `_utc_now()` call, then use the precomputed JSON value in the guarded `UPDATE`. A deterministic barrier covering expiry during this post-sample/pre-execute interval should prove both complete and fail reject and roll back follow-ups.

## Checks that are addressed

- **Renewal samples and calculates after the real writer lock.** `_transaction` executes `BEGIN IMMEDIATE` before yielding at `ashare_pipeline/state_store.py:285`–296. `renew_job_lease` enters that context at `ashare_pipeline/state_store.py:568`, samples/normalizes at line 569, and computes expiry at lines 570–571. The update uses the same post-lock `now` for `updated_at` and the lease guard, and uses `now + lease_seconds` for `lease_expires_at`, at lines 572–576.
- **Explicit `now_utc` semantics remain deterministic.** `_utc_iso` only calls the wall clock for `None` at `ashare_pipeline/state_store.py:252`–259. The existing explicit-time regression at `tests/test_state_store.py:1617`–1625 asserts that T30 plus 120 seconds yields T150 and still rejects a wrong owner.
- **Initial complete/fail authorization is post-lock.** Complete acquires the immediate transaction at `ashare_pipeline/state_store.py:591`, then samples and checks at lines 592–593. Fail does the same at lines 620–622.
- **The second sample is after follow-up preparation and drives terminal timestamps/guards.** Complete inserts follow-ups at `ashare_pipeline/state_store.py:594`, re-samples at line 595, and uses that value for both `updated_at` and `lease_expires_at > ?` at lines 596–603. Fail follows the equivalent sequence at lines 623–639. The remaining defect is the JSON work between that sample and actual execution, not reuse of the initial timestamp.
- **Zero-row terminal updates roll back follow-ups.** Both paths raise inside the transaction on `rowcount != 1` at `ashare_pipeline/state_store.py:604`–607 and 640–643. `_transaction` rolls back every post-`BEGIN` exception at `ashare_pipeline/state_store.py:297`–306, and `_insert_followups` uses the same connection at lines 661–694.
- **No owned strict transition path was omitted.** Both owner-aware terminal paths are modified. The legacy `complete_job` and `fail_job` paths call `_require_legacy_transition_allowed` at `ashare_pipeline/state_store.py:696`–704 and 733–744; that helper rejects every `_OWNED_JOB_KINDS` job at lines 749–761, so leased deep/feature jobs cannot bypass the strict methods.

## Deterministic test evidence

- `tests/test_state_store.py:1627`–1691 holds a real second-connection `BEGIN IMMEDIATE`, observes the blocked renewal's lock attempt before releasing it, flips the controlled clock past expiry, asserts `[False]` for pre-`BEGIN` sampling, and proves the lease was not renewed.
- `tests/test_state_store.py:1693`–1789 runs the same real-lock barrier for both `complete` and `fail`; each rejects after lock acquisition and leaves the running job, lease, and follow-up set unchanged.
- `tests/test_state_store.py:1791`–1865 runs both terminal actions through an event-gated follow-up preparation boundary, flips the clock from T9 to T11 for a T10 lease, and proves the zero-row guarded update rolls back the inserted follow-up.
- The appended final-wave report records genuine RED on unchanged `4cd2acc`: 3 tests with 5 failures, covering renew, both lock-wait terminal actions, and both follow-up-preparation terminal actions. Supplied GREEN evidence on `1f155ef` is exact former RED 3/3, focused lease matrix 13/13, affected StateStore/DeepWorker modules 163/163, and staged-tree full offline suite 424/424.
- Those tests are non-vacuous for the named writer-lock and follow-up barriers. They do not exercise expiry during `_json(result)` or `_json(error)` after the final time sample, which is the remaining gap above.

## New breakage scan within the three-file diff

- New Critical findings: none separate from the still-open portion of the reported Critical.
- New Important findings: none.
- New Minor findings: none.
- The `progress.md` summary matches the supplied RED/GREEN record, but its statement that the sample is immediately before the terminal update is stronger than the execution order currently guarantees.

## Assessment

**Ready to integrate within this scoped re-review? No.** Renewal is fixed, explicit logical-time behavior is preserved, real-lock barriers are substantive, and follow-up rollback is correct. Complete and fail must move result/error serialization before the final authorization-time sample so no potentially non-trivial preparation remains between that sample and the guarded terminal update. No unrelated whole-branch finding or operational gate was revisited.
