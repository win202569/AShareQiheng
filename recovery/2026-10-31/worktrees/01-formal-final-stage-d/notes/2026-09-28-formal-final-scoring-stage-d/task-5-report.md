# Task 5 implementation report

## Scope

- Baseline: `3916065333df1a7c2686185c5d1f0dbde7b75915`.
- Changed for commit: `ashare_pipeline/formal_final_eligibility.py`, `tests/test_formal_final_eligibility.py`, `tests/test_formal_final_eligibility_guards.py`.
- Genuine fixture: existing signed 23-member `shared_ready_batch()` D1→D2 proof chain from `tests.test_formal_final_scoring`; no plain D1/D2 doubles.

## RED → GREEN

- RED command: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_eligibility tests.test_formal_final_eligibility_guards -v`.
- RED result: exit 1; both test modules failed to import because `ashare_pipeline.formal_final_eligibility` did not exist.
- Additional state branch RED: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_eligibility -v` exited 1 because `_state_for` was absent; it was added only after this failure.
- Initial GREEN attempt: the original implementation remained inside setup with no test-case line for approximately 126 minutes. Its exact test process (PID 17272) was stopped for excessive runtime while CPU kept increasing; the exact terminal CPU value was not captured. This is a performance diagnostic, not a pass or an assertion failure.
- Second full attempt: the first per-proof-read optimization also produced no test-case line after more than 136 minutes. Its exact process (PID 25268) was stopped per coordinator ruling while CPU kept increasing; the exact terminal CPU value was not captured. It is a performance diagnostic, not GREEN.
- Narrow genuine 3-member command: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_eligibility.SmallGenuineEligibilityTests -v`; PID 2232 was stopped under the coordinator's 90-minute limit with no first test-case output. CPU rose beyond 4,762 seconds, and working set stayed around 36 MiB. Exit 1 is a deliberate interruption, not a test assertion result or GREEN evidence.
- Lightweight command: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_eligibility.PureEligibilityRulesTests tests.test_formal_final_eligibility_guards.PureEligibilityGuardTests -v`; exit 0, 6 tests passed in 0.003 seconds; rerun after self-review also exit 0, 6 tests passed in 0.001 seconds. These check state priority, exact Decimal neighbors, public type rejection, and proof forgery rejection without a D1/D2 fixture.
- Final full GREEN command: not run after the genuine 3-member diagnostic; genuine scored/vetoed behavior remains unverified in this version.

## Coverage and limitations

- Genuine batches verify source identity, complete card/pending partition, member hashes, status, policy flags, immutable ordering values, and ordinary-A scope.
- Pure Decimal threshold tests check equality and both immediate neighbors for all seven boundary values. The pure state table checks pending priority, hard veto, both prohibitions, and single-pool prohibition.
- A genuine ready hard-veto member is not yet exercised by this fixture; the corresponding state branch is exercised by the pure state table. The fixture does exercise genuine ready and pending members.

## Performance diagnosis

- The existing 23-member fixture and D3b construction together produced no test-case line for approximately 126 minutes in the initial run, while Python CPU increased and memory stayed around 35 MiB. That run did not instrument the boundary between fixture setup and D3b construction, so the individual costs cannot be attributed precisely.
- Coordinator ruling after the second long run: keep exact genuine D1/D2 root, frozen universe, membership, hash, capability, selector identity, and revocation checks; derive D3b from a read-only canonical batch snapshot parsed once.
- The resulting implementation authenticates each whole batch and its exact D1→D2 source instance, rechecks root/frozen/universe/membership/hash closure, and compares each genuine selector's canonical bytes against its batch snapshot once. Derivation then reads only frozen rows from those verified bytes. Repeated eligibility access still verifies both live source batches and exact canonical bytes, but does not replay member selectors. No caller DTO acquires proof authority. Decimal reconstruction from canonical text preserves the exact values and resulting status/hash semantics.
- Static call-graph review after the 90-minute narrow run: fixture population precedes D1, whose `build_batch` rebuilds base, policy, and valuation source batches, then produces and revalidates per-member/per-metric peer proofs; D2 production follows, and only then D3b. D3b itself has one D1 and one D2 canonical DTO snapshot, one authentic selector call per member and a linear derivation loop. Before the snapshot, D3b still makes repeated batch proof calls (`require_verified`, private D2 source record, `canonical_bytes`, `to_dict`, `security_ids`, `batch_hash`); each D2 record revalidates D1. These are a candidate small de-duplication, but no phase timing was captured, so elapsed time cannot be attributed conclusively to D1/D2 versus D3b. No further source optimization was made after this review.

