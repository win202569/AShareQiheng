# Final six-Minor cleanup scoped review

Range: `56b0343..3ce5a90`

Verdict: `0 Critical / 1 Important / 1 Minor`; findings remain open; not integrable.

## Finding status

1. **NOT ADDRESSED — Important.** `_LeaseHeartbeat.ensure_owned()` checks a cached loss flag outside the renewal transaction. Snapshot, fact, quality-issue, and feature writes are not atomically fenced by the current `job_id`/`worker_id` lease. A stale worker can pass the check, lose the lease to a recovered worker, and still commit durable intermediate artifacts. Probe result: `non_atomic_guard True True`. Independent concurrency audit confirmed the concrete lease-expiry/recovery/write interleaving and graded it P1/High.
2. **ADDRESSED.** Resolved legacy absolute snapshot paths are confined to `data_root`, with positive and negative tests.
3. **ADDRESSED.** The migration plan names `source_snapshot` and `artifact` correctly.
4. **ADDRESSED.** The unclassified negative regression now pins construction, persistence, verified-read, and status boundaries independently.
5. **ADDRESSED.** Zero-financial-slot bank/insurance/broker templates consistently omit the unauthenticatable balance marker while remaining specialized-input blocked.
6. **NOT ADDRESSED — Minor.** `_process_feature_jobs` no longer catches `BaseException`, but `_LeaseHeartbeat.close()` can raise `RuntimeError` after a bounded join, masking an active `KeyboardInterrupt`/`SystemExit`; the renewal thread can remain alive. Probe result: `process_control_observed RuntimeError context KeyboardInterrupt thread_alive_after_timeout True`.

## Required residual repair boundary

- Fence each lease-authorized durable mutation in the same `BEGIN IMMEDIATE` transaction that validates the unexpired `job_id`/`worker_id` owner; a separate `ensure_owned()` lock is not sufficient.
- Stage immutable files first, then validate owner, publish file, insert metadata, commit, and clean up on rollback.
- Heartbeat shutdown must preserve `KeyboardInterrupt`/`SystemExit` and must not leave a live renewal thread after the worker exits.
- Add deterministic barrier regressions for ownership transfer during a write and a hung/in-flight renewal during process-control exit.

The implementation report records genuine RED and focused/affected/full/staged GREEN evidence. Broad suites were not rerun by this scoped review.
