# Task R1 implementation report

## Status

Implemented the signed source-v2 range catalog and same-root active-policy M/C/Bx
binding foundation in the R1 whitelist.  No Git state was written and no
production network or data path was used.

Controller ruling applied: `select_range` is intentionally deferred to R2's
genuine `FormalRangeRequestV1`; R1 contains no duck-typed request or placeholder.
The brief's reference to `FormalPolicyRegistry.require_official` was corrected by
the controller to the existing exact captured `FormalPolicyRegistry.require_verified`
method.  `formal_policy_registry.py` was not changed.

## TDD RED

Command:

```powershell
& 'D:/Projects/AShareQiheng/.venv/Scripts/python.exe' -m unittest tests.test_formal_range_contract -v
```

Exit code: `1`

Exact result lines:

```text
test_absent_and_duplicate_pairs_are_contract_failures ... ERROR (2 subtests)
test_closed_range_contract ... ERROR
test_complete_graph_binds_every_active_market_rule_for_every_exchange ... ERROR
test_market_calendar_and_bootstrap_identities_cannot_be_mixed ... ERROR (3 subtests)
test_range_format_rejects_wrong_types_versions_templates_and_bridge_shapes ... ERROR
test_source_registry_versions_are_closed_and_old_configs_stay_closed ... ERROR
test_v2_registry_keeps_legacy_selection_separate_and_seals_range_snapshots ... ERROR
test_wrong_root_and_mutated_returned_binding_fail_current_validation ... ERROR
test_wrong_source_exchange_and_active_capability_are_rejected ... ERROR (3 subtests)

Ran 9 tests in 0.004s
FAILED (errors=14)
```

The failure was the intended missing-feature RED, not a fixture-signing failure:

```text
ModuleNotFoundError: No module named 'ashare_pipeline.formal_range_contract'
AttributeError: 'SignedSourceRegistry' object has no attribute 'range_configs'
ValueError: source registry has unknown or missing keys
```

## Focused GREEN

Command:

```powershell
& 'D:/Projects/AShareQiheng/.venv/Scripts/python.exe' -m unittest tests.test_formal_range_contract -v
```

Exit code: `0`

Full per-test result:

```text
test_absent_and_duplicate_pairs_are_contract_failures ... ok
test_closed_range_contract ... ok
test_complete_graph_binds_every_active_market_rule_for_every_exchange ... ok
test_market_calendar_and_bootstrap_identities_cannot_be_mixed ... ok
test_range_format_rejects_wrong_types_versions_templates_and_bridge_shapes ... ok
test_source_registry_versions_are_closed_and_old_configs_stay_closed ... ok
test_v2_registry_keeps_legacy_selection_separate_and_seals_range_snapshots ... ok
test_wrong_root_and_mutated_returned_binding_fail_current_validation ... ok
test_wrong_source_exchange_and_active_capability_are_rejected ... ok

Ran 9 tests in 29.248s
OK
```

After the compatibility run, the existing identity-mixing test was extended with
the explicit Bx-as-C case (no production change).  Fresh targeted confirmation:

```powershell
& 'D:/Projects/AShareQiheng/.venv/Scripts/python.exe' -m unittest tests.test_formal_range_contract.FormalRangeContractTests.test_market_calendar_and_bootstrap_identities_cannot_be_mixed -v
```

```text
test_market_calendar_and_bootstrap_identities_cannot_be_mixed ... ok

Ran 1 test in 7.304s
OK
```

Exit code: `0`.

## Required compatibility GREEN

Command:

```powershell
& 'D:/Projects/AShareQiheng/.venv/Scripts/python.exe' -m unittest tests.test_formal_range_contract tests.test_formal_sources tests.test_formal_policy_registry tests.test_formal_policy_registry_guards -v
```

Every emitted test result was `ok`.  Exact terminal summary:

```text
----------------------------------------------------------------------
Ran 112 tests in 285.729s

OK
```

Exit code: `0`.

This includes the pre-existing
`test_input_security_bootstrap_calendar_is_rejected`, so the original `_bind_context`
bootstrap rejection remained green.

## Changed files

- `ashare_pipeline/formal_range_contract.py` (new)
- `ashare_pipeline/formal_sources.py` (modified)
- `tests/formal_range_fixtures.py` (new)
- `tests/test_formal_range_contract.py` (new)
- This required report file

