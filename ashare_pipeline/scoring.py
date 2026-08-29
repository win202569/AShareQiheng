"""Auditable bulk-report prefiltering that never masquerades as V2 scoring."""

from __future__ import annotations

import math
from collections import defaultdict


METRICS = (
    "revenue_yoy",
    "net_profit_yoy",
    "roe",
    "gross_margin",
    "operating_cash_flow_per_share",
)
GROWTH_WEIGHTS = {"revenue_yoy": 0.5, "net_profit_yoy": 0.5}
QUALITY_WEIGHTS = {"roe": 0.4, "gross_margin": 0.3, "operating_cash_flow_per_share": 0.3}
ATOMIC_COVERAGE_WEIGHTS = {
    "revenue_yoy": 0.275,
    "net_profit_yoy": 0.275,
    "roe": 0.18,
    "gross_margin": 0.135,
    "operating_cash_flow_per_share": 0.135,
}
MIN_INDUSTRY_SAMPLE = 20
MIN_REPRESENTATIVE_COVERAGE = 0.55
MAX_CANDIDATES = 120
PREFILTER_REASON = "仅供深抓排序，不是V2正式总分"


def _numeric(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        text = value.strip().replace(",", "")
        if not text:
            return None
        if text.endswith("%"):
            text = text[:-1]
        value = text
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(result) or math.isinf(result) else result


def _percentile_ranks(items: list[tuple[int, float]]) -> dict[int, float]:
    """Return average-tie percent ranks on [0, 100], with a singleton at 50."""

    if not items:
        return {}
    if len(items) == 1:
        return {items[0][0]: 50.0}
    ordered = sorted(items, key=lambda item: (item[1], item[0]))
    result: dict[int, float] = {}
    start = 0
    while start < len(ordered):
        end = start + 1
        while end < len(ordered) and ordered[end][1] == ordered[start][1]:
            end += 1
        average_zero_based_rank = (start + end - 1) / 2
        percentile = 100.0 * average_zero_based_rank / (len(ordered) - 1)
        for index, _ in ordered[start:end]:
            result[index] = percentile
        start = end
    return result


def _weighted_available(values: dict[str, float | None], weights: dict[str, float]) -> float | None:
    usable = [(values[key], weight) for key, weight in weights.items() if values.get(key) is not None]
    denominator = sum(weight for _, weight in usable)
    if denominator == 0:
        return None
    return sum(float(value) * weight for value, weight in usable) / denominator


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 6)


def build_prefilter(performance: list[dict]) -> tuple[list[dict], dict]:
    """Rank a maximum of 120 deep-fetch candidates using only present bulk fields."""

    values: list[dict[str, float | None]] = [
        {metric: _numeric(row.get(metric)) for metric in METRICS} for row in performance
    ]
    market_ranks: dict[str, dict[int, float]] = {}
    industry_ranks: dict[str, dict[str, dict[int, float]]] = {}
    industry_members: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(performance):
        industry_members[str(row.get("industry") or "")].append(index)

    for metric in METRICS:
        market_items = [(index, row_values[metric]) for index, row_values in enumerate(values) if row_values[metric] is not None]
        market_ranks[metric] = _percentile_ranks(market_items)
        metric_industry: dict[str, dict[int, float]] = {}
        for industry, members in industry_members.items():
            items = [(index, values[index][metric]) for index in members if values[index][metric] is not None]
            if industry and len(items) >= MIN_INDUSTRY_SAMPLE:
                metric_industry[industry] = _percentile_ranks(items)
        industry_ranks[metric] = metric_industry

    scored: list[dict] = []
    for index, source_row in enumerate(performance):
        industry = str(source_row.get("industry") or "")
        percentiles: dict[str, float | None] = {}
        scopes: dict[str, str | None] = {}
        for metric in METRICS:
            if values[index][metric] is None:
                percentiles[metric] = None
                scopes[metric] = None
            elif industry in industry_ranks[metric]:
                percentiles[metric] = industry_ranks[metric][industry][index]
                scopes[metric] = "industry"
            else:
                percentiles[metric] = market_ranks[metric][index]
                scopes[metric] = "market"

        growth = _weighted_available(percentiles, GROWTH_WEIGHTS)
        quality = _weighted_available(percentiles, QUALITY_WEIGHTS)
        proxy_modules = {"growth": growth, "quality": quality}
        prefilter = _weighted_available(proxy_modules, {"growth": 0.55, "quality": 0.45})
        coverage = sum(
            weight for metric, weight in ATOMIC_COVERAGE_WEIGHTS.items() if values[index][metric] is not None
        )
        row = dict(source_row)
        row.update(
            {
                "metric_percentiles": {key: _round(value) for key, value in percentiles.items()},
                "percentile_scope": scopes,
                "growth_proxy": _round(growth),
                "quality_proxy": _round(quality),
                "prefilter_score": _round(prefilter),
                "coverage": round(coverage, 6),
                "missing_metrics": [metric for metric in METRICS if values[index][metric] is None],
                "is_official_score": False,
                "reason": PREFILTER_REASON,
            }
        )
        if prefilter is not None:
            scored.append(row)

    def ranking_key(row: dict) -> tuple:
        return (-float(row["prefilter_score"]), -float(row["coverage"]), str(row.get("security_id") or row.get("code6") or ""))

    scored.sort(key=ranking_key)
    selected_ids: set[str] = set()
    selection_origin: dict[str, str] = {}
    candidates: list[dict] = []

    for industry in sorted(industry_members):
        if len(candidates) >= MAX_CANDIDATES:
            break
        if not industry or len(industry_members[industry]) < MIN_INDUSTRY_SAMPLE:
            continue
        eligible = [
            row
            for row in scored
            if str(row.get("industry") or "") == industry and float(row["coverage"]) >= MIN_REPRESENTATIVE_COVERAGE
        ]
        for row in eligible[:2]:
            if len(candidates) >= MAX_CANDIDATES:
                break
            security_id = str(row.get("security_id") or row.get("code6") or "")
            if security_id not in selected_ids:
                selected_ids.add(security_id)
                selection_origin[security_id] = "industry_representative"
                candidates.append(row)

    for row in scored:
        if len(candidates) >= MAX_CANDIDATES:
            break
        security_id = str(row.get("security_id") or row.get("code6") or "")
        if security_id in selected_ids:
            continue
        selected_ids.add(security_id)
        selection_origin[security_id] = "global_supplement"
        candidates.append(row)

    for row in candidates:
        security_id = str(row.get("security_id") or row.get("code6") or "")
        row["selection_origin"] = selection_origin[security_id]
    candidates.sort(key=ranking_key)
    coverage_values = [float(row["coverage"]) for row in scored]
    return candidates, {
        "input_count": len(performance),
        "scored_count": len(scored),
        "unscorable_count": len(performance) - len(scored),
        "candidate_count": len(candidates),
        "industry_representative_count": sum(
            row["selection_origin"] == "industry_representative" for row in candidates
        ),
        "average_scored_coverage": sum(coverage_values) / len(coverage_values) if coverage_values else 0.0,
        "is_official_score": False,
        "reason": PREFILTER_REASON,
    }
