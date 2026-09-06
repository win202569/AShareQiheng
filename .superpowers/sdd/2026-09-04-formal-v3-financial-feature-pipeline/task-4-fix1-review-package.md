# Task 4 fix-1 independent review package

Review range: `44b974a..1eef9a6`.

This patch addresses the second independent review's reproduced P1: different effective release eligibility produced different bundle contents under the same input hash. Confirm the new canonical hash field is snapshot-safe, deterministic, semantically sufficient, and scoped to the two authorized Task4 files. Re-read `task-4-brief.md`; review read-only and report concrete findings or PASS.

```diff
diff --git a/ashare_pipeline/formal_financial_features.py b/ashare_pipeline/formal_financial_features.py
index ddeaa5e..d27b981 100644
--- a/ashare_pipeline/formal_financial_features.py
+++ b/ashare_pipeline/formal_financial_features.py
@@ -620,16 +620,17 @@ def build_formal_feature_bundle(*, security_id: str, as_of_utc: str, template_id
         security_id=security_id,
         as_of_utc=as_of_utc,
         template_id=template_id,
         contract_version=contract_version,
         registry_manifest_hash=root_hash,
         source_registry_hash=source_hash,
         mapping_registry_hash=mapping_hash,
         feature_registry_hash=feature_hash,
+        effective_release_eligible=eligible,
         visible_candidates=[candidates[key] for key in sorted(candidates)],
         selected_fact_ids=sorted({wire["id"] for _, wire in selected}),
         quarter_ids=sorted(q.to_dict()["id"] for q in quarters.facts),
         derivation_version=_DERIVATION,
         issues=[issue_wires[key] for key in sorted(issue_wires)],
     )
     return FormalFeatureBundle(
         schema_version=1,
diff --git a/tests/test_formal_financial_features.py b/tests/test_formal_financial_features.py
index bdd4a57..54cde34 100644
--- a/tests/test_formal_financial_features.py
+++ b/tests/test_formal_financial_features.py
@@ -305,16 +305,45 @@ class FormulaTests(unittest.TestCase):
             with self.assertRaises(ValueError):
                 evaluate_formula(leaf(), mapping)
         missing = evaluate_formula(FormulaNode(op="add", left=leaf(), right=leaf("absent")), {("revenue", "FY2025"): fact()})
         self.assertEqual(missing.missing_reason, "formula_fact_missing")
         self.assertEqual(missing.evidence, ())
 
 
 class BundleTests(unittest.TestCase):
+    def test_input_hash_binds_effective_registry_release_eligibility(self):
+        slots = sorted(
+            [slot_wire(template, unit="CNY", formula=leaf().to_dict()) for template in TEMPLATES],
+            key=lambda item: item["slot_id"],
+        )
+        raw = feature_registry_bytes(slots=slots)
+        root = registry_manifest(raw)
+        bound = load_registry(raw, root)
+        unbound = load_registry(raw)
+        inputs = [fact(), fact(metric_key="profit", value=20)]
+        derived = bundle(inputs, registry=bound, registry_manifest=root)
+        blocked = bundle(inputs, registry=unbound, registry_manifest=root)
+        self.assertEqual(derived.values[0].status, "derived")
+        self.assertEqual(blocked.values[0].status, "blocked")
+        self.assertEqual(derived.registry_manifest_hash, blocked.registry_manifest_hash)
+        self.assertEqual(derived.feature_registry_hash, blocked.feature_registry_hash)
+        self.assertNotEqual(derived.input_hash, blocked.input_hash)
+        for registry, expected in ((bound, derived), (unbound, blocked)):
+            self.assertEqual(
+                expected.input_hash,
+                bundle(inputs[::-1], registry=registry, registry_manifest=root).input_hash,
+            )
+        # With a passed test root both children have the same effective false gate.
+        test_root = registry_manifest(raw, purpose="test")
+        bound_test = bundle(inputs, registry=bound, registry_manifest=test_root)
+        unbound_test = bundle(inputs, registry=unbound, registry_manifest=test_root)
+        self.assertEqual(bound_test.values[0].status, "blocked")
+        self.assertEqual(bound_test.input_hash, unbound_test.input_hash)
+
     def test_issue_iterator_cannot_mutate_facts_or_registry_snapshots(self):
         slots = sorted([slot_wire(template, unit="CNY", formula=leaf().to_dict()) for template in TEMPLATES], key=lambda item: item["slot_id"])
         raw = feature_registry_bytes(slots=slots)
         root = registry_manifest(raw)
         registry = load_registry(raw, root)
         original = fact()
         expected = bundle([original], registry=registry, registry_manifest=root)
         def hostile():

```

