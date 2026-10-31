# Stage D Task 7 recovery report

## Status

The original implementation commit is `5f0bbfa` (`feat: audit formal production coverage`) on base `7f71934`. Recovery commits are `24e144f` (`fix: close formal coverage audit gates`) and `2459e12` (`feat: bind official coverage to signed roots and repository identity`). Together they change only the three Task 7 code/test files. The existing plan modification in the worktree was not staged or committed by this task.

Task 7's specified software gates are **implemented and green**. Official readiness now requires a genuine frozen universe, a reloaded signed registry bundle with official approval, a signed exact requirement catalog, repository validation provenance for every required domain/key, and read-only database/workspace identities. No real production contract or production data were supplied or audited; this report does not claim a real official run is ready.

## Requirements reviewed

- The 15 coverage classes in the implementation exactly match the design vocabulary.
- The seven exact coverage test names from brief Step 1 and the named proof guard test from Step 2 exist and pass.
- Absent evidence, missing tables, cross-exchange calendar identity, duplicate requirements, SQL-count diagnostics, and audit timing hash stability have focused tests.
- The recovery adds explicit contract purpose, approval and identity checks; registry disapproval affects the member class; repository callback success must be exact `True`; sparse verified lineage is blocked; canonical bytes reproduce `manifest_hash`; an empty requirement universe is rejected; proof class method replacement and explicit revocation are tested.

## RED / GREEN evidence

Initial focused command on `5f0bbfa`:

```text
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_coverage_manifest tests.test_formal_coverage_guards -v
Ran 12 tests in 0.003s — OK
```

Recovery RED checks before each implementation change:

```text
tests.test_formal_coverage_guards -v: Ran 8 tests — FAILED (failures=7)
  unapproved/nonofficial contract, registry member class, nonboolean validator verdict
tests.test_formal_coverage_manifest tests.test_formal_coverage_guards -v:
  Ran 18 tests — FAILED (failures=23)
  14 sparse-lineage cases and 9 absent audit projection fields
test_manifest_hash_matches_exported_canonical_bytes: FAILED (1 failure)
test_source_cannot_clear_required_flag_or_hash_recheck_time: FAILED (1 failure)
test_every_required_member_domain_key_is_unique_and_enumerated: FAILED (1 failure)
test_coverage_proof_rejects_plain_construction_copy_pickle_weakref_redirect_method_replacement_and_revocation:
  FAILED on class method replacement (1 failure)
```

Final GREEN, after `24e144f`:

```text
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_coverage_manifest tests.test_formal_coverage_guards tests.test_formal_snapshot_repository tests.test_formal_universe -v
Ran 51 tests in 1.339s — OK
```

The focused Task 7 modules contribute 20 of these 51 tests. No real production chain, network fetch, database mutation, or broad suite was run.

## Historical self-review findings after `24e144f` (closed by `2459e12`)

1. **Root completeness is not proved.** `audit()` accepts a caller-supplied list of requirements; it cannot prove that every member and domain from a genuine `FormalFrozenUniverseInput` is present. Rejecting an empty list and duplicate keys prevents two simple false positives but does not close omission of an arbitrary member or domain.
2. **Registry and production contract are not genuine proof objects.** The recovery requires an approved, `purpose=official` contract mapping with signing identity and root manifest hash, then binds that identity into the manifest hash. A caller can still supply such a mapping without verifying a signature or binding it to a `VerifiedRegistryBundle`; `registry` is likewise an optional mapping. Official readiness must not be treated as authoritative until these inputs are revalidated through the existing repository and registry boundaries.
3. **Repository validation is caller supplied.** The auditor calls a per-domain callback for present records and now accepts only an exact `True`, but a permissive callback can still return `True` for fabricated source fields. The design calls for domain-specific repository validation of identity, signature, current parser/mapping version, timestamps, and immutable hashes. The current callback contract does not prove it is such an entry point.
4. **Top-level audit identity is incomplete.** The manifest omits several design-required fields, including workspace revision, database path and SHA-256, schema versions, status generation, universe records hash, frozen input hash, registry manifest hash, member counts by exchange, report period, and query version. The row projection now contains the required field names, but several are `null` when not supplied and are not independently checked.
5. **Gate coverage needs stronger semantics.** `require_preview_ready()` and `require_official_ready()` currently use blockers and contract presence; they do not recheck repository state at gate time. The current tests do not establish a legitimate production run or full SH/SZ/BJ coverage.

