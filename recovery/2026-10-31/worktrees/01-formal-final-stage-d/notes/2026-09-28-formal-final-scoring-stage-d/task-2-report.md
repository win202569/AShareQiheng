# Task 2 report — policy-adjusted final score inputs

Status: **DONE** (2026-09-29 02:37 UTC). Implementation and required scoped verification complete; independent Task 2 review remains coordinator-owned.

Commit: `1a10a41aff3116b49ee2cba972f4e461050fc195` (`feat: compose policy-adjusted final score inputs`). Parent commit: independently repaired/reviewed fixture `c91dac09292de22c31e525f6a67ffd245101f4f3`.

## Scope and changes

- New `ashare_pipeline/formal_final_score_inputs.py`: closure-owned D1 entry/batch/repository, complete frozen membership, hashed pending entries, genuine base/policy/valuation composition, source identity and publication revalidation, and mint-time proof-type seal.
- New `tests/test_formal_final_score_inputs.py`: four genuine 3-member contract tests, one genuine 20-member ready-content test, and one genuine 3-member class-retag regression.
- No other implementation files changed. The pre-existing `.superpowers/sdd/.gitignore` modification remains untouched. This report is not a staged deliverable.

## RED evidence

Initial command:

`& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_score_inputs -v`

- Expected missing production module observed: `ModuleNotFoundError: No module named 'ashare_pipeline.formal_final_score_inputs'`.
- 0 actual tests executed, 1 loader error; unittest 0.000 s, command wall time 0.559 s.

Additional coordinator-approved type-seal RED:

`& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_score_inputs.FinalScoreInputTypeSealTests -v`

- 0 passed, 1 failed, 0 skipped; **337.198 s**.
- Expected failure: `AssertionError: ValueError not raised` after a genuine minted entry was relabelled as its sibling batch type with `object.__setattr__`.
- Minimal subsequent production fix stores and verifies mint-time class identity. No recursive-freeze change was included.

## Earlier exact test failure (before fixture repair; not GREEN)

Command:

`& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_score_inputs -v`

- **5 passed, 1 failed, 0 skipped; 3927.714 s**; exit 1.
- The four 3-member contract tests passed. Observed phase interval: approximately **779–833 s**, including genuine source preparation and replay (start 21:14:13 UTC; transition observed between 21:27:12 and 21:28:06 UTC).
- The 20-member default-pending scenario failed at `row.status == 'ready'`: FOCAL was `pending_evidence`. The earlier assertions for complete 20-member enumeration, 19 peers' D1 policy-pending entries, and their genuine Stage C `passthrough_not_applicable` inputs passed. Observed ready phase interval: approximately **2670–2784 s** (transition to the last test observed between 22:12:36 and 22:13:36 UTC).
- The final 3-member class-retag regression passed. Its observed phase duration was approximately **365–425 s**, based on the preceding polling interval and the exact command total.
- Phase timings are polling-derived intervals, not independently timed test invocations. No extra expensive runs were started solely to measure phases.

## Failure investigation and resolved scope blocker

A single-process genuine 3-member fixture diagnostic populated the existing fixture and inspected FOCAL's full feature bundle, without minting any D1 proof. It returned:

- `blockers = ('quarter_missing_prerequisite',)`.
- FY history 2021–2025 and comparable quarter keys from 2024Q1 through 2026Q2 were present.
- All 25 scoring slots and policy slots were `blocked` with `feature_input_not_trustworthy`.

The D1 pending result therefore preserves the real base-input business gap. Static tracing identifies the earlier fixture's synthetic V leaves being written as duration facts without matching quarter prerequisites as the candidate origin; the established complete-score fixture writes toy scoring leaves as instant facts. No production gate or peer threshold was relaxed.

Coordinator confirmed a load-bearing Task 1 fixture defect and paused Task 2. The original Task 1 implementer repaired it with TDD in `c91dac09292de22c31e525f6a67ffd245101f4f3`: synthetic V leaves are instant facts and actual policy duration series receive genuine quarter prerequisites. Coordinator reported independent review verdict ADDRESSED with no new Critical/Important findings, then explicitly resumed Task 2. The shared branch was verified to contain that commit before rerunning; neither Task 2 code file needed another change. D1 was never allowed to bypass the full-bundle blocker.

## Final exact GREEN

Command:

`& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_score_inputs -v`

