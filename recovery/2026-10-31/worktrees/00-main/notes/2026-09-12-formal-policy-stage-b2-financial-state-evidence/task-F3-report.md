# F3 implementation report

Base: `c7fb672bfe47d2831bb4c1e850d6397407b9464b`.
Working tree: `D:/Projects/AShareQiheng/.worktrees/formal-v3-implementation`.
Branch: `codex/formal-v3-implementation`.
Status: implementation frozen; complete amended compatibility GREEN (144 tests); ready for root final independent-review disposition.

## Scope and user decision

The user explicitly chose **保持 v1，本轮记录缺口** after the controller confirmed that the genuine v1 contract cannot consume a quantified event selector. This task implements current security/regulatory state evidence, including the existing signed boolean major-event flag, and the pure closed event-record DTO format. It does not implement or claim quantified event policy consumption.

Six approved task paths (the controller expanded the original five-file whitelist for the demonstrated original-owner authority defect):

- `ashare_pipeline/formal_policy_state.py` (new).
- `ashare_pipeline/formal_policy_values.py`.
- `ashare_pipeline/formal_policy_registry.py` (original-owner private authenticated reader only; no signed contract change).
- `tests/test_formal_policy_state.py` (new).
- `tests/test_formal_policy_values.py`.
- `tests/formal_policy_runtime_fixtures.py`.

This requested report is separate from the six source/test paths. No Git writes, dependency installation, production data/database/signature/network/collection/scoring/pool/publication operations were performed. Fixture data, SQLite files, sources and negative-test deletions belong exclusively to each fixture's TemporaryDirectory. Existing data/progress and `tmpj4zv9_fq/` were preserved. R3's StateStore/source/range files and the controller's plan edits were not modified.

## Implementation and actual API handoff

`FormalPolicyStateRepository(context_repository).select(security_id, as_of_utc, *, template_id, policy_registry)` returns the closure-registered internal `PolicyStateSelection`, with read-only `values`, read-only `lineage`, `selection_hash`, and `recheck()`.

The repository requires the genuine Context repository and policy registry, canonical security ID, the exact UTC freeze `2026-08-31T07:00:00+00:00`, and a signed template. It collects actual signed security_state and regulatory_state inputs, groups them by kind/scope, calls the captured genuine `get_verified_many` with a sorted unique security tuple, and rereads all groups after projection to close cross-group correction/absence races. No legacy exception is interpreted as absence: actual `None` or a genuinely absent flag becomes `runtime/state_entry_missing`; source, signature, receipt, corruption, tie and trust failures remain terminal exceptions.

`values` is keyed by the digest of the exact selector. Values keep the existing six-field non-authoritative PolicyValue shape. Each lineage entry retains the complete original Context Fact (including all flags), exact signed descriptor, requested security/kind/scope/freeze/root, selector/entry ID, applicable rule IDs and entry hash. Top-level lineage binds security/exchange/template, freeze, algorithm/contract version, root, nine role hashes, policy contract hash and rules. Actual fact source times, source/content IDs, request fingerprint, upstream/refresh generation, normalization hash and calendar binding are preserved within the original fact. Missing factor entries carry the exact signed request binding and are rechecked against current Context absence.

The controller approved a genuine internal `FormalMetricContextRepository` companion solely to reuse its retained authentic Context/store/snapshot/raw/verifier dependency checks. There are no calls to load_universe or resolve_industries, no added universe/industry prerequisites, no callback registration, and no alternate state factory. Selection and repository identities live in closure-owned weak-reference registrations; ordinary construction, copies/forgeries, shadows and changed retained dependencies cannot confer authority. Dependency capture occurs at module initialization, not on first selection. PolicyValue parser/serializer class descriptors are pinned as well.

`PolicyRuntimeFixture.put_policy_context(security_id, kind, value, *, generation="g1")` resolves the signed request, enqueues and leases a genuine formal_context task, persists the verified snapshot, normalizes with FixtureNormalizer, persists the sealed Context normalization receipt and completes the task. It returns `(fact, ref)`. New fixture generations use deterministic later timestamps for correction tests. The helper supports security_state, regulatory_state and event_calendar only; invalid/unquantified Context records are rejected by the genuine producer. `state_selection(security_id)` calls the genuine repository using the fixture's signed template. Normal proof setup never uses SQL; SQL is confined to deliberate receipt-loss negatives.

`PolicyValue.from_dict` now accepts only the closed present event_record shape `event_id/event_date/quantified_value/unit`. The nested record is immutable; wire export detaches it and keeps canonical decimal text. Event IDs/units retain controlled Context text (including `%` and `CNY/share`), dates must be valid canonical ISO dates, and quantities must be exact canonical finite decimal strings. Missing quantity is never filled with zero. The outer compound unit remains null; the actual event unit stays inside the record. calendar_record and market_window present values remain rejected. DTO construction does not grant require_verified/recheck or current visibility.

## Explicit remaining v1 gap

`formal_policy_contract.py` defines event_calendar.event as event_record, but parse_policy_rule admits only numeric_redline (feature), boolean_state (bool), enum_state (enum), cyclic_protection (feature/annual_series), and market_liquidity (market_record/calendar_record). Its typed selector check rejects event_record for every current rule kind. No accepted rule can request quantified event evidence or express its date/unit/effective-time consumption semantics.

Accordingly there is no event-calendar policy read, fabricated pending rule, new rule kind, fake signed event selector, unreachable activation stub, dynamic compound validator or signature-contract relaxation. A regression attempts a genuine signed v1 event_record input and verifies rejection. Another proves that adding an unrequested genuine event-calendar factor does not change a state selection. The closed DTO date/unit/quantity tests cover format only, never policy applicability, effective-time proof or quantified event rule evaluation. Future activation needs a separately versioned specification.

## TDD and corrective evidence

The complete TDD SKILL.md and writing-good-tests.md were read before test/production edits. Verification-before-completion was read for final acceptance.

Initial required RED command:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_state -v
```

Observed: all 12 initial tests failed at the explicit feature-presence assertion, before any implementation existed:

```text
AssertionError: unexpectedly None : authenticated policy state selection is missing
Ran 12 tests in 0.002s
FAILED (failures=12)
```

Exit 1; command wall time 0.5734652 s. Covered initial requirements: false/missing flag, genuine expected=false, missing factor, missing entry, security enums/suspension, unauthorized IDs, correction, lost raw source, copying, method shadows, invalid freeze/template/registry.

Closed DTO RED command:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_values.PolicyValueTests.test_event_record_preserves_four_fields_without_evidence_authority -v
```

The first run exposed the expected old compound ValueError (one error; 0.000 s). The test translated the known unsupported branch into an explicit assertion and reran RED before implementation:

```text
AssertionError: the closed event record must preserve actual Context fields: compound policy values require their closed producer validator
Ran 1 test in 0.001s
FAILED (failures=1)
```

Exit 1; wall 0.2757083 s.

Context-unit RED command:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_values.PolicyValueTests.test_event_dto_preserves_context_unit_text_without_claiming_visibility -v
```

```text
AssertionError: Context unit text and scheduled date must be retained by the DTO: event unit must be a canonical identifier
Ran 1 test in 0.001s
FAILED (failures=1)
```

Exit 1; wall 0.2686968 s. Fixed the overly narrow unit identifier check to preserve controlled actual Context unit text. Pure DTO class then passed 11 tests in 0.001 s (exit 0; wall 0.3584233 s).

Initial focused integration command:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_state tests.test_formal_policy_values.PolicyValueTests -v
```

22 tests in 74.508 s, exit 1, two fixture-test setup errors: attempting to change a mandatory audit rule to expected=false violates the unchanged v1 coverage contract; attempting copy.copy(registry) raises immediately by design. Corrected the fixture test to add an optional genuinely signed regulatory rule and whitelisted flag with expected=false, preserving every mandatory expected=true semantic. Replaced the copied-registry test input with an unregistered forged instance. No production contract was changed.

Subsequent state-only diagnostic: 20 tests in 155.305 s, exit 0. This ran before the final two dependency regressions and is not the final frozen acceptance.

## Retained-method and copy regressions

The two retained DTO-method tests first reproduced invalid behavior: a plain-function replacement of from_dict raised AttributeError instead of an integrity failure, and a replaced to_dict could mint a selection. The test assertions captured both failures before the production fix.

Command (RED and GREEN):

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_state.PolicyStateTests.test_value_validator_replacement_is_an_integrity_failure tests.test_formal_policy_state.PolicyStateTests.test_value_serializer_replacement_cannot_forge_selected_values -v
```

RED output (exit 1; wall 7.9154676 s):

```text
test_value_validator_replacement_is_an_integrity_failure (tests.test_formal_policy_state.PolicyStateTests.test_value_validator_replacement_is_an_integrity_failure) ... FAIL
test_value_serializer_replacement_cannot_forge_selected_values (tests.test_formal_policy_state.PolicyStateTests.test_value_serializer_replacement_cannot_forge_selected_values) ... FAIL