The continuation commit closes these four interface gaps for the official gate. The repository callback and signature verifier are trusted dependencies supplied by the configured runner; official readiness requires their successful recheck at the gate.

## Continuation RED / GREEN evidence

The new official-boundary tests were RED on `24e144f`:

```text
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_coverage_guards.OfficialCoverageBoundaryTests -v
Ran 5 tests — FAILED (errors=5): audit rejected the new contract_verifier input.
test_official_gate_rechecks_repository_and_registry_proofs: FAILED — a stale callback was not rerun.
test_official_gate_reloads_registry_from_read_only_repository: ERROR — registry_loader input absent.
test_database_sidecar_changes_invalidate_official_gate: FAILED — new WAL sidecar was not bound.
test_coverage_proof_seal_does_not_keep_abandoned_manifest_alive: FAILED — weakref callback retained the proof.
```

One follow-up RED exposed that SQLite `PRAGMA user_version` is not the project `StateStore` schema version; the status schema version is now checked separately while both are recorded in `db_schema_versions`.

Final GREEN on `2459e12` (same commands required by the brief):

```text
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_coverage_manifest tests.test_formal_coverage_guards -v
Ran 31 tests in 1.937s — OK

& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_coverage_manifest tests.test_formal_coverage_guards tests.test_formal_snapshot_repository tests.test_formal_universe -v
Ran 62 tests in 1.878s — OK
```

The official fixture uses a genuine `FormalFrozenUniverseInput` and a `VerifiedRegistryBundle` loaded from signed fixture envelopes. A signed coverage contract pins the root, approval, member requirement catalog, domain owners, schema, report period, and query version. Requirements must exactly equal that signed catalog and cover every frozen member; the catalog's approved signer defines which domains and applicability keys are required. A matching provenance receipt from each configured domain repository callback is recorded in each row and rechecked before official use. The registry loader is also rerun. DB main, WAL, and SHM hashes, status-to-DB hash, schema status, and Git workspace revision are read without mutation and checked again by the official gate.

## Remaining external prerequisites

There is no approved production coverage contract or verified complete SH/SZ/BJ production record set in this task. The runner must configure its real signature verifier and owning repository callbacks and provide the actual read-only DB/status paths; fixture signatures and callbacks used in unit tests are only test evidence. Until those inputs exist and every callback accepts every signed requirement, `official_candidate` remains blocked. No production chain or network fetch was run.

## Formal review fix round 1 (supersedes earlier readiness claims)

The six formal-review findings were treated as binding gaps. This round changes only the Task 7 module and its two tests. Earlier text above describing caller-configured callbacks as trusted should no longer be read as sufficient for official authorization.

1. **Caller-minted authority:** Official mode now requires a constructor-authenticated `StateStore` behind the registry loader, its configured verifier, matching DB path, and a constructor-authenticated `FormalSnapshotRepository` sharing that same store. Financial evidence is re-read by manifest from the snapshot repository, raw bytes are re-hashed, every source lineage field is compared to the repository reference, and same-snapshot/period financial facts and units are read from `StateStore`. Callback receipts must match a digest computed from actual raw evidence and facts; they cannot substitute for the owning repository reads. The positive fixture now persists signed registry envelopes, leased verified raw snapshots, and financial facts. A fabricated snapshot ID fails despite a permissive callback. Unsupported non-financial owners fail closed with `repository owner has no authenticated adapter` rather than receiving official readiness. This last limitation remains for scoped re-review.
2. **Revoked proof replay:** Module-exposed `_SEALS`, `_LIVE_CONTEXTS`, and `_seal` were removed. Proof seals and live contexts are held only by an installation closure; `audit`, `revoke`, proof read, and official gate close over it. The regression verifies those module attributes are absent and a revoked proof stays rejected.
3. **Applicability/partial:** `not_applicable_signed` requires explicit authenticated applicability, signature/hash verdicts and a SHA-256 rule hash for preview; official mode currently rejects it without an authenticated owner adapter. `verified_partial` with missing required units gets an explicit blocker; financial official mode requires `verified_complete` with repository-backed facts for all required units.
4. **Lineage/time:** Verified rows now require refresh generation, task ID, collection state, capture/source-update timestamps, nonempty evidence hashes, SHA-256 request/content/manifest hashes, and publication/effective/source-update visibility by freeze time. Missing or future identities block.
5. **DB generation/schema:** The read-only gate checks the real `StateStore` migration ledger and table/index DDL, rejects foreign nonzero `user_version`, binds main DB and WAL/SHM SHA-256 generation to status, and rechecks identity before repository reads at official gate time. Empty SQLite and modified sidecar regressions pass.
6. **Diagnostic hash stability:** `rechecked_at_utc` and timing diagnostics are removed before source record hashing as well as manifest canonicalization; changing only recheck time no longer changes the official hash.

