# Task 1 implementer report

Status: DONE_WITH_CONCERNS (implementation and focused checks complete; independent parent review and full Context regression pending at report time).

## Scope and evidence

Implemented the five-template, seven-dimension V3 registry in `ashare_pipeline/formal_scoring_registry.py`, a complete canonical `purpose=test` fixture, and focused registry tests. Context changes are limited to accepting the explicitly versioned four-key combined wrapper; legacy three-key wrapper and descriptor validation are preserved. No feature repository, formula evaluator, policy evaluator, runner, data collection, user-data storage, or Git index/commit changes were made. Existing unrelated `tmpj4zv9_fq/` is untouched.

Read Task 1 brief, binding progress ledger, authoritative spec sections 6.3/7.2, TDD SKILL.md and writing-good-tests.md, existing bundle/feature/Context trust interfaces, and actual V6 formula evaluator denominator behavior. Parent confirmed the derived-feature adapter and metadata-only policy binding interfaces before implementation.

All Python commands used `D:/Projects/AShareQiheng/.venv/Scripts/python.exe`, from `D:/Projects/AShareQiheng/.worktrees/formal-v3-implementation`.

### RED

- `-m unittest tests.test_formal_scoring_registry -v`: initial bootstrap 1 failure (module absent), followed by 15 behavioral tests failing before production module creation. The bootstrap-only existence test was removed from final coverage.
- `-m unittest tests.test_formal_context_repository.ScoringWrapperIntegrationTests.test_combined_scoring_wrapper_preserves_legacy_descriptor_identity -v`: one failure before Context edit; legacy wrapper loaded, combined wrapper rejected by old three-key validation. First attempt surfaced expected ValueError; test was adjusted to an explicit failing assertion and rerun to observe FAIL rather than ERROR.
- `-m unittest tests.test_formal_scoring_registry.FormalScoringRegistryTests.test_signed_divide_and_cagr_preserve_actual_v6_denominator_semantics -v`: three failing subcases for divide/CAGR/nested formulas before correcting the initially too-strict denominator declaration. Failures identified the wrong denominator semantics, not a fixture setup error.

### GREEN

- Initial `-m unittest tests.test_formal_scoring_registry -v`: 15 tests, 3.913 seconds, OK.
- Final `-m unittest tests.test_formal_scoring_registry tests.test_formal_feature_contract -v`: 36 tests, 4.411 seconds, OK, no test warnings/errors. Includes 17 scoring tests and all 19 existing feature contract tests.
- Focused Context `-m unittest tests.test_formal_context_repository.ScoringWrapperIntegrationTests -v`: 2 tests, 0.587 seconds, OK (old/new descriptor identity, malformed keys/version/scoring/descriptors).
- Parent separately confirmed manifest + feature baseline: 35 tests / 0.040 seconds / OK before this implementation.
- Parent is running complete Context and foundation regressions independently. Those results are not claimed here before completion.

The signed graph test helper authors one complete nine-child graph before signing anything. It uses real standard-library HMAC-SHA256 verification with a test-only key for root, child bytes and every root/role/child binding, then uses the actual FormalRegistryBundleLoader and actual sealed SignedFormalFeatureRegistry loader. Official-path success therefore exercises real byte-sensitive signature validation and graph closure, not an accepting verifier or a fabricated bundle. This test graph is not an approved investment policy.

## Public API

`load_formal_registry(source, approval, *, feature_registry=None) -> FormalScoringRegistry`

- Official source MUST be an exact `VerifiedRegistryBundle`; scoring bytes are obtained only via `bundle.blob("scoring")`. `feature_registry` MUST be an exact, sealed, release-eligible `SignedFormalFeatureRegistry` matching this graph's feature bytes/hash and source/mapping hashes.
- Standalone `bytes` and filesystem paths are accepted only for test content with `RegistryApproval.for_test_fixture()`. Official approval cannot promote the test fixture. Test content cannot be loaded from an official bundle.
- `RegistryValidationError(ValueError)` normalizes malformed input and trust-boundary failures.
- `RegistryApproval(purpose, approved_content_sha256, approval_id)` is frozen. Official content requires `purpose="official"`, a nonempty matching root approval ID, and the exact hash of the signed scoring child bytes.
- `FormalScoringRegistry` exposes contract_version, content_sha256, templates, dimension_weights, internal_weights, cyclic_secondary_industries, redlines, status_rules, cyclic_rule, market_liquidity_rule, policy_contracts, approval, registry_manifest_hash and all nine role_hashes.
- `template_for(template_id)` validates the registry seal and returns the template; unknown template IDs fail.
- `require_official(bundle)` rechecks the private registry seal, the verified bundle, all nine child re-hashes, exact root, scoring bytes, and the still-sealed matching feature vocabulary. Copying, forging or low-level mutation does not confer official eligibility.
- `TemplateDefinition(template_id, metrics)` maps dimension names to ordered immutable tuples of MetricDefinition, 25 metrics per template (125 total).
- `MetricDefinition` exposes the task's metric_id, dimension, internal_weight, direction, required_feature_keys, formula_version, field_map_version and denominator_rule; additionally formula, original_formula, field_map, unit_rule, period_rule, invalid_denominator_rule, equivalence_description, source_evidence_categories and policy_refs.
- `RedlineDefinition` and `StatusRule` expose rule_id, policy_role, registry_hash, registry_version, source_evidence_categories and a detached immutable rule body. Cyclic and market rules use the same StatusRule record shape.

