# Task W1 implementation report

## Outcome

Implemented W1 calendar coverage, proof-driven market range acquisition, independent
market/veto evaluation, and next-request planning within the amended 13-path
code/test whitelist. No production data, network access, crawling, scoring, pool
generation, Git staging, commit, merge, or push was performed.

## TDD evidence

### RED

Command:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_market -v
```

- Exit code: `1`
- Result: `Ran 10 tests in 0.006s`; all exercised paths failed because
  `ashare_pipeline.formal_policy_market` did not exist (`ModuleNotFoundError`).
- Tool wall time: `1.744s`.
- This was the genuine pre-implementation RED; production code was not altered to
  manufacture it.

### Focused implementation checks

- `tests.test_formal_policy_market`: an intermediate run reached 9/10 with one
  test-placement error (`512.679s`, exit `1`); after the minimal correction,
  10/10 passed in `577.497s`, exit `0` (tool wall `578.917s`).
- `tests.test_formal_range_contract`: 17/17 passed in `22.317s`, exit `0`.
- `tests.test_formal_range_source`: 32/32 passed in `312.701s`, exit `0` during
  development. A temporary extra source test was later removed to restore the exact
  whitelist; the unchanged authorized module was rerun at the end, 31/31 in
  `191.626s`, exit `0`.
- `tests.test_formal_policy_values`: 22/22 passed in `15.346s`, exit `0`.
- New Store resolution tests: 2/2 passed in `10.548s`, exit `0`.
- New Worker market-budget test: 1/1 passed in `99.618s`, exit `0`.
- Full Store compatibility: 32/32 passed in `1691.747s`, exit `0`.
- Initial full Worker compatibility: 24 tests in `1245.539s`, exit `1`, with two
  errors at the same locus: a reconstructed genuine request binding was rejected
  by source object identity. The fix compares the complete owner-authenticated
  semantic binding identity while retaining Store-owned same-store/root checks.
- Targeted Worker regression rerun: 2/2 passed in `324.451s`, exit `0`.

One early focused market process was stopped during test-fixture diagnosis. The
duration came from repeatedly authenticating the same signed binding while producing
hundreds of calendar rows, not from production acquisition. The fixture now snapshots
that authenticated base row once before generating rows.

### Expanded W1 GREEN

Command:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_range_contract tests.test_formal_range_source tests.test_formal_range_store tests.test_formal_range_worker tests.test_formal_policy_values tests.test_formal_policy_market tests.test_formal_context_schema -v
```

- Exit code: `0`
- Result: `Ran 147 tests in 4004.497s`; `OK`.
- Module counts in that run: contract 17, source 32, store 32, worker 24,
  policy values 22, market 10, context schema 10.
- After the audit removed the one temporary out-of-whitelist source test (no
  production change), the final authorized source module was rerun separately:
  31/31 passed in `191.626s`, exit `0`.

### Whitespace and path audit

`git diff --check` exited `0`; output contained only informational LF-to-CRLF
working-copy warnings. The final code/test status contains exactly the amended 13
W1 paths listed below, plus this required report. No data, SQLite, WAL, SHM,
progress, history, or `tmpj4zv9_fq` path was changed.

## Changed files

1. `ashare_pipeline/formal_policy_market.py` (new)
2. `tests/test_formal_policy_market.py` (new)
3. `ashare_pipeline/formal_range_source.py`
4. `tests/formal_range_fixtures.py`
5. `tests/formal_policy_runtime_fixtures.py`
6. `ashare_pipeline/formal_policy_values.py`
7. `tests/test_formal_policy_values.py`
8. `ashare_pipeline/formal_range_store.py`
9. `tests/test_formal_range_store.py`
10. `ashare_pipeline/formal_range_worker.py`
11. `tests/test_formal_range_worker.py`
12. `ashare_pipeline/formal_range_contract.py`
13. `tests/test_formal_range_contract.py`
14. `.superpowers/sdd/2026-09-12-formal-policy-stage-b3-window-policy-batch/task-W1-report.md`
    (required implementation report, outside the code/test whitelist)