RED evidence was recorded before fixes: the new guard cases produced 16 assertion failures across the six exploit classes; after intermediate repairs, the exact four-module command still failed only on `test_fabricated_callback_and_empty_database_cannot_grant_official`. A later `test_foreign_sqlite_user_version_is_not_formal_schema` was RED (`ValueError not raised`) before the explicit version check. Final commands:

```text
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_coverage_manifest tests.test_formal_coverage_guards -v
Ran 38 tests in 8.771s — OK

& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_coverage_manifest tests.test_formal_coverage_guards tests.test_formal_snapshot_repository tests.test_formal_universe -v
Ran 69 tests in 24.163s — OK
```

Self-review: the financial path has a genuine repository-backed positive case and fail-closed negative cases. Other domain owners do not yet have a Task 7 authenticated adapter, so this is **not** a claim of full multi-domain production coverage or real official-run readiness. A signed contract naming such an owner is rejected before a manifest is minted. No long chain, production data mutation, network fetch, plan edit, or ledger edit was performed.

## Formal review fix round 2 — WAL and applicability; multi-domain blocker

The WAL regression held a writer connection open, removed migration 7 in committed WAL frames, and refreshed status hashes. With SQLite `immutable=1`, `_read_environment` incorrectly saw the checkpointed main DB and the test failed (`ValueError not raised`). The read-only schema check now selects `mode=ro` whenever a WAL exists, so migration/DDL validation sees committed frames. It retains immutable read-only mode for a checkpointed DB without a WAL, avoiding creation of sidecars there; before/after DB/WAL/SHM hashes still reject a concurrent generation change. The targeted WAL test is GREEN.

The applicability regression supplied all prior `not_applicable_signed` caller flags, a SHA-shaped rule hash, and optionally a permissive callback. Both cases previously passed preview (two RED failures). No existing Task 7 owner adapter can authenticate that assertion. The class now maps to `blocked_dependency:applicability_owner_proof_missing` even in preview and cannot be promoted by generic caller callbacks. This is fail-closed, not a positive signed-applicability implementation.

I inspected the existing typed repositories for the remaining Step 4 requirement. `FormalContextRepository.get_verified(kind, scope_key, security_id, as_of_utc, registry_manifest_hash)` requires the original kind and scope key, whereas the signed coverage key carries only `domain`, `selector_hash`, and `period_or_window`; no authenticated selector-hash-to-arguments binding or per-requirement receipt API exists. `FormalFeatureRepository.get_verified_formal_feature_bundle(input_hash=...)` requires an input hash and returns an aggregate bundle, without a signed mapping from a coverage requirement to its bundle/slot receipt. `FormalPolicyRepository.build_batch(frozen_input_hash, scoring_registry=..., policy_registry=...)` requires typed scoring/policy registries and builds a full batch, not a per-requirement validation receipt. The market, metric, valuation and final-input repositories likewise expose specialized selection or batch-build interfaces, not the uniform owner-validated `(requirement, source) -> authenticated provenance` interface needed by Task 7. The current contract permits arbitrary `domain_owners` strings; treating these specialized methods or a caller callback as interchangeable would reopen the authority bug. Accordingly non-financial owners remain explicitly official-blocked. This is a **load-bearing functional blocker**, not a claim that all formal domains are covered. It needs a signed domain/selector schema and typed owner adapters or an upstream repository-issued coverage receipt interface before Task 7 can be marked DONE.

Final test evidence for this round:

```text
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_coverage_manifest tests.test_formal_coverage_guards -v
Ran 40 tests in 9.453s — OK

& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_coverage_manifest tests.test_formal_coverage_guards tests.test_formal_snapshot_repository tests.test_formal_universe -v
Ran 71 tests in 13.447s — OK
```

