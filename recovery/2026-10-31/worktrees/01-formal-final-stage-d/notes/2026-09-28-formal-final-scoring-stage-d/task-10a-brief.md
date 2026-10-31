### Task 10A: Signed test-root computation gate

Task 11 requires `test_preview` to consume a genuine HMAC-signed v2 ten-role
`purpose=test` root.  Current Stage A/B/C/D1 code unconditionally requires an
official root, so this prerequisite must be completed first.

Implement with strict TDD.  Add focused tests first and report the exact RED
failure before changing production code.  Do not run genuine `FinalScoringFixture`
suites in the subagent sandbox; the main agent will run those through the authorized
path after you supply the tests.

Required behavior:

1. Add an exact-purpose authenticated computation gate.  A loader-sealed signed
   v2 ten-role root with purpose `test`, null approval identity, valid child hashes,
   signatures and root bindings may be consumed by test-preview computation.
2. Preserve all existing official gates.  `require_official` must still require an
   official root plus exact approval ID/content hash and must reject every test root.
3. Every signed child that declares a purpose must match the root purpose.  Reject
   mixed-purpose graphs, approvals on test roots, cross-root, copied, forged,
   mutated, missing-role, or test-to-official promotion attempts.
4. The standalone unsigned `RegistryApproval.for_test_fixture()` path remains only
   for pure scoring-registry unit fixtures and must not authenticate a Stage D root.
5. Thread the new computation gate only through root/feature/context and Stage
   A/B/C/D1 producers needed to build genuine preview inputs.  Do not change
   formulas, scoring rules, eligibility, pool selection, capacities, schema,
   persistence, official coverage, official candidate, or V9 release behavior.
6. Prefer explicit purpose APIs such as `require_authenticated(...,
   expected_purpose="test"|"official")`; do not add `allow_test=True` or another
   ambiguous downgrade switch.

Expected production scope (narrow it if tests prove fewer files are needed):

- `ashare_pipeline/formal_registry_manifest.py`
- `ashare_pipeline/formal_feature_contract.py`
- `ashare_pipeline/formal_scoring_registry.py`
- `ashare_pipeline/formal_financial_features.py`
- `ashare_pipeline/formal_feature_repository.py`
- `ashare_pipeline/formal_context_schema.py`
- `ashare_pipeline/formal_metric_context.py`
- `ashare_pipeline/formal_metric_engine.py`
- `ashare_pipeline/formal_score_inputs.py`
- `ashare_pipeline/formal_policy_registry.py`
- `ashare_pipeline/formal_policy_repository.py`
- `ashare_pipeline/formal_range_contract.py`
- `ashare_pipeline/formal_valuation_adapter_contract.py`
- `ashare_pipeline/formal_valuation_engine.py`
- `ashare_pipeline/formal_final_score_inputs.py`

Fixture/test scope may include the existing signed graph and Stage D fixture
helpers plus a new focused `tests/test_formal_test_root_contract.py`.

Mandatory tests:

- genuine signed test bundle passes authenticated(test) and fails official;
- official bundle passes authenticated(official) and official;
- expected-purpose mismatch and mixed child purpose fail closed;
- test root with any approval identity fails closed;
- standalone fixture registry cannot enter the authenticated bundle path;
- copied/forged/mutated/cross-root proof objects fail closed;
- genuine test-root Stage A/B/C/D1 chain succeeds under preview computation;
- the same test root cannot pass official coverage/candidate/release gates.

After focused GREEN, report changed files, exact commands/results, remaining genuine
suite commands for the main agent, and any scope expansion before committing.  Do
not commit until the main agent has observed RED and authorized the GREEN phase.
