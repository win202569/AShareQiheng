"""Policy-adjusted valuation peer cohorts and percentile proofs."""

import atexit
import json
import unittest
from decimal import Decimal, ROUND_DOWN, localcontext
from types import MappingProxyType

from ashare_pipeline import formal_valuation_engine as valuation_engine
from ashare_pipeline.formal_valuation_engine import (
    FormalValuationRepository,
    PolicyAdjustedValuationPeerContext,
    PolicyAdjustedValuationScore,
    build_valuation_peer_context,
    score_valuation_percentile,
    valuation_peer_eligible,
)
from tests.formal_valuation_fixtures import ValuationRuntimeFixture


class SmallValuationRankingTests(unittest.TestCase):
    """Fast proof-binding coverage; the 20-member acceptance lives below."""

    @classmethod
    def setUpClass(cls):
        cls.fixture = ValuationRuntimeFixture(peer_count=3)
        for security_id in cls.fixture.templates:
            cls.fixture.put_industry(security_id)
        cls.batch = cls.fixture.build_adjusted_batch()

    @classmethod
    def tearDownClass(cls):
        cls.fixture.close()

    def test_pending_rows_are_ineligible_and_small_cohort_stays_unscored(self):
        row = self.batch.input_for("BJ430001", "V.normalized_earnings_yield")
        self.assertFalse(valuation_peer_eligible(row))
        context = build_valuation_peer_context(
            self.batch,
            security_id="BJ430001",
            metric_id="V.normalized_earnings_yield",
        )
        context.require_verified()
        self.assertEqual(context.template_id, "general_nonfinancial")
        self.assertIsNone(context.industry_id)
        self.assertEqual(context.reason, row.reason)
        self.assertEqual(context.peer_security_ids, ())
        self.assertIsNone(score_valuation_percentile(self.batch, context))

    def test_cross_batch_peer_context_is_rejected(self):
        context = build_valuation_peer_context(
            self.batch,
            security_id="BJ430001",
            metric_id="V.normalized_earnings_yield",
        )
        second = self.fixture.build_adjusted_batch()
        with self.assertRaisesRegex(ValueError, "another complete adjusted batch"):
            score_valuation_percentile(second, context)

    def test_diagnostics_bind_the_batch_and_count_one_group_index(self):
        for security_id in self.batch.security_ids:
            build_valuation_peer_context(
                self.batch,
                security_id=security_id,
                metric_id="V.normalized_earnings_yield",
            )
        report = self.fixture.repository.diagnostic_report(self.batch)
        self.assertEqual(report["batch_hash"], self.batch.batch_hash)
        self.assertEqual(report["security_count"], 3)
        self.assertEqual(report["valuation_row_count"], 9)
        self.assertEqual(report["group_index_builds"], 1)
        self.assertEqual(report["full_financial_rederivations"], 0)
        self.assertEqual(report["registry_full_parses"], 1)
        self.assertEqual(report["base_batch_full_validations"], 1)
        self.assertEqual(report["policy_batch_full_validations"], 1)
        self.assertEqual(set(report["phase_seconds"]), {
            "input_registry_validation", "identity_closure", "row_adjustment",
            "peer_grouping", "peer_sorting", "final_verification", "publication"})
        self.assertTrue(all(type(value) is float and value >= 0
                            for value in report["phase_seconds"].values()))
        self.assertIn("status_counts", report)
        self.assertIn("cohort_count", report)
        self.assertIn("sort_count", report)
        with self.assertRaises(TypeError):
            report["batch_hash"] = "forged"

    def test_foreign_repository_cannot_report_another_repository_batch(self):
        foreign = FormalValuationRepository(self.fixture.feature_repository,
            self.fixture.context, self.fixture.range_store,
            registry_signature_verifier=self.fixture.verifier)
        with self.assertRaisesRegex(ValueError, "another valuation repository"):
            foreign.diagnostic_report(self.batch)

