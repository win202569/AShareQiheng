# Task 6 implementation report

Status: 6A RED established; implementation pending.

This report records each RED/GREEN cycle, scoped review, commit, and any recovery or provenance concern for Task 6. It is ignored and must never be staged.

## 6A test-first reset

An interrupted first implementer created an unreported `formal_deep_worker.py` before returning a verifiable RED/GREEN record. Its untracked production file was deleted without inspection; the pre-existing test file was retained. This is a test-discipline reset, not an accepted implementation.

RED command:

```powershell
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m unittest -v tests.test_formal_deep_worker
```

Result: exit 1, expected `ModuleNotFoundError: No module named 'ashare_pipeline.formal_deep_worker'`. The next implementer must write the minimal production code from this failure, then record GREEN. No production code, data, or SQLite artifact is currently retained.

## 6A contract/runtime GREEN

Changed interface names: `CalendarBindingPending`, the five frozen typed task payloads,
`FormalTaskSpec`, `FormalRegistryRuntime`, `FormalRegistryRuntimeLoader`,
`FormalUniverseSourceResolution`, `SignedUniverseRequestResolver`,
`derive_collection_refresh_generation`, `FormalWorkerDependencies`,
`FormalCollectionSummary`, and `formal_statement_task_specs`.  The runtime reloads a
verified root bundle and re-constructs the source adapter, mapping registry, and feature
registry only from its signed child blobs.  Queue execution, context work, universe
finalization, and feature rebuild remain explicitly deferred to their assigned deliveries.

GREEN command:

```powershell
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m unittest -v tests.test_formal_deep_worker
```

Result: exit 0; `Ran 6 tests in 0.042s`, `OK`.

Exact GREEN output:

```text
test_date_only_generation_requires_an_exact_selector_and_binding_pair (tests.test_formal_deep_worker.FormalDeepWorkerContractTests.test_date_only_generation_requires_an_exact_selector_and_binding_pair) ... ok
test_date_only_payload_rejects_mismatched_or_partial_prerequisite_binding (tests.test_formal_deep_worker.FormalDeepWorkerContractTests.test_date_only_payload_rejects_mismatched_or_partial_prerequisite_binding) ... ok
test_generation_is_canonical_and_changes_for_root_role_and_calendar_binding (tests.test_formal_deep_worker.FormalDeepWorkerContractTests.test_generation_is_canonical_and_changes_for_root_role_and_calendar_binding) ... ok
test_runtime_loader_reloads_verified_bundle_and_rejects_role_hash_disagreement (tests.test_formal_deep_worker.FormalDeepWorkerContractTests.test_runtime_loader_reloads_verified_bundle_and_rejects_role_hash_disagreement) ... ok
test_statement_specs_are_lexical_and_bind_key_to_derived_generation (tests.test_formal_deep_worker.FormalDeepWorkerContractTests.test_statement_specs_are_lexical_and_bind_key_to_derived_generation) ... ok
test_typed_payloads_are_frozen_and_task_spec_only_accepts_closed_kind_payload_pairs (tests.test_formal_deep_worker.FormalDeepWorkerContractTests.test_typed_payloads_are_frozen_and_task_spec_only_accepts_closed_kind_payload_pairs) ... ok

----------------------------------------------------------------------
Ran 6 tests in 0.042s

OK
```

Regression/scope commands:

```powershell
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m py_compile ashare_pipeline\formal_deep_worker.py tests\test_formal_deep_worker.py
git diff --check
git status --short
git diff --stat
```

Result: compile exit 0 and `git diff --check` exit 0 with no output.  Status showed only
the two allowed worker/test files as untracked; no data, SQLite, ledger, or other source
files changed. `git diff --stat` has no output for untracked files.

Exact final scope output:

```text
git diff --check
(exit 0; no output)

git status --short
?? ashare_pipeline/formal_deep_worker.py
?? tests/test_formal_deep_worker.py

git diff --stat
(exit 0; no output)
```

