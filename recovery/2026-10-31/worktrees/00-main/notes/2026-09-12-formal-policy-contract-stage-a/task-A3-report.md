# Task A3 implementation report

Status: DONE after fix round 1. Original acceptance evidence is retained below; corrected frozen-file evidence is appended at the end. Independent review and commit remain controller-owned.

Worktree: `D:/Projects/AShareQiheng/.worktrees/formal-v3-implementation`.
Base: `6ea72c16ba206cdf69f5f1ac6aaaa9a1258fd670`.
Python: `D:/Projects/AShareQiheng/.venv/Scripts/python.exe`.

## Scope and implementation

Read the complete active task brief and the approved specification at `docs/superpowers/specs/2026-09-12-formal-policy-contract-design.md`, plus the actual A2 binder, relevant source verification paths and the existing `formal_scoring.py` proof pattern. Used executing-plans, test-driven-development (including writing-good-tests), and verification-before-completion guidance within the controller's explicit ownership limits.

Only implementation/test edits:

- `ashare_pipeline/formal_policy_registry.py`: retain the actual A2 binder; add a local closure-private proof loader, immutable payload freezing, explicit dependency/owner checks, source reauthentication, guarded field/method access, and weak-reference ownership.
- `tests/test_formal_policy_registry_guards.py`: 17 distinct tests covering public serialization and immutability, copies/forgeries/subclasses, source and dependency mutations, protected inheritance/lookup, no policy parsing during reads, construction-time invalidation, garbage collection, and definition-versus-runtime boundaries.

`canonical_bytes()` remains byte-for-byte A2 output. `contract_hash` is its SHA-256, exposed as a read-only field and in the detached `to_dict()` result, never inserted into the hashed bytes. The fixed public field whitelist contains A2 fields plus that hash. No instance payload slots or public reconstruction/mint API exist. Copy, deep copy and pickle reconstruction are rejected.

`dependencies()` checks the actual owner bindings used by the policy parser, binder, feature parsing and source verification, plus local aliases and the used JSON/hash/freeze/weakref dependencies. Upstream class checks are limited to methods and record fields on those call paths, with MRO/bases checks. All members and inheritance of the new proof classes are checked. The original source verifiers are captured and called directly. `verify_sources()` authenticates the exact bundle/scoring/feature types and all nine roles, hashes actual root/child bytes, and compares feature canonical/source/mapping identities against the current root.

Reads authenticate sources but do not invoke the policy parser or binder. Scoring's existing verification already checks all five feature slot sets; A3 does not add another all-template slot loop. It authenticates the supplied feature once before reading its actual sealed scalar identity fields. Source objects are historical signed definitions; no database generation is invented.

The loader checks sources before binding and again before registration. Its weakref cleanup captures the object's ID, compares the callback reference to the current record, and removes only that record. It never strongly retains its proof object. The result retains source objects for historical audit.

## TDD and verification evidence

All commands below ran from the worktree above. Commands are shown exactly with the supplied interpreter path. No environment/import problem other than the expected absent A3 API was counted as RED.

1. RED, before production implementation:

   `& 'D:/Projects/AShareQiheng/.venv/Scripts/python.exe' -m unittest tests.test_formal_policy_registry_guards.PolicyProofTests -v`

   Exit 1. `Ran 1 test in 0.000s`, `FAILED (errors=1)`; command wall time 0.455s. The error was exactly `ImportError: cannot import name 'FormalPolicyRegistry' from 'ashare_pipeline.formal_policy_registry'`, the absent A3 public API. All guard tests had already been written in the new file.

2. Initial public API GREEN:

   `& 'D:/Projects/AShareQiheng/.venv/Scripts/python.exe' -m unittest tests.test_formal_policy_registry_guards.PolicyProofTests -v`

   Exit 0. `Ran 3 tests in 28.081s`, `OK`.