======================================================================
FAIL: test_value_validator_replacement_is_an_integrity_failure (tests.test_formal_policy_state.PolicyStateTests.test_value_validator_replacement_is_an_integrity_failure)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\tests\test_formal_policy_state.py", line 175, in test_value_validator_replacement_is_an_integrity_failure
    selected.recheck()
    ^^^^^^^^^^^^^^^^
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\ashare_pipeline\formal_policy_state.py", line 99, in __getattr__
    payload = json.loads(record(self)[1])
                         ^^^^^^^^^^^^
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\ashare_pipeline\formal_policy_state.py", line 71, in record
    interfaces()
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\ashare_pipeline\formal_policy_state.py", line 59, in interfaces
    or PolicyValue.from_dict.__func__ is not parse_value.__func__):
       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AttributeError: 'function' object has no attribute '__func__'. Did you mean: '__doc__'?

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\tests\test_formal_policy_state.py", line 177, in test_value_validator_replacement_is_an_integrity_failure
    self.fail(f"validator substitution requires an integrity error: {error}")
AssertionError: validator substitution requires an integrity error: 'function' object has no attribute '__func__'

======================================================================
FAIL: test_value_serializer_replacement_cannot_forge_selected_values (tests.test_formal_policy_state.PolicyStateTests.test_value_serializer_replacement_cannot_forge_selected_values)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\tests\test_formal_policy_state.py", line 183, in test_value_serializer_replacement_cannot_forge_selected_values
    with self.assertRaises(ValueError):
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: ValueError not raised

----------------------------------------------------------------------
Ran 2 tests in 7.378s

FAILED (failures=2)
```

The implementation pins the original class descriptors rather than assuming a replacement is a bound classmethod.

GREEN output (exit 0; wall 5.9453531 s):

```text
test_value_validator_replacement_is_an_integrity_failure (tests.test_formal_policy_state.PolicyStateTests.test_value_validator_replacement_is_an_integrity_failure) ... ok
test_value_serializer_replacement_cannot_forge_selected_values (tests.test_formal_policy_state.PolicyStateTests.test_value_serializer_replacement_cannot_forge_selected_values) ... ok

----------------------------------------------------------------------
Ran 2 tests in 5.436s

OK
```

The first prescribed compatibility run exposed a separate F3-local sequence bug: copy.copy of the slotted repository added Python's __slotnames__ class cache, which correctly tripped the complete interface identity guard but left later genuine repositories unusable. An isolated previously failing factor test passed (one test in 2.487 s); copied-repository followed by current-correction reproduced the interface failure (two tests in 11.897 s), identifying sequence poisoning rather than an R3 or lease defect.

Strengthened RED:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_state.PolicyStateTests.test_copied_selection_or_repository_has_no_authority -v
```

```text
test_copied_selection_or_repository_has_no_authority (tests.test_formal_policy_state.PolicyStateTests.test_copied_selection_or_repository_has_no_authority) ... FAIL

======================================================================
FAIL: test_copied_selection_or_repository_has_no_authority (tests.test_formal_policy_state.PolicyStateTests.test_copied_selection_or_repository_has_no_authority)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\tests\test_formal_policy_state.py", line 154, in test_copied_selection_or_repository_has_no_authority
    with self.assertRaises(TypeError):
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: TypeError not raised

----------------------------------------------------------------------
Ran 1 test in 1.860s

FAILED (failures=1)
```

Exit 1; wall 2.4120409 s. Explicit repository __copy__/__deepcopy__ now reject copying before Python caches slots, and the regression verifies the original repository remains usable.

GREEN:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_state.PolicyStateTests.test_copied_selection_or_repository_has_no_authority tests.test_formal_policy_state.PolicyStateTests.test_current_correction_invalidates_even_same_value -v
```

```text
test_copied_selection_or_repository_has_no_authority (tests.test_formal_policy_state.PolicyStateTests.test_copied_selection_or_repository_has_no_authority) ... ok
test_current_correction_invalidates_even_same_value (tests.test_formal_policy_state.PolicyStateTests.test_current_correction_invalidates_even_same_value) ... ok

----------------------------------------------------------------------
Ran 2 tests in 30.103s