Other modified/untracked files visible in the shared worktree belong to the F1
worker or pre-existing workspace state and were not edited for R1.

## Self-review

- `RangeConfig` is a closed `formal-range-source-config-v1` parser product.  It
  preserves exact JSON scalar types, freezes nested request/selector structures,
  emits a detached `to_dict()`, and derives `entry_id` from complete canonical
  ENTRY bytes.
- Source registry version dispatch is strict: v1 accepts only its original three
  top-level fields and exposes `range_configs == ()`; v2 requires exactly the four
  approved fields.  Legacy configs still use the unchanged `_CONFIG_KEYS` and old
  `select(OfficialRequest)` still searches only legacy configs.
- The source-registry seal records the public range tuple identity plus a direct,
  full nested-field fingerprint.  Trusted snapshots reparse the signed canonical
  bytes and do not trust `RangeConfig.to_dict()`, including when that method is
  monkeypatched.
- Range catalog uniqueness uses the specified five-part identity.  Binding then
  independently requires unique active market/calendar pairs per rule/exchange.
- `load_policy_range_bindings` checks exact genuine bundle/scoring/policy types,
  calls their captured authentic verification methods, hashes the actual nine
  role blobs, compares the policy's same-root role hashes, reparses source v2,
  and validates actual Context descriptor ENTRY identities.
- Each binding closes the active rule's M descriptor, complete C selector bridge,
  exchange-specific bootstrap Bx descriptor, legacy bootstrap source config, and
  the new market/calendar source+dataset identities.  It rejects C-as-Bx,
  Bx-as-C, cross-exchange Bx, and same-text/wrong-descriptor selectors.
- `RangeBinding.require_current()` re-runs the genuine graph and version checks
  and verifies the returned config snapshots have not been replaced or mutated.
  No binding claims any date coverage.
- The fixture uses the real byte-sensitive HMAC verifier, updates feature
  source/mapping dependencies and policy-contract hashes before the nine-role
  manifest is signed, and does not use `AcceptingVerifier`.
- `git diff --check` reported no whitespace errors.  It emitted only existing
  Windows LF-to-CRLF warnings for shared-worktree files.
- After the controller's staged check exposed an untracked-file-only trailing
  blank line at `tests/formal_range_fixtures.py:163`, that whitespace was removed
  with no semantic code change; tests were not rerun by instruction.

## Concerns / handoff notes

- `select_range` remains absent by explicit controller ruling and must be added
  only with R2's genuine request factory.
- The binding verifier's project-type imports are lazy to avoid the existing
  `formal_context_schema -> formal_sources` import cycle; range-format parsing
  itself has no policy/source initialization dependency.
- The range contract intentionally authorizes configuration only.  Request dates,
  pagination evidence, coverage, and transport execution remain later-task work.

## Fix round 1 — review findings and focused evidence

Fix baseline: `db093077c57a180499a96c1182a603c50ebdb00e`. The original R1
reviewed head was `ed25b6a553f0738c4de24dd88583c28061d196e0`. This section
supersedes the original report's lazy trust-capture and retention descriptions.

Read the fix brief, original brief/report, full TDD skill and writing-good-tests
reference before edits. Added seven regression methods before implementation.
The same focused command was run RED and GREEN:

```powershell
D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_range_contract -v
```

RED, exit 1:

```text
Ran 16 tests in 62.022s
FAILED (failures=26, errors=4)
```

- The first-load test uses a fresh Python process, imports the contract before
  replacing policy methods, constructs a genuine signed graph, and then attempts
  to load an unregistered exact-type policy object. Both the first load and the
  accepted binding's later `require_current()` after method restoration failed
  their expected-ValueError assertions. The nested process reported 1 test in
  1.227s, `FAILED (failures=2)`; the outer test correctly failed on that result.
- Replacing the RangeConfig alias produced the substitute class. Unsigned dataset
  mutation remained accepted while aliases were replaced and after restoration:
  three separate failing assertions.
- Query/header list and mapping values escaped rejection; null values and
  nonempty header containers raised four real TypeErrors in the production
  parser. Query keys and values accepted all 14 whitespace/control subcases.
- Both GC tests failed because a parent remained alive after all caller binding
  references were dropped. The live-child test also established that the child
  retained its real upstream validation before final collection was checked.

These were actual defect reproductions, not signature/setup failures. Tests use
the existing byte-sensitive signed range fixture. The parser assertions require
ValueError, so TypeErrors are not hidden by generic catches.

