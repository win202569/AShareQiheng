# F3 independent task review

Reviewer: /root/stage_b_f3_reviewer. BASE c7fb672bfe47d2831bb4c1e850d6397407b9464b;
HEAD d2cc791829b76aecf0b5a6d69e3290b603e96704. Six-file task gate, not merge review.
The following retains the reviewer's substantive verdict; formatting normalized.

### Spec Compliance

- ✅ Compliant with the approved F3 scope. All six authorized files have corresponding changes. Explicit false remains a value, absent entries become bound runtime/state_entry_missing, and existing signed state selectors determine consumption (ashare_pipeline/formal_policy_state.py:24, :118).
- ✅ The registry change introduces an original-owner authenticated reader without changing signed rule syntax (ashare_pipeline/formal_policy_registry.py:503). Event support remains a closed, non-authoritative DTO; state consumption excludes event_calendar (ashare_pipeline/formal_policy_values.py:150, ashare_pipeline/formal_policy_state.py:21).
- ⚠️ Full compatibility acceptance remains pending: the report records 26 state and 21 value/fixture tests emitting ok, but no final compatibility exit/count or post-run hashes. Root should complete that evidence gate.
- ⚠️ Unchanged global financial formulas, policy weights, pool limits and production-data preservation cannot be independently established from this task-scoped diff.

### Strengths

- Complete factors and signed request/descriptor identity are retained before projection; a second grouped read detects changes during selection (ashare_pipeline/formal_policy_state.py:145).
- Selection registration, detached immutable audit views and explicit copy rejection preserve the internal evidence boundary (ashare_pipeline/formal_policy_state.py:84).
- Original PolicyValue parser, serializer, validation dependencies and class interfaces are retained and checked, including pre-import public substitution risks (ashare_pipeline/formal_policy_values.py:273).
- Fixture evidence follows resolver → task → verified snapshot → normalization receipt, with SQL confined to a deliberate receipt-loss negative (tests/formal_policy_runtime_fixtures.py:174, tests/test_formal_policy_state.py:344).
- Regression tests cover pre-import substitutions, missing-to-present changes, equal-leading conflicts, raw/receipt loss, genuine import order and the explicit v1 event limitation (tests/test_formal_policy_state.py:22, :327).

### Issues

- Critical: None found.
- Important: None found.
- Minor: None identified.

### Focused Outside-Diff Checks

- Companion-authentication risk: inspected formal_metric_context.py:76, :107, :137, :259; its retained guard checks Context/store/raw/verifier and Fact serialization, and construction does not load universe or industry evidence.
- Volatile-lineage risk: inspected formal_context_schema.py:320; Fact export contains canonical content plus its content-derived ID.
- No tests rerun; no writes or Git operations performed.

### Assessment

Task quality: Approved. The implementation fits the clarified v1 boundary and preserves authenticated absence, explicit values and revocation behavior. Approval is for the reviewed code; final compatibility acceptance remains a separate pending gate.

