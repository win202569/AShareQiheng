"""Explicit provisional industry-to-template registry for financial inputs."""

from __future__ import annotations

from dataclasses import dataclass


TEMPLATE_VERSION = "template-registry-v1"

_COMMON_FINANCIAL_SLOTS = (
    "revenue", "operating_cost", "operating_profit", "total_profit", "income_tax",
    "net_profit", "parent_net_profit", "deduct_parent_net_profit", "interest_expense",
    "rd_expense", "cash", "total_assets", "total_liabilities", "parent_equity",
    "total_equity", "short_term_debt", "current_portion_long_term_debt", "long_term_debt",
    "bonds_payable", "lease_liabilities", "notes_receivable", "accounts_receivable",
    "contract_assets", "inventory", "notes_payable", "accounts_payable", "contract_liabilities",
    "share_capital", "goodwill", "operating_cash_flow", "capital_expenditure", "cash_dividends",
    "interest_paid", "acquisition_cash_paid", "disposal_long_asset_cash", "equity_financing_cash",
    "debt_financing_cash", "debt_repayment_cash",
)


@dataclass(frozen=True)
class TemplateDefinition:
    template_id: str
    financial_slots: tuple[str, ...]
    specialized_inputs_required: bool


TEMPLATES: dict[str, TemplateDefinition] = {
    "bank": TemplateDefinition("bank", (), True),
    "insurance": TemplateDefinition("insurance", (), True),
    "broker": TemplateDefinition("broker", (), True),
    "real_estate_high_leverage": TemplateDefinition("real_estate_high_leverage", _COMMON_FINANCIAL_SLOTS, False),
    "resource_cycle": TemplateDefinition("resource_cycle", _COMMON_FINANCIAL_SLOTS, False),
    "utility": TemplateDefinition("utility", _COMMON_FINANCIAL_SLOTS, False),
    "rd_growth": TemplateDefinition("rd_growth", _COMMON_FINANCIAL_SLOTS, False),
    "general_nonfinancial": TemplateDefinition("general_nonfinancial", _COMMON_FINANCIAL_SLOTS, False),
    "unclassified": TemplateDefinition("unclassified", (), True),
}

# These source labels are intentionally exact.  Adding a new label requires a versioned mapping change.
INDUSTRY_TO_TEMPLATE: dict[str, str] = {
    "银行": "bank",
    "保险": "insurance",
    "证券": "broker",
    "证券Ⅱ": "broker",
    "房地产开发": "real_estate_high_leverage",
    "工业金属": "resource_cycle",
    "炼化及贸易": "resource_cycle",
    "煤炭开采": "resource_cycle",
    "普钢": "resource_cycle",
    "小金属": "resource_cycle",
    "化学原料": "resource_cycle",
    "水泥": "resource_cycle",
    "电力": "utility",
    "燃气Ⅱ": "utility",
    "半导体": "rd_growth",
    "电池": "rd_growth",
    "光伏设备": "rd_growth",
    "电子化学品Ⅱ": "rd_growth",
    "光学光电子": "rd_growth",
    "军工电子Ⅱ": "rd_growth",
    "其他电子Ⅱ": "rd_growth",
    "消费电子": "rd_growth",
    "元件": "rd_growth",
    "化学制药": "rd_growth",
    "生物制品": "rd_growth",
    "中药Ⅱ": "rd_growth",
    "医疗器械": "rd_growth",
    "自动化设备": "rd_growth",
    "游戏Ⅱ": "rd_growth",
    "IT服务Ⅱ": "rd_growth",
    "多元金融": "unclassified",
    "包装印刷": "general_nonfinancial",
    "出版": "general_nonfinancial",
    "电机Ⅱ": "general_nonfinancial",
    "电网设备": "general_nonfinancial",
    "纺织制造": "general_nonfinancial",
    "服装家纺": "general_nonfinancial",
    "工程机械": "general_nonfinancial",
    "工程咨询服务Ⅱ": "general_nonfinancial",
    "广告营销": "general_nonfinancial",
    "化学纤维": "general_nonfinancial",
    "化学制品": "general_nonfinancial",
    "环保设备Ⅱ": "general_nonfinancial",
    "环境治理": "general_nonfinancial",
    "基础建设": "general_nonfinancial",
    "家电零部件Ⅱ": "general_nonfinancial",
    "家居用品": "general_nonfinancial",
    "旅游及景区": "general_nonfinancial",
    "农产品加工": "general_nonfinancial",
    "农化制品": "general_nonfinancial",
    "其他电源设备Ⅱ": "general_nonfinancial",
    "汽车零部件": "general_nonfinancial",
    "塑料": "general_nonfinancial",
    "文娱用品": "general_nonfinancial",
    "文娱用品": "general_nonfinancial",
    "物流": "general_nonfinancial",
    "小家电": "general_nonfinancial",
    "休闲食品": "general_nonfinancial",
    "养殖业": "general_nonfinancial",
    "一般零售": "general_nonfinancial",
    "医疗服务": "general_nonfinancial",
    "医药商业": "general_nonfinancial",
    "专业服务": "general_nonfinancial",
    "专业工程": "general_nonfinancial",
    "专用设备": "general_nonfinancial",
}


def resolve_template(industry_name: str | None) -> TemplateDefinition:
    """Resolve only versioned exact labels; unknown labels fail closed."""
    template_id = INDUSTRY_TO_TEMPLATE.get(industry_name, "unclassified")
    return TEMPLATES[template_id]