Concern: this delivery intentionally does not execute queued work or construct context,
universe, or feature-build tasks; those interfaces raise `NotImplementedError` so no
unverified transport, task lease, or persistence path can be reached before their later
delivery contracts exist.

## 6A review-fix round 1 RED

Before changing production code, focused regressions were added for: forged direct
idempotency keys; finalizer's three opaque positional source edges; recursive wire
freezing; direct runtime root/adapter provenance; closed Context request identity;
date-only binding freeze equality; and statement role/hash equality.

RED command:

```powershell
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m unittest -v tests.test_formal_deep_worker
```

Result: exit 1, `Ran 13 tests in 0.114s`, with exactly the expected assertion-level
contract failures: forged idempotency key accepted; non-lexical valid BJ/SH/SZ finalizer
tuple rejected; nested payload role list mutable; adapter from root A accepted for root B;
`market_close` paired with `universe_listing` accepted; mismatched calendar freeze accepted;
and mismatched statement role hash accepted. The seven named regressions are therefore RED
for the reviewed missing behavior, while the six original contract tests remained green.

## 6A review-fix round 1 GREEN

The minimal repair now: derives and enforces the exact canonical V5 key on every direct
`FormalTaskSpec` construction; preserves the finalizer's three opaque BJ/SH/SZ-positioned
source edges without lexical sorting; recursively detaches and freezes payload wires while
retaining deepcopy compatibility for V6 persistence; verifies sealed adapter provenance and
its root against the verified bundle; closes Context kinds/request identity; binds date-only
calendar freeze exactly to `as_of_utc`; and requires statement source/mapping relevant roles
to exactly equal their explicit fields.

One transient post-fix runtime error was diagnosed from its complete traceback: the new wire
freezer removed the `MappingProxyType` import while `FormalRegistryRuntimeLoader` still uses it
to seal injected policies/parsers. The single root-cause repair restored that import; no
contract behavior was changed by this integration correction.

GREEN command:

```powershell
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m unittest -v tests.test_formal_deep_worker
```

Exact GREEN output:

```text
test_context_kind_and_request_identity_reject_non_context_dataset (tests.test_formal_deep_worker.FormalDeepWorkerContractTests.test_context_kind_and_request_identity_reject_non_context_dataset) ... ok
test_date_only_generation_requires_an_exact_selector_and_binding_pair (tests.test_formal_deep_worker.FormalDeepWorkerContractTests.test_date_only_generation_requires_an_exact_selector_and_binding_pair) ... ok
test_date_only_payload_binding_freeze_must_equal_payload_as_of (tests.test_formal_deep_worker.FormalDeepWorkerContractTests.test_date_only_payload_binding_freeze_must_equal_payload_as_of) ... ok
test_date_only_payload_rejects_mismatched_or_partial_prerequisite_binding (tests.test_formal_deep_worker.FormalDeepWorkerContractTests.test_date_only_payload_rejects_mismatched_or_partial_prerequisite_binding) ... ok
test_direct_task_spec_rejects_a_forged_idempotency_key (tests.test_formal_deep_worker.FormalDeepWorkerContractTests.test_direct_task_spec_rejects_a_forged_idempotency_key) ... ok
test_finalizer_uses_its_three_positional_source_edges_without_lexical_sorting (tests.test_formal_deep_worker.FormalDeepWorkerContractTests.test_finalizer_uses_its_three_positional_source_edges_without_lexical_sorting) ... ok
test_generation_is_canonical_and_changes_for_root_role_and_calendar_binding (tests.test_formal_deep_worker.FormalDeepWorkerContractTests.test_generation_is_canonical_and_changes_for_root_role_and_calendar_binding) ... ok
test_runtime_direct_construction_rejects_adapter_from_another_root (tests.test_formal_deep_worker.FormalDeepWorkerContractTests.test_runtime_direct_construction_rejects_adapter_from_another_root) ... ok
test_runtime_loader_reloads_verified_bundle_and_rejects_role_hash_disagreement (tests.test_formal_deep_worker.FormalDeepWorkerContractTests.test_runtime_loader_reloads_verified_bundle_and_rejects_role_hash_disagreement) ... ok
test_statement_roles_must_match_explicit_source_and_mapping_hashes (tests.test_formal_deep_worker.FormalDeepWorkerContractTests.test_statement_roles_must_match_explicit_source_and_mapping_hashes) ... ok
test_statement_specs_are_lexical_and_bind_key_to_derived_generation (tests.test_formal_deep_worker.FormalDeepWorkerContractTests.test_statement_specs_are_lexical_and_bind_key_to_derived_generation) ... ok
test_task_spec_recursively_freezes_nested_payload_data (tests.test_formal_deep_worker.FormalDeepWorkerContractTests.test_task_spec_recursively_freezes_nested_payload_data) ... ok
test_typed_payloads_are_frozen_and_task_spec_only_accepts_closed_kind_payload_pairs (tests.test_formal_deep_worker.FormalDeepWorkerContractTests.test_typed_payloads_are_frozen_and_task_spec_only_accepts_closed_kind_payload_pairs) ... ok

----------------------------------------------------------------------
Ran 13 tests in 0.145s

OK
```