OK
```

Exit 0. The existing failed compatibility process output was retained; the controller then directed interruption of that superseded run before a fresh full run.

## Approved lineage assurance boundary

The controller explicitly accepted complete selected Context Fact plus exact signed selector/descriptor/read scope as F3's internal authenticated reference. This is not an embedded full OfficialSnapshotRef or standalone receipt export. The existing normalization_input_hash binds the full request, snapshot manifest/content and full Fact, while get_verified_many replays the producer, receipt and raw validation, including historical-calendar capability. Receipt-loss/raw-loss tests exercise revocation. No new current-only snapshot reads were introduced. Final cross-stage consumers must recheck this internal object; serialized lineage does not grant current evidence authority.

## Superseded compatibility attempt

The first prescribed compatibility process used the pre-copy-fix state hash `82382D6358076CDFFA5B8566270AEE7F0CB7810C7008638BED35E31CD08F8AAC` and state-test hash `874D065468502CD19046B3EE6CF8C4B0F2183BEA878B413AA1D1BDAB30B525EB`. It was already failed by the reproduced copy-cache problem. At the controller's explicit direction it was interrupted only via its own tool session (58268) after retaining all emitted output. Exit 1; observed elapsed 358.961 s. It did not reach a final unittest count and is **not acceptance evidence**.

The long historical-calendar-revision case completed successfully before interruption. One range-enabled fixture error was also reported in that old process, but its traceback had not been emitted; a single isolated diagnostic of that unchanged test passed in 1.624 s (exit 0). No cause is claimed for that unprinted traceback, and no R3-owned file was edited. Fresh complete compatibility must cover it.

Complete emitted output from the aborted process:

```text
test_absent_factor_is_bound_pending_and_late_factor_invalidates (tests.test_formal_policy_state.PolicyStateTests.test_absent_factor_is_bound_pending_and_late_factor_invalidates) ... ok
test_audit_views_are_detached_and_read_only (tests.test_formal_policy_state.PolicyStateTests.test_audit_views_are_detached_and_read_only) ... ok
test_context_method_shadow_is_rejected_before_and_after_selection (tests.test_formal_policy_state.PolicyStateTests.test_context_method_shadow_is_rejected_before_and_after_selection) ... ok
test_copied_selection_or_repository_has_no_authority (tests.test_formal_policy_state.PolicyStateTests.test_copied_selection_or_repository_has_no_authority) ... ok
test_current_correction_invalidates_even_same_value (tests.test_formal_policy_state.PolicyStateTests.test_current_correction_invalidates_even_same_value) ... ERROR
test_equal_leading_versions_are_not_pending (tests.test_formal_policy_state.PolicyStateTests.test_equal_leading_versions_are_not_pending) ... ERROR
test_false_flag_is_not_missing_flag (tests.test_formal_policy_state.PolicyStateTests.test_false_flag_is_not_missing_flag) ... ok
test_missing_flag_is_pending_and_keeps_whole_factor (tests.test_formal_policy_state.PolicyStateTests.test_missing_flag_is_pending_and_keeps_whole_factor) ... ERROR
test_real_false_matches_signed_expected_false (tests.test_formal_policy_state.PolicyStateTests.test_real_false_matches_signed_expected_false) ... ERROR
test_receipt_loss_revokes_current_selection (tests.test_formal_policy_state.PolicyStateTests.test_receipt_loss_revokes_current_selection) ... ERROR
test_registered_raw_loss_is_failure_not_pending (tests.test_formal_policy_state.PolicyStateTests.test_registered_raw_loss_is_failure_not_pending) ... ERROR
test_replaced_raw_store_or_verifier_invalidates_retained_repository (tests.test_formal_policy_state.PolicyStateTests.test_replaced_raw_store_or_verifier_invalidates_retained_repository) ... ERROR
test_security_flags_and_enum_are_projected_without_suspension_veto (tests.test_formal_policy_state.PolicyStateTests.test_security_flags_and_enum_are_projected_without_suspension_veto) ... ERROR
test_selection_method_shadow_is_rejected (tests.test_formal_policy_state.PolicyStateTests.test_selection_method_shadow_is_rejected) ... ERROR
test_signed_major_event_flag_remains_boolean_not_quantified_zero (tests.test_formal_policy_state.PolicyStateTests.test_signed_major_event_flag_remains_boolean_not_quantified_zero) ... ERROR
test_unapproved_flag_or_event_id_fails_producer_contract (tests.test_formal_policy_state.PolicyStateTests.test_unapproved_flag_or_event_id_fails_producer_contract) ... ok
test_unquantified_context_event_cannot_be_zero_filled (tests.test_formal_policy_state.PolicyStateTests.test_unquantified_context_event_cannot_be_zero_filled) ... ok
test_unrequested_event_factor_is_not_read_or_given_policy_authority (tests.test_formal_policy_state.PolicyStateTests.test_unrequested_event_factor_is_not_read_or_given_policy_authority) ... ERROR
test_v1_genuine_registry_rejects_quantified_event_rule_input (tests.test_formal_policy_state.PolicyStateTests.test_v1_genuine_registry_rejects_quantified_event_rule_input) ... ok
test_value_serializer_replacement_cannot_forge_selected_values (tests.test_formal_policy_state.PolicyStateTests.test_value_serializer_replacement_cannot_forge_selected_values) ... ERROR
test_value_validator_replacement_is_an_integrity_failure (tests.test_formal_policy_state.PolicyStateTests.test_value_validator_replacement_is_an_integrity_failure) ... ERROR
test_wrong_freeze_template_and_registry_fail (tests.test_formal_policy_state.PolicyStateTests.test_wrong_freeze_template_and_registry_fail) ... ERROR
test_bridge_preserves_v6_float_not_original_decimal (tests.test_formal_policy_values.DecimalBridgeTests.test_bridge_preserves_v6_float_not_original_decimal) ... ok
test_canonical_helpers_are_deterministic_and_reject_nonfinite_json (tests.test_formal_policy_values.DecimalBridgeTests.test_canonical_helpers_are_deterministic_and_reject_nonfinite_json) ... ok
test_decimal_wire_is_fixed_minimal_and_independent_of_ambient_precision (tests.test_formal_policy_values.DecimalBridgeTests.test_decimal_wire_is_fixed_minimal_and_independent_of_ambient_precision) ... ok
test_financial_helpers_reject_invalid_security_without_persistence (tests.test_formal_policy_values.PolicyRuntimeFixtureTests.test_financial_helpers_reject_invalid_security_without_persistence) ... ok
test_five_template_mapping_defines_matching_frozen_universe_and_memberships (tests.test_formal_policy_values.PolicyRuntimeFixtureTests.test_five_template_mapping_defines_matching_frozen_universe_and_memberships) ... ok
test_fixture_builds_one_genuine_signed_policy_runtime_graph (tests.test_formal_policy_values.PolicyRuntimeFixtureTests.test_fixture_builds_one_genuine_signed_policy_runtime_graph) ... ok
test_fixture_registry_detects_signed_child_mutation (tests.test_formal_policy_values.PolicyRuntimeFixtureTests.test_fixture_registry_detects_signed_child_mutation) ... ok
test_policy_financial_values_writes_distinct_real_fy_evidence_and_receipt (tests.test_formal_policy_values.PolicyRuntimeFixtureTests.test_policy_financial_values_writes_distinct_real_fy_evidence_and_receipt) ... ok
test_put_policy_financial_requires_explicit_year_and_per_key_units (tests.test_formal_policy_values.PolicyRuntimeFixtureTests.test_put_policy_financial_requires_explicit_year_and_per_key_units) ... ok
test_range_enabled_fixture_integrates_real_signed_range_documents (tests.test_formal_policy_values.PolicyRuntimeFixtureTests.test_range_enabled_fixture_integrates_real_signed_range_documents) ... ERROR
test_dto_detaches_input_and_output_containers (tests.test_formal_policy_values.PolicyValueTests.test_dto_detaches_input_and_output_containers) ... ok
test_enum_preserves_exact_strings_without_identifier_restrictions (tests.test_formal_policy_values.PolicyValueTests.test_enum_preserves_exact_strings_without_identifier_restrictions) ... ok
test_event_dto_preserves_context_unit_text_without_claiming_visibility (tests.test_formal_policy_values.PolicyValueTests.test_event_dto_preserves_context_unit_text_without_claiming_visibility) ... ok
test_event_record_preserves_four_fields_without_evidence_authority (tests.test_formal_policy_values.PolicyValueTests.test_event_record_preserves_four_fields_without_evidence_authority) ... ok
test_event_record_rejects_malformed_dates_units_or_quantities (tests.test_formal_policy_values.PolicyValueTests.test_event_record_rejects_malformed_dates_units_or_quantities) ... ok
test_exact_wire_and_hash_shapes_are_required (tests.test_formal_policy_values.PolicyValueTests.test_exact_wire_and_hash_shapes_are_required) ... ok
test_missing_and_domain_conflict_are_typed_records_not_values (tests.test_formal_policy_values.PolicyValueTests.test_missing_and_domain_conflict_are_typed_records_not_values) ... ok
test_nonmissing_remaining_compound_records_wait_for_closed_producer_validators (tests.test_formal_policy_values.PolicyValueTests.test_nonmissing_remaining_compound_records_wait_for_closed_producer_validators) ... ok
test_runtime_and_signed_policy_pending_reasons_are_strict (tests.test_formal_policy_values.PolicyValueTests.test_runtime_and_signed_policy_pending_reasons_are_strict) ... ok
test_scalar_values_use_exact_types_and_normalize_evidence_hashes (tests.test_formal_policy_values.PolicyValueTests.test_scalar_values_use_exact_types_and_normalize_evidence_hashes) ... ok
test_terminal_policy_errors_remain_value_errors (tests.test_formal_policy_values.PolicyValueTests.test_terminal_policy_errors_remain_value_errors) ... ok
test_aliases_non_json_and_nonfinite_values_are_rejected (tests.test_formal_context_schema.ContextSchemaTests.test_aliases_non_json_and_nonfinite_values_are_rejected) ... ok
test_closed_per_kind_values (tests.test_formal_context_schema.ContextSchemaTests.test_closed_per_kind_values) ... ok
test_cutoffs_are_inclusive_and_late_capture_is_allowed (tests.test_formal_context_schema.ContextSchemaTests.test_cutoffs_are_inclusive_and_late_capture_is_allowed) ... ok
test_event_quantity_is_signed_but_market_volume_is_nonnegative (tests.test_formal_context_schema.ContextSchemaTests.test_event_quantity_is_signed_but_market_volume_is_nonnegative) ... ok
test_fact_id_detachment_and_creation_time_exclusion (tests.test_formal_context_schema.ContextSchemaTests.test_fact_id_detachment_and_creation_time_exclusion) ... ok
test_forgery_and_mutation_are_rejected (tests.test_formal_context_schema.ContextSchemaTests.test_forgery_and_mutation_are_rejected) ... ok
test_issue_is_sealed_detached_audit_data (tests.test_formal_context_schema.ContextSchemaTests.test_issue_is_sealed_detached_audit_data) ... ok
test_malformed_calendar_industry_and_allowlist_entry_values (tests.test_formal_context_schema.ContextSchemaTests.test_malformed_calendar_industry_and_allowlist_entry_values) ... ok
test_market_stale_rules_and_exact_types (tests.test_formal_context_schema.ContextSchemaTests.test_market_stale_rules_and_exact_types) ... ok
test_no_coverage_is_explicit_and_consensus_only (tests.test_formal_context_schema.ContextSchemaTests.test_no_coverage_is_explicit_and_consensus_only) ... ok
test_batch_corruption_does_not_become_absence (tests.test_formal_context_repository.ContextIntegrationTests.test_batch_corruption_does_not_become_absence) ... ok
test_batch_detects_correction_between_scope_snapshots (tests.test_formal_context_repository.ContextIntegrationTests.test_batch_detects_correction_between_scope_snapshots) ... ok
test_batch_preserves_leading_tie_failure (tests.test_formal_context_repository.ContextIntegrationTests.test_batch_preserves_leading_tie_failure) ... ok
test_batch_rejects_invalid_identity_instead_of_absence (tests.test_formal_context_repository.ContextIntegrationTests.test_batch_rejects_invalid_identity_instead_of_absence) ... ok
test_batch_selection_preserves_single_result_and_actual_absence (tests.test_formal_context_repository.ContextIntegrationTests.test_batch_selection_preserves_single_result_and_actual_absence) ... ok
test_calendar_exchange_is_a_logical_generation_discriminator (tests.test_formal_context_repository.ContextIntegrationTests.test_calendar_exchange_is_a_logical_generation_discriminator) ... ok
test_calendar_exchange_separation_binding_substitutions_and_no_weekday_inference (tests.test_formal_context_repository.ContextIntegrationTests.test_calendar_exchange_separation_binding_substitutions_and_no_weekday_inference) ... ok
test_calendar_revision_preserves_date_only_history_and_rejects_missing_anchor (tests.test_formal_context_repository.ContextIntegrationTests.test_calendar_revision_preserves_date_only_history_and_rejects_missing_anchor) ... ok
test_consensus_requires_explicit_verified_no_coverage (tests.test_formal_context_repository.ContextIntegrationTests.test_consensus_requires_explicit_verified_no_coverage) ... ok
test_context_writer_new_owner_recovers_same_receipt_and_rejects_old_capability (tests.test_formal_context_repository.ContextIntegrationTests.test_context_writer_new_owner_recovers_same_receipt_and_rejects_old_capability) ... ok
test_context_writer_persists_before_completion_without_publishing_leased_facts (tests.test_formal_context_repository.ContextIntegrationTests.test_context_writer_persists_before_completion_without_publishing_leased_facts) ... ok
test_context_writer_rechecks_lease_after_normalizer_callback (tests.test_formal_context_repository.ContextIntegrationTests.test_context_writer_rechecks_lease_after_normalizer_callback) ... ok
test_context_writer_rejects_expired_lease_at_normalize_and_put (tests.test_formal_context_repository.ContextIntegrationTests.test_context_writer_rejects_expired_lease_at_normalize_and_put) ... ok
test_context_writer_rejects_wrong_worker_and_task (tests.test_formal_context_repository.ContextIntegrationTests.test_context_writer_rejects_wrong_worker_and_task) ... ok
test_context_writer_rolls_back_when_lease_expires_after_insert (tests.test_formal_context_repository.ContextIntegrationTests.test_context_writer_rolls_back_when_lease_expires_after_insert) ... ok
test_date_only_uses_calendar_provenance_without_recursive_self_lookup (tests.test_formal_context_repository.ContextIntegrationTests.test_date_only_uses_calendar_provenance_without_recursive_self_lookup) ...
```

## Superseded five-path hashes and self-review

Historical SHA-256 values before the later original-owner authority correction (not the final frozen files):

| Path | SHA-256 |
| --- | --- |
| ashare_pipeline/formal_policy_state.py | EFCFB41FA0B908E5D4141E9EEAD2957AAC045700A397F1D40B46B67D3E01225A |
| ashare_pipeline/formal_policy_values.py | D69C08D8E1A7ABEEE4B113595420B381DB99EC0B8D55159BD6092331272B8C6D |
| tests/test_formal_policy_state.py | 1EBB602952593FB5F6ECEE1949A3E3E160147232947B2E88234D9DBB60C4CC04 |
| tests/test_formal_policy_values.py | 9DDD4D421D7286B494B1FCBE8A2077C9B270BD3F498F0DF18BA25F23559B7A59 |
| tests/formal_policy_runtime_fixtures.py | 9B9FBB88860F8CF80F56D7E70A40CCE2A6B40DD38ECD202000FFAC44F23CCE9B |

Self-review:

- Only actual active signed state selectors are consumed; no boolean applicability bypass, score/pool calculation or unsigned suspension veto.
- Actual false is present and can match an optional signed expected=false rule. Mandatory v1 expected=true coverage remains unchanged. Missing audit flags/whole factors stay null with runtime/state_entry_missing and evidence hashes bound to the exact request and whole factor.
- Original factor values/source metadata and all flag entries are preserved before projection; no DTO lineage extras, zero substitution, arbitrary source row selector or exception-text classification.
- Current correction with unchanged scalar, absence-to-present change, equal-leading ambiguity and receipt/raw loss fail recheck. Source/store/raw/verifier and method replacement are rejected.
- Read-only detached audit views do not confer proof. Copies/forgeries/shadows cannot substitute for the private registered selection/repository. Explicit copy methods prevent Python's slot cache from mutating the pinned class.
- Closed event DTO has exactly four actual Context fields, immutable nested storage, canonical signed decimal text, valid ISO date and preserved controlled unit text. It deliberately does not validate an as-of visibility claim without a consuming signed rule.
- Explicit user-approved v1 gap remains documented. Present calendar/market compounds and quantified event consumption are deferred.
- `git diff --check` on the five task paths exited 0 (only existing Git LF-to-CRLF advisory messages). This historical freeze was superseded by the six-file authority correction documented below.
- Final cross-stage consumers must still recheck and bind the state selection to their frozen-universe/industry batch. The state API itself intentionally does not create a public cross-stage batch proof.

## Original-owner authority correction and amended scope

Root independently reproduced two genuine authority defects in the earlier state module: replacing the public FormalPolicyRegistry alias before first state import allowed a forged registry to mint/recheck a selection, and replacing the public PolicyValue alias before first state import allowed absent bool factors to become observed true. Exact root probes are retained alongside this report in task-F3-root-preimport-probe.md and task-F3-root-preimport-value-probe.md.

At root direction the then-running corrected-copy compatibility session (81809) was interrupted as superseded diagnostic evidence, exit 1, observed elapsed 242.434 s; no final unittest count was emitted. Its complete emitted output is below. It is not acceptance evidence.

```text
test_absent_factor_is_bound_pending_and_late_factor_invalidates (tests.test_formal_policy_state.PolicyStateTests.test_absent_factor_is_bound_pending_and_late_factor_invalidates) ... ok
test_audit_views_are_detached_and_read_only (tests.test_formal_policy_state.PolicyStateTests.test_audit_views_are_detached_and_read_only) ... ok
test_context_method_shadow_is_rejected_before_and_after_selection (tests.test_formal_policy_state.PolicyStateTests.test_context_method_shadow_is_rejected_before_and_after_selection) ... ok
test_copied_selection_or_repository_has_no_authority (tests.test_formal_policy_state.PolicyStateTests.test_copied_selection_or_repository_has_no_authority) ... ok
test_current_correction_invalidates_even_same_value (tests.test_formal_policy_state.PolicyStateTests.test_current_correction_invalidates_even_same_value) ... ok
test_equal_leading_versions_are_not_pending (tests.test_formal_policy_state.PolicyStateTests.test_equal_leading_versions_are_not_pending) ... ok
test_false_flag_is_not_missing_flag (tests.test_formal_policy_state.PolicyStateTests.test_false_flag_is_not_missing_flag) ... ok
test_missing_flag_is_pending_and_keeps_whole_factor (tests.test_formal_policy_state.PolicyStateTests.test_missing_flag_is_pending_and_keeps_whole_factor) ... ok
test_real_false_matches_signed_expected_false (tests.test_formal_policy_state.PolicyStateTests.test_real_false_matches_signed_expected_false) ... ok
test_receipt_loss_revokes_current_selection (tests.test_formal_policy_state.PolicyStateTests.test_receipt_loss_revokes_current_selection) ... ok
test_registered_raw_loss_is_failure_not_pending (tests.test_formal_policy_state.PolicyStateTests.test_registered_raw_loss_is_failure_not_pending) ... ok
test_replaced_raw_store_or_verifier_invalidates_retained_repository (tests.test_formal_policy_state.PolicyStateTests.test_replaced_raw_store_or_verifier_invalidates_retained_repository) ... ok
test_security_flags_and_enum_are_projected_without_suspension_veto (tests.test_formal_policy_state.PolicyStateTests.test_security_flags_and_enum_are_projected_without_suspension_veto) ... ok
test_selection_method_shadow_is_rejected (tests.test_formal_policy_state.PolicyStateTests.test_selection_method_shadow_is_rejected) ... ok
test_signed_major_event_flag_remains_boolean_not_quantified_zero (tests.test_formal_policy_state.PolicyStateTests.test_signed_major_event_flag_remains_boolean_not_quantified_zero) ... ok
test_unapproved_flag_or_event_id_fails_producer_contract (tests.test_formal_policy_state.PolicyStateTests.test_unapproved_flag_or_event_id_fails_producer_contract) ... ok
test_unquantified_context_event_cannot_be_zero_filled (tests.test_formal_policy_state.PolicyStateTests.test_unquantified_context_event_cannot_be_zero_filled) ... ok
test_unrequested_event_factor_is_not_read_or_given_policy_authority (tests.test_formal_policy_state.PolicyStateTests.test_unrequested_event_factor_is_not_read_or_given_policy_authority) ... ok
test_v1_genuine_registry_rejects_quantified_event_rule_input (tests.test_formal_policy_state.PolicyStateTests.test_v1_genuine_registry_rejects_quantified_event_rule_input) ...
```

The approved scope expanded to six files by adding formal_policy_registry.py. No signed policy syntax, semantic rule, registry document, Context implementation or dynamic registration was changed. The final amended compatibility command adds existing tests.test_formal_policy_registry.

Final owner boundaries:

- `_read_authenticated_policy_registry(proof) -> dict` is created inside the original registry installer. It calls that installer's original proof_record closure, original deserializer and sealed contract hash. It authenticates the original registry class, registration and signed source chain. The owner also checks the private reader entry-point identity. State no longer captures the caller-mutable public registry class or public require_verified/to_dict methods.
- `_policy_value_operations() -> (parse, serialize, check)` is created during value-module initialization. It retains the original bound parser, original unbound serializer, original value/pending classes and their validation helper bindings. State calls the explicit original serializer, never an instance-dispatched serializer. The check rejects public alias, field, method, lookup or inheritance substitution. It permits Python's harmless __slotnames__ copy cache, which is not used by validation or serialization; a regression copies detached DTOs and still rechecks the genuine selection.
- These private original owner authorities are part of the established trusted implementation boundary, consistent with existing formal_sources/formal_range_contract authorities. They are not a caller registration mechanism and do not promise protection from arbitrary replacement of trusted private implementation code before module initialization. No paired-import machinery or extra runtime dependencies were added.

Registry public-alias RED:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_state.PolicyStateTests.test_registry_alias_replacement_before_state_import_cannot_mint_evidence -v
```