GREEN, exit 0:

```text
Ran 16 tests in 40.798s
OK
```

### Implementation and self-review

- Added the explicitly authorized `ashare_pipeline/formal_range_format.py` and
  moved pure RangeConfig syntax there. `formal_range_contract` still exports
  RangeConfig and parse_range_entry. `formal_sources` imports only the pure
  format module, breaking the source/policy/context import cycle.
- Genuine RangeConfig constructor and serializer identity are captured in the
  format factory's local closures. Source parsing checks the exact result type
  before registration, and unexpected range configs/tuples now raise ValueError
  instead of returning a stable invalid fingerprint.
- Binding factory initialization captures genuine bundle/scoring/policy types,
  actual trust methods, policy bytes method, descriptor validator and range
  parser/type before first use. Removed the mutable lazy first-load cache.
  Authority tables, records and verifier functions are private closure values.
- Query/header values now require exact strings before iteration; static keys
  reject whitespace/controls; query strings reject whitespace/controls and raw
  ampersand/hash delimiters. Headers preserve the original permitted spaces and
  reject controls. Nested POST bodies and new placeholders remain accepted and
  deeply frozen. Existing HTTPS, placeholder, alias/cycle, pagination and identity
  constraints remain in place.
- Authority records hold weak parent/child references. Actual parent and child
  objects hold the lifetime edges, so their cycle is collectible when external
  references disappear. A live child retains its parent and upstream context;
  require_current still rejects changed genuine source bytes. Slot identity and
  child membership are checked against private records.
- No Stage A/F1 edits, old trust-gate changes, Git writes, production network,
  database/scoring operations or subagents. Existing range fixtures were reused
  unchanged. R1 source stability was coordinated with the F1 fix worker.

Frozen at the focused GREEN checkpoint for the prescribed four-module run:

| File | SHA-256 |
| --- | --- |
| ashare_pipeline/formal_range_contract.py | 5f646aca4332e6a9287e3e7e7fe99dbc7a0487a14d405580776a267fb2898746 |
| ashare_pipeline/formal_range_format.py | c6f3504f5b65bdbaaf3ed21d8c7d4f3cae58748ea5f449fa2cfcc6b442a2e517 |
| ashare_pipeline/formal_sources.py | d854aa889eb3143f44f3fbb855dd7f00fb5f078b535f59f83f82b0e6fa6309f4 |
| tests/test_formal_range_contract.py | 72925f06dd0b4c3aa6f4920d01d53f59e80fa5695be63387d02d4ed5e1401efb |
| tests/formal_range_fixtures.py (unchanged) | 12ce3232bef49b6cc59b9ee849692199e205bad4e5f920e3b533a82bb4b80e5b |

Final four-module result pending. No completion claim at this checkpoint.

### Fix round 1 final compatibility result

Exact prescribed command:

```powershell
D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_range_contract tests.test_formal_sources tests.test_formal_policy_registry tests.test_formal_policy_registry_guards -v
```

Final output, exit 0:

```text
Ran 119 tests in 336.446s
OK
```

Every emitted method result was `ok`. This is the original 112-method R1
compatibility suite plus seven new regression methods. It includes the existing
`test_input_security_bootstrap_calendar_is_rejected` and the Stage A genuine
signed selector-family guards. The R1 regression also independently exercises
first load in a new interpreter, both alias-restoration phases, strict request
template errors, parent/child collection and live-child source invalidation.

After the full suite, recomputed all five hashes in the checkpoint table: every
one is unchanged. No R1 source/test edits occurred after focused GREEN. Read-only
`git diff --check` found no whitespace errors; only existing Windows conversion
warnings were emitted. Shared F1/plan changes are other workers' changes and were
not edited by this implementer.

Fix-round changed files are `formal_range_contract.py`, `formal_sources.py`,
`test_formal_range_contract.py`, the new `formal_range_format.py`, and this report.
`formal_range_fixtures.py` is unchanged. Stage A and F1 files are untouched by R1.

Status: **DONE**. All four Important findings have regression coverage and the
prescribed full regression passed. No remaining implementation concern identified.
Source/tests are frozen for controller-owned commit and independent re-review;
no Git write or commit was performed by this implementer. R2 select_range and
runtime/date coverage remain deferred by the original controller ruling.