Final verification commands:

```powershell
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m py_compile ashare_pipeline\formal_deep_worker.py tests\test_formal_deep_worker.py
git diff --check
git status --short
git diff --stat
```

Exact result: compile exit 0/no output; `git diff --check` exit 0/no output;
`git status --short` reported only `?? ashare_pipeline/formal_deep_worker.py` and
`?? tests/test_formal_deep_worker.py`; `git diff --stat` exit 0/no output because the two
allowed files remain untracked. No report, data, SQLite, ledger, or unrelated source was staged.

## 6A review-fix round 2 Context capability RED

The first Context harness route was invalid and is not a RED result: importing the integration
`ContextIntegrationTests` class caused unittest collection of that unrelated suite, and its
date-only path did not complete promptly in this environment. The route was removed. A thin,
temporary `StateStore` fixture now stores only signed root/blob descriptors because
`SignedContextRequestResolver` deliberately requires exact `StateStore`; it performs no network,
snapshot, fact, context-repository, or worktree persistence operations. Its one-test resolver
construction/canonical-bytes sanity check passed in 1.480s. A first three-test setup run exposed
only a fixture diagnostic—bootstrap source configs must use dataset `trading_calendar`—which was
corrected by making the signed bootstrap descriptor/config agree. That diagnostic is not RED.

Clean RED command:

```powershell
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m unittest -v tests.test_formal_deep_worker.FormalDeepWorkerContractTests.test_context_payload_uses_sealed_request_capability_and_keeps_it_unpersisted tests.test_formal_deep_worker.FormalDeepWorkerContractTests.test_context_payload_rejects_raw_or_field_mismatched_construction tests.test_formal_deep_worker.FormalDeepWorkerContractTests.test_context_payload_keeps_timestamp_only_calendar_shape_empty
```

Exact result: exit 1; `Ran 3 tests in 4.342s`; all three failures were assertion-level and
expected—`FormalContextTaskPayload.from_request` is absent for genuine resolver-minted calendar
and security-scoped market-close requests, and raw/caller-assembled context payload construction
is still accepted. No production code was edited before this clean RED.

## 6A review-fix round 2 Context capability GREEN

`FormalContextTaskPayload` now accepts a resolver-minted `FormalContextRequest` only as an
`InitVar` construction capability. It is not retained as a dataclass field, equality member, or
serialized task-payload key. Both direct construction and `from_request` call the capability's
sealed `canonical_bytes()` and compare every persisted Context identity field to that canonical
wire: kind, scope, security, freeze, official request, source, request/upstream/refresh values,
root, exact selected role tuple, and optional binding/edge. `formal_context_task_specs(request)`
uses `from_request`. Guessed dataset/scope/security restrictions were removed; resolver closure
is the authority. Timestamp-only requests retain no binding or prerequisite edge. A later
date-only request is subject to the same canonical binding/edge equality before its existing
freeze-pair validation.