No real long chain, production DB/workspace/data mutation, plan edit, or ledger edit was performed.

## Formal review fix round 3 — durable WAL generation and signed selectors

RED: a valid writer-open WAL with an unchanged migration row caused `_read_environment` to raise `database changed during identity read`; a normal SQLite read-only connection changed transient SHM read marks. The generation now hashes/checks only the main DB and WAL bytes. SHM remains SQLite coordination state, not a committed-content identity. The reader still uses `mode=ro` when a WAL exists and validates the effective migration/DDL snapshot; the corrupted committed-WAL migration regression remains GREEN. Status producers must use the same main+WAL generation hash. Tests show a stable valid WAL passes twice and a committed WAL removal of migration 7 fails.

RED: the signed contract had only opaque `selector_hash` values; changing a selector's source or owner could not be detected because there was no signed selector preimage. The contract now requires `selector_descriptors` covering every catalog hash. Each descriptor's canonical SHA-256 must equal its `selector_hash`, its member/domain/exchange/period/owner must match the signed requirement and owner map, and its fields must match a fixed typed schema for snapshot, Context, Feature, or Policy owners. The financial adapter additionally binds descriptor source/dataset to the authenticated snapshot. Bad hash and wrong owner regressions are GREEN.

The full multi-domain Step 4 requirement is **still BLOCKED**. Typed descriptors solve the opaque-hash preimage but do not turn the existing heterogeneous repository outputs into Task 7's single-snapshot canonical row/provenance. The exact missing integration contracts are:

- Context: an owner-issued per-requirement receipt/recheck binding `get_verified(kind, scope_key, security_id, as_of_utc, registry_manifest_hash)` output, its source-snapshot evidence and signed selector to the six-part coverage key. The current method returns a `FormalContextFact`; Task 7 has no typed conversion and recheck receipt for that fact.
- Feature: a current (not merely historical) `input_hash`/`slot_id` selection receipt from `FormalFeatureRepository` binding the selected `FormalFeatureBundle` slot, all underlying financial-fact evidence, frozen root, and complete requirement key. `get_verified_formal_feature_bundle(input_hash=...)` returns an aggregate bundle, not that receipt.
- Policy: an owner-issued item receipt from `FormalPolicyRepository.build_batch(...)`/`recheck_current(batch)` binding a selected security/rule item, signed scoring and policy registries, all dependent feature/context/market selections, and the complete requirement key. The API publishes/rechecks a batch, not a Task 7 per-item coverage receipt.
- Other signed formal owners (market/metric/valuation/final inputs): their specialized selection/batch proof schemas also need explicit adapters and a signed domain vocabulary; arbitrary owner strings remain rejected.

I did not create a generic caller-supplied validator or treat a public dictionary as a production capability. Financial remains the only owner that can mint official coverage; non-financial owners are explicitly rejected. Hence this round does not meet the requested genuine Context+Feature+Policy positive proof tests and must not be marked Task 7 DONE.

```text
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_coverage_manifest tests.test_formal_coverage_guards -v
Ran 42 tests in 13.323s — OK

& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_coverage_manifest tests.test_formal_coverage_guards tests.test_formal_snapshot_repository tests.test_formal_universe -v
Ran 73 tests in 14.727s — OK
```

## Formal review fix round 4 — genuine Context, Feature and Policy owners

The missing owner integration is implemented entirely in the Task 7 module and its guard tests. No owning repository, plan, ledger, or production data was changed.