- **6 passed, 0 failed, 0 skipped; 4641.582 s**; exit 0.
- Began approximately 2026-09-28 23:08:12 UTC; completion observed 2026-09-29 00:25:35 UTC.
- Four genuine 3-member contract tests: approximately **995–1049 s**, including preparation and replay; transition to ready observed between 23:24:47 and 23:25:41 UTC.
- Genuine 20-member ready test: approximately **3096–3255 s** from polling bounds. Last pending observation was 00:17:17 UTC; ready PASS and transition to the last test were observed at 00:19:02 UTC.
- Separate genuine 3-member class-retag regression: approximately **392–497 s** from those polling bounds and the exact command total.
- Full 20-member enumeration was preserved. FOCAL is ready with exactly 22 unchanged genuine non-V slots and three genuine Stage C score/context/hash sets, adjusted earnings yield `0.12`, percentile `97.5`, and peer count `20`. Other 19 members remain D1 policy-pending while their Stage C inputs are genuine `passthrough_not_applicable` peers.
- Per-size durations are observation intervals rather than independently instrumented test durations; the complete command duration above is the exact unittest result. No extra timing-only test runs were performed.

## Required source regression

Exact command:

`& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_score_inputs tests.test_formal_policy_repository tests.test_formal_valuation_batch tests.test_formal_valuation_ranking -v`

**55 passed, 0 failed, 0 skipped; 7704.359 s**; exit 0. Began approximately 2026-09-29 00:25:44 UTC only after exact GREEN finished; completion observed at 02:34:11 UTC. Module counts: score inputs 14, policy repository 20, valuation batch 2, valuation ranking 19. This was one sequential process, including the existing genuine 20-member and 23-member source acceptance fixtures. No full-repository discovery was run.

## Non-evidence diagnostics

- Three initial sandboxed test attempts could not create usable temporary fixture directories and spun in temporary-directory retries. All were explicitly interrupted. They are environment diagnostics, not GREEN or regression failures.
- An earlier 20-member `pending_ids=()` all-policy-evidence baseline was proactively terminated by coordinator instruction after more than two hours because that heavyweight scenario was superseded. Its first four contract tests had passed, but the incomplete run is not counted as GREEN or a functional test failure.
- The first inline diagnostic command had a PowerShell quoting/SyntaxError before fixture execution; it was corrected and is not test evidence.
- Effective tests used elevated filesystem permission solely for temporary fixture creation/cleanup in the authorized worktree. No concurrent test processes remain active.
- Coordinator-authorized cleanup removed only the exact abandoned old-baseline directory `.tmp/formal-feature-store-tests/tmp9y07k9v4`, after verifying its resolved path remained under this worktree's test-temp root, that it was not a reparse target, and that all recorded Task 2 test processes had ended. These disposable generated fixture files were deleted (not placed in a recoverable trash); no other temporary directory was touched.

## Self-review

- D1 enumerates every canonical frozen member; business gaps remain typed proofs with entry hashes, never `None`.
- Three genuine source batches must close over root, frozen identity, universe, membership, policy, industry, and valuation identities; structural mismatch rejects publication.
- A ready entry requires 22 unchanged non-V base slots and three genuine Stage C score/context/hash sets. Policy pending cannot be removed by cap/veto.
- Registry and source canonical bytes are revalidated before publication; genuine provenance chains are retained.
- Mint-time type identity is now covered by observed RED and passing regression.
- No Task 3 attack matrix, D2 implementation, plain score doubles, direct source-proof minting, or lowered production requirements were introduced.
- Reviewed the final production file and tests against the brief. `git diff --cached --check` passed. Staged and committed scope is exactly the two Task 2 files: 365 production lines and 158 test lines. Post-commit SHA and file list were verified.
- No data, SQLite/WAL/SHM, progress, backup, report, fixture-repair, or pre-existing `.gitignore` change was included in the commit. The only remaining tracked worktree change is the original unrelated `.superpowers/sdd/.gitignore` modification.

## Concerns

1. Full repository `unittest discover` was explicitly not run; coordinator reserves full Stage D and affected-suite verification for Task 11. Exact Task 2 and all four specified source regression modules did pass.
2. Complete dynamic helper/encoder and lifecycle attack coverage belongs to Task 3. In particular, imported metric `_freeze` recursively resolves its original module-global `_freeze`; this transitive dynamic-binding concern was identified and deliberately not changed without its coverage, per coordinator instruction.
3. Genuine end-to-end tests are expensive. Static inspection indicates repeated real source builds and peer-context canonical validation can introduce superlinear work; this is an inference, not a profiler result. No performance bypass or unrelated optimization was introduced. Phase intervals and terminated diagnostics are separated from valid evidence above.
4. The earlier fixture defect is resolved by the separately reviewed predecessor commit; no remaining Task 2 functional blocker was observed in the required tests. Independent Task 2 review is for the coordinator; no subagent or reviewer was spawned by this implementer.

