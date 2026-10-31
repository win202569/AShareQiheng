# Task 1 report — genuine Stage D scoring fixture

Status: **DONE**

Commit: `18aa67ed526ca880680b3a62fd8ab72b10d37d5e` (`test: add genuine Stage D scoring fixture`)

## RED

Command: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_fixture -v`

- Initial run: 0 tests executed, 1 import error, 0.000 s reported by unittest. `ModuleNotFoundError: No module named 'tests.formal_final_scoring_fixtures'`, the missing fixture specified by the brief.
- After the coordinator narrowed Task 1's contract test to the smallest genuine three-exchange cohort, the same command was rerun before opening that interface: 0 tests executed, 1 setup error, 0.001 s. `ValueError: Stage D fixture supports 20 or 23 members` from `FinalScoringFixture(peer_count=3)`.

## GREEN and regression

- GREEN command: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_fixture -v` — **2 passed, 0 failed, 0 skipped; 306.553 s**.
- Required regression command: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_fixture tests.test_formal_valuation_integration tests.test_formal_score_inputs tests.test_formal_policy_integration -v` — **21 passed, 0 failed, 0 skipped; 7302.460 s**. This includes the existing 23-member Stage C valuation replay that checks independently rebuilt canonical bytes.
- The successful commands ran with permission to create and remove temporary fixture files inside the assigned worktree. Earlier sandboxed diagnostic attempts could not create the fixture directory and were interrupted; they are not counted as GREEN or regression evidence.

## Changed files

- `tests/formal_final_scoring_fixtures.py` (new): one signed v2 ten-role graph; 25 scoring slots, consensus alternative, actual policy and range evidence, valuation adapter, configurable pending/cap/prohibition/veto/no-coverage and explicit 20/23-member cohorts. The contract tests use a three-member cohort; 20/23-member integration belongs to Task 11 per coordinator ruling.
- `tests/formal_valuation_fixtures.py`: optional default-`None` test-only pre-signature document configurator. The default branch does not call it or alter existing document bytes.
- `tests/test_formal_final_fixture.py` (new): tests shared manifest/frozen/universe/member identities across genuine base, policy and adjusted valuation batches; verifies public proof types and absence of a fixture mint API.

## Self-review

- Reviewed the staged diff and `git diff --cached --check` (clean); the commit contains exactly the three Task 1 test files and no production module.
- Proofs are created only through the real repositories. `build_d1_sources()` returns their public proof instances and calls `require_verified()` in the tests; no plain proof double or fixture mint method is exposed.
- The test-only callback runs before signing only when supplied. Existing fixture regression passed, including the independent canonical-byte replay.
- Removed four exact temporary fixture directories left by interrupted diagnostics after verifying their paths under the worktree's test temp root. The temp root contains no remaining fixture subdirectories; `git status --short` was clean after commit.

## Concerns

No functional concerns in Task 1. The required existing integration regression is expensive (7302.460 s); full 20/23-member Stage D scenario validation is reserved for Task 11.

## Fix round 1 — focal full-feature trustworthiness

Status: **DONE**

Fix commit: `c91dac09292de22c31e525f6a67ffd245101f4f3` (`test: make Stage D focal features trustworthy`). This is separate from the original Task 1 commit.

### RED and root cause

- Added `test_focal_full_feature_bundle_has_trustworthy_required_slots` before changing the fixture. Command: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_fixture.FinalScoringFixtureTests.test_focal_full_feature_bundle_has_trustworthy_required_slots -v` — **0 passed, 1 failed, 0 skipped; 329.427 s**. `bundle.blockers` was `('quarter_missing_prerequisite',)` instead of `()`.
- Changed only the three V toy leaves to instant and reran the same command: **0 passed, 1 failed, 0 skipped; 354.012 s**, same blocker. This isolated another source: 2024/2025 duration FY policy facts from the real policy producer lacked matching Q1/H1/Q3 prerequisites. Quarter derivation scans every selected recent duration FY family, independent of the Stage D feature formula using that family.
- An attempted signed-quarter-mapping addition was rejected by the existing mapping registry's duplicate-source-field rule during setup: **0 tests, 1 setup error; 221.618 s**. That addition was removed; the signed mapping and production quarter contract remain unchanged.

### GREEN and scope

- Focused command above — **1 passed, 0 failed, 0 skipped; 422.346 s**. FOCAL's genuine full bundle has no blockers and all 25 required Stage D slots are `derived`.
- Task 1 exact command: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_fixture -v` — **3 passed, 0 failed, 0 skipped; 417.513 s**. The shared-root and verified-proof tests still pass.
- Per coordinator direction, the prior four-module 7302.460-second regression was not rerun for this fix. The original Task 1 result remains recorded above; subsequent Task 2 and source-regression work will cover the changed fixture's downstream use.

### Changed files and self-review

- `tests/formal_final_scoring_fixtures.py`: V toy leaves now use instant nature. The fixture adds genuine verified source snapshots, formal tasks, and provenance-backed Q1/H1/Q3 policy facts with the same family, units, parser, and mapping version as the duration FY policy facts. No public proof minting, plain proof double, production module, or default `ValuationRuntimeFixture` behavior changed.
- `tests/test_formal_final_fixture.py`: regression assertion checks no full-bundle blockers and all 25 required slots derived.
- Reviewed the two-file staged diff; `git diff --cached --check` passed, and only these two files were staged and committed. Task 2's unrelated working-tree changes were preserved.

Concerns: No known functional concern in this fix. The requested full four-module regression was intentionally not repeated in this round.