class ValuationRankKernelTests(unittest.TestCase):
    def test_peer_and_score_proofs_cannot_be_constructed_or_forged(self):
        for cls in (PolicyAdjustedValuationPeerContext, PolicyAdjustedValuationScore):
            with self.assertRaises(TypeError):
                cls()
            forged = object.__new__(cls)
            with self.assertRaisesRegex(ValueError, "forged"):
                forged.require_verified()

    def test_fixture_cyclic_members_are_authored_in_the_signed_membership(self):
        fixture = ValuationRuntimeFixture(peer_count=4,
            cyclic_ids=("BJ430001", "SH600000"))
        self.addCleanup(fixture.close)
        memberships = json.loads(fixture.bundle.blob("industry").canonical_json)["memberships"]
        by_security = {item["security_id"]: item for item in memberships}
        self.assertEqual(by_security["BJ430001"]["secondary_industry"], "fixture-cyclic")
        self.assertEqual(by_security["SH600000"]["secondary_industry"], "fixture-cyclic")
        self.assertEqual(by_security["SZ000001"]["secondary_industry"], "fixture-noncyclic")

    def test_ties_negative_zero_and_extremes_use_average_rank(self):
        values = (Decimal("-1E+999"), Decimal("0"), Decimal("0"), Decimal("1E+999"))
        ranks = valuation_engine._rank_valuation_values(values, "higher")
        self.assertIs(type(ranks), MappingProxyType)
        self.assertEqual(ranks[Decimal("-1E+999")], (Decimal("1"), Decimal("12.5")))
        self.assertEqual(ranks[Decimal("0")], (Decimal("2.5"), Decimal("50")))
        self.assertEqual(ranks[Decimal("1E+999")], (Decimal("4"), Decimal("87.5")))

    def test_lower_reverses_only_the_percentile(self):
        ranks = valuation_engine._rank_valuation_values(
            (Decimal("-1"), Decimal("0"), Decimal("2")), "lower")
        self.assertEqual(ranks[Decimal("-1")][0], Decimal("1"))
        self.assertEqual(ranks[Decimal("-1")][1],
                         Decimal("83.333333333333333333333333333333333333333333333333"))
        self.assertEqual(ranks[Decimal("2")][0], Decimal("3"))
        self.assertEqual(ranks[Decimal("2")][1],
                         Decimal("16.666666666666666666666666666666666666666666666667"))

    def test_ambient_decimal_context_cannot_change_ranks(self):
        values = (Decimal("1"), Decimal("2"), Decimal("3"))
        with localcontext() as ambient:
            ambient.prec = 2
            ambient.rounding = ROUND_DOWN
            first = valuation_engine._rank_valuation_values(values, "higher")
        second = valuation_engine._rank_valuation_values(values, "higher")
        self.assertEqual(dict(first), dict(second))