- The signed descriptor remains the selector preimage: its canonical hash, owner, member, exchange, domain, and period/window must agree with the complete signed requirement. For the new as-of adapters, `period_or_window` denotes the frozen cutoff. Equivalent Beijing/UTC timestamps are normalized only for repository selection; the original signed requirement bytes remain part of the receipt hash.
- Context requires the constructor-authenticated exact `FormalContextRepository` on the same store/snapshot repository/verifier. It invokes `get_verified` for the signed kind/scope/member/cutoff/root and binds the selected `FormalContextFact`, its source evidence, and every registry hash into the requirement receipt.
- Feature requires the authentic exact `FormalFeatureRepository` and its store-owned typed current input provider. It authenticates the persisted input receipt, then uses the genuine current per-slot metric selection for required signed slots. This preserves valid slot evidence when unrelated history/quarter slots are incomplete. Optional slots use the existing complete current-bundle entry. It compares the selected input/bundle identity, requires a derived slot with matching units, and retains the full bundle, current selection, persisted facts, and verified source refs.
- Policy requires an exact `FormalPolicyRepository` and genuine sealed `VerifiedPolicyResultBatch` belonging to that owner/store. `recheck_current` revalidates the original Context/Feature/market selections and signed scoring/policy registries. The adapter binds the signed batch hash, frozen root, universe, population, member, rule, complete selected decision, and entire evidence batch. Missing or pending selected decisions cannot authorize coverage. Dictionaries, booleans, generic callbacks, and uninitialized owner instances are rejected.
- Canonical rows are derived from owners. A supplied row must exactly agree with that derived record. Aggregate lineage columns retain sorted distinct source values; the complete source refs and owner evidence are kept in canonical provenance. The complete requirement hash, record hash, selection hash, evidence hash, frozen input, and registry hashes are bound together.
- Both preview and official gates rerun authenticated contract/root/environment checks and the fixed owner adapter, comparing fresh provenance to the sealed receipt. Database identity is checked again after owner reads. The existing financial adapter and its callback-constraining repository reads remain intact.

RED evidence: before implementation, the real three-owner fixture completed and the genuine positive test failed for each of Context, Feature, and Policy because `_audit_payload` did not accept `context_repository` (`Ran 1 test in 59.972s — FAILED, errors=3`). This was followed by an integrated run exposing equivalent-cutoff representations, the aggregate-vs-slot Feature distinction, and an existing rejection-message assertion; those were corrected. The owner-only integration run then passed all six original grouped tests in 255.332 seconds. The same scenarios were subsequently split into separate Context/Feature/Policy test names for clearer progress and failure reporting.

The tests persist real signed graphs, universe/Context/financial producers, current feature inputs and a sealed Policy batch for SH/SZ/BJ members. They cover genuine readiness for each owner; both gates rejecting changed raw bytes without a database change; wrong owner/key/scope/slot/rule; signed cross-root input; plain batch impostors; and owner-side Policy publication revocation. Fixture metric formulas share a signed synthetic input to keep the evidence set small. This is software-boundary evidence, not an approved production data run. Exchange-wide Context calendars and other owner families continue to require their distinct selection contracts; this change exercises per-security Context facts, required Feature slots and Policy security/rule items.

Test execution note: the assigned worktree is outside the shell's default writable roots. Early fixture setup was stopped after a traceback identified Windows `tempfile.mkdtemp` retrying denied worktree writes. The scoped tests were rerun with approved worktree access; no production chain or network request was involved.

Focused verification completed:

```text
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_coverage_manifest tests.test_formal_coverage_guards -v
Ran 52 tests in 371.814s — OK

& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_coverage_guards.OwnerCoverageAdapterTests.test_feature_gates_reject_stale_current_inputs_with_intact_historical_receipt -v
Ran 1 test in 85.651s — OK
```

The additional Feature regression publishes a new issue snapshot through the genuine current input provider. The persisted historical receipt remains authenticated, raw source files are unchanged, and the DB generation remains equal; both coverage gates nevertheless reject the old selection. This tests current selection separately from raw-integrity or DB-generation checks.

Operational concern for later production use: Policy rows currently retain the entire canonical batch evidence to make every dependency binding explicit. That duplicates batch content across requirements; this round does not establish production-size memory or runtime behavior. A future compact representation would need a separately bound shared evidence catalog rather than dropping dependency hashes.

Final exact four-module verification (including the stale-current Feature regression and the genuine foreign-Policy-owner rejection):

```text
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_coverage_manifest tests.test_formal_coverage_guards tests.test_formal_snapshot_repository tests.test_formal_universe -v
Ran 84 tests in 242.278s — OK
```

`git diff --check` passed. Only the Task 7 module and its guard-test file are included in the round 4 commit; the pre-existing plan modification is preserved and excluded. This report remains in the ignored working evidence directory.

Round 4 commit: `9999ff1 fix: validate coverage through typed domain owners` (2 files, 415 insertions, 11 deletions). Post-commit status contains only the pre-existing plan modification.

## Formal review fix round 5 — exchange calendars and closed owner/domain scope

