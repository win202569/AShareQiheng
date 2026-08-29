"""Incremental curation CLI with explicit final-publication blocking."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import math
import re
import sqlite3
import tempfile
from contextlib import closing
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from .curation import CORE_FIELDS, CUTOFF_CN, curate_performance, curate_universe, quality_gate
from .scoring import PREFILTER_REASON, build_prefilter
from .state_store import StateStore


SCHEMA_VERSION = 1
CURATED_SCHEMA_VERSION = 2
SHANGHAI = ZoneInfo("Asia/Shanghai")
RULESET_HASH = hashlib.sha256(b"a-share-scoring-v2-partial-prefilter-only").hexdigest()
PREFILTER_RULESET_HASH = hashlib.sha256(
    b"prefilter-v1:industry-percentiles:growth-55:quality-45:top-120"
).hexdigest()
CURATION_RULESET_HASH = hashlib.sha256(
    b"curation-v2:sh-sz-a:no-689:cutoff-2026-08-31:stable-dedupe:coverage-95"
).hexdigest()
FORMAL_FEATURES = ("G", "V", "M", "EQ", "FS", "CA", "T")
MARKET_PRICE_TRANSFORMATION_VERSION = "market-effective-close-v1"


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _hash(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _now_cn(value: str | None) -> datetime:
    if value is None:
        return datetime.now(SHANGHAI)
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError("now_cn must include a timezone offset")
    return parsed.astimezone(SHANGHAI)


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, part_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".part", dir=path.parent)
    part = Path(part_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            json.dump(payload, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(part, path)
    except BaseException:
        part.unlink(missing_ok=True)
        raise


def _read_json(path: Path) -> dict | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    return value if isinstance(value, dict) else None


def _default_sources():
    from .sources import AKShareSource, BaoStockSource

    return BaoStockSource(), AKShareSource()


def _default_snapshot_store(root: Path):
    from .snapshot_store import SnapshotStore

    return SnapshotStore(root)


def _latest_completed_market_date(now: datetime) -> str:
    candidate = now.date()
    if now.timetz().replace(tzinfo=None) < time(15, 30):
        candidate -= timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return candidate.isoformat()


def _snapshot_row(db: Path, source: str, dataset: str) -> dict | None:
    with closing(sqlite3.connect(db)) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """SELECT source, dataset, payload_hash, payload_path, row_count, fetched_at
            FROM source_snapshot WHERE source = ? AND dataset = ?
            ORDER BY fetched_at DESC, created_at DESC LIMIT 1""",
            (source, dataset),
        ).fetchone()
    return dict(row) if row else None


def _snapshot_document(row: dict | None, root: Path) -> dict | None:
    if row is None:
        return None
    path = Path(row["payload_path"])
    if not path.is_absolute():
        path = root / path
    return _read_json(path)


def _semantic_batch_payload(batch: Any) -> dict:
    return {
        "source": batch.source,
        "dataset": batch.dataset,
        "request": batch.request,
        "records": batch.records,
        "source_version": batch.source_version,
        "metadata": batch.metadata,
    }


def _semantic_snapshot_payload(document: dict) -> dict:
    return {
        "source": document.get("source"),
        "dataset": document.get("dataset"),
        "request": document.get("request", {}),
        "records": document.get("records", []),
        "source_version": document.get("source_version"),
        "metadata": document.get("metadata", {}),
    }


def _persist_batch(root: Path, db: Path, store: StateStore, snapshots: Any, batch: Any) -> dict:
    previous_row = _snapshot_row(db, batch.source, batch.dataset)
    previous_document = _snapshot_document(previous_row, root)
    semantic_hash = _hash(_semantic_batch_payload(batch))
    if previous_document is not None and _hash(_semantic_snapshot_payload(previous_document)) == semantic_hash:
        return {
            "dataset": batch.dataset,
            "source": batch.source,
            "source_version": batch.source_version,
            "request": batch.request,
            "rows": len(batch.records),
            "hash": previous_row["payload_hash"],
            "path": str(Path(previous_row["payload_path"]).resolve()),
            "semantic_hash": semantic_hash,
            "created": False,
        }
    path, digest, created = snapshots.write(batch)
    request_fingerprint = _hash(batch.request)
    store.record_snapshot(
        batch.source,
        batch.dataset,
        request_fingerprint,
        digest,
        str(path.resolve()),
        len(batch.records),
        batch.fetched_at_utc,
    )
    return {
        "dataset": batch.dataset,
        "source": batch.source,
        "source_version": batch.source_version,
        "request": batch.request,
        "rows": len(batch.records),
        "hash": digest,
        "path": str(path.resolve()),
        "semantic_hash": semantic_hash,
        "created": created,
    }


def _source_exception(error: BaseException) -> tuple[str, bool]:
    from .sources import RetryableSourceError, SourceBlocked, SourceError, TerminalSourceError

    if isinstance(error, SourceBlocked):
        return "blocked", True
    if isinstance(error, RetryableSourceError):
        return "retryable", True
    if isinstance(error, TerminalSourceError):
        return "terminal", False
    if isinstance(error, SourceError):
        return "terminal", False
    return "unexpected", True


def _collect_online(
    root: Path,
    db: Path,
    store: StateStore,
    now: datetime,
    sources: tuple[Any, Any] | None,
    snapshot_store: Any | None,
) -> tuple[list[dict], list[dict], list[str], int]:
    now_utc = now.astimezone(timezone.utc).isoformat()
    recovered_expired = store.recover_expired_leases(now_utc)
    bao, ak = sources if sources is not None else _default_sources()
    snapshots = snapshot_store if snapshot_store is not None else _default_snapshot_store(root)
    market_date = _latest_completed_market_date(now)
    tasks: list[tuple[str, str, Callable[[], Any]]] = [
        ("baostock", "security_master", bao.fetch_security_master),
        ("baostock", "trade_dates", lambda: bao.fetch_trade_dates("2026-08-24", market_date)),
        ("akshare", "disclosure_schedule", ak.fetch_disclosure_schedule),
        ("akshare", "performance_report", ak.fetch_performance_report),
    ]
    batches: list[dict] = []
    errors: list[dict] = []
    circuit_breakers: set[str] = set()
    attempt_date = now.date().isoformat()

    def cached_job_result(source: str, dataset: str, job_id: str) -> list[dict]:
        job = store.get_job(job_id)
        if job is None:
            return [{"source": source, "dataset": dataset, "status": "pending", "job_id": job_id}]
        if job["status"] == "succeeded" and job.get("result"):
            prior_batches = list(job["result"].get("batches", []))
            if prior_batches:
                return [
                    {"source": source, "status": "succeeded", "cached": True, **item}
                    for item in prior_batches
                ]
        result = {
            "source": source,
            "dataset": dataset,
            "status": job["status"],
            "job_id": job_id,
            "cached": False,
        }
        if job.get("error") is not None:
            result["error"] = job["error"]
        if job.get("next_retry_at") is not None:
            result["next_retry_at"] = job["next_retry_at"]
        if job.get("lease_expires_at") is not None:
            result["lease_expires_at"] = job["lease_expires_at"]
        return [result]

    for source, dataset, collect in tasks:
        if source in circuit_breakers:
            batches.append({"source": source, "dataset": dataset, "status": "circuit_open"})
            continue
        kind = f"fetch_source:{source}:{dataset}:{attempt_date}"
        job_id = store.enqueue_job(kind, kind, {"source": source, "dataset": dataset, "attempt_date": attempt_date})
        leased = store.lease_next_job([kind], "orchestrator", 900, now_utc)
        if leased is None:
            cached = cached_job_result(source, dataset, job_id)
            batches.extend(cached)
            for item in cached:
                cached_error = item.get("error")
                if not isinstance(cached_error, dict) or cached_error.get("classification") != "blocked":
                    continue
                issue = {
                    "source": source,
                    "dataset": dataset,
                    "classification": "blocked",
                    "error": str(cached_error.get("error") or "cached source block"),
                    "cached": True,
                }
                errors.append(issue)
                circuit_breakers.add(source)
            continue
        try:
            collected = collect()
            items = list(collected.values()) if isinstance(collected, dict) else [collected]
            persisted = [_persist_batch(root, db, store, snapshots, item) for item in items]
            store.complete_job(job_id, {"batches": persisted})
            batches.extend({"source": source, "status": "succeeded", **item} for item in persisted)
        except Exception as error:
            classification, retryable = _source_exception(error)
            retry_at = (now + timedelta(hours=1)).astimezone(timezone.utc).isoformat() if retryable else None
            store.fail_job(job_id, {"classification": classification, "error": str(error)}, retryable, retry_at)
            issue = {
                "source": source,
                "dataset": dataset,
                "classification": classification,
                "error": str(error),
            }
            errors.append(issue)
            batches.append({**issue, "status": "retryable_failed" if retryable else "terminal_failed"})
            if classification == "blocked":
                circuit_breakers.add(source)
    return batches, errors, sorted(circuit_breakers), recovered_expired


def _curated_document(
    path: Path,
    generated_at: str,
    input_hashes: dict,
    records: list[dict],
    metrics: dict,
    *,
    preserve_if_inputs_equal: bool = True,
    preserve_if_records_equal: bool = False,
) -> dict:
    existing = _read_json(path)
    existing_inputs = existing.get("input_hashes", {}) if existing else {}
    rules_current = bool(
        existing
        and existing.get("schema_version") == CURATED_SCHEMA_VERSION
        and existing_inputs.get("curation_schema_version") == CURATED_SCHEMA_VERSION
        and existing_inputs.get("curation_ruleset_hash") == CURATION_RULESET_HASH
    )
    if (
        preserve_if_records_equal
        and rules_current
        and existing.get("records_hash") == _hash(records)
    ):
        return existing
    if (
        preserve_if_inputs_equal
        and rules_current
        and existing.get("input_hashes") == input_hashes
    ):
        return existing
    document = {
        "schema_version": CURATED_SCHEMA_VERSION,
        "generated_at_utc": generated_at,
        "input_hashes": input_hashes,
        "records_hash": _hash(records),
        "records": records,
        "metrics": metrics,
    }
    _atomic_write_json(path, document)
    return document


def _curation_inputs(values: dict) -> dict:
    return {
        "curation_schema_version": CURATED_SCHEMA_VERSION,
        "curation_ruleset_hash": CURATION_RULESET_HASH,
        **values,
    }


def _merge_late_revision_replacements(
    path: Path,
    current_cutoff_records: list[dict],
    observed_records: list[dict],
    metrics: dict,
) -> tuple[list[dict], dict]:
    """Carry the prior cutoff row when a latest-only source replaces it after cutoff."""

    existing = _read_json(path)
    existing_inputs = existing.get("input_hashes", {}) if existing else {}
    existing_records = existing.get("records", []) if existing else []
    trustworthy = bool(
        existing
        and existing.get("schema_version") == CURATED_SCHEMA_VERSION
        and existing_inputs.get("curation_schema_version") == CURATED_SCHEMA_VERSION
        and existing_inputs.get("curation_ruleset_hash") == CURATION_RULESET_HASH
        and existing_inputs.get("cutoff_cn") == CUTOFF_CN.isoformat()
        and isinstance(existing_records, list)
        and existing.get("records_hash") == _hash(existing_records)
    )
    if not trustworthy:
        return current_cutoff_records, metrics

    cutoff_ids = {
        str(row.get("security_id")) for row in current_cutoff_records if row.get("security_id")
    }
    observed_ids = {str(row.get("security_id")) for row in observed_records if row.get("security_id")}
    late_replacement_ids = observed_ids - cutoff_ids
    existing_by_id = {
        str(row.get("security_id")): row
        for row in existing_records
        if isinstance(row, dict) and row.get("security_id")
    }
    carried = [
        existing_by_id[security_id]
        for security_id in sorted(late_replacement_ids)
        if security_id in existing_by_id
    ]
    if not carried:
        return current_cutoff_records, metrics

    merged = [*current_cutoff_records, *carried]
    merged.sort(key=lambda row: str(row.get("security_id", "")))
    available = sum(row.get(field) is not None for row in merged for field in CORE_FIELDS)
    denominator = len(merged) * len(CORE_FIELDS)
    dates = [row.get("announcement_date") for row in merged if row.get("announcement_date")]
    merged_metrics = {
        **metrics,
        "disclosed_unique_count": len(merged),
        "core_field_completeness": available / denominator if denominator else 0.0,
        "latest_announcement_date": max(dates, default=None),
        "carried_forward_cutoff_security_count": len(carried),
    }
    return merged, merged_metrics


def _rebuild_curated(root: Path, db: Path, now: datetime) -> dict[str, dict]:
    security_row = _snapshot_row(db, "baostock", "security_master")
    performance_row = _snapshot_row(db, "akshare", "performance_report")
    security_document = _snapshot_document(security_row, root)
    performance_document = _snapshot_document(performance_row, root)
    if security_document is None or performance_document is None:
        return {}

    generated_at = now.astimezone(timezone.utc).isoformat()
    curated_dir = root / "curated"
    universe, universe_metrics = curate_universe(list(security_document.get("records", [])))
    universe_inputs = _curation_inputs({"security_master": security_row["payload_hash"]})
    universe_document = _curated_document(
        curated_dir / "universe.json", generated_at, universe_inputs, universe, universe_metrics
    )

    raw_performance = list(performance_document.get("records", []))
    performance, performance_metrics = curate_performance(
        raw_performance, universe, cutoff_cn=CUTOFF_CN.isoformat()
    )
    observed: list[dict] | None = None
    observed_metrics: dict | None = None
    if performance_metrics["post_cutoff_observation_rows"]:
        observed, observed_metrics = curate_performance(raw_performance, universe)
        performance, performance_metrics = _merge_late_revision_replacements(
            curated_dir / "performance.json", performance, observed, performance_metrics
        )
    performance_metrics.update(
        {"frozen_cutoff": True, "observation_mode": "official_cutoff", "is_official_score": False}
    )
    performance_inputs = _curation_inputs({
        "security_master": security_row["payload_hash"],
        "performance_report": performance_row["payload_hash"],
        "cutoff_cn": CUTOFF_CN.isoformat(),
    })
    performance_document_out = _curated_document(
        curated_dir / "performance.json",
        generated_at,
        performance_inputs,
        performance,
        performance_metrics,
        preserve_if_records_equal=True,
    )

    candidates, prefilter_metrics = build_prefilter(performance)
    prefilter_inputs = {
        **performance_document_out["input_hashes"],
        "prefilter_ruleset_hash": PREFILTER_RULESET_HASH,
    }
    prefilter_document = _curated_document(
        curated_dir / "prefilter.json",
        generated_at,
        prefilter_inputs,
        candidates,
        prefilter_metrics,
    )

    if observed is not None and observed_metrics is not None:
        observed_metrics.update(
            {
                "frozen_cutoff": False,
                "observation_mode": "post_cutoff_provisional",
                "is_official_score": False,
            }
        )
        _curated_document(
            curated_dir / "performance_post_cutoff.json",
            generated_at,
            _curation_inputs(
                {
                    "security_master": security_row["payload_hash"],
                    "performance_report": performance_row["payload_hash"],
                    "view": "post_cutoff_provisional",
                }
            ),
            observed,
            observed_metrics,
        )

    quality = quality_gate(universe, performance, now.isoformat())
    quality.update(
        {
            "outside_universe_rows": performance_metrics["outside_universe_rows"],
            "source_duplicate_security_count": performance_metrics["duplicate_security_count"],
            "source_duplicate_row_count": performance_metrics["duplicate_row_count"],
            "post_cutoff_observation_rows": performance_metrics["post_cutoff_observation_rows"],
            "post_cutoff_security_count": performance_metrics["post_cutoff_security_count"],
            "source_announcement_timestamp_missing_rows": performance_metrics[
                "announcement_timestamp_missing_rows"
            ],
            "source_announcement_timestamp_unparseable_rows": performance_metrics[
                "announcement_timestamp_unparseable_rows"
            ],
        }
    )
    if (
        performance_metrics["announcement_timestamp_missing_rows"]
        or performance_metrics["announcement_timestamp_unparseable_rows"]
    ) and now > CUTOFF_CN:
        quality["data_quality_passed"] = False
        quality["status"] = "failed"
    quality_document = _curated_document(
        root / "status" / "quality.json",
        generated_at,
        {**performance_inputs, "as_of_cn": now.isoformat()},
        [],
        quality,
        preserve_if_inputs_equal=False,
    )
    return {
        "universe": universe_document,
        "performance": performance_document_out,
        "prefilter": prefilter_document,
        "quality": quality_document,
    }


def _performance_input_hash(row: dict) -> str:
    return _hash(row)


def _formal_feature_coverage(candidate: dict) -> float:
    feature_map = candidate.get("formal_features")
    if not isinstance(feature_map, dict):
        return 0.0
    available = sum(feature_map.get(feature) is not None for feature in FORMAL_FEATURES)
    return available / len(FORMAL_FEATURES)


def _enqueue_deep_and_partial_scores(store: StateStore, curated: dict[str, dict], now: datetime) -> None:
    if not curated:
        return
    performance_by_id = {
        row["security_id"]: row for row in curated["performance"].get("records", []) if row.get("security_id")
    }
    candidates = curated["prefilter"].get("records", [])
    for candidate in candidates:
        security_id = str(candidate["security_id"])
        source_row = performance_by_id[security_id]
        input_hash = _performance_input_hash(source_row)
        store.enqueue_job(
            "deep_financial",
            f"deep_financial:{security_id}:{input_hash}",
            {"security_id": security_id, "input_hash": input_hash, "report_period": "2026-06-30"},
        )

    scoring_input_hash = _hash(curated["performance"].get("input_hashes", {}))
    with closing(sqlite3.connect(store.db_path)) as connection:
        existing = connection.execute(
            """SELECT id FROM score_run WHERE status = 'provisional' AND ruleset_hash = ?
            AND universe_hash = ? ORDER BY created_at DESC LIMIT 1""",
            (RULESET_HASH, scoring_input_hash),
        ).fetchone()
    score_run_id = existing[0] if existing else store.create_score_run(
        "2026-06-30", now.isoformat(), RULESET_HASH, scoring_input_hash, "incremental"
    )
    for candidate in candidates:
        security_id = str(candidate["security_id"])
        input_hash = _performance_input_hash(performance_by_id[security_id])
        store.upsert_score_item(
            score_run_id,
            security_id,
            "partial",
            _formal_feature_coverage(candidate),
            input_hash,
            None,
            [PREFILTER_REASON, "缺少V2七维特征、正文风险核验与2026-08-31收盘估值"],
        )


def _curated_metrics(root: Path) -> dict[str, dict]:
    paths = {
        "universe": root / "curated" / "universe.json",
        "performance": root / "curated" / "performance.json",
        "prefilter": root / "curated" / "prefilter.json",
        "quality": root / "status" / "quality.json",
    }
    result: dict[str, dict] = {}
    for name, path in paths.items():
        document = _read_json(path)
        if document is not None:
            result[name] = document.get("metrics", {})
    return result


def _status_payload(
    root: Path,
    store: StateStore,
    now: datetime,
    command: str,
    mode: str,
    *,
    pipeline_state: str | None = None,
    source_batches: list[dict] | None = None,
    source_errors: list[dict] | None = None,
    circuit_breakers: list[str] | None = None,
    blocked_reasons: list[str] | None = None,
    recovered_expired_leases: int = 0,
) -> dict:
    curated = _curated_metrics(root)
    if pipeline_state is None:
        pipeline_state = str(curated.get("quality", {}).get("status", "pending"))
    return {
        "schema_version": SCHEMA_VERSION,
        "command": command,
        "mode": mode,
        "pipeline_state": pipeline_state,
        "generated_at_utc": now.astimezone(timezone.utc).isoformat(),
        "state": store.progress_snapshot(),
        "curated": curated,
        "source_batches": source_batches or [],
        "source_errors": source_errors or [],
        "circuit_breakers": circuit_breakers or [],
        "blocked_reasons": blocked_reasons or [],
        "recovered_expired_leases": recovered_expired_leases,
        "next_actions": [
            "继续增量采集披露变化和候选完整三表",
            "2026-08-31收盘后补齐行情证据",
            "七维正式特征和财报正文风险核验完成前不得冻结股票池",
        ],
    }


def _market_security_id(record: dict, universe_by_code: dict[str, str]) -> str | None:
    security_id = str(record.get("security_id", "")).upper().strip()
    if re.fullmatch(r"(?:SH|SZ)\d{6}", security_id):
        return security_id
    code = str(record.get("code", record.get("code6", ""))).strip().lower()
    if re.fullmatch(r"sh\.\d{6}", code):
        return "SH" + code[3:]
    if re.fullmatch(r"sz\.\d{6}", code):
        return "SZ" + code[3:]
    if re.fullmatch(r"\d{6}", code):
        return universe_by_code.get(code)
    return None


def _nonempty_number(value: object) -> bool:
    if value is None or isinstance(value, bool):
        return False
    if isinstance(value, str) and not value.strip():
        return False
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return not math.isnan(number) and not math.isinf(number)


def _verified_market_snapshot(root: Path, db: Path, digest: str) -> dict | None:
    with closing(sqlite3.connect(db)) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """SELECT source, dataset, payload_hash, payload_path, row_count, fetched_at
            FROM source_snapshot WHERE payload_hash = ? AND dataset IN ('daily','spot_snapshot')
            ORDER BY created_at DESC LIMIT 1""",
            (digest,),
        ).fetchone()
    if row is None:
        return None
    document = _snapshot_document(dict(row), root)
    if document is None:
        return None
    try:
        from .sources import FetchBatch

        verified = FetchBatch(
            document["source"],
            document["dataset"],
            document["request"],
            document["records"],
            document["fetched_at_utc"],
            document["source_version"],
            document["metadata"],
        )
    except (KeyError, TypeError, ValueError):
        return None
    return document if verified.sha256() == digest else None


def _market_ready(root: Path, db: Path, universe: list[dict]) -> tuple[bool, dict]:
    evidence = _read_json(root / "curated" / "market_2026-08-31.json")
    errors: list[str] = []
    if evidence is None:
        return False, {
            "date": "2026-08-31",
            "record_count": 0,
            "coverage_rate": 0.0,
            "validation_errors": ["market_evidence_missing"],
        }

    if evidence.get("schema_version") != CURATED_SCHEMA_VERSION:
        errors.append("market_schema_stale")
    if evidence.get("date") != "2026-08-31":
        errors.append("market_wrong_date")
    input_hashes = evidence.get("input_hashes") if isinstance(evidence.get("input_hashes"), dict) else {}
    expected_universe_hash = _hash(universe)
    if input_hashes.get("universe_records") != expected_universe_hash:
        errors.append("market_universe_hash_mismatch")
    declared_hashes = input_hashes.get("source_snapshots")
    if not isinstance(declared_hashes, list) or not declared_hashes:
        declared_hashes = []
        errors.append("market_snapshot_hash_unverified")

    verified_documents: list[dict] = []
    for digest in declared_hashes:
        document = _verified_market_snapshot(root, db, str(digest))
        if document is None:
            if "market_snapshot_hash_unverified" not in errors:
                errors.append("market_snapshot_hash_unverified")
        else:
            verified_documents.append(document)
    backed_record_hashes = {
        _hash(record)
        for document in verified_documents
        for record in document.get("records", [])
        if isinstance(record, dict)
    }

    records = evidence.get("records") if isinstance(evidence.get("records"), list) else []
    if any(not isinstance(record, dict) or _hash(record) not in backed_record_hashes for record in records):
        errors.append("market_records_not_backed_by_snapshot")
    universe_ids = {str(row.get("security_id", "")) for row in universe if row.get("security_id")}
    universe_by_code = {
        str(row.get("code6", "")): str(row.get("security_id", "")) for row in universe if row.get("code6")
    }
    security_ids = [
        _market_security_id(record, universe_by_code) if isinstance(record, dict) else None
        for record in records
    ]
    recognized_ids = [security_id for security_id in security_ids if security_id is not None]
    if len(recognized_ids) != len(set(recognized_ids)):
        errors.append("market_duplicate_security")
    outside_ids = {security_id for security_id in recognized_ids if security_id not in universe_ids}
    if outside_ids or any(security_id is None for security_id in security_ids):
        errors.append("market_outside_universe")
    covered_ids = set(recognized_ids) & universe_ids
    if covered_ids != universe_ids:
        errors.append("market_incomplete_universe")

    effective_prices: list[dict] = []
    for record, security_id in zip(records, security_ids):
        if not isinstance(record, dict):
            continue
        if str(record.get("date", "")) != "2026-08-31":
            if "market_wrong_date" not in errors:
                errors.append("market_wrong_date")
        trade_status = str(record.get("tradestatus", "")).strip().lower()
        suspended = trade_status in {"0", "false", "停牌"}
        active = trade_status in {"1", "true", "交易", "正常", "active"}
        if not (suspended or active):
            errors.append("market_invalid_tradestatus")
            continue
        if active and _nonempty_number(record.get("close")):
            effective_prices.append(
                {
                    "security_id": security_id,
                    "effective_close": float(record["close"]),
                    "price_basis": "close",
                    "raw_record_hash": _hash(record),
                    "transformation_version": MARKET_PRICE_TRANSFORMATION_VERSION,
                }
            )
            continue
        if active or not _nonempty_number(record.get("preclose")):
            errors.append("market_missing_close")
            continue
        effective_prices.append(
            {
                "security_id": security_id,
                "effective_close": float(record["preclose"]),
                "price_basis": "suspended_preclose",
                "raw_record_hash": _hash(record),
                "transformation_version": MARKET_PRICE_TRANSFORMATION_VERSION,
            }
        )

    errors = list(dict.fromkeys(errors))
    summary = {
        "date": evidence.get("date"),
        "record_count": len(records),
        "universe_count": len(universe_ids),
        "covered_universe_count": len(covered_ids),
        "coverage_rate": len(covered_ids) / len(universe_ids) if universe_ids else 0.0,
        "universe_hash": input_hashes.get("universe_records"),
        "source_snapshot_hashes": declared_hashes,
        "price_transformation_version": MARKET_PRICE_TRANSFORMATION_VERSION,
        "effective_prices": effective_prices,
        "validation_errors": errors,
    }
    return not errors, summary


def _finalize(root: Path, store: StateStore, now: datetime) -> tuple[list[str], dict]:
    prior_quality_document = _read_json(root / "status" / "quality.json") or {}
    prior_quality = dict(prior_quality_document.get("metrics", {}))
    rebuilt = _rebuild_curated(root, store.db_path, now)
    universe_document = _read_json(root / "curated" / "universe.json") or {}
    performance_document = _read_json(root / "curated" / "performance.json") or {}
    universe = list(universe_document.get("records", []))
    performance = list(performance_document.get("records", []))
    rebuilt_quality = dict(rebuilt.get("quality", {}).get("metrics", {}))
    quality = {**prior_quality, **rebuilt_quality, **quality_gate(universe, performance, now.isoformat())}
    if (
        quality.get("source_announcement_timestamp_missing_rows", 0)
        or quality.get("source_announcement_timestamp_unparseable_rows", 0)
    ):
        quality["data_quality_passed"] = False
    market_ready, market_evidence = _market_ready(root, store.db_path, universe)
    reasons: list[str] = []
    if now <= CUTOFF_CN:
        reasons.append("cutoff_not_passed")
    if not quality["data_quality_passed"] and now > CUTOFF_CN:
        reasons.append("quality_gate_failed")
    if not market_ready:
        reasons.append("market_2026_08_31_missing")
    reasons.append("formal_v2_scores_unavailable")
    if now <= CUTOFF_CN:
        quality["status"] = "partial"
    elif quality["data_quality_passed"] and market_ready:
        quality["status"] = "passed"
    else:
        quality["status"] = "failed"
    quality.update(
        {
            "market_ready": market_ready,
            "market_evidence": market_evidence,
            "market_validation_errors": market_evidence.get("validation_errors", []),
            "formal_score_ready": False,
        }
    )
    _curated_document(
        root / "status" / "quality.json",
        now.astimezone(timezone.utc).isoformat(),
        {**performance_document.get("input_hashes", {}), "as_of_cn": now.isoformat()},
        [],
        quality,
        preserve_if_inputs_equal=False,
    )
    return reasons, quality


def run_command(
    root: str | Path,
    db: str | Path,
    command: str,
    *,
    online: bool = False,
    now_cn: str | None = None,
    sources: tuple[Any, Any] | None = None,
    snapshot_store: Any | None = None,
) -> tuple[dict, int]:
    root_path = Path(root).resolve()
    db_path = Path(db).resolve()
    now = _now_cn(now_cn)
    store = StateStore(db_path)
    store.initialize()

    if command == "status":
        payload = _status_payload(root_path, store, now, command, "status")
        _atomic_write_json(root_path / "status" / "pipeline_status.json", payload)
        return payload, 0

    run_id = store.start_run(command, now.isoformat(), {"online": online})

    def write_then_finish(payload: dict, terminal_status: str, error: str | None = None) -> None:
        recent = payload.get("state", {}).get("recent_run")
        if isinstance(recent, dict) and recent.get("id") == run_id:
            recent["status"] = terminal_status
            recent["finished_at"] = now.astimezone(timezone.utc).isoformat()
        _atomic_write_json(root_path / "status" / "pipeline_status.json", payload)
        store.finish_run(run_id, terminal_status, error)

    try:
        if command == "finalize":
            reasons, _ = _finalize(root_path, store, now)
            payload = _status_payload(
                root_path,
                store,
                now,
                command,
                "offline",
                pipeline_state="blocked",
                blocked_reasons=reasons,
            )
            error = ",".join(reasons)
            write_then_finish(payload, "failed", error)
            return payload, 2

        if command not in {"bootstrap", "incremental"}:
            raise ValueError(f"unknown command: {command}")

        if not online:
            payload = _status_payload(
                root_path, store, now, command, "offline", pipeline_state="pending"
            )
            write_then_finish(payload, "succeeded")
            return payload, 0

        source_batches, source_errors, circuit_breakers, recovered_expired = _collect_online(
            root_path, db_path, store, now, sources, snapshot_store
        )
        curated = _rebuild_curated(root_path, db_path, now)
        _enqueue_deep_and_partial_scores(store, curated, now)
        payload = _status_payload(
            root_path,
            store,
            now,
            command,
            "online",
            source_batches=source_batches,
            source_errors=source_errors,
            circuit_breakers=circuit_breakers,
            recovered_expired_leases=recovered_expired,
        )
        write_then_finish(payload, "succeeded")
        return payload, 0
    except BaseException as original_error:
        try:
            store.finish_run(
                run_id,
                "failed",
                f"{type(original_error).__name__}: {original_error}",
            )
        except BaseException:
            pass
        raise


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--db", required=True)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("bootstrap", "incremental"):
        child = subparsers.add_parser(command)
        child.add_argument("--online", action="store_true")
    subparsers.add_parser("status")
    finalize = subparsers.add_parser("finalize")
    finalize.add_argument("--now-cn", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    payload, exit_code = run_command(
        arguments.root,
        arguments.db,
        arguments.command,
        online=bool(getattr(arguments, "online", False)),
        now_cn=getattr(arguments, "now_cn", None),
    )
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