class FullValuationRankingTests(unittest.TestCase):
    """One producer-backed 23-member batch covers every cohort branch."""

    @classmethod
    def setUpClass(cls):
        if hasattr(cls, "batch"):
            return
        cls.fixture = ValuationRuntimeFixture(peer_count=23,
            cyclic_ids=("BJ430001", "SH600000", "SH600001"))
        templates = cls.fixture.templates
        cls.fixture.populate_policy_evidence(
            skip_financial=tuple(sorted(set(templates) - {"BJ430001"})),
            financial_overrides={"BJ430001": dict(current_profit=10.0,
                annual_profit=(4.0, 5.0, 6.0, 7.0, 8.0))})
        cls.raw_earnings = {}
        omit_enterprise = {"BJ430001", "SH600000", "SH600001", "SH600002"}
        for index, security_id in enumerate(sorted(templates)):
            earnings = Decimal("0.20") if security_id == "BJ430001" else Decimal("0.1") + Decimal(index) / 1000
            values = {
                "V.normalized_free_cash_flow_yield": float(
                    Decimal("0.08") + Decimal(index) / 1000),
            }
            if security_id != "SH600002":
                values["V.normalized_earnings_yield"] = float(earnings)
                cls.raw_earnings[security_id] = earnings
            if security_id not in omit_enterprise:
                values["V.enterprise_value_or_sustainable_roe"] = float(
                    Decimal("0.1") + Decimal(index) / 1000)
            cls.fixture.put_financial(security_id, values)
            cls.fixture.valuation_feature_bundles[security_id] = cls.fixture.persist_features(security_id)
        cls.batch = cls.fixture.build_adjusted_batch()
        atexit.register(cls.fixture.close)

    @classmethod
    def tearDownClass(cls):
        # The integration module reuses this expensive genuine batch.  The
        # atexit cleanup above closes it for standalone and combined runs.
        pass

    def context(self, security_id, metric_id="V.normalized_earnings_yield"):
        return build_valuation_peer_context(self.batch,
            security_id=security_id, metric_id=metric_id)

    def test_secondary_twenty_and_secondary_nineteen_falls_back_to_primary(self):
        secondary = self.context("SZ000001", "V.normalized_free_cash_flow_yield")
        self.assertEqual(secondary.scope, "template_secondary_industry")
        self.assertEqual(secondary.peer_count, 20)
        fallback = self.context("BJ430001")
        self.assertEqual(fallback.scope, "template_primary_industry")
        self.assertEqual(fallback.peer_count, 20)
        self.assertIn("BJ430001", fallback.peer_security_ids)

    def test_primary_nineteen_stays_unscored(self):
        context = self.context("SZ000001", "V.enterprise_value_or_sustainable_roe")
        self.assertEqual(context.reason, "peer_count_below_20")
        self.assertEqual(context.peer_count, 19)
        self.assertIsNone(score_valuation_percentile(self.batch, context))

    def test_pending_affected_is_excluded_but_pending_unaffected_is_retained(self):
        affected = self.batch.input_for("SH600000", "V.normalized_earnings_yield")
        unaffected = self.batch.input_for("SH600000", "V.normalized_free_cash_flow_yield")
        self.assertEqual(affected.status, "pending_policy_evidence")
        self.assertFalse(valuation_peer_eligible(affected))
        self.assertEqual(unaffected.status, "passthrough_unaffected")
        self.assertTrue(valuation_peer_eligible(unaffected))
        self.assertNotIn("SH600000", self.context("BJ430001").peer_security_ids)
        self.assertIn("SH600000", self.context(
            "BJ430001", "V.normalized_free_cash_flow_yield").peer_security_ids)

    def test_one_adjustment_reranks_every_member_in_the_cohort(self):
        direction = self.batch.input_for(
            "BJ430001", "V.normalized_earnings_yield").original_metric["direction"]
        peers = self.context("BJ430001").peer_security_ids
        before = valuation_engine._rank_valuation_values(
            tuple(self.raw_earnings[security_id] for security_id in peers), direction)
        after = {}
        for security_id in peers:
            after[security_id] = score_valuation_percentile(
                self.batch, self.context(security_id)).percentile
        self.assertNotEqual(after["BJ430001"], before[self.raw_earnings["BJ430001"]][1])
        self.assertTrue(any(after[security_id] != before[self.raw_earnings[security_id]][1]
            for security_id in after if security_id != "BJ430001"))

    def test_each_cohort_is_sorted_once_and_peer_tuple_is_shared(self):
        first = self.context("SH600003")
        second = self.context("SH600004")
        self.assertIs(first.peer_security_ids, second.peer_security_ids)
        for security_id in first.peer_security_ids:
            score_valuation_percentile(self.batch, self.context(security_id))
        report = self.fixture.repository.diagnostic_report(self.batch)
        self.assertEqual(report["group_index_builds"], 1)
        self.assertEqual(report["sorts_by_cohort"][first.cohort_hash], 1)


if __name__ == "__main__":
    unittest.main()
