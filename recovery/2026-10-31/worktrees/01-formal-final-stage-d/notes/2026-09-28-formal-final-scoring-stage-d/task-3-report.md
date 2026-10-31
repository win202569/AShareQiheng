# Task 3 report — D1 identity and proof lifecycle guards

Status: implementation, required combined regression, self-review and commit complete; independent review is coordinator-owned and pending.

Commit: `377bfe71a1f37c802917f0e005806e225c390e9e` (`test: seal final score input provenance`). `git show --format= --name-only HEAD` confirms exactly the production module and new guard test; `git show --format= --check HEAD` passed. The only remaining tracked worktree change is the unrelated pre-existing plan edit.

Base: `c7a71c28e3447758fad6a23b3d4789f75f2c5177`. Only `ashare_pipeline/formal_final_score_inputs.py` and `tests/test_formal_final_score_input_guards.py` are implementation deliverables. The unrelated tracked plan edit was present before Task 3 and is untouched. This report is not a commit deliverable.

## RED → GREEN attack matrix

All seven exact-name tests use real D1 producers/proofs and signed fixture roots; no source proof or Stage C score is mocked or minted by the test. The three-member fixture is used for identity, pending, and lifecycle attacks. The genuine twenty-member `22+3` ready proof remains in the Task 2 regression, which is included in the required combined command below. Test-only attack injection replaces and restores live Python bindings, publishes a real current-input snapshot during finalization, or temporarily corrupts a closure-owned batch index and restores it afterward.

| Attack test | Corrected RED | Focused GREEN | Evidence |
|---|---|---|---|
| `test_cross_root_frozen_security_and_source_batch_are_rejected` | passed | passed | A separate signed v2 root, unknown selector, and genuine source batches against the wrong frozen root are rejected. |
| `test_raw_v_percentile_cannot_replace_stage_c_score` | passed | passed | Three-member pending D1 has no raw V final slots; a real adjusted input cannot construct a D1 proof or mutate frozen slots. The separate Task 2 ready test checks genuine 20-peer Stage C scores in all three V slots. |
| `test_forged_copied_pickled_inherited_or_weakref_redirected_proofs_are_rejected` | failed: subclass definition succeeded | passed | Ordinary construction, object forgery, copy/deepcopy/pickle, forged weakref proxy and inheritance reject. The minimal change closes subclassing after D1 defines its two legitimate proof classes. |
| `test_v1_root_prepolicy_and_plain_v2_objects_cannot_impersonate_d1` | passed | passed | A real signed v1 registry root fails D1's v2 snapshot gate; genuine pre-policy/Stage C batches and plain v2-shaped dictionaries are not D1 proofs. |
| `test_method_or_encoder_replacement_is_rejected` | failed: imported metric `_freeze` global replacement left an existing D1 proof verified | passed | D1 now captures and checks the metric engine recursive freeze binding and its encoder dependency guard. The test also replaces JSON encoder internals and an inherited source batch method, restoring each afterward; all are rejected. |
| `test_source_change_during_final_sweep_revokes_all_d1_children` | passed | passed | A real provider publication increments the epoch at D1's final sweep; failed finalization leaves every prepared D1 child revoked. |
| `test_capability_cannot_be_replayed_across_batch_or_context` | failed: published batch selector returned a revoked child substituted from another batch | passed | The selector now verifies the selected child's own publication, retention and four canonical identity fields against the parent batch. Revoked children stay revoked while the earlier published batch remains valid. |

Initial exact RED command: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_score_input_guards -v`. It ran 7 tests in **481.650 s**, exit 1: 3 expected assertion failures, 2 setup errors, 2 passes. The setup errors were a second fixture with identical deterministic signed root and using frozen `as_of_utc` rather than the provider's canonical cutoff. These were corrected in test code before touching production.

Corrected exact RED command: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_score_input_guards -v`. It ran 7 tests in **933.526 s**, exit 1: **3 failures, 0 errors**. The three failures are the subclass, recursive `_freeze` and cross-batch capability cases above. Four other guards already held and were retained as regression coverage.

Focused exact GREEN command: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_score_input_guards -v`. It ran **7/7 passed, 0 failures/errors/skips in 895.466 s**, exit 0. No API signature, source producer, fixture, Stage C score, peer threshold, or `22+3` readiness logic changed.

## Required combined regression

Command: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_score_inputs tests.test_formal_final_score_input_guards -v`.

**15/15 passed, 0 failures/errors/skips in 4614.137 s; exit 0.** The eight Task 2 tests all printed `ok`: six genuine three-member contracts, the genuine twenty-member ready input with all 22 unchanged base and three Stage C slots, and the independent three-member class-retag seal. All seven Task 3 attack tests then printed `ok` in the same process. This is the complete required combined regression, not a collection of partial runs.

## Environment and performance diagnostics

The first sandboxed exact RED attempt was interrupted after roughly 700 CPU seconds with no test output. It showed the same empty temporary-directory retry pattern described in Task 2's report and is **not** counted as RED, GREEN or a code failure. Subsequent genuine fixture commands were run as single processes with the narrowly escalated test command; no primary-worktree data was touched.

