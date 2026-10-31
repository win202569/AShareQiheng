# Task 6D — frozen universe execution

## Authority and decisions

User confirmed the two compatibility adjustments on 2026-09-08:

- Add `universe_listing` to the foundation ingestor's closed listing dataset set, retaining `official_security_listing` compatibility and original snapshot identity.
- `formal_universe_task_specs` returns three source specs in BJ/SH/SZ order. The enqueue coordinator persists them, then creates the finalizer with their actual immutable task IDs. No UUID prediction or placeholder edges.

Worker implementation remains in `formal_deep_worker.py` and its tests. Foundation compatibility is confined to `formal_universe.py` and its tests. Only pure code/test files are eligible for commit; no merge or push.

One additional integration detail was resolved within foundation compatibility: existing ingestor required the literal historical China-time freeze, while new worker payloads require canonical UTC. Accept precisely the two canonical representations of the same 2026-08-31 closing instant, retaining the supplied representation so legacy hashes and new task lineage remain intact. Other dates, adjacent seconds, and noncanonical representations remain rejected.

## Foundation evidence

- RED: two targeted acceptance tests failed with the actual existing dataset and freeze validation errors.
- GREEN: `python -m unittest tests.test_formal_universe -v`: 13 tests passed, 0.014s.
- Regression: `python -m unittest tests.test_state_store -k universe -v`: 24 tests passed, 40.824s.
- Interpreter: `D:\Projects\AShareQiheng\.venv\Scripts\python.exe`.

## Coordination (completed)

Worker implementation and integrated fixtures were delegated to `universe_api_inventory`, followed by explicit root single-writer handoff. Independent security review was performed by `universe_security_audit`; foundation review and baseline history-fixture diagnosis by `calendar_bootstrap_static`. Root completed the final legacy-test edge cases and collected the final verification results.

Preserved unrelated untracked directory: `tmpj4zv9_fq/` (test SQLite artifacts from the preceding task). Do not stage or remove it.

## Integration notes

- Source and financial feature regression: 76 tests passed, 1.346s.
- Foundation independent review: no blocking issue. Added the historical frozen-input digest from HEAD (`ac8575dab15f28a9c9d032463704565c01ae9ce49f723eac55bd57ebbd2868c9`) to lock legacy hash compatibility and asserted different representation identities. Foundation 13 tests passed again.
- Added finalizer failure/recovery tests in `FormalUniverseFinalizerTests` (accepted/excluded parser-row drift and lease loss after raw read, parse, graph insert, completion). Initial RED confirmed no source execution yet (0 instead of 3 attempts).
- Concurrent tool patches to the same worker file overwrote the root's finalizer insertion. Switched to a single-writer handoff: implementation agent owns source/runtime/dispatcher until explicit release; root then adds finalizer. Reviews may remain parallel. Do not assume a successful apply response means another writer preserved its contents; verify final diff.

## Final integration and regression audit

- Source resolver/spec/enqueue, source execution, and zero-transport finalizer are implemented. The source result has exactly ten evidence fields, including effective_time_evidence_hash. The finalizer recomputes all ten from the verified receipt/raw/parser/calendar path before atomic universe persistence.
- New cohorts are persisted before precise full-payload supersession of unfinished older cohorts. Verified source tasks are preserved. Statement dispatch priority remains unchanged.
- Source receipt lease-loss recovery retains the identical receipt and makes zero new requests. Finalizer recovery replays the frozen evidence and retains the original universe ID, frozen-input hash, and universe hash after insertion/completion interruptions.
- Universe integration/finalizer suite: 10 tests passed in 115.780s. Includes signed timestamp/date-only positive paths, missing date-only raw binding bridge rejection, accepted/excluded row drift rejection, per-source circuit isolation, and interrupted-write recovery.
- Independent source/finalizer/foundation reviews: no blocking code findings after fixes; final test audit also accepted the effective-time binding and receipt identity checks.
- Initial monolithic discovery: 976 tests in 1110.286s, 29 failures, 2 errors, 4 skips. It imported an earlier revision of the universe circuit test fixture. Do not describe this run as green.
- The 29 failures were independently reproduced in untouched HEAD feature-repository tests: D1 introduced universal history maturity, while this repository fixture still installed only the four 2025 cumulative periods. Commit ee85a76 aligned only StateStore fixtures. Repair is limited to real persisted history in tests/test_formal_feature_repository.py; no production gate changes.
- The other non-universe error was reproduced in untouched HEAD tests/test_orchestrator.py: Windows system temp on C: cannot be made relative to the D: workspace. Only the relative-path case now uses a cwd-local temporary directory, retaining relative-path and persisted-output assertions. RED: 1 test errored in 0.004s; GREEN: 1 test passed in 0.681s.
- The two legacy test-only fixture repairs are isolated from the four-file Task 6D implementation and will be committed separately. No production source outside formal_deep_worker.py and formal_universe.py is changed.
- Final full-regression partition: 93 worker tests + 39 Context repository tests + 208 StateStore tests + 30 formal feature repository tests + 609 remaining tests = 979 discovered tests. Only test fixtures changed after the initial discovery; production files were frozen before it.
- Final worker partition: 93 tests passed in 521.958s, no skips/errors/failures.
- Final StateStore partition: 208 tests passed in 158.003s, no skips/errors/failures.
- Remaining partition first pass reproduced only the Windows fixture error (609 tests, 242.536s, 4 skips); rerunning after the local fixture fix.
- Final remaining partition: 609 tests in 231.611s, OK with 4 skips, no failures/errors.
- Final Context repository partition: 39 tests passed in 717.085s, no skips/errors/failures. Independent read-only review of the Windows relative-path fixture fix found no blocking issue.
- Mature feature-repository setup exposed two further obsolete test-body expectations (root reproduction: 30 tests, 56.275s, 1 failure and 1 error). Empty history cannot bypass the universal gate through an optional slot, and FY-only data must block every derived slot. The fixes retain the empty-history negative path, add an optional unobserved FY2021 slot over full real persisted history, and assert raw FY value preservation alongside exact blocked bundle status/value/evidence/reason. These semantics are explicitly covered by the existing D1 builder regressions; no production behavior was changed.
- Final formal feature repository partition: 30 tests passed in 114.180s, no skips/errors/failures. Final independent review accepted both legacy test-file diffs without assertion weakening or gate bypasses.
- Final full coverage: 979 discovered tests, 975 passed and 4 skipped across the five non-overlapping module partitions; zero failures/errors. All six changed Python files passed py_compile, and git diff --check passed.

## Delivered commits

- `b76623c64e25c70af1a34bf51304a280d42f8b20` — feat: execute signed frozen universe tasks. Exactly the four Task 6D code/test files; 1186 insertions and 23 deletions.
- `f2efe84aa36f5bb609b162cfc8e5c4e216286aae` — test: restore mature history and Windows path fixtures. Exactly the two legacy test files; 44 insertions and 18 deletions.

Both commits remain on `codex/formal-v3-implementation`. Post-commit tracked status is clean; only the pre-existing untracked `tmpj4zv9_fq/` remains. This progress file is ignored and was not staged. Task 6D is delivered; this is not a claim of live-data acquisition or formal score/pool publication.

No live collection, production registry signing, formal scoring, pool publication, merge, push, or main-branch mutation was performed. Progress and test databases remain excluded from code staging; tmpj4zv9_fq/ remains untouched.