## Key design decisions

- Kept the accepted five-anchor range-binding authority unchanged. Added a separate
  owner reader for planning identity containing both signed range configs and all
  root/source/binding/rule/exchange identity fields.
- `FormalRangeStore.resolve_planning_binding` authenticates the caller, rebuilds the
  complete signed graph through the owning Store, and compares full semantic identity.
  A binding whose manifest root is absent from the Store is rejected.
- Source initialization eagerly seals distinct calendar and market parser/normalizer
  implementations. Request authentication chooses the signed config by actual request
  kind; Worker retry/cooldown/page budgets therefore use the market config for market
  requests.
- Market request minting revalidates a genuine, current, same-binding calendar proof
  inside the private mint boundary. Restored persisted requests use the authenticated
  Store/replay path and cannot create proof authority.
- Calendar and market proofs are owner-recorded, non-subclassable, immutable,
  non-copyable, hash-bound objects whose `require_current` closures reread every
  supporting observation.
- Calendar selection verifies complete natural-day coverage, visibility at the formal
  freeze, explicit open status for the freeze day, page continuity, and adjacent
  backwards groups until 250 actual trading days or a genuine gap.
- Market evaluation keeps veto and price axes independent. Domain conflicts and
  visibility gaps remain explicit pending reasons; missing evidence is never converted
  to zero or confirmed no-trade.
- Closed calendar and market DTO validation stays inside the original policy-value
  owner boundary and grants no evidence authority.

## Remaining limitations

- W1 is an offline authenticated planning/evaluation layer only. It intentionally does
  not schedule work, access a live source, crawl, score securities, or create pools.
- The genuine signed-registry fixtures are intentionally expensive; the expanded suite
  took about 66.7 minutes. This is verification cost, not a production network wait.
- The implementation proves results only for evidence present in the owning Store at
  the formal freeze. Missing or temporally unproven evidence remains pending for later
  stages rather than being inferred.

## Rejection-fix round after checkpoint `d2cc8fe`

The independent review in `task-W1-review-d2cc8fe.md` was read in full before
editing. This round remained inside the active 13-path code/test whitelist and did
not rerun the final combined 147+ test command, as instructed.

### Fix-round RED