Public records are frozen dataclasses. Nested mappings are read-only MappingProxyType objects; sequences are tuples; weights are exact Decimal values. Registry construction/sealing tables live in a deleted factory's private closure. The deep typed fingerprint seals nested records, mappings, approval and rules, and detects object.__setattr__ changes during official reuse. The caller's approval record is detached at load time.

## Wire contract for downstream tasks

Combined wrapper exact keys: `registry_role="scoring"`, `schema_version="formal-scoring-registry-v1"`, `descriptors=[...]`, `scoring={...}`. Legacy Context accepts exactly its old keys and `formal-context-registry-v1`; scoring loading does not accept the legacy wrapper. Context owns descriptor semantics and continues validating them unchanged.

`scoring` has exact keys: contract_version, purpose, dimension_weights, internal_weights, templates, policy_contracts, cyclic_rule, redlines, status_rules, market_liquidity_rule. Test-only content additionally requires fixture_feature_slots and fixture_policies; official content rejects these fields. `contract_version` is exactly `V3`. Top-level dimension weights must be exactly 18/18/18/12/8/16/10 percent, not merely any distribution summing to one. Every dimension's slot identities/order and internal weights are fixed to spec 7.2. All decimal weights are canonical decimal strings in JSON and parsed to Decimal; original signed bytes determine content_sha256.

Each template has exact keys `template_id`, `metrics`; each dimension's metrics are an ordered array. The stable metric IDs are listed by `_SLOTS` in the module. No financial-template slot can be silently deleted/reweighted.

The supported formula adapter is exactly `{"op":"feature","feature_key":"<V6 slot_id>"}`. `required_feature_keys` must contain exactly that one ID, and `field_map` is exactly `{"value":"<same V6 slot_id>"}`. The key must resolve to a required slot in that same template and dimension. No new scoring expression language is introduced. The public `original_formula` is copied from the actual signed V6 slot AST, including all fact keys, periods, numerators/denominators and intervals. `formula_version` and `unit_rule` must equal that signed slot. `period_rule` is the sorted unique array of all fact-node period keys in the V6 AST.

`invalid_denominator_rule` is exactly `block`. `denominator_rule` is inferred/checked against the referenced AST and actual V6 evaluator semantics:

- No divide or CAGR nodes: `not_applicable`.
- Divide nodes only: `nonzero` (negative ordinary divisors are supported by V6).
- CAGR nodes only: `positive_endpoints` (both endpoints must be positive).
- Both operations present: `nonzero_divisors_and_positive_cagr_endpoints`.

This is a declaration/validation contract; Task 1 does not evaluate formulas or score data.

Policy contracts have exactly the four named roles cyclic/redline/status/event. Each role records exact keys `registry_hash`, `registry_version`, `source_evidence_categories`. The named same-root policy child has exact keys `registry_role`, `schema_version="formal-scoring-policy-v1"`, `purpose`, `registry_version`, `source_evidence_categories`, `rules`. Metadata must agree with the scoring reference and purpose must match the official root/content. `rules` is a nonempty map from nonempty rule_id to a nonempty signed object. Task 1 preserves that object immutably without interpreting thresholds or introducing final-score/pool override APIs.

Every policy reference has exact keys `policy_role`, `rule_id`. Metric policy_refs are nonempty lists of such references. Redlines may reference only redline; status_rules include both status and event; cyclic_rule only cyclic; market_liquidity_rule only status. Every ID must exist, and duplicate top-level rule references are rejected. The cyclic classification rule has exactly `secondary_industries`, an explicit unique array (empty is allowed); registry.cyclic_secondary_industries comes from that signed same-root child. No parallel unsigned official industry list is accepted.

The fixture uses canonical compact sorted UTF-8 JSON with no terminal newline, synthetic V6 fact/slot IDs and purpose=test policy children. A final mechanical fixture formatting pass removed apply_patch's terminal newline so the file itself is canonical, without modifying values or changing signed-bundle JSON semantics.

## Self-review and remaining concerns

- Verified all 125 slots preserve independent literal spec weights; high-precision decimal perturbations fail rather than rounding into approved weights.
- Tested malformed/noncanonical/duplicate/nonfinite JSON; missing metric contracts and template slots; wrong feature/version/unit/period/direction/denominator; mixed roots; copied/forged/mutated registries; wrong approvals; changed child bindings; wrong policy hashes/versions/categories/purposes/rules; nested immutability.
- Explicit compatibility boundary: this adapter only ranks an already-derived V6 feature. It does not manufacture production market-cap, expected earnings, consensus, or Context-to-financial features. Real production V6 slots for all valuation/buy-point concepts may be unavailable; missing slots fail closed. The synthetic graph demonstrates trust and contract behavior only.
- Policy bodies remain opaque signed definitions until Task 4 adds a versioned interpreter. Nonempty signed equivalence descriptions document reviewer-approved intent; Task 1 cannot mathematically prove financial conceptual equivalence.
- No separate production policy configuration or approval was created. Parent still owns independent review, remaining regression results, staging and commit.

Files frozen for parent review after this report update. No additional implementation or test changes planned.
