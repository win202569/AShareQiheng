"""Optional-dependency adapters for auditable, raw A-share source batches."""

from __future__ import annotations

import hashlib
import importlib
import json
import math
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Callable


class SourceError(RuntimeError):
    """A source could not provide a valid batch."""


class RetryableSourceError(SourceError):
    """A temporary source problem; callers may schedule a retry."""


class TerminalSourceError(SourceError):
    """A locally invalid request or unavailable optional dependency."""


class SourceBlocked(SourceError):
    """The remote source appears to have blocked or challenged the request."""


def _normalize(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _normalize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    try:
        if value != value:  # NaN and pandas NaT without importing pandas.
            return None
    except (TypeError, ValueError):
        pass
    if value.__class__.__name__ == "NaTType" or str(value) == "NaT":
        return None
    return value


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        _normalize(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


@dataclass(frozen=True)
class FetchBatch:
    source: str
    dataset: str
    request: dict
    records: list[dict]
    fetched_at_utc: str
    source_version: str
    metadata: dict

    def __post_init__(self) -> None:
        object.__setattr__(self, "request", _normalize(self.request))
        object.__setattr__(self, "records", _normalize(self.records))
        object.__setattr__(self, "metadata", _normalize(self.metadata))

    def canonical_bytes(self) -> bytes:
        return _canonical_json({
            "source": self.source,
            "dataset": self.dataset,
            "request": self.request,
            "records": self.records,
            "source_version": self.source_version,
            "metadata": self.metadata,
        })

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


_HTTP_STATUS = re.compile(r"(?<!\d)(?:http\s*)?(?:403|429)(?!\d)", re.IGNORECASE)
_HTTP_CHALLENGE = re.compile(r"(?:http\s*403|429\s+(?:too\s+many\s+)?requests?)", re.IGNORECASE)


def _is_access_error(value: object) -> bool:
    """Only inspect error contexts, where a bare HTTP status is meaningful."""
    text = str(value)
    lowered = text.lower()
    return bool(_HTTP_STATUS.search(text)) or any(marker in lowered for marker in ("验证码", "captcha", "<html", "<!doctype"))


def _is_challenge_cell(value: object) -> bool:
    """Do not turn ordinary numeric sequence numbers or stock codes into HTTP errors."""
    if not isinstance(value, str):
        return False
    lowered = value.lower()
    return bool(_HTTP_CHALLENGE.search(value)) or any(marker in lowered for marker in ("验证码", "captcha", "<html", "<!doctype"))


def _frame_records(frame: Any) -> list[dict]:
    try:
        records = frame.to_dict(orient="records")
    except AttributeError as error:
        raise RetryableSourceError("source did not return a DataFrame-like result") from error
    if not isinstance(records, list):
        raise RetryableSourceError("source returned malformed tabular result")
    if any(_is_challenge_cell(value) for record in records for value in record.values()):
        raise SourceBlocked("source returned access-control or HTML response")
    return [_normalize(dict(record)) for record in records]


class BaoStockSource:
    """BaoStock adapter whose public operations own their login lifecycle."""

    DAILY_FIELDS = (
        "date,code,open,high,low,close,preclose,volume,amount,adjustflag,turn,"
        "tradestatus,pctChg,peTTM,pbMRQ,psTTM,pcfNcfTTM,isST"
    )

    def __init__(self, module: Any | None = None, clock: Callable[[], str] | None = None, sleeper: Callable[[float], None] | None = None):
        self.module = module
        self.clock = clock or (lambda: datetime.now(timezone.utc).isoformat())
        self.sleeper = sleeper or time.sleep

    def _module(self) -> Any:
        if self.module is None:
            try:
                self.module = importlib.import_module("baostock")
            except ImportError as error:
                raise TerminalSourceError("baostock is required only for online collection") from error
        return self.module

    def _rows(self, result: Any) -> list[dict]:
        if str(getattr(result, "error_code", "0")) != "0":
            message = getattr(result, "error_msg", "unknown BaoStock error")
            if _is_access_error(f"{getattr(result, 'error_code', '')} {message}"):
                raise SourceBlocked(str(message))
            raise RetryableSourceError(str(message))
        fields = list(getattr(result, "fields", []))
        records: list[dict] = []
        while result.next():
            records.append(dict(zip(fields, result.get_row_data())))
        return records

    def _fetch(self, dataset: str, request: dict, query: Callable[[Any], Any], metadata: dict | None = None) -> FetchBatch:
        module = self._module()
        try:
            login = module.login()
            if str(getattr(login, "error_code", "0")) != "0":
                message = str(getattr(login, "error_msg", "BaoStock login failed"))
                if _is_access_error(f"{getattr(login, 'error_code', '')} {message}"):
                    raise SourceBlocked(message)
                raise RetryableSourceError(message)
            self.sleeper(0.2)
            records = self._rows(query(module))
            result_metadata = dict(metadata or {})
            if dataset == "security_master":
                result_metadata["type_counts"] = _count(records, "type")
                result_metadata["status_counts"] = _count(records, "status")
            return FetchBatch(dataset=dataset, source="baostock", request=request, records=records,
                              fetched_at_utc=self.clock(), source_version=str(getattr(module, "__version__", "unknown")),
                              metadata=result_metadata)
        finally:
            module.logout()

    def fetch_security_master(self) -> FetchBatch:
        return self._fetch("security_master", {}, lambda module: module.query_stock_basic())

    def fetch_trade_dates(self, start_date: str, end_date: str) -> FetchBatch:
        return self._fetch("trade_dates", {"start_date": start_date, "end_date": end_date}, lambda module: module.query_trade_dates(start_date=start_date, end_date=end_date))

    def fetch_daily(self, code: str, start_date: str, end_date: str) -> FetchBatch:
        request = {"code": code, "start_date": start_date, "end_date": end_date, "frequency": "d", "adjustflag": "3", "fields": self.DAILY_FIELDS}
        return self._fetch("daily", request, lambda module: module.query_history_k_data_plus(**request))


def _count(records: list[dict], field: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for record in records:
        value = record.get(field)
        if value is not None:
            result[str(value)] = result.get(str(value), 0) + 1
    return result


class AKShareSource:
    """AKShare adapter that preserves raw source rows and records query evidence."""

    def __init__(self, module: Any | None = None, clock: Callable[[], str] | None = None):
        self.module = module
        self.clock = clock or (lambda: datetime.now(timezone.utc).isoformat())

    def _module(self) -> Any:
        if self.module is None:
            try:
                self.module = importlib.import_module("akshare")
            except ImportError as error:
                raise TerminalSourceError("akshare is required only for online collection") from error
        return self.module

    def _batch(self, dataset: str, request: dict, call: Callable[[Any], Any], metadata: dict | None = None, require_rows: bool = False) -> FetchBatch:
        module = self._module()
        try:
            records = _frame_records(call(module))
        except SourceError:
            raise
        except Exception as error:
            if _is_access_error(error):
                raise SourceBlocked(str(error)) from error
            raise RetryableSourceError(str(error)) from error
        if require_rows and not records:
            raise RetryableSourceError("source returned an empty spot snapshot")
        return FetchBatch("akshare", dataset, request, records, self.clock(), str(getattr(module, "__version__", "unknown")), metadata or {})

    def fetch_disclosure_schedule(self) -> FetchBatch:
        request = {"market": "沪深京", "period": "2026半年报"}
        return self._batch("disclosure_schedule", request, lambda module: module.stock_report_disclosure(**request))

    def fetch_performance_report(self, report_period: str = "20260630") -> FetchBatch:
        request = {"date": report_period}
        batch = self._batch("performance_report", request, lambda module: module.stock_yjbb_em(**request))
        source_mapping = {
            "股票代码": "股票代码", "股票简称": "股票简称", "每股收益": "每股收益",
            "营业总收入": "营业总收入-营业总收入", "营业总收入同比增长": "营业总收入-同比增长",
            "净利润": "净利润-净利润", "净利润同比增长": "净利润-同比增长",
            "每股净资产": "每股净资产", "净资产收益率": "净资产收益率",
            "每股经营现金流量": "每股经营现金流量", "销售毛利率": "销售毛利率",
            "所处行业": "所处行业", "最新公告日期": "最新公告日期",
        }
        available = set(batch.records[0]) if batch.records else set()
        missing = [source for source in source_mapping.values() if source not in available]
        if missing:
            raise TerminalSourceError(f"performance report missing required columns: {', '.join(missing)}")
        records = [{stable: record[source] for stable, source in source_mapping.items()} for record in batch.records]
        metadata = dict(batch.metadata)
        metadata["source_column_mapping"] = source_mapping
        return FetchBatch(batch.source, batch.dataset, batch.request, records, batch.fetched_at_utc, batch.source_version, metadata)

    def fetch_financial_statements(self, symbol: str, report_period: str = "2026-06-30") -> dict[str, FetchBatch]:
        specifications = {
            "balance_sheet": "stock_balance_sheet_by_report_em",
            "profit_sheet": "stock_profit_sheet_by_report_em",
            "cash_flow_sheet": "stock_cash_flow_sheet_by_report_em",
        }
        batches: dict[str, FetchBatch] = {}
        for dataset, method_name in specifications.items():
            request = {"symbol": symbol, "report_period": report_period}
            def collect(module: Any, name: str = method_name) -> Any:
                return getattr(module, name)(symbol=symbol)
            batch = self._batch(dataset, request, collect)
            matches = sum(str(row.get("REPORT_DATE", ""))[:10] == report_period for row in batch.records)
            metadata = {"report_period_match_count": matches, "column_count": len(batch.records[0]) if batch.records else 0,
                        "NOTICE_DATE": [row.get("NOTICE_DATE") for row in batch.records if row.get("NOTICE_DATE") is not None],
                        "UPDATE_DATE": [row.get("UPDATE_DATE") for row in batch.records if row.get("UPDATE_DATE") is not None]}
            batches[dataset] = FetchBatch(batch.source, batch.dataset, batch.request, batch.records, batch.fetched_at_utc, batch.source_version, metadata)
        return batches

    def fetch_cninfo_halfyear_disclosures(self, symbol: str, start_date: str = "20260701", end_date: str = "20260831") -> FetchBatch:
        request = {"symbol": symbol, "market": "沪深京", "category": "半年报", "start_date": start_date, "end_date": end_date}
        return self._batch("cninfo_halfyear_disclosures", request, lambda module: module.stock_zh_a_disclosure_report_cninfo(**request))

    def fetch_spot_snapshot(self) -> FetchBatch:
        return self._batch("spot_snapshot", {}, lambda module: module.stock_zh_a_spot_em(), require_rows=True)
