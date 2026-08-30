import json
import math
from pathlib import Path
import unittest

from ashare_pipeline.financial_schema import (
    DATASET_TO_STATEMENT,
    FINANCIAL_REQUEST_VERSION,
    MAPPING_VERSION,
    FinancialFact,
    classify_period,
    field_rules,
)
from ashare_pipeline.industry_templates import (
    INDUSTRY_TO_TEMPLATE,
    TEMPLATE_VERSION,
    resolve_template,
)


def fact_fields(**overrides):
    fields = {
        "security_id": "SH600001",
        "statement": "income",
        "metric_key": "revenue",
        "period_start": "2025-01-01",
        "period_end": "2025-12-31",
        "period_kind": "FY",
        "value": 123.0,
        "unit": "CNY",
        "nature": "duration",
        "announced_at_utc": "2026-03-31T16:00:00+08:00",
        "effective_at_utc": "2026-04-01T07:00:00+00:00",
        "source_updated_at_utc": None,
        "source_snapshot_id": "snapshot-a",
        "source_field": "TOTAL_OPERATE_INCOME",
        "raw_row_hash": "a" * 64,
        "mapping_version": MAPPING_VERSION,
        "created_at": "2026-08-29T00:00:00+00:00",
    }
    fields.update(overrides)
    return fields


class FinancialSchemaTests(unittest.TestCase):
    def test_classify_period_preserves_other_periods_but_marks_feature_window(self):
        self.assertEqual(classify_period("2025-12-31", "2025年报", "年报").period_kind, "FY")
        self.assertEqual(classify_period("2026-06-30", "2026中报", "中报").period_kind, "H1")
        self.assertEqual(classify_period("2026-03-31", "2026一季报", "一季报").period_kind, "Q1")
        self.assertEqual(classify_period("2026-09-30", "2026三季报", "三季报").period_kind, "Q3")
        other = classify_period("2026-02-28", "其他", "其他")
        self.assertEqual(other.period_kind, "OTHER")
        self.assertFalse(other.is_feature_period)
        self.assertEqual(other.period_start, "2026-01-01")
        self.assertTrue(classify_period("2026-06-30", None, None).is_feature_period)
        self.assertIsNone(classify_period("not-a-date", None, None))

    def test_financial_fact_identity_excludes_created_at_but_includes_revision(self):
        first = FinancialFact.create(**fact_fields(created_at="2026-08-29T00:00:00+00:00"))
        rebuilt = FinancialFact.create(**fact_fields(created_at="2026-08-30T00:00:00+00:00"))
        revised = FinancialFact.create(**fact_fields(
            created_at="2026-08-30T00:00:00+00:00",
            raw_row_hash="b" * 64,
        ))
        self.assertEqual(first.id, rebuilt.id)
        self.assertNotEqual(first.id, revised.id)
        self.assertEqual(first.announced_at_utc, "2026-03-31T08:00:00+00:00")
        self.assertEqual(FinancialFact.from_record(first.to_record()), first)

    def test_financial_fact_rejects_nonfinite_values_invalid_units_and_bad_nature_periods(self):
        for invalid in (True, math.nan, math.inf, -math.inf):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                FinancialFact.create(**fact_fields(value=invalid))
        with self.assertRaises(ValueError):
            FinancialFact.create(**fact_fields(unit="USD"))
        with self.assertRaises(ValueError):
            FinancialFact.create(**fact_fields(nature="instant", period_start="2025-01-01"))

    def test_field_rules_cover_approved_facts_without_financial_misclassification(self):
        rules = {
            rule.metric_key: rule
            for statement in ("income", "balance", "cash_flow")
            for rule in field_rules(statement)
        }
        self.assertEqual(DATASET_TO_STATEMENT["profit_sheet"], "income")
        self.assertEqual(MAPPING_VERSION, "eastmoney-financial-mapping-v1")
        self.assertEqual(FINANCIAL_REQUEST_VERSION, "eastmoney-financial-request-v1")
        self.assertEqual(rules["revenue"].source_fields, ("TOTAL_OPERATE_INCOME", "OPERATE_INCOME"))
        self.assertEqual(rules["operating_cost"].source_fields, ("TOTAL_OPERATE_COST", "OPERATE_COST"))
        self.assertEqual(rules["short_term_debt"].source_fields, ("SHORT_LOAN", "SHORT_FIN_PAYABLE"))
        self.assertEqual(rules["operating_cash_flow"].source_fields, ("NETCASH_OPERATE", "OPERATE_NETCASH_BALANCE"))
        self.assertTrue({
            "revenue", "operating_cost", "operating_profit", "total_profit", "income_tax",
            "net_profit", "parent_net_profit", "deduct_parent_net_profit", "interest_expense",
            "rd_expense", "cash", "total_assets", "total_liabilities", "parent_equity",
            "total_equity", "short_term_debt", "current_portion_long_term_debt", "long_term_debt",
            "bonds_payable", "lease_liabilities", "notes_receivable", "accounts_receivable",
            "contract_assets", "inventory", "notes_payable", "accounts_payable", "contract_liabilities",
            "share_capital", "goodwill", "operating_cash_flow", "capital_expenditure",
            "cash_dividends", "interest_paid", "acquisition_cash_paid", "disposal_long_asset_cash",
            "equity_financing_cash", "debt_financing_cash", "debt_repayment_cash",
        }.issubset(rules))
        industrial_sources = {source for rule in rules.values() for source in rule.source_fields}
        self.assertFalse({"DEPOSIT", "TRADING_LIAB", "INSURANCE_RESERVE"} & industrial_sources)

    def test_registry_has_no_implicit_general_fallback(self):
        self.assertEqual(resolve_template("半导体").template_id, "rd_growth")
        self.assertEqual(resolve_template("房地产开发").template_id, "real_estate_high_leverage")
        self.assertEqual(resolve_template("银行").template_id, "bank")
        self.assertEqual(resolve_template("不存在行业").template_id, "unclassified")
        self.assertEqual(TEMPLATE_VERSION, "template-registry-v1")

    def test_registry_explicitly_lists_all_design_candidate_industries(self):
        fixture = json.loads(Path("tests/fixtures/industry_template_registry_v1.json").read_text(encoding="utf-8"))
        prefilter = json.loads(Path("data/curated/prefilter.json").read_text(encoding="utf-8"))
        candidate_industries = {record["industry"] for record in prefilter["records"]}
        fixture_industries = set(fixture["candidate_industries"])
        self.assertEqual(fixture_industries, candidate_industries)
        for industry in fixture_industries:
            with self.subTest(industry=industry):
                self.assertIn(industry, INDUSTRY_TO_TEMPLATE)


if __name__ == "__main__":
    unittest.main()