Command:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_market.MarketRepositoryTests.test_no_module_global_proof_mint_survives_either_import_order tests.test_formal_policy_market.MarketRepositoryTests.test_date_only_hash_without_resolved_temporal_proof_stays_unproven tests.test_formal_policy_market.MarketRepositoryTests.test_calendar_rejects_nonadjacent_and_mixed_generation_composition tests.test_formal_policy_market.MarketRepositoryTests.test_calendar_proof_tracks_absent_older_segment tests.test_formal_policy_market.MarketRepositoryTests.test_market_window_tracks_absent_request_and_numbered_page tests.test_formal_policy_market.MarketRepositoryTests.test_planner_does_not_repeat_verified_blocker_or_scan_past_price_blocker tests.test_formal_policy_market.MarketRepositoryTests.test_authenticated_domain_conflict_survives_repository_path tests.test_formal_policy_values.PolicyValueTests.test_closed_calendar_and_market_dtos_validate_and_detach -v
```

- Exit code: `1`.
- Result: `Ran 8 tests in 744.337s`; `12 failures, 1 error`.
- Genuine failure loci at `d2cc8fe`: both fresh import orders exposed proof mint
  globals; a structurally valid date-only hash minted visible coverage; calendar
  groups accepted a natural-day gap and mixed generations; calendar and market
  proofs stayed current after absent dependencies arrived; the planner repeated an
  already verified first request; the authenticated domain-conflict wire failed the
  real repository path; and four impossible market-window DTO combinations were
  accepted.

### Fix-round focused GREEN

Exact focused commands, in execution order (all from the isolated W1 worktree):

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_market.MarketRepositoryTests.test_no_module_global_proof_mint_survives_either_import_order tests.test_formal_policy_values.PolicyValueTests.test_closed_calendar_and_market_dtos_validate_and_detach -v
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_market.MarketRepositoryTests.test_date_only_hash_without_resolved_temporal_proof_stays_unproven -v
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_market.MarketRepositoryTests.test_calendar_rejects_nonadjacent_and_mixed_generation_composition -v
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_market.MarketRepositoryTests.test_calendar_proof_tracks_absent_older_segment -v
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_market.MarketRepositoryTests.test_market_window_tracks_absent_request_and_numbered_page -v
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_market.MarketRepositoryTests.test_planner_does_not_repeat_verified_blocker_or_scan_past_price_blocker -v
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_market.MarketRepositoryTests.test_authenticated_domain_conflict_survives_repository_path -v
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_market.MarketRepositoryTests.test_distinct_signed_config_keys_and_wrong_binding_boundaries -v
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_market.MarketRepositoryTests.test_numbered_market_pages_reject_duplicate_dates -v
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_range_worker.WorkerTests.test_market_request_uses_market_retry_cooldown_and_page_budgets -v
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_range_worker.FormalRangeWorkerTests.test_market_request_uses_market_retry_cooldown_and_page_budgets -v
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m py_compile ashare_pipeline/formal_policy_market.py ashare_pipeline/formal_policy_values.py tests/formal_range_fixtures.py tests/test_formal_policy_market.py tests/test_formal_policy_values.py tests/test_formal_range_worker.py
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_values -v
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_market -v
```

- Proof-authority/import-order plus DTO semantics: 2/2 in `0.609s`, exit `0`.
- Date-only visibility: 1/1 in `94.931s`, exit `0`.
- Non-adjacent/mixed-generation calendar composition: 1/1 in `397.507s`, exit `0`.
- Absent older-calendar currentness: 1/1 in `85.636s`, exit `0`.
- Absent market request/numbered-page currentness: 1/1 in `282.489s`, exit `0`.
- Planner no-repeat/no-spurious-history behavior: 1/1 in `239.223s`, exit `0`.
- Authenticated domain-conflict real path: 1/1 in `70.612s`, exit `0`.
- Distinct-config/binding regression initially exited `1` after `185.427s` because
  the new test incorrectly expected a semantically identical distinct binding to be
  rejected. The active brief requires that binding to resolve, so the test was
  corrected to assert acceptance and separately reject a genuine different-root
  binding; the corrected case passed 1/1 in `264.850s`, exit `0`.
- Numbered-page duplicate-date defense: 1/1 in `332.597s`, exit `0`.
- The first Worker selector command named a nonexistent `WorkerTests` class and
  exited `1` after `0.001s` without running a test. The corrected command targeting
  `FormalRangeWorkerTests.test_market_request_uses_market_retry_cooldown_and_page_budgets`
  passed 1/1 in `367.255s`, exit `0`.
- Python compilation of all six touched code/test files succeeded, exit `0`.
- Full touched policy-value module: 22/22 in `15.177s`, exit `0`.
- Full market module: 19/19 in `4585.872s`, exit `0`.

### Fix-round implementation decisions

- Proof mint and registration functions are consumed once into the repository owner
  closure and deleted from module globals. Fresh source-first and market-first
  processes expose no mint/install/register global, while proof constructors remain
  caller-rejecting.
- Date-only effective-time/hash pairs remain `visibility_unproven` because W1 has no
  authenticated independent temporal-proof resolver. No production mapping was
  invented.
- Calendar composition requires exact natural-day adjacency and one common
  upstream/refresh generation pair across all page groups.
- Calendar and market proof currentness recomputes and byte-compares the complete
  selection, so newly arrived older calendar groups, missing requests, and missing
  numbered pages invalidate old proofs.
