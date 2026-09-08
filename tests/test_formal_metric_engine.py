"""Arithmetic and whole-population proofs use independent literal expectations."""

import copy
import hashlib
from decimal import Decimal, DefaultContext, getcontext, setcontext
import importlib
import sys
import unittest
from unittest.mock import patch
from ashare_pipeline.formal_financial_schema import FormalFactIssue
from ashare_pipeline.formal_universe import FormalUniverseDecision
from tests.formal_metric_feature_fixtures import FinancialFixture, METRICS


class PercentileArithmeticTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec("ashare_pipeline.formal_metric_engine"),
            "metric engine is missing")
        self.api = importlib.import_module("ashare_pipeline.formal_metric_engine")

    def test_ties_use_midpoint_average_rank_and_lower_reverses_only_percentile(self):
        rank, percentile = self.api.percentile_rank(Decimal("2"), tuple(map(Decimal, ("1", "2", "2", "4"))), direction="higher")
        self.assertEqual((rank, percentile), (Decimal("2.5"), Decimal("50")))
        self.assertEqual(self.api.percentile_rank(Decimal("1"), (Decimal("1"), Decimal("3")), direction="lower"),
            (Decimal("1"), Decimal("75")))

    def test_negative_zero_and_all_equal_values_are_valid(self):
        self.assertEqual(self.api.percentile_rank(Decimal("0"), tuple(map(Decimal, ("-1", "0", "1"))), direction="higher"),
            (Decimal("2"), Decimal("50")))
        self.assertEqual(self.api.percentile_rank(Decimal("-2"), (Decimal("-2"),) * 4, direction="lower"),
            (Decimal("2.5"), Decimal("50")))

    def test_arithmetic_rejects_empty_nonfinite_and_focal_substitution(self):
        for focal, values, direction in ((Decimal("1"), (), "higher"), (Decimal("NaN"), (Decimal("1"),), "higher"),
                (Decimal("1"), (Decimal("Infinity"),), "higher"), (Decimal("2"), (Decimal("1"),), "higher"),
                (Decimal("1"), (1,), "higher"), (Decimal("1"), (Decimal("1"),), "wrong")):
            with self.subTest(focal=focal, values=values), self.assertRaises(ValueError):
                self.api.percentile_rank(focal, values, direction=direction)

    def test_decimal_precision_rounding_exponents_and_traps_are_locally_fixed(self):
        saved, default = getcontext().copy(), DefaultContext.copy()
        try:
            getcontext().prec = 2
            getcontext().Emax = 1
            getcontext().Emin = -1
            DefaultContext.prec = 3
            for signal in getcontext().traps:
                getcontext().traps[signal] = True
                DefaultContext.traps[signal] = True
            self.assertEqual(self.api.percentile_rank(Decimal("1"), tuple(map(Decimal, ("1", "2", "3"))), direction="higher"),
                (Decimal("1"), Decimal("16.666666666666666666666666666666666666666666666667")))
            self.assertEqual(getcontext().prec, 2)
        finally:
            setcontext(saved)
            for field in ("prec", "rounding", "Emin", "Emax", "capitals", "clamp"):
                setattr(DefaultContext, field, getattr(default, field))
            DefaultContext.traps = default.traps.copy()


class CompleteMetricBatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api = importlib.import_module("ashare_pipeline.formal_metric_engine")
        if not hasattr(cls.api, "FormalMetricInputRepository"):
            return
        cls.fixture = FinancialFixture(population=True)
        cls.addClassCleanup(cls.fixture.close)
        cls.fixture.populate()
        cls.repo = cls.api.FormalMetricInputRepository(cls.fixture.feature_repository, cls.fixture.context,
            registry_signature_verifier=cls.fixture.verifier)
        cls.batch = cls.repo.build_batch(cls.fixture.frozen.frozen_input_hash,
            scoring_registry=cls.fixture.scoring, metric_ids=METRICS)

    def setUp(self):
        self.assertTrue(hasattr(self.api, "FormalMetricInputRepository"), "complete metric factory is missing")

    def test_complete_batch_enumerates_every_frozen_member_and_preserves_metric_local_pending(self):
        self.assertEqual(len(self.batch.security_ids), 22)
        self.assertEqual(len(self.batch.inputs), 88)
        self.assertEqual(self.batch.metric_ids, METRICS)
        good = self.batch.input_for("SH600018", METRICS[0])
        missing = self.batch.input_for("SH600018", METRICS[1])
        self.assertTrue(self.api.metric_peer_eligible(good))
        self.assertEqual(good.raw_value, Decimal("18.0"))
        self.assertFalse(self.api.metric_peer_eligible(missing))
        self.assertEqual(missing.invalid_reason, "formula_fact_missing")
        self.assertTrue(good.verified_feature_refs)
        self.assertTrue(self.api.metric_peer_eligible(self.batch.input_for("BJ430001", METRICS[0])))

    def test_twenty_secondary_qualifies_nineteen_falls_back_and_nineteen_primary_fails(self):
        contexts = [self.api.build_metric_peer_context(self.batch, metric_id=m, security_id="BJ430001") for m in METRICS[:3]]
        self.assertEqual((contexts[0].scope, contexts[0].peer_count), ("template_secondary_industry", 20))
        self.assertEqual((contexts[1].scope, contexts[1].peer_count), ("template_primary_industry", 20))
        self.assertEqual((contexts[2].reason, contexts[2].peer_count), ("peer_count_below_20", 19))
        self.assertNotIn("SZ000001", contexts[0].peer_security_ids)
        invalid = self.api.build_metric_peer_context(self.batch, metric_id=METRICS[1], security_id="SH600018")
        self.assertEqual(invalid.reason, "formula_fact_missing")
        self.assertIsNone(self.api.score_metric_percentile(self.batch, invalid))

    def test_formal_score_binds_focal_value_exact_cohort_direction_and_all_proof_hashes(self):
        context = self.api.build_metric_peer_context(self.batch, metric_id=METRICS[0], security_id="BJ430001")
        score = self.api.score_metric_percentile(self.batch, context)
        self.assertEqual((score.raw_value, score.average_rank, score.percentile), (Decimal("-1.0"), Decimal("1"), Decimal("2.5")))
        self.assertEqual(score.peer_context, context)
        self.assertEqual(score.batch_hash, self.batch.batch_hash)
        self.assertEqual(score.definition_hash, self.batch.input_for("BJ430001", METRICS[0]).definition_hash)
        lower = self.api.build_metric_peer_context(self.batch, metric_id=METRICS[3], security_id="BJ430001")
        self.assertEqual(self.api.score_metric_percentile(self.batch, lower).percentile, Decimal("97.5"))
        score.require_verified()
        self.assertEqual(self.api.score_metric_percentile(self.batch, context).canonical_bytes(), score.canonical_bytes())

    def test_proofs_reject_construction_copy_mutation_subsets_and_replaced_identities(self):
        context = self.api.build_metric_peer_context(self.batch, metric_id=METRICS[0], security_id="BJ430001")
        score = self.api.score_metric_percentile(self.batch, context)
        for proof in (self.batch, self.batch.inputs[0], context, score):
            with self.assertRaises(TypeError):
                type(proof)()
            with self.assertRaises(ValueError):
                object.__new__(type(proof)).require_verified()
            for copier in (copy.copy, copy.deepcopy):
                with self.assertRaises((TypeError, ValueError)):
                    copier(proof)
            with self.assertRaises((TypeError, AttributeError, ValueError)):
                object.__setattr__(proof, "security_id", "SH600019")
        with self.assertRaises((TypeError, ValueError)):
            self.api.build_metric_peer_context(self.batch.inputs[:20], metric_id=METRICS[0], security_id="BJ430001")
        for sid, mid in (("BJ899001", METRICS[0]), ("BJ430001", "operating_profit_per_share_cagr_3y")):
            with self.assertRaises(ValueError):
                self.api.build_metric_peer_context(self.batch, metric_id=mid, security_id=sid)
        with self.assertRaises(TypeError):
            self.api.score_metric_percentile(self.batch, context, direction="lower")

    def test_factory_rejects_subset_selectors_unqualified_ids_and_copied_repository(self):
        for selected in ((), [METRICS[0]], (METRICS[0], METRICS[0]), ("return_persistence",), ("G.unknown",)):
            with self.assertRaises(ValueError):
                self.repo.build_batch(self.fixture.frozen.frozen_input_hash, scoring_registry=self.fixture.scoring, metric_ids=selected)
        with self.assertRaises(TypeError):
            self.repo.build_batch(self.fixture.frozen.frozen_input_hash, scoring_registry=self.fixture.scoring, security_ids=("BJ430001",))
        with self.assertRaises((TypeError, ValueError)):
            copy.copy(self.repo)