## Independent review fix round 1 — pending member identity

Status: COMPLETE. Parent implementation commit: `1a10a41aff3116b49ee2cba972f4e461050fc195`. Fix commit: `c7a71c28e3447758fad6a23b3d4789f75f2c5177`.

Important finding confirmed: when the genuine base repository returns no input for a business-pending member, D1's empty initial payload omitted `template_id`, `primary_industry`, and `secondary_industry`.

Coordinator ruling: the minimal coverage combines a public pending-entry test and an internal per-member identity-check test with genuine conflicting inputs. A same-root/frozen normal producer chain cannot naturally yield that conflict without source-proof forgery or dynamic method replacement. The internal closure must be called by the actual public composition path. Public-boundary dynamic injection is explicitly deferred to Task 3, rather than introducing its attack matrix here.

### RED

Command:

`& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_score_inputs.FinalScoreInputContractTests.test_pending_without_base_retains_authenticated_member_identity tests.test_formal_final_score_inputs.FinalScoreInputContractTests.test_member_identity_rejects_inconsistent_genuine_valuation_inputs -v`

Result: **2 tests, 0 passed, 1 assertion failure, 1 error, 0 skipped; 751.664 s; exit 1**. The public test first establishes that each base input is `None` and its D1 row is pending; the first member then fails because `template_id` is absent. The internal test errors with `KeyError: 'member_identity'` because the new composition closure does not yet exist. Production code was unchanged until this observed RED. The failure output contained a long genuine policy payload; its diagnostic message, exit, counts and exact unittest duration were visible.

### Implementation and verification scope

Only the two Task 2 code files are changed. A private composition closure derives all three identity fields from the authenticated policy industry's member entry, re-verifies all three genuine adjusted V inputs and any available genuine base input, rejects disagreement before publication, and fills those fields regardless of business readiness. An unresolved industry identity is represented by explicit `None` fields consistently with its valuation inputs, not by absent keys. No scoring, peer threshold, 22+3 readiness, source-batch verification, proof minting or registry policy was relaxed.

The internal test passes actual different-member genuine V inputs one metric at a time and explicitly confirms their secondary industry differs. It does not mint or mutate proof objects. The public test checks all three fields for every pending member without a base input.

Risk-based GREEN command (one sequential process):

`& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_score_inputs.FinalScoreInputContractTests tests.test_formal_final_score_inputs.FinalScoreInputTypeSealTests -v`

Result: the first six genuine 3-member contract tests each printed `ok`, including the two new tests, complete membership/source binding/business pending/replay. That process did not produce a final seven-test summary before it ended, so it is not represented as a complete GREEN run.

Final class-retag GREEN was run separately in one process:

`& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_score_inputs.FinalScoreInputTypeSealTests -v`

Result: **1 passed, 0 failed, 0 skipped; 199.333 s; exit 0**. Together with the six individually observed `ok` results, this completes the seven intended risk-based cases, but no single seven-test command is claimed to have completed. The tests use genuine fixture builds and no mocks. The public pending test asserts identity fields on every pending D1 entry with `original is None`; the conflict test passes genuine adjusted V inputs from a different member to the same private closure that the public `build_batch` calls. No proof is minted or altered by either test.

This fix round did not rerun the expensive 20-member ready test or the four source modules (55 tests). Their passing results above belong to the parent commit and are carried forward as prior evidence, not fresh fix-commit results. The fix changes identity extraction/comparison and serialization but neither the source implementations nor valuation/ranking/slot algorithms. Full discovery remains reserved for Task 11. The test temporary root was inspected after the final run and contained no child directories or files attributable to this round; no cleanup was necessary.

Post-commit verification: `git diff --cached --check` passed before committing. The commit contains exactly `ashare_pipeline/formal_final_score_inputs.py` and `tests/test_formal_final_score_inputs.py` (48 insertions, 2 deletions). The only tracked worktree change left is the pre-existing `.superpowers/sdd/.gitignore` modification. The report, data, SQLite/WAL/SHM, progress, backups and `.gitignore` were excluded.