This is the fifth and final allowed Task 7 repair round, based on `9999ff1`. The implementation and test changes stay in `ashare_pipeline/formal_coverage_manifest.py` and `tests/test_formal_coverage_guards.py`; this ignored report records working evidence. The pre-existing plan edit is excluded.

### Calendar authority

The generic Context API intentionally rejects `trading_calendar`. The coverage adapter now uses the genuine `FormalContextRepository.resolve_verified_calendar_binding(CalendarSelector, exchange, cutoff, root)` entry. A signed calendar descriptor includes `context_kind`, `scope_key`, `as_of_utc`, and `as_of_rule=visible_at_freeze`, plus the existing member/domain/exchange/window/owner fields. Its canonical hash remains the signed selector hash of the complete requirement.

The adapter retains the exact typed CalendarSelector, the repository-returned immutable binding, the selected exchange-wide fact, source snapshot/manifest/task, raw source hashes, registry identities and full requirement hash. It explicitly checks the null source security against the selected exchange, while the row remains bound to its frozen member. Calendar authority comes from the authenticated repository call, not from the binding dataclass alone. It repeats the exchange selector after collecting the source evidence, and both readiness gates repeat the entire authenticated selection and compare the fresh receipt. SH evidence cannot satisfy SZ or BJ requirements.

Genuine SH/SZ/BJ positives and cross-exchange, wrong scope/kind/as-of rule, wrong cutoff, raw-tamper, later calendar correction and revoked producer cases are covered. A raw-byte attack leaves the database generation unchanged and still fails both gates. A correction selects the new genuine calendar in a fresh manifest and invalidates the old manifest; a revoked source task also prevents a fresh audit.

### Closed formal source catalog

The scope decision follows Stage D design sections 3–5, 7.3, 9, 13 and 15, plus the release contract's source requirements. Section 9 is an independent production-data audit. Section 15 specifically names missing financial/market/industry/Context/Policy/Range/regulatory/event/consensus sources. The closed mapping is now enforced during signed contract/catalog verification, before evidence adapters or caller validators can run:

| Signed domain | Required owner | Authenticated selection |
| --- | --- | --- |
| `financial` | `formal_snapshot_repository` | Verified raw snapshot and financial facts; existing callback receipt constrained to actual evidence |
| `trading_calendar` | `formal_context_repository` | Exchange-specific CalendarSelector API and global fact/source binding |
| `market_close`, `security_state`, `industry_snapshot`, `regulatory_state`, `event_calendar`, `consensus_snapshot` | `formal_context_repository` | Exact matching Context kind/scope/member/cutoff/root |
| `context` | `formal_context_repository` | Compatibility umbrella restricted to those six non-calendar Context kinds |
| `feature` | `formal_feature_repository` | Current signed Feature input/slot and underlying financial evidence |
| `policy` | `formal_policy_repository` | Original published security/rule decision and complete current evidence graph |
| `market`, `range` | `formal_policy_repository` | Complete signed `market_liquidity` window, underlying authenticated Market/Range observations and calendar-coverage binding |

`market` and `range` mean the selected policy's signed trading window. The fixed adapter checks the actual rule kind, security/exchange/root/cutoff/rule identity, complete required trading-day coverage, absence of pending evidence, and the original market selection in the genuine Policy batch. A genuine ST-clear decision cannot substitute for that window. Canonical source lineage includes the authenticated Range observations' snapshot, raw/manifest hashes, task, request, versions, timestamps and generation. The original Policy recheck authenticates the underlying Range/Market repositories and the bound calendar before coverage can pass. There is no new caller callback authority.

The frozen universe and its listing sources remain authenticated root prerequisites, rather than separately named member-domain rows. Invalid signed Policy selections are rejected from the genuine immutable batch before expensive source reads; every accepted Policy/Market/Range row still requires the original owner's complete current recheck. The per-audit cache is filled only after that recheck succeeds.

Metric percentiles, Stage C adjusted valuation, base-score-input and D1 final-input batches are downstream calculation proofs with their own Stage B/C/D repository gates. They are outside the section 9 source-evidence catalog: `metric`, `valuation`, `score_input` and `final_input`, their standalone repository owners, and arbitrary owner/domain pairs are rejected at contract verification. This does not grant those calculations readiness. Within the documented source-audit scope, no required source family remains without an adapter. If a later approved contract introduces independent downstream-proof coverage domains, it requires an explicit typed adapter/schema extension; arbitrary owner strings cannot enter today's official catalog.

