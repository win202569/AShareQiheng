"""Neutral, pure authority for the versioned derived financial projection."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping


DERIVED_FORMULA_VERSION = "financial-derived-v1"

FORMULA_PERIODS = (
    ("2021-12-31", "FY2021"),
    ("2022-12-31", "FY2022"),
    ("2023-12-31", "FY2023"),
    ("2024-12-31", "FY2024"),
    ("2025-12-31", "FY2025"),
    ("2025-06-30", "2025H1"),
    ("2026-06-30", "2026H1"),
)

_PERIOD_KEY = dict(FORMULA_PERIODS)
_OPENING_PERIOD = {
    "2022-12-31": "2021-12-31",
    "2023-12-31": "2022-12-31",
    "2024-12-31": "2023-12-31",
    "2025-12-31": "2024-12-31",
    "2025-06-30": "2024-12-31",
    "2026-06-30": "2025-12-31",
}


@dataclass(frozen=True)
class FormulaFact:
    metric_key: str
    period_end: str
    value: float
    unit: str
    identity: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.metric_key, str)
            or not self.metric_key
            or not isinstance(self.period_end, str)
            or not self.period_end
            or isinstance(self.value, bool)
            or not isinstance(self.value, (int, float))
            or not math.isfinite(float(self.value))
            or not isinstance(self.unit, str)
            or not self.unit
            or not isinstance(self.identity, str)
            or not self.identity
        ):
            raise ValueError("formula fact must contain canonical finite input data")
        object.__setattr__(self, "value", float(self.value))


@dataclass(frozen=True)
class DerivedFormulaSpec:
    dimension: str
    metric_key: str
    period_key: str
    unit: str
    missing_reason: str
    result_state: str = "derived_or_missing"
    formula_version: str = DERIVED_FORMULA_VERSION

    @property
    def logical_id(self) -> str:
        return f"{self.dimension}.{self.metric_key}.{self.period_key}"

    @property
    def canonical_key(self) -> str:
        return f"{self.dimension.lower()}.{self.metric_key}.{self.period_key}"


@dataclass(frozen=True)
class DerivedFormulaResult:
    spec: DerivedFormulaSpec
    status: str
    value: float | None
    missing_reason: str | None
    operand_ids: tuple[str, ...]


_PER_PERIOD_SPECS = (
    ("M", "gross_profit", "CNY", "missing_operand:gross_profit"),
    ("M", "ebit", "CNY", "missing_operand:ebit"),
    ("M", "effective_tax_rate", "ratio", "invalid_denominator:total_profit"),
    ("M", "nopat", "CNY", "missing_operand:nopat"),
    ("CA", "fcf", "CNY", "missing_operand:fcf"),
    ("FS", "interest_bearing_debt", "CNY", "missing_operand:interest_bearing_debt"),
    ("FS", "net_debt", "CNY", "missing_operand:net_debt"),
    ("M", "invested_capital", "CNY", "missing_operand:invested_capital"),
    (
        "M",
        "operating_working_capital",
        "CNY",
        "missing_operand:operating_working_capital",
    ),
    ("M", "gross_margin", "ratio", "invalid_denominator:revenue"),
    (
        "EQ",
        "total_accruals",
        "ratio",
        "invalid_denominator:average_total_assets",
    ),
    ("M", "roic", "ratio", "invalid_denominator:average_invested_capital"),
)


def _build_catalog() -> tuple[DerivedFormulaSpec, ...]:
    specs: list[DerivedFormulaSpec] = []
    for _period_end_value, period_key in FORMULA_PERIODS:
        for dimension, metric_key, unit, reason in _PER_PERIOD_SPECS:
            if period_key == "FY2021" and metric_key in {"total_accruals", "roic"}:
                specs.append(
                    DerivedFormulaSpec(
                        dimension,
                        metric_key,
                        period_key,
                        unit,
                        "frozen_window_no_opening_period",
                        "not_applicable",
                    )
                )
            else:
                specs.append(
                    DerivedFormulaSpec(
                        dimension, metric_key, period_key, unit, reason
                    )
                )
    for period_key in ("FY2022", "FY2023", "FY2024", "FY2025", "2026H1"):
        specs.append(
            DerivedFormulaSpec(
                "G",
                "revenue_symmetric_growth",
                period_key,
                "ratio",
                "invalid_denominator:symmetric_growth",
            )
        )
    specs.append(
        DerivedFormulaSpec(
            "G",
            "revenue_cagr",
            "FY2025",
            "ratio",
            "invalid_endpoint:revenue_cagr",
        )
    )
    return tuple(specs)


DERIVED_FORMULA_SPECS = _build_catalog()
_SPEC_BY_SLOT = {
    (spec.metric_key, spec.period_key): spec for spec in DERIVED_FORMULA_SPECS
}


def symmetric_growth(current: float, previous: float) -> float | None:
    if any(
        isinstance(value, bool) or not isinstance(value, (int, float))
        for value in (current, previous)
    ):
        return None
    current_value = float(current)
    previous_value = float(previous)
    if not math.isfinite(current_value) or not math.isfinite(previous_value):
        return None
    denominator = abs(current_value) + abs(previous_value)
    if denominator == 0:
        return None
    return 200.0 * (current_value - previous_value) / denominator


def positive_cagr(start: float, end: float, years: int) -> float | None:
    if (
        isinstance(start, bool)
        or isinstance(end, bool)
        or isinstance(years, bool)
        or not isinstance(start, (int, float))
        or not isinstance(end, (int, float))
        or not isinstance(years, int)
    ):
        return None
    start_value = float(start)
    end_value = float(end)
    if not math.isfinite(start_value) or not math.isfinite(end_value):
        return None
    if start_value <= 0 or end_value <= 0 or years <= 0:
        return None
    return 100.0 * ((end_value / start_value) ** (1.0 / years) - 1.0)


def _facts(
    inputs: Mapping[tuple[str, str], FormulaFact],
    period_end: str,
    metric_keys: tuple[str, ...],
) -> tuple[FormulaFact, ...] | None:
    result = tuple(inputs.get((metric_key, period_end)) for metric_key in metric_keys)
    if any(fact is None or fact.unit != "CNY" for fact in result):
        return None
    return result  # type: ignore[return-value]


def _deduplicated(*groups: tuple[FormulaFact, ...]) -> tuple[FormulaFact, ...]:
    by_identity = {fact.identity: fact for group in groups for fact in group}
    return tuple(by_identity[identity] for identity in sorted(by_identity))


def _sum(
    inputs: Mapping[tuple[str, str], FormulaFact],
    period_end: str,
    metric_keys: tuple[str, ...],
    signs: tuple[float, ...] | None = None,
) -> tuple[float | None, tuple[FormulaFact, ...]]:
    operands = _facts(inputs, period_end, metric_keys)
    if operands is None:
        return None, ()
    coefficients = signs or (1.0,) * len(metric_keys)
    return (
        sum(
            coefficient * fact.value
            for coefficient, fact in zip(coefficients, operands)
        ),
        operands,
    )


def _invested_capital(
    inputs: Mapping[tuple[str, str], FormulaFact], period_end: str
) -> tuple[float | None, tuple[FormulaFact, ...]]:
    operands = _facts(
        inputs,
        period_end,
        (
            "total_equity",
            "short_term_debt",
            "current_portion_long_term_debt",
            "long_term_debt",
            "bonds_payable",
            "lease_liabilities",
            "cash",
        ),
    )
    if operands is None:
        return None, ()
    return (
        operands[0].value
        + sum(item.value for item in operands[1:6])
        - operands[6].value,
        operands,
    )


def _result(
    spec: DerivedFormulaSpec,
    value: float | None,
    operands: tuple[FormulaFact, ...],
) -> DerivedFormulaResult:
    if spec.result_state == "not_applicable":
        return DerivedFormulaResult(
            spec, "not_applicable", None, spec.missing_reason, ()
        )
    if value is None or not math.isfinite(float(value)) or not operands:
        return DerivedFormulaResult(spec, "missing", None, spec.missing_reason, ())
    return DerivedFormulaResult(
        spec,
        "derived",
        float(value),
        None,
        tuple(fact.identity for fact in _deduplicated(operands)),
    )


def evaluate_derived_financial(
    facts_by_metric_period: Mapping[tuple[str, str], FormulaFact],
) -> tuple[DerivedFormulaResult, ...]:
    """Evaluate the exact 90-slot projection from frozen canonical raw inputs."""
    inputs = dict(facts_by_metric_period)
    for slot, fact in inputs.items():
        if slot != (fact.metric_key, fact.period_end):
            raise ValueError("formula fact mapping key does not match its fact")

    results: list[DerivedFormulaResult] = []
    for period_end, period_key in FORMULA_PERIODS:
        gross_profit, gross_operands = _sum(
            inputs,
            period_end,
            ("revenue", "operating_cost"),
            (1.0, -1.0),
        )
        results.append(
            _result(_SPEC_BY_SLOT[("gross_profit", period_key)], gross_profit, gross_operands)
        )

        ebit, ebit_operands = _sum(
            inputs, period_end, ("total_profit", "interest_expense")
        )
        results.append(_result(_SPEC_BY_SLOT[("ebit", period_key)], ebit, ebit_operands))

        tax_operands = _facts(inputs, period_end, ("income_tax", "total_profit"))
        tax_rate = None
        if tax_operands is not None and tax_operands[1].value > 0:
            tax_rate = min(
                0.5, max(0.0, tax_operands[0].value / tax_operands[1].value)
            )
        results.append(
            _result(
                _SPEC_BY_SLOT[("effective_tax_rate", period_key)],
                tax_rate,
                tax_operands or (),
            )
        )

        nopat = None
        nopat_operands: tuple[FormulaFact, ...] = ()
        if ebit is not None and tax_rate is not None:
            nopat = ebit * (1.0 - tax_rate)
            nopat_operands = _deduplicated(ebit_operands, tax_operands or ())
        results.append(
            _result(_SPEC_BY_SLOT[("nopat", period_key)], nopat, nopat_operands)
        )

        fcf, fcf_operands = _sum(
            inputs,
            period_end,
            ("operating_cash_flow", "capital_expenditure"),
            (1.0, -1.0),
        )
        results.append(_result(_SPEC_BY_SLOT[("fcf", period_key)], fcf, fcf_operands))

        debt_metrics = (
            "short_term_debt",
            "current_portion_long_term_debt",
            "long_term_debt",
            "bonds_payable",
            "lease_liabilities",
        )
        debt, debt_operands = _sum(inputs, period_end, debt_metrics)
        results.append(
            _result(
                _SPEC_BY_SLOT[("interest_bearing_debt", period_key)],
                debt,
                debt_operands,
            )
        )

        cash = inputs.get(("cash", period_end))
        cash_operands = (cash,) if cash is not None and cash.unit == "CNY" else ()
        net_debt = debt - cash.value if debt is not None and cash_operands else None
        results.append(
            _result(
                _SPEC_BY_SLOT[("net_debt", period_key)],
                net_debt,
                _deduplicated(debt_operands, cash_operands),
            )
        )

        invested_capital, invested_operands = _invested_capital(inputs, period_end)
        results.append(
            _result(
                _SPEC_BY_SLOT[("invested_capital", period_key)],
                invested_capital,
                invested_operands,
            )
        )

        working_capital, working_operands = _sum(
            inputs,
            period_end,
            (
                "notes_receivable",
                "accounts_receivable",
                "contract_assets",
                "inventory",
                "notes_payable",
                "accounts_payable",
                "contract_liabilities",
            ),
            (1.0, 1.0, 1.0, 1.0, -1.0, -1.0, -1.0),
        )
        results.append(
            _result(
                _SPEC_BY_SLOT[("operating_working_capital", period_key)],
                working_capital,
                working_operands,
            )
        )

        revenue = inputs.get(("revenue", period_end))
        revenue_operands = (
            (revenue,) if revenue is not None and revenue.unit == "CNY" else ()
        )
        gross_margin = (
            gross_profit / revenue.value
            if gross_profit is not None
            and revenue_operands
            and math.isfinite(revenue.value)
            and revenue.value != 0
            else None
        )
        results.append(
            _result(
                _SPEC_BY_SLOT[("gross_margin", period_key)],
                gross_margin,
                _deduplicated(gross_operands, revenue_operands),
            )
        )

        opening_period = _OPENING_PERIOD.get(period_end)
        if opening_period is None:
            results.append(
                _result(
                    _SPEC_BY_SLOT[("total_accruals", period_key)], None, ()
                )
            )
            results.append(_result(_SPEC_BY_SLOT[("roic", period_key)], None, ()))
            continue

        assets = _facts(
            inputs,
            period_end,
            ("net_profit", "operating_cash_flow", "total_assets"),
        )
        opening_assets = inputs.get(("total_assets", opening_period))
        accruals = None
        accrual_operands: tuple[FormulaFact, ...] = ()
        if assets is not None and opening_assets is not None and opening_assets.unit == "CNY":
            average_assets = (opening_assets.value + assets[2].value) / 2.0
            accrual_operands = _deduplicated(assets, (opening_assets,))
            if math.isfinite(average_assets) and average_assets != 0:
                accruals = (assets[0].value - assets[1].value) / average_assets
        results.append(
            _result(
                _SPEC_BY_SLOT[("total_accruals", period_key)],
                accruals,
                accrual_operands,
            )
        )

        opening_invested, opening_invested_operands = _invested_capital(
            inputs, opening_period
        )
        roic = None
        roic_operands: tuple[FormulaFact, ...] = ()
        if nopat is not None and invested_capital is not None and opening_invested is not None:
            average_invested = (opening_invested + invested_capital) / 2.0
            roic_operands = _deduplicated(
                nopat_operands, invested_operands, opening_invested_operands
            )
            if math.isfinite(average_invested) and average_invested != 0:
                roic = nopat / average_invested
        results.append(
            _result(_SPEC_BY_SLOT[("roic", period_key)], roic, roic_operands)
        )

    growth_pairs = (
        ("2022-12-31", "2021-12-31"),
        ("2023-12-31", "2022-12-31"),
        ("2024-12-31", "2023-12-31"),
        ("2025-12-31", "2024-12-31"),
        ("2026-06-30", "2025-06-30"),
    )
    for current_period, previous_period in growth_pairs:
        current = inputs.get(("revenue", current_period))
        previous = inputs.get(("revenue", previous_period))
        operands: tuple[FormulaFact, ...] = ()
        value = None
        if (
            current is not None
            and previous is not None
            and current.unit == previous.unit == "CNY"
        ):
            operands = _deduplicated((current,), (previous,))
            value = symmetric_growth(current.value, previous.value)
        results.append(
            _result(
                _SPEC_BY_SLOT[("revenue_symmetric_growth", _PERIOD_KEY[current_period])],
                value,
                operands,
            )
        )

    start = inputs.get(("revenue", "2022-12-31"))
    end = inputs.get(("revenue", "2025-12-31"))
    cagr_operands: tuple[FormulaFact, ...] = ()
    cagr = None
    if start is not None and end is not None and start.unit == end.unit == "CNY":
        cagr_operands = _deduplicated((start,), (end,))
        cagr = positive_cagr(start.value, end.value, 3)
    results.append(
        _result(
            _SPEC_BY_SLOT[("revenue_cagr", "FY2025")],
            cagr,
            cagr_operands,
        )
    )
    if len(results) != len(DERIVED_FORMULA_SPECS):
        raise AssertionError("derived formula projection cardinality drift")
    return tuple(results)