3. Initial guard GREEN:

   `& 'D:/Projects/AShareQiheng/.venv/Scripts/python.exe' -m unittest tests.test_formal_policy_registry_guards.PolicyProofGuardTests -v`

   Exit 0. `Ran 17 tests in 133.602s`, `OK`. This initial test-class hierarchy repeated the 3 public API cases. The final test file factors shared graph setup into a test-free base, leaving 3 public API tests and 14 distinct guard tests. The final acceptance command below covers the refactored test file and narrowed upstream dependency checks.

4. Final policy acceptance:

   `& 'D:/Projects/AShareQiheng/.venv/Scripts/python.exe' -m unittest tests.test_formal_policy_contract tests.test_formal_policy_registry tests.test_formal_policy_registry_guards -v`

   Exit 0. `Ran 85 tests in 265.594s`, `OK`: unchanged A1/A2 68 tests plus final A3 17 tests (3 public API and 14 guard tests). No failures or errors.

5. Required legacy regression:

   `& 'D:/Projects/AShareQiheng/.venv/Scripts/python.exe' -m unittest tests.test_formal_registry_manifest tests.test_formal_feature_contract tests.test_formal_scoring_registry tests.test_formal_scoring_consensus_registry tests.test_formal_context_schema -v`

   Exit 0. `Ran 72 tests in 30.284s`, `OK`. These are the specified legacy modules; no additional runtime fixture/database suites were needed.

6. Final whitespace check:

   `git -c safe.directory=D:/Projects/AShareQiheng/.worktrees/formal-v3-implementation diff --check`

   Exit 0, wall time 0.181s. No whitespace errors. Git printed its existing LF-to-CRLF working-copy conversion warning for the edited registry file.

## Final file identities

SHA-256 from `Get-FileHash -Algorithm SHA256 -LiteralPath 'ashare_pipeline/formal_policy_registry.py','tests/test_formal_policy_registry_guards.py'`:

| File | SHA-256 |
| --- | --- |
| `ashare_pipeline/formal_policy_registry.py` | `035f40f873da565d4f569f44fd1a7169aff1d04b739197e1fa184c8c8fc08af7` |
| `tests/test_formal_policy_registry_guards.py` | `3194aa2976f20fa0ed92f5ada24abeede4b2b9c8e87af6a7346ce9f3bfb66189` |

The final source content differs from the version imported by the acceptance process only by a two-line explanatory comment correction ("runtime introspection" was replaced with the precise description "inferring a dependency graph"). No executable code changed after that acceptance run started. The source and test files are frozen for controller review.

Read-only Git confirmation: branch is `codex/formal-v3-implementation`; index is empty; tracked modifications contain only the owned registry file; the new guard test and pre-existing `tmpj4zv9_fq/` are untracked. This report lives in the ignored task workspace. No Git write was performed.

## Self-review and concerns

- Requirements checked: three exact genuine inputs, same-root content binding, all-nine-role verification, immutable definitions, detached serialization, fixed extra hash field, guarded reads, ordinary dependency/member replacement checks, copy/reconstruction denial, source failure during loading, and proof garbage collection.
- The tests use real signed policy graphs and restored mutations; they do not add a fixture-only mint. A profile-based read test observes the real parser/binder functions without replacing them, confirming reads do not reparse policy rules. A second profile-based test mutates a source at binder return and verifies construction fails before publishing a proof.
- Runtime boundaries remain explicit: no actual security, financial observation or market values are required to authenticate definitions; market-window and valuation-adapter identities remain declarations. The original `calculate_pre_policy_score` rejects the new registry, parsed contract, detached rule, binding bytes and detached dictionary. No evaluate/apply/score/readiness/pool eligibility API was introduced.
- The checked threat boundary is ordinary Python module/type/method/attribute replacement and mutated source records, following the approved pattern. This is not protection against arbitrary interpreter or metaclass internals being rewritten.
- Source authentication still invokes the existing feature/scoring verification paths, so reads have their existing validation cost. No cached source-authentication bypass or new runtime evidence claim was introduced.
- No production module outside the owned registry file changed. No dependency installation, network, SQLite/data mutation, Git write/commit, subagent/reviewer creation, or unrelated cleanup occurred. The pre-existing `tmpj4zv9_fq/` remains untouched. The controller owns independent review, staging, commit and final HEAD/index checks.
- No unresolved requirement gap identified in self-review. All requested worker acceptance checks passed. Independent controller review and commit are the remaining handoff steps.