- Missing reasons are date-local. Authenticated typed domain-conflict rows retain
  their signed reason and observation identity through daily records and evaluation.
- Planning returns no repeated already-verified first request and requests older
  calendar history only for a genuine `calendar_coverage_missing` no-trade search.
- The fixture now seals genuinely distinct calendar/market implementation keys, and
  the Worker regression exercises signed market `max_pages=2`, two attempts, and a
  23-second challenge cooldown.
- Market-window DTOs reject pending complete prices, veto/staleness contradictions,
  confirmed-no-price values without the required pending reason, and incomplete
  states without any explicit pending reason.

### Fix-round changed files and limitations

The worktree delta from `d2cc8fe` contains only these six whitelisted paths:

1. `ashare_pipeline/formal_policy_market.py`
2. `ashare_pipeline/formal_policy_values.py`
3. `tests/formal_range_fixtures.py`
4. `tests/test_formal_policy_market.py`
5. `tests/test_formal_policy_values.py`
6. `tests/test_formal_range_worker.py`

This report is the separately required ignored SDD artifact. Date-only claims remain
pending until a future accepted stage supplies an authenticated temporal resolver.
Complete-selection recomputation makes `require_current()` deliberately more
expensive, but preserves absence-sensitive currentness without weakening Store,
signature, binding, or observation checks. No production data/network access,
crawling, scoring, pool generation, Git state mutation, or data/history cleanup was
performed.

Final scoped verification:

- `git diff --check`: exit `0`; only informational LF-to-CRLF working-copy warnings.
- Explicit whitelist comparison over `git diff --name-only`: whitelist `13`, changed
  `6`, outside `0`, exit `0`.
- Fresh module namespace check for names containing `mint`, `install`, or `register`:
  `[]`, exit `0`.

## Fix round 2 after checkpoint `39443ca`

The independent review in `task-W1-fix1-review-39443ca.md` was read completely
before editing. This round addresses only its remaining repository-owner and
same-Store proof-provenance findings. It did not run the full market module or
the expanded 147+ suite.

### Fix-round-2 RED

Command:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_market.MarketRepositoryTests.test_repository_rejects_instance_authority_method_shadowing tests.test_formal_policy_market.MarketRepositoryTests.test_repository_rejects_subclass_authority_overrides tests.test_formal_policy_market.MarketRepositoryTests.test_repository_rejects_store_replacement tests.test_formal_policy_market.MarketRepositoryTests.test_stale_recheck_cannot_be_bypassed_by_method_shadowing tests.test_formal_policy_market.MarketRepositoryTests.test_calendar_proof_rejects_same_root_cross_store_reuse -v
```

- Exit code: `1`.
- Result: `Ran 5 tests in 271.093s`; `7 failures`.
- Expected failure loci at `39443ca`: all three authority method names accepted
  instance shadowing; repository subclass overrides were accepted; `_store` was
  replaceable; the stale calendar proof recheck could be bypassed by shadowing;
  and Store B accepted Store A's current same-root calendar proof.

### Fix-round-2 GREEN

Exact commands and results:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_market.MarketRepositoryTests.test_repository_rejects_instance_authority_method_shadowing tests.test_formal_policy_market.MarketRepositoryTests.test_repository_rejects_subclass_authority_overrides tests.test_formal_policy_market.MarketRepositoryTests.test_repository_rejects_store_replacement -v
```

- Exit code: `0`; `Ran 3 tests in 2.316s`; `OK`.

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_market.MarketRepositoryTests.test_calendar_proof_rejects_same_root_cross_store_reuse -v
```

- Exit code: `0`; `Ran 1 test in 181.007s`; `OK`.

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_market.MarketRepositoryTests.test_stale_recheck_cannot_be_bypassed_by_method_shadowing -v
```