Focused GREEN command:

```powershell
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m unittest -v tests.test_formal_deep_worker.FormalDeepWorkerContractTests.test_context_payload_uses_sealed_request_capability_and_keeps_it_unpersisted tests.test_formal_deep_worker.FormalDeepWorkerContractTests.test_context_payload_rejects_raw_or_field_mismatched_construction tests.test_formal_deep_worker.FormalDeepWorkerContractTests.test_context_payload_keeps_timestamp_only_calendar_shape_empty
```

Result: exit 0; `Ran 3 tests in 5.873s`, `OK`. The mismatch assertion was then strengthened to
pass the genuine capability while changing `context_kind`, proving field equality rather than
only absent-capability rejection.

Full GREEN command:

```powershell
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m unittest -v tests.test_formal_deep_worker
```

Result: exit 0; `Ran 16 tests in 9.428s`, `OK`. This includes the thin resolver
`canonical_bytes()` sanity test, sealed calendar `fixture-calendar-SZ` request, security-scoped
`market_close` request with independent signed dataset/scope, raw/mismatched Context rejection,
and all prior 6A regressions.

Final verification commands:

```powershell
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m py_compile ashare_pipeline\formal_deep_worker.py tests\test_formal_deep_worker.py
git diff --check
git status --short
git diff --stat
```

Exact result: compile exit 0/no output; `git diff --check` exit 0/no output;
`git status --short` reported only `?? ashare_pipeline/formal_deep_worker.py` and
`?? tests/test_formal_deep_worker.py`; `git diff --stat` output is empty because both allowed
files are untracked. No commit or staging occurred.

## 6A review-fix round 3 hostile-equality RED

RED command:

```powershell
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m unittest -v tests.test_formal_deep_worker.FormalDeepWorkerContractTests.test_context_payload_rejects_hostile_equality_values_before_task_serialization
```

Exact result: exit 1; one test ran in 5.271s with two assertion-level subtest failures.
`EqualityLiar("market_close")` for `context_kind` and `EqualityLiar("attacker-scope")` for
`scope_key` override equality to masquerade as the sealed values, yet construction and
`FormalTaskSpec.from_payload` both completed. This proves the ordinary equality comparison could
admit a different JSON payload/key. No fixture error occurred and no production code was edited
before this RED.

## 6A review-fix round 3 hostile-equality GREEN

`FormalContextTaskPayload` now validates every caller-retained scalar using exact built-in
types before comparison (`str`, including IDs/hashes/timestamps; exact `OfficialRequest`; exact
`VerifiedCalendarBinding`; exact role-pair tuples). It converts the official request and selected
roles to canonical wire values, compares the complete candidate wire to the resolver-sealed
canonical request wire, then replaces every persisted payload member with freshly reconstructed
sealed values. It consequently neither calls caller-controlled equality nor retains a hostile
subclass/object in payload serialization, task identity, or nested binding/role structures. The
resolver capability remains only an `InitVar` and the legitimate independent scope/dataset,
security-scoped market-close, and date-only calendar behavior remain governed solely by the
signed resolver request.

Focused hostile-value GREEN command:

```powershell
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m unittest -v tests.test_formal_deep_worker.FormalDeepWorkerContractTests.test_context_payload_rejects_hostile_equality_values_before_task_serialization
```

Exact result: exit 0; `Ran 1 test in 1.693s`; `OK`.

Focused Context capability GREEN command:

```powershell
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m unittest -v tests.test_formal_deep_worker.FormalDeepWorkerContractTests.test_context_payload_uses_sealed_request_capability_and_keeps_it_unpersisted tests.test_formal_deep_worker.FormalDeepWorkerContractTests.test_context_payload_rejects_raw_or_field_mismatched_construction tests.test_formal_deep_worker.FormalDeepWorkerContractTests.test_context_payload_keeps_timestamp_only_calendar_shape_empty
```