## Independent review fix round 1 — missing exchange owner binding

Read the complete independent finding in `task-A3-review-result.md` and checked the actual `formal_sources._require_exchange` implementation. The finding is valid: its defining module's `_EXCHANGES` constant is read by the captured calendar-selector descriptor path but was absent from A3's explicit owner-binding inventory. The original self-review did not identify that omission. Applied receiving-code-review and the existing TDD/verification guidance to this narrowly scoped correction.

The production fix adds only `_EXCHANGES` to the existing `vars(sources_module)` binding list. The new restored-mutation regression first loads and verifies the real signed graph, replaces the exchange set with `frozenset({'SH', 'SZ', 'BJ', 'FAKE'})`, requires every existing proof read and new loading to raise `ValueError`, then restores the original binding and verifies both the old proof and a newly loaded proof. No source module, public API, rule grammar, economic rule, source-verification path or threat boundary was redesigned.

### Focused TDD evidence

Exact command, run once before and once after the one-binding production fix:

`& 'D:/Projects/AShareQiheng/.venv/Scripts/python.exe' -m unittest tests.test_formal_policy_registry_guards.PolicyProofGuardTests.test_replaced_exchange_enum_invalidates_reads_and_loads_until_restored -v`

- RED: exit 1; `Ran 1 test in 1.227s`, `FAILED (failures=1)`; wall time 1.718s. The authentic old proof did not raise `ValueError` after `_EXCHANGES` replacement (`AssertionError: ValueError not raised`). This was a behavioral regression reproduction, not an import/environment failure.
- GREEN: exit 0; `Ran 1 test in 1.976s`, `OK`; wall time 2.437s. The test covers all existing public reads and new loading during replacement, and recovery of old/new proofs after restoration.

### Frozen-fix final verification

Source and test files were frozen before both final commands started. These runs use the corrected module and 18 distinct A3 tests; they are separate from the controller's concurrently running pre-fix 85-test process. No production or test edit is planned during these runs.

1. `& 'D:/Projects/AShareQiheng/.venv/Scripts/python.exe' -m unittest tests.test_formal_policy_registry_guards -v`

   Exit 0. `Ran 18 tests in 125.243s`, `OK`. This is the complete guard/public API suite on the frozen corrected files, including the new exchange-enum replacement regression.

2. `& 'D:/Projects/AShareQiheng/.venv/Scripts/python.exe' -m unittest tests.test_formal_policy_contract tests.test_formal_policy_registry tests.test_formal_policy_registry_guards -v`

   Exit 0. `Ran 86 tests in 275.907s`, `OK`: unchanged A1/A2 68 tests plus corrected A3 18 tests. No failures or errors. This run imported the exact frozen corrected files identified below; no source/test edits occurred during the run.

The unaffected 72-test legacy suite was not rerun, as explicitly directed by the controller; its prior passing evidence remains above. This fix only detects replacement of an existing binder dependency and changes no upstream behavior.

Final corrected file identities (SHA-256):

| File | SHA-256 |
| --- | --- |
| `ashare_pipeline/formal_policy_registry.py` | `4dd60dd588e4f19deae5e9c7e378237c774610ac2c35cad158eaa67b4ec080b3` |
| `tests/test_formal_policy_registry_guards.py` | `67f8685add176becac44994bd02d870a83ff7e03bfb260dbe5ce5989f393e594` |

`git -c safe.directory=D:/Projects/AShareQiheng/.worktrees/formal-v3-implementation diff --check` exited 0 in 0.237s, with no whitespace errors (only Git's LF-to-CRLF conversion warnings for the two owned files). Frozen file hashes were reconfirmed unchanged after the guard run.

No Git writes, upstream edits, agents, network/SQLite/data actions or unrelated cleanup occurred in this fix round. The independent finding is addressed and all requested corrected-file acceptance checks passed. No additional concerns identified in this narrow fix; controller re-review and commit remain controller-owned.
