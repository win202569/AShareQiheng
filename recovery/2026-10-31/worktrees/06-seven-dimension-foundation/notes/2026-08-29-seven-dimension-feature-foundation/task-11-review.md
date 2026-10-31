APPROVED

# Task 11 scoped re-review — round 1

Reviewed fix range `b467e2086f88088c834eee23898e10643aadae3a..6b41ff648ab8e6753b72c821f84ee7e60c1cc596` against the three original Important findings, the updated implementation report, and the complete scoped diff. No production or test code was modified during this review.

## Finding dispositions

### 1. Frozen statement ref semantic binding — ADDRESSED

- Public payload construction now validates every non-null ref against `source=akshare`, its exact statement dataset slot, and the exact security/report-period request fingerprint, and rejects repeated snapshot IDs.
- Executor resolution independently rechecks the repository `SnapshotRef`, verified batch source/dataset/request, and duplicate IDs before `_normalize_statement_snapshot()` can insert any facts.
- New tests cover public wrong-slot rejection plus executor wrong-slot, wrong-security request, and duplicate-cross-slot payloads. Invalid jobs become terminal and the shared assertion verifies zero financial facts, feature rows, and feature files.

### 2. CandidateContext and feature-key binding before side effects — ADDRESSED

- `CandidateContext` now flows through every offline feature-processing call into `_execute_feature_job()`.
- Before snapshot parsing or persistence, execution checks security membership and the four associated fields: candidate-set hash, performance-input hash, industry, and reported-target flag.
- After frozen ref resolution, the exact Task 8 input hash/key is recomputed and checked before calendar parsing, fact normalization, feature-file creation, or feature-row insertion.
- New tests independently tamper security membership and each of the four context fields. A real-snapshot wrong-key regression also proves rejection occurs before the previously observed fact insertion. All cases assert terminal job state with no fact/file/feature artifacts.

### 3. Periodic heartbeat-loss precedence — ADDRESSED

- Remote source taxonomies are now captured inside the heartbeat context rather than transitioned immediately.
- After the context stops and joins the renewal thread, `heartbeat.lost` is checked before every SourceBlocked, retryable, terminal, mismatched, or successful outcome path. A lost lease produces only the bounded `lease_lost` item and exits remote processing without snapshot/fact persistence, fail/complete transition, follow-up enqueue or processing, or SourceBlocked circuit mutation.
- The six new regressions cover all three source taxonomies under both a real handoff to `worker-b` and a transient renewal failure while `worker-a` remains the DB owner. They assert the winning/current owner and running state remain untouched, no circuit/follow-up/snapshot/feature artifact appears, and no run-level exception escapes.

## Regression assessment

The fix remains scoped to `ashare_pipeline/deep_worker.py` and `tests/test_deep_worker.py`. Exact same-context queued feature builds continue to use their frozen snapshot IDs and hashes; valid SourceBlocked/retryable/terminal behavior is preserved when the lease remains healthy. No new Critical or Important issue, over-restriction, or unrelated behavior change was found in the scoped diff.

The updated report records 64/64 Task 11 tests, 235/235 related Task 4–10 tests, 314/314 full regression tests, plus successful `py_compile` and `git diff --check`. Those already-covering commands were not redundantly rerun during this scoped review.