class MetricClosureTests(unittest.TestCase):
    def setUp(self):
        self.api = importlib.import_module("ashare_pipeline.formal_metric_engine")
        self.fixture = FinancialFixture()
        self.addCleanup(self.fixture.close)
        for sid in ("BJ430001", "SH600000", "SZ000001"):
            self.fixture.put_industry(sid)
        self.repo = self.api.FormalMetricInputRepository(self.fixture.feature_repository, self.fixture.context,
            registry_signature_verifier=self.fixture.verifier)

    def build(self, **kwargs):
        return self.repo.build_batch(self.fixture.frozen.frozen_input_hash,
            scoring_registry=self.fixture.scoring, **kwargs)

    def test_identical_cohorts_share_the_immutable_membership_tuple(self):
        for sid in ("SH600000", "SZ000001"):
            self.fixture.put_financial(sid, {METRICS[0]: 1})
            self.fixture.persist_features(sid)
        batch = self.build(metric_ids=(METRICS[0],))
        first = self.api.build_metric_peer_context(batch, metric_id=METRICS[0], security_id="SH600000")
        second = self.api.build_metric_peer_context(batch, metric_id=METRICS[0], security_id="SZ000001")
        self.assertEqual(first.peer_security_ids, ("SH600000", "SZ000001"))
        self.assertIs(first.peer_security_ids, second.peer_security_ids)

    def test_missing_receipts_are_authenticated_pending_for_the_complete_population(self):
        batch = self.build(metric_ids=(METRICS[0],))
        self.assertEqual(batch.security_ids, ("BJ430001", "SH600000", "SZ000001"))
        self.assertEqual(tuple(row.invalid_reason for row in batch.inputs), ("current_receipt_absent",) * 3)
        self.assertEqual(set(batch.feature_states), set(batch.security_ids))
        self.assertEqual(batch.canonical_bytes(), self.build(metric_ids=(METRICS[0],)).canonical_bytes())
        batch.to_dict()["inputs"][0]["raw_value"] = "999"
        self.assertIsNone(batch.inputs[0].raw_value)

    def test_vetoed_unscored_company_still_supplies_a_complete_metric(self):
        ref = self.fixture.put_financial("BJ430001", {METRICS[0]: 0})
        bundle = self.fixture.persist_features("BJ430001")
        self.assertTrue(bundle.blockers)  # Other dimensions and history are incomplete.
        statuses = self.fixture.store.list_formal_universe_statuses(self.fixture.snapshot_id)
        decisions = tuple(FormalUniverseDecision(row["security_id"],
            "pool_vetoed" if row["security_id"] == "BJ430001" else row["status"],
            () if row["security_id"] == "BJ430001" else tuple(row["reasons"]),
            ("fixture_veto",) if row["security_id"] == "BJ430001" else tuple(row["veto_flags"]),
            ref.content_sha256 if row["security_id"] == "BJ430001" else row["evidence_hash"])
            for row in statuses)
        self.fixture.store.replace_formal_universe_statuses(self.fixture.snapshot_id, decisions)
        batch = self.build(metric_ids=(METRICS[0],))
        self.assertTrue(self.api.metric_peer_eligible(batch.input_for("BJ430001", METRICS[0])))
        self.assertEqual(batch.input_for("BJ430001", METRICS[0]).raw_value, Decimal("0.0"))

    def test_industry_correction_during_feature_reads_is_rechecked_for_the_whole_population(self):
        fired = False
        def profile(frame, event, arg):
            nonlocal fired
            if (not fired and event == "return" and frame.f_code.co_name == "resolve_current_inputs"
                    and getattr(arg, "security_id", None) == "SZ000001"):
                fired = True
                self.fixture.put_industry("BJ430001", changes={"secondary_industry": "corrected"},
                    generation="corrected", published="2026-08-29T07:00:00+00:00")
        previous = sys.getprofile()
        try:
            sys.setprofile(profile)
            with self.assertRaisesRegex(ValueError, "industry Context correction or absence changed"):
                self.build(metric_ids=(METRICS[0],))
        finally:
            sys.setprofile(previous)
        self.assertTrue(fired)

    def test_default_selection_preserves_both_return_persistence_definitions(self):
        batch = self.build()
        self.assertEqual(len(batch.metric_ids), 25)
        self.assertIn("M.return_persistence", batch.metric_ids)
        self.assertIn("CA.return_persistence", batch.metric_ids)
        first = batch.input_for("BJ430001", "M.return_persistence")
        second = batch.input_for("BJ430001", "CA.return_persistence")
        self.assertNotEqual(first.definition_hash, second.definition_hash)

    def test_cross_member_still_absent_fact_issue_and_provider_corrections_fail_closure(self):
        for mutation in ("facts", "issues", "provider", "receipt"):
            fired = False
            def profile(frame, event, arg):
                nonlocal fired
                if (not fired and event == "return" and frame.f_code.co_name == "resolve_current_inputs"
                        and getattr(arg, "security_id", None) == "SH600000"):
                    fired = True
                    if mutation == "facts":
                        self.fixture.put_financial("BJ430001", {METRICS[0]: 1}, generation="correction")
                    elif mutation == "issues":
                        self.fixture.set_issues("BJ430001", (FormalFactIssue("unknown_source_field", None, "OTHER", {}),))
                    elif mutation == "provider":
                        self.fixture.set_generation("BJ430001", "changed-provider")
                    else:
                        self.fixture.persist_features("BJ430001")
            previous = sys.getprofile()
            try:
                sys.setprofile(profile)
                with self.subTest(mutation=mutation), self.assertRaisesRegex(ValueError, "changed during complete batch"):
                    self.build(metric_ids=(METRICS[0],))
            finally:
                sys.setprofile(previous)
            self.assertTrue(fired)

    def test_present_receipt_becoming_absent_during_later_member_read_fails(self):
        self.fixture.put_financial("BJ430001", {METRICS[0]: 1})
        self.fixture.persist_features("BJ430001")
        fired = False
        def profile(frame, event, arg):
            nonlocal fired
            if (not fired and event == "return" and frame.f_code.co_name == "resolve_current_inputs"
                    and getattr(arg, "security_id", None) == "SH600000"):
                fired = True
                self.fixture.put_financial("BJ430001", {METRICS[0]: 2}, generation="correction",
                    updated="2026-04-01T00:00:00+00:00")
        previous = sys.getprofile()
        try:
            sys.setprofile(profile)
            with self.assertRaisesRegex(ValueError, "changed during complete batch"):
                self.build(metric_ids=(METRICS[0],))
        finally:
            sys.setprofile(previous)
        self.assertTrue(fired)

    def test_replaced_reader_copied_repository_wrong_root_or_definition_cannot_mint(self):
        feature = self.fixture.feature_repository
        real_reader = feature.select_current_verified_metric_feature_state
        with patch.object(feature, "select_current_verified_metric_feature_state", real_reader), self.assertRaises(ValueError):
            self.build(metric_ids=(METRICS[0],))
        fake = object.__new__(type(feature))
        fake.__dict__.update(feature.__dict__)
        with self.assertRaises(ValueError):
            self.api.FormalMetricInputRepository(fake, self.fixture.context,
                registry_signature_verifier=self.fixture.verifier)
        metric = self.fixture.scoring.template_for("general_nonfinancial").metrics["G"][0]
        for field, changed in (("direction", "lower"), ("unit_rule", "shares"), ("metric_id", "different")):
            original = getattr(metric, field)
            try:
                object.__setattr__(metric, field, changed)
                with self.subTest(field=field), self.assertRaises(ValueError):
                    self.build(metric_ids=(METRICS[0],))
            finally:
                object.__setattr__(metric, field, original)
        self.assertIsNone(self.repo.build_batch("f" * 64, scoring_registry=self.fixture.scoring, metric_ids=(METRICS[0],)))


class AllPendingRepositoryTests(unittest.TestCase):
    def test_all_missing_memberships_do_not_allow_a_copied_feature_repository(self):
        api = importlib.import_module("ashare_pipeline.formal_metric_engine")
        fixture = FinancialFixture(missing_memberships=True)
        self.addCleanup(fixture.close)
        genuine = api.FormalMetricInputRepository(fixture.feature_repository, fixture.context,
            registry_signature_verifier=fixture.verifier)
        batch = genuine.build_batch(fixture.frozen.frozen_input_hash, scoring_registry=fixture.scoring, metric_ids=(METRICS[0],))
        self.assertEqual(tuple(item.invalid_reason for item in batch.inputs), ("invalid_template",) * 3)
        fake = object.__new__(type(fixture.feature_repository))
        fake.__dict__.update(fixture.feature_repository.__dict__)
        with self.assertRaises(ValueError):
            api.FormalMetricInputRepository(fake, fixture.context, registry_signature_verifier=fixture.verifier)


if __name__ == "__main__":
    unittest.main()
