"""Small, restartable pilot collector. Optional source packages load only online."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .state_store import StateStore


SHANGHAI = ZoneInfo("Asia/Shanghai")
DEFAULT_SYMBOLS = "SH600000,SZ000001,SZ300750,SH688001,SZ002594,SH601318"


def market_date_status(requested: str, now: datetime | None = None) -> str:
    local_now = now.astimezone(SHANGHAI) if now else datetime.now(SHANGHAI)
    requested_date = datetime.fromisoformat(requested).date()
    if requested_date > local_now.date() or (requested_date == local_now.date() and local_now.hour * 60 + local_now.minute < 15 * 60 + 30):
        return "pending"
    return "completed"


def _persist_status(root: Path, status: dict) -> None:
    root.mkdir(parents=True, exist_ok=True)
    part: Path | None = None
    try:
        descriptor, part_name = tempfile.mkstemp(prefix=".pilot_status.", suffix=".part", dir=root)
        part = Path(part_name)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            json.dump(status, handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(part, root / "pilot_status.json")
        part = None
    except BaseException:
        if part is not None:
            part.unlink(missing_ok=True)
        raise


def _write_batch(store: StateStore, snapshots, batch, task_key: str, job_id: str) -> dict:
    path, digest, _ = snapshots.write(batch)
    request_fingerprint = json.dumps(batch.request, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    store.record_snapshot(batch.source, batch.dataset, request_fingerprint, digest, str(path), len(batch.records), batch.fetched_at_utc)
    return {"dataset": batch.dataset, "source": batch.source, "source_version": batch.source_version,
            "request_fingerprint": hashlib.sha256(request_fingerprint.encode("utf-8")).hexdigest(),
            "fetched_at_utc": batch.fetched_at_utc, "rows": len(batch.records), "hash": digest,
            "path": str(path), "task_key": task_key, "job_id": job_id, "status": "succeeded"}


def _job_result(store: StateStore, job_id: str, task_key: str) -> list[dict]:
    job = store.get_job(job_id)
    if job is None:
        return [{"dataset": task_key, "status": "pending"}]
    if job["status"] == "succeeded" and job["result"]:
        return list(job["result"].get("batches", []))
    result = {"dataset": task_key, "status": job["status"], "job_id": job_id}
    if job["error"] is not None:
        result["error"] = job["error"]
    if job["next_retry_at"] is not None:
        result["next_retry_at"] = job["next_retry_at"]
    return [result]


def _trading_date(records: list[dict], latest_allowed) -> str | None:
    dates: list[str] = []
    for row in records:
        value = row.get("calendar_date", row.get("date"))
        status = str(row.get("is_trading_day", row.get("is_trading", "0"))).strip().lower()
        if value is None or status not in {"1", "true", "yes", "是"}:
            continue
        parsed = datetime.fromisoformat(str(value)).date()
        if parsed <= latest_allowed:
            dates.append(parsed.isoformat())
    return max(dates) if dates else None


def _calendar_records(summary: list[dict]) -> list[dict]:
    from .sources import FetchBatch

    for item in summary:
        if item.get("dataset") != "trade_dates" or not item.get("path"):
            continue
        try:
            payload = json.loads(Path(item["path"]).read_text(encoding="utf-8"))
            batch = FetchBatch(payload["source"], payload["dataset"], payload["request"], payload["records"], payload["fetched_at_utc"], payload["source_version"], payload["metadata"])
            if batch.sha256() != item.get("hash"):
                return []
            return list(batch.records)
        except (OSError, ValueError, TypeError, KeyError):
            return []
    return []


def _calendar_evidence(records: list[dict], latest_allowed) -> list[dict]:
    evidence = []
    for row in records:
        value = row.get("calendar_date", row.get("date"))
        if value is None:
            continue
        try:
            if datetime.fromisoformat(str(value)).date() <= latest_allowed:
                evidence.append({"calendar_date": str(value), "is_trading_day": str(row.get("is_trading_day", row.get("is_trading", "0")))})
        except ValueError:
            continue
    return evidence[-10:]


def _run_online(root: Path, store: StateStore, symbols: list[str], now: datetime | None = None) -> dict:
    from .snapshot_store import SnapshotStore
    from .sources import AKShareSource, BaoStockSource, RetryableSourceError, SourceBlocked, SourceError

    local_now = (now or datetime.now(SHANGHAI)).astimezone(SHANGHAI)
    now_utc = local_now.astimezone(timezone.utc).isoformat()
    store.recover_expired_leases(now_utc)
    snapshots = SnapshotStore(root)
    bao, ak = BaoStockSource(), AKShareSource()
    as_of = local_now.date()
    as_of_text = as_of.isoformat()
    requested_status = market_date_status(as_of_text, local_now)
    latest_allowed = as_of if requested_status == "completed" else as_of - timedelta(days=1)
    blocked_sources: set[str] = set()

    def execute(source: str, task: str, collect) -> list[dict]:
        task_key = f"{source}:{task}:{as_of_text}"
        job_kind = f"pilot_fetch:{task_key}"
        job_id = store.enqueue_job(job_kind, task_key, {"task": task, "source": source, "as_of_cn": as_of_text})
        existing = store.get_job(job_id)
        existing_blocked = bool(existing and existing["status"] == "terminal_failed" and existing["error"] and existing["error"].get("classification") == "blocked")
        if existing_blocked:
            blocked_sources.add(source)
            return _job_result(store, job_id, task_key)
        if source in blocked_sources:
            if existing and existing["status"] == "succeeded":
                return _job_result(store, job_id, task_key)
            return [{"dataset": task_key, "status": "blocked_by_circuit", "source": source, "job_id": job_id}]
        leased = store.lease_next_job([job_kind], "pilot", 300, now_utc)
        if leased is None:
            return _job_result(store, job_id, task_key)
        try:
            collected = collect()
            batches = collected.values() if isinstance(collected, dict) else [collected]
            written = [_write_batch(store, snapshots, batch, task_key, job_id) for batch in batches]
            store.complete_job(job_id, {"batches": written})
            return written
        except SourceBlocked as error:
            store.fail_job(job_id, {"classification": "blocked", "message": str(error)}, False)
            blocked_sources.add(source)
            return [{"dataset": task_key, "status": "blocked", "source": source, "error": str(error), "job_id": job_id}]
        except RetryableSourceError as error:
            store.fail_job(job_id, {"classification": "retryable", "message": str(error)}, True)
            return [{"dataset": task_key, "status": "retryable_failed", "source": source, "error": str(error), "job_id": job_id}]
        except SourceError as error:
            store.fail_job(job_id, {"classification": "terminal", "message": str(error)}, False)
            return [{"dataset": task_key, "status": "terminal_failed", "source": source, "error": str(error), "job_id": job_id}]
        except Exception as error:
            store.fail_job(job_id, {"classification": "unexpected", "message": str(error), "type": type(error).__name__}, True)
            return [{"dataset": task_key, "status": "retryable_failed", "source": source, "error": str(error), "job_id": job_id}]

    results = []
    results.extend(execute("baostock", "security_master", bao.fetch_security_master))
    calendar = execute("baostock", "trade_dates", lambda: bao.fetch_trade_dates("2026-08-24", as_of_text))
    results.extend(calendar)
    calendar_records = _calendar_records(calendar)
    latest = _trading_date(calendar_records, latest_allowed)
    results.extend(execute("akshare", "disclosure_schedule", ak.fetch_disclosure_schedule))
    results.extend(execute("akshare", "performance_report", ak.fetch_performance_report))
    if latest is not None:
        for symbol in symbols:
            code = "sh." + symbol[2:] if symbol.startswith("SH") else "sz." + symbol[2:]
            results.extend(execute("baostock", f"daily:{symbol}:{latest}", lambda code=code: bao.fetch_daily(code, "2026-08-24", latest)))
    else:
        results.append({"dataset": "daily_refresh", "status": "pending", "reason": "no_completed_trading_date"})
    for symbol in symbols:
        results.extend(execute("akshare", f"financial:{symbol}", lambda symbol=symbol: ak.fetch_financial_statements(symbol)))
    results.extend(execute("akshare", "spot_snapshot", ak.fetch_spot_snapshot))
    return {"batches": results, "requested_shanghai_date": as_of_text,
            "requested_shanghai_date_status": requested_status, "latest_completed_trading_date": latest,
            "trading_calendar_evidence": _calendar_evidence(calendar_records, latest_allowed)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--db", required=True)
    parser.add_argument("--online", action="store_true")
    parser.add_argument("--symbols", default=DEFAULT_SYMBOLS)
    arguments = parser.parse_args(argv)
    root = Path(arguments.root)
    store = StateStore(arguments.db)
    store.initialize()
    status = {"schema_version": 1, "mode": "online" if arguments.online else "offline",
              "generated_at_utc": datetime.now(timezone.utc).isoformat(), "batches": [],
              "next_step": "run with --online"}
    if arguments.online:
        status.update(_run_online(root, store, [item for item in arguments.symbols.split(",") if item]))
        status["next_step"] = "retry retryable_failed batches; do not treat pending dates as empty data"
    _persist_status(root, status)
    print(json.dumps(status, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