The valid corrected RED took 933.526 s and focused GREEN 895.466 s. The test intentionally builds genuine source batches and repeats one D1 build under a profile hook to inject a real provider publication at the final sweep. These timings alone do not isolate per-member Stage C accessor cost. No private batch snapshot or proof weakening was introduced, because there is no measured accessor-specific performance RED.

## Remaining verification and concerns

Independent review remains coordinator-owned and pending. The standalone seven-case guard suite uses three members; its raw V assertion protects pending proof mutation/impersonation, while the passing combined Task 2 test supplies the genuine 20-peer ready proof. A separate all-policy-evidence twenty-member scenario was not run, consistent with the Task 2 ledger ruling. Repository-wide discovery remains assigned to Task 11 in the ledger. No data, SQLite/WAL/SHM, progress, backup, report or plan file was staged in the implementation commit.

## Fix round 1 — independent review follow-up

Commit base: `377bfe71a1f37c802917f0e005806e225c390e9e`. Fix commit: `2fa7e62a32d612f241356f08277fd97ba7516d6f` (`fix: exercise final input attack boundaries`). The deliverable contains only `ashare_pipeline/formal_final_score_inputs.py` and `tests/test_formal_final_score_input_guards.py`; `git show --format= --name-only HEAD` confirms exactly those two paths and `git show --format= --check HEAD` exited 0. The pre-existing plan and `.superpowers/sdd/.gitignore` worktree edits were left untouched. This report is a sidecar, not a commit deliverable.

The raw-V guard now creates a genuine signed twenty-peer ready D1 row. A test-only producer-backed fixture moves one peer's raw earnings yield to 0.13, placing the focal raw percentile above that peer while its capped Stage C value (0.12) ranks below it. The test verifies the raw base and Stage C percentiles differ, the row is ready with 25 slots, and its embedded genuine Stage C score matches the final slot. It then replaces the published row's frozen slot value with that genuine raw base percentile; both the row verifier and batch selector must reject it. D1 source proofs are read from the publication's retained genuine source tuple, avoiding a second twenty-peer source build. The minimal production change compares a child's current frozen payload encoding with its published canonical bytes in `record()`.

The cross-root test now builds a distinct signed Stage D root with genuine base, policy and valuation source batches, verifies those proofs, swaps its genuine base batch into the current source tuple, and observes the whole-batch identity gate reject it. The capability replay test now publishes a genuine D1 batch from that other root/context, verifies its child before and after substitution, and observes the current batch selector reject the still-valid foreign child. These latter two tests passed before the production edit: the review found test coverage gaps, not failures of the existing identity/publication checks.

### Exact test commands and results

All completed fixture commands below ran one process at a time with narrowly elevated temporary-fixture filesystem access. The initial default-sandbox focused raw command produced no unittest output after over 900 CPU seconds, matching the earlier empty temporary-directory retry pattern; it was interrupted and is not counted as RED or GREEN.

| Phase | Command | Exact result |
|---|---|---|
| Test correction 1 | `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_score_input_guards.FinalScoreInputGuardTests.test_raw_v_percentile_cannot_replace_stage_c_score -v` | Exit 1; 1 test in 2435.801 s, one assertion failure at the test's string-versus-Decimal comparison (`'92.5' != Decimal('92.5')`). The raw/Stage C difference assertion had passed; this was not valid RED. |
| Test correction 2 | Same focused raw command | Exit 1; 1 test in 1568.634 s, one setup error in the test from treating the genuine retained source tuple as a namedtuple (`'tuple' object has no attribute 'base'`). Not valid RED. |
| Valid RED | Same focused raw command | Exit 1; 1 test in 1730.900 s, one expected failure at the rejection assertion: `AssertionError: ValueError not raised` by `row.require_verified()` after the ready raw-V substitution. No errors. |
| Other two baseline guards | `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_score_input_guards.FinalScoreInputGuardTests.test_cross_root_frozen_security_and_source_batch_are_rejected tests.test_formal_final_score_input_guards.FinalScoreInputGuardTests.test_capability_cannot_be_replayed_across_batch_or_context -v` | Exit 0; 2/2 passed in 1231.509 s, no failures/errors/skips. Both new genuine attacks were already rejected before the production edit. |
| Focused GREEN | Focused raw command above | Exit 0; 1/1 passed in 1796.291 s, no failures/errors/skips. |
| Full affected guard regression | `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_score_input_guards -v` | Exit 0; 7/7 passed in 4602.998 s, no failures/errors/skips. All seven exact-name guards printed `ok` in one process, including the twenty-peer ready/raw-V and final-sweep revocation tests. |

`git diff --check` exited 0 (Git reported only worktree LF-to-CRLF conversion warnings). The parent Task 2+3 combined regression, 15/15 in 4614.137 s at commit `377bfe7`, was not rerun for this fix round; it remains historical parent evidence, not a fresh claim. No repository-wide discovery was run. The genuine twenty-peer fixture and repeated source/publication verification dominate runtime; no accessor-specific performance RED was measured and no batch snapshot, peer threshold, 22+3 rule, source revalidation or revocation gate was changed.