- Exit code: `0`; `Ran 1 test in 527.676s`; `OK`.

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_range_store.FormalRangeStoreTests.test_planning_resolution_uses_owning_store_graph_and_reconstructed_binding tests.test_formal_range_store.FormalRangeStoreTests.test_planning_resolution_rejects_genuine_binding_from_absent_store_root tests.test_formal_range_source.FormalRangeSourceTests.test_first_calendar_request_needs_no_existing_calendar tests.test_formal_policy_market.MarketRepositoryTests.test_no_module_global_proof_mint_survives_either_import_order tests.test_formal_policy_market.MarketRepositoryTests.test_calendar_proof_is_genuine_current_and_drives_bounded_market_request -v
```

- Exit code: `0`; `Ran 5 tests in 125.962s`; `OK`.

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m py_compile ashare_pipeline/formal_policy_market.py ashare_pipeline/formal_range_source.py ashare_pipeline/formal_range_store.py tests/test_formal_policy_market.py
```

- Exit code: `0`.

### Fix-round-2 implementation decisions

- The public repository type is now built inside the proof-owner closure. Its
  metaclass rejects subclassing and class mutation; its slot-only instances reject
  field and method shadowing and carry no public `_store` field.
- Each genuine repository is registered in an owner-private record containing the
  exact `FormalRangeStore` plus captured original Store, Source, and observation
  operations. Assembly calls these captured unbound functions instead of dispatching
  through caller-mutable repository attributes.
- Calendar and market recheck callbacks capture the owner record and original
  assembly functions. They never call `self.select_calendar`, `self.select`, or
  `self._page_group`, so stale proofs cannot be preserved by method shadowing.
- Calendar and market proof records bind the exact owning Store object. The Store
  closure binds each reconstructed Source to that exact Store once, and the Source
  passes that private provenance into the calendar-proof validator.
- Semantic binding identity remains independent from Store provenance: a semantically
  equal distinct genuine binding still reconstructs and succeeds through the same
  Store, while another Store containing the identical signed root cannot reuse its
  proof.

### Fix-round-2 changed paths and limitations

The delta from `39443ca` contains four active-whitelist paths:

1. `ashare_pipeline/formal_policy_market.py`
2. `ashare_pipeline/formal_range_source.py`
3. `ashare_pipeline/formal_range_store.py`
4. `tests/test_formal_policy_market.py`

This required report remains a separately ignored SDD artifact. Verification was
deliberately limited to the new attacks and directly affected compatibility paths;
the controller explicitly deferred the full market and expanded W1 suites. No Git
state mutation, network/data access, crawling, scoring, pool generation, or
data/history cleanup was performed.

Final round-2 static checks:

- `git diff --check`: exit `0`; only informational LF-to-CRLF warnings.
- Explicit `git diff --name-only` whitelist audit: `13` allowed, `4` changed,
  `0` outside, exit `0`.
- Fresh owner namespace/type check: no surviving mint/install/register or
  implementation-owner global; repository slots are exactly `('__weakref__',)`,
  exit `0`.

## Fix round 3 after checkpoint `ae444d0`

The independent review in `task-W1-fix2-review-ae444d0.md` was read completely
before editing. This round addresses only the remaining initial market-request
Store-provenance gap. It did not run a full test module or the expanded W1 suite.

### Fix-round-3 RED

Command:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_market.MarketRepositoryTests.test_initial_market_request_rejects_same_root_cross_store_enqueue -v
```

- Exit code: `1`.
- Result: `Ran 1 test in 53.257s`; `FAILED (failures=1)`.
- Expected failure locus at `ae444d0`: after Store A accepted an initial market
  request minted by Store A's Store-bound Source from Store A's proof, Store B
  containing the same signed root also accepted that request instead of raising
  `ValueError`.

### Fix-round-3 GREEN

The exact RED command was rerun after the minimal implementation:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_market.MarketRepositoryTests.test_initial_market_request_rejects_same_root_cross_store_enqueue -v
```

- Exit code: `0`; `Ran 1 test in 187.656s`; `OK`.

