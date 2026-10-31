# Task 1 implementer brief

Read progress.md in this directory for binding preflight rulings. Read the authoritative spec sections 6.3 and 7.2 and the existing signed-registry/Context interfaces before implementation. The task text below is authoritative except the explicit integration rulings in progress.md. No production policy choices.

### Task 1: Hash-Pinned V3 Registry and Template Contract

**Files:**
- Create: ashare_pipeline/formal_scoring_registry.py
- Create: tests/fixtures/formal_v3_test_registry.json
- Create: tests/test_formal_scoring_registry.py

**Interfaces:**
- Produces FormalScoringRegistry, TemplateDefinition, MetricDefinition, RedlineDefinition, StatusRule, RegistryApproval, and load_formal_registry.
- Consumes canonical JSON bytes, the verified V6 formal feature-key vocabulary, and VerifiedRegistryBundle from the financial-feature plan.
- A test registry may be used only with purpose test; FormalScoringRegistry.require_official rejects it and rejects a registry whose approval hash is absent or different from its canonical content hash or whose declared scoring hash does not match the verified bundle.

- [ ] **Step 1: Write the failing registry tests**

~~~python
import unittest

from ashare_pipeline.formal_scoring_registry import (
    RegistryApproval,
    RegistryValidationError,
    load_formal_registry,
)


class FormalScoringRegistryTests(unittest.TestCase):
    def test_complete_test_registry_has_exact_v3_weights_and_five_templates(self):
        registry = load_formal_registry(
            "tests/fixtures/formal_v3_test_registry.json",
            RegistryApproval.for_test_fixture(),
        )
        self.assertEqual(
            tuple(registry.templates),
            ("general_nonfinancial", "bank", "broker", "insurance", "real_estate"),
        )
        self.assertEqual(registry.dimension_weights, {
            "G": 0.18, "V": 0.18, "M": 0.18, "EQ": 0.12,
            "FS": 0.08, "CA": 0.16, "T": 0.10,
        })
        self.assertEqual(registry.internal_weights["G"], (0.35, 0.25, 0.25, 0.15))

    def test_missing_field_map_or_policy_rule_cannot_be_loaded(self):
        payload = complete_registry_json_without("bank.metrics.V.normalized_earnings_yield.field_map")
        with self.assertRaisesRegex(RegistryValidationError, "field_map"):
            load_formal_registry_bytes(payload, RegistryApproval.for_test_fixture())

    def test_test_or_unapproved_registry_cannot_run_official_scoring(self):
        registry = load_fixture_registry()
        with self.assertRaisesRegex(RegistryValidationError, "official"):
            registry.require_official(fixture_registry_bundle())

    def test_root_manifest_rejects_mixed_feature_and_scoring_registries(self):
        registry = load_fixture_registry()
        with self.assertRaisesRegex(RegistryValidationError, "manifest"):
            registry.require_official(bundle_with_other_scoring_hash())
~~~

- [ ] **Step 2: Run the registry tests and verify RED**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m unittest tests.test_formal_scoring_registry -v
~~~

Expected: FAIL because the formal registry module and fixture do not exist.

- [ ] **Step 3: Implement canonical registry parsing and validation**

Implement immutable types with this public contract:

~~~python
@dataclass(frozen=True)
class RegistryApproval:
    purpose: Literal["test", "official"]
    approved_content_sha256: str | None
    approval_id: str | None

@dataclass(frozen=True)
class MetricDefinition:
    metric_id: str
    dimension: Literal["G", "V", "M", "EQ", "FS", "CA", "T"]
    internal_weight: Decimal
    direction: Literal["higher", "lower"]
    required_feature_keys: tuple[str, ...]
    formula_version: str
    field_map_version: str
    denominator_rule: str | None

@dataclass(frozen=True)
class FormalScoringRegistry:
    contract_version: str
    content_sha256: str
    templates: Mapping[str, TemplateDefinition]
    dimension_weights: Mapping[str, Decimal]
    internal_weights: Mapping[str, tuple[Decimal, ...]]
    cyclic_secondary_industries: frozenset[str]
    redlines: tuple[RedlineDefinition, ...]
    status_rules: tuple[StatusRule, ...]

    def require_official(self, registry_bundle: VerifiedRegistryBundle) -> None: ...
    def template_for(self, template_id: str) -> TemplateDefinition: ...
~~~

Canonicalize JSON using UTF-8, sorted keys, compact separators, and Decimal parsing before hashing. Validate all of the following before returning a registry:

- Contract version is V3 and the seven dimension weights sum exactly to Decimal("1.00").
- Each dimension contains the exact V3 internal weights from section 7.2 and every template has a conceptually equivalent definition for every slot.
- Every metric lists nonempty required feature keys, a formula version, field-map version, direction, unit/period rule, and invalid-denominator rule.
- Every template has an explicit template-specific map for financial-equivalent facts, not an implied deletion or reweighting.
- Cyclic classification, redline, status/event, and market-liquidity rules all have registry versions and source evidence categories.
- Test-only registry content declares purpose test and cannot satisfy require_official. An official registry requires purpose official, a nonempty approval_id, exact approved_content_sha256, and a VerifiedRegistryBundle whose loaded source/mapping/feature/scoring/industry/cyclic/redline/status/event blobs all re-hash to the root manifest declarations. The scoring registry itself is loaded only from registry_bundle.blob("scoring"), while the policy engine consumes the named cyclic/redline/status/event blobs from the same bundle.

The fixture registry is internally complete but uses synthetic V6 fixture feature keys and explicitly declares purpose test. It demonstrates engine behavior only; it is not a production investment-policy configuration.

- [ ] **Step 4: Run registry and feature-contract regression tests**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m unittest tests.test_formal_scoring_registry tests.test_formal_feature_contract -v
~~~

Expected: PASS; no V1 feature-contract behavior changes.

- [ ] **Step 5: Commit the formal registry contract**

~~~powershell
git add -- ashare_pipeline/formal_scoring_registry.py tests/fixtures/formal_v3_test_registry.json tests/test_formal_scoring_registry.py
git commit -m "feat: add hash-pinned formal scoring registry"
~~~



## Additional allowed integration files
- ashare_pipeline/formal_context_schema.py: only the explicit new scoring wrapper acceptance; preserve old exact wrapper and descriptor semantics.
- tests/test_formal_context_repository.py (or the closest existing Context test file): focused old/new wrapper and malformed-wrapper integration coverage. Parent will not edit your files concurrently.

## Work and report
- Workdir D:/Projects/AShareQiheng/.worktrees/formal-v3-implementation.
- Python D:/Projects/AShareQiheng/.venv/Scripts/python.exe.
- Use apply_patch, TDD RED before production edits, offline real signature/bundle fixtures. No nested agents, network, git stage/commit, data writes outside temporary test directories.
- Parent will review and commit the code/test allowlist. Record focused RED/GREEN commands, output, self-review and any concerns to task-1-report.md in this directory using apply_patch. Parent owns ledger.
- Include official success with genuinely verified same-root bundle + signed feature vocabulary, every five-template slot, mixed roots, fake/mutated objects, unapproved/test official rejection, field-map/denominator/unit/period completeness, exact weights, malformed JSON and policy role binding failures. Test-only helper objects are not proof of official eligibility.
- Keep implementation focused. Raise concrete architecture ambiguity before guessing. Use the shared combined fixture approach rather than combining independently installed placeholder roots.

