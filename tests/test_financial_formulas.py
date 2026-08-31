import importlib
import unittest


class FinancialFormulaAuthorityTests(unittest.TestCase):
    def authority(self):
        try:
            return importlib.import_module("ashare_pipeline.financial_formulas")
        except ModuleNotFoundError:
            self.fail("neutral financial formula authority is missing")

    def result(self, results, dimension, metric_key, period_key):
        return next(
            item
            for item in results
            if (item.spec.dimension, item.spec.metric_key, item.spec.period_key)
            == (dimension, metric_key, period_key)
        )

    def test_catalog_is_the_literal_closed_ninety_slot_projection(self):
        authority = self.authority()
        specs = authority.DERIVED_FORMULA_SPECS

        self.assertEqual(authority.DERIVED_FORMULA_VERSION, "financial-derived-v1")
        self.assertEqual(len(specs), 90)
        self.assertEqual(len({spec.logical_id for spec in specs}), 90)
        self.assertEqual(
            sum(spec.metric_key == "revenue_symmetric_growth" for spec in specs),
            5,
        )
        self.assertEqual(sum(spec.metric_key == "revenue_cagr" for spec in specs), 1)
        self.assertEqual(
            {
                spec.logical_id
                for spec in specs
                if spec.result_state == "not_applicable"
            },
            {"EQ.total_accruals.FY2021", "M.roic.FY2021"},
        )

    def test_evaluator_returns_hand_checked_results_and_exact_operand_ids(self):
        authority = self.authority()
        fact = authority.FormulaFact
        inputs = {
            ("revenue", "2021-12-31"): fact(
                "revenue", "2021-12-31", 100.0, "CNY", "revenue-2021"
            ),
            ("operating_cost", "2021-12-31"): fact(
                "operating_cost", "2021-12-31", 60.0, "CNY", "cost-2021"
            ),
            ("total_profit", "2021-12-31"): fact(
                "total_profit", "2021-12-31", 20.0, "CNY", "profit-2021"
            ),
            ("interest_expense", "2021-12-31"): fact(
                "interest_expense", "2021-12-31", 2.0, "CNY", "interest-2021"
            ),
            ("income_tax", "2021-12-31"): fact(
                "income_tax", "2021-12-31", 40.0, "CNY", "tax-2021"
            ),
        }

        results = authority.evaluate_derived_financial(inputs)
        gross = self.result(results, "M", "gross_profit", "FY2021")
        tax = self.result(results, "M", "effective_tax_rate", "FY2021")
        nopat = self.result(results, "M", "nopat", "FY2021")

        self.assertEqual((gross.status, gross.value), ("derived", 40.0))
        self.assertEqual(gross.operand_ids, ("cost-2021", "revenue-2021"))
        self.assertEqual((tax.status, tax.value), ("derived", 0.5))
        self.assertEqual(tax.operand_ids, ("profit-2021", "tax-2021"))
        self.assertEqual((nopat.status, nopat.value), ("derived", 11.0))
        self.assertEqual(
            nopat.operand_ids,
            ("interest-2021", "profit-2021", "tax-2021"),
        )

    def test_evaluator_preserves_growth_cagr_and_frozen_window_boundaries(self):
        authority = self.authority()
        fact = authority.FormulaFact
        inputs = {
            ("revenue", "2021-12-31"): fact(
                "revenue", "2021-12-31", -100.0, "CNY", "r21"
            ),
            ("revenue", "2022-12-31"): fact(
                "revenue", "2022-12-31", -50.0, "CNY", "r22"
            ),
            ("revenue", "2025-12-31"): fact(
                "revenue", "2025-12-31", 200.0, "CNY", "r25"
            ),
        }

        results = authority.evaluate_derived_financial(inputs)
        growth = self.result(results, "G", "revenue_symmetric_growth", "FY2022")
        cagr = self.result(results, "G", "revenue_cagr", "FY2025")
        accruals = self.result(results, "EQ", "total_accruals", "FY2021")
        roic = self.result(results, "M", "roic", "FY2021")

        self.assertAlmostEqual(growth.value, 200.0 / 3.0)
        self.assertEqual(growth.operand_ids, ("r21", "r22"))
        self.assertEqual(
            (cagr.status, cagr.value, cagr.missing_reason),
            ("missing", None, "invalid_endpoint:revenue_cagr"),
        )
        for frozen in (accruals, roic):
            self.assertEqual(
                (frozen.status, frozen.value, frozen.operand_ids, frozen.missing_reason),
                (
                    "not_applicable",
                    None,
                    (),
                    "frozen_window_no_opening_period",
                ),
            )

    def test_accrual_and_roic_use_the_exact_hand_checked_raw_operand_sets(self):
        authority = self.authority()
        fact = authority.FormulaFact
        inputs = {}

        def put(metric, period, value, identity):
            inputs[(metric, period)] = fact(metric, period, value, "CNY", identity)

        put("net_profit", "2022-12-31", 30.0, "a-net")
        put("operating_cash_flow", "2022-12-31", 20.0, "a-ocf")
        put("total_assets", "2022-12-31", 120.0, "a-current")
        put("total_assets", "2021-12-31", 80.0, "a-opening")
        put("total_profit", "2022-12-31", 20.0, "n-profit")
        put("interest_expense", "2022-12-31", 2.0, "n-interest")
        put("income_tax", "2022-12-31", 4.0, "n-tax")
        for period, prefix, equity in (
            ("2022-12-31", "c", 100.0),
            ("2021-12-31", "o", 80.0),
        ):
            put("total_equity", period, equity, f"{prefix}-equity")
            put("short_term_debt", period, 1.0, f"{prefix}-short")
            put("current_portion_long_term_debt", period, 1.0, f"{prefix}-current")
            put("long_term_debt", period, 1.0, f"{prefix}-long")
            put("bonds_payable", period, 1.0, f"{prefix}-bonds")
            put("lease_liabilities", period, 1.0, f"{prefix}-lease")
            put("cash", period, 5.0, f"{prefix}-cash")

        results = authority.evaluate_derived_financial(inputs)
        accruals = self.result(results, "EQ", "total_accruals", "FY2022")
        roic = self.result(results, "M", "roic", "FY2022")

        self.assertEqual((accruals.status, accruals.value), ("derived", 0.1))
        self.assertEqual(
            accruals.operand_ids,
            ("a-current", "a-net", "a-ocf", "a-opening"),
        )
        self.assertAlmostEqual(roic.value, 17.6 / 90.0)
        self.assertEqual(
            roic.operand_ids,
            (
                "c-bonds",
                "c-cash",
                "c-current",
                "c-equity",
                "c-lease",
                "c-long",
                "c-short",
                "n-interest",
                "n-profit",
                "n-tax",
                "o-bonds",
                "o-cash",
                "o-current",
                "o-equity",
                "o-lease",
                "o-long",
                "o-short",
            ),
        )


if __name__ == "__main__":
    unittest.main()