### RED and fixture adjustments

- The corrected genuine calendar fixture was RED on the new signed calendar descriptor before implementation (`coverage contract selector descriptor or owner mismatch`). The original generic entry was confirmed by source inspection to reject trading calendars without an exchange selector.
- Eleven signed domain substitutions into the financial owner were RED (`ValueError not raised` for `made_up`, calendar, Context, Feature, Policy, Market, Range and the four downstream proof families). The closed catalog now rejects them before the evidence validator is called.
- The genuine Market/Range adapter tests were RED in 129.914 seconds: the positive receipt lacked `market_selection`, and both `market` and `range` accepted an unrelated genuine ST-clear decision.
- Test setup corrections were kept separate from these behavioral REDs: bootstrap calendar source configs must have no exchange scope (the signed Context descriptor provides the exchange), and persisted Context cutoffs use the canonical UTC timestamp. An attempted one-member universe correctly failed because each listing exchange requires ordinary-A evidence. The final market fixture keeps genuine SH/SZ/BJ source/member evidence, exercises one SH market-liquidity window, and covers BJ/SZ with real Context facts. It skips financial history. Two earlier heavier diagnostic runs were stopped and are not counted as successful verification.
- The five Calendar tests passed in 98.796 seconds. Two catalog route/scope tests passed in 0.648 seconds.
- The three genuine Market/Range integration tests passed in 294.755 seconds, including raw calendar and market tampering with unchanged database generation. This run preceded the ordering change that moves invalid-selection rejection ahead of the full Policy recheck; the final specified commands verify the final ordering.
- A targeted Context kind-guard mutation produced five expected failures after removing the kind/domain match, then passed in 0.344 seconds after restoring it. This proves the catalog rejects relabelling a genuine Context kind as another source family.

### Final verification and controller adjudication

Both final commands completed with exit code 0 against the final implementation, including the invalid-selection ordering change:

```text
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_coverage_manifest tests.test_formal_coverage_guards -v
Ran 64 tests in 2379.728s — OK

& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_coverage_manifest tests.test_formal_coverage_guards tests.test_formal_snapshot_repository tests.test_formal_universe -v
Ran 95 tests in 2421.151s — OK
```

These two final commands ran concurrently with separate synthetic fixture databases. All new Calendar/Market/Range/catalog tests passed, as did the existing Context/Feature/Policy genuine positives, current-selection/raw-tamper/publication-revocation attacks, and Snapshot/Universe regressions. Neither command was interrupted or counted from partial output. The long waits were concentrated in the existing full Policy integration checks; process CPU continued increasing and both commands eventually completed normally.

Residual findings and scope limits for the controller:

- No further required source-family adapter gap was found within the documented section 9/15 source-audit scope. The closed mapping above is enforced before evidence callbacks. Metric/Valuation/score-input/final-input are expressly rejected as independent catalog domains, not silently accepted or claimed supported; their downstream readiness still requires their own repositories and gates. If an approved production contract requires them as independent audit domains, this source-audit schema must be explicitly extended before that contract can pass.
- There is no approved production contract/data-run readiness claim here. The positive evidence is from genuine repository-backed, signed synthetic fixtures. No production data, network collection, D1/D2 long chain, plan or ledger edit is part of this round.
- The previously noted Policy evidence duplication remains: each row carries the entire canonical batch and underlying evidence, and full current-state verification is expensive. The roughly 40-minute concurrent final runs are recorded as observed integration-test cost, not a production-size benchmark or a proven causal performance profile. Production-scale runtime/memory behavior remains unestablished; reducing evidence must preserve an authenticated shared dependency catalog.
- `git diff --check` and the staged diff check passed. The staged set is exactly the Task 7 module and guard tests (454 insertions, 15 deletions). The pre-existing plan edit is preserved and excluded; this report remains ignored working evidence.

Round 5 commit: `ef89225 fix: close calendar coverage and catalog owner scope` (2 files, 454 insertions, 15 deletions). Post-commit status contains only the pre-existing plan modification. No plan/ledger status has been changed by this fixer; final Task 7 adjudication remains with the controller.
