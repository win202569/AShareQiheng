import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Mapping

from ashare_pipeline.deep_worker import STATEMENT_DATASETS
from ashare_pipeline.feature_contract import canonical_json_bytes, canonical_sha256
from ashare_pipeline.sources import FetchBatch
from ashare_pipeline.state_store import StateStore


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "financial"


def _fetch_batch(document: Mapping[str, object]) -> FetchBatch:
    return FetchBatch(
        str(document["source"]),
        str(document["dataset"]),
        dict(document["request"]),
        list(document["records"]),
        str(document["fetched_at_utc"]),
        str(document["source_version"]),
        dict(document["metadata"]),
    )


def load_calendar_fixture(name: str) -> FetchBatch:
    document = json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))
    batch = _fetch_batch(document)
    if batch.dataset != "trade_dates":
        raise AssertionError("calendar fixture must be trade_dates")
    return batch


def load_statement_fixture_batches(
    candidates: Mapping[str, str],
    fixture_names: Mapping[str, str],
) -> dict[tuple[str, str], FetchBatch]:
    result: dict[tuple[str, str], FetchBatch] = {}
    for security_id in sorted(candidates):
        document = json.loads(
            (FIXTURE_ROOT / fixture_names[security_id]).read_text(encoding="utf-8")
        )
        if (
            security_id == "SH600002"
            and fixture_names[security_id] == "real_estate_statements.json"
        ):
            if document["security_id"] != "SZ000002":
                raise AssertionError("real-estate fixture alias source mismatch")
            document["security_id"] = "SH600002"
            for dataset in STATEMENT_DATASETS:
                request = document["batches"][dataset]["request"]
                if request.get("symbol") != "SZ000002":
                    raise AssertionError("real-estate fixture request alias mismatch")
                request["symbol"] = "SH600002"
        if document["security_id"] != security_id:
            raise AssertionError("fixture security mismatch")
        if set(document["batches"]) != set(STATEMENT_DATASETS):
            raise AssertionError("fixture must define all three statement batches")
        for dataset in STATEMENT_DATASETS:
            batch = _fetch_batch(document["batches"][dataset])
            expected_request = {
                "symbol": security_id,
                "report_period": "2026-06-30",
            }
            if batch.dataset != dataset or batch.request != expected_request:
                raise AssertionError("fixture request mismatch")
            result[(security_id, dataset)] = batch
    return result


def write_candidate_fixture_documents(
    data_root: Path,
    candidates: Mapping[str, str],
) -> None:
    records = [
        {
            "security_id": security_id,
            "industry": candidates[security_id],
            "announcement_date": "2026-08-29",
            "report_period": "2026-06-30",
        }
        for security_id in sorted(candidates)
    ]
    performance = {
        "schema_version": 2,
        "input_hashes": {"fixture_records": canonical_sha256(records)},
        "records_hash": canonical_sha256(records),
        "records": records,
    }
    prefilter_records = [
        {"security_id": row["security_id"], "industry": row["industry"]}
        for row in records
    ]
    prefilter = {
        "schema_version": 2,
        "input_hashes": {"performance": canonical_sha256(performance)},
        "records_hash": canonical_sha256(prefilter_records),
        "records": prefilter_records,
    }
    for name, document in (("performance", performance), ("prefilter", prefilter)):
        path = data_root / "curated" / f"{name}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(canonical_json_bytes(document))


def enqueue_legacy_parent_fixtures(
    store: StateStore,
    candidates: Mapping[str, str],
) -> tuple[str, ...]:
    return tuple(
        store.enqueue_job(
            "deep_financial",
            f"fixture:deep_financial:{security_id}",
            {
                "security_id": security_id,
                "report_period": "2026-06-30",
                "input_hash": canonical_sha256(
                    {"security_id": security_id, "industry": candidates[security_id]}
                ),
            },
        )
        for security_id in sorted(candidates)
    )


def latest_feature_set_rows(
    store: StateStore,
    report_period: str,
    contract_version: str,
) -> list[dict[str, object]]:
    with closing(sqlite3.connect(store.db_path)) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """SELECT * FROM feature_set
            WHERE report_period=? AND contract_version=?
            ORDER BY security_id""",
            (report_period, contract_version),
        ).fetchall()
    return [dict(row) for row in rows]