Minimum directly affected compatibility command:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest -v tests.test_formal_policy_market.MarketRepositoryTests.test_calendar_proof_rejects_same_root_cross_store_reuse tests.test_formal_policy_market.MarketRepositoryTests.test_genuine_source_path_proves_tail_veto_and_keeps_older_gap_pending tests.test_formal_range_store.FormalRangeStoreTests.test_enqueue_replay_and_noncanonical_payload_tamper tests.test_formal_range_store.FormalRangeStoreTests.test_continuation_cannot_be_enqueued_under_a_different_raw_root
```

- Exit code: `0`; `Ran 4 tests in 682.226s`; `OK`.
- These checks cover same-Store semantically equal reconstructed binding use,
  genuine initial-market restoration/execution, unchanged initial-calendar enqueue
  replay, and unchanged continuation provenance enforcement.

Compilation command:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m py_compile ashare_pipeline/formal_range_source.py tests/test_formal_policy_market.py
```

- Exit code: `0`; command wall time `0.201s`.

### Fix-round-3 implementation decisions

- The owner-private request record now carries the exact Store object only for an
  initial market request. The request wire and persisted task schema are unchanged.
- The Source passes the same Store used to authenticate the calendar proof into
  the private request mint. Stored initial market requests are reconstructed with
  the Store that owns the authenticated Source graph.
- `require_execution`, already called before enqueue persistence, rejects an initial
  market request unless its recorded Store is the exact destination Store object.
- Initial calendar requests continue to have no Store provenance. Continuations
  continue to use the existing authenticated previous-observation provenance rule;
  neither behavior was broadened or replaced.
- The regression deliberately resolves Store A's Source using Store B's semantically
  equal genuine binding before minting. Store A accepts the resulting request and
  Store B rejects it, preserving semantic-binding compatibility without weakening
  exact Store ownership.

### Fix-round-3 changed paths and limitations

The delta from `ae444d0` contains two active-whitelist paths:

1. `ashare_pipeline/formal_range_source.py`
2. `tests/test_formal_policy_market.py`

This required report remains a separately ignored SDD artifact. Verification was
deliberately limited to the new regression and four directly affected compatibility
tests, as instructed. The full market module and expanded W1 suite were not run.
No Git state mutation, network/data access, crawling, scoring, pool generation, or
data/history cleanup was performed.

Final round-3 static checks:

- `git diff --check`: exit `0`; only informational LF-to-CRLF warnings for the
  two changed files.
- Explicit `git diff --name-only` whitelist audit: `13` allowed, `2` changed,
  `0` outside, exit `0`.

## Final W1 acceptance gate at checkpoint `31f727e`

The code/test checkpoint was frozen before this gate. The required compatibility
suite was run exactly once in one Python process from the isolated worktree; no
other test ran concurrently and no code or test file was edited.