Exact result: exit 0; `Ran 3 tests in 5.848s`; `OK`.

Full 6A module GREEN command:

```powershell
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m unittest -v tests.test_formal_deep_worker
```

Exact result: exit 0; `Ran 17 tests in 11.561s`; `OK`.

Final verification commands:

```powershell
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m py_compile ashare_pipeline\formal_deep_worker.py tests\test_formal_deep_worker.py
git diff --check
git status --short
git diff --stat
```

Exact result: compile exit 0/no output; `git diff --check` exit 0/no output; `git status --short`
reported only `?? ashare_pipeline/formal_deep_worker.py` and `?? tests/test_formal_deep_worker.py`;
`git diff --stat` output is empty because the two allowed production/test files are untracked.
No commit or staging occurred.

## 6B2 Option B history-gate task identity RED

The D1 financial builder had already sealed the fixed universal baseline
`formal-history-gate-noncyclic-v1` into `formal-feature-input-v2`, but the
feature task-generation wire did not yet bind that semantics.  The new
migration test independently constructed the pre-D1 wire from the same
verified facts, root, and selected snapshot lineage, then scheduled the
current input.

RED command:

```powershell
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m unittest -v tests.test_formal_deep_worker.FormalDeepWorkerContractTests.test_history_gate_rekeys_legacy_feature_input_and_preserves_verified_history
```

Exact result: exit 1; one test ran in 0.173s.  The assertion-level failure
was expected: the rebuilt generation and hand-derived legacy generation were
both `35a6173cbe5201a9ce7b89f1b0c1abbd60bc477655882f875f060c65036d84a8`.
Thus a pre-D1 ungated task could be reused for unchanged facts/root/snapshots.
No fixture error occurred and no production code was modified before this
RED.

During the first green attempt, the test's original setup mistakenly treated
the source worker's *newly generated* task as a legacy artifact after the
production change, so it failed at an obsolete equality assertion.  The test
was corrected to construct an explicit valid pre-D1 `FormalTaskSpec`; the
original generation-equality RED above remains the accepted behavior proof.

## 6B2 Option B history-gate task identity GREEN

`_feature_refresh_generation` now canonically includes
`history_gate_version: "formal-history-gate-noncyclic-v1"`.  The literal
matches D1 exactly but remains local to the task worker, avoiding a dependency
on D1's private implementation symbol.  Because the canonical generation is
part of the V5 idempotency key, an otherwise identical post-D1 enqueue has a
new key.  The existing security/as-of/template supersession call then fences
only unfinished old tasks; verified rows remain audit artifacts.

The migration test uses a real `StateStore`, signed runtime, executed source
statement, and persisted V6 fact.  It proves a manually constructed same-input
legacy task has a different post-D1 generation/key; a verified same-scope
legacy task remains verified; pending and retryable-failed same-scope legacy
tasks become superseded; and otherwise identical tasks differing in template,
security, or freeze remain pending.

Focused GREEN command:

```powershell
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m unittest -v tests.test_formal_deep_worker.FormalDeepWorkerContractTests.test_history_gate_rekeys_legacy_feature_input_and_preserves_verified_history
```

Result: exit 0; `Ran 1 test in 0.248s`; `OK`.

Full verification commands:

```powershell
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m unittest -v tests.test_formal_deep_worker
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m unittest -v tests.test_formal_financial_features
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m py_compile ashare_pipeline\formal_deep_worker.py tests\test_formal_deep_worker.py
```

Result: worker suite exit 0, `Ran 37 tests in 2.444s`, `OK`; financial-feature
suite exit 0, `Ran 36 tests in 0.824s`, `OK`; compile exit 0 with no output.
Only the allowed worker and worker-test source files changed; no data, SQLite,
WAL/SHM, progress, or registry file was touched, staged, or committed.