```text
AssertionError: 1 != 0 : Traceback (most recent call last):
  File "<string>", line 21, in <module>
AssertionError: public registry alias minted a state selection

Ran 1 test in 28.709s
FAILED (failures=1)
```

Exit 1. The failure was observed before adding the owner reader.

Value alias/parser/serializer RED:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_state.PolicyStateTests.test_value_alias_replacement_before_state_import_cannot_invent_flags tests.test_formal_policy_state.PolicyStateTests.test_value_methods_replaced_before_state_import_are_rejected -v
```

```text
FAIL
test_value_methods_replaced_before_state_import_are_rejected (tests.test_formal_policy_state.PolicyStateTests.test_value_methods_replaced_before_state_import_are_rejected) ... 
  test_value_methods_replaced_before_state_import_are_rejected (tests.test_formal_policy_state.PolicyStateTests.test_value_methods_replaced_before_state_import_are_rejected) (method='from_dict') ... FAIL
  test_value_methods_replaced_before_state_import_are_rejected (tests.test_formal_policy_state.PolicyStateTests.test_value_methods_replaced_before_state_import_are_rejected) (method='to_dict') ... FAIL

======================================================================
FAIL: test_value_alias_replacement_before_state_import_cannot_invent_flags (tests.test_formal_policy_state.PolicyStateTests.test_value_alias_replacement_before_state_import_cannot_invent_flags)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\tests\test_formal_policy_state.py", line 51, in test_value_alias_replacement_before_state_import_cannot_invent_flags
    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