## Self-review concern

- The D2 private-record/source-identity helper is currently module-scoped in D3b. A hostile caller able to monkeypatch D3b's module globals could replace that helper; no genuine-proof behavior test of this attack was completed. A closure-capture hardening was considered and reverted before verification, following the TDD ruling against an untested speculative security change.

## Commit

- `e530dac` (`feat: derive formal score eligibility`) contains exactly the three Task 5 source/test files. `git diff --cached --check` was clean before the commit. The report and pre-existing `.superpowers/sdd/.gitignore` and plan changes are excluded.
- Independent review and genuine integration GREEN remain outstanding; the commit must not be represented as fully verified.

## Review fix round 1

- Critical root cause: D2 batch `cards` contain raw payload rows. `score_batch_hash` is added only to each sealed card proof during D2 `mint`; the old D3b ready branch indexed that absent key and would raise `KeyError`. The existing D3b selector check already compares each genuine card proof's canonical bytes with its batch row plus the D2 batch-level `score_batch_hash`; the fix leaves that card-hash/source-identity check intact and validates the row's D1 entry hash, D1 batch hash, security ID and secondary industry without reading the proof-only field.
- Genuine ready RED command: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_eligibility.ReadyCardProvenanceRegressionTests.test_genuine_ready_card_builds_eligibility_from_batch_score_hash -v`. The process (PID 50252) was stopped under the coordinator's 90-minute window without a first test-case line; CPU reached at least 4,995.98 seconds and memory remained around 34 MiB. Exit 1 was the deliberate interruption. This run is a non-evidence RED performance diagnostic: it did not reach the expected `KeyError`, nor prove ready GREEN.
- Lightweight card-row RED: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_eligibility_guards.PureEligibilityGuardTests.test_ready_batch_card_row_uses_bound_source_without_proof_only_score_hash -v` exited 1. An initial draft errored for the absent helper; after changing the test to a clear failure, the definitive RED was 1 FAIL (`_validate_ready_card_provenance` absent). After the minimal row-validation extraction, the same command exited 0, 1 test passed.
- Important root cause: the old `_d2_source` resolved a module-level `_D2_RECORD`, and the D3b builder resolved module-level `_d2_source`; replacing either could falsify the same-hash D1 publication identity check. Lightweight authority RED command: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_eligibility_guards.PureEligibilityGuardTests.test_module_record_swap_cannot_authorize_nonproof_source tests.test_formal_final_eligibility_guards.PureEligibilityGuardTests.test_module_source_helper_swap_cannot_rebind_builder_authority -v` exited 1 with 2 expected FAILs: a swapped record accepted a non-proof source, and the builder had no captured checker. The fix captures D2's genuine record capability and the checker inside `_install_eligibility`; module-global swaps no longer alter the builder's authority.
- Final narrow command: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_eligibility.PureEligibilityRulesTests tests.test_formal_final_eligibility_guards.PureEligibilityGuardTests -v` exited 0, 9 tests passed in 0.003 seconds. This covers pure state/Decimal boundaries, row-level provenance and module-swap guards, not genuine ready/scored or mismatched-publication integration. Per coordinator ruling the genuine ready fixture was not rerun after timeout; no scored GREEN claim is made.
- Fix-round commit: `caa5306d783083d4695847b21cde47ab3d54955f` (`fix: bind eligibility scorecard provenance`). Fresh pre-commit narrow verification was again 9/9 in 0.003 seconds; staged `git diff --cached --check` exited 0, and `git show --stat` confirms exactly the three Task 5 files. The report remains excluded from commit. Genuine ready/scored GREEN and the full Task 5 suite remain outstanding because the signed fixture did not finish inside the performance window.