Exact command:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_range_contract tests.test_formal_range_source tests.test_formal_range_store tests.test_formal_range_worker tests.test_formal_policy_values tests.test_formal_policy_market tests.test_formal_context_schema -v
```

Exact terminal result:

- Exit code: `0`.
- `Ran 161 tests in 18046.539s`.
- `OK`.
- Complete verbose output, terminal summary, command, timing, and exit status are
  preserved in `task-W1-final-compatibility.log`.

Module counts observed at the boundaries were:

- `tests.test_formal_range_contract`: 17 passed.
- `tests.test_formal_range_source`: 31 passed.
- `tests.test_formal_range_store`: 32 passed.
- `tests.test_formal_range_worker`: 24 passed.
- `tests.test_formal_policy_values`: 22 passed.
- `tests.test_formal_policy_market`: 25 passed.
- `tests.test_formal_context_schema`: 10 passed.

### Pre/post SHA-256 hashes for all 13 W1 files

Every post-run value exactly matched its pre-run value:

| Path | Pre-run SHA-256 | Post-run SHA-256 |
| --- | --- | --- |
| `ashare_pipeline/formal_policy_market.py` | `d1c8c21b560f72e5efcbed5caaab1ed98a005672a00b2587782b1ff3f14cc1be` | `d1c8c21b560f72e5efcbed5caaab1ed98a005672a00b2587782b1ff3f14cc1be` |
| `tests/test_formal_policy_market.py` | `7b2e8b6840a4827047e99d2b1d6e6288ecb603c73210460b31db660ae9fd89a8` | `7b2e8b6840a4827047e99d2b1d6e6288ecb603c73210460b31db660ae9fd89a8` |
| `ashare_pipeline/formal_range_source.py` | `6657a2a3929aa631f1b703700b4d434034e96f8473a0ea8391a4c1f11b98dccc` | `6657a2a3929aa631f1b703700b4d434034e96f8473a0ea8391a4c1f11b98dccc` |
| `tests/formal_range_fixtures.py` | `5377dc2ca7f46fa7437c1b415ec51fdaaa2517e46629571b09db2d78db9bb31a` | `5377dc2ca7f46fa7437c1b415ec51fdaaa2517e46629571b09db2d78db9bb31a` |
| `tests/formal_policy_runtime_fixtures.py` | `2c747002e62c676fec0fbb8df4d66b9bcf4ef5a8afaffd6cd8c8b908a8a29ba8` | `2c747002e62c676fec0fbb8df4d66b9bcf4ef5a8afaffd6cd8c8b908a8a29ba8` |
| `ashare_pipeline/formal_policy_values.py` | `643ae27d842d591eba926957c6ba58642515a698669c37f3217f0283590ca6da` | `643ae27d842d591eba926957c6ba58642515a698669c37f3217f0283590ca6da` |
| `tests/test_formal_policy_values.py` | `0d5ac9642972968daddf8749ee97c22a10e0d035f93129da3508d1972cf11502` | `0d5ac9642972968daddf8749ee97c22a10e0d035f93129da3508d1972cf11502` |
| `ashare_pipeline/formal_range_store.py` | `79b47e67f2457ec3e6ace91e53cfc611c0120386d4d199384482d07a74ea735c` | `79b47e67f2457ec3e6ace91e53cfc611c0120386d4d199384482d07a74ea735c` |
| `tests/test_formal_range_store.py` | `292545114f26ffbdc5d3045f6337df5aba5d705611d917197b0b6d492858d231` | `292545114f26ffbdc5d3045f6337df5aba5d705611d917197b0b6d492858d231` |
| `ashare_pipeline/formal_range_worker.py` | `52626d27eca7fa5e91858731b19949c2ad8add3aef1e5cdea05f2fa1ead780ff` | `52626d27eca7fa5e91858731b19949c2ad8add3aef1e5cdea05f2fa1ead780ff` |
| `tests/test_formal_range_worker.py` | `c17bba1340eeec1a0785ef2fd6f93ca71d203d38d10f437dafbf4cad403b7515` | `c17bba1340eeec1a0785ef2fd6f93ca71d203d38d10f437dafbf4cad403b7515` |
| `ashare_pipeline/formal_range_contract.py` | `971599133cdbb9a358060e297445a956c00f1b7d2be932697e83e3beedd2393c` | `971599133cdbb9a358060e297445a956c00f1b7d2be932697e83e3beedd2393c` |
| `tests/test_formal_range_contract.py` | `536b0099497fa71f60098ac210636d48aa37a304f5d44396d7b9da06dd87d327` | `536b0099497fa71f60098ac210636d48aa37a304f5d44396d7b9da06dd87d327` |

### Final read-only checks

- `git diff --check`: exit `0`, no output.
- `git status --short`: exit `0`, no output (clean worktree).
- `git rev-parse --short HEAD`: exit `0`, `31f727e`.
- `Get-Process -Name python -ErrorAction SilentlyContinue`: zero Python
  processes remained after the suite.

No Git write, network/data access, merge, push, or subagent action occurred.