AssertionError: 1 != 0 : Traceback (most recent call last):
  File "<string>", line 24, in <module>
AssertionError: public value alias invented observed flags from absence


======================================================================
FAIL: test_value_methods_replaced_before_state_import_are_rejected (tests.test_formal_policy_state.PolicyStateTests.test_value_methods_replaced_before_state_import_are_rejected) (method='from_dict')
----------------------------------------------------------------------
Traceback (most recent call last):
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\tests\test_formal_policy_state.py", line 89, in test_value_methods_replaced_before_state_import_are_rejected
    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
AssertionError: 1 != 0 : Traceback (most recent call last):
  File "<string>", line 29, in <module>
AssertionError: replaced value method manufactured current evidence


======================================================================
FAIL: test_value_methods_replaced_before_state_import_are_rejected (tests.test_formal_policy_state.PolicyStateTests.test_value_methods_replaced_before_state_import_are_rejected) (method='to_dict')
----------------------------------------------------------------------
Traceback (most recent call last):
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\tests\test_formal_policy_state.py", line 89, in test_value_methods_replaced_before_state_import_are_rejected
    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
AssertionError: 1 != 0 : Traceback (most recent call last):
  File "<string>", line 29, in <module>
AssertionError: replaced value method manufactured current evidence


----------------------------------------------------------------------
Ran 2 tests in 15.075s

FAILED (failures=3)
```

Exit 1; two tests in 15.075 s, three failed assertions including both parser/serializer subtests. After the initial owner-method fix, a further pre-import __getattribute__ substitution was reproduced and then fixed by checking the original owner class members/lookup/inheritance:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_state.PolicyStateTests.test_value_methods_replaced_before_state_import_are_rejected -v
```

```text
test_value_methods_replaced_before_state_import_are_rejected (tests.test_formal_policy_state.PolicyStateTests.test_value_methods_replaced_before_state_import_are_rejected) ... 
  test_value_methods_replaced_before_state_import_are_rejected (tests.test_formal_policy_state.PolicyStateTests.test_value_methods_replaced_before_state_import_are_rejected) (method='__getattribute__') ... FAIL

======================================================================
FAIL: test_value_methods_replaced_before_state_import_are_rejected (tests.test_formal_policy_state.PolicyStateTests.test_value_methods_replaced_before_state_import_are_rejected) (method='__getattribute__')
----------------------------------------------------------------------
Traceback (most recent call last):
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\tests\test_formal_policy_state.py", line 101, in test_value_methods_replaced_before_state_import_are_rejected
    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
AssertionError: 1 != 0 : Traceback (most recent call last):
  File "<string>", line 41, in <module>
AssertionError: replaced value method manufactured current evidence


----------------------------------------------------------------------
Ran 1 test in 5.520s

FAILED (failures=1)
```

Exit 1; one test in 5.520 s.

Final focused owner-boundary GREEN:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_state.PolicyStateTests.test_registry_alias_replacement_before_state_import_cannot_mint_evidence tests.test_formal_policy_state.PolicyStateTests.test_value_alias_replacement_before_state_import_cannot_invent_flags tests.test_formal_policy_state.PolicyStateTests.test_value_methods_replaced_before_state_import_are_rejected tests.test_formal_policy_state.PolicyStateTests.test_state_first_import_preserves_genuine_registry_reads -v
```

```text
test_registry_alias_replacement_before_state_import_cannot_mint_evidence (tests.test_formal_policy_state.PolicyStateTests.test_registry_alias_replacement_before_state_import_cannot_mint_evidence) ... ok
test_value_alias_replacement_before_state_import_cannot_invent_flags (tests.test_formal_policy_state.PolicyStateTests.test_value_alias_replacement_before_state_import_cannot_invent_flags) ... ok
test_value_methods_replaced_before_state_import_are_rejected (tests.test_formal_policy_state.PolicyStateTests.test_value_methods_replaced_before_state_import_are_rejected) ... ok
test_state_first_import_preserves_genuine_registry_reads (tests.test_formal_policy_state.PolicyStateTests.test_state_first_import_preserves_genuine_registry_reads) ... ok

----------------------------------------------------------------------
Ran 4 tests in 10.430s

OK
```

Exit 0. This includes fresh subprocess tests of the original public registry/value alias attacks, parser, serializer and attribute-lookup substitution, plus genuine state-first import.

## Final six-path frozen hashes

| Path | SHA-256 |
| --- | --- |
| ashare_pipeline/formal_policy_state.py | 2775BA031CDCC5F8A5A30D636E6A24690D8CA428F5E8A68DCE014356AF988D62 |
| ashare_pipeline/formal_policy_values.py | 6C4D8E7D2FD47C45D760504DEAFE81F67BEDA3E5BBBE89E94EC8B7435BC2609B |
| ashare_pipeline/formal_policy_registry.py | 9B6D9B7F3F7C9DFDABA14B0687184DDF1990CDF94CB6F4919282CA3D2A70525E |
| tests/test_formal_policy_state.py | C4241517FF5A88D71650310B9D6DB2766F8B01924FE899B449ACDD7B8509D6DF |
| tests/test_formal_policy_values.py | 9DDD4D421D7286B494B1FCBE8A2077C9B270BD3F498F0DF18BA25F23559B7A59 |
| tests/formal_policy_runtime_fixtures.py | 9B9FBB88860F8CF80F56D7E70A40CCE2A6B40DD38ECD202000FFAC44F23CCE9B |

All six files passed git diff --check (exit 0; only LF-to-CRLF Git advisories). These are the final authority-corrected files, held unchanged for the amended full compatibility run.

## Final verification

**GREEN: 144 tests passed in 621.686 s; exit 0.** Module counts: 26 state, 21 values/fixture, 40 existing policy registry, 10 Context schema and 47 Context repository. Tool-observed elapsed through completion polling was 641.553 s; the exact unittest-reported execution time is 621.686 s.

Final exact command:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_state tests.test_formal_policy_values tests.test_formal_policy_registry tests.test_formal_context_schema tests.test_formal_context_repository -v
```

Complete final output:

```text
test_absent_factor_is_bound_pending_and_late_factor_invalidates (tests.test_formal_policy_state.PolicyStateTests.test_absent_factor_is_bound_pending_and_late_factor_invalidates) ... ok
test_audit_views_are_detached_and_read_only (tests.test_formal_policy_state.PolicyStateTests.test_audit_views_are_detached_and_read_only) ... ok
test_context_method_shadow_is_rejected_before_and_after_selection (tests.test_formal_policy_state.PolicyStateTests.test_context_method_shadow_is_rejected_before_and_after_selection) ... ok
test_copied_selection_or_repository_has_no_authority (tests.test_formal_policy_state.PolicyStateTests.test_copied_selection_or_repository_has_no_authority) ... ok
test_current_correction_invalidates_even_same_value (tests.test_formal_policy_state.PolicyStateTests.test_current_correction_invalidates_even_same_value) ... ok
test_equal_leading_versions_are_not_pending (tests.test_formal_policy_state.PolicyStateTests.test_equal_leading_versions_are_not_pending) ... ok
test_false_flag_is_not_missing_flag (tests.test_formal_policy_state.PolicyStateTests.test_false_flag_is_not_missing_flag) ... ok
test_missing_flag_is_pending_and_keeps_whole_factor (tests.test_formal_policy_state.PolicyStateTests.test_missing_flag_is_pending_and_keeps_whole_factor) ... ok
test_real_false_matches_signed_expected_false (tests.test_formal_policy_state.PolicyStateTests.test_real_false_matches_signed_expected_false) ... ok
test_receipt_loss_revokes_current_selection (tests.test_formal_policy_state.PolicyStateTests.test_receipt_loss_revokes_current_selection) ... ok
test_registered_raw_loss_is_failure_not_pending (tests.test_formal_policy_state.PolicyStateTests.test_registered_raw_loss_is_failure_not_pending) ... ok
test_registry_alias_replacement_before_state_import_cannot_mint_evidence (tests.test_formal_policy_state.PolicyStateTests.test_registry_alias_replacement_before_state_import_cannot_mint_evidence) ... ok
test_replaced_raw_store_or_verifier_invalidates_retained_repository (tests.test_formal_policy_state.PolicyStateTests.test_replaced_raw_store_or_verifier_invalidates_retained_repository) ... ok
test_security_flags_and_enum_are_projected_without_suspension_veto (tests.test_formal_policy_state.PolicyStateTests.test_security_flags_and_enum_are_projected_without_suspension_veto) ... ok
test_selection_method_shadow_is_rejected (tests.test_formal_policy_state.PolicyStateTests.test_selection_method_shadow_is_rejected) ... ok
test_signed_major_event_flag_remains_boolean_not_quantified_zero (tests.test_formal_policy_state.PolicyStateTests.test_signed_major_event_flag_remains_boolean_not_quantified_zero) ... ok
test_state_first_import_preserves_genuine_registry_reads (tests.test_formal_policy_state.PolicyStateTests.test_state_first_import_preserves_genuine_registry_reads) ... ok
test_unapproved_flag_or_event_id_fails_producer_contract (tests.test_formal_policy_state.PolicyStateTests.test_unapproved_flag_or_event_id_fails_producer_contract) ... ok
test_unquantified_context_event_cannot_be_zero_filled (tests.test_formal_policy_state.PolicyStateTests.test_unquantified_context_event_cannot_be_zero_filled) ... ok
test_unrequested_event_factor_is_not_read_or_given_policy_authority (tests.test_formal_policy_state.PolicyStateTests.test_unrequested_event_factor_is_not_read_or_given_policy_authority) ... ok
test_v1_genuine_registry_rejects_quantified_event_rule_input (tests.test_formal_policy_state.PolicyStateTests.test_v1_genuine_registry_rejects_quantified_event_rule_input) ... ok
test_value_alias_replacement_before_state_import_cannot_invent_flags (tests.test_formal_policy_state.PolicyStateTests.test_value_alias_replacement_before_state_import_cannot_invent_flags) ... ok
test_value_methods_replaced_before_state_import_are_rejected (tests.test_formal_policy_state.PolicyStateTests.test_value_methods_replaced_before_state_import_are_rejected) ... ok
test_value_serializer_replacement_cannot_forge_selected_values (tests.test_formal_policy_state.PolicyStateTests.test_value_serializer_replacement_cannot_forge_selected_values) ... ok
test_value_validator_replacement_is_an_integrity_failure (tests.test_formal_policy_state.PolicyStateTests.test_value_validator_replacement_is_an_integrity_failure) ... ok
test_wrong_freeze_template_and_registry_fail (tests.test_formal_policy_state.PolicyStateTests.test_wrong_freeze_template_and_registry_fail) ... ok
test_bridge_preserves_v6_float_not_original_decimal (tests.test_formal_policy_values.DecimalBridgeTests.test_bridge_preserves_v6_float_not_original_decimal) ... ok
test_canonical_helpers_are_deterministic_and_reject_nonfinite_json (tests.test_formal_policy_values.DecimalBridgeTests.test_canonical_helpers_are_deterministic_and_reject_nonfinite_json) ... ok
test_decimal_wire_is_fixed_minimal_and_independent_of_ambient_precision (tests.test_formal_policy_values.DecimalBridgeTests.test_decimal_wire_is_fixed_minimal_and_independent_of_ambient_precision) ... ok
test_financial_helpers_reject_invalid_security_without_persistence (tests.test_formal_policy_values.PolicyRuntimeFixtureTests.test_financial_helpers_reject_invalid_security_without_persistence) ... ok
test_five_template_mapping_defines_matching_frozen_universe_and_memberships (tests.test_formal_policy_values.PolicyRuntimeFixtureTests.test_five_template_mapping_defines_matching_frozen_universe_and_memberships) ... ok
test_fixture_builds_one_genuine_signed_policy_runtime_graph (tests.test_formal_policy_values.PolicyRuntimeFixtureTests.test_fixture_builds_one_genuine_signed_policy_runtime_graph) ... ok
test_fixture_registry_detects_signed_child_mutation (tests.test_formal_policy_values.PolicyRuntimeFixtureTests.test_fixture_registry_detects_signed_child_mutation) ... ok
test_policy_financial_values_writes_distinct_real_fy_evidence_and_receipt (tests.test_formal_policy_values.PolicyRuntimeFixtureTests.test_policy_financial_values_writes_distinct_real_fy_evidence_and_receipt) ... ok
test_put_policy_financial_requires_explicit_year_and_per_key_units (tests.test_formal_policy_values.PolicyRuntimeFixtureTests.test_put_policy_financial_requires_explicit_year_and_per_key_units) ... ok
test_range_enabled_fixture_integrates_real_signed_range_documents (tests.test_formal_policy_values.PolicyRuntimeFixtureTests.test_range_enabled_fixture_integrates_real_signed_range_documents) ... ok
test_dto_detaches_input_and_output_containers (tests.test_formal_policy_values.PolicyValueTests.test_dto_detaches_input_and_output_containers) ... ok
test_enum_preserves_exact_strings_without_identifier_restrictions (tests.test_formal_policy_values.PolicyValueTests.test_enum_preserves_exact_strings_without_identifier_restrictions) ... ok
test_event_dto_preserves_context_unit_text_without_claiming_visibility (tests.test_formal_policy_values.PolicyValueTests.test_event_dto_preserves_context_unit_text_without_claiming_visibility) ... ok
test_event_record_preserves_four_fields_without_evidence_authority (tests.test_formal_policy_values.PolicyValueTests.test_event_record_preserves_four_fields_without_evidence_authority) ... ok
test_event_record_rejects_malformed_dates_units_or_quantities (tests.test_formal_policy_values.PolicyValueTests.test_event_record_rejects_malformed_dates_units_or_quantities) ... ok
test_exact_wire_and_hash_shapes_are_required (tests.test_formal_policy_values.PolicyValueTests.test_exact_wire_and_hash_shapes_are_required) ... ok
test_missing_and_domain_conflict_are_typed_records_not_values (tests.test_formal_policy_values.PolicyValueTests.test_missing_and_domain_conflict_are_typed_records_not_values) ... ok
test_nonmissing_remaining_compound_records_wait_for_closed_producer_validators (tests.test_formal_policy_values.PolicyValueTests.test_nonmissing_remaining_compound_records_wait_for_closed_producer_validators) ... ok
test_runtime_and_signed_policy_pending_reasons_are_strict (tests.test_formal_policy_values.PolicyValueTests.test_runtime_and_signed_policy_pending_reasons_are_strict) ... ok
test_scalar_values_use_exact_types_and_normalize_evidence_hashes (tests.test_formal_policy_values.PolicyValueTests.test_scalar_values_use_exact_types_and_normalize_evidence_hashes) ... ok
test_terminal_policy_errors_remain_value_errors (tests.test_formal_policy_values.PolicyValueTests.test_terminal_policy_errors_remain_value_errors) ... ok
test_complete_signed_graph_binds_without_runtime_evidence (tests.test_formal_policy_registry.PolicyBindingTests.test_complete_signed_graph_binds_without_runtime_evidence) ... ok
test_additional_signed_regulatory_semantic_cannot_alias_required_flag (tests.test_formal_policy_registry.PolicyCompatibilityTests.test_additional_signed_regulatory_semantic_cannot_alias_required_flag) ... ok
test_changed_signed_definition_changes_root_bytes_and_rejects_old_scoring (tests.test_formal_policy_registry.PolicyCompatibilityTests.test_changed_signed_definition_changes_root_bytes_and_rejects_old_scoring) ... ok
test_classification_metric_reference_remains_the_only_inactive_exception (tests.test_formal_policy_registry.PolicyCompatibilityTests.test_classification_metric_reference_remains_the_only_inactive_exception) ... ok
test_exact_objects_and_copies_cannot_replace_verified_inputs (tests.test_formal_policy_registry.PolicyCompatibilityTests.test_exact_objects_and_copies_cannot_replace_verified_inputs) ... ok
test_legacy_policy_metadata_mismatch_errors_are_preserved (tests.test_formal_policy_registry.PolicyCompatibilityTests.test_legacy_policy_metadata_mismatch_errors_are_preserved) ... ok
test_mutated_verified_child_bytes_are_rejected (tests.test_formal_policy_registry.PolicyCompatibilityTests.test_mutated_verified_child_bytes_are_rejected) ... ok
test_old_feature_content_cannot_be_mixed_into_changed_feature_graph (tests.test_formal_policy_registry.PolicyCompatibilityTests.test_old_feature_content_cannot_be_mixed_into_changed_feature_graph) ... ok
test_old_signed_graph_remains_loadable_but_has_no_execution_contract (tests.test_formal_policy_registry.PolicyCompatibilityTests.test_old_signed_graph_remains_loadable_but_has_no_execution_contract) ... ok
test_original_verifiers_cannot_be_shadowed_to_accept_copies (tests.test_formal_policy_registry.PolicyCompatibilityTests.test_original_verifiers_cannot_be_shadowed_to_accept_copies) ... ok
test_v1_v2_preserve_original_context_entries_and_consensus_links (tests.test_formal_policy_registry.PolicyCompatibilityTests.test_v1_v2_preserve_original_context_entries_and_consensus_links) ... ok
test_delisting_enum_cannot_veto_listed_securities (tests.test_formal_policy_registry.PolicyCoverageTests.test_delisting_enum_cannot_veto_listed_securities) ... ok
test_duplicate_semantic_across_roles_is_rejected (tests.test_formal_policy_registry.PolicyCoverageTests.test_duplicate_semantic_across_roles_is_rejected) ... ok
test_every_mandatory_semantic_is_required_after_valid_signing (tests.test_formal_policy_registry.PolicyCoverageTests.test_every_mandatory_semantic_is_required_after_valid_signing) ... ok
test_every_scoring_reference_requires_an_active_rule (tests.test_formal_policy_registry.PolicyCoverageTests.test_every_scoring_reference_requires_an_active_rule) ... ok
test_hard_veto_cannot_be_reduced_to_one_pool (tests.test_formal_policy_registry.PolicyCoverageTests.test_hard_veto_cannot_be_reduced_to_one_pool) ... ok
test_independent_status_needs_status_and_explicit_pool (tests.test_formal_policy_registry.PolicyCoverageTests.test_independent_status_needs_status_and_explicit_pool) ... ok
test_invalid_v_dependency_declarations_fail_with_signed_graph (tests.test_formal_policy_registry.PolicyCoverageTests.test_invalid_v_dependency_declarations_fail_with_signed_graph) ... ok
test_mandatory_security_semantics_cannot_use_another_field (tests.test_formal_policy_registry.PolicyCoverageTests.test_mandatory_security_semantics_cannot_use_another_field) ... ok
test_metric_policy_reference_must_belong_to_its_template (tests.test_formal_policy_registry.PolicyCoverageTests.test_metric_policy_reference_must_belong_to_its_template) ... ok
test_nonpositive_equity_requires_lte_zero (tests.test_formal_policy_registry.PolicyCoverageTests.test_nonpositive_equity_requires_lte_zero) ... ok
test_regulatory_semantics_cannot_share_one_generic_flag (tests.test_formal_policy_registry.PolicyCoverageTests.test_regulatory_semantics_cannot_share_one_generic_flag) ... ok
test_st_and_regulatory_rules_cannot_match_false (tests.test_formal_policy_registry.PolicyCoverageTests.test_st_and_regulatory_rules_cannot_match_false) ... ok
test_valuation_dependencies_cover_exact_current_template_v_metrics (tests.test_formal_policy_registry.PolicyCoverageTests.test_valuation_dependencies_cover_exact_current_template_v_metrics) ... ok
test_annual_cross_year_balance_formula_binds_complete_period_set (tests.test_formal_policy_registry.PolicySelectorBindingTests.test_annual_cross_year_balance_formula_binds_complete_period_set) ... ok
test_annual_repeated_slot_fails_even_with_distinct_year_labels (tests.test_formal_policy_registry.PolicySelectorBindingTests.test_annual_repeated_slot_fails_even_with_distinct_year_labels) ... ok
test_context_flag_must_be_authorized (tests.test_formal_policy_registry.PolicySelectorBindingTests.test_context_flag_must_be_authorized) ... ok
test_context_scope_kind_and_field_type_must_match (tests.test_formal_policy_registry.PolicySelectorBindingTests.test_context_scope_kind_and_field_type_must_match) ... ok
test_descriptor_source_identity_fields_and_calendar_must_match (tests.test_formal_policy_registry.PolicySelectorBindingTests.test_descriptor_source_identity_fields_and_calendar_must_match) ... ok
test_distinct_slots_with_identical_formula_cannot_fake_five_years (tests.test_formal_policy_registry.PolicySelectorBindingTests.test_distinct_slots_with_identical_formula_cannot_fake_five_years) ... ok
test_duplicate_context_descriptor_is_rejected_in_v1 (tests.test_formal_policy_registry.PolicySelectorBindingTests.test_duplicate_context_descriptor_is_rejected_in_v1) ... ok
test_input_security_bootstrap_calendar_is_rejected (tests.test_formal_policy_registry.PolicySelectorBindingTests.test_input_security_bootstrap_calendar_is_rejected) ... ok
test_manifest_preserves_full_signed_context_entry_and_identity (tests.test_formal_policy_registry.PolicySelectorBindingTests.test_manifest_preserves_full_signed_context_entry_and_identity) ... ok
test_matching_calendar_text_cannot_bind_sz_calendar_for_sh_and_bj (tests.test_formal_policy_registry.PolicySelectorBindingTests.test_matching_calendar_text_cannot_bind_sz_calendar_for_sh_and_bj) ... ok
test_missing_exchange_and_null_plus_exact_source_are_rejected (tests.test_formal_policy_registry.PolicySelectorBindingTests.test_missing_exchange_and_null_plus_exact_source_are_rejected) ... ok
test_security_market_and_calendar_require_input_security_exchange (tests.test_formal_policy_registry.PolicySelectorBindingTests.test_security_market_and_calendar_require_input_security_exchange) ... ok
test_series_units_must_match_current_even_when_each_slot_matches (tests.test_formal_policy_registry.PolicySelectorBindingTests.test_series_units_must_match_current_even_when_each_slot_matches) ... ok
test_source_identity_mismatch_on_only_bj_is_rejected (tests.test_formal_policy_registry.PolicySelectorBindingTests.test_source_identity_mismatch_on_only_bj_is_rejected) ... ok
test_unknown_cross_template_unit_version_and_period_feature_fail (tests.test_formal_policy_registry.PolicySelectorBindingTests.test_unknown_cross_template_unit_version_and_period_feature_fail) ... ok
test_wrapper_hash_cannot_impersonate_descriptor_entry (tests.test_formal_policy_registry.PolicySelectorBindingTests.test_wrapper_hash_cannot_impersonate_descriptor_entry) ... ok
test_aliases_non_json_and_nonfinite_values_are_rejected (tests.test_formal_context_schema.ContextSchemaTests.test_aliases_non_json_and_nonfinite_values_are_rejected) ... ok
test_closed_per_kind_values (tests.test_formal_context_schema.ContextSchemaTests.test_closed_per_kind_values) ... ok
test_cutoffs_are_inclusive_and_late_capture_is_allowed (tests.test_formal_context_schema.ContextSchemaTests.test_cutoffs_are_inclusive_and_late_capture_is_allowed) ... ok
test_event_quantity_is_signed_but_market_volume_is_nonnegative (tests.test_formal_context_schema.ContextSchemaTests.test_event_quantity_is_signed_but_market_volume_is_nonnegative) ... ok
test_fact_id_detachment_and_creation_time_exclusion (tests.test_formal_context_schema.ContextSchemaTests.test_fact_id_detachment_and_creation_time_exclusion) ... ok
test_forgery_and_mutation_are_rejected (tests.test_formal_context_schema.ContextSchemaTests.test_forgery_and_mutation_are_rejected) ... ok
test_issue_is_sealed_detached_audit_data (tests.test_formal_context_schema.ContextSchemaTests.test_issue_is_sealed_detached_audit_data) ... ok
test_malformed_calendar_industry_and_allowlist_entry_values (tests.test_formal_context_schema.ContextSchemaTests.test_malformed_calendar_industry_and_allowlist_entry_values) ... ok
test_market_stale_rules_and_exact_types (tests.test_formal_context_schema.ContextSchemaTests.test_market_stale_rules_and_exact_types) ... ok
test_no_coverage_is_explicit_and_consensus_only (tests.test_formal_context_schema.ContextSchemaTests.test_no_coverage_is_explicit_and_consensus_only) ... ok
test_batch_corruption_does_not_become_absence (tests.test_formal_context_repository.ContextIntegrationTests.test_batch_corruption_does_not_become_absence) ... ok
test_batch_detects_correction_between_scope_snapshots (tests.test_formal_context_repository.ContextIntegrationTests.test_batch_detects_correction_between_scope_snapshots) ... ok
test_batch_preserves_leading_tie_failure (tests.test_formal_context_repository.ContextIntegrationTests.test_batch_preserves_leading_tie_failure) ... ok
test_batch_rejects_invalid_identity_instead_of_absence (tests.test_formal_context_repository.ContextIntegrationTests.test_batch_rejects_invalid_identity_instead_of_absence) ... ok
test_batch_selection_preserves_single_result_and_actual_absence (tests.test_formal_context_repository.ContextIntegrationTests.test_batch_selection_preserves_single_result_and_actual_absence) ... ok
test_calendar_exchange_is_a_logical_generation_discriminator (tests.test_formal_context_repository.ContextIntegrationTests.test_calendar_exchange_is_a_logical_generation_discriminator) ... ok
test_calendar_exchange_separation_binding_substitutions_and_no_weekday_inference (tests.test_formal_context_repository.ContextIntegrationTests.test_calendar_exchange_separation_binding_substitutions_and_no_weekday_inference) ... ok
test_calendar_revision_preserves_date_only_history_and_rejects_missing_anchor (tests.test_formal_context_repository.ContextIntegrationTests.test_calendar_revision_preserves_date_only_history_and_rejects_missing_anchor) ... ok
test_consensus_requires_explicit_verified_no_coverage (tests.test_formal_context_repository.ContextIntegrationTests.test_consensus_requires_explicit_verified_no_coverage) ... ok
test_context_writer_new_owner_recovers_same_receipt_and_rejects_old_capability (tests.test_formal_context_repository.ContextIntegrationTests.test_context_writer_new_owner_recovers_same_receipt_and_rejects_old_capability) ... ok
test_context_writer_persists_before_completion_without_publishing_leased_facts (tests.test_formal_context_repository.ContextIntegrationTests.test_context_writer_persists_before_completion_without_publishing_leased_facts) ... ok
test_context_writer_rechecks_lease_after_normalizer_callback (tests.test_formal_context_repository.ContextIntegrationTests.test_context_writer_rechecks_lease_after_normalizer_callback) ... ok
test_context_writer_rejects_expired_lease_at_normalize_and_put (tests.test_formal_context_repository.ContextIntegrationTests.test_context_writer_rejects_expired_lease_at_normalize_and_put) ... ok
test_context_writer_rejects_wrong_worker_and_task (tests.test_formal_context_repository.ContextIntegrationTests.test_context_writer_rejects_wrong_worker_and_task) ... ok
test_context_writer_rolls_back_when_lease_expires_after_insert (tests.test_formal_context_repository.ContextIntegrationTests.test_context_writer_rolls_back_when_lease_expires_after_insert) ... ok
test_date_only_uses_calendar_provenance_without_recursive_self_lookup (tests.test_formal_context_repository.ContextIntegrationTests.test_date_only_uses_calendar_provenance_without_recursive_self_lookup) ... ok
test_db_receipt_task_and_raw_tamper_fail_closed (tests.test_formal_context_repository.ContextIntegrationTests.test_db_receipt_task_and_raw_tamper_fail_closed) ... ok
test_descriptor_allowlists_reject_unknown_regulatory_and_event_codes (tests.test_formal_context_repository.ContextIntegrationTests.test_descriptor_allowlists_reject_unknown_regulatory_and_event_codes) ... ok
test_distinct_upstream_generations_preserve_and_select_history (tests.test_formal_context_repository.ContextIntegrationTests.test_distinct_upstream_generations_preserve_and_select_history) ... ok
test_duplicate_json_keys_in_stored_fact_are_rejected (tests.test_formal_context_repository.ContextIntegrationTests.test_duplicate_json_keys_in_stored_fact_are_rejected) ... ok
test_duplicate_leading_calendar_is_not_resolved_by_insertion_order (tests.test_formal_context_repository.ContextIntegrationTests.test_duplicate_leading_calendar_is_not_resolved_by_insertion_order) ... ok
test_equal_leading_versions_are_explicit_conflict (tests.test_formal_context_repository.ContextIntegrationTests.test_equal_leading_versions_are_explicit_conflict) ... ok
test_future_source_is_pending_and_late_capture_is_accepted (tests.test_formal_context_repository.ContextIntegrationTests.test_future_source_is_pending_and_late_capture_is_accepted) ... ok
test_historical_calendar_anchor_tamper_invalidates_existing_capability (tests.test_formal_context_repository.ContextIntegrationTests.test_historical_calendar_anchor_tamper_invalidates_existing_capability) ... ok
test_historical_capability_roundtrips_full_fact_record_and_rejects_id_changes (tests.test_formal_context_repository.ContextIntegrationTests.test_historical_capability_roundtrips_full_fact_record_and_rejects_id_changes) ... ok
test_historical_read_capability_is_target_bound_and_unforgeable (tests.test_formal_context_repository.ContextIntegrationTests.test_historical_read_capability_is_target_bound_and_unforgeable) ... ok
test_missing_duplicate_and_mismatched_descriptor_fail_closed (tests.test_formal_context_repository.ContextIntegrationTests.test_missing_duplicate_and_mismatched_descriptor_fail_closed) ... ok
test_missing_receipt_or_source_is_not_no_coverage (tests.test_formal_context_repository.ContextIntegrationTests.test_missing_receipt_or_source_is_not_no_coverage) ... ok
test_non_context_producer_is_never_context_evidence (tests.test_formal_context_repository.ContextIntegrationTests.test_non_context_producer_is_never_context_evidence) ... ok
test_normalization_hash_binds_scientific_value_and_verified_source_manifest (tests.test_formal_context_repository.ContextIntegrationTests.test_normalization_hash_binds_scientific_value_and_verified_source_manifest) ... ok
test_normalizer_version_raw_and_direct_persistence_bypass_rejected (tests.test_formal_context_repository.ContextIntegrationTests.test_normalizer_version_raw_and_direct_persistence_bypass_rejected) ... ok
test_persistence_idempotence_list_detachment_and_verified_read (tests.test_formal_context_repository.ContextIntegrationTests.test_persistence_idempotence_list_detachment_and_verified_read) ... ok
test_private_fact_check_cannot_use_forged_or_mutated_request (tests.test_formal_context_repository.ContextIntegrationTests.test_private_fact_check_cannot_use_forged_or_mutated_request) ... ok
test_public_resolver_requires_signed_request_version_and_exact_context_kind (tests.test_formal_context_repository.ContextIntegrationTests.test_public_resolver_requires_signed_request_version_and_exact_context_kind) ... ok
test_put_revalidates_only_incoming_logical_generation_while_public_list_stays_fail_closed (tests.test_formal_context_repository.ContextIntegrationTests.test_put_revalidates_only_incoming_logical_generation_while_public_list_stays_fail_closed) ... ok
test_read_reloads_signature_gate_and_never_reruns_semantic_normalizer (tests.test_formal_context_repository.ContextIntegrationTests.test_read_reloads_signature_gate_and_never_reruns_semantic_normalizer) ... ok
test_recheck_detects_correction_during_snapshot_verification (tests.test_formal_context_repository.ContextIntegrationTests.test_recheck_detects_correction_during_snapshot_verification) ... ok
test_request_capability_rejects_alias_mutation_and_source_identity_substitution (tests.test_formal_context_repository.ContextIntegrationTests.test_request_capability_rejects_alias_mutation_and_source_identity_substitution) ... ok
test_same_generation_conflicts_preserve_existing_version (tests.test_formal_context_repository.ContextIntegrationTests.test_same_generation_conflicts_preserve_existing_version) ... ok
test_signed_descriptor_exact_identity_and_no_direct_trust_minting (tests.test_formal_context_repository.ContextIntegrationTests.test_signed_descriptor_exact_identity_and_no_direct_trust_minting) ... ok
test_signed_event_allowlist_preserves_negative_quantified_evidence (tests.test_formal_context_repository.ContextIntegrationTests.test_signed_event_allowlist_preserves_negative_quantified_evidence) ... ok
test_source_update_order_precedes_capture_and_missing_update (tests.test_formal_context_repository.ContextIntegrationTests.test_source_update_order_precedes_capture_and_missing_update) ... ok
test_sql_canonical_scientific_rewrite_without_input_hash_update_is_rejected (tests.test_formal_context_repository.ContextIntegrationTests.test_sql_canonical_scientific_rewrite_without_input_hash_update_is_rejected) ... ok
test_verified_context_repository_and_store_apis_exist (tests.test_formal_context_repository.ContextRepositoryApiTests.test_verified_context_repository_and_store_apis_exist) ... ok
test_combined_scoring_wrapper_preserves_legacy_descriptor_identity (tests.test_formal_context_repository.ScoringWrapperIntegrationTests.test_combined_scoring_wrapper_preserves_legacy_descriptor_identity) ... ok
test_combined_wrapper_rejects_unknown_keys_versions_and_invalid_descriptors (tests.test_formal_context_repository.ScoringWrapperIntegrationTests.test_combined_wrapper_rejects_unknown_keys_versions_and_invalid_descriptors) ... ok
test_v2_linked_consensus_descriptor_resolves_with_canonical_entry_id (tests.test_formal_context_repository.ScoringWrapperIntegrationTests.test_v2_linked_consensus_descriptor_resolves_with_canonical_entry_id) ... ok

----------------------------------------------------------------------
Ran 144 tests in 621.686s

OK
```

Post-run SHA-256 verification exited 0 and matched all six final frozen hashes exactly. The six source/test files remained unchanged throughout this complete amended run. Both earlier interrupted compatibility attempts are superseded diagnostic records; this complete clean run is the implementation's final test evidence.

Status: ready for root's final independent-review disposition and acceptance. No Git writes were performed by the implementer. Remaining functional gap is only the user-approved unchanged-v1 quantified-event consumption limitation described above; the DTO is format support, not a claim of signed runtime event consumption. Historical lineage is an internal transitive reference; new batches must recheck it.
