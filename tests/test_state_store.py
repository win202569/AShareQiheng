import copy
import hashlib
import json
import math
import sqlite3
import tempfile
import threading
import unittest
import uuid
from contextlib import closing
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Mapping
from unittest.mock import patch

import ashare_pipeline.state_store as state_store_module
from ashare_pipeline.feature_contract import (
    CONTRACT_VERSION,
    DIMENSIONS,
    FINANCIAL_DIMENSIONS,
    ConfidenceInputs,
    DimensionInput,
    EvidenceRef,
    FeatureBundle,
    FeatureValue,
    IndustryContext,
    canonical_sha256,
)
from ashare_pipeline.financial_schema import MAPPING_VERSION, FinancialFact
from ashare_pipeline.financial_features import feature_input_hash
from ashare_pipeline.formal_evidence import (
    EvidenceVerification,
    OfficialFetch,
    OfficialRequest,
    OfficialSnapshotRef,
    SourcePolicy,
    verify_official_fetch,
)
from ashare_pipeline.formal_snapshot_store import FormalSnapshotStore, FormalStoredSnapshot
from ashare_pipeline.formal_universe import (
    FormalFrozenUniverseInput,
    FormalUniverseIngestor,
    FormalUniverseSourceDocument,
    extract_formal_universe_members,
)
from ashare_pipeline.state_store import FinalizationBlocked, JobSpec, StateStore
from tests.test_financial_features import (
    build_bundle_with_overrides,
    complete_general_facts,
    rebuild_fact,
)
from tests.test_feature_contract import bundle_with_copied_financial_value


UTC = timezone.utc


def utc_at(seconds: int) -> str:
    return (datetime(2026, 8, 31, tzinfo=UTC) + timedelta(seconds=seconds)).isoformat()


def financial_fact(
    *, snapshot_id: str, raw_row_hash: str = "1" * 64, value: float = 100.0,
    effective_at_utc: str = "2026-08-21T07:00:00+00:00",
) -> FinancialFact:
    return FinancialFact.create(
        security_id="SH600001",
        statement="income",
        metric_key="revenue",
        period_start="2026-01-01",
        period_end="2026-06-30",
        period_kind="H1",
        value=value,
        unit="CNY",
        nature="duration",
        announced_at_utc="2026-08-20T15:59:59+00:00",
        effective_at_utc=effective_at_utc,
        source_updated_at_utc=None,
        source_snapshot_id=snapshot_id,
        source_field="TOTAL_OPERATE_INCOME",
        raw_row_hash=raw_row_hash,
        mapping_version=MAPPING_VERSION,
        created_at="2026-08-29T00:00:00+00:00",
    )


def historical_mapping_fact(fact: FinancialFact) -> FinancialFact:
    record = fact.to_record()
    record["mapping_version"] = "eastmoney-financial-mapping-v1"
    identity = dict(record)
    identity.pop("id")
    identity.pop("created_at")
    record["id"] = canonical_sha256(identity)
    return FinancialFact.from_record(record)


def valid_feature_bundle(
    *, input_hash: str = "b" * 64,
    as_of_utc: str = "2026-08-29T16:00:00+00:00",
    blockers: tuple[str, ...] = ("formal_industry_mapping_missing",),
) -> FeatureBundle:
    return replace(
        build_bundle_with_overrides(facts=()),
        input_hash=input_hash,
        as_of_utc=as_of_utc,
        blockers=blockers,
    )


def installed_ready_bundle(
    store: StateStore, **overrides: object
) -> tuple[FeatureBundle, tuple[FinancialFact, ...], dict[str, str]]:
    """Share the real evidence prerequisite without exporting a TestCase class."""
    return StateStoreTestCase.installed_ready_bundle(store, **overrides)


def written_formal_snapshot(
    root: Path,
    *,
    raw_bytes: bytes = b"%PDF-1.7 official bootstrap",
    refresh_generation: str = "bootstrap-v1",
    producing_task_id: str | None = None,
) -> tuple[FormalSnapshotStore, OfficialFetch, FormalStoredSnapshot, EvidenceVerification]:
    raw_store = FormalSnapshotStore(root)
    fetch = OfficialFetch(
        request=OfficialRequest(
            "cninfo", "annual_report", "SZ000001", "2025-12-31", "SZ"
        ),
        raw_bytes=raw_bytes,
        original_url="https://static.cninfo.com.cn/finalpage/2026-03-20/123.pdf",
        published_at_utc="2026-03-20T08:00:00+00:00",
        published_precision="timestamp",
        source_updated_at_utc=None,
        captured_at_utc="2026-09-04T08:00:00+00:00",
        effective_at_utc="2026-03-20T08:00:00+00:00",
        effective_time_evidence_hash=None,
        refresh_generation=refresh_generation,
        parser_id="cninfo-pdf",
        parser_version="cninfo-pdf-v1",
        mapping_version="cninfo-annual-v1",
        declared_security_id="SZ000001",
        declared_period="2025-12-31",
    )
    verification = verify_official_fetch(fetch, SourcePolicy.cninfo())
    if verification.status != "verified":
        raise AssertionError(verification)
    stored = raw_store.write_verified(
        fetch, verification, producing_task_id=producing_task_id
    )
    return raw_store, fetch, stored, verification


def forge_balance_semantics(
    bundle: FeatureBundle,
    *,
    status: str,
    include_mismatch_blocker: bool,
) -> FeatureBundle:
    forged = copy.copy(bundle)
    blockers = set(bundle.blockers)
    if include_mismatch_blocker:
        blockers.add("balance_equation_mismatch")
    else:
        blockers.discard("balance_equation_mismatch")
    dimensions = dict(bundle.dimension_inputs)
    dimension_status = "blocked" if status == "blocked" else status
    if dimension_status == "financial_ready":
        dimension_status = "input_ready"
    for dimension in FINANCIAL_DIMENSIONS:
        dimensions[dimension] = DimensionInput(
            dimension_status,
            bundle.dimension_inputs[dimension].values,
        )
    object.__setattr__(forged, "financial_status", status)
    object.__setattr__(forged, "blockers", tuple(sorted(blockers)))
    object.__setattr__(forged, "dimension_inputs", dimensions)
    forged.validate()
    return forged


def unsafe_materialize_feature_bundle(
    store: StateStore,
    bundle: FeatureBundle,
    *,
    bundle_path: str,
) -> str:
    """Create reviewed pre-fix state without invoking a production validator."""
    bundle_hash = bundle.bundle_hash()
    header, values = store._feature_bundle_content(bundle, bundle_hash)
    with closing(sqlite3.connect(store.db_path)) as connection:
        connection.execute(
            """INSERT INTO feature_set
            (id,security_id,report_period,as_of_utc,candidate_set_hash,
             template_id,template_version,contract_version,input_hash,status,
             financial_coverage,dimension_status_json,confidence_inputs_json,
             blockers_json,bundle_hash,bundle_path,missing_json,created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                bundle_hash,
                header["security_id"],
                header["report_period"],
                header["as_of_utc"],
                header["candidate_set_hash"],
                header["template_id"],
                header["template_version"],
                header["contract_version"],
                header["input_hash"],
                header["status"],
                header["financial_coverage"],
                header["dimension_status_json"],
                header["confidence_inputs_json"],
                header["blockers_json"],
                header["bundle_hash"],
                bundle_path,
                header["missing_json"],
                utc_at(99),
            ),
        )
        for value in values:
            connection.execute(
                """INSERT INTO feature_value
                (feature_set_id,dimension,feature_key,period_key,value,unit,status,
                 formula_version,evidence_json,missing_reason)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    bundle_hash,
                    value["dimension"],
                    value["feature_key"],
                    value["period_key"],
                    value["value"],
                    value["unit"],
                    value["status"],
                    value["formula_version"],
                    value["evidence_json"],
                    value["missing_reason"],
                ),
            )
        connection.commit()
    return bundle_hash


class StateStoreTestCase(unittest.TestCase):
    """Each test guards a durable public state-transition contract."""

    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "state.sqlite3"
        self.store = StateStore(self.db_path)
        self.store.initialize()
        self._reconciliation_case_index = 0

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def create_score_run(self) -> str:
        return self.store.create_score_run(
            "2026-06-30", "2026-08-31T08:00:00+08:00", "rules-v1", "universe-v1", "incremental"
        )

    def malformed_reconciliation_case(
        self, label: str, *, raw_row_hash: str | None = None
    ) -> dict[str, object]:
        self._reconciliation_case_index += 1
        refresh_at = (
            datetime(2026, 8, 1, 1, tzinfo=UTC)
            + timedelta(days=self._reconciliation_case_index)
        )
        refresh_date = refresh_at.date().isoformat()
        snapshot_hash = canonical_sha256({"reconciliation_snapshot": label})
        statement_request = {
            "symbol": "SH600001",
            "report_period": "2026-06-30",
        }
        snapshot_id, created = self.store.record_snapshot(
            "akshare",
            "profit_sheet",
            canonical_sha256(statement_request),
            snapshot_hash,
            f"data/raw/reconciliation-{label}.json",
            1,
            refresh_at.isoformat(),
        )
        self.assertTrue(created)
        calendar_request = {
            "start_date": "2021-01-01",
            "end_date": "2026-09-08",
        }
        calendar_hash = canonical_sha256({"reconciliation_calendar": label})
        calendar_id, calendar_created = self.store.record_snapshot(
            "baostock",
            "trade_dates",
            canonical_sha256(calendar_request),
            calendar_hash,
            f"data/raw/reconciliation-calendar-{label}.json",
            1,
            "2026-01-01T00:00:00+00:00",
        )
        self.assertTrue(calendar_created)
        payload = {
            "security_id": "SH600001",
            "dataset": "profit_sheet",
            "report_period": "2026-06-30",
            "candidate_set_hash": "a" * 64,
            "performance_input_hash": "b" * 64,
            "request_version": "eastmoney-financial-request-v1",
            "refresh_date": refresh_date,
        }
        idempotency_key = (
            "deep_statement:v1:SH600001:profit_sheet:2026-06-30:"
            f"{refresh_date}"
        )
        job_id = self.store.enqueue_job("deep_statement", idempotency_key, payload)
        worker_id = f"worker-{label}"
        self.store.lease_next_job(["deep_statement"], worker_id, 3600)
        fact = financial_fact(
            snapshot_id=snapshot_id,
            raw_row_hash=(
                raw_row_hash
                if raw_row_hash is not None
                else canonical_sha256({"reconciliation_row": label})
            ),
        )
        issue_details = {
            "security_id": "SH600001",
            "dataset": "profit_sheet",
            "details": {
                "security_id": "SH600001",
                "row_hash": fact.raw_row_hash,
            },
        }
        issue_id = self.store.record_quality_issue(
            run_id=None,
            score_run_id=None,
            severity="error",
            code="statement_report_date_invalid",
            details=issue_details,
            job_id=job_id,
            worker_id=worker_id,
            source_snapshot_id=snapshot_id,
        )
        self.store.fail_job_with_followups(
            job_id,
            worker_id,
            {"error_classification": "malformed_statement"},
            False,
            None,
            (),
        )
        statement_snapshots = {
            "balance_sheet": None,
            "profit_sheet": {
                "source_snapshot_id": snapshot_id,
                "payload_hash": snapshot_hash,
            },
            "cash_flow_sheet": None,
        }
        feature_payload = {
            "security_id": "SH600001",
            "report_period": "2026-06-30",
            "as_of_utc": "2026-08-31T16:00:00+00:00",
            "candidate_set_hash": "a" * 64,
            "industry": "包装印刷",
            "reported_target_period": True,
            "performance_input_hash": "b" * 64,
            "statement_snapshots": statement_snapshots,
            "trade_calendar_snapshot": {
                "source_snapshot_id": calendar_id,
                "payload_hash": calendar_hash,
                "source": "baostock",
                "dataset": "trade_dates",
                "request": calendar_request,
                "request_fingerprint": canonical_sha256(calendar_request),
            },
        }
        input_hash = feature_input_hash(
            security_id="SH600001",
            report_period="2026-06-30",
            as_of_utc=feature_payload["as_of_utc"],
            candidate_set_hash=feature_payload["candidate_set_hash"],
            statement_snapshot_hashes={
                dataset: (
                    value["payload_hash"] if value is not None else None
                )
                for dataset, value in statement_snapshots.items()
            },
            trade_calendar_snapshot_hash=calendar_hash,
        )
        followup = JobSpec(
            "feature_build",
            f"feature_build:v1:SH600001:2026-06-30:{input_hash}",
            feature_payload,
        )
        result = {
            "outcome": "reconciled_verified_snapshot",
            "snapshot_hash": snapshot_hash,
            "mapping_version": MAPPING_VERSION,
            "recovered_error": "malformed_statement",
        }
        return {
            "snapshot_hash": snapshot_hash,
            "snapshot_id": snapshot_id,
            "payload": payload,
            "idempotency_key": idempotency_key,
            "job_id": job_id,
            "fact": fact,
            "issue_id": issue_id,
            "issue_details": issue_details,
            "calendar_id": calendar_id,
            "calendar_hash": calendar_hash,
            "calendar_request": calendar_request,
            "snapshot_fetched_at": refresh_at.isoformat(),
            "followup": followup,
            "result": result,
        }

    def reconciliation_followup(
        self,
        case: Mapping[str, object],
        *,
        statement_snapshots: Mapping[str, object] | None = None,
        trade_calendar_snapshot: object = ...,
    ) -> JobSpec:
        payload = copy.deepcopy(case["followup"].payload)
        if statement_snapshots is not None:
            payload["statement_snapshots"] = copy.deepcopy(statement_snapshots)
        if trade_calendar_snapshot is not ...:
            payload["trade_calendar_snapshot"] = copy.deepcopy(
                trade_calendar_snapshot
            )
        calendar = payload["trade_calendar_snapshot"]
        input_hash = feature_input_hash(
            security_id=payload["security_id"],
            report_period=payload["report_period"],
            as_of_utc=payload["as_of_utc"],
            candidate_set_hash=payload["candidate_set_hash"],
            statement_snapshot_hashes={
                dataset: (
                    value["payload_hash"] if value is not None else None
                )
                for dataset, value in payload["statement_snapshots"].items()
            },
            trade_calendar_snapshot_hash=(
                calendar["payload_hash"] if calendar is not None else None
            ),
        )
        return JobSpec(
            "feature_build",
            f"feature_build:v1:{payload['security_id']}:{payload['report_period']}:{input_hash}",
            payload,
        )

    def add_succeeded_reconciliation_sibling(
        self,
        case: Mapping[str, object],
        dataset: str,
        *,
        label: str,
        outcome: str = "statement_persisted",
    ) -> tuple[dict[str, str], str]:
        statement_payload = dict(case["payload"])
        statement_payload["dataset"] = dataset
        statement_key = (
            f"deep_statement:v1:{statement_payload['security_id']}:{dataset}:"
            f"{statement_payload['report_period']}:{statement_payload['refresh_date']}"
        )
        snapshot_hash = canonical_sha256(
            {"reconciliation_sibling": label, "dataset": dataset}
        )
        statement_request = {
            "symbol": statement_payload["security_id"],
            "report_period": statement_payload["report_period"],
        }
        snapshot_id, created = self.store.record_snapshot(
            "akshare",
            dataset,
            canonical_sha256(statement_request),
            snapshot_hash,
            f"data/raw/reconciliation-sibling-{label}-{dataset}.json",
            1,
            case["snapshot_fetched_at"],
        )
        self.assertTrue(created)
        sibling_job_id = self.store.enqueue_job(
            "deep_statement", statement_key, statement_payload
        )
        sibling_worker = f"sibling-{label}-{dataset}"
        self.store.lease_next_job(["deep_statement"], sibling_worker, 3600)
        if outcome == "reconciled_verified_snapshot":
            result = {
                "outcome": outcome,
                "snapshot_hash": snapshot_hash,
                "mapping_version": MAPPING_VERSION,
                "recovered_error": "malformed_statement",
            }
        else:
            result = {"outcome": outcome, "snapshot_hash": snapshot_hash}
        self.store.complete_job_with_followups(
            sibling_job_id, sibling_worker, result, ()
        )
        return {
            "source_snapshot_id": snapshot_id,
            "payload_hash": snapshot_hash,
        }, sibling_job_id

    @staticmethod
    def reconciliation_arguments(
        case: Mapping[str, object],
        *,
        followup: JobSpec | None = None,
        issue_id: str | None = None,
        issue_details: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        return {
            "expected_idempotency_key": case["idempotency_key"],
            "expected_payload": case["payload"],
            "expected_quality_issue_id": issue_id or case["issue_id"],
            "expected_quality_issue_details": issue_details or case["issue_details"],
            "source_snapshot_id": case["snapshot_id"],
            "source_snapshot_hash": case["snapshot_hash"],
            "facts": (case["fact"],),
            "followup": followup or case["followup"],
            "result": case["result"],
        }

    @staticmethod
    def evidence_for_fact(fact: FinancialFact) -> EvidenceRef:
        return EvidenceRef(
            fact.id,
            fact.source_snapshot_id,
            fact.source_field,
            fact.raw_row_hash,
            fact.announced_at_utc,
            fact.effective_at_utc,
        )

    def stored_evidence_bundle(self, **overrides: object) -> FeatureBundle:
        snapshot_id, _created = self.store.record_snapshot(
            "akshare", "profit_sheet", canonical_sha256({"fixture": "sample"}),
            "a" * 64, "data/raw/sample.json", 1, utc_at(0),
        )
        fact = financial_fact(snapshot_id=snapshot_id)
        self.store.insert_financial_facts((fact,))
        return replace(build_bundle_with_overrides(facts=(fact,)), **overrides)

    @staticmethod
    def installed_ready_bundle(
        store: StateStore,
        *,
        security_id: str = "SH600001",
        snapshot_tag: str = "current",
        **overrides: object,
    ) -> tuple[FeatureBundle, tuple[FinancialFact, ...], dict[str, str]]:
        fact_values = dict(overrides.pop("fact_values", {}))
        omitted_slots = set(overrides.pop("omit_fact_slots", ()))
        dataset_by_statement = {
            "income": "profit_sheet",
            "balance": "balance_sheet",
            "cash_flow": "cash_flow_sheet",
        }
        snapshot_ids: dict[str, str] = {}
        snapshot_hashes: dict[str, str] = {}
        for index, (statement, dataset) in enumerate(
            dataset_by_statement.items(), start=1
        ):
            payload_hash = canonical_sha256(
                {"fixture": snapshot_tag, "dataset": dataset}
            )
            snapshot_id, _created = store.record_snapshot(
                "akshare",
                dataset,
                canonical_sha256(
                    {"symbol": security_id, "tag": snapshot_tag, "dataset": dataset}
                ),
                payload_hash,
                f"data/raw/{snapshot_tag}-{dataset}.json",
                1,
                utc_at(index),
            )
            snapshot_ids[statement] = snapshot_id
            snapshot_hashes[dataset] = payload_hash
        facts = tuple(
            rebuild_fact(
                fact,
                security_id=security_id,
                source_snapshot_id=snapshot_ids[fact.statement],
                **(
                    {"value": fact_values[(fact.metric_key, fact.period_end)]}
                    if (fact.metric_key, fact.period_end) in fact_values
                    else {}
                ),
            )
            for fact in complete_general_facts()
            if (fact.metric_key, fact.period_end) not in omitted_slots
        )
        self_inserted, ignored = store.insert_financial_facts(facts)
        if self_inserted != len(facts) or ignored:
            raise AssertionError("ready evidence fixture must insert canonical facts once")
        arguments: dict[str, object] = {
            "security_id": security_id,
            "facts": facts,
            "statement_snapshot_hashes": snapshot_hashes,
        }
        arguments.update(overrides)
        bundle = build_bundle_with_overrides(**arguments)
        return bundle, facts, snapshot_ids

    @classmethod
    def bundle_with_replaced_evidence(
        cls,
        bundle: FeatureBundle,
        *,
        feature_key: str,
        evidence: EvidenceRef,
    ) -> FeatureBundle:
        payload = bundle.to_dict()
        target = next(
            value
            for dimension in payload["dimension_inputs"].values()
            for value in dimension["values"]
            if value["key"] == feature_key
        )
        target["evidence"] = [evidence.to_dict()]
        return FeatureBundle.from_dict(payload)

    @staticmethod
    def insert_feature_set(
        connection: sqlite3.Connection,
        *,
        feature_set_id: str = "feature-set-1",
        status: str = "partial",
        coverage: float = 0.5,
    ) -> None:
        connection.execute(
            """INSERT INTO feature_set (
            id, security_id, report_period, as_of_utc, candidate_set_hash,
            template_id, template_version, contract_version, input_hash,
            status, financial_coverage, dimension_status_json,
            confidence_inputs_json, blockers_json, bundle_hash, bundle_path,
            missing_json, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                feature_set_id,
                "SH600001",
                "2026-06-30",
                utc_at(0),
                "candidate-hash-1",
                "general",
                "template-v1",
                "contract-v1",
                f"input-{feature_set_id}",
                status,
                coverage,
                "{}",
                "{}",
                "[]",
                f"bundle-{feature_set_id}",
                f"data/curated/formal_features/{feature_set_id}.json",
                "[]",
                utc_at(1),
            ),
        )

    def test_initialize_migrates_literal_v2_database_to_v5_without_changing_existing_rows(self) -> None:
        legacy_path = Path(self.tempdir.name) / "legacy.sqlite3"
        schema_sql = Path("tests/fixtures/schema_v2.sql").read_text(encoding="utf-8")
        ordered_tables = {
            "run": "id",
            "source_snapshot": "id",
            "job": "id",
            "score_run": "id",
            "score_item": "score_run_id, security_id",
            "quality_issue": "id",
            "artifact": "id",
        }
        with closing(sqlite3.connect(legacy_path)) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.executescript(schema_sql)
            connection.execute(
                "INSERT INTO run VALUES (?,?,?,?,?,?,?,?)",
                ("run-1", "incremental", utc_at(0), "{}", "succeeded", None, utc_at(0), utc_at(1)),
            )
            connection.execute(
                "INSERT INTO source_snapshot VALUES (?,?,?,?,?,?,?,?,?)",
                ("snapshot-1", "provider", "daily", "request-1", "payload-1", "raw/1.json", 1, utc_at(0), utc_at(1)),
            )
            connection.execute(
                "INSERT INTO job VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                ("job-1", "fetch", "fetch:1", "{}", "succeeded", None, None, None, "{}", None, utc_at(0), utc_at(1)),
            )
            connection.execute(
                "INSERT INTO score_run VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                ("score-1", "2026-06-30", utc_at(0), "rules-1", "universe-1", "incremental", "final", utc_at(0), utc_at(1), utc_at(0), 1, 1, "{}", "{}"),
            )
            connection.execute(
                "INSERT INTO score_item VALUES (?,?,?,?,?,?,?,?)",
                ("score-1", "SH600001", "final", 1.0, "input-1", '{"total":90}', "[]", utc_at(1)),
            )
            connection.execute(
                "INSERT INTO quality_issue VALUES (?,?,?,?,?,?,?)",
                ("issue-1", "run-1", "score-1", "warning", "fixture", "{}", utc_at(1)),
            )
            connection.execute(
                "INSERT INTO artifact VALUES (?,?,?,?,?,?)",
                ("artifact-1", "run-1", "export", "artifact-hash-1", "exports/1.json", utc_at(1)),
            )
            connection.commit()
            before = {
                table: connection.execute(f"SELECT * FROM {table} ORDER BY {order_by}").fetchall()
                for table, order_by in ordered_tables.items()
            }

        StateStore(legacy_path).initialize()

        with closing(sqlite3.connect(legacy_path)) as connection:
            for table, order_by in ordered_tables.items():
                self.assertEqual(
                    connection.execute(f"SELECT * FROM {table} ORDER BY {order_by}").fetchall(),
                    before[table],
                    table,
                )
            self.assertEqual(
                connection.execute("SELECT version FROM schema_migration ORDER BY version").fetchall(),
                [(2,), (3,), (4,), (5,)],
            )
            tables = {
                row[0]
                for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
        self.assertTrue(
            {
                "financial_fact",
                "feature_set",
                "feature_value",
                "quality_issue_binding",
            }
            <= tables
        )

        with self.assertRaises(ValueError):
            StateStore(legacy_path).upsert_score_item(
                "score-1", "SH600001", "ready", 1.0, "changed", {"total": 91}, []
            )
        with closing(sqlite3.connect(legacy_path)) as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT * FROM score_item ORDER BY score_run_id, security_id"
                ).fetchall(),
                before["score_item"],
            )

    def test_initialize_migrates_literal_v4_database_to_v5_without_changing_legacy_rows(self) -> None:
        legacy_path = Path(self.tempdir.name) / "legacy-v4.sqlite3"
        schema_sql = Path("tests/fixtures/schema_v4.sql").read_text(encoding="utf-8")
        with closing(sqlite3.connect(legacy_path)) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.executescript(schema_sql)
            connection.execute(
                "INSERT INTO source_snapshot VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    "legacy-snapshot",
                    "provider",
                    "daily",
                    "legacy-request",
                    "legacy-payload",
                    "raw/legacy.json",
                    1,
                    utc_at(0),
                    utc_at(1),
                ),
            )
            connection.execute(
                "INSERT INTO score_run VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "legacy-score",
                    "2026-06-30",
                    utc_at(0),
                    "rules-v4",
                    "universe-v4",
                    "incremental",
                    "final",
                    utc_at(0),
                    utc_at(1),
                    utc_at(0),
                    1,
                    1,
                    "{}",
                    "{}",
                ),
            )
            connection.commit()
            before_snapshot = connection.execute(
                "SELECT * FROM source_snapshot"
            ).fetchall()
            before_score_run = connection.execute("SELECT * FROM score_run").fetchall()

        StateStore(legacy_path).initialize()

        with closing(sqlite3.connect(legacy_path)) as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT version FROM schema_migration ORDER BY version"
                ).fetchall(),
                [(2,), (3,), (4,), (5,)],
            )
            self.assertEqual(
                connection.execute("SELECT * FROM source_snapshot").fetchall(),
                before_snapshot,
            )
            self.assertEqual(
                connection.execute("SELECT * FROM score_run").fetchall(),
                before_score_run,
            )
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            self.assertTrue(
                {
                    "formal_source_snapshot",
                    "formal_universe_source",
                    "formal_universe_status",
                    "formal_collection_task",
                }
                <= tables
            )
            snapshot_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(formal_source_snapshot)")
            }
            self.assertIn("request_fingerprint", snapshot_columns)
            self.assertEqual(
                connection.execute("SELECT * FROM formal_source_snapshot").fetchall(),
                [],
            )

        discontinuous_path = Path(self.tempdir.name) / "discontinuous-v4.sqlite3"
        with closing(sqlite3.connect(discontinuous_path)) as connection:
            connection.executescript(schema_sql)
            connection.execute("DELETE FROM schema_migration WHERE version = 3")
            connection.commit()

        with self.assertRaisesRegex(RuntimeError, "migration versions"):
            StateStore(discontinuous_path).initialize()

    def test_initialize_twice_keeps_one_complete_v5_schema_and_ledger(self) -> None:
        self.store.initialize()

        with closing(sqlite3.connect(self.db_path)) as connection:
            self.assertEqual(
                connection.execute("SELECT version FROM schema_migration ORDER BY version").fetchall(),
                [(2,), (3,), (4,), (5,)],
            )
            counts = dict(
                connection.execute(
                    """SELECT name, COUNT(*) FROM sqlite_master
                    WHERE type = 'table' AND name IN (
                        'financial_fact','feature_set','feature_value','quality_issue_binding'
                    )
                    GROUP BY name"""
                )
            )
        self.assertEqual(
            counts,
            {
                "financial_fact": 1,
                "feature_set": 1,
                "feature_value": 1,
                "quality_issue_binding": 1,
            },
        )

    def test_initialize_rejects_partial_v2_database_without_creating_ledger(self) -> None:
        corrupt_path = Path(self.tempdir.name) / "partial.sqlite3"
        with closing(sqlite3.connect(corrupt_path)) as connection:
            connection.execute("CREATE TABLE run (id TEXT PRIMARY KEY)")
            connection.commit()

        with self.assertRaisesRegex(RuntimeError, "v2 schema"):
            StateStore(corrupt_path).initialize()

        with closing(sqlite3.connect(corrupt_path)) as connection:
            tables = {
                row[0]
                for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
        self.assertEqual(tables, {"run"})

    def test_initialize_rejects_v2_check_with_changed_string_literal_case(self) -> None:
        corrupt_path = Path(self.tempdir.name) / "uppercase-check.sqlite3"
        schema_sql = Path("tests/fixtures/schema_v2.sql").read_text(encoding="utf-8")
        corrupt_sql = schema_sql.replace(
            "CHECK (status IN ('pending','running','succeeded','retryable_failed','terminal_failed'))",
            "CHECK (status IN ('PENDING','running','succeeded','retryable_failed','terminal_failed'))",
            1,
        )
        self.assertNotEqual(corrupt_sql, schema_sql)
        with closing(sqlite3.connect(corrupt_path)) as connection:
            connection.executescript(corrupt_sql)

        with self.assertRaisesRegex(RuntimeError, "v2 schema"):
            StateStore(corrupt_path).initialize()

        with closing(sqlite3.connect(corrupt_path)) as connection:
            tables = {
                row[0]
                for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
        self.assertNotIn("schema_migration", tables)
        self.assertTrue({"financial_fact", "feature_set", "feature_value"}.isdisjoint(tables))

    def test_ddl_normalization_preserves_escaped_single_quoted_literals(self) -> None:
        canonical = "CREATE TABLE Sample (value TEXT CHECK(value='It''s Ready'))"
        outside_case_and_spacing = "create table sample(value text check ( value = 'It''s Ready' ) )"
        changed_literal = "create table sample(value text check ( value = 'it''s ready' ) )"

        self.assertEqual(
            StateStore._normalized_ddl(canonical),
            StateStore._normalized_ddl(outside_case_and_spacing),
        )
        self.assertNotEqual(
            StateStore._normalized_ddl(canonical),
            StateStore._normalized_ddl(changed_literal),
        )

    def test_initialize_rejects_migration_ledgers_outside_contiguous_v2_to_v5(self) -> None:
        schema_sql = Path("tests/fixtures/schema_v2.sql").read_text(encoding="utf-8")
        for index, versions in enumerate(((3,), (2, 4), (2, 3, 5), (2, 3, 4, 6))):
            with self.subTest(versions=versions):
                legacy_path = Path(self.tempdir.name) / f"invalid-ledger-{index}.sqlite3"
                with closing(sqlite3.connect(legacy_path)) as connection:
                    connection.executescript(schema_sql)
                    connection.execute(
                        "CREATE TABLE schema_migration(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
                    )
                    connection.executemany(
                        "INSERT INTO schema_migration VALUES (?, ?)",
                        ((version, utc_at(version)) for version in versions),
                    )
                    connection.commit()

                with self.assertRaisesRegex(RuntimeError, "migration versions"):
                    StateStore(legacy_path).initialize()

    def test_initialize_applies_v3_through_v5_when_migration_ledger_contains_only_v2(self) -> None:
        legacy_path = Path(self.tempdir.name) / "ledger-v2.sqlite3"
        schema_sql = Path("tests/fixtures/schema_v2.sql").read_text(encoding="utf-8")
        with closing(sqlite3.connect(legacy_path)) as connection:
            connection.executescript(schema_sql)
            connection.execute(
                "CREATE TABLE schema_migration(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            connection.execute("INSERT INTO schema_migration VALUES (2, ?)", (utc_at(2),))
            connection.commit()

        StateStore(legacy_path).initialize()

        with closing(sqlite3.connect(legacy_path)) as connection:
            self.assertEqual(
                connection.execute("SELECT version FROM schema_migration ORDER BY version").fetchall(),
                [(2,), (3,), (4,), (5,)],
            )

    def test_initialize_migrates_complete_v3_database_to_v5_preserving_issues(self) -> None:
        legacy_path = Path(self.tempdir.name) / "ledger-v3.sqlite3"
        schema_sql = Path("tests/fixtures/schema_v2.sql").read_text(encoding="utf-8")
        with closing(sqlite3.connect(legacy_path)) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.executescript(schema_sql)
            connection.execute(
                "CREATE TABLE schema_migration(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            connection.execute("INSERT INTO schema_migration VALUES (2, ?)", (utc_at(2),))
            StateStore._apply_v3_migration(connection)
            connection.execute(
                "INSERT INTO quality_issue VALUES (?,?,?,?,?,?,?)",
                ("legacy-issue", None, None, "error", "legacy", "{}", utc_at(3)),
            )
            connection.commit()

        StateStore(legacy_path).initialize()

        with closing(sqlite3.connect(legacy_path)) as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT version FROM schema_migration ORDER BY version"
                ).fetchall(),
                [(2,), (3,), (4,), (5,)],
            )
            self.assertEqual(
                connection.execute("SELECT * FROM quality_issue").fetchall(),
                [("legacy-issue", None, None, "error", "legacy", "{}", utc_at(3))],
            )
            self.assertEqual(
                connection.execute("SELECT * FROM quality_issue_binding").fetchall(),
                [],
            )

    def test_initialize_rolls_back_v3_when_approved_index_name_is_preoccupied(self) -> None:
        legacy_path = Path(self.tempdir.name) / "wrong-index.sqlite3"
        schema_sql = Path("tests/fixtures/schema_v2.sql").read_text(encoding="utf-8")
        with closing(sqlite3.connect(legacy_path)) as connection:
            connection.executescript(schema_sql)
            connection.execute("CREATE INDEX feature_set_latest_idx ON job(id)")

        with self.assertRaisesRegex(RuntimeError, "v3 schema"):
            StateStore(legacy_path).initialize()

        with closing(sqlite3.connect(legacy_path)) as connection:
            tables = {
                row[0]
                for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            indexes = dict(
                connection.execute(
                    """SELECT name, tbl_name FROM sqlite_master
                    WHERE type='index' AND name IN (
                        'financial_fact_lookup_idx',
                        'financial_fact_snapshot_idx',
                        'feature_set_latest_idx'
                    )"""
                )
            )
        self.assertNotIn("schema_migration", tables)
        self.assertTrue({"financial_fact", "feature_set", "feature_value"}.isdisjoint(tables))
        self.assertEqual(indexes, {"feature_set_latest_idx": "job"})

    def configured_formal_store(
        self,
        *,
        raw_bytes: bytes = b"%PDF-1.7 official bootstrap",
        refresh_generation: str = "bootstrap-v1",
        producing_task_id: str | None = None,
        label: str = "default",
    ) -> tuple[StateStore, FormalSnapshotStore, OfficialFetch, FormalStoredSnapshot, EvidenceVerification]:
        raw_store, fetch, stored, verification = written_formal_snapshot(
            Path(self.tempdir.name) / f"formal-raw-{label}",
            raw_bytes=raw_bytes,
            refresh_generation=refresh_generation,
            producing_task_id=producing_task_id,
        )
        return (
            StateStore(self.db_path, formal_snapshot_store=raw_store),
            raw_store,
            fetch,
            stored,
            verification,
        )

    def task_backed_frozen_universe(
        self,
        *,
        label: str = "universe",
        db_path: Path | None = None,
    ) -> tuple[StateStore, FormalFrozenUniverseInput, dict[str, str]]:
        path = db_path or self.db_path
        if path != self.db_path:
            StateStore(path).initialize()
        raw_store = FormalSnapshotStore(
            Path(self.tempdir.name) / f"formal-universe-raw-{label}"
        )
        store = StateStore(path, formal_snapshot_store=raw_store)
        registry_manifest_hash = "7" * 64
        as_of_utc = "2026-08-31T15:00:00+08:00"
        exchange_values = {
            "BJ": ("bse", "https://www.bse.cn/listing", "430001"),
            "SH": ("sse", "https://www.sse.com.cn/listing", "600000"),
            "SZ": ("szse", "https://www.szse.cn/listing", "000001"),
        }
        policies = {
            "bse": SourcePolicy.bse(),
            "sse": SourcePolicy.sse(),
            "szse": SourcePolicy.szse(),
        }
        documents = []
        task_ids: dict[str, str] = {}
        for exchange in ("BJ", "SH", "SZ"):
            source, original_url, code6 = exchange_values[exchange]
            generation = f"universe-{exchange.lower()}-generation-v1"
            parser_id = f"{source}-listing-json"
            parser_version = f"{source}-listing-json-v1"
            request = OfficialRequest(
                source,
                "official_security_listing",
                None,
                "2026-08-31",
                exchange,
            )
            payload = {
                "as_of_utc": as_of_utc,
                "calendar_binding": None,
                "calendar_prerequisite_task_id": None,
                "exchange": exchange,
                "official_request": json.loads(
                    request.canonical_json_bytes().decode("utf-8")
                ),
                "refresh_generation": generation,
                "registry_manifest_hash": registry_manifest_hash,
                "relevant_registry_hashes": [["source_registry", "8" * 64]],
                "request_version": "universe-listing-v1",
                "source": source,
                "upstream_generation": "9" * 64,
            }
            task_id = store.enqueue_formal_task(
                "formal_universe_source",
                f"formal-universe-source:{label}:{exchange}",
                generation,
                payload,
            )
            task_ids[exchange] = task_id
            leased = store.lease_next_formal_task(
                ("formal_universe_source",), f"worker-{exchange.lower()}", 300
            )
            self.assertEqual(leased["id"], task_id)
            rows = ({
                "listing_status": "listed",
                "metadata": {
                    "aliases": [f"{exchange}-alpha", {"language": "zh"}],
                },
                "security_id": exchange + code6,
                "security_type": "ordinary_a",
            },)
            if exchange == "BJ":
                rows += ({
                    "listing_status": "listed",
                    "security_id": "BJ899001",
                    "security_type": "bond",
                },)
            raw_bytes = json.dumps(
                list(rows),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            fetch = OfficialFetch(
                request=request,
                raw_bytes=raw_bytes,
                original_url=original_url,
                published_at_utc="2026-08-31T06:00:00+00:00",
                published_precision="timestamp",
                source_updated_at_utc=None,
                captured_at_utc="2026-08-31T06:30:00+00:00",
                effective_at_utc="2026-08-31T06:00:00+00:00",
                effective_time_evidence_hash=None,
                refresh_generation=generation,
                parser_id=parser_id,
                parser_version=parser_version,
                mapping_version=f"{source}-listing-map-v1",
                declared_security_id=None,
                declared_period="2026-08-31",
            )
            verification = verify_official_fetch(fetch, policies[source])
            self.assertEqual(verification.status, "verified")
            stored = raw_store.write_verified(
                fetch, verification, producing_task_id=task_id
            )
            ref = store.put_formal_snapshot_for_leased_task(
                fetch,
                stored,
                verification,
                task_id=task_id,
                worker_id=f"worker-{exchange.lower()}",
            )
            document = FormalUniverseSourceDocument(
                exchange=exchange,
                snapshot=ref,
                parser_id=parser_id,
                parser_version=parser_version,
                parsed_rows=rows,
            )
            extraction = extract_formal_universe_members(document)
            store.complete_formal_task(
                task_id,
                f"worker-{exchange.lower()}",
                {
                    "exchange": exchange,
                    "manifest_sha256": ref.manifest_sha256,
                    "parsed_rows_hash": extraction.audit.parsed_rows_hash,
                    "parser_id": parser_id,
                    "parser_version": parser_version,
                    "refresh_generation": generation,
                    "registry_manifest_hash": registry_manifest_hash,
                    "snapshot_id": ref.snapshot_id,
                    "source_content_sha256": ref.content_sha256,
                },
            )
            documents.append(document)
        frozen = FormalUniverseIngestor().build(
            as_of_utc, registry_manifest_hash, tuple(documents)
        )
        return store, frozen, task_ids

    def insert_formal_receipt_fixture(
        self,
        *,
        db_path: Path | None = None,
        include_receipt: bool = True,
        task_id: str,
        raw_store: FormalSnapshotStore,
        fetch: OfficialFetch,
        stored: FormalStoredSnapshot,
        verification: EvidenceVerification,
    ) -> tuple[str, dict[str, object]]:
        validated = raw_store.validate_stored_snapshot(
            fetch,
            stored,
            verification,
            expected_producing_task_id=task_id,
        )
        snapshot_id = str(uuid.uuid4())
        receipt = {
            "task_id": task_id,
            "snapshot_id": snapshot_id,
            "manifest_sha256": validated.manifest_sha256,
            "refresh_generation": validated.refresh_generation,
            "recorded_at": utc_at(5),
        }
        with closing(sqlite3.connect(db_path or self.db_path)) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute(
                """INSERT INTO formal_source_snapshot
                (id,source,dataset,request_json,request_fingerprint,content_sha256,
                 manifest_sha256,content_path,manifest_path,original_url,published_at_utc,
                 published_precision,source_updated_at_utc,captured_at_utc,effective_at_utc,
                 effective_time_evidence_hash,parser_id,parser_version,mapping_version,
                 refresh_generation,producing_task_id,verification_json,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    snapshot_id,
                    validated.source,
                    validated.dataset,
                    validated.request_json,
                    validated.request_fingerprint,
                    validated.content_sha256,
                    validated.manifest_sha256,
                    validated.content_path,
                    validated.manifest_path,
                    validated.original_url,
                    validated.published_at_utc,
                    validated.published_precision,
                    validated.source_updated_at_utc,
                    validated.captured_at_utc,
                    validated.effective_at_utc,
                    validated.effective_time_evidence_hash,
                    validated.parser_id,
                    validated.parser_version,
                    validated.mapping_version,
                    validated.refresh_generation,
                    validated.producing_task_id,
                    validated.verification_json,
                    utc_at(4),
                ),
            )
            if include_receipt:
                connection.execute(
                    """INSERT INTO formal_task_snapshot_receipt
                    (task_id,snapshot_id,manifest_sha256,refresh_generation,recorded_at)
                    VALUES (?,?,?,?,?)""",
                    tuple(receipt.values()),
                )
            connection.commit()
        return snapshot_id, receipt

    def test_formal_snapshot_store_injection_is_optional_but_formal_apis_fail_closed(self) -> None:
        self.assertIsNone(self.store.get_job("missing"))
        for operation in (
            lambda: self.store.put_formal_snapshot(None, None, None),
            lambda: self.store.put_formal_snapshot_for_leased_task(
                None, None, None, task_id="task", worker_id="worker"
            ),
            lambda: self.store.get_formal_snapshot("missing"),
            lambda: self.store.get_formal_task_snapshot_receipt("missing"),
        ):
            with self.subTest(operation=operation):
                with self.assertRaisesRegex(ValueError, "formal snapshot store.*configured"):
                    operation()
        with self.assertRaisesRegex(ValueError, "formal_snapshot_store"):
            StateStore(self.db_path, formal_snapshot_store=object())

    def test_put_formal_bootstrap_snapshot_returns_revalidated_ref_without_receipt(self) -> None:
        store, _, fetch, stored, verification = self.configured_formal_store()

        first = store.put_formal_snapshot(fetch, stored, verification)
        replay = store.put_formal_snapshot(fetch, stored, verification)

        self.assertIsInstance(first, OfficialSnapshotRef)
        self.assertEqual(replay, first)
        self.assertEqual(store.get_formal_snapshot(first.snapshot_id), first)
        self.assertEqual(first.request_fingerprint, fetch.request.request_fingerprint)
        self.assertEqual(first.content_sha256, fetch.content_sha256)
        self.assertEqual(first.manifest_sha256, stored.manifest_sha256)
        self.assertEqual(first.refresh_generation, "bootstrap-v1")
        self.assertIsNone(first.producing_task_id)
        self.assertEqual(first.verification_status, "verified")
        with closing(sqlite3.connect(self.db_path)) as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM formal_source_snapshot").fetchone()[0],
                1,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT producing_task_id FROM formal_source_snapshot"
                ).fetchone()[0],
                None,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM formal_task_snapshot_receipt"
                ).fetchone()[0],
                0,
            )

    def test_formal_bootstrap_new_generation_shares_binary_but_keeps_distinct_lineage(self) -> None:
        raw_root = Path(self.tempdir.name) / "formal-shared-binary"
        raw_store, first_fetch, first_stored, first_verification = written_formal_snapshot(
            raw_root, refresh_generation="generation-v1"
        )
        _, second_fetch, second_stored, second_verification = written_formal_snapshot(
            raw_root, refresh_generation="generation-v2"
        )
        store = StateStore(self.db_path, formal_snapshot_store=raw_store)

        first = store.put_formal_snapshot(
            first_fetch, first_stored, first_verification
        )
        second = store.put_formal_snapshot(
            second_fetch, second_stored, second_verification
        )

        self.assertNotEqual(first.snapshot_id, second.snapshot_id)
        self.assertNotEqual(first.manifest_sha256, second.manifest_sha256)
        self.assertEqual(first.content_sha256, second.content_sha256)
        self.assertEqual(first.content_path, second.content_path)
        with closing(sqlite3.connect(self.db_path)) as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM formal_source_snapshot").fetchone()[0],
                2,
            )

    def test_formal_snapshot_manifest_and_lineage_conflicts_never_repair_rows(self) -> None:
        store, _, fetch, stored, verification = self.configured_formal_store(
            label="manifest-conflict"
        )
        ref = store.put_formal_snapshot(fetch, stored, verification)
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                "UPDATE formal_source_snapshot SET original_url = ? WHERE id = ?",
                ("https://static.cninfo.com.cn/tampered.pdf", ref.snapshot_id),
            )
            connection.commit()
            before = connection.execute(
                "SELECT * FROM formal_source_snapshot WHERE id = ?", (ref.snapshot_id,)
            ).fetchone()

        with self.assertRaisesRegex(ValueError, "formal_snapshot_manifest_conflict"):
            store.put_formal_snapshot(fetch, stored, verification)
        with closing(sqlite3.connect(self.db_path)) as connection:
            after = connection.execute(
                "SELECT * FROM formal_source_snapshot WHERE id = ?", (ref.snapshot_id,)
            ).fetchone()
        self.assertEqual(after, before)

        lineage_path = Path(self.tempdir.name) / "lineage.sqlite3"
        raw_root = Path(self.tempdir.name) / "lineage-raw"
        raw_store, first_fetch, first_stored, first_verification = written_formal_snapshot(
            raw_root, raw_bytes=b"first", refresh_generation="same-generation"
        )
        _, second_fetch, second_stored, second_verification = written_formal_snapshot(
            raw_root, raw_bytes=b"second", refresh_generation="same-generation"
        )
        lineage_store = StateStore(lineage_path, formal_snapshot_store=raw_store)
        lineage_store.initialize()
        first_ref = lineage_store.put_formal_snapshot(
            first_fetch, first_stored, first_verification
        )
        with self.assertRaisesRegex(ValueError, "formal_snapshot_lineage_conflict"):
            lineage_store.put_formal_snapshot(
                second_fetch, second_stored, second_verification
            )
        self.assertEqual(lineage_store.get_formal_snapshot(first_ref.snapshot_id), first_ref)
        with closing(sqlite3.connect(lineage_path)) as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM formal_source_snapshot").fetchone()[0],
                1,
            )

    def test_formal_bootstrap_rejections_leave_database_empty(self) -> None:
        cases: list[tuple[str, OfficialFetch, FormalStoredSnapshot, EvidenceVerification, FormalSnapshotStore]] = []
        raw_store, fetch, stored, verification = written_formal_snapshot(
            Path(self.tempdir.name) / "formal-rejections-valid"
        )
        cases.append(
            (
                "rejected",
                fetch,
                stored,
                replace(verification, status="rejected"),
                raw_store,
            )
        )
        producer_store, producer_fetch, producer_stored, producer_verification = written_formal_snapshot(
            Path(self.tempdir.name) / "formal-rejections-producer",
            producing_task_id="task-produced",
        )
        cases.append(
            (
                "producer",
                producer_fetch,
                producer_stored,
                producer_verification,
                producer_store,
            )
        )
        cases.append(
            (
                "mismatch",
                replace(fetch, refresh_generation="other-generation"),
                stored,
                verification,
                raw_store,
            )
        )
        for index, (label, candidate_fetch, candidate_stored, candidate_verification, candidate_raw_store) in enumerate(cases):
            with self.subTest(label=label):
                path = Path(self.tempdir.name) / f"formal-rejection-{index}.sqlite3"
                store = StateStore(path, formal_snapshot_store=candidate_raw_store)
                store.initialize()
                with self.assertRaises(ValueError):
                    store.put_formal_snapshot(
                        candidate_fetch, candidate_stored, candidate_verification
                    )
                with closing(sqlite3.connect(path)) as connection:
                    self.assertEqual(
                        connection.execute(
                            "SELECT COUNT(*) FROM formal_source_snapshot"
                        ).fetchone()[0],
                        0,
                    )
                    self.assertEqual(
                        connection.execute(
                            "SELECT COUNT(*) FROM formal_task_snapshot_receipt"
                        ).fetchone()[0],
                        0,
                    )

    def test_put_formal_snapshot_for_leased_task_is_atomic_replayable_and_durable_after_failure(self) -> None:
        generation = "leased-generation"
        raw_root = Path(self.tempdir.name) / "formal-leased-success"
        raw_store, bootstrap_fetch, bootstrap_stored, bootstrap_verification = written_formal_snapshot(
            raw_root,
            refresh_generation=generation,
        )
        store = StateStore(self.db_path, formal_snapshot_store=raw_store)
        bootstrap = store.put_formal_snapshot(
            bootstrap_fetch, bootstrap_stored, bootstrap_verification
        )
        task_id = store.enqueue_formal_task(
            "formal_statement", "leased-success", generation, {"slot": 1}
        )
        store.lease_next_formal_task(
            ("formal_statement",), "worker-a", 30, now_utc=utc_at(0)
        )
        _, fetch, stored, verification = written_formal_snapshot(
            raw_root,
            refresh_generation=generation,
            producing_task_id=task_id,
        )

        for invalid_task_id, invalid_worker_id in (
            (None, "worker-a"),
            (7, "worker-a"),
            ("", "worker-a"),
            (task_id, None),
            (task_id, 7),
            (task_id, "   "),
        ):
            with self.subTest(
                invalid_task_id=invalid_task_id,
                invalid_worker_id=invalid_worker_id,
            ):
                with self.assertRaises(ValueError):
                    store.put_formal_snapshot_for_leased_task(
                        fetch,
                        stored,
                        verification,
                        task_id=invalid_task_id,
                        worker_id=invalid_worker_id,
                    )

        with patch("ashare_pipeline.state_store._utc_now", return_value=utc_at(1)):
            ref = store.put_formal_snapshot_for_leased_task(
                fetch,
                stored,
                verification,
                task_id=task_id,
                worker_id="worker-a",
            )
        with patch("ashare_pipeline.state_store._utc_now", return_value=utc_at(2)):
            replay = store.put_formal_snapshot_for_leased_task(
                fetch,
                stored,
                verification,
                task_id=task_id,
                worker_id="worker-a",
            )

        self.assertEqual(replay, ref)
        self.assertNotEqual(ref.snapshot_id, bootstrap.snapshot_id)
        self.assertNotEqual(ref.manifest_sha256, bootstrap.manifest_sha256)
        self.assertEqual(ref.content_path, bootstrap.content_path)
        self.assertEqual(ref.producing_task_id, task_id)
        receipt = store.get_formal_task_snapshot_receipt(task_id)
        self.assertEqual(receipt["snapshot_id"], ref.snapshot_id)
        self.assertEqual(receipt["manifest_sha256"], ref.manifest_sha256)
        self.assertEqual(receipt["refresh_generation"], generation)
        with closing(sqlite3.connect(self.db_path)) as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM formal_source_snapshot").fetchone()[0],
                2,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM formal_task_snapshot_receipt"
                ).fetchone()[0],
                1,
            )

        with patch("ashare_pipeline.state_store._utc_now", return_value=utc_at(3)):
            store.fail_formal_task(
                task_id,
                "worker-a",
                {"code": "parse_failed", "snapshot_id": ref.snapshot_id},
                "terminal_failed",
                None,
            )
        self.assertEqual(
            store.get_formal_task_snapshot_receipt(task_id)["snapshot_id"],
            ref.snapshot_id,
        )

    def test_put_formal_snapshot_for_leased_task_accepts_only_source_fetch_kinds(self) -> None:
        for index, kind in enumerate(
            ("formal_statement", "formal_context", "formal_universe_source")
        ):
            with self.subTest(kind=kind):
                path = Path(self.tempdir.name) / f"formal-source-kind-{index}.sqlite3"
                task_store = StateStore(path)
                task_store.initialize()
                generation = f"source-kind-generation-{index}"
                task_id = task_store.enqueue_formal_task(
                    kind, f"source-kind-{index}", generation, {}
                )
                task_store.lease_next_formal_task(
                    (kind,), "worker-a", 30, now_utc=utc_at(0)
                )
                raw_store, fetch, stored, verification = written_formal_snapshot(
                    Path(self.tempdir.name) / f"formal-source-kind-raw-{index}",
                    refresh_generation=generation,
                    producing_task_id=task_id,
                )
                configured = StateStore(path, formal_snapshot_store=raw_store)
                with patch(
                    "ashare_pipeline.state_store._utc_now", return_value=utc_at(1)
                ):
                    ref = configured.put_formal_snapshot_for_leased_task(
                        fetch,
                        stored,
                        verification,
                        task_id=task_id,
                        worker_id="worker-a",
                    )
                self.assertEqual(ref.producing_task_id, task_id)

    def test_put_formal_snapshot_for_leased_task_rejects_fencing_and_evidence_mismatches_without_rows(self) -> None:
        cases = (
            "pending",
            "verified",
            "wrong-worker",
            "expired",
            "taken-over",
            "wrong-generation",
            "non-source-kind",
            "mismatched-producer",
            "raw-mismatch",
        )
        for index, case in enumerate(cases):
            with self.subTest(case=case):
                path = Path(self.tempdir.name) / f"formal-leased-rejection-{index}.sqlite3"
                task_store = StateStore(path)
                task_store.initialize()
                task_generation = "task-generation"
                kind = "formal_feature" if case == "non-source-kind" else "formal_statement"
                task_id = task_store.enqueue_formal_task(
                    kind, f"leased-rejection-{index}", task_generation, {}
                )
                if case != "pending":
                    task_store.lease_next_formal_task(
                        (kind,), "worker-a", 10, now_utc=utc_at(0)
                    )
                if case == "verified":
                    with closing(sqlite3.connect(path)) as connection:
                        connection.execute(
                            "UPDATE formal_collection_task SET status='verified' WHERE id=?",
                            (task_id,),
                        )
                        connection.commit()
                if case == "taken-over":
                    task_store.lease_next_formal_task(
                        (kind,), "worker-new", 30, now_utc=utc_at(10)
                    )
                fetch_generation = (
                    "wrong-generation" if case == "wrong-generation" else task_generation
                )
                producer = "other-task" if case == "mismatched-producer" else task_id
                raw_store, fetch, stored, verification = written_formal_snapshot(
                    Path(self.tempdir.name) / f"formal-leased-rejection-raw-{index}",
                    refresh_generation=fetch_generation,
                    producing_task_id=producer,
                )
                if case == "raw-mismatch":
                    fetch = replace(fetch, raw_bytes=b"caller-substituted-raw")
                configured = StateStore(path, formal_snapshot_store=raw_store)
                worker = "worker-b" if case == "wrong-worker" else "worker-a"
                now = utc_at(11) if case in {"expired", "taken-over"} else utc_at(1)

                with patch("ashare_pipeline.state_store._utc_now", return_value=now):
                    with self.assertRaises(ValueError):
                        configured.put_formal_snapshot_for_leased_task(
                            fetch,
                            stored,
                            verification,
                            task_id=task_id,
                            worker_id=worker,
                        )
                with closing(sqlite3.connect(path)) as connection:
                    self.assertEqual(
                        connection.execute(
                            "SELECT COUNT(*) FROM formal_source_snapshot"
                        ).fetchone()[0],
                        0,
                    )
                    self.assertEqual(
                        connection.execute(
                            "SELECT COUNT(*) FROM formal_task_snapshot_receipt"
                        ).fetchone()[0],
                        0,
                    )

    def test_put_formal_snapshot_for_leased_task_rejects_replacement_and_cross_task_attachment(self) -> None:
        generation = "receipt-conflict-generation"
        raw_root = Path(self.tempdir.name) / "formal-receipt-conflict-raw"
        task_id = self.store.enqueue_formal_task(
            "formal_statement", "receipt-conflict-first", generation, {}
        )
        self.store.lease_next_formal_task(
            ("formal_statement",), "worker-a", 30, now_utc=utc_at(0)
        )
        raw_store, first_fetch, first_stored, first_verification = written_formal_snapshot(
            raw_root,
            raw_bytes=b"first task evidence",
            refresh_generation=generation,
            producing_task_id=task_id,
        )
        store = StateStore(self.db_path, formal_snapshot_store=raw_store)
        with patch("ashare_pipeline.state_store._utc_now", return_value=utc_at(1)):
            first_ref = store.put_formal_snapshot_for_leased_task(
                first_fetch,
                first_stored,
                first_verification,
                task_id=task_id,
                worker_id="worker-a",
            )
        _, second_fetch, second_stored, second_verification = written_formal_snapshot(
            raw_root,
            raw_bytes=b"replacement task evidence",
            refresh_generation=generation,
            producing_task_id=task_id,
        )
        with patch("ashare_pipeline.state_store._utc_now", return_value=utc_at(2)):
            with self.assertRaisesRegex(ValueError, "receipt.*conflict"):
                store.put_formal_snapshot_for_leased_task(
                    second_fetch,
                    second_stored,
                    second_verification,
                    task_id=task_id,
                    worker_id="worker-a",
                )

        other_task_id = store.enqueue_formal_task(
            "formal_statement", "receipt-conflict-second", generation, {}
        )
        store.lease_next_formal_task(
            ("formal_statement",), "worker-b", 30, now_utc=utc_at(2)
        )
        with patch("ashare_pipeline.state_store._utc_now", return_value=utc_at(3)):
            with self.assertRaises(ValueError):
                store.put_formal_snapshot_for_leased_task(
                    first_fetch,
                    first_stored,
                    first_verification,
                    task_id=other_task_id,
                    worker_id="worker-b",
                )

        self.assertEqual(store.get_formal_snapshot(first_ref.snapshot_id), first_ref)
        self.assertIsNone(store.get_formal_task_snapshot_receipt(other_task_id))
        with closing(sqlite3.connect(self.db_path)) as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM formal_source_snapshot").fetchone()[0],
                1,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM formal_task_snapshot_receipt"
                ).fetchone()[0],
                1,
            )

    def test_put_formal_snapshot_for_leased_task_rolls_back_snapshot_when_receipt_insert_fails(self) -> None:
        path = Path(self.tempdir.name) / "formal-late-receipt-failure.sqlite3"
        task_store = StateStore(path)
        task_store.initialize()
        generation = "late-failure-generation"
        task_id = task_store.enqueue_formal_task(
            "formal_statement", "late-receipt-failure", generation, {}
        )
        task_store.lease_next_formal_task(
            ("formal_statement",), "worker-a", 30, now_utc=utc_at(0)
        )
        raw_store, fetch, stored, verification = written_formal_snapshot(
            Path(self.tempdir.name) / "formal-late-receipt-failure-raw",
            refresh_generation=generation,
            producing_task_id=task_id,
        )
        store = StateStore(path, formal_snapshot_store=raw_store)
        with closing(sqlite3.connect(path)) as connection:
            connection.execute(
                """CREATE TRIGGER force_late_receipt_failure
                BEFORE INSERT ON formal_task_snapshot_receipt
                BEGIN SELECT RAISE(ABORT, 'forced late receipt failure'); END"""
            )
            connection.commit()

        with patch("ashare_pipeline.state_store._utc_now", return_value=utc_at(1)):
            with self.assertRaisesRegex(ValueError, "receipt.*conflict"):
                store.put_formal_snapshot_for_leased_task(
                    fetch,
                    stored,
                    verification,
                    task_id=task_id,
                    worker_id="worker-a",
                )
        with closing(sqlite3.connect(path)) as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM formal_source_snapshot").fetchone()[0],
                0,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM formal_task_snapshot_receipt"
                ).fetchone()[0],
                0,
            )

    def test_formal_snapshot_getter_rejects_malformed_ids_and_stored_tamper(self) -> None:
        store, raw_store, fetch, stored, verification = self.configured_formal_store(
            label="getter-inputs"
        )
        ref = store.put_formal_snapshot(fetch, stored, verification)
        for invalid_id in ("", "   ", None, 7):
            with self.subTest(invalid_id=invalid_id):
                with self.assertRaises(ValueError):
                    store.get_formal_snapshot(invalid_id)
        self.assertIsNone(store.get_formal_snapshot("missing-snapshot"))

        tamper_cases = (
            ("request_json", '{"dataset":"annual_report"}'),
            ("request_json", '{"dataset":"annual_report","extra":1}'),
            ("request_fingerprint", "0" * 64),
            ("verification_json", '{"content_sha256":"0"}'),
            ("original_url", "https://static.cninfo.com.cn/tampered.pdf"),
            ("created_at", "2026-09-04T08:00:00"),
        )
        for index, (column, value) in enumerate(tamper_cases):
            with self.subTest(column=column, value=value):
                path = Path(self.tempdir.name) / f"formal-db-tamper-{index}.sqlite3"
                candidate = StateStore(path, formal_snapshot_store=raw_store)
                candidate.initialize()
                candidate_ref = candidate.put_formal_snapshot(fetch, stored, verification)
                with closing(sqlite3.connect(path)) as connection:
                    connection.execute(
                        f"UPDATE formal_source_snapshot SET {column} = ? WHERE id = ?",
                        (value, candidate_ref.snapshot_id),
                    )
                    connection.commit()
                with self.assertRaises(ValueError):
                    candidate.get_formal_snapshot(candidate_ref.snapshot_id)

        Path(ref.content_path).write_bytes(b"tampered raw bytes")
        with self.assertRaises(ValueError):
            store.get_formal_snapshot(ref.snapshot_id)

        manifest_raw_store, manifest_fetch, manifest_stored, manifest_verification = written_formal_snapshot(
            Path(self.tempdir.name) / "formal-raw-manifest-tamper"
        )
        manifest_store = StateStore(
            Path(self.tempdir.name) / "formal-manifest-tamper.sqlite3",
            formal_snapshot_store=manifest_raw_store,
        )
        manifest_store.initialize()
        manifest_ref = manifest_store.put_formal_snapshot(
            manifest_fetch, manifest_stored, manifest_verification
        )
        Path(manifest_ref.manifest_path).write_bytes(b"{}")
        with self.assertRaises(ValueError):
            manifest_store.get_formal_snapshot(manifest_ref.snapshot_id)

    def test_formal_receipt_getter_revalidates_task_snapshot_lineage_and_survives_failure(self) -> None:
        task_id = self.store.enqueue_formal_task(
            "formal_statement", "receipt-task", "receipt-generation", {"slot": 1}
        )
        store, raw_store, fetch, stored, verification = self.configured_formal_store(
            refresh_generation="receipt-generation",
            producing_task_id=task_id,
            label="receipt-success",
        )
        snapshot_id, expected = self.insert_formal_receipt_fixture(
            task_id=task_id,
            raw_store=raw_store,
            fetch=fetch,
            stored=stored,
            verification=verification,
        )

        self.assertEqual(store.get_formal_task_snapshot_receipt(task_id), expected)
        self.assertEqual(store.get_formal_snapshot(snapshot_id).producing_task_id, task_id)
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                """UPDATE formal_collection_task
                SET status='terminal_failed', error_json=? WHERE id=?""",
                ('{"code":"parse_failed"}', task_id),
            )
            connection.commit()
        self.assertEqual(store.get_formal_task_snapshot_receipt(task_id), expected)

        for invalid_id in ("", None, 9):
            with self.subTest(invalid_id=invalid_id):
                with self.assertRaises(ValueError):
                    store.get_formal_task_snapshot_receipt(invalid_id)
        self.assertIsNone(store.get_formal_task_snapshot_receipt("missing-task"))

    def test_formal_receipt_getter_rejects_every_cross_lineage_mismatch(self) -> None:
        mutations = (
            ("formal_task_snapshot_receipt", "manifest_sha256", "0" * 64),
            ("formal_task_snapshot_receipt", "refresh_generation", "wrong-generation"),
            ("formal_source_snapshot", "manifest_sha256", "0" * 64),
            ("formal_source_snapshot", "refresh_generation", "wrong-generation"),
            ("formal_source_snapshot", "producing_task_id", None),
            ("formal_collection_task", "refresh_generation", "wrong-generation"),
            ("formal_task_snapshot_receipt", "recorded_at", "2026-09-04T08:00:00"),
        )
        for index, (table, column, value) in enumerate(mutations):
            with self.subTest(table=table, column=column):
                path = Path(self.tempdir.name) / f"receipt-mismatch-{index}.sqlite3"
                task_store = StateStore(path)
                task_store.initialize()
                task_id = task_store.enqueue_formal_task(
                    "formal_statement",
                    f"receipt-mismatch-{index}",
                    "receipt-generation",
                    {},
                )
                raw_store, fetch, stored, verification = written_formal_snapshot(
                    Path(self.tempdir.name) / f"receipt-mismatch-raw-{index}",
                    refresh_generation="receipt-generation",
                    producing_task_id=task_id,
                )
                configured = StateStore(path, formal_snapshot_store=raw_store)
                snapshot_id, _ = self.insert_formal_receipt_fixture(
                    db_path=path,
                    task_id=task_id,
                    raw_store=raw_store,
                    fetch=fetch,
                    stored=stored,
                    verification=verification,
                )
                target_id = task_id if table != "formal_source_snapshot" else snapshot_id
                id_column = "id" if table != "formal_task_snapshot_receipt" else "task_id"
                with closing(sqlite3.connect(path)) as connection:
                    connection.execute("PRAGMA foreign_keys = OFF")
                    connection.execute(
                        f"UPDATE {table} SET {column} = ? WHERE {id_column} = ?",
                        (value, target_id),
                    )
                    connection.commit()
                with self.assertRaises(ValueError):
                    configured.get_formal_task_snapshot_receipt(task_id)

    def test_formal_receipt_getter_rejects_deleted_receipt_orphan(self) -> None:
        task_id = self.store.enqueue_formal_task(
            "formal_statement", "receipt-orphan", "receipt-generation", {}
        )
        store, raw_store, fetch, stored, verification = self.configured_formal_store(
            refresh_generation="receipt-generation",
            producing_task_id=task_id,
            label="receipt-orphan",
        )
        snapshot_id, _ = self.insert_formal_receipt_fixture(
            task_id=task_id,
            raw_store=raw_store,
            fetch=fetch,
            stored=stored,
            verification=verification,
        )
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                "DELETE FROM formal_task_snapshot_receipt WHERE task_id = ?",
                (task_id,),
            )
            connection.commit()

        self.assertEqual(store.get_formal_snapshot(snapshot_id).producing_task_id, task_id)
        with self.assertRaisesRegex(ValueError, "receipt.*producer|producer.*receipt"):
            store.get_formal_task_snapshot_receipt(task_id)

        empty_task = self.store.enqueue_formal_task(
            "formal_statement", "genuine-no-receipt", "receipt-generation", {}
        )
        self.assertIsNone(store.get_formal_task_snapshot_receipt(empty_task))

    def test_formal_receipt_getter_rejects_extra_producer_snapshot(self) -> None:
        task_id = self.store.enqueue_formal_task(
            "formal_statement", "receipt-extra", "receipt-generation", {}
        )
        raw_root = Path(self.tempdir.name) / "receipt-extra-raw"
        raw_store, fetch, stored, verification = written_formal_snapshot(
            raw_root,
            refresh_generation="receipt-generation",
            producing_task_id=task_id,
        )
        store = StateStore(self.db_path, formal_snapshot_store=raw_store)
        _, expected = self.insert_formal_receipt_fixture(
            task_id=task_id,
            raw_store=raw_store,
            fetch=fetch,
            stored=stored,
            verification=verification,
        )
        _, extra_fetch, extra_stored, extra_verification = written_formal_snapshot(
            raw_root,
            raw_bytes=b"extra producer row",
            refresh_generation="extra-generation",
            producing_task_id=task_id,
        )
        extra_snapshot_id, _ = self.insert_formal_receipt_fixture(
            include_receipt=False,
            task_id=task_id,
            raw_store=raw_store,
            fetch=extra_fetch,
            stored=extra_stored,
            verification=extra_verification,
        )

        with self.assertRaisesRegex(ValueError, "receipt.*producer|producer.*receipt"):
            store.get_formal_task_snapshot_receipt(task_id)
        with closing(sqlite3.connect(self.db_path)) as connection:
            self.assertEqual(
                connection.execute(
                    """SELECT id FROM formal_source_snapshot
                    WHERE producing_task_id = ? ORDER BY id""",
                    (task_id,),
                ).fetchall(),
                sorted([(expected["snapshot_id"],), (extra_snapshot_id,)]),
            )

    def test_formal_receipt_getter_reads_one_consistent_database_snapshot(self) -> None:
        task_id = self.store.enqueue_formal_task(
            "formal_statement", "receipt-consistent-read", "receipt-generation", {}
        )
        raw_root = Path(self.tempdir.name) / "receipt-consistent-read-raw"
        raw_store, fetch, stored, verification = written_formal_snapshot(
            raw_root,
            refresh_generation="receipt-generation",
            producing_task_id=task_id,
        )
        store = StateStore(self.db_path, formal_snapshot_store=raw_store)
        _, receipt = self.insert_formal_receipt_fixture(
            task_id=task_id,
            raw_store=raw_store,
            fetch=fetch,
            stored=stored,
            verification=verification,
        )
        _, extra_fetch, extra_stored, extra_verification = written_formal_snapshot(
            raw_root,
            raw_bytes=b"extra producer before interleaving",
            refresh_generation="extra-generation",
            producing_task_id=task_id,
        )
        extra_snapshot_id, _ = self.insert_formal_receipt_fixture(
            include_receipt=False,
            task_id=task_id,
            raw_store=raw_store,
            fetch=extra_fetch,
            stored=extra_stored,
            verification=extra_verification,
        )
        real_connect = store._connect
        database_path = self.db_path
        interleaved = False

        class ReceiptCursor:
            def __init__(self, cursor):
                self.cursor = cursor

            def fetchone(self):
                nonlocal interleaved
                row = self.cursor.fetchone()
                with closing(sqlite3.connect(database_path)) as mutator:
                    mutator.execute("PRAGMA foreign_keys = OFF")
                    mutator.execute(
                        "DELETE FROM formal_task_snapshot_receipt WHERE task_id = ?",
                        (task_id,),
                    )
                    mutator.execute(
                        "DELETE FROM formal_source_snapshot WHERE id = ?",
                        (extra_snapshot_id,),
                    )
                    mutator.commit()
                interleaved = True
                return row

        class ObservedConnection:
            def __init__(self, connection):
                self.connection = connection

            def __getattr__(self, name):
                return getattr(self.connection, name)

            def execute(self, sql, parameters=()):
                cursor = self.connection.execute(sql, parameters)
                if "SELECT * FROM formal_task_snapshot_receipt" in sql:
                    return ReceiptCursor(cursor)
                return cursor

        with patch.object(
            store,
            "_connect",
            side_effect=lambda: ObservedConnection(real_connect()),
        ):
            with self.assertRaisesRegex(ValueError, "producer set"):
                store.get_formal_task_snapshot_receipt(task_id)

        self.assertTrue(interleaved)
        with closing(sqlite3.connect(self.db_path)) as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM formal_task_snapshot_receipt WHERE task_id = ?",
                    (task_id,),
                ).fetchone()[0],
                0,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT id FROM formal_source_snapshot WHERE producing_task_id = ?",
                    (task_id,),
                ).fetchall(),
                [(receipt["snapshot_id"],)],
            )

    def test_formal_snapshot_lookup_never_reads_legacy_source_snapshot(self) -> None:
        store, _, fetch, stored, verification = self.configured_formal_store(
            label="legacy-isolation"
        )
        legacy_id, _ = self.store.record_snapshot(
            fetch.request.source,
            fetch.request.dataset,
            fetch.request.request_fingerprint,
            fetch.content_sha256,
            stored.content_path,
            1,
            fetch.captured_at_utc,
        )

        self.assertIsNone(store.get_formal_snapshot(legacy_id))
        self.assertIsNone(store.get_formal_task_snapshot_receipt(legacy_id))
        with closing(sqlite3.connect(self.db_path)) as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM source_snapshot").fetchone()[0],
                1,
            )
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM formal_source_snapshot").fetchone()[0],
                0,
            )

    def test_formal_task_contract_exact_replay_and_initial_public_row(self) -> None:
        self.assertEqual(
            getattr(state_store_module, "FORMAL_TASK_STATES", None),
            {
                "pending",
                "leased",
                "verified",
                "retryable_failed",
                "terminal_failed",
                "superseded",
            },
        )
        task_id = self.store.enqueue_formal_task(
            "formal_statement",
            "statement-v1",
            "generation-v1",
            {"security_id": "SH600001", "labels": ["年报", "审计"]},
        )

        replayed_id = self.store.enqueue_formal_task(
            "formal_statement",
            "statement-v1",
            "generation-v1",
            {"labels": ["年报", "审计"], "security_id": "SH600001"},
        )
        row = self.store.get_formal_task(task_id)

        self.assertEqual(replayed_id, task_id)
        self.assertEqual(row["id"], task_id)
        self.assertEqual(row["kind"], "formal_statement")
        self.assertEqual(row["idempotency_key"], "statement-v1")
        self.assertEqual(row["refresh_generation"], "generation-v1")
        self.assertEqual(
            row["payload"],
            {"labels": ["年报", "审计"], "security_id": "SH600001"},
        )
        self.assertEqual(row["status"], "pending")
        self.assertEqual(row["prerequisite_task_ids"], [])
        for field in (
            "lease_worker",
            "lease_expires_at",
            "next_retry_at",
            "result",
            "error",
        ):
            self.assertIsNone(row[field])
        self.assertIsNotNone(row["created_at"])
        self.assertIsNotNone(row["updated_at"])
        self.assertEqual(
            row["payload_sha256"],
            hashlib.sha256(
                '{"labels":["年报","审计"],"security_id":"SH600001"}'.encode("utf-8")
            ).hexdigest(),
        )
        self.assertIsNone(self.store.get_formal_task("missing-task"))

    def test_formal_task_replay_ignores_prerequisite_order_and_getter_sorts(self) -> None:
        first = self.store.enqueue_formal_task(
            "formal_context", "context-first", "generation-v1", {"slot": 1}
        )
        second = self.store.enqueue_formal_task(
            "formal_context", "context-second", "generation-v1", {"slot": 2}
        )
        task_id = self.store.enqueue_formal_task(
            "formal_statement",
            "statement-with-deps",
            "generation-v1",
            {"security_id": "SH600001"},
            prerequisite_task_ids=(second, first),
        )

        replayed_id = self.store.enqueue_formal_task(
            "formal_statement",
            "statement-with-deps",
            "generation-v1",
            {"security_id": "SH600001"},
            prerequisite_task_ids=(first, second),
        )

        self.assertEqual(replayed_id, task_id)
        self.assertEqual(
            self.store.get_formal_task(task_id)["prerequisite_task_ids"],
            sorted((first, second)),
        )

    def test_formal_task_idempotency_conflicts_roll_back_without_mutation(self) -> None:
        prerequisite = self.store.enqueue_formal_task(
            "formal_context", "context-v1", "generation-v1", {"slot": 1}
        )
        task_id = self.store.enqueue_formal_task(
            "formal_statement",
            "statement-v1",
            "generation-v1",
            {"security_id": "SH600001"},
            prerequisite_task_ids=(prerequisite,),
        )
        original = self.store.get_formal_task(task_id)
        conflicts = (
            ("other_kind", "generation-v1", {"security_id": "SH600001"}, (prerequisite,)),
            ("formal_statement", "generation-v2", {"security_id": "SH600001"}, (prerequisite,)),
            ("formal_statement", "generation-v1", {"security_id": "SZ000002"}, (prerequisite,)),
            ("formal_statement", "generation-v1", {"security_id": "SH600001"}, ()),
        )

        for kind, generation, payload, prerequisites in conflicts:
            with self.subTest(kind=kind, generation=generation, payload=payload, prerequisites=prerequisites):
                with self.assertRaisesRegex(ValueError, "idempotency_payload_conflict"):
                    self.store.enqueue_formal_task(
                        kind,
                        "statement-v1",
                        generation,
                        payload,
                        prerequisite_task_ids=prerequisites,
                    )

        with closing(sqlite3.connect(self.db_path)) as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM formal_collection_task").fetchone()[0],
                2,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM formal_collection_task_dependency"
                ).fetchone()[0],
                1,
            )
        self.assertEqual(self.store.get_formal_task(task_id), original)

    def test_formal_task_snapshots_caller_payload_and_rejects_invalid_inputs(self) -> None:
        payload = {"security_id": "SH600001", "nested": {"period": "2026-06-30"}}
        task_id = self.store.enqueue_formal_task(
            "formal_statement", "snapshot-v1", "generation-v1", payload
        )
        payload["security_id"] = "SZ000002"
        payload["nested"]["period"] = "2099-12-31"
        self.assertEqual(
            self.store.get_formal_task(task_id)["payload"],
            {"nested": {"period": "2026-06-30"}, "security_id": "SH600001"},
        )

        invalid_identifiers = (
            ("", "key", "generation"),
            ("kind", "", "generation"),
            ("kind", "key", ""),
            ("   ", "key", "generation"),
        )
        for kind, key, generation in invalid_identifiers:
            with self.subTest(kind=kind, key=key, generation=generation):
                with self.assertRaises(ValueError):
                    self.store.enqueue_formal_task(kind, key, generation, {})
        for payload_value in (
            [],
            {"value": math.nan},
            {"value": math.inf},
            {"value": -math.inf},
            {1: "coerced-key"},
            {"nested": {1: "coerced-key"}},
        ):
            with self.subTest(payload=payload_value):
                with self.assertRaises((TypeError, ValueError)):
                    self.store.enqueue_formal_task(
                        "formal_statement", "invalid-payload", "generation-v1", payload_value
                    )

    def test_formal_task_rejects_missing_duplicate_self_and_cyclic_prerequisites(self) -> None:
        parent = self.store.enqueue_formal_task(
            "formal_context", "parent-v1", "generation-v1", {"slot": 1}
        )
        with self.assertRaisesRegex(ValueError, "missing prerequisite"):
            self.store.enqueue_formal_task(
                "formal_statement",
                "missing-dependency",
                "generation-v1",
                {},
                prerequisite_task_ids=("missing-task",),
            )
        with self.assertRaisesRegex(ValueError, "duplicate prerequisite"):
            self.store.enqueue_formal_task(
                "formal_statement",
                "duplicate-dependency",
                "generation-v1",
                {},
                prerequisite_task_ids=(parent, parent),
            )
        with patch.object(state_store_module.uuid, "uuid4", return_value="self-task"):
            with self.assertRaisesRegex(ValueError, "self"):
                self.store.enqueue_formal_task(
                    "formal_statement",
                    "self-dependency",
                    "generation-v1",
                    {},
                    prerequisite_task_ids=("self-task",),
                )

        child = self.store.enqueue_formal_task(
            "formal_context",
            "child-v1",
            "generation-v1",
            {"slot": 2},
            prerequisite_task_ids=(parent,),
        )
        with patch.object(state_store_module.uuid, "uuid4", return_value=parent):
            with self.assertRaisesRegex(ValueError, "cycle"):
                self.store.enqueue_formal_task(
                    "formal_context",
                    "cycle-v1",
                    "generation-v1",
                    {"slot": 3},
                    prerequisite_task_ids=(child,),
                )

    def test_get_formal_task_rejects_payload_hash_and_noncanonical_json_tampering(self) -> None:
        task_id = self.store.enqueue_formal_task(
            "formal_statement", "tamper-v1", "generation-v1", {"a": 1, "b": 2}
        )
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                "UPDATE formal_collection_task SET payload_sha256 = ? WHERE id = ?",
                ("0" * 64, task_id),
            )
            connection.commit()
        with self.assertRaisesRegex(ValueError, "payload hash"):
            self.store.get_formal_task(task_id)

        canonical = '{"a":1,"b":2}'
        canonical_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                "UPDATE formal_collection_task SET payload_json = ?, payload_sha256 = ? WHERE id = ?",
                ('{"b":2, "a":1}', canonical_hash, task_id),
            )
            connection.commit()
        with self.assertRaisesRegex(ValueError, "canonical"):
            self.store.get_formal_task(task_id)

    def test_formal_lease_orders_all_ready_states_and_honors_exact_boundaries(self) -> None:
        task_ids = {
            name: self.store.enqueue_formal_task(
                "formal_statement", f"lease-{name}", "generation-v1", {"name": name}
            )
            for name in (
                "pending",
                "retry-null",
                "retry-boundary",
                "retry-future",
                "expired",
                "expiry-boundary",
                "live",
                "verified",
                "terminal",
                "superseded",
            )
        }
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                "UPDATE formal_collection_task SET created_at = ? WHERE id = ?",
                (utc_at(3), task_ids["pending"]),
            )
            for name, retry_at in (
                ("retry-null", None),
                ("retry-boundary", utc_at(10)),
                ("retry-future", utc_at(11)),
            ):
                connection.execute(
                    """UPDATE formal_collection_task
                    SET status = 'retryable_failed', next_retry_at = ?, created_at = ?
                    WHERE id = ?""",
                    (retry_at, utc_at(2), task_ids[name]),
                )
            for name, expiry, created_at in (
                ("expired", utc_at(1), utc_at(1)),
                ("expiry-boundary", utc_at(10), utc_at(1)),
                ("live", utc_at(11), utc_at(0)),
            ):
                connection.execute(
                    """UPDATE formal_collection_task
                    SET status = 'leased', lease_worker = 'old-worker',
                        lease_expires_at = ?, created_at = ? WHERE id = ?""",
                    (expiry, created_at, task_ids[name]),
                )
            for name, status in (
                ("verified", "verified"),
                ("terminal", "terminal_failed"),
                ("superseded", "superseded"),
            ):
                connection.execute(
                    "UPDATE formal_collection_task SET status = ? WHERE id = ?",
                    (status, task_ids[name]),
                )
            connection.commit()

        lease = getattr(self.store, "lease_next_formal_task", None)
        self.assertIsNotNone(lease, "formal lease API is missing")
        first_wave = [
            lease(("formal_statement",), "worker-a", 30, now_utc=utc_at(10))
            for _ in range(4)
        ]
        self.assertEqual(
            [row["id"] if row is not None else None for row in first_wave],
            [
                task_ids["expired"],
                task_ids["pending"],
                task_ids["expiry-boundary"],
                task_ids["retry-boundary"],
            ],
        )
        for row in first_wave:
            self.assertEqual(row["status"], "leased")
            self.assertEqual(row["lease_worker"], "worker-a")
            self.assertEqual(row["lease_expires_at"], utc_at(40))
            self.assertIsNone(row["next_retry_at"])
        self.assertIsNone(
            lease(("formal_statement",), "worker-a", 30, now_utc=utc_at(10))
        )

        boundary_wave = [
            lease(("formal_statement",), "worker-b", 30, now_utc=utc_at(11))
            for _ in range(2)
        ]
        self.assertEqual(
            [row["id"] for row in boundary_wave],
            [task_ids["live"], task_ids["retry-future"]],
        )
        self.assertIsNone(
            lease(("formal_statement",), "worker-b", 30, now_utc=utc_at(11))
        )

    def test_formal_lease_blocks_until_every_prerequisite_is_verified(self) -> None:
        first = self.store.enqueue_formal_task(
            "formal_context", "lease-dependency-first", "generation-v1", {}
        )
        second = self.store.enqueue_formal_task(
            "formal_context", "lease-dependency-second", "generation-v1", {}
        )
        child = self.store.enqueue_formal_task(
            "formal_statement",
            "lease-dependency-child",
            "generation-v1",
            {"security_id": "SH600001"},
            prerequisite_task_ids=(second, first),
        )

        lease = getattr(self.store, "lease_next_formal_task", None)
        self.assertIsNotNone(lease, "formal lease API is missing")
        self.assertIsNone(
            lease(("formal_statement",), "worker-a", 30, now_utc=utc_at(0))
        )
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                "UPDATE formal_collection_task SET status = 'verified' WHERE id = ?",
                (first,),
            )
            connection.commit()
        self.assertIsNone(
            lease(("formal_statement",), "worker-a", 30, now_utc=utc_at(0))
        )
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                "UPDATE formal_collection_task SET status = 'verified' WHERE id = ?",
                (second,),
            )
            connection.commit()

        leased = lease(("formal_statement",), "worker-a", 30, now_utc=utc_at(0))

        self.assertEqual(leased["id"], child)
        self.assertEqual(leased["prerequisite_task_ids"], sorted((first, second)))

    def test_formal_lease_cas_rechecks_dependency_after_candidate_selection(self) -> None:
        prerequisite = self.store.enqueue_formal_task(
            "formal_context", "lease-cas-prerequisite", "generation-v1", {}
        )
        child = self.store.enqueue_formal_task(
            "formal_statement",
            "lease-cas-child",
            "generation-v1",
            {},
            prerequisite_task_ids=(prerequisite,),
        )
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                "UPDATE formal_collection_task SET status = 'verified' WHERE id = ?",
                (prerequisite,),
            )
            connection.commit()
        real_connect = self.store._connect
        candidate_mutated = False

        class CandidateCursor:
            def __init__(self, connection, cursor):
                self.connection = connection
                self.cursor = cursor

            def fetchone(self):
                nonlocal candidate_mutated
                row = self.cursor.fetchone()
                self.connection.execute(
                    "UPDATE formal_collection_task SET status = 'pending' WHERE id = ?",
                    (prerequisite,),
                )
                candidate_mutated = True
                return row

        class ObservedConnection:
            def __init__(self, connection):
                self.connection = connection

            def __getattr__(self, name):
                return getattr(self.connection, name)

            def execute(self, sql, parameters=()):
                cursor = self.connection.execute(sql, parameters)
                if "SELECT task.*" in sql:
                    return CandidateCursor(self.connection, cursor)
                return cursor

        with patch.object(
            self.store,
            "_connect",
            side_effect=lambda: ObservedConnection(real_connect()),
        ):
            leased = self.store.lease_next_formal_task(
                ("formal_statement",), "worker-a", 30, now_utc=utc_at(0)
            )

        self.assertTrue(candidate_mutated)
        self.assertIsNone(leased)
        row = self.store.get_formal_task(child)
        self.assertEqual(row["status"], "pending")
        self.assertIsNone(row["lease_worker"])
        self.assertIsNone(row["lease_expires_at"])

    def test_two_stores_lease_one_formal_task_and_distinct_worker_takes_over(self) -> None:
        task_id = self.store.enqueue_formal_task(
            "formal_statement", "lease-contention", "generation-v1", {}
        )
        stores = (StateStore(self.db_path), StateStore(self.db_path))
        barrier = threading.Barrier(2)
        results: list[dict[str, object] | None] = []
        errors: list[BaseException] = []

        def claim(store: StateStore, worker_id: str) -> None:
            try:
                barrier.wait(timeout=5)
                results.append(
                    store.lease_next_formal_task(
                        ("formal_statement",), worker_id, 30, now_utc=utc_at(0)
                    )
                )
            except BaseException as error:
                errors.append(error)

        workers = [
            threading.Thread(target=claim, args=(store, f"worker-{index}"))
            for index, store in enumerate(stores)
        ]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=10)

        self.assertFalse(any(worker.is_alive() for worker in workers))
        self.assertEqual(errors, [])
        winners = [row for row in results if row is not None]
        self.assertEqual(len(winners), 1)
        self.assertEqual(winners[0]["id"], task_id)
        self.assertEqual(sum(row is None for row in results), 1)

        takeover = self.store.lease_next_formal_task(
            ("formal_statement",), "worker-takeover", 30, now_utc=utc_at(30)
        )
        self.assertEqual(takeover["id"], task_id)
        self.assertEqual(takeover["lease_worker"], "worker-takeover")

    def test_formal_lease_rejects_invalid_inputs_and_rolls_back_tampered_payload(self) -> None:
        self.assertIsNone(
            self.store.lease_next_formal_task((), "worker-a", 30, now_utc=utc_at(0))
        )
        for worker_id in ("", "   ", None):
            with self.subTest(worker_id=worker_id):
                with self.assertRaises(ValueError):
                    self.store.lease_next_formal_task(
                        ("formal_statement",), worker_id, 30, now_utc=utc_at(0)
                    )
        for lease_seconds in (0, -1):
            with self.subTest(lease_seconds=lease_seconds):
                with self.assertRaises(ValueError):
                    self.store.lease_next_formal_task(
                        ("formal_statement",), "worker-a", lease_seconds,
                        now_utc=utc_at(0),
                    )
        with self.assertRaisesRegex(ValueError, "timezone"):
            self.store.lease_next_formal_task(
                ("formal_statement",), "worker-a", 30,
                now_utc="2026-08-31T00:00:00",
            )

        task_id = self.store.enqueue_formal_task(
            "formal_statement", "lease-tampered", "generation-v1", {"value": 1}
        )
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                "UPDATE formal_collection_task SET payload_sha256 = ? WHERE id = ?",
                ("0" * 64, task_id),
            )
            before = connection.execute(
                "SELECT * FROM formal_collection_task WHERE id = ?", (task_id,)
            ).fetchone()
            connection.commit()

        with self.assertRaisesRegex(ValueError, "payload hash"):
            self.store.lease_next_formal_task(
                ("formal_statement",), "worker-a", 30, now_utc=utc_at(0)
            )
        with closing(sqlite3.connect(self.db_path)) as connection:
            after = connection.execute(
                "SELECT * FROM formal_collection_task WHERE id = ?", (task_id,)
            ).fetchone()
        self.assertEqual(after, before)

    def test_formal_lease_samples_implicit_time_after_writer_lock(self) -> None:
        task_id = self.store.enqueue_formal_task(
            "formal_statement", "formal-lease-lock-boundary", "generation-v1", {}
        )
        holder = sqlite3.connect(self.db_path, timeout=5, isolation_level=None)
        holder.execute("BEGIN IMMEDIATE")
        begin_attempted = threading.Event()
        clock_sampled = threading.Event()
        after_wait = threading.Event()
        sampled_before_begin: list[bool] = []
        results: list[dict[str, object] | None] = []
        errors: list[BaseException] = []
        real_connect = self.store._connect

        class ObservedConnection:
            def __init__(self, connection):
                self.connection = connection

            def __getattr__(self, name):
                return getattr(self.connection, name)

            def execute(self, sql, parameters=()):
                if sql == "BEGIN IMMEDIATE":
                    sampled_before_begin.append(clock_sampled.is_set())
                    begin_attempted.set()
                return self.connection.execute(sql, parameters)

        def controlled_now() -> str:
            clock_sampled.set()
            return utc_at(20) if after_wait.is_set() else utc_at(0)

        def claim() -> None:
            try:
                results.append(
                    self.store.lease_next_formal_task(
                        ("formal_statement",), "worker-a", 30
                    )
                )
            except BaseException as error:
                errors.append(error)

        try:
            with (
                patch.object(
                    self.store,
                    "_connect",
                    side_effect=lambda: ObservedConnection(real_connect()),
                ),
                patch("ashare_pipeline.state_store._utc_now", side_effect=controlled_now),
            ):
                worker = threading.Thread(target=claim)
                worker.start()
                self.assertTrue(begin_attempted.wait(timeout=5))
                after_wait.set()
                holder.rollback()
                worker.join(timeout=10)
        finally:
            holder.close()

        self.assertFalse(worker.is_alive())
        self.assertEqual(sampled_before_begin, [False])
        self.assertEqual(errors, [])
        self.assertEqual(results[0]["id"], task_id)
        self.assertEqual(results[0]["lease_expires_at"], utc_at(50))

    def test_complete_formal_task_canonicalizes_result_and_clears_transition_fields(self) -> None:
        prerequisite = self.store.enqueue_formal_task(
            "formal_context", "complete-prerequisite", "generation-v1", {}
        )
        task_id = self.store.enqueue_formal_task(
            "formal_feature_build",
            "complete-feature",
            "generation-v1",
            {"security_id": "SH600001"},
            prerequisite_task_ids=(prerequisite,),
        )
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                "UPDATE formal_collection_task SET status = 'verified' WHERE id = ?",
                (prerequisite,),
            )
            connection.execute(
                """UPDATE formal_collection_task
                SET error_json = ?, next_retry_at = ? WHERE id = ?""",
                ('{"code":"stale"}', utc_at(20), task_id),
            )
            connection.commit()
        self.store.lease_next_formal_task(
            ("formal_feature_build",), "worker-a", 30, now_utc=utc_at(0)
        )
        before = self.store.get_formal_task(task_id)
        result = {"z": ["完成"], "a": {"score": 1}}

        with patch("ashare_pipeline.state_store._utc_now", return_value=utc_at(1)):
            self.store.complete_formal_task(task_id, "worker-a", result)
        result["a"]["score"] = 99

        completed = self.store.get_formal_task(task_id)
        self.assertEqual(completed["status"], "verified")
        self.assertEqual(completed["result"], {"a": {"score": 1}, "z": ["完成"]})
        self.assertIsNone(completed["error"])
        self.assertIsNone(completed["next_retry_at"])
        self.assertIsNone(completed["lease_worker"])
        self.assertIsNone(completed["lease_expires_at"])
        for field in (
            "id",
            "kind",
            "idempotency_key",
            "refresh_generation",
            "payload_sha256",
            "payload",
            "prerequisite_task_ids",
            "created_at",
        ):
            self.assertEqual(completed[field], before[field], field)
        with closing(sqlite3.connect(self.db_path)) as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT result_json FROM formal_collection_task WHERE id = ?",
                    (task_id,),
                ).fetchone()[0],
                '{"a":{"score":1},"z":["完成"]}',
            )

    def test_complete_formal_task_validates_result_and_fences_final_mutation(self) -> None:
        task_id = self.store.enqueue_formal_task(
            "formal_feature_build", "complete-fencing", "generation-v1", {}
        )
        self.store.lease_next_formal_task(
            ("formal_feature_build",), "worker-a", 10, now_utc=utc_at(0)
        )
        original = self.store.get_formal_task(task_id)

        invalid_calls = (
            ("", "worker-a", {}),
            (7, "worker-a", {}),
            (task_id, "", {}),
            (task_id, 7, {}),
            (task_id, "worker-a", []),
            (task_id, "worker-a", {"value": math.nan}),
            (task_id, "worker-a", {"value": math.inf}),
        )
        for candidate_task, worker_id, result in invalid_calls:
            with self.subTest(candidate_task=candidate_task, worker_id=worker_id, result=result):
                with self.assertRaises(ValueError):
                    self.store.complete_formal_task(candidate_task, worker_id, result)
                self.assertEqual(self.store.get_formal_task(task_id), original)

        with patch("ashare_pipeline.state_store._utc_now", return_value=utc_at(1)):
            with self.assertRaisesRegex(ValueError, "unexpired lease owner"):
                self.store.complete_formal_task(task_id, "worker-b", {})
        with patch("ashare_pipeline.state_store._utc_now", return_value=utc_at(10)):
            with self.assertRaisesRegex(ValueError, "unexpired lease owner"):
                self.store.complete_formal_task(task_id, "worker-a", {})
        self.assertEqual(self.store.get_formal_task(task_id), original)

        self.store.lease_next_formal_task(
            ("formal_feature_build",), "worker-new", 20, now_utc=utc_at(10)
        )
        taken_over = self.store.get_formal_task(task_id)
        with patch("ashare_pipeline.state_store._utc_now", return_value=utc_at(11)):
            with self.assertRaisesRegex(ValueError, "unexpired lease owner"):
                self.store.complete_formal_task(task_id, "worker-a", {})
            self.store.complete_formal_task(task_id, "worker-new", {"ok": True})
            with self.assertRaisesRegex(ValueError, "unexpired lease owner"):
                self.store.complete_formal_task(task_id, "worker-new", {"ok": True})
            with self.assertRaisesRegex(ValueError, "unexpired lease owner"):
                self.store.complete_formal_task("missing-task", "worker-new", {})
        self.assertEqual(taken_over["payload"], self.store.get_formal_task(task_id)["payload"])

    def test_complete_formal_task_samples_time_after_result_serialization(self) -> None:
        task_id = self.store.enqueue_formal_task(
            "formal_feature_build", "complete-serialization", "generation-v1", {}
        )
        self.store.lease_next_formal_task(
            ("formal_feature_build",), "worker-a", 10, now_utc=utc_at(0)
        )
        before = self.store.get_formal_task(task_id)
        result = {"code": "late"}
        serialization_finished = False
        real_canonical = state_store_module._canonical_mapping_json

        def observed_canonical(value, field):
            nonlocal serialization_finished
            canonical = real_canonical(value, field)
            if value is result:
                serialization_finished = True
            return canonical

        def controlled_now() -> str:
            return utc_at(11) if serialization_finished else utc_at(9)

        with (
            patch(
                "ashare_pipeline.state_store._canonical_mapping_json",
                side_effect=observed_canonical,
            ),
            patch("ashare_pipeline.state_store._utc_now", side_effect=controlled_now),
        ):
            with self.assertRaisesRegex(ValueError, "unexpired lease owner"):
                self.store.complete_formal_task(task_id, "worker-a", result)
        self.assertEqual(self.store.get_formal_task(task_id), before)

    def test_complete_formal_source_task_requires_one_valid_exact_receipt(self) -> None:
        missing_id = self.store.enqueue_formal_task(
            "formal_statement", "complete-source-missing", "generation-v1", {}
        )
        self.store.lease_next_formal_task(
            ("formal_statement",), "worker-missing", 30, now_utc=utc_at(0)
        )
        missing_before = self.store.get_formal_task(missing_id)
        with patch("ashare_pipeline.state_store._utc_now", return_value=utc_at(1)):
            with self.assertRaisesRegex(ValueError, "receipt"):
                self.store.complete_formal_task(missing_id, "worker-missing", {})
        self.assertEqual(self.store.get_formal_task(missing_id), missing_before)

        for index, kind in enumerate(
            ("formal_statement", "formal_context", "formal_universe_source")
        ):
            with self.subTest(kind=kind):
                path = Path(self.tempdir.name) / f"complete-source-{index}.sqlite3"
                task_store = StateStore(path)
                task_store.initialize()
                generation = f"source-generation-{index}"
                task_id = task_store.enqueue_formal_task(
                    kind, f"complete-source-{index}", generation, {}
                )
                task_store.lease_next_formal_task(
                    (kind,), "worker-a", 30, now_utc=utc_at(0)
                )
                raw_store, fetch, stored, verification = written_formal_snapshot(
                    Path(self.tempdir.name) / f"complete-source-raw-{index}",
                    refresh_generation=generation,
                    producing_task_id=task_id,
                )
                configured = StateStore(path, formal_snapshot_store=raw_store)
                with patch(
                    "ashare_pipeline.state_store._utc_now", return_value=utc_at(1)
                ):
                    ref = configured.put_formal_snapshot_for_leased_task(
                        fetch,
                        stored,
                        verification,
                        task_id=task_id,
                        worker_id="worker-a",
                    )
                with patch(
                    "ashare_pipeline.state_store._utc_now", return_value=utc_at(2)
                ):
                    configured.complete_formal_task(
                        task_id, "worker-a", {"snapshot_id": ref.snapshot_id}
                    )
                self.assertEqual(configured.get_formal_task(task_id)["status"], "verified")
                self.assertEqual(
                    configured.get_formal_task_snapshot_receipt(task_id)["snapshot_id"],
                    ref.snapshot_id,
                )

    def test_complete_formal_source_task_rejects_invalid_receipt_graph_without_mutation(self) -> None:
        mutations = (
            ("formal_task_snapshot_receipt", "refresh_generation", "wrong-generation"),
            ("formal_source_snapshot", "producing_task_id", None),
            ("formal_source_snapshot", "manifest_sha256", "0" * 64),
        )
        for index, (table, column, value) in enumerate(mutations):
            with self.subTest(table=table, column=column):
                path = Path(self.tempdir.name) / f"complete-invalid-receipt-{index}.sqlite3"
                task_store = StateStore(path)
                task_store.initialize()
                task_id = task_store.enqueue_formal_task(
                    "formal_statement",
                    f"complete-invalid-receipt-{index}",
                    "receipt-generation",
                    {},
                )
                task_store.lease_next_formal_task(
                    ("formal_statement",), "worker-a", 30, now_utc=utc_at(0)
                )
                raw_store, fetch, stored, verification = written_formal_snapshot(
                    Path(self.tempdir.name) / f"complete-invalid-receipt-raw-{index}",
                    refresh_generation="receipt-generation",
                    producing_task_id=task_id,
                )
                configured = StateStore(path, formal_snapshot_store=raw_store)
                snapshot_id, _ = self.insert_formal_receipt_fixture(
                    db_path=path,
                    task_id=task_id,
                    raw_store=raw_store,
                    fetch=fetch,
                    stored=stored,
                    verification=verification,
                )
                target_id = task_id if table == "formal_task_snapshot_receipt" else snapshot_id
                id_column = "task_id" if table == "formal_task_snapshot_receipt" else "id"
                with closing(sqlite3.connect(path)) as connection:
                    connection.execute("PRAGMA foreign_keys = OFF")
                    connection.execute(
                        f"UPDATE {table} SET {column} = ? WHERE {id_column} = ?",
                        (value, target_id),
                    )
                    before = connection.execute(
                        "SELECT * FROM formal_collection_task WHERE id = ?", (task_id,)
                    ).fetchone()
                    connection.commit()

                with patch(
                    "ashare_pipeline.state_store._utc_now", return_value=utc_at(1)
                ):
                    with self.assertRaises(ValueError):
                        configured.complete_formal_task(task_id, "worker-a", {})
                with closing(sqlite3.connect(path)) as connection:
                    after = connection.execute(
                        "SELECT * FROM formal_collection_task WHERE id = ?", (task_id,)
                    ).fetchone()
                self.assertEqual(after, before)

    def test_complete_formal_task_resamples_time_after_receipt_validation(self) -> None:
        generation = "completion-receipt-time-generation"
        task_id = self.store.enqueue_formal_task(
            "formal_statement", "completion-receipt-time", generation, {}
        )
        self.store.lease_next_formal_task(
            ("formal_statement",), "worker-a", 10, now_utc=utc_at(0)
        )
        raw_store, fetch, stored, verification = written_formal_snapshot(
            Path(self.tempdir.name) / "completion-receipt-time-raw",
            refresh_generation=generation,
            producing_task_id=task_id,
        )
        configured = StateStore(self.db_path, formal_snapshot_store=raw_store)
        with patch("ashare_pipeline.state_store._utc_now", return_value=utc_at(1)):
            configured.put_formal_snapshot_for_leased_task(
                fetch,
                stored,
                verification,
                task_id=task_id,
                worker_id="worker-a",
            )
        before = configured.get_formal_task(task_id)
        receipt_validated = False
        real_receipt = configured._formal_task_snapshot_receipt_from_connection

        def observed_receipt(connection, candidate_task_id):
            nonlocal receipt_validated
            receipt = real_receipt(connection, candidate_task_id)
            receipt_validated = True
            return receipt

        def controlled_now() -> str:
            return utc_at(11) if receipt_validated else utc_at(9)

        with (
            patch.object(
                configured,
                "_formal_task_snapshot_receipt_from_connection",
                side_effect=observed_receipt,
            ),
            patch("ashare_pipeline.state_store._utc_now", side_effect=controlled_now),
        ):
            with self.assertRaisesRegex(ValueError, "unexpired lease owner"):
                configured.complete_formal_task(task_id, "worker-a", {"ok": True})

        self.assertTrue(receipt_validated)
        self.assertEqual(configured.get_formal_task(task_id), before)

    def test_complete_formal_task_fails_closed_for_finalizer_and_rolls_back_update_failure(self) -> None:
        finalizer_id = self.store.enqueue_formal_task(
            "formal_universe_finalize", "complete-finalizer", "generation-v1", {}
        )
        self.store.lease_next_formal_task(
            ("formal_universe_finalize",), "worker-finalizer", 30, now_utc=utc_at(0)
        )
        finalizer_before = self.store.get_formal_task(finalizer_id)
        with patch("ashare_pipeline.state_store._utc_now", return_value=utc_at(1)):
            with self.assertRaisesRegex(ValueError, "universe.*proof|finalizer"):
                self.store.complete_formal_task(
                    finalizer_id, "worker-finalizer", {"snapshot_id": "arbitrary"}
                )
        self.assertEqual(self.store.get_formal_task(finalizer_id), finalizer_before)

        task_id = self.store.enqueue_formal_task(
            "formal_feature_build", "complete-trigger-rollback", "generation-v1", {}
        )
        self.store.lease_next_formal_task(
            ("formal_feature_build",), "worker-a", 30, now_utc=utc_at(0)
        )
        before = self.store.get_formal_task(task_id)
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                """CREATE TRIGGER force_formal_completion_failure
                BEFORE UPDATE ON formal_collection_task
                WHEN OLD.id = '%s' AND NEW.status = 'verified'
                BEGIN SELECT RAISE(ABORT, 'forced formal completion failure'); END"""
                % task_id
            )
            connection.commit()
        with patch("ashare_pipeline.state_store._utc_now", return_value=utc_at(1)):
            with self.assertRaises(sqlite3.IntegrityError):
                self.store.complete_formal_task(task_id, "worker-a", {"ok": True})
        self.assertEqual(self.store.get_formal_task(task_id), before)

        legacy_id, _ = self.store.record_snapshot(
            "cninfo", "annual_report", "request", "payload", "legacy.json", 1, utc_at(0)
        )
        source_id = self.store.enqueue_formal_task(
            "formal_statement", "complete-legacy-isolation", "generation-v1", {}
        )
        self.store.lease_next_formal_task(
            ("formal_statement",), "worker-source", 30, now_utc=utc_at(0)
        )
        with patch("ashare_pipeline.state_store._utc_now", return_value=utc_at(1)):
            with self.assertRaisesRegex(ValueError, "receipt"):
                self.store.complete_formal_task(
                    source_id, "worker-source", {"snapshot_id": legacy_id}
                )
        self.assertEqual(self.store.get_formal_task(source_id)["status"], "leased")

    def test_supersede_formal_tasks_matches_exact_scope_and_preserves_audit_rows(self) -> None:
        prerequisite = self.store.enqueue_formal_task(
            "formal_context", "supersede-prerequisite", "generation-current", {}
        )
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                "UPDATE formal_collection_task SET status = 'verified' WHERE id = ?",
                (prerequisite,),
            )
            connection.commit()
        old_pending = self.store.enqueue_formal_task(
            "formal_feature_build",
            "supersede-old-pending",
            "generation-z",
            {"security_id": "SH600001", "nested": {"slot": 1}},
        )
        old_leased = self.store.enqueue_formal_task(
            "formal_statement",
            "supersede-old-leased",
            "generation-a",
            {"security_id": "SH600001", "nested": {"slot": 1}},
            prerequisite_task_ids=(prerequisite,),
        )
        old_retry = self.store.enqueue_formal_task(
            "formal_feature_build",
            "supersede-old-retry",
            "generation-z",
            {"security_id": "SH600001", "nested": {"slot": 1}},
        )
        current = self.store.enqueue_formal_task(
            "formal_feature_build",
            "supersede-current",
            "generation-current",
            {"security_id": "SH600001", "nested": {"slot": 1}},
        )
        other_scope = self.store.enqueue_formal_task(
            "formal_feature_build",
            "supersede-other-scope",
            "generation-a",
            {"security_id": "SZ000002", "nested": {"slot": 1}},
        )
        nested_not_exact = self.store.enqueue_formal_task(
            "formal_feature_build",
            "supersede-nested-not-exact",
            "generation-a",
            {"security_id": "SH600001", "nested": {"slot": 1, "extra": True}},
        )
        terminal_ids = {
            status: self.store.enqueue_formal_task(
                "formal_feature_build",
                f"supersede-{status}",
                "generation-a",
                {"security_id": "SH600001", "nested": {"slot": 1}},
            )
            for status in ("verified", "terminal_failed", "superseded")
        }
        self.store.lease_next_formal_task(
            ("formal_statement",), "worker-old", 30, now_utc=utc_at(0)
        )
        raw_store, fetch, stored, verification = written_formal_snapshot(
            Path(self.tempdir.name) / "supersede-receipt-raw",
            refresh_generation="generation-a",
            producing_task_id=old_leased,
        )
        configured = StateStore(self.db_path, formal_snapshot_store=raw_store)
        with patch("ashare_pipeline.state_store._utc_now", return_value=utc_at(1)):
            ref = configured.put_formal_snapshot_for_leased_task(
                fetch,
                stored,
                verification,
                task_id=old_leased,
                worker_id="worker-old",
            )
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                """UPDATE formal_collection_task
                SET status = 'retryable_failed', next_retry_at = ?, result_json = ?,
                    error_json = ? WHERE id = ?""",
                (utc_at(20), '{"keep":"result"}', '{"code":"retry"}', old_retry),
            )
            connection.execute(
                "UPDATE formal_collection_task SET result_json = ?, error_json = ? WHERE id = ?",
                ('{"keep":"leased-result"}', '{"code":"leased-error"}', old_leased),
            )
            for status, candidate_id in terminal_ids.items():
                connection.execute(
                    "UPDATE formal_collection_task SET status = ? WHERE id = ?",
                    (status, candidate_id),
                )
            connection.commit()

        selected = (old_pending, old_leased, old_retry)
        untouched = (current, other_scope, nested_not_exact, *terminal_ids.values())
        before_selected = {task_id: configured.get_formal_task(task_id) for task_id in selected}
        before_untouched = {task_id: configured.get_formal_task(task_id) for task_id in untouched}

        with patch("ashare_pipeline.state_store._utc_now", return_value=utc_at(2)):
            changed = configured.supersede_formal_tasks(
                {"nested": {"slot": 1}, "security_id": "SH600001"},
                "generation-current",
            )

        self.assertEqual(changed, 3)
        for task_id in selected:
            after = configured.get_formal_task(task_id)
            self.assertEqual(after["status"], "superseded")
            self.assertIsNone(after["lease_worker"])
            self.assertIsNone(after["lease_expires_at"])
            self.assertIsNone(after["next_retry_at"])
            for field in (
                "id",
                "kind",
                "idempotency_key",
                "refresh_generation",
                "payload_sha256",
                "payload",
                "result",
                "error",
                "prerequisite_task_ids",
                "created_at",
            ):
                self.assertEqual(after[field], before_selected[task_id][field], field)
        for task_id in untouched:
            self.assertEqual(configured.get_formal_task(task_id), before_untouched[task_id])
        self.assertEqual(
            configured.get_formal_task_snapshot_receipt(old_leased)["snapshot_id"],
            ref.snapshot_id,
        )

        with patch("ashare_pipeline.state_store._utc_now", return_value=utc_at(3)):
            self.assertEqual(
                configured.supersede_formal_tasks(
                    {"nested": {"slot": 1}, "security_id": "SH600001"},
                    "generation-current",
                ),
                0,
            )

    def test_supersede_formal_tasks_validates_scope_and_immediately_fences_owner(self) -> None:
        task_id = self.store.enqueue_formal_task(
            "formal_feature_build",
            "supersede-validation",
            "generation-old",
            {"security_id": "SH600001"},
        )
        self.store.lease_next_formal_task(
            ("formal_feature_build",), "worker-old", 30, now_utc=utc_at(0)
        )
        before = self.store.get_formal_task(task_id)
        for scope, generation in (
            ({}, "generation-current"),
            ([], "generation-current"),
            ({"value": math.nan}, "generation-current"),
            ({1: "coerced"}, "generation-current"),
            ({"security_id": "SH600001"}, ""),
            ({"security_id": "SH600001"}, 7),
        ):
            with self.subTest(scope=scope, generation=generation):
                with self.assertRaises(ValueError):
                    self.store.supersede_formal_tasks(scope, generation)
                self.assertEqual(self.store.get_formal_task(task_id), before)

        with patch("ashare_pipeline.state_store._utc_now", return_value=utc_at(1)):
            self.assertEqual(
                self.store.supersede_formal_tasks(
                    {"security_id": "SH600001"}, "generation-current"
                ),
                1,
            )
            for operation in (
                lambda: self.store.renew_formal_task_lease(
                    task_id, "worker-old", 30, now_utc=utc_at(1)
                ),
                lambda: self.store.complete_formal_task(task_id, "worker-old", {}),
                lambda: self.store.fail_formal_task(
                    task_id, "worker-old", {"code": "late"}, "terminal_failed", None
                ),
            ):
                with self.subTest(operation=operation):
                    with self.assertRaisesRegex(ValueError, "unexpired lease owner"):
                        operation()
        self.assertEqual(self.store.get_formal_task(task_id)["status"], "superseded")

    def test_supersede_formal_tasks_rolls_back_when_candidate_changes_before_cas(self) -> None:
        task_id = self.store.enqueue_formal_task(
            "formal_feature_build",
            "supersede-cas",
            "generation-old",
            {"security_id": "SH600001"},
        )
        before = self.store.get_formal_task(task_id)
        real_connect = self.store._connect
        changed_before_cas = False

        class ObservedConnection:
            def __init__(self, connection):
                self.connection = connection

            def __getattr__(self, name):
                return getattr(self.connection, name)

            def execute(self, sql, parameters=()):
                nonlocal changed_before_cas
                if "SET status = 'superseded'" in sql and not changed_before_cas:
                    self.connection.execute(
                        """UPDATE formal_collection_task
                        SET payload_json = ?, payload_sha256 = ? WHERE id = ?""",
                        (
                            '{"security_id":"SZ000002"}',
                            hashlib.sha256(
                                b'{"security_id":"SZ000002"}'
                            ).hexdigest(),
                            task_id,
                        ),
                    )
                    changed_before_cas = True
                return self.connection.execute(sql, parameters)

        with (
            patch.object(
                self.store,
                "_connect",
                side_effect=lambda: ObservedConnection(real_connect()),
            ),
            patch("ashare_pipeline.state_store._utc_now", return_value=utc_at(1)),
        ):
            with self.assertRaisesRegex(ValueError, "changed during supersession"):
                self.store.supersede_formal_tasks(
                    {"security_id": "SH600001"}, "generation-current"
                )

        self.assertTrue(changed_before_cas)
        self.assertEqual(self.store.get_formal_task(task_id), before)

    def test_renew_formal_lease_uses_current_time_and_preserves_task_content(self) -> None:
        prerequisite = self.store.enqueue_formal_task(
            "formal_context", "renew-prerequisite", "generation-v1", {}
        )
        task_id = self.store.enqueue_formal_task(
            "formal_statement",
            "renew-task",
            "generation-v1",
            {"nested": {"value": 1}},
            prerequisite_task_ids=(prerequisite,),
        )
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                "UPDATE formal_collection_task SET status = 'verified' WHERE id = ?",
                (prerequisite,),
            )
            connection.commit()
        self.store.lease_next_formal_task(
            ("formal_statement",), "worker-a", 100, now_utc=utc_at(0)
        )
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                """UPDATE formal_collection_task
                SET result_json = ?, error_json = ? WHERE id = ?""",
                ('{"receipt":"keep"}', '{"code":"keep"}', task_id),
            )
            connection.commit()
        before = self.store.get_formal_task(task_id)

        expiry = self.store.renew_formal_task_lease(
            task_id, "worker-a", 40, now_utc="2026-08-31T08:00:10+08:00"
        )

        after = self.store.get_formal_task(task_id)
        self.assertEqual(expiry, utc_at(50))
        self.assertEqual(after["lease_expires_at"], utc_at(50))
        for field in (
            "id",
            "kind",
            "idempotency_key",
            "refresh_generation",
            "payload_sha256",
            "payload",
            "result",
            "error",
            "prerequisite_task_ids",
            "status",
            "lease_worker",
        ):
            self.assertEqual(after[field], before[field], field)

    def test_renew_formal_lease_fences_wrong_owner_and_exact_expiry_without_mutation(self) -> None:
        task_id = self.store.enqueue_formal_task(
            "formal_statement", "renew-fencing", "generation-v1", {}
        )
        self.store.lease_next_formal_task(
            ("formal_statement",), "worker-a", 30, now_utc=utc_at(0)
        )
        before = self.store.get_formal_task(task_id)

        for worker_id, now in (("worker-b", utc_at(1)), ("worker-a", utc_at(30))):
            with self.subTest(worker_id=worker_id, now=now):
                with self.assertRaisesRegex(ValueError, "unexpired lease owner"):
                    self.store.renew_formal_task_lease(
                        task_id, worker_id, 30, now_utc=now
                    )
                self.assertEqual(self.store.get_formal_task(task_id), before)
        for task, worker_id, duration, now in (
            (task_id, "", 30, utc_at(1)),
            (task_id, "worker-a", 0, utc_at(1)),
            (task_id, "worker-a", -1, utc_at(1)),
            (task_id, "worker-a", 30, "2026-08-31T00:00:01"),
            ("missing-task", "worker-a", 30, utc_at(1)),
        ):
            with self.subTest(task=task, worker_id=worker_id, duration=duration, now=now):
                with self.assertRaises(ValueError):
                    self.store.renew_formal_task_lease(
                        task, worker_id, duration, now_utc=now
                    )
        self.assertEqual(self.store.get_formal_task(task_id), before)

    def test_fail_formal_task_retries_at_boundary_and_terminal_failure_is_permanent(self) -> None:
        retry_id = self.store.enqueue_formal_task(
            "formal_statement", "formal-fail-retry", "generation-v1", {"value": 1}
        )
        self.store.lease_next_formal_task(
            ("formal_statement",), "worker-a", 30, now_utc=utc_at(-10)
        )
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                "UPDATE formal_collection_task SET result_json = ? WHERE id = ?",
                ('{"receipt":"keep"}', retry_id),
            )
            connection.commit()
        error = {"nested": {"attempt": 1}, "code": "timeout"}
        with patch("ashare_pipeline.state_store._utc_now", return_value=utc_at(0)):
            self.store.fail_formal_task(
                retry_id,
                "worker-a",
                error,
                "retryable_failed",
                "2026-08-31T08:00:00+08:00",
            )
        error["nested"]["attempt"] = 2

        failed = self.store.get_formal_task(retry_id)
        self.assertEqual(failed["status"], "retryable_failed")
        self.assertEqual(failed["next_retry_at"], utc_at(0))
        self.assertEqual(failed["error"], {"code": "timeout", "nested": {"attempt": 1}})
        self.assertEqual(failed["result"], {"receipt": "keep"})
        self.assertIsNone(failed["lease_worker"])
        self.assertIsNone(failed["lease_expires_at"])
        retry = self.store.lease_next_formal_task(
            ("formal_statement",), "worker-b", 30, now_utc=utc_at(0)
        )
        self.assertEqual(retry["id"], retry_id)

        terminal_id = self.store.enqueue_formal_task(
            "formal_terminal_fixture", "formal-fail-terminal", "generation-v1", {}
        )
        self.store.lease_next_formal_task(
            ("formal_terminal_fixture",), "worker-terminal", 30, now_utc=utc_at(1)
        )
        with patch("ashare_pipeline.state_store._utc_now", return_value=utc_at(2)):
            self.store.fail_formal_task(
                terminal_id,
                "worker-terminal",
                {"code": "permanent"},
                "terminal_failed",
                None,
            )
        terminal = self.store.get_formal_task(terminal_id)
        self.assertEqual(terminal["status"], "terminal_failed")
        self.assertIsNone(terminal["next_retry_at"])
        self.assertIsNone(
            self.store.lease_next_formal_task(
                ("formal_terminal_fixture",), "worker-c", 30, now_utc=utc_at(100)
            )
        )

    def test_fail_formal_task_validates_inputs_and_fences_owner_at_final_update(self) -> None:
        task_id = self.store.enqueue_formal_task(
            "formal_statement", "formal-fail-validation", "generation-v1", {}
        )
        self.store.lease_next_formal_task(
            ("formal_statement",), "worker-a", 10, now_utc=utc_at(0)
        )
        before = self.store.get_formal_task(task_id)
        invalid_calls = (
            ("", {"code": "bad"}, "terminal_failed", None),
            ("worker-a", [], "terminal_failed", None),
            ("worker-a", {"value": math.nan}, "terminal_failed", None),
            ("worker-a", {"code": "bad"}, "pending", None),
            ("worker-a", {"code": "bad"}, [], None),
            ("worker-a", {"code": "bad"}, "retryable_failed", None),
            ("worker-a", {"code": "bad"}, "terminal_failed", utc_at(20)),
            (
                "worker-a",
                {"code": "bad"},
                "retryable_failed",
                "2026-08-31T00:00:20",
            ),
        )
        for worker_id, error, status, retry_at in invalid_calls:
            with self.subTest(worker_id=worker_id, error=error, status=status):
                with self.assertRaises(ValueError):
                    self.store.fail_formal_task(
                        task_id, worker_id, error, status, retry_at
                    )
                self.assertEqual(self.store.get_formal_task(task_id), before)

        with patch("ashare_pipeline.state_store._utc_now", return_value=utc_at(1)):
            with self.assertRaisesRegex(ValueError, "unexpired lease owner"):
                self.store.fail_formal_task(
                    task_id,
                    "worker-b",
                    {"code": "wrong-owner"},
                    "terminal_failed",
                    None,
                )
        self.assertEqual(self.store.get_formal_task(task_id), before)
        with patch("ashare_pipeline.state_store._utc_now", return_value=utc_at(10)):
            with self.assertRaisesRegex(ValueError, "unexpired lease owner"):
                self.store.fail_formal_task(
                    task_id,
                    "worker-a",
                    {"code": "expired"},
                    "terminal_failed",
                    None,
                )
        self.assertEqual(self.store.get_formal_task(task_id), before)

    def test_expired_formal_owner_is_fenced_after_distinct_worker_takeover(self) -> None:
        task_id = self.store.enqueue_formal_task(
            "formal_statement", "formal-takeover-fencing", "generation-v1", {}
        )
        self.store.lease_next_formal_task(
            ("formal_statement",), "worker-old", 10, now_utc=utc_at(0)
        )
        self.store.lease_next_formal_task(
            ("formal_statement",), "worker-new", 30, now_utc=utc_at(10)
        )
        before = self.store.get_formal_task(task_id)

        with self.assertRaisesRegex(ValueError, "unexpired lease owner"):
            self.store.renew_formal_task_lease(
                task_id, "worker-old", 30, now_utc=utc_at(11)
            )
        with patch("ashare_pipeline.state_store._utc_now", return_value=utc_at(11)):
            with self.assertRaisesRegex(ValueError, "unexpired lease owner"):
                self.store.fail_formal_task(
                    task_id,
                    "worker-old",
                    {"code": "stale-owner"},
                    "terminal_failed",
                    None,
                )
        self.assertEqual(self.store.get_formal_task(task_id), before)

    def test_fail_formal_task_samples_time_after_error_serialization(self) -> None:
        task_id = self.store.enqueue_formal_task(
            "formal_statement", "formal-fail-serialization", "generation-v1", {}
        )
        self.store.lease_next_formal_task(
            ("formal_statement",), "worker-a", 10, now_utc=utc_at(0)
        )
        before = self.store.get_formal_task(task_id)
        error = {"code": "late"}
        serialization_finished = False
        real_canonical = state_store_module._canonical_mapping_json

        def observed_canonical(value, field):
            nonlocal serialization_finished
            result = real_canonical(value, field)
            if value is error:
                serialization_finished = True
            return result

        def controlled_now() -> str:
            return utc_at(11) if serialization_finished else utc_at(9)

        with (
            patch(
                "ashare_pipeline.state_store._canonical_mapping_json",
                side_effect=observed_canonical,
            ),
            patch("ashare_pipeline.state_store._utc_now", side_effect=controlled_now),
        ):
            with self.assertRaisesRegex(ValueError, "unexpired lease owner"):
                self.store.fail_formal_task(
                    task_id, "worker-a", error, "terminal_failed", None
                )
        self.assertEqual(self.store.get_formal_task(task_id), before)

    def test_resolve_formal_task_dependencies_cascades_terminal_and_superseded(self) -> None:
        terminal_parent = self.store.enqueue_formal_task(
            "formal_context", "terminal-parent", "generation-v1", {}
        )
        child = self.store.enqueue_formal_task(
            "formal_statement",
            "terminal-child",
            "generation-v1",
            {},
            prerequisite_task_ids=(terminal_parent,),
        )
        grandchild = self.store.enqueue_formal_task(
            "formal_feature",
            "terminal-grandchild",
            "generation-v1",
            {},
            prerequisite_task_ids=(child,),
        )
        superseded_parent = self.store.enqueue_formal_task(
            "formal_context", "superseded-parent", "generation-v1", {}
        )
        superseded_child = self.store.enqueue_formal_task(
            "formal_statement",
            "superseded-child",
            "generation-v1",
            {},
            prerequisite_task_ids=(superseded_parent,),
        )
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                "UPDATE formal_collection_task SET status = 'terminal_failed' WHERE id = ?",
                (terminal_parent,),
            )
            connection.execute(
                "UPDATE formal_collection_task SET status = 'superseded' WHERE id = ?",
                (superseded_parent,),
            )
            connection.commit()

        self.assertEqual(self.store.resolve_formal_task_dependencies(), 3)
        self.assertEqual(self.store.get_formal_task(child)["status"], "terminal_failed")
        self.assertEqual(self.store.get_formal_task(grandchild)["status"], "terminal_failed")
        superseded_row = self.store.get_formal_task(superseded_child)
        self.assertEqual(superseded_row["status"], "terminal_failed")
        self.assertEqual(
            superseded_row["error"],
            {
                "blocking_prerequisite_task_ids": [superseded_parent],
                "code": "prerequisite_terminal_failed",
            },
        )
        self.assertEqual(self.store.resolve_formal_task_dependencies(), 0)

    def test_resolve_formal_task_dependencies_sorts_blockers_and_clears_retry_state(self) -> None:
        first = self.store.enqueue_formal_task(
            "formal_context", "blocking-first", "generation-v1", {}
        )
        second = self.store.enqueue_formal_task(
            "formal_context", "blocking-second", "generation-v1", {}
        )
        child = self.store.enqueue_formal_task(
            "formal_statement",
            "retryable-child",
            "generation-v1",
            {},
            prerequisite_task_ids=(second, first),
        )
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                "UPDATE formal_collection_task SET status = 'terminal_failed' WHERE id = ?",
                (first,),
            )
            connection.execute(
                "UPDATE formal_collection_task SET status = 'superseded' WHERE id = ?",
                (second,),
            )
            connection.execute(
                """UPDATE formal_collection_task
                SET status = 'retryable_failed', next_retry_at = ?,
                    result_json = ?, error_json = ? WHERE id = ?""",
                (utc_at(20), '{"stale":true}', '{"code":"retry"}', child),
            )
            connection.commit()

        self.assertEqual(self.store.resolve_formal_task_dependencies(), 1)
        row = self.store.get_formal_task(child)
        self.assertEqual(row["status"], "terminal_failed")
        self.assertEqual(
            row["error"],
            {
                "blocking_prerequisite_task_ids": sorted((first, second)),
                "code": "prerequisite_terminal_failed",
            },
        )
        self.assertIsNone(row["result"])
        self.assertIsNone(row["next_retry_at"])
        self.assertIsNone(row["lease_worker"])
        self.assertIsNone(row["lease_expires_at"])

    def test_resolve_formal_task_dependencies_does_not_rewrite_leased_child(self) -> None:
        parent = self.store.enqueue_formal_task(
            "formal_context", "leased-parent", "generation-v1", {}
        )
        child = self.store.enqueue_formal_task(
            "formal_statement",
            "leased-child",
            "generation-v1",
            {},
            prerequisite_task_ids=(parent,),
        )
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                "UPDATE formal_collection_task SET status = 'terminal_failed' WHERE id = ?",
                (parent,),
            )
            connection.execute(
                """UPDATE formal_collection_task SET status = 'leased', lease_worker = ?,
                lease_expires_at = ?, error_json = ? WHERE id = ?""",
                ("worker-a", utc_at(30), '{"code":"keep"}', child),
            )
            before = connection.execute(
                "SELECT * FROM formal_collection_task WHERE id = ?", (child,)
            ).fetchone()
            connection.commit()

        with patch("ashare_pipeline.state_store._utc_now", return_value=utc_at(10)):
            self.assertEqual(self.store.resolve_formal_task_dependencies(), 0)
        with closing(sqlite3.connect(self.db_path)) as connection:
            after = connection.execute(
                "SELECT * FROM formal_collection_task WHERE id = ?", (child,)
            ).fetchone()
        self.assertEqual(after, before)

    def test_resolve_formal_task_dependencies_terminalizes_exactly_expired_lease(self) -> None:
        parent = self.store.enqueue_formal_task(
            "formal_context", "expired-child-parent", "generation-v1", {}
        )
        child = self.store.enqueue_formal_task(
            "formal_statement",
            "expired-child",
            "generation-v1",
            {},
            prerequisite_task_ids=(parent,),
        )
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                "UPDATE formal_collection_task SET status = 'terminal_failed' WHERE id = ?",
                (parent,),
            )
            connection.execute(
                """UPDATE formal_collection_task SET status = 'leased',
                lease_worker = 'worker-old', lease_expires_at = ?, next_retry_at = ?,
                result_json = ?, error_json = ? WHERE id = ?""",
                (
                    utc_at(10),
                    utc_at(20),
                    '{"stale":true}',
                    '{"code":"old"}',
                    child,
                ),
            )
            connection.commit()

        with patch("ashare_pipeline.state_store._utc_now", return_value=utc_at(10)):
            self.assertEqual(self.store.resolve_formal_task_dependencies(), 1)

        row = self.store.get_formal_task(child)
        self.assertEqual(row["status"], "terminal_failed")
        self.assertEqual(
            row["error"],
            {
                "blocking_prerequisite_task_ids": [parent],
                "code": "prerequisite_terminal_failed",
            },
        )
        self.assertIsNone(row["lease_worker"])
        self.assertIsNone(row["lease_expires_at"])
        self.assertIsNone(row["next_retry_at"])
        self.assertIsNone(row["result"])
        self.assertIsNone(
            self.store.lease_next_formal_task(
                ("formal_statement",), "worker-new", 30, now_utc=utc_at(11)
            )
        )

    def test_formal_task_operations_leave_legacy_queue_contract_untouched(self) -> None:
        legacy_id = self.store.enqueue_job("legacy", "legacy-v1", {"value": 1})
        formal_id = self.store.enqueue_formal_task(
            "formal_context", "formal-v1", "generation-v1", {"value": 2}
        )

        self.assertEqual(self.store.get_job(legacy_id)["status"], "pending")
        self.assertEqual(self.store.get_job(legacy_id)["payload"], {"value": 1})
        self.assertEqual(self.store.get_formal_task(formal_id)["status"], "pending")
        self.assertEqual(
            state_store_module.JOB_STATES,
            {"pending", "running", "succeeded", "retryable_failed", "terminal_failed"},
        )

    def test_v3_foreign_keys_reject_missing_snapshot_and_feature_set(self) -> None:
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """INSERT INTO financial_fact VALUES
                    (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        "fact-1", "SH600001", "income", "revenue", utc_at(0),
                        "2026-06-30", "H1", 100.0, "CNY", "duration", utc_at(0),
                        utc_at(0), None, "missing-snapshot", "revenue", "raw-hash-1",
                        "mapping-v1", utc_at(1),
                    ),
                )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO feature_value VALUES (?,?,?,?,?,?,?,?,?,?)",
                    ("missing-set", "G", "revenue_growth", "FY0", 0.1, "ratio", "observed", "v1", "[]", None),
                )

    def test_v3_rejects_invalid_feature_status_and_dimension(self) -> None:
        with closing(sqlite3.connect(self.db_path)) as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                self.insert_feature_set(connection, feature_set_id="bad-header", status="ready")
            self.insert_feature_set(connection)
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO feature_value VALUES (?,?,?,?,?,?,?,?,?,?)",
                    ("feature-set-1", "X", "growth", "FY0", 0.1, "ratio", "observed", "v1", "[]", None),
                )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO feature_value VALUES (?,?,?,?,?,?,?,?,?,?)",
                    ("feature-set-1", "G", "growth", "FY0", None, "ratio", "unknown", "v1", "[]", "invalid"),
                )

    def test_v3_rejects_feature_coverage_outside_closed_unit_interval(self) -> None:
        with closing(sqlite3.connect(self.db_path)) as connection:
            for index, coverage in enumerate((-0.01, 1.01)):
                with self.subTest(coverage=coverage):
                    with self.assertRaises(sqlite3.IntegrityError):
                        self.insert_feature_set(
                            connection,
                            feature_set_id=f"coverage-{index}",
                            coverage=coverage,
                        )

    def test_insert_financial_facts_is_idempotent_and_preserves_revision(self) -> None:
        snapshot_id, _ = self.store.record_snapshot(
            "akshare", "balance_sheet", "request-a", "a" * 64,
            "data/raw/a.json", 1, utc_at(0),
        )
        first = financial_fact(snapshot_id=snapshot_id, raw_row_hash="1" * 64, value=100.0)
        revised = financial_fact(snapshot_id=snapshot_id, raw_row_hash="2" * 64, value=101.0)

        self.assertEqual(self.store.insert_financial_facts([first, first]), (1, 1))
        self.assertEqual(self.store.insert_financial_facts([revised]), (1, 0))
        stored = self.store.list_financial_facts("SH600001")
        self.assertEqual(len(stored), 2)
        self.assertEqual({fact.raw_row_hash for fact in stored}, {"1" * 64, "2" * 64})

    def test_list_financial_facts_preserves_known_v1_and_v2_history(self) -> None:
        snapshot_id, _ = self.store.record_snapshot(
            "akshare", "profit_sheet", "request-history", "a" * 64,
            "data/raw/history.json", 1, utc_at(0),
        )
        current = financial_fact(snapshot_id=snapshot_id)
        historical = historical_mapping_fact(current)

        self.assertEqual(
            self.store.insert_financial_facts((historical, current)),
            (2, 0),
        )
        stored = self.store.list_financial_facts("SH600001")
        self.assertEqual(
            {fact.mapping_version for fact in stored},
            {"eastmoney-financial-mapping-v1", MAPPING_VERSION},
        )

    def test_list_financial_facts_applies_exact_snapshot_and_effective_filters(self) -> None:
        first_snapshot, _ = self.store.record_snapshot(
            "akshare", "profit_sheet", "request-a", "a" * 64,
            "data/raw/a.json", 1, utc_at(0),
        )
        second_snapshot, _ = self.store.record_snapshot(
            "akshare", "profit_sheet", "request-b", "b" * 64,
            "data/raw/b.json", 1, utc_at(1),
        )
        first = financial_fact(snapshot_id=first_snapshot, raw_row_hash="1" * 64)
        second = financial_fact(
            snapshot_id=second_snapshot,
            raw_row_hash="2" * 64,
            effective_at_utc="2026-08-22T07:00:00+00:00",
        )
        self.store.insert_financial_facts([first, second])

        self.assertEqual(
            self.store.list_financial_facts(
                "SH600001", source_snapshot_ids=[first_snapshot]
            ),
            [first],
        )
        self.assertEqual(
            self.store.list_financial_facts(
                "SH600001", effective_at_or_before="2026-08-21T07:00:00Z"
            ),
            [first],
        )
        self.assertEqual(
            self.store.list_financial_facts("SH600001", source_snapshot_ids=[]), []
        )

    def test_put_feature_bundle_is_atomic_and_rejects_nondeterministic_conflict(self) -> None:
        bundle = self.stored_evidence_bundle(input_hash="b" * 64)
        feature_id, created = self.store.put_feature_bundle(
            bundle,
            bundle_path="data/curated/formal_features/2026-06-30/SH600001/b.json",
            bundle_hash=bundle.bundle_hash(),
        )
        self.assertTrue(created)
        self.assertEqual(feature_id, bundle.bundle_hash())
        self.assertEqual(
            self.store.put_feature_bundle(
                bundle,
                bundle_path="data/curated/formal_features/2026-06-30/SH600001/b.json",
                bundle_hash=bundle.bundle_hash(),
            ),
            (feature_id, False),
        )
        conflicting = replace(bundle, blockers=("changed-without-input-hash",))
        with self.assertRaisesRegex(ValueError, "stored feature bundle content mismatch"):
            self.store.put_feature_bundle(
                conflicting,
                bundle_path="data/curated/formal_features/2026-06-30/SH600001/c.json",
                bundle_hash=conflicting.bundle_hash(),
            )
        stored = self.store.get_feature_bundle_row("SH600001", "2026-06-30", "b" * 64)
        self.assertEqual(stored["bundle_hash"], bundle.bundle_hash())
        with closing(sqlite3.connect(self.db_path)) as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM feature_value").fetchone()[0], 363
            )

    def test_put_feature_bundle_rolls_back_header_and_values_when_one_value_aborts(self) -> None:
        bundle = self.stored_evidence_bundle()
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.executescript(
                """CREATE TRIGGER abort_fs_feature_value
                BEFORE INSERT ON feature_value WHEN NEW.dimension = 'FS'
                BEGIN SELECT RAISE(ABORT, 'forced feature value failure'); END;"""
            )

        with self.assertRaisesRegex(sqlite3.IntegrityError, "forced feature value failure"):
            self.store.put_feature_bundle(
                bundle,
                bundle_path="data/curated/formal_features/2026-06-30/SH600001/b.json",
                bundle_hash=bundle.bundle_hash(),
            )

        with closing(sqlite3.connect(self.db_path)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM feature_set").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM feature_value").fetchone()[0], 0)

    def test_first_insert_mirror_validation_rolls_back_materialization_drift(self) -> None:
        bundle, _facts, _snapshots = self.installed_ready_bundle(
            self.store, snapshot_tag="first-insert-mirror"
        )
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.executescript(
                """CREATE TRIGGER corrupt_inserted_feature_value
                AFTER INSERT ON feature_value
                WHEN NEW.dimension = 'G' AND NEW.feature_key = 'g.revenue.FY2021'
                BEGIN
                    UPDATE feature_value SET value = value + 1.0
                    WHERE feature_set_id = NEW.feature_set_id
                    AND dimension = NEW.dimension
                    AND feature_key = NEW.feature_key
                    AND period_key = NEW.period_key;
                END;"""
            )

        with self.assertRaisesRegex(
            ValueError, "stored feature bundle content mismatch"
        ):
            self.store.put_feature_bundle(
                bundle,
                bundle_path=(
                    "data/curated/formal_features/2026-06-30/SH600001/"
                    "first-insert-mirror.json"
                ),
                bundle_hash=bundle.bundle_hash(),
            )

        with closing(sqlite3.connect(self.db_path)) as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM feature_set").fetchone()[0],
                0,
            )
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM feature_value").fetchone()[0],
                0,
            )

    def test_put_feature_bundle_rejects_hash_mismatch_and_unsafe_paths(self) -> None:
        bundle = valid_feature_bundle()
        invalid_paths = (
            "/data/curated/formal_features/b.json",
            "C:/data/curated/formal_features/b.json",
            "data\\curated\\formal_features\\b.json",
            "data/curated/formal_features/../outside.json",
            "data/curated/formal_features",
            "data/curated/other/b.json",
        )
        for invalid_path in invalid_paths:
            with self.subTest(path=invalid_path), self.assertRaisesRegex(
                ValueError, "bundle_path"
            ):
                self.store.put_feature_bundle(
                    bundle, bundle_path=invalid_path, bundle_hash=bundle.bundle_hash()
                )
        with self.assertRaisesRegex(ValueError, "bundle_hash"):
            self.store.put_feature_bundle(
                bundle,
                bundle_path="data/curated/formal_features/b.json",
                bundle_hash="0" * 64,
            )
        with closing(sqlite3.connect(self.db_path)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM feature_set").fetchone()[0], 0)

    def test_put_feature_bundle_rejects_ready_bundle_when_evidence_database_is_empty(self) -> None:
        bundle = build_bundle_with_overrides()

        with self.assertRaisesRegex(ValueError, "evidence"):
            self.store.put_feature_bundle(
                bundle,
                bundle_path="data/curated/formal_features/2026-06-30/SH600001/empty.json",
                bundle_hash=bundle.bundle_hash(),
            )

        with closing(sqlite3.connect(self.db_path)) as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM feature_set").fetchone()[0],
                0,
            )
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM feature_value").fetchone()[0],
                0,
            )

    def test_put_feature_bundle_revalidates_evidence_before_idempotent_success(self) -> None:
        bundle, facts, _snapshot_ids = self.installed_ready_bundle(
            self.store, snapshot_tag="idempotent"
        )
        path = "data/curated/formal_features/2026-06-30/SH600001/idempotent.json"
        feature_id, created = self.store.put_feature_bundle(
            bundle, bundle_path=path, bundle_hash=bundle.bundle_hash()
        )
        self.assertTrue(created)
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                "DELETE FROM financial_fact WHERE id=?", (facts[0].id,)
            )
            connection.commit()

        with self.assertRaisesRegex(ValueError, "evidence"):
            self.store.put_feature_bundle(
                bundle, bundle_path=path, bundle_hash=bundle.bundle_hash()
            )

        with closing(sqlite3.connect(self.db_path)) as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM feature_set").fetchone()[0],
                1,
            )
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM feature_value").fetchone()[0],
                363,
            )
        self.assertEqual(feature_id, bundle.bundle_hash())

    def test_put_feature_bundle_rejects_future_fact_on_idempotent_success_path(self) -> None:
        bundle, _facts, _snapshot_ids = self.installed_ready_bundle(
            self.store,
            snapshot_tag="pit-idempotent",
            as_of_utc="2026-04-01T07:00:00+00:00",
        )
        path = "data/curated/formal_features/2026-06-30/SH600001/pit.json"
        feature_id, created = self.store.put_feature_bundle(
            bundle, bundle_path=path, bundle_hash=bundle.bundle_hash()
        )
        self.assertTrue(created)

        forged = copy.copy(bundle)
        object.__setattr__(forged, "as_of_utc", "2026-04-01T06:59:59+00:00")
        forged_hash = forged.bundle_hash()
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                "UPDATE feature_set SET as_of_utc=?, bundle_hash=? WHERE id=?",
                (forged.as_of_utc, forged_hash, feature_id),
            )
            connection.commit()

        with self.assertRaisesRegex(ValueError, "effective.*as_of"):
            self.store.put_feature_bundle(
                forged, bundle_path=path, bundle_hash=forged_hash
            )

        with closing(sqlite3.connect(self.db_path)) as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM feature_set").fetchone()[0],
                1,
            )
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM feature_value").fetchone()[0],
                363,
            )

    def test_put_feature_bundle_rejects_missing_or_mismatched_evidence_rows(self) -> None:
        cases = (
            "missing_fact",
            "missing_snapshot",
            "source_snapshot_id",
            "source_field",
            "raw_row_hash",
            "announced_at_utc",
            "effective_at_utc",
        )
        for case in cases:
            with self.subTest(case=case):
                case_store = StateStore(Path(self.tempdir.name) / f"{case}.sqlite3")
                case_store.initialize()
                bundle, facts, snapshot_ids = self.installed_ready_bundle(
                    case_store, snapshot_tag=case
                )
                target_fact = next(
                    fact
                    for fact in facts
                    if fact.metric_key == "revenue" and fact.period_end == "2021-12-31"
                )
                if case == "missing_fact":
                    with closing(sqlite3.connect(case_store.db_path)) as connection:
                        connection.execute(
                            "DELETE FROM financial_fact WHERE id=?", (target_fact.id,)
                        )
                        connection.commit()
                    attacked = bundle
                elif case == "missing_snapshot":
                    with closing(sqlite3.connect(case_store.db_path)) as connection:
                        connection.execute(
                            "DELETE FROM source_snapshot WHERE id=?",
                            (target_fact.source_snapshot_id,),
                        )
                        connection.commit()
                    attacked = bundle
                else:
                    derived = next(
                        value
                        for value in bundle.dimension_inputs["M"].values
                        if value.key == "m.gross_profit.FY2021"
                    )
                    original = derived.evidence[0]
                    replacements = {
                        "source_snapshot_id": EvidenceRef(
                            original.financial_fact_id,
                            snapshot_ids["balance"],
                            original.source_field,
                            original.raw_row_hash,
                            original.announced_at_utc,
                            original.effective_at_utc,
                        ),
                        "source_field": EvidenceRef(
                            original.financial_fact_id,
                            original.source_snapshot_id,
                            "WRONG_SOURCE_FIELD",
                            original.raw_row_hash,
                            original.announced_at_utc,
                            original.effective_at_utc,
                        ),
                        "raw_row_hash": EvidenceRef(
                            original.financial_fact_id,
                            original.source_snapshot_id,
                            original.source_field,
                            "f" * 64,
                            original.announced_at_utc,
                            original.effective_at_utc,
                        ),
                        "announced_at_utc": EvidenceRef(
                            original.financial_fact_id,
                            original.source_snapshot_id,
                            original.source_field,
                            original.raw_row_hash,
                            "2026-03-30T15:59:59+00:00",
                            original.effective_at_utc,
                        ),
                        "effective_at_utc": EvidenceRef(
                            original.financial_fact_id,
                            original.source_snapshot_id,
                            original.source_field,
                            original.raw_row_hash,
                            original.announced_at_utc,
                            "2026-04-02T07:00:00+00:00",
                        ),
                    }
                    attacked = self.bundle_with_replaced_evidence(
                        bundle,
                        feature_key=derived.key,
                        evidence=replacements[case],
                    )

                with self.assertRaisesRegex(ValueError, "evidence"):
                    case_store.put_feature_bundle(
                        attacked,
                        bundle_path=(
                            "data/curated/formal_features/2026-06-30/SH600001/"
                            f"{case}.json"
                        ),
                        bundle_hash=attacked.bundle_hash(),
                    )
                with closing(sqlite3.connect(case_store.db_path)) as connection:
                    self.assertEqual(
                        connection.execute("SELECT COUNT(*) FROM feature_set").fetchone()[0],
                        0,
                    )
                    self.assertEqual(
                        connection.execute("SELECT COUNT(*) FROM feature_value").fetchone()[0],
                        0,
                    )

    def test_put_feature_bundle_authenticates_derived_values_and_operands(self) -> None:
        def raw_value(payload, key):
            return next(
                value
                for dimension in payload["dimension_inputs"].values()
                for value in dimension["values"]
                if value["key"] == key
            )

        def mutate_numeric(payload):
            raw_value(payload, "m.gross_profit.FY2021")["value"] += 1.0

        def substitute_gross_profit_operand(payload):
            target = raw_value(payload, "m.gross_profit.FY2021")
            cost = raw_value(payload, "m.operating_cost.FY2021")["evidence"][0]
            substitute = raw_value(payload, "m.total_profit.FY2021")["evidence"][0]
            target["evidence"] = [
                copy.deepcopy(substitute if item["financial_fact_id"] == cost["financial_fact_id"] else item)
                for item in target["evidence"]
            ]

        def substitute_growth_period(payload):
            target = raw_value(payload, "g.revenue_symmetric_growth.FY2022")
            previous = raw_value(payload, "g.revenue.FY2021")["evidence"][0]
            substitute = raw_value(payload, "g.revenue.FY2023")["evidence"][0]
            target["evidence"] = [
                copy.deepcopy(substitute if item["financial_fact_id"] == previous["financial_fact_id"] else item)
                for item in target["evidence"]
            ]

        for case, mutate in (
            ("numeric", mutate_numeric),
            ("gross_profit_operand", substitute_gross_profit_operand),
            ("growth_period_operand", substitute_growth_period),
        ):
            with self.subTest(case=case):
                case_store = StateStore(Path(self.tempdir.name) / f"derived-{case}.sqlite3")
                case_store.initialize()
                honest, _facts, _snapshots = self.installed_ready_bundle(
                    case_store, snapshot_tag=f"derived-{case}"
                )
                payload = honest.to_dict()
                mutate(payload)
                forged = FeatureBundle.from_dict(payload)

                with self.assertRaisesRegex(ValueError, "derived financial projection"):
                    case_store.put_feature_bundle(
                        forged,
                        bundle_path=(
                            "data/curated/formal_features/2026-06-30/SH600001/"
                            f"derived-{case}.json"
                        ),
                        bundle_hash=forged.bundle_hash(),
                    )
                with closing(sqlite3.connect(case_store.db_path)) as connection:
                    self.assertEqual(
                        connection.execute("SELECT COUNT(*) FROM feature_set").fetchone()[0],
                        0,
                    )

    def test_balance_equation_semantics_reject_forged_ready_partial_and_blocked(self) -> None:
        cases = (
            ("ready_omission", 10_000.0, "financial_ready", False),
            ("partial_omission", 10_000.0, "partial", False),
            ("blocked_addition", 900.0, "blocked", True),
        )
        for case, assets, status, include_marker in cases:
            with self.subTest(case=case):
                case_store = StateStore(Path(self.tempdir.name) / f"{case}.sqlite3")
                case_store.initialize()
                built, _facts, _snapshots = self.installed_ready_bundle(
                    case_store,
                    snapshot_tag=case,
                    fact_values={("total_assets", "2021-12-31"): assets},
                )
                forged = forge_balance_semantics(
                    built,
                    status=status,
                    include_mismatch_blocker=include_marker,
                )

                with self.assertRaisesRegex(ValueError, "balance equation"):
                    case_store.put_feature_bundle(
                        forged,
                        bundle_path=(
                            "data/curated/formal_features/2026-06-30/SH600001/"
                            f"{case}.json"
                        ),
                        bundle_hash=forged.bundle_hash(),
                    )
                with closing(sqlite3.connect(case_store.db_path)) as connection:
                    self.assertEqual(
                        connection.execute(
                            "SELECT COUNT(*) FROM feature_set"
                        ).fetchone()[0],
                        0,
                    )

    def test_balance_equation_is_reauthenticated_before_idempotent_success(self) -> None:
        built, _facts, _snapshots = self.installed_ready_bundle(
            self.store,
            snapshot_tag="balance-idempotent",
            fact_values={("total_assets", "2021-12-31"): 10_000.0},
        )
        forged = forge_balance_semantics(
            built,
            status="financial_ready",
            include_mismatch_blocker=False,
        )
        path = (
            "data/curated/formal_features/2026-06-30/SH600001/"
            "balance-idempotent.json"
        )
        feature_id = unsafe_materialize_feature_bundle(
            self.store, forged, bundle_path=path
        )
        stored = self.store.get_feature_bundle_row(
            forged.security_id, forged.report_period, forged.input_hash
        )
        self.assertEqual(stored["status"], "financial_ready")
        self.assertEqual(stored["id"], feature_id)

        with self.assertRaisesRegex(ValueError, "balance equation"):
            self.store.put_feature_bundle(
                forged, bundle_path=path, bundle_hash=forged.bundle_hash()
            )

        with closing(sqlite3.connect(self.db_path)) as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM feature_set").fetchone()[0],
                1,
            )
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM feature_value").fetchone()[0],
                363,
            )

    def test_balance_equation_accepts_exact_tolerance_and_missing_triplet(self) -> None:
        cases = (
            (
                "exact_tolerance",
                {("total_assets", "2021-12-31"): 1_900.0},
                (),
                "financial_ready",
            ),
            (
                "missing_equity",
                {},
                (("total_equity", "2021-12-31"),),
                "partial",
            ),
        )
        for case, values, omitted, expected_status in cases:
            with self.subTest(case=case):
                case_store = StateStore(Path(self.tempdir.name) / f"{case}.sqlite3")
                case_store.initialize()
                bundle, _facts, _snapshots = self.installed_ready_bundle(
                    case_store,
                    snapshot_tag=case,
                    fact_values=values,
                    omit_fact_slots=omitted,
                )
                feature_id, created = case_store.put_feature_bundle(
                    bundle,
                    bundle_path=(
                        "data/curated/formal_features/2026-06-30/SH600001/"
                        f"{case}.json"
                    ),
                    bundle_hash=bundle.bundle_hash(),
                )
                self.assertTrue(created)
                self.assertEqual(feature_id, bundle.bundle_hash())
                self.assertEqual(bundle.financial_status, expected_status)
                self.assertNotIn("balance_equation_mismatch", bundle.blockers)

    def test_first_persistence_rejects_financial_formula_copy_in_t(self) -> None:
        honest, _facts, _snapshots = self.installed_ready_bundle(
            self.store, snapshot_tag="formula-copy-first"
        )
        forged = bundle_with_copied_financial_value(honest, "T")

        with self.assertRaisesRegex(ValueError, "financial projection"):
            self.store.put_feature_bundle(
                forged,
                bundle_path=(
                    "data/curated/formal_features/2026-06-30/SH600001/"
                    "formula-copy-first.json"
                ),
                bundle_hash=forged.bundle_hash(),
            )

        with closing(sqlite3.connect(self.db_path)) as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM feature_set").fetchone()[0],
                0,
            )

    def test_evidence_authority_rejects_financial_formula_aliases_in_v_and_t(self) -> None:
        honest, _facts, _snapshots = self.installed_ready_bundle(
            self.store, snapshot_tag="formula-copy-evidence"
        )
        sources = (
            ("formula", "M", "m.gross_profit.FY2021"),
            ("raw", "G", "g.revenue.FY2021"),
        )
        for case, source_dimension, feature_key in sources:
            for target_dimension in ("V", "T"):
                with self.subTest(
                    case=case, target_dimension=target_dimension
                ):
                    forged = bundle_with_copied_financial_value(
                        honest,
                        target_dimension,
                        source_dimension=source_dimension,
                        feature_key=feature_key,
                    )
                    with self.store._transaction() as connection:
                        with self.assertRaisesRegex(
                            ValueError, "financial projection"
                        ):
                            self.store._validate_feature_bundle_evidence(
                                connection, forged
                            )

    def test_idempotent_put_reauthenticates_derived_numeric_projection(self) -> None:
        honest, _facts, _snapshots = self.installed_ready_bundle(
            self.store, snapshot_tag="derived-idempotent"
        )
        path = "data/curated/formal_features/2026-06-30/SH600001/derived-idempotent.json"
        feature_id, created = self.store.put_feature_bundle(
            honest, bundle_path=path, bundle_hash=honest.bundle_hash()
        )
        self.assertTrue(created)
        payload = honest.to_dict()
        gross = next(
            value
            for value in payload["dimension_inputs"]["M"]["values"]
            if value["key"] == "m.gross_profit.FY2021"
        )
        gross["value"] += 1.0
        forged = FeatureBundle.from_dict(payload)
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                "UPDATE feature_set SET bundle_hash=? WHERE id=?",
                (forged.bundle_hash(), feature_id),
            )
            connection.execute(
                """UPDATE feature_value SET value=?
                WHERE feature_set_id=? AND dimension='M'
                AND feature_key='m.gross_profit.FY2021' AND period_key='FY2021'""",
                (gross["value"], feature_id),
            )
            connection.commit()

        with self.assertRaisesRegex(ValueError, "derived financial projection"):
            self.store.put_feature_bundle(
                forged, bundle_path=path, bundle_hash=forged.bundle_hash()
            )

    def test_idempotent_put_rejects_exact_child_mirror_corruption_without_repair(self) -> None:
        for case in ("deleted", "updated", "extra"):
            with self.subTest(case=case):
                case_store = StateStore(Path(self.tempdir.name) / f"mirror-{case}.sqlite3")
                case_store.initialize()
                bundle, _facts, _snapshots = self.installed_ready_bundle(
                    case_store, snapshot_tag=f"mirror-{case}"
                )
                path = (
                    "data/curated/formal_features/2026-06-30/SH600001/"
                    f"mirror-{case}.json"
                )
                feature_id, created = case_store.put_feature_bundle(
                    bundle, bundle_path=path, bundle_hash=bundle.bundle_hash()
                )
                self.assertTrue(created)
                with closing(sqlite3.connect(case_store.db_path)) as connection:
                    before = connection.execute(
                        "SELECT COUNT(*) FROM feature_value WHERE feature_set_id=?",
                        (feature_id,),
                    ).fetchone()[0]
                    if case == "deleted":
                        cursor = connection.execute(
                            """DELETE FROM feature_value WHERE feature_set_id=?
                            AND dimension='G' AND feature_key='g.revenue.FY2021'
                            AND period_key='FY2021'""",
                            (feature_id,),
                        )
                        expected_count = before - 1
                    elif case == "updated":
                        cursor = connection.execute(
                            """UPDATE feature_value SET value=value+1.0
                            WHERE feature_set_id=? AND dimension='G'
                            AND feature_key='g.revenue.FY2021' AND period_key='FY2021'""",
                            (feature_id,),
                        )
                        expected_count = before
                    else:
                        cursor = connection.execute(
                            """INSERT INTO feature_value
                            (feature_set_id,dimension,feature_key,period_key,value,unit,status,
                             formula_version,evidence_json,missing_reason)
                            SELECT feature_set_id,dimension,'g.unregistered_extra.FY2021',period_key,
                                   value,unit,status,formula_version,evidence_json,missing_reason
                            FROM feature_value WHERE feature_set_id=? AND dimension='G'
                            AND feature_key='g.revenue.FY2021' AND period_key='FY2021'""",
                            (feature_id,),
                        )
                        expected_count = before + 1
                    self.assertEqual(cursor.rowcount, 1)
                    connection.commit()

                with self.assertRaisesRegex(
                    ValueError, "stored feature bundle content mismatch"
                ):
                    case_store.put_feature_bundle(
                        bundle, bundle_path=path, bundle_hash=bundle.bundle_hash()
                    )
                with closing(sqlite3.connect(case_store.db_path)) as connection:
                    self.assertEqual(
                        connection.execute(
                            "SELECT COUNT(*) FROM feature_value WHERE feature_set_id=?",
                            (feature_id,),
                        ).fetchone()[0],
                        expected_count,
                    )

    def test_put_feature_bundle_rejects_raw_observed_fact_mismatches(self) -> None:
        cases = ("wrong_security", "metric", "period", "value", "unit", "mapping")
        for case in cases:
            with self.subTest(case=case):
                case_store = StateStore(Path(self.tempdir.name) / f"raw-{case}.sqlite3")
                case_store.initialize()
                bundle, facts, _snapshot_ids = self.installed_ready_bundle(
                    case_store, snapshot_tag=f"raw-{case}"
                )
                original = next(
                    fact
                    for fact in facts
                    if fact.metric_key == "revenue" and fact.period_end == "2021-12-31"
                )
                if case == "mapping":
                    with closing(sqlite3.connect(case_store.db_path)) as connection:
                        connection.execute(
                            "UPDATE financial_fact SET mapping_version=? WHERE id=?",
                            ("wrong-mapping-v1", original.id),
                        )
                        connection.commit()
                    attacked = bundle
                else:
                    overrides: dict[str, object] = {}
                    if case == "wrong_security":
                        overrides["security_id"] = "SH600002"
                    elif case == "metric":
                        overrides["metric_key"] = "operating_cost"
                    elif case == "period":
                        overrides.update(
                            period_start="2020-01-01",
                            period_end="2020-12-31",
                            period_kind="FY",
                        )
                    elif case == "value":
                        overrides["value"] = original.value + 1.0
                    elif case == "unit":
                        overrides["unit"] = "shares"
                    substitute = rebuild_fact(original, **overrides)
                    case_store.insert_financial_facts((substitute,))
                    attacked = self.bundle_with_replaced_evidence(
                        bundle,
                        feature_key="g.revenue.FY2021",
                        evidence=self.evidence_for_fact(substitute),
                    )

                with self.assertRaisesRegex(ValueError, "evidence"):
                    case_store.put_feature_bundle(
                        attacked,
                        bundle_path=(
                            "data/curated/formal_features/2026-06-30/SH600001/"
                            f"raw-{case}.json"
                        ),
                        bundle_hash=attacked.bundle_hash(),
                    )

    def test_latest_feature_set_filters_exactly_orders_and_parses_json(self) -> None:
        older = self.stored_evidence_bundle(
            input_hash="1" * 64, as_of_utc="2026-08-28T16:00:00+00:00"
        )
        newer = self.stored_evidence_bundle(
            input_hash="2" * 64,
            as_of_utc="2026-08-29T16:00:00+00:00",
            blockers=("z-blocker", "a-blocker"),
        )
        for label, bundle in (("older", older), ("newer", newer)):
            self.store.put_feature_bundle(
                bundle,
                bundle_path=f"data/curated/formal_features/{label}.json",
                bundle_hash=bundle.bundle_hash(),
            )

        latest = self.store.latest_feature_set("SH600001", "2026-06-30")
        self.assertEqual(latest["id"], newer.bundle_hash())
        self.assertEqual(
            latest["dimension_status"],
            {
                "G": "partial",
                "V": "missing",
                "M": "missing",
                "EQ": "missing",
                "FS": "missing",
                "CA": "missing",
                "T": "missing",
            },
        )
        self.assertEqual(latest["confidence_inputs"]["history_years_present"], 0)
        self.assertEqual(latest["blockers"], ["a-blocker", "z-blocker"])
        self.assertEqual(len(latest["missing"]), 362)
        self.assertTrue(
            all(
                set(item) == {"dimension", "feature_key", "period_key", "reason"}
                for item in latest["missing"]
            )
        )
        self.assertNotIn("dimension_status_json", latest)
        self.assertNotIn("value", latest)
        self.assertEqual(
            self.store.latest_feature_set(
                "SH600001", "2026-06-30", as_of_utc=older.as_of_utc
            )["id"],
            older.bundle_hash(),
        )
        self.assertIsNone(
            self.store.latest_feature_set(
                "SH600001", "2026-06-30", contract_version="other-contract"
            )
        )
        self.assertIsNone(
            self.store.latest_feature_set(
                "SH600001", "2026-06-30", as_of_utc="2026-08-28T16:00:01+00:00"
            )
        )

    def test_latest_feature_set_breaks_as_of_ties_by_created_at_then_id(self) -> None:
        bundles = (
            self.stored_evidence_bundle(input_hash="3" * 64),
            self.stored_evidence_bundle(input_hash="4" * 64),
        )
        for index, bundle in enumerate(bundles):
            self.store.put_feature_bundle(
                bundle,
                bundle_path=f"data/curated/formal_features/tie-{index}.json",
                bundle_hash=bundle.bundle_hash(),
            )
        low_id, high_id = sorted(bundle.bundle_hash() for bundle in bundles)
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                "UPDATE feature_set SET created_at = ? WHERE id = ?", (utc_at(1), high_id)
            )
            connection.execute(
                "UPDATE feature_set SET created_at = ? WHERE id = ?", (utc_at(2), low_id)
            )
            connection.commit()
        self.assertEqual(
            self.store.latest_feature_set("SH600001", "2026-06-30")["id"], low_id
        )

        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute("UPDATE feature_set SET created_at = ?", (utc_at(3),))
            connection.commit()
        self.assertEqual(
            self.store.latest_feature_set("SH600001", "2026-06-30")["id"], high_id
        )

    def test_record_quality_issue_stores_canonical_details_json(self) -> None:
        issue_id = self.store.record_quality_issue(
            run_id=None,
            score_run_id=None,
            severity="warning",
            code="mapping_gap",
            details={"z": 1, "message": "缺失", "a": [2, 1]},
        )

        with closing(sqlite3.connect(self.db_path)) as connection:
            row = connection.execute(
                "SELECT id, run_id, score_run_id, severity, code, details_json FROM quality_issue"
            ).fetchone()
        self.assertEqual(
            row,
            (issue_id, None, None, "warning", "mapping_gap", '{"a":[2,1],"message":"缺失","z":1}'),
        )

    def test_record_quality_issue_rejects_nonfinite_details_without_rows(self) -> None:
        for invalid in (math.nan, math.inf, -math.inf):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                self.store.record_quality_issue(
                    run_id=None,
                    score_run_id=None,
                    severity="warning",
                    code="nonfinite_observation",
                    details={"observed": invalid},
                )

        with closing(sqlite3.connect(self.db_path)) as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM quality_issue").fetchone()[0], 0
            )

    def test_owned_quality_issue_and_snapshot_binding_commit_together(self) -> None:
        snapshot_id, _ = self.store.record_snapshot(
            "akshare",
            "profit_sheet",
            canonical_sha256({"symbol": "SH600001", "report_period": "2026-06-30"}),
            "a" * 64,
            "data/raw/bound-quality.json",
            1,
            "2026-08-31T01:00:00+00:00",
        )
        job_id = self.store.enqueue_job("deep_statement", "quality:bound", {})
        self.store.lease_next_job(["deep_statement"], "quality-worker", 3600)

        issue_id = self.store.record_quality_issue(
            run_id=None,
            score_run_id=None,
            severity="error",
            code="statement_report_date_invalid",
            details={"row_hash": "1" * 64},
            job_id=job_id,
            worker_id="quality-worker",
            source_snapshot_id=snapshot_id,
        )

        with closing(sqlite3.connect(self.db_path)) as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT issue_id,job_id,source_snapshot_id FROM quality_issue_binding"
                ).fetchall(),
                [(issue_id, job_id, snapshot_id)],
            )

    def test_owned_quality_issue_invalid_snapshot_rolls_back_issue(self) -> None:
        job_id = self.store.enqueue_job("deep_statement", "quality:missing-snapshot", {})
        self.store.lease_next_job(["deep_statement"], "quality-worker", 3600)

        with self.assertRaisesRegex(ValueError, "snapshot"):
            self.store.record_quality_issue(
                run_id=None,
                score_run_id=None,
                severity="error",
                code="statement_report_date_invalid",
                details={"row_hash": "1" * 64},
                job_id=job_id,
                worker_id="quality-worker",
                source_snapshot_id="missing-snapshot",
            )

        with closing(sqlite3.connect(self.db_path)) as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM quality_issue").fetchone()[0],
                0,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM quality_issue_binding"
                ).fetchone()[0],
                0,
            )

    def test_find_quality_issue_ids_is_exact_canonical_and_stably_sorted(self) -> None:
        matching = tuple(
            self.store.record_quality_issue(
                run_id=None,
                score_run_id=None,
                severity="error",
                code="statement_report_date_invalid",
                details={"z": 1, "a": [2, 1]},
            )
            for _ in range(2)
        )
        self.store.record_quality_issue(
            run_id=None,
            score_run_id=None,
            severity="warning",
            code="statement_report_date_invalid",
            details={"a": [2, 1], "z": 1},
        )

        self.assertEqual(
            self.store.find_quality_issue_ids(
                severity="error",
                code="statement_report_date_invalid",
                details={"a": [2, 1], "z": 1},
            ),
            tuple(sorted(matching)),
        )
        self.assertEqual(
            self.store.find_quality_issue_ids(
                severity="error",
                code="statement_report_date_invalid",
                details={"a": [1, 2], "z": 1},
            ),
            (),
        )

    def test_resolve_reconciliation_issue_prioritizes_exact_current_provenance(
        self,
    ) -> None:
        shared_row_hash = "1" * 64
        other = self.malformed_reconciliation_case(
            "resolver-other", raw_row_hash=shared_row_hash
        )
        current = self.malformed_reconciliation_case(
            "resolver-current", raw_row_hash=shared_row_hash
        )

        self.assertEqual(
            self.store.resolve_reconciliation_quality_issue(
                severity="error",
                code="statement_report_date_invalid",
                details=current["issue_details"],
                job_id=current["job_id"],
                source_snapshot_id=current["snapshot_id"],
            ),
            (current["issue_id"], "bound"),
        )

        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                "DELETE FROM quality_issue_binding WHERE issue_id=?",
                (current["issue_id"],),
            )
            connection.commit()
        self.assertIsNone(
            self.store.resolve_reconciliation_quality_issue(
                severity="error",
                code="statement_report_date_invalid",
                details=current["issue_details"],
                job_id=current["job_id"],
                source_snapshot_id=current["snapshot_id"],
            )
        )

        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                "DELETE FROM quality_issue_binding WHERE issue_id=?",
                (other["issue_id"],),
            )
            connection.execute(
                "DELETE FROM quality_issue WHERE id=?", (other["issue_id"],)
            )
            connection.execute("DELETE FROM job WHERE id=?", (other["job_id"],))
            connection.commit()
        self.assertEqual(
            self.store.resolve_reconciliation_quality_issue(
                severity="error",
                code="statement_report_date_invalid",
                details=current["issue_details"],
                job_id=current["job_id"],
                source_snapshot_id=current["snapshot_id"],
            ),
            (current["issue_id"], "legacy"),
        )
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                "UPDATE quality_issue SET created_at=? WHERE id=?",
                ("2000-01-01T00:00:00+00:00", current["issue_id"]),
            )
            connection.commit()
        self.assertIsNone(
            self.store.resolve_reconciliation_quality_issue(
                severity="error",
                code="statement_report_date_invalid",
                details=current["issue_details"],
                job_id=current["job_id"],
                source_snapshot_id=current["snapshot_id"],
            )
        )

    def test_duplicate_enqueue_returns_original_job_without_second_row(self) -> None:
        job_id = self.store.enqueue_job("fetch", "source:000001", {"request": "first"})
        repeated_id = self.store.enqueue_job("fetch", "source:000001", {"request": "changed"})

        self.assertEqual(job_id, repeated_id)
        with closing(sqlite3.connect(self.db_path)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM job").fetchone()[0], 1)

    def test_leasing_claims_one_pending_job_exclusively(self) -> None:
        job_id = self.store.enqueue_job("fetch", "lease:one", {"x": 1})

        first = self.store.lease_next_job(["fetch"], "worker-a", 60, utc_at(0))
        second = self.store.lease_next_job(["fetch"], "worker-b", 60, utc_at(1))

        self.assertEqual(first["id"], job_id)
        self.assertEqual(first["status"], "running")
        self.assertEqual(first["lease_worker"], "worker-a")
        self.assertIsNone(second)

    def test_two_connections_cannot_lease_same_job(self) -> None:
        self.store.enqueue_job("fetch", "lease:race", {})
        other_connection = StateStore(self.db_path)
        other_connection.initialize()

        first = self.store.lease_next_job(["fetch"], "worker-a", 60, utc_at(0))
        second = other_connection.lease_next_job(["fetch"], "worker-b", 60, utc_at(0))

        self.assertIsNotNone(first)
        self.assertIsNone(second)

    def test_concurrent_workers_claim_only_one_job_after_barrier(self) -> None:
        job_id = self.store.enqueue_job("fetch", "lease:thread-race", {})
        barrier = threading.Barrier(3)
        results: list[dict | None] = []
        errors: list[BaseException] = []

        def claim(worker_id: str) -> None:
            try:
                barrier.wait(timeout=5)
                result = StateStore(self.db_path).lease_next_job(["fetch"], worker_id, 60, utc_at(0))
                results.append(result)
            except BaseException as error:
                errors.append(error)

        workers = [threading.Thread(target=claim, args=(worker_id,)) for worker_id in ("worker-a", "worker-b")]
        for worker in workers:
            worker.start()
        barrier.wait(timeout=5)
        for worker in workers:
            worker.join(timeout=5)

        self.assertEqual(errors, [])
        self.assertEqual([result["id"] for result in results if result is not None], [job_id])
        self.assertEqual(sum(result is None for result in results), 1)

    def test_retryable_failure_waits_until_retry_time(self) -> None:
        job_id = self.store.enqueue_job("fetch", "retry:future", {})
        self.store.lease_next_job(["fetch"], "worker", 60, utc_at(0))
        self.store.fail_job(job_id, {"reason": "temporary"}, True, utc_at(120))

        self.assertIsNone(self.store.lease_next_job(["fetch"], "worker", 60, utc_at(119)))
        self.assertEqual(
            self.store.lease_next_job(["fetch"], "worker", 60, utc_at(120))["id"], job_id
        )

    def test_terminal_failure_is_never_automatically_released(self) -> None:
        job_id = self.store.enqueue_job("fetch", "retry:terminal", {})
        self.store.lease_next_job(["fetch"], "worker", 60, utc_at(0))
        self.store.fail_job(job_id, {"reason": "bad input"}, False)

        self.assertIsNone(self.store.lease_next_job(["fetch"], "worker", 60, utc_at(10_000)))

    def test_expired_lease_is_recovered_with_audit_error(self) -> None:
        job_id = self.store.enqueue_job("fetch", "lease:expired", {})
        self.store.lease_next_job(["fetch"], "worker-a", 10, utc_at(0))

        self.assertEqual(self.store.recover_expired_leases(utc_at(11)), 1)
        with closing(sqlite3.connect(self.db_path)) as connection:
            status, error_text = connection.execute(
                "SELECT status, last_error_json FROM job WHERE id = ?", (job_id,)
            ).fetchone()
        self.assertEqual(status, "retryable_failed")
        self.assertIn("lease_expired", error_text)
        self.assertEqual(self.store.lease_next_job(["fetch"], "worker-b", 10, utc_at(11))["id"], job_id)

    def test_completed_job_remains_completed_after_reopen(self) -> None:
        job_id = self.store.enqueue_job("fetch", "persist:job", {"symbol": "000001"})
        self.store.lease_next_job(["fetch"], "worker", 10, utc_at(0))
        self.store.complete_job(job_id, {"rows": 1})

        reopened = StateStore(self.db_path)
        reopened.initialize()
        self.assertIsNone(reopened.lease_next_job(["fetch"], "new-worker", 10, utc_at(100)))

    def test_get_job_returns_public_status_result_error_and_retry_fields(self) -> None:
        job_id = self.store.enqueue_job("fetch", "read:job", {"symbol": "000001"})
        self.store.lease_next_job(["fetch"], "worker", 60, utc_at(0))
        self.store.fail_job(job_id, {"reason": "temporary"}, True, utc_at(60))

        job = self.store.get_job(job_id)
        self.assertEqual(job["status"], "retryable_failed")
        self.assertEqual(job["payload"], {"symbol": "000001"})
        self.assertEqual(job["error"], {"reason": "temporary"})
        self.assertEqual(job["next_retry_at"], utc_at(60))
        self.assertIsNone(self.store.get_job("missing"))

    def test_job_spec_is_frozen(self) -> None:
        spec = JobSpec("feature_build", "feature:frozen", {"security_id": "SH600001"})

        with self.assertRaises(FrozenInstanceError):
            spec.kind = "deep_statement"

    def test_job_spec_payload_is_a_stable_construction_snapshot(self) -> None:
        source_payload = {
            "security_id": "SH600001",
            "nested": {"version": 1},
            "items": [{"dataset": "balance_sheet"}],
        }
        spec = JobSpec("feature_build", "feature:immutable", source_payload)

        source_payload["nested"]["version"] = 2
        source_payload["items"][0]["dataset"] = "profit_sheet"
        source_payload["added"] = True
        self.assertEqual(
            spec.payload,
            {
                "security_id": "SH600001",
                "nested": {"version": 1},
                "items": [{"dataset": "balance_sheet"}],
            },
        )

        exposed_payload = spec.payload
        exposed_payload["nested"]["version"] = 3
        exposed_payload["items"].append({"dataset": "cash_flow_sheet"})
        exposed_payload["security_id"] = "SZ000001"

        parent_id = self.store.enqueue_job("deep_statement", "statement:immutable", {})
        self.store.lease_next_job(["deep_statement"], "worker-a", 60)
        self.store.complete_job_with_followups(
            parent_id, "worker-a", {"outcome": "expanded"}, (spec,)
        )

        stored = self.store.list_jobs(["feature_build"])[0]
        self.assertEqual(
            stored["payload"],
            {
                "security_id": "SH600001",
                "nested": {"version": 1},
                "items": [{"dataset": "balance_sheet"}],
            },
        )
        self.assertEqual(spec.payload, stored["payload"])

    def test_renew_job_lease_requires_current_unexpired_owner(self) -> None:
        job_id = self.store.enqueue_job("deep_statement", "statement-a", {})
        self.store.lease_next_job(["deep_statement"], "worker-a", 60, utc_at(0))

        expiry = self.store.renew_job_lease(job_id, "worker-a", 120, utc_at(30))

        self.assertEqual(expiry, utc_at(150))
        with self.assertRaisesRegex(ValueError, "lease owner"):
            self.store.renew_job_lease(job_id, "worker-b", 120, utc_at(31))

    def test_renew_samples_default_time_after_writer_lock_wait(self) -> None:
        job_id = self.store.enqueue_job("deep_statement", "renew:lock-boundary", {})
        self.store.lease_next_job(["deep_statement"], "worker-a", 10, utc_at(0))
        holder = sqlite3.connect(self.db_path, timeout=5, isolation_level=None)
        holder.execute("BEGIN IMMEDIATE")
        begin_attempted = threading.Event()
        clock_sampled = threading.Event()
        after_expiry = threading.Event()
        sampled_before_begin: list[bool] = []
        errors: list[BaseException] = []
        results: list[str] = []
        real_connect = self.store._connect

        class ObservedConnection:
            def __init__(self, connection):
                self.connection = connection

            def __getattr__(self, name):
                return getattr(self.connection, name)

            def execute(self, sql, parameters=()):
                if sql == "BEGIN IMMEDIATE":
                    sampled_before_begin.append(clock_sampled.is_set())
                    begin_attempted.set()
                return self.connection.execute(sql, parameters)

        def controlled_now():
            clock_sampled.set()
            return utc_at(11) if after_expiry.is_set() else utc_at(9)

        def renew():
            try:
                results.append(
                    self.store.renew_job_lease(job_id, "worker-a", 60)
                )
            except BaseException as error:
                errors.append(error)

        try:
            with (
                patch.object(
                    self.store,
                    "_connect",
                    side_effect=lambda: ObservedConnection(real_connect()),
                ),
                patch("ashare_pipeline.state_store._utc_now", side_effect=controlled_now),
            ):
                worker = threading.Thread(target=renew)
                worker.start()
                self.assertTrue(begin_attempted.wait(timeout=5))
                after_expiry.set()
                holder.rollback()
                worker.join(timeout=10)
        finally:
            holder.close()

        self.assertFalse(worker.is_alive())
        self.assertEqual(sampled_before_begin, [False])
        self.assertEqual(results, [])
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], ValueError)
        job = self.store.get_job(job_id)
        self.assertEqual(job["status"], "running")
        self.assertEqual(job["lease_worker"], "worker-a")
        self.assertEqual(job["lease_expires_at"], utc_at(10))

    def test_final_transitions_sample_time_after_writer_lock_wait(self) -> None:
        for action in ("complete", "fail"):
            with self.subTest(action=action):
                job_id = self.store.enqueue_job(
                    "deep_statement", f"{action}:lock-boundary", {}
                )
                self.store.lease_next_job(
                    ["deep_statement"], "worker-a", 10, utc_at(0)
                )
                followup = JobSpec(
                    "feature_build", f"followup:{action}:lock-boundary", {}
                )
                holder = sqlite3.connect(
                    self.db_path, timeout=5, isolation_level=None
                )
                holder.execute("BEGIN IMMEDIATE")
                begin_attempted = threading.Event()
                clock_sampled = threading.Event()
                after_expiry = threading.Event()
                sampled_before_begin: list[bool] = []
                errors: list[BaseException] = []
                real_connect = self.store._connect

                class ObservedConnection:
                    def __init__(self, connection):
                        self.connection = connection

                    def __getattr__(self, name):
                        return getattr(self.connection, name)

                    def execute(self, sql, parameters=()):
                        if sql == "BEGIN IMMEDIATE":
                            sampled_before_begin.append(clock_sampled.is_set())
                            begin_attempted.set()
                        return self.connection.execute(sql, parameters)

                def controlled_now():
                    clock_sampled.set()
                    return utc_at(11) if after_expiry.is_set() else utc_at(9)

                def transition():
                    try:
                        if action == "complete":
                            self.store.complete_job_with_followups(
                                job_id, "worker-a", {"outcome": "late"}, (followup,)
                            )
                        else:
                            self.store.fail_job_with_followups(
                                job_id,
                                "worker-a",
                                {"reason": "late"},
                                False,
                                None,
                                (followup,),
                            )
                    except BaseException as error:
                        errors.append(error)

                try:
                    with (
                        patch.object(
                            self.store,
                            "_connect",
                            side_effect=lambda: ObservedConnection(real_connect()),
                        ),
                        patch(
                            "ashare_pipeline.state_store._utc_now",
                            side_effect=controlled_now,
                        ),
                    ):
                        worker = threading.Thread(target=transition)
                        worker.start()
                        self.assertTrue(begin_attempted.wait(timeout=5))
                        after_expiry.set()
                        holder.rollback()
                        worker.join(timeout=10)
                finally:
                    holder.close()

                self.assertFalse(worker.is_alive())
                self.assertEqual(sampled_before_begin, [False])
                self.assertEqual(len(errors), 1)
                self.assertIsInstance(errors[0], ValueError)
                job = self.store.get_job(job_id)
                self.assertEqual(job["status"], "running")
                self.assertEqual(job["lease_worker"], "worker-a")
                self.assertEqual(job["lease_expires_at"], utc_at(10))
                self.assertIsNone(
                    next(
                        (
                            item
                            for item in self.store.list_jobs(["feature_build"])
                            if item["idempotency_key"] == followup.idempotency_key
                        ),
                        None,
                    )
                )

    def test_final_transitions_resample_after_followup_preparation(self) -> None:
        for action in ("complete", "fail"):
            with self.subTest(action=action):
                job_id = self.store.enqueue_job(
                    "deep_statement", f"{action}:followup-time-boundary", {}
                )
                self.store.lease_next_job(
                    ["deep_statement"], "worker-a", 10, utc_at(0)
                )
                followup = JobSpec(
                    "feature_build", f"followup:{action}:time-boundary", {}
                )
                followup_entered = threading.Event()
                release_followup = threading.Event()
                after_expiry = threading.Event()
                errors: list[BaseException] = []
                real_insert = self.store._insert_followups

                def controlled_now():
                    return utc_at(11) if after_expiry.is_set() else utc_at(9)

                def blocked_insert(*args, **kwargs):
                    followup_entered.set()
                    if not release_followup.wait(timeout=5):
                        raise RuntimeError("test did not release followup preparation")
                    return real_insert(*args, **kwargs)

                def transition():
                    try:
                        if action == "complete":
                            self.store.complete_job_with_followups(
                                job_id, "worker-a", {"outcome": "late"}, (followup,)
                            )
                        else:
                            self.store.fail_job_with_followups(
                                job_id,
                                "worker-a",
                                {"reason": "late"},
                                False,
                                None,
                                (followup,),
                            )
                    except BaseException as error:
                        errors.append(error)

                with (
                    patch("ashare_pipeline.state_store._utc_now", side_effect=controlled_now),
                    patch.object(
                        self.store, "_insert_followups", side_effect=blocked_insert
                    ),
                ):
                    worker = threading.Thread(target=transition)
                    worker.start()
                    self.assertTrue(followup_entered.wait(timeout=5))
                    after_expiry.set()
                    release_followup.set()
                    worker.join(timeout=10)

                self.assertFalse(worker.is_alive())
                self.assertEqual(len(errors), 1)
                self.assertIsInstance(errors[0], ValueError)
                job = self.store.get_job(job_id)
                self.assertEqual(job["status"], "running")
                self.assertEqual(job["lease_worker"], "worker-a")
                self.assertEqual(job["lease_expires_at"], utc_at(10))
                self.assertIsNone(
                    next(
                        (
                            item
                            for item in self.store.list_jobs(["feature_build"])
                            if item["idempotency_key"] == followup.idempotency_key
                        ),
                        None,
                    )
                )

    def _assert_terminal_serialization_resamples_before_update(
        self, action: str
    ) -> None:
        job_id = self.store.enqueue_job(
            "deep_statement", f"{action}:serialization-time-boundary", {}
        )
        self.store.lease_next_job(["deep_statement"], "worker-a", 10, utc_at(0))
        job_before = self.store.get_job(job_id)
        followup = JobSpec(
            "feature_build", f"followup:{action}:serialization-time-boundary", {}
        )
        payload = {"outcome": "late"} if action == "complete" else {"reason": "late"}
        serialization_entered = threading.Event()
        release_serialization = threading.Event()
        after_expiry = threading.Event()
        errors: list[BaseException] = []
        real_json = state_store_module._json

        def controlled_now():
            return utc_at(11) if after_expiry.is_set() else utc_at(9)

        def blocked_json(value):
            if value is payload:
                serialization_entered.set()
                if not release_serialization.wait(timeout=5):
                    raise RuntimeError("test did not release terminal serialization")
            return real_json(value)

        def transition():
            try:
                if action == "complete":
                    self.store.complete_job_with_followups(
                        job_id, "worker-a", payload, (followup,)
                    )
                else:
                    self.store.fail_job_with_followups(
                        job_id,
                        "worker-a",
                        payload,
                        False,
                        None,
                        (followup,),
                    )
            except BaseException as error:
                errors.append(error)

        with (
            patch("ashare_pipeline.state_store._utc_now", side_effect=controlled_now),
            patch("ashare_pipeline.state_store._json", side_effect=blocked_json),
        ):
            worker = threading.Thread(target=transition)
            worker.start()
            try:
                self.assertTrue(serialization_entered.wait(timeout=5))
                after_expiry.set()
            finally:
                release_serialization.set()
            worker.join(timeout=10)

        self.assertFalse(worker.is_alive())
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], ValueError)
        self.assertEqual(self.store.get_job(job_id), job_before)
        self.assertIsNone(
            next(
                (
                    item
                    for item in self.store.list_jobs(["feature_build"])
                    if item["idempotency_key"] == followup.idempotency_key
                ),
                None,
            )
        )

    def test_complete_resamples_after_result_serialization(self) -> None:
        self._assert_terminal_serialization_resamples_before_update("complete")

    def test_fail_resamples_after_error_serialization(self) -> None:
        self._assert_terminal_serialization_resamples_before_update("fail")

    def test_owned_job_transaction_fences_wrong_expired_and_valid_owners(self) -> None:
        valid_id = self.store.enqueue_job("deep_statement", "owned-mutation:valid", {})
        self.store.lease_next_job(["deep_statement"], "worker-a", 3600)

        with self.assertRaisesRegex(ValueError, "lease owner"):
            with self.store.owned_job_transaction(valid_id, "worker-b") as connection:
                connection.execute(
                    "INSERT INTO quality_issue VALUES (?,?,?,?,?,?,?)",
                    ("wrong", None, None, "warning", "wrong", "{}", utc_at(1)),
                )

        expired_id = self.store.enqueue_job("deep_statement", "owned-mutation:expired", {})
        self.store.lease_next_job(["deep_statement"], "worker-a", 3600)
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                "UPDATE job SET lease_expires_at = ? WHERE id = ?",
                ("2000-01-01T00:00:00+00:00", expired_id),
            )
            connection.commit()
        with self.assertRaisesRegex(ValueError, "lease owner"):
            with self.store.owned_job_transaction(expired_id, "worker-a") as connection:
                connection.execute(
                    "INSERT INTO quality_issue VALUES (?,?,?,?,?,?,?)",
                    ("expired", None, None, "warning", "expired", "{}", utc_at(1)),
                )

        with self.store.owned_job_transaction(valid_id, "worker-a") as connection:
            connection.execute(
                "INSERT INTO quality_issue VALUES (?,?,?,?,?,?,?)",
                ("valid", None, None, "warning", "valid", "{}", utc_at(1)),
            )
        with closing(sqlite3.connect(self.db_path)) as connection:
            ids = [row[0] for row in connection.execute("SELECT id FROM quality_issue")]
        self.assertEqual(ids, ["valid"])

        expiring_id = self.store.enqueue_job(
            "deep_statement", "owned-mutation:expires-before-commit", {}
        )
        self.store.lease_next_job(
            ["deep_statement"], "worker-a", 60, utc_at(0)
        )
        with patch(
            "ashare_pipeline.state_store._utc_now",
            side_effect=(utc_at(1), utc_at(61)),
        ), self.assertRaisesRegex(ValueError, "lease owner"):
            with self.store.owned_job_transaction(
                expiring_id, "worker-a"
            ) as connection:
                connection.execute(
                    "INSERT INTO quality_issue VALUES (?,?,?,?,?,?,?)",
                    ("late", None, None, "warning", "late", "{}", utc_at(1)),
                )
        with closing(sqlite3.connect(self.db_path)) as connection:
            self.assertIsNone(
                connection.execute(
                    "SELECT 1 FROM quality_issue WHERE id = 'late'"
                ).fetchone()
            )

    def test_renew_job_lease_rejects_nonpositive_duration(self) -> None:
        job_id = self.store.enqueue_job("deep_statement", "statement-duration", {})
        self.store.lease_next_job(["deep_statement"], "worker-a", 60, utc_at(0))

        for lease_seconds in (0, -1):
            with self.subTest(lease_seconds=lease_seconds), self.assertRaisesRegex(
                ValueError, "lease_seconds"
            ):
                self.store.renew_job_lease(
                    job_id, "worker-a", lease_seconds, utc_at(1)
                )

    def test_expired_and_completed_jobs_cannot_renew(self) -> None:
        expired_id = self.store.enqueue_job("deep_statement", "statement-expired", {})
        self.store.lease_next_job(["deep_statement"], "worker-a", 10, utc_at(0))
        with self.assertRaisesRegex(ValueError, "lease owner"):
            self.store.renew_job_lease(expired_id, "worker-a", 60, utc_at(10))

        completed_id = self.store.enqueue_job("fetch", "fetch-complete", {})
        self.store.lease_next_job(["fetch"], "worker-a", 60, utc_at(20))
        self.store.complete_job(completed_id, {"rows": 1})
        with self.assertRaisesRegex(ValueError, "lease owner"):
            self.store.renew_job_lease(completed_id, "worker-a", 60, utc_at(21))

    def test_wrong_worker_cannot_complete_or_fail_owned_job(self) -> None:
        followup = JobSpec("feature_build", "feature:wrong-owner", {"version": 1})
        complete_id = self.store.enqueue_job("deep_statement", "complete:owned", {})
        self.store.lease_next_job(["deep_statement"], "worker-a", 60)
        with self.assertRaisesRegex(ValueError, "lease owner"):
            self.store.complete_job_with_followups(
                complete_id, "worker-b", {"snapshot": "a" * 64}, (followup,)
            )

        fail_id = self.store.enqueue_job("deep_statement", "fail:owned", {})
        self.store.lease_next_job(["deep_statement"], "worker-a", 60)
        with self.assertRaisesRegex(ValueError, "lease owner"):
            self.store.fail_job_with_followups(
                fail_id,
                "worker-b",
                {"reason": "temporary"},
                True,
                utc_at(120),
                (followup,),
            )

        self.assertEqual(self.store.get_job(complete_id)["status"], "running")
        self.assertEqual(self.store.get_job(fail_id)["status"], "running")
        self.assertEqual(self.store.list_jobs(["feature_build"]), [])

    def test_expired_worker_cannot_complete_or_fail_owned_job(self) -> None:
        for action in ("complete", "fail"):
            with self.subTest(action=action):
                job_id = self.store.enqueue_job(
                    "deep_statement", f"statement:stale:{action}", {}
                )
                self.store.lease_next_job(["deep_statement"], "worker-a", 60)
                with closing(sqlite3.connect(self.db_path)) as connection:
                    connection.execute(
                        "UPDATE job SET lease_expires_at = ? WHERE id = ?",
                        ("2000-01-01T00:00:00+00:00", job_id),
                    )
                    connection.commit()
                with self.assertRaisesRegex(ValueError, "lease owner"):
                    if action == "complete":
                        self.store.complete_job_with_followups(
                            job_id, "worker-a", {"rows": 1}, ()
                        )
                    else:
                        self.store.fail_job_with_followups(
                            job_id,
                            "worker-a",
                            {"reason": "late"},
                            False,
                            None,
                            (),
                        )
                self.assertEqual(self.store.get_job(job_id)["status"], "running")

    def test_owned_kinds_reject_ownerless_legacy_transitions_after_release(self) -> None:
        for kind in ("deep_financial", "deep_statement", "feature_build"):
            with self.subTest(kind=kind):
                job_id = self.store.enqueue_job(kind, f"owned:legacy:{kind}", {})
                self.store.lease_next_job([kind], "worker-a", 10, utc_at(0))
                self.assertEqual(self.store.recover_expired_leases(utc_at(11)), 1)
                leased = self.store.lease_next_job([kind], "worker-b", 60, utc_at(11))

                with self.assertRaisesRegex(ValueError, "owner"):
                    self.store.complete_job(job_id, {"outcome": "stale-complete"})
                with self.assertRaisesRegex(ValueError, "owner"):
                    self.store.fail_job(
                        job_id, {"reason": "stale-failure"}, False
                    )

                current = self.store.get_job(job_id)
                self.assertEqual(current["status"], "running")
                self.assertEqual(current["lease_worker"], "worker-b")
                self.assertEqual(current["lease_expires_at"], leased["lease_expires_at"])

    def test_strict_success_clears_recovered_failure_fields(self) -> None:
        now = datetime.now(UTC)
        old_start = (now - timedelta(minutes=2)).isoformat()
        recovery_time = (now - timedelta(minutes=1)).isoformat()
        job_id = self.store.enqueue_job("deep_statement", "statement:recovered", {})
        self.store.lease_next_job(["deep_statement"], "worker-a", 10, old_start)
        self.assertEqual(self.store.recover_expired_leases(recovery_time), 1)
        self.store.lease_next_job(["deep_statement"], "worker-b", 3600)
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                "UPDATE job SET next_retry_at = ? WHERE id = ?",
                ((now + timedelta(hours=1)).isoformat(), job_id),
            )
            connection.commit()

        self.store.complete_job_with_followups(
            job_id, "worker-b", {"outcome": "recovered"}, ()
        )

        completed = self.store.get_job(job_id)
        self.assertEqual(completed["status"], "succeeded")
        self.assertIsNone(completed["error"])
        self.assertIsNone(completed["next_retry_at"])

    def test_malformed_statement_reconciliation_commits_verified_recovery_once(self) -> None:
        case = self.malformed_reconciliation_case("success")
        statement_snapshots = copy.deepcopy(
            case["followup"].payload["statement_snapshots"]
        )
        statement_snapshots["balance_sheet"], _ = (
            self.add_succeeded_reconciliation_sibling(
                case, "balance_sheet", label="success-balance"
            )
        )
        statement_snapshots["cash_flow_sheet"], _ = (
            self.add_succeeded_reconciliation_sibling(
                case,
                "cash_flow_sheet",
                label="success-cash",
                outcome="reconciled_verified_snapshot",
            )
        )
        followup = self.reconciliation_followup(
            case, statement_snapshots=statement_snapshots
        )
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                """UPDATE job SET lease_worker = 'stale-worker',
                lease_expires_at = ?, next_retry_at = ? WHERE id = ?""",
                (utc_at(10), utc_at(20), case["job_id"]),
            )
            connection.commit()

        recovered = self.store.reconcile_malformed_statement(
            case["job_id"],
            expected_idempotency_key=case["idempotency_key"],
            expected_payload=case["payload"],
            expected_quality_issue_id=case["issue_id"],
            expected_quality_issue_details=case["issue_details"],
            source_snapshot_id=case["snapshot_id"],
            source_snapshot_hash=case["snapshot_hash"],
            facts=(case["fact"],),
            followup=followup,
            result=case["result"],
        )

        self.assertTrue(recovered)
        completed = self.store.get_job(case["job_id"])
        self.assertEqual(completed["status"], "succeeded")
        self.assertEqual(completed["result"], case["result"])
        self.assertIsNone(completed["error"])
        self.assertIsNone(completed["lease_worker"])
        self.assertIsNone(completed["lease_expires_at"])
        self.assertIsNone(completed["next_retry_at"])
        self.assertEqual(
            self.store.list_financial_facts("SH600001"), [case["fact"]]
        )
        followups = self.store.list_jobs(["feature_build"])
        self.assertEqual(len(followups), 1)
        self.assertEqual(followups[0]["idempotency_key"], followup.idempotency_key)
        self.assertEqual(followups[0]["payload"], followup.payload)
        with closing(sqlite3.connect(self.db_path)) as connection:
            stored_result = connection.execute(
                "SELECT result_json FROM job WHERE id = ?", (case["job_id"],)
            ).fetchone()[0]
        self.assertEqual(
            stored_result,
            f'{{"mapping_version":"{MAPPING_VERSION}",'
            '"outcome":"reconciled_verified_snapshot",'
            '"recovered_error":"malformed_statement",'
            f'"snapshot_hash":"{case["snapshot_hash"]}"}}',
        )

        repeated = self.store.reconcile_malformed_statement(
            case["job_id"],
            expected_idempotency_key=case["idempotency_key"],
            expected_payload=case["payload"],
            expected_quality_issue_id=case["issue_id"],
            expected_quality_issue_details=case["issue_details"],
            source_snapshot_id=case["snapshot_id"],
            source_snapshot_hash=case["snapshot_hash"],
            facts=(case["fact"],),
            followup=followup,
            result=case["result"],
        )
        self.assertFalse(repeated)
        self.assertEqual(len(self.store.list_jobs(["feature_build"])), 1)
        self.assertEqual(len(self.store.list_financial_facts("SH600001")), 1)

    def test_reconciliation_allows_short_cross_midnight_snapshot_within_job_lifetime(
        self,
    ) -> None:
        case = self.malformed_reconciliation_case("cross-midnight")
        refresh_date = case["payload"]["refresh_date"]
        self.assertIsInstance(refresh_date, str)
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                "UPDATE source_snapshot SET fetched_at=?, created_at=? WHERE id=?",
                (
                    f"{refresh_date}T16:00:07+00:00",
                    f"{refresh_date}T16:00:07.250000+00:00",
                    case["snapshot_id"],
                ),
            )
            connection.execute(
                """UPDATE job SET created_at=?, updated_at=? WHERE id=?""",
                (
                    f"{refresh_date}T15:55:00+00:00",
                    f"{refresh_date}T16:00:08+00:00",
                    case["job_id"],
                ),
            )
            connection.execute(
                "UPDATE quality_issue SET created_at=? WHERE id=?",
                (f"{refresh_date}T16:00:07.500000+00:00", case["issue_id"]),
            )
            connection.commit()

        recovered = self.store.reconcile_malformed_statement(
            case["job_id"], **self.reconciliation_arguments(case)
        )

        self.assertTrue(recovered)
        self.assertEqual(self.store.get_job(case["job_id"])["status"], "succeeded")
        self.assertEqual(self.store.list_financial_facts("SH600001"), [case["fact"]])

    def test_reconciliation_rejects_cross_midnight_snapshot_outside_grace_without_writes(
        self,
    ) -> None:
        case = self.malformed_reconciliation_case("cross-midnight-late")
        refresh_date = case["payload"]["refresh_date"]
        self.assertIsInstance(refresh_date, str)
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                "UPDATE source_snapshot SET fetched_at=?, created_at=? WHERE id=?",
                (
                    f"{refresh_date}T16:00:15.001000+00:00",
                    f"{refresh_date}T16:00:15.001500+00:00",
                    case["snapshot_id"],
                ),
            )
            connection.execute(
                """UPDATE job SET created_at=?, updated_at=? WHERE id=?""",
                (
                    f"{refresh_date}T15:55:00+00:00",
                    f"{refresh_date}T16:00:15.002000+00:00",
                    case["job_id"],
                ),
            )
            connection.execute(
                "UPDATE quality_issue SET created_at=? WHERE id=?",
                (f"{refresh_date}T16:00:15.001750+00:00", case["issue_id"]),
            )
            connection.commit()

        with self.assertRaisesRegex(ValueError, "snapshot refresh date"):
            self.store.reconcile_malformed_statement(
                case["job_id"], **self.reconciliation_arguments(case)
            )

        self.assertEqual(
            self.store.get_job(case["job_id"])["status"], "terminal_failed"
        )
        self.assertEqual(self.store.list_financial_facts("SH600001"), [])
        self.assertEqual(self.store.list_jobs(["feature_build"]), [])

    def test_reconciliation_rejects_cross_midnight_evidence_out_of_order_without_writes(
        self,
    ) -> None:
        case = self.malformed_reconciliation_case("cross-midnight-out-of-order")
        refresh_date = case["payload"]["refresh_date"]
        self.assertIsInstance(refresh_date, str)
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                "UPDATE source_snapshot SET fetched_at=?, created_at=? WHERE id=?",
                (
                    f"{refresh_date}T16:00:07.139000+00:00",
                    f"{refresh_date}T16:00:07.100000+00:00",
                    case["snapshot_id"],
                ),
            )
            connection.execute(
                """UPDATE job SET created_at=?, updated_at=? WHERE id=?""",
                (
                    f"{refresh_date}T15:55:00+00:00",
                    f"{refresh_date}T16:00:08+00:00",
                    case["job_id"],
                ),
            )
            connection.execute(
                "UPDATE quality_issue SET created_at=? WHERE id=?",
                (f"{refresh_date}T16:00:07.500000+00:00", case["issue_id"]),
            )
            connection.commit()

        with self.assertRaisesRegex(ValueError, "cross-midnight chronology"):
            self.store.reconcile_malformed_statement(
                case["job_id"], **self.reconciliation_arguments(case)
            )

        self.assertEqual(
            self.store.get_job(case["job_id"])["status"], "terminal_failed"
        )
        self.assertEqual(self.store.list_financial_facts("SH600001"), [])
        self.assertEqual(self.store.list_jobs(["feature_build"]), [])

    def test_reconciliation_rejects_cross_midnight_job_started_too_early_without_writes(
        self,
    ) -> None:
        case = self.malformed_reconciliation_case("cross-midnight-early-job")
        refresh_date = case["payload"]["refresh_date"]
        self.assertIsInstance(refresh_date, str)
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                "UPDATE source_snapshot SET fetched_at=?, created_at=? WHERE id=?",
                (
                    f"{refresh_date}T16:00:07+00:00",
                    f"{refresh_date}T16:00:07.250000+00:00",
                    case["snapshot_id"],
                ),
            )
            connection.execute(
                """UPDATE job SET created_at=?, updated_at=? WHERE id=?""",
                (
                    f"{refresh_date}T15:54:59+00:00",
                    f"{refresh_date}T16:00:08+00:00",
                    case["job_id"],
                ),
            )
            connection.execute(
                "UPDATE quality_issue SET created_at=? WHERE id=?",
                (f"{refresh_date}T16:00:07.500000+00:00", case["issue_id"]),
            )
            connection.commit()

        with self.assertRaisesRegex(ValueError, "snapshot refresh date"):
            self.store.reconcile_malformed_statement(
                case["job_id"], **self.reconciliation_arguments(case)
            )

        self.assertEqual(
            self.store.get_job(case["job_id"])["status"], "terminal_failed"
        )
        self.assertEqual(self.store.list_financial_facts("SH600001"), [])
        self.assertEqual(self.store.list_jobs(["feature_build"]), [])

    def test_reconciliation_rejects_primary_wrong_refresh_or_future_as_of(self) -> None:
        for label in ("wrong-refresh", "future-as-of"):
            with self.subTest(label=label):
                case = self.malformed_reconciliation_case(f"primary-{label}")
                followup = case["followup"]
                if label == "wrong-refresh":
                    wrong_day = (
                        datetime.fromisoformat(case["snapshot_fetched_at"])
                        + timedelta(days=1)
                    ).isoformat()
                    with closing(sqlite3.connect(self.db_path)) as connection:
                        connection.execute(
                            "UPDATE source_snapshot SET fetched_at=? WHERE id=?",
                            (wrong_day, case["snapshot_id"]),
                        )
                        connection.commit()
                else:
                    payload = copy.deepcopy(case["followup"].payload)
                    payload["as_of_utc"] = (
                        datetime.fromisoformat(case["snapshot_fetched_at"])
                        - timedelta(minutes=1)
                    ).isoformat()
                    seeded = dict(case)
                    seeded["followup"] = JobSpec(
                        "feature_build",
                        case["followup"].idempotency_key,
                        payload,
                    )
                    followup = self.reconciliation_followup(seeded)

                with self.assertRaisesRegex(ValueError, "snapshot"):
                    self.store.reconcile_malformed_statement(
                        case["job_id"],
                        **self.reconciliation_arguments(case, followup=followup),
                    )
                self.assertEqual(
                    self.store.get_job(case["job_id"])["status"],
                    "terminal_failed",
                )
                self.assertEqual(self.store.list_financial_facts("SH600001"), [])

    def test_reconciliation_rejects_missing_or_mismatched_calendar_snapshot(self) -> None:
        labels = (
            "missing",
            "fake-id",
            "wrong-source",
            "wrong-dataset",
            "wrong-request",
            "wrong-hash",
            "future",
        )
        for label in labels:
            with self.subTest(label=label):
                case = self.malformed_reconciliation_case(f"calendar-{label}")
                calendar = copy.deepcopy(
                    case["followup"].payload["trade_calendar_snapshot"]
                )
                if label == "missing":
                    calendar = None
                elif label == "fake-id":
                    calendar["source_snapshot_id"] = "missing-calendar"
                elif label == "wrong-hash":
                    calendar["payload_hash"] = "f" * 64
                else:
                    mutations = {
                        "wrong-source": ("source", "akshare"),
                        "wrong-dataset": ("dataset", "daily"),
                        "wrong-request": ("request_fingerprint", "f" * 64),
                        "future": ("fetched_at", "2026-09-01T16:00:01+00:00"),
                    }
                    column, value = mutations[label]
                    with closing(sqlite3.connect(self.db_path)) as connection:
                        connection.execute(
                            f"UPDATE source_snapshot SET {column}=? WHERE id=?",
                            (value, case["calendar_id"]),
                        )
                        connection.commit()
                followup = self.reconciliation_followup(
                    case, trade_calendar_snapshot=calendar
                )

                with self.assertRaisesRegex(ValueError, "calendar"):
                    self.store.reconcile_malformed_statement(
                        case["job_id"],
                        **self.reconciliation_arguments(case, followup=followup),
                    )
                self.assertEqual(self.store.list_financial_facts("SH600001"), [])

    def test_reconciliation_rejects_unbound_or_mismatched_sibling_snapshot(self) -> None:
        labels = (
            "fake-snapshot-id",
            "wrong-snapshot-db",
            "missing-job",
            "wrong-job-payload",
            "wrong-job-result",
        )
        for label in labels:
            with self.subTest(label=label):
                case = self.malformed_reconciliation_case(f"sibling-{label}")
                sibling, sibling_job_id = self.add_succeeded_reconciliation_sibling(
                    case, "balance_sheet", label=label
                )
                if label == "fake-snapshot-id":
                    sibling["source_snapshot_id"] = "missing-sibling"
                elif label == "wrong-snapshot-db":
                    with closing(sqlite3.connect(self.db_path)) as connection:
                        connection.execute(
                            "UPDATE source_snapshot SET source='baostock' WHERE id=?",
                            (sibling["source_snapshot_id"],),
                        )
                        connection.commit()
                elif label == "missing-job":
                    with closing(sqlite3.connect(self.db_path)) as connection:
                        connection.execute(
                            "DELETE FROM job WHERE id=?", (sibling_job_id,)
                        )
                        connection.commit()
                elif label == "wrong-job-payload":
                    with closing(sqlite3.connect(self.db_path)) as connection:
                        connection.execute(
                            "UPDATE job SET payload_json='{}' WHERE id=?",
                            (sibling_job_id,),
                        )
                        connection.commit()
                else:
                    with closing(sqlite3.connect(self.db_path)) as connection:
                        connection.execute(
                            "UPDATE job SET result_json=? WHERE id=?",
                            (
                                '{"outcome":"statement_persisted",'
                                f'"snapshot_hash":"{"f" * 64}"}}',
                                sibling_job_id,
                            ),
                        )
                        connection.commit()
                snapshots = copy.deepcopy(
                    case["followup"].payload["statement_snapshots"]
                )
                snapshots["balance_sheet"] = sibling
                followup = self.reconciliation_followup(
                    case, statement_snapshots=snapshots
                )

                with self.assertRaisesRegex(ValueError, "snapshot|sibling"):
                    self.store.reconcile_malformed_statement(
                        case["job_id"],
                        **self.reconciliation_arguments(case, followup=followup),
                    )
                self.assertEqual(self.store.list_financial_facts("SH600001"), [])

    def test_reconciliation_requires_exact_issue_binding_and_fact_row_hash(self) -> None:
        labels = (
            "bound-other-job",
            "bound-other-snapshot",
            "wrong-details",
            "wrong-row-hash",
        )
        for label in labels:
            with self.subTest(label=label):
                case = self.malformed_reconciliation_case(f"issue-{label}")
                issue_id = case["issue_id"]
                issue_details = copy.deepcopy(case["issue_details"])
                if label == "bound-other-job":
                    other_job_id = self.store.enqueue_job("fetch", f"other:{label}", {})
                    with closing(sqlite3.connect(self.db_path)) as connection:
                        connection.execute(
                            "UPDATE quality_issue_binding SET job_id=? WHERE issue_id=?",
                            (other_job_id, issue_id),
                        )
                        connection.commit()
                elif label == "bound-other-snapshot":
                    with closing(sqlite3.connect(self.db_path)) as connection:
                        connection.execute(
                            "UPDATE quality_issue_binding SET source_snapshot_id=? WHERE issue_id=?",
                            (case["calendar_id"], issue_id),
                        )
                        connection.commit()
                elif label == "wrong-details":
                    issue_details["dataset"] = "balance_sheet"
                else:
                    issue_details["details"]["row_hash"] = "f" * 64
                    issue_id = self.store.record_quality_issue(
                        run_id=None,
                        score_run_id=None,
                        severity="error",
                        code="statement_report_date_invalid",
                        details=issue_details,
                    )

                with self.assertRaisesRegex(ValueError, "quality issue|row hash"):
                    self.store.reconcile_malformed_statement(
                        case["job_id"],
                        **self.reconciliation_arguments(
                            case,
                            issue_id=issue_id,
                            issue_details=issue_details,
                        ),
                    )
                self.assertEqual(self.store.list_financial_facts("SH600001"), [])

    def test_reconciliation_uniquely_binds_legacy_issue(self) -> None:
        case = self.malformed_reconciliation_case("legacy-unique")
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                "DELETE FROM quality_issue_binding WHERE issue_id=?",
                (case["issue_id"],),
            )
            connection.commit()

        recovered = self.store.reconcile_malformed_statement(
            case["job_id"], **self.reconciliation_arguments(case)
        )

        self.assertTrue(recovered)
        with closing(sqlite3.connect(self.db_path)) as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT issue_id,job_id,source_snapshot_id FROM quality_issue_binding"
                ).fetchall(),
                [(case["issue_id"], case["job_id"], case["snapshot_id"])],
            )

    def test_reconciliation_rejects_legacy_issue_with_conflicting_bound_provenance(
        self,
    ) -> None:
        case = self.malformed_reconciliation_case("legacy-conflicting")
        other = self.malformed_reconciliation_case(
            "legacy-conflicting-other", raw_row_hash=case["fact"].raw_row_hash
        )
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                "DELETE FROM quality_issue_binding WHERE issue_id=?",
                (case["issue_id"],),
            )
            connection.execute(
                """UPDATE job SET status='succeeded', result_json='{}',
                last_error_json=NULL WHERE id=?""",
                (other["job_id"],),
            )
            connection.commit()

        with self.assertRaisesRegex(ValueError, "legacy quality issue.*conflicting"):
            self.store.reconcile_malformed_statement(
                case["job_id"], **self.reconciliation_arguments(case)
            )
        with closing(sqlite3.connect(self.db_path)) as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM quality_issue_binding WHERE issue_id=?",
                    (case["issue_id"],),
                ).fetchone()[0],
                0,
            )

    def test_reconciliation_rejects_legacy_issue_outside_current_job_lifetime(
        self,
    ) -> None:
        case = self.malformed_reconciliation_case("legacy-stale")
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                "DELETE FROM quality_issue_binding WHERE issue_id=?",
                (case["issue_id"],),
            )
            connection.execute(
                "UPDATE quality_issue SET created_at=? WHERE id=?",
                ("2000-01-01T00:00:00+00:00", case["issue_id"]),
            )
            connection.commit()

        with self.assertRaisesRegex(ValueError, "legacy quality issue.*lifetime"):
            self.store.reconcile_malformed_statement(
                case["job_id"], **self.reconciliation_arguments(case)
            )
        with closing(sqlite3.connect(self.db_path)) as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM quality_issue_binding WHERE issue_id=?",
                    (case["issue_id"],),
                ).fetchone()[0],
                0,
            )

    def test_reconciliation_rejects_ambiguous_unbound_legacy_issue_or_job(self) -> None:
        for label in ("duplicate-issue", "duplicate-job"):
            with self.subTest(label=label):
                case = self.malformed_reconciliation_case(f"legacy-{label}")
                with closing(sqlite3.connect(self.db_path)) as connection:
                    connection.execute(
                        "DELETE FROM quality_issue_binding WHERE issue_id=?",
                        (case["issue_id"],),
                    )
                    connection.commit()
                if label == "duplicate-issue":
                    self.store.record_quality_issue(
                        run_id=None,
                        score_run_id=None,
                        severity="error",
                        code="statement_report_date_invalid",
                        details=case["issue_details"],
                    )
                else:
                    payload = dict(case["payload"])
                    payload["refresh_date"] = (
                        datetime.fromisoformat(case["snapshot_fetched_at"])
                        + timedelta(days=1)
                    ).date().isoformat()
                    key = (
                        f"deep_statement:v1:{payload['security_id']}:{payload['dataset']}:"
                        f"{payload['report_period']}:{payload['refresh_date']}"
                    )
                    other_job = self.store.enqueue_job("deep_statement", key, payload)
                    worker = f"ambiguous-{label}"
                    self.store.lease_next_job(["deep_statement"], worker, 3600)
                    self.store.fail_job_with_followups(
                        other_job,
                        worker,
                        {"error_classification": "malformed_statement"},
                        False,
                        None,
                        (),
                    )

                with self.assertRaisesRegex(ValueError, "legacy|quality issue"):
                    self.store.reconcile_malformed_statement(
                        case["job_id"], **self.reconciliation_arguments(case)
                    )
                with closing(sqlite3.connect(self.db_path)) as connection:
                    self.assertEqual(
                        connection.execute(
                            "SELECT COUNT(*) FROM quality_issue_binding WHERE issue_id=?",
                            (case["issue_id"],),
                        ).fetchone()[0],
                        0,
                    )

    def test_malformed_statement_reconciliation_rejects_historical_mapping_facts(self) -> None:
        case = self.malformed_reconciliation_case("historical-mapping")
        historical = historical_mapping_fact(case["fact"])
        result = dict(case["result"])
        result["mapping_version"] = historical.mapping_version
        before_job = self.store.get_job(case["job_id"])

        with self.assertRaisesRegex(ValueError, "current mapping"):
            self.store.reconcile_malformed_statement(
                case["job_id"],
                expected_idempotency_key=case["idempotency_key"],
                expected_payload=case["payload"],
                expected_quality_issue_id=case["issue_id"],
                expected_quality_issue_details=case["issue_details"],
                source_snapshot_id=case["snapshot_id"],
                source_snapshot_hash=case["snapshot_hash"],
                facts=(historical,),
                followup=case["followup"],
                result=result,
            )

        self.assertEqual(self.store.get_job(case["job_id"]), before_job)
        self.assertEqual(self.store.list_financial_facts("SH600001"), [])
        self.assertEqual(self.store.list_jobs(["feature_build"]), [])

    def test_malformed_statement_reconciliation_rejects_same_id_fact_conflict(self) -> None:
        case = self.malformed_reconciliation_case("same-id-conflict")
        conflicting = replace(case["fact"], created_at=utc_at(99))
        self.assertEqual(
            self.store.insert_financial_facts((conflicting,)),
            (1, 0),
        )
        before_job = self.store.get_job(case["job_id"])

        with self.assertRaisesRegex(ValueError, "stored financial fact conflicts"):
            self.store.reconcile_malformed_statement(
                case["job_id"],
                expected_idempotency_key=case["idempotency_key"],
                expected_payload=case["payload"],
                expected_quality_issue_id=case["issue_id"],
                expected_quality_issue_details=case["issue_details"],
                source_snapshot_id=case["snapshot_id"],
                source_snapshot_hash=case["snapshot_hash"],
                facts=(case["fact"],),
                followup=case["followup"],
                result=case["result"],
            )

        self.assertEqual(self.store.get_job(case["job_id"]), before_job)
        self.assertEqual(
            self.store.list_financial_facts("SH600001"),
            [conflicting],
        )
        self.assertEqual(self.store.list_jobs(["feature_build"]), [])

    def test_malformed_statement_reconciliation_rejects_unbound_feature_followup(self) -> None:
        labels = (
            "wrong-security",
            "wrong-period",
            "wrong-snapshot-slot",
            "wrong-candidate-hash",
            "wrong-performance-hash",
            "wrong-key",
            "empty-industry",
            "nonboolean-reported",
            "invalid-as-of",
            "nonstring-as-of",
            "incomplete-calendar",
        )
        for label in labels:
            with self.subTest(label=label):
                case = self.malformed_reconciliation_case(
                    f"followup-{label}"
                )
                payload = copy.deepcopy(case["followup"].payload)
                if label == "wrong-security":
                    payload["security_id"] = "SH600002"
                elif label == "wrong-period":
                    payload["report_period"] = "2025-12-31"
                elif label == "wrong-snapshot-slot":
                    payload["statement_snapshots"]["profit_sheet"] = {
                        "source_snapshot_id": "other-snapshot",
                        "payload_hash": "f" * 64,
                    }
                elif label == "wrong-candidate-hash":
                    payload["candidate_set_hash"] = "f" * 64
                elif label == "wrong-performance-hash":
                    payload["performance_input_hash"] = "f" * 64
                elif label == "empty-industry":
                    payload["industry"] = ""
                elif label == "nonboolean-reported":
                    payload["reported_target_period"] = "yes"
                elif label == "invalid-as-of":
                    payload["as_of_utc"] = "not-a-timestamp"
                elif label == "nonstring-as-of":
                    payload["as_of_utc"] = None
                elif label == "incomplete-calendar":
                    payload["trade_calendar_snapshot"] = {
                        "payload_hash": "e" * 64
                    }

                statements = payload["statement_snapshots"]
                calendar = payload["trade_calendar_snapshot"]
                input_hash = feature_input_hash(
                    security_id=payload["security_id"],
                    report_period=payload["report_period"],
                    as_of_utc=payload["as_of_utc"],
                    candidate_set_hash=payload["candidate_set_hash"],
                    statement_snapshot_hashes={
                        dataset: (
                            value["payload_hash"]
                            if value is not None
                            else None
                        )
                        for dataset, value in statements.items()
                    },
                    trade_calendar_snapshot_hash=(
                        calendar["payload_hash"]
                        if isinstance(calendar, dict)
                        else None
                    ),
                )
                followup_key = (
                    "feature_build:v1:"
                    f"{payload['security_id']}:{payload['report_period']}:"
                    f"{input_hash}"
                )
                if label == "wrong-key":
                    followup_key = (
                        "feature_build:v1:SH600001:2026-06-30:"
                        + "0" * 64
                    )
                followup = JobSpec("feature_build", followup_key, payload)
                before_job = self.store.get_job(case["job_id"])
                expected_error = (
                    "as_of_utc is not canonical"
                    if label == "nonstring-as-of"
                    else "follow-up"
                )

                with self.assertRaisesRegex(ValueError, expected_error):
                    self.store.reconcile_malformed_statement(
                        case["job_id"],
                        expected_idempotency_key=case["idempotency_key"],
                        expected_payload=case["payload"],
                        expected_quality_issue_id=case["issue_id"],
                        expected_quality_issue_details=case["issue_details"],
                        source_snapshot_id=case["snapshot_id"],
                        source_snapshot_hash=case["snapshot_hash"],
                        facts=(case["fact"],),
                        followup=followup,
                        result=case["result"],
                    )

                self.assertEqual(
                    self.store.get_job(case["job_id"]), before_job
                )
                self.assertEqual(
                    self.store.list_financial_facts("SH600001"), []
                )
                self.assertEqual(
                    self.store.list_jobs(["feature_build"]), []
                )

    def test_malformed_statement_reconciliation_rejects_identity_mismatches_without_writes(self) -> None:
        cases = (
            ("wrong-kind", "UPDATE job SET kind='deep_financial' WHERE id=?", {}),
            (
                "wrong-error",
                "UPDATE job SET last_error_json='{\"error_classification\":\"terminal_source\"}' WHERE id=?",
                {},
            ),
            (
                "extra-error",
                "UPDATE job SET last_error_json='{\"detail\":\"old\",\"error_classification\":\"malformed_statement\"}' WHERE id=?",
                {},
            ),
            (
                "noncanonical-error",
                "UPDATE job SET last_error_json='{ \"error_classification\": \"malformed_statement\" }' WHERE id=?",
                {},
            ),
            ("wrong-key", None, {"expected_idempotency_key": "different:key"}),
            (
                "wrong-payload",
                None,
                {"expected_payload": {"security_id": "SH600001", "dataset": "profit_sheet"}},
            ),
            ("wrong-snapshot-id", None, {"source_snapshot_id": "missing-snapshot"}),
            ("wrong-snapshot-hash", None, {"source_snapshot_hash": "f" * 64}),
            (
                "wrong-snapshot-dataset",
                "UPDATE source_snapshot SET dataset='balance_sheet' WHERE id=?",
                {},
            ),
            (
                "wrong-snapshot-source",
                "UPDATE source_snapshot SET source='baostock' WHERE id=?",
                {},
            ),
            (
                "wrong-snapshot-request",
                f"UPDATE source_snapshot SET request_fingerprint='{'f' * 64}' WHERE id=?",
                {},
            ),
            ("wrong-status", "UPDATE job SET status='retryable_failed' WHERE id=?", {}),
        )
        for label, mutation, overrides in cases:
            with self.subTest(label=label):
                case = self.malformed_reconciliation_case(label)
                if mutation is not None:
                    target_id = (
                        case["snapshot_id"]
                        if label.startswith("wrong-snapshot-")
                        else case["job_id"]
                    )
                    with closing(sqlite3.connect(self.db_path)) as connection:
                        connection.execute(mutation, (target_id,))
                        connection.commit()
                arguments = {
                    "expected_idempotency_key": case["idempotency_key"],
                    "expected_payload": case["payload"],
                    "expected_quality_issue_id": case["issue_id"],
                    "expected_quality_issue_details": case["issue_details"],
                    "source_snapshot_id": case["snapshot_id"],
                    "source_snapshot_hash": case["snapshot_hash"],
                    "facts": (case["fact"],),
                    "followup": case["followup"],
                    "result": case["result"],
                }
                arguments.update(overrides)
                before_job = self.store.get_job(case["job_id"])
                before_fact_count = len(self.store.list_financial_facts("SH600001"))
                before_followup_count = len(self.store.list_jobs(["feature_build"]))

                recovered = self.store.reconcile_malformed_statement(
                    case["job_id"], **arguments
                )

                self.assertFalse(recovered)
                self.assertEqual(self.store.get_job(case["job_id"]), before_job)
                self.assertEqual(
                    len(self.store.list_financial_facts("SH600001")),
                    before_fact_count,
                )
                self.assertEqual(
                    len(self.store.list_jobs(["feature_build"])),
                    before_followup_count,
                )

    def test_malformed_statement_reconciliation_rejects_nonexact_result_without_writes(self) -> None:
        result_mutations = {
            "wrong-outcome": {"outcome": "statement_persisted"},
            "wrong-snapshot": {"snapshot_hash": "f" * 64},
            "wrong-mapping": {"mapping_version": "legacy-mapping"},
            "wrong-error": {"recovered_error": "terminal_source"},
            "extra-field": {"unexpected": True},
        }
        for label, mutation in result_mutations.items():
            with self.subTest(label=label):
                case = self.malformed_reconciliation_case(f"result-{label}")
                supplied_result = dict(case["result"])
                supplied_result.update(mutation)
                before_job = self.store.get_job(case["job_id"])
                with closing(sqlite3.connect(self.db_path)) as connection:
                    before_counts = (
                        connection.execute(
                            "SELECT COUNT(*) FROM financial_fact"
                        ).fetchone()[0],
                        connection.execute(
                            "SELECT COUNT(*) FROM job WHERE kind='feature_build'"
                        ).fetchone()[0],
                    )

                with self.assertRaisesRegex(ValueError, "result"):
                    self.store.reconcile_malformed_statement(
                        case["job_id"],
                        expected_idempotency_key=case["idempotency_key"],
                        expected_payload=case["payload"],
                        expected_quality_issue_id=case["issue_id"],
                        expected_quality_issue_details=case["issue_details"],
                        source_snapshot_id=case["snapshot_id"],
                        source_snapshot_hash=case["snapshot_hash"],
                        facts=(case["fact"],),
                        followup=case["followup"],
                        result=supplied_result,
                    )

                self.assertEqual(self.store.get_job(case["job_id"]), before_job)
                with closing(sqlite3.connect(self.db_path)) as connection:
                    after_counts = (
                        connection.execute(
                            "SELECT COUNT(*) FROM financial_fact"
                        ).fetchone()[0],
                        connection.execute(
                            "SELECT COUNT(*) FROM job WHERE kind='feature_build'"
                        ).fetchone()[0],
                    )
                self.assertEqual(after_counts, before_counts)

    def test_malformed_statement_reconciliation_rejects_unbound_facts_and_followup_without_writes(self) -> None:
        labels = (
            "empty-facts",
            "wrong-fact-snapshot",
            "wrong-fact-security",
            "wrong-fact-statement",
            "mixed-mapping-versions",
            "wrong-followup-kind",
        )
        for label in labels:
            with self.subTest(label=label):
                case = self.malformed_reconciliation_case(f"binding-{label}")
                facts = (case["fact"],)
                followup = case["followup"]
                if label == "empty-facts":
                    facts = ()
                elif label == "wrong-fact-snapshot":
                    other_snapshot_id, _ = self.store.record_snapshot(
                        "akshare",
                        "profit_sheet",
                        canonical_sha256({"other_request": label}),
                        canonical_sha256({"other_snapshot": label}),
                        f"data/raw/{label}.json",
                        1,
                        utc_at(1),
                    )
                    facts = (
                        rebuild_fact(
                            case["fact"], source_snapshot_id=other_snapshot_id
                        ),
                    )
                elif label == "wrong-fact-security":
                    facts = (rebuild_fact(case["fact"], security_id="SH600002"),)
                elif label == "wrong-fact-statement":
                    facts = (rebuild_fact(case["fact"], statement="balance"),)
                elif label == "mixed-mapping-versions":
                    second = rebuild_fact(
                        case["fact"], raw_row_hash=canonical_sha256({"second": label})
                    )
                    facts = (case["fact"], replace(second, mapping_version="legacy"))
                else:
                    followup = JobSpec(
                        "fetch",
                        f"not-feature:{label}",
                        {"security_id": "SH600001"},
                    )
                before_job = self.store.get_job(case["job_id"])
                with closing(sqlite3.connect(self.db_path)) as connection:
                    before_counts = (
                        connection.execute(
                            "SELECT COUNT(*) FROM financial_fact"
                        ).fetchone()[0],
                        connection.execute("SELECT COUNT(*) FROM job").fetchone()[0],
                    )

                with self.assertRaisesRegex(ValueError, "facts|follow-up"):
                    self.store.reconcile_malformed_statement(
                        case["job_id"],
                        expected_idempotency_key=case["idempotency_key"],
                        expected_payload=case["payload"],
                        expected_quality_issue_id=case["issue_id"],
                        expected_quality_issue_details=case["issue_details"],
                        source_snapshot_id=case["snapshot_id"],
                        source_snapshot_hash=case["snapshot_hash"],
                        facts=facts,
                        followup=followup,
                        result=case["result"],
                    )

                self.assertEqual(self.store.get_job(case["job_id"]), before_job)
                with closing(sqlite3.connect(self.db_path)) as connection:
                    after_counts = (
                        connection.execute(
                            "SELECT COUNT(*) FROM financial_fact"
                        ).fetchone()[0],
                        connection.execute("SELECT COUNT(*) FROM job").fetchone()[0],
                    )
                self.assertEqual(after_counts, before_counts)

    def test_malformed_statement_reconciliation_rolls_back_followup_conflict(self) -> None:
        case = self.malformed_reconciliation_case("followup-conflict")
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                "DELETE FROM quality_issue_binding WHERE issue_id=?",
                (case["issue_id"],),
            )
            connection.commit()
        self.store.enqueue_job(
            "feature_build",
            case["followup"].idempotency_key,
            {"security_id": "SH600002", "report_period": "2026-06-30"},
        )
        before_job = self.store.get_job(case["job_id"])

        with self.assertRaisesRegex(ValueError, "idempotency"):
            self.store.reconcile_malformed_statement(
                case["job_id"],
                expected_idempotency_key=case["idempotency_key"],
                expected_payload=case["payload"],
                expected_quality_issue_id=case["issue_id"],
                expected_quality_issue_details=case["issue_details"],
                source_snapshot_id=case["snapshot_id"],
                source_snapshot_hash=case["snapshot_hash"],
                facts=(case["fact"],),
                followup=case["followup"],
                result=case["result"],
            )

        self.assertEqual(self.store.get_job(case["job_id"]), before_job)
        self.assertEqual(self.store.list_financial_facts("SH600001"), [])
        feature_jobs = self.store.list_jobs(["feature_build"])
        self.assertEqual(len(feature_jobs), 1)
        self.assertEqual(feature_jobs[0]["payload"]["security_id"], "SH600002")
        with closing(sqlite3.connect(self.db_path)) as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM quality_issue_binding WHERE issue_id=?",
                    (case["issue_id"],),
                ).fetchone()[0],
                0,
            )

    def test_malformed_statement_reconciliation_rolls_back_trigger_failure(self) -> None:
        case = self.malformed_reconciliation_case("trigger-failure")
        before_job = self.store.get_job(case["job_id"])
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                """CREATE TRIGGER reject_reconciliation_followup
                BEFORE INSERT ON job WHEN NEW.kind='feature_build'
                BEGIN SELECT RAISE(ABORT, 'forced reconciliation failure'); END"""
            )
            connection.commit()

        with self.assertRaisesRegex(
            sqlite3.IntegrityError, "forced reconciliation failure"
        ):
            self.store.reconcile_malformed_statement(
                case["job_id"],
                expected_idempotency_key=case["idempotency_key"],
                expected_payload=case["payload"],
                expected_quality_issue_id=case["issue_id"],
                expected_quality_issue_details=case["issue_details"],
                source_snapshot_id=case["snapshot_id"],
                source_snapshot_hash=case["snapshot_hash"],
                facts=(case["fact"],),
                followup=case["followup"],
                result=case["result"],
            )

        self.assertEqual(self.store.get_job(case["job_id"]), before_job)
        self.assertEqual(self.store.list_financial_facts("SH600001"), [])
        self.assertEqual(self.store.list_jobs(["feature_build"]), [])

    def test_malformed_statement_reconciliation_rolls_back_cas_trigger_side_effect(self) -> None:
        case = self.malformed_reconciliation_case("cas-failure")
        before_job = self.store.get_job(case["job_id"])
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                "DELETE FROM quality_issue_binding WHERE issue_id=?",
                (case["issue_id"],),
            )
            connection.execute(
                f"""CREATE TRIGGER force_reconciliation_cas_miss
                BEFORE UPDATE OF status ON job
                WHEN OLD.id='{case["job_id"]}' AND NEW.status='succeeded'
                BEGIN
                  UPDATE job SET last_error_json='{{"error_classification":"terminal_source"}}'
                  WHERE id=OLD.id;
                  SELECT RAISE(IGNORE);
                END"""
            )
            connection.commit()

        with self.assertRaisesRegex(RuntimeError, "CAS"):
            self.store.reconcile_malformed_statement(
                case["job_id"],
                expected_idempotency_key=case["idempotency_key"],
                expected_payload=case["payload"],
                expected_quality_issue_id=case["issue_id"],
                expected_quality_issue_details=case["issue_details"],
                source_snapshot_id=case["snapshot_id"],
                source_snapshot_hash=case["snapshot_hash"],
                facts=(case["fact"],),
                followup=case["followup"],
                result=case["result"],
            )

        self.assertEqual(self.store.get_job(case["job_id"]), before_job)
        self.assertEqual(self.store.list_financial_facts("SH600001"), [])
        self.assertEqual(self.store.list_jobs(["feature_build"]), [])
        with closing(sqlite3.connect(self.db_path)) as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM quality_issue_binding WHERE issue_id=?",
                    (case["issue_id"],),
                ).fetchone()[0],
                0,
            )

    def test_legacy_success_clears_recovered_failure_fields(self) -> None:
        now = datetime.now(UTC)
        old_start = (now - timedelta(minutes=2)).isoformat()
        recovery_time = (now - timedelta(minutes=1)).isoformat()
        job_id = self.store.enqueue_job("fetch", "legacy:recovered", {})
        self.store.lease_next_job(["fetch"], "worker-a", 10, old_start)
        self.assertEqual(self.store.recover_expired_leases(recovery_time), 1)
        self.store.lease_next_job(["fetch"], "worker-b", 3600)
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                "UPDATE job SET next_retry_at = ? WHERE id = ?",
                ((now + timedelta(hours=1)).isoformat(), job_id),
            )
            connection.commit()

        self.store.complete_job(job_id, {"outcome": "recovered"})

        completed = self.store.get_job(job_id)
        self.assertEqual(completed["status"], "succeeded")
        self.assertIsNone(completed["error"])
        self.assertIsNone(completed["next_retry_at"])

    def test_statement_completion_and_feature_followup_are_one_transaction(self) -> None:
        job_id = self.store.enqueue_job("deep_statement", "statement-b", {})
        self.store.lease_next_job(["deep_statement"], "worker-a", 60)
        followup = JobSpec(
            "feature_build", "feature-b", {"security_id": "SH600001"}
        )
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                """CREATE TRIGGER reject_feature BEFORE INSERT ON job
                WHEN NEW.kind='feature_build' BEGIN
                  SELECT RAISE(ABORT,'reject feature');
                END"""
            )
            connection.commit()

        with self.assertRaises(sqlite3.IntegrityError):
            self.store.complete_job_with_followups(
                job_id, "worker-a", {"snapshot": "a" * 64}, (followup,)
            )

        self.assertEqual(self.store.get_job(job_id)["status"], "running")
        self.assertEqual(self.store.list_jobs(["feature_build"]), [])

    def test_statement_failure_and_feature_followup_are_one_transaction(self) -> None:
        job_id = self.store.enqueue_job("deep_statement", "statement-failure", {})
        self.store.lease_next_job(["deep_statement"], "worker-a", 60)
        followup = JobSpec(
            "feature_build", "feature-after-failure", {"security_id": "SH600001"}
        )
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                """CREATE TRIGGER reject_failure_followup BEFORE INSERT ON job
                WHEN NEW.kind='feature_build' BEGIN
                  SELECT RAISE(ABORT,'reject failure followup');
                END"""
            )
            connection.commit()

        with self.assertRaises(sqlite3.IntegrityError):
            self.store.fail_job_with_followups(
                job_id,
                "worker-a",
                {"reason": "temporary"},
                True,
                utc_at(120),
                (followup,),
            )

        job = self.store.get_job(job_id)
        self.assertEqual(job["status"], "running")
        self.assertIsNone(job["error"])
        self.assertEqual(self.store.list_jobs(["feature_build"]), [])

    def test_repeated_identical_followups_are_idempotent_and_canonical(self) -> None:
        job_id = self.store.enqueue_job("deep_statement", "statement-idempotent", {})
        self.store.lease_next_job(["deep_statement"], "worker-a", 60)
        followup = JobSpec(
            "feature_build",
            "feature:idempotent",
            {"z": 1, "security_id": "深证", "a": [2, 1]},
        )

        self.store.complete_job_with_followups(
            job_id, "worker-a", {"outcome": "expanded"}, (followup, followup)
        )

        jobs = self.store.list_jobs(["feature_build"])
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["payload"], followup.payload)
        with closing(sqlite3.connect(self.db_path)) as connection:
            stored_json = connection.execute(
                "SELECT payload_json FROM job WHERE idempotency_key = ?",
                (followup.idempotency_key,),
            ).fetchone()[0]
        self.assertEqual(stored_json, '{"a":[2,1],"security_id":"深证","z":1}')

    def test_conflicting_followup_idempotency_key_fails_closed_and_rolls_back(self) -> None:
        self.store.enqueue_job(
            "feature_build", "feature:conflict", {"security_id": "SH600001"}
        )
        parent_id = self.store.enqueue_job("deep_statement", "statement-conflict", {})
        self.store.lease_next_job(["deep_statement"], "worker-a", 60)

        with self.assertRaisesRegex(ValueError, "idempotency"):
            self.store.complete_job_with_followups(
                parent_id,
                "worker-a",
                {"outcome": "expanded"},
                (
                    JobSpec(
                        "feature_build",
                        "feature:conflict",
                        {"security_id": "SZ000001"},
                    ),
                ),
            )

        self.assertEqual(self.store.get_job(parent_id)["status"], "running")
        self.assertEqual(
            self.store.list_jobs(["feature_build"])[0]["payload"],
            {"security_id": "SH600001"},
        )

        kind_parent_id = self.store.enqueue_job(
            "deep_statement", "statement-kind-conflict", {}
        )
        self.store.lease_next_job(["deep_statement"], "worker-a", 60)
        with self.assertRaisesRegex(ValueError, "idempotency"):
            self.store.complete_job_with_followups(
                kind_parent_id,
                "worker-a",
                {"outcome": "expanded"},
                (
                    JobSpec(
                        "deep_statement",
                        "feature:conflict",
                        {"security_id": "SH600001"},
                    ),
                ),
            )
        self.assertEqual(self.store.get_job(kind_parent_id)["status"], "running")

    def test_nonfinite_followup_payload_rolls_back_parent_transition(self) -> None:
        job_id = self.store.enqueue_job("deep_statement", "statement-nonfinite", {})
        self.store.lease_next_job(["deep_statement"], "worker-a", 60)

        with self.assertRaises(ValueError):
            self.store.complete_job_with_followups(
                job_id,
                "worker-a",
                {"outcome": "expanded"},
                (JobSpec("feature_build", "feature:nan", {"value": math.nan}),),
            )

        self.assertEqual(self.store.get_job(job_id)["status"], "running")
        self.assertEqual(self.store.list_jobs(["feature_build"]), [])

    def test_list_jobs_filters_by_parameter_and_orders_created_at_then_id(self) -> None:
        first_id = self.store.enqueue_job("deep_statement", "list:first", {"order": 1})
        ignored_id = self.store.enqueue_job("feature_build", "list:ignored", {})
        second_id = self.store.enqueue_job("deep_statement", "list:second", {"order": 2})
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                "UPDATE job SET created_at = ? WHERE id IN (?, ?)",
                (utc_at(0), first_id, ignored_id),
            )
            connection.execute(
                "UPDATE job SET created_at = ? WHERE id = ?", (utc_at(1), second_id)
            )
            connection.commit()

        jobs = self.store.list_jobs(["deep_statement", "x') OR 1=1 --"])

        self.assertEqual([job["id"] for job in jobs], [first_id, second_id])
        self.assertEqual(self.store.list_jobs([]), [])

        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                "UPDATE job SET created_at = ? WHERE id IN (?, ?)",
                (utc_at(2), first_id, second_id),
            )
            connection.commit()
        self.assertEqual(
            [job["id"] for job in self.store.list_jobs(["deep_statement"])],
            sorted((first_id, second_id)),
        )

    def test_legacy_completion_and_failure_without_worker_remain_compatible(self) -> None:
        completed_id = self.store.enqueue_job("fetch", "legacy:complete", {})
        self.store.lease_next_job(["fetch"], "worker-a", 60)
        self.store.complete_job(completed_id, {"rows": 1})

        failed_id = self.store.enqueue_job("fetch", "legacy:fail", {})
        self.store.lease_next_job(["fetch"], "worker-a", 60)
        self.store.fail_job(failed_id, {"reason": "bad input"}, False)

        self.assertEqual(self.store.get_job(completed_id)["status"], "succeeded")
        self.assertEqual(self.store.get_job(failed_id)["status"], "terminal_failed")

    def test_snapshot_deduplicates_same_content_and_versions_new_hash(self) -> None:
        first_id, first_created = self.store.record_snapshot(
            "baostock", "daily", "request-a", "hash-a", "raw/a.json", 1, utc_at(0)
        )
        duplicate_id, duplicate_created = self.store.record_snapshot(
            "baostock", "daily", "request-a", "hash-a", "raw/duplicate.json", 99, utc_at(1)
        )
        second_id, second_created = self.store.record_snapshot(
            "baostock", "daily", "request-a", "hash-b", "raw/b.json", 2, utc_at(2)
        )

        self.assertEqual((duplicate_id, duplicate_created), (first_id, False))
        self.assertTrue(first_created)
        self.assertTrue(second_created)
        self.assertNotEqual(first_id, second_id)

    def test_score_item_rejects_invalid_coverage_and_does_not_default_missing_scores(self) -> None:
        score_run_id = self.create_score_run()
        with self.assertRaises(ValueError):
            self.store.upsert_score_item(score_run_id, "000001", "partial", 1.01, "input-a", None, ["missing"])

        self.store.upsert_score_item(score_run_id, "000001", "partial", 0.5, "input-a", None, ["missing"])
        with closing(sqlite3.connect(self.db_path)) as connection:
            score_json = connection.execute("SELECT scores_json FROM score_item").fetchone()[0]
        self.assertIsNone(score_json)

    def test_run_as_of_rejects_naive_time_and_persists_utc(self) -> None:
        with self.assertRaises(ValueError):
            self.store.start_run("incremental", "2026-08-31T08:00:00", {})
        with self.assertRaises(ValueError):
            self.store.create_score_run("2026-06-30", "2026-08-31T08:00:00", "r", "u", "incremental")

        run_id = self.store.start_run("incremental", "2026-08-31T08:00:00+08:00", {})
        score_run_id = self.store.create_score_run("2026-06-30", "2026-08-31T08:00:00+08:00", "r", "u", "incremental")
        with closing(sqlite3.connect(self.db_path)) as connection:
            stored_run = connection.execute("SELECT as_of_cn FROM run WHERE id = ?", (run_id,)).fetchone()[0]
            stored_score_run = connection.execute("SELECT as_of_cn FROM score_run WHERE id = ?", (score_run_id,)).fetchone()[0]
        self.assertEqual(stored_run, "2026-08-31T00:00:00+00:00")
        self.assertEqual(stored_score_run, "2026-08-31T00:00:00+00:00")

    def test_provisional_run_cannot_directly_write_final_score_item(self) -> None:
        score_run_id = self.create_score_run()

        with self.assertRaises(ValueError):
            self.store.upsert_score_item(score_run_id, "000001", "final", 1.0, "a", {"total": 90}, [])

    def test_finalization_persists_utc_gate_and_evidence(self) -> None:
        score_run_id = self.create_score_run()
        self.store.upsert_score_item(score_run_id, "000001", "ready", 1.0, "a", {"total": 90}, [])

        self.store.finalize_score_run(
            score_run_id,
            "2026-09-01T00:00:00+08:00",
            "2026-08-31T23:59:59+08:00",
            True,
            True,
            market_evidence={"daily_snapshot": "hash-market"},
            quality_evidence={"coverage": 0.96},
        )
        with closing(sqlite3.connect(self.db_path)) as connection:
            stored = connection.execute(
                """SELECT cutoff_utc, market_ready, quality_passed, market_evidence_json, quality_evidence_json
                FROM score_run WHERE id = ?""", (score_run_id,)
            ).fetchone()
        self.assertEqual(stored[0], "2026-08-31T15:59:59+00:00")
        self.assertEqual(stored[1:3], (1, 1))
        self.assertEqual(stored[3], '{"daily_snapshot":"hash-market"}')
        self.assertEqual(stored[4], '{"coverage":0.96}')

    def test_equal_offset_time_blocks_but_later_absolute_time_finalizes(self) -> None:
        cutoff_cn = "2026-08-31T23:59:59+08:00"
        equal_absolute_time = "2026-08-31T15:59:59+00:00"
        blocked_run = self.create_score_run()
        with self.assertRaises(FinalizationBlocked):
            self.store.finalize_score_run(blocked_run, equal_absolute_time, cutoff_cn, True, True)

        final_run = self.create_score_run()
        self.store.finalize_score_run(final_run, "2026-08-31T16:00:00+00:00", cutoff_cn, True, True)
        with closing(sqlite3.connect(self.db_path)) as connection:
            self.assertEqual(connection.execute("SELECT status FROM score_run WHERE id = ?", (final_run,)).fetchone()[0], "final")

    def test_finalize_blocks_at_cutoff_including_timezone_boundary(self) -> None:
        score_run_id = self.create_score_run()

        with self.assertRaises(FinalizationBlocked):
            self.store.finalize_score_run(
                score_run_id,
                "2026-08-31T23:59:59+08:00",
                "2026-08-31T23:59:59+08:00",
                True,
                True,
            )
        with closing(sqlite3.connect(self.db_path)) as connection:
            self.assertEqual(connection.execute("SELECT status FROM score_run").fetchone()[0], "provisional")

    def test_finalize_requires_market_and_quality_gates(self) -> None:
        score_run_id = self.create_score_run()
        for market_ready, quality_passed in ((False, True), (True, False)):
            with self.assertRaises(FinalizationBlocked):
                self.store.finalize_score_run(
                    score_run_id, "2026-09-01T00:00:00+08:00", "2026-08-31T23:59:59+08:00", market_ready, quality_passed
                )

    def test_finalization_promotes_only_ready_items_and_is_idempotent(self) -> None:
        score_run_id = self.create_score_run()
        self.store.upsert_score_item(score_run_id, "000001", "ready", 1.0, "a", {"total": 90}, [])
        self.store.upsert_score_item(score_run_id, "000002", "partial", 0.5, "b", None, ["missing report"])
        self.store.upsert_score_item(score_run_id, "000003", "blocked", 0.0, "c", None, ["quality hold"])

        arguments = (score_run_id, "2026-09-01T00:00:00+08:00", "2026-08-31T23:59:59+08:00", True, True)
        self.store.finalize_score_run(*arguments)
        self.store.finalize_score_run(*arguments)
        with closing(sqlite3.connect(self.db_path)) as connection:
            states = dict(connection.execute("SELECT security_id, state FROM score_item"))
            run_status = connection.execute("SELECT status FROM score_run").fetchone()[0]
        self.assertEqual(run_status, "final")
        self.assertEqual(states, {"000001": "final", "000002": "partial", "000003": "blocked"})

    def test_final_run_cannot_be_modified_and_new_input_creates_new_run(self) -> None:
        score_run_id = self.create_score_run()
        self.store.upsert_score_item(score_run_id, "000001", "ready", 1.0, "a", {"total": 90}, [])
        self.store.finalize_score_run(
            score_run_id, "2026-09-01T00:00:00+08:00", "2026-08-31T23:59:59+08:00", True, True
        )

        with self.assertRaises(ValueError):
            self.store.upsert_score_item(score_run_id, "000001", "ready", 1.0, "changed", {"total": 91}, [])
        replacement_id = self.store.create_score_run(
            "2026-06-30", "2026-08-31T08:00:00+08:00", "rules-v2", "universe-v1", "incremental"
        )
        self.assertNotEqual(score_run_id, replacement_id)

    def test_illegal_state_is_rejected(self) -> None:
        job_id = self.store.enqueue_job("fetch", "invalid:state", {})
        with self.assertRaises(ValueError):
            self.store.finish_run(job_id, "not-a-run-status")
        score_run_id = self.create_score_run()
        with self.assertRaises(ValueError):
            self.store.upsert_score_item(score_run_id, "000001", "unknown", 0.5, "a", None, [])

    def test_progress_snapshot_has_counts_recent_run_update_and_no_payloads(self) -> None:
        run_id = self.store.start_run("incremental", "2026-08-31T08:00:00+08:00", {"secret": "payload"})
        self.store.finish_run(run_id, "succeeded")
        self.store.enqueue_job("fetch", "progress:job", {"large": "payload"})
        score_run_id = self.create_score_run()
        self.store.upsert_score_item(score_run_id, "000001", "ready", 1.0, "a", {"total": 90}, [])

        snapshot = self.store.progress_snapshot()
        self.assertGreaterEqual(snapshot["schema_version"], 1)
        self.assertEqual(snapshot["job_counts"]["pending"], 1)
        self.assertEqual(snapshot["score_item_counts"]["ready"], 1)
        self.assertEqual(snapshot["recent_run"]["id"], run_id)
        self.assertIn("updated_at", snapshot)
        self.assertNotIn("payload", repr(snapshot))

    def test_progress_updated_at_includes_finished_run_artifact_and_quality_issue(self) -> None:
        run_id = self.store.start_run("incremental", "2026-08-31T08:00:00+08:00", {})
        self.store.finish_run(run_id, "succeeded")
        marker = "2099-01-01T00:00:00+00:00"
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute("UPDATE run SET finished_at = ? WHERE id = ?", (marker, run_id))
            connection.execute(
                "INSERT INTO artifact VALUES (?, ?, ?, ?, ?, ?)",
                ("artifact-1", run_id, "raw", "hash-a", "raw/a.json", marker),
            )
            connection.execute(
                "INSERT INTO quality_issue VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("issue-1", run_id, None, "warning", "coverage", "{}", marker),
            )
            connection.commit()

        self.assertEqual(self.store.progress_snapshot()["updated_at"], marker)

    def test_formal_universe_snapshot_persists_complete_canonical_graph_and_initial_statuses(self) -> None:
        store, frozen, _ = self.task_backed_frozen_universe(label="canonical")

        snapshot_id = store.put_formal_universe_snapshot(frozen)

        header = store.get_formal_universe_snapshot_by_input_hash(
            frozen.frozen_input_hash
        )
        self.assertEqual(header["id"], snapshot_id)
        self.assertEqual(
            {
                key: header[key]
                for key in (
                    "as_of_utc",
                    "registry_manifest_hash",
                    "universe_hash",
                    "source_audit_hash",
                    "frozen_input_hash",
                )
            },
            {
                "as_of_utc": frozen.as_of_utc,
                "registry_manifest_hash": frozen.registry_manifest_hash,
                "universe_hash": frozen.universe_hash,
                "source_audit_hash": frozen.source_audit_hash,
                "frozen_input_hash": frozen.frozen_input_hash,
            },
        )
        sources = store.list_formal_universe_sources(snapshot_id)
        self.assertEqual([source["exchange"] for source in sources], ["BJ", "SH", "SZ"])
        self.assertEqual(
            sources[0]["extraction"]["members"][0]["raw_row"]["metadata"]["aliases"],
            ["BJ-alpha", {"language": "zh"}],
        )
        self.assertEqual(
            sources[0]["extraction"]["audit"]["excluded_by_security_type"],
            [["bond", 1]],
        )
        with closing(sqlite3.connect(self.db_path)) as connection:
            counts = {
                table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in (
                    "formal_universe_snapshot",
                    "formal_universe_source",
                    "formal_universe_member",
                    "formal_universe_status",
                )
            }
            members = connection.execute(
                "SELECT security_id,raw_json FROM formal_universe_member ORDER BY security_id"
            ).fetchall()
            statuses = connection.execute(
                """SELECT security_id,status,reasons_json,veto_flags_json,evidence_hash
                FROM formal_universe_status ORDER BY security_id"""
            ).fetchall()
        self.assertEqual(counts, {
            "formal_universe_snapshot": 1,
            "formal_universe_source": 3,
            "formal_universe_member": 3,
            "formal_universe_status": 3,
        })
        self.assertEqual([row[0] for row in members], ["BJ430001", "SH600000", "SZ000001"])
        self.assertIn('"aliases":["BJ-alpha",{"language":"zh"}]', members[0][1])
        for security_id, status, reasons_json, veto_flags_json, evidence_hash in statuses:
            self.assertEqual(status, "pending_evidence")
            self.assertEqual(reasons_json, '["formal_collection_pending"]')
            self.assertEqual(veto_flags_json, "[]")
            expected = hashlib.sha256(json.dumps(
                {
                    "frozen_input_hash": frozen.frozen_input_hash,
                    "reasons": ["formal_collection_pending"],
                    "security_id": security_id,
                    "status": "pending_evidence",
                    "veto_flags": [],
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")).hexdigest()
            self.assertEqual(evidence_hash, expected)

    def test_formal_universe_snapshot_replay_is_exact_and_never_resets_statuses(self) -> None:
        store, frozen, _ = self.task_backed_frozen_universe(label="replay")
        snapshot_id = store.put_formal_universe_snapshot(frozen)
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                """UPDATE formal_universe_status
                SET status='pool_vetoed', reasons_json='[\"verified-risk\"]',
                    veto_flags_json='[\"ST\"]', evidence_hash=?
                WHERE snapshot_id=? AND security_id='BJ430001'""",
                ("a" * 64, snapshot_id),
            )
            connection.commit()

        self.assertEqual(store.put_formal_universe_snapshot(frozen), snapshot_id)

        with closing(sqlite3.connect(self.db_path)) as connection:
            row = connection.execute(
                """SELECT status,reasons_json,veto_flags_json,evidence_hash
                FROM formal_universe_status
                WHERE snapshot_id=? AND security_id='BJ430001'""",
                (snapshot_id,),
            ).fetchone()
        self.assertEqual(row, ("pool_vetoed", '["verified-risk"]', '["ST"]', "a" * 64))

    def test_formal_universe_initial_status_recomputes_evidence_hash_on_read_and_replay(self) -> None:
        store, frozen, _ = self.task_backed_frozen_universe(
            label="initial-status-evidence"
        )
        snapshot_id = store.put_formal_universe_snapshot(frozen)
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                """UPDATE formal_universe_status SET evidence_hash=?
                WHERE snapshot_id=? AND security_id='BJ430001'""",
                ("a" * 64, snapshot_id),
            )
            connection.commit()

        with self.assertRaises(ValueError):
            store.get_formal_universe_snapshot_by_input_hash(
                frozen.frozen_input_hash
            )
        with self.assertRaisesRegex(ValueError, "frozen_input_hash_conflict"):
            store.put_formal_universe_snapshot(frozen)

    def test_formal_universe_snapshot_requires_exact_typed_recomputed_input(self) -> None:
        store, frozen, _ = self.task_backed_frozen_universe(label="typed")
        with self.assertRaises(ValueError):
            store.put_formal_universe_snapshot({"frozen_input_hash": frozen.frozen_input_hash})

        mutations = (
            ("as_of_utc", "2026-08-31T14:59:59+08:00"),
            ("registry_manifest_hash", ""),
            ("members", tuple(reversed(frozen.members))),
            ("sources", tuple(reversed(frozen.sources))),
            ("universe_hash", "0" * 64),
            ("source_audit_hash", "1" * 64),
            ("frozen_input_hash", "2" * 64),
        )
        for field, value in mutations:
            with self.subTest(field=field):
                forged = copy.copy(frozen)
                object.__setattr__(forged, field, value)
                with self.assertRaises(ValueError):
                    store.put_formal_universe_snapshot(forged)

    def test_formal_universe_snapshot_rejects_missing_duplicate_cross_exchange_and_untrusted_source_graphs(self) -> None:
        store, frozen, task_ids = self.task_backed_frozen_universe(label="source-shape")
        malformed_sources = (
            frozen.sources[:2],
            (frozen.sources[0], frozen.sources[0], frozen.sources[2]),
            (replace(frozen.sources[0], exchange="SH"), *frozen.sources[1:]),
            (
                replace(
                    frozen.sources[0],
                    snapshot=replace(frozen.sources[0].snapshot, producing_task_id=None),
                ),
                *frozen.sources[1:],
            ),
        )
        for sources in malformed_sources:
            with self.subTest(sources=sources):
                forged = copy.copy(frozen)
                object.__setattr__(forged, "sources", tuple(sources))
                with self.assertRaises(ValueError):
                    store.put_formal_universe_snapshot(forged)

        bootstrap_raw_store = FormalSnapshotStore(
            Path(self.tempdir.name) / "formal-universe-raw-source-shape"
        )
        bootstrap_rows = ({
            "listing_status": "listed",
            "metadata": {"aliases": ["BJ-bootstrap"]},
            "security_id": "BJ430001",
            "security_type": "ordinary_a",
        },)
        bootstrap_fetch = OfficialFetch(
            request=OfficialRequest(
                "bse", "official_security_listing", None, "2026-08-31", "BJ"
            ),
            raw_bytes=b"bootstrap listing",
            original_url="https://www.bse.cn/listing",
            published_at_utc="2026-08-31T06:00:00+00:00",
            published_precision="timestamp",
            source_updated_at_utc=None,
            captured_at_utc="2026-08-31T06:30:00+00:00",
            effective_at_utc="2026-08-31T06:00:00+00:00",
            effective_time_evidence_hash=None,
            refresh_generation="bootstrap-universe-v1",
            parser_id="bse-listing-json",
            parser_version="bse-listing-json-v1",
            mapping_version="bse-listing-map-v1",
            declared_security_id=None,
            declared_period="2026-08-31",
        )
        bootstrap_verification = verify_official_fetch(
            bootstrap_fetch, SourcePolicy.bse()
        )
        bootstrap_stored = bootstrap_raw_store.write_verified(
            bootstrap_fetch, bootstrap_verification, producing_task_id=None
        )
        bootstrap_ref = store.put_formal_snapshot(
            bootstrap_fetch, bootstrap_stored, bootstrap_verification
        )
        bootstrap_documents = (
            FormalUniverseSourceDocument(
                "BJ",
                bootstrap_ref,
                bootstrap_ref.parser_id,
                bootstrap_ref.parser_version,
                bootstrap_rows,
            ),
            *(
                FormalUniverseSourceDocument(
                    source.exchange,
                    source.snapshot,
                    source.snapshot.parser_id,
                    source.snapshot.parser_version,
                    tuple(member.raw_row for member in source.extraction.members),
                )
                for source in frozen.sources[1:]
            ),
        )
        bootstrap_frozen = FormalUniverseIngestor().build(
            frozen.as_of_utc,
            frozen.registry_manifest_hash,
            bootstrap_documents,
        )
        with self.assertRaisesRegex(ValueError, "bootstrap"):
            store.put_formal_universe_snapshot(bootstrap_frozen)

        self.assertEqual(store.get_formal_task(task_ids["BJ"])["status"], "verified")

    def test_formal_universe_snapshot_revalidates_task_receipt_and_result_lineage(self) -> None:
        cases = (
            "missing-receipt",
            "duplicate-producer",
            "wrong-kind",
            "wrong-status",
            "wrong-generation",
            "wrong-manifest",
            "wrong-result",
            "cross-exchange-payload",
        )
        for index, case in enumerate(cases):
            with self.subTest(case=case):
                path = Path(self.tempdir.name) / f"universe-lineage-{index}.sqlite3"
                store, frozen, task_ids = self.task_backed_frozen_universe(
                    label=f"lineage-{index}", db_path=path
                )
                task_id = task_ids["BJ"]
                with closing(sqlite3.connect(path)) as connection:
                    if case == "missing-receipt":
                        connection.execute(
                            "DELETE FROM formal_task_snapshot_receipt WHERE task_id=?",
                            (task_id,),
                        )
                    elif case == "duplicate-producer":
                        row = connection.execute(
                            "SELECT * FROM formal_source_snapshot WHERE producing_task_id=?",
                            (task_id,),
                        ).fetchone()
                        values = list(row)
                        values[0] = str(uuid.uuid4())
                        values[6] = "0" * 64
                        values[19] = "duplicate-generation"
                        connection.execute(
                            "INSERT INTO formal_source_snapshot VALUES (" + ",".join("?" for _ in values) + ")",
                            values,
                        )
                    elif case == "wrong-kind":
                        connection.execute(
                            "UPDATE formal_collection_task SET kind='formal_statement' WHERE id=?",
                            (task_id,),
                        )
                    elif case == "wrong-status":
                        connection.execute(
                            "UPDATE formal_collection_task SET status='terminal_failed' WHERE id=?",
                            (task_id,),
                        )
                    elif case == "wrong-generation":
                        connection.execute(
                            "UPDATE formal_collection_task SET refresh_generation='wrong' WHERE id=?",
                            (task_id,),
                        )
                    elif case == "wrong-manifest":
                        connection.execute(
                            "UPDATE formal_task_snapshot_receipt SET manifest_sha256=? WHERE task_id=?",
                            ("0" * 64, task_id),
                        )
                    elif case == "wrong-result":
                        result = json.loads(connection.execute(
                            "SELECT result_json FROM formal_collection_task WHERE id=?",
                            (task_id,),
                        ).fetchone()[0])
                        result["parsed_rows_hash"] = "0" * 64
                        connection.execute(
                            "UPDATE formal_collection_task SET result_json=? WHERE id=?",
                            (json.dumps(result, sort_keys=True, separators=(",", ":")), task_id),
                        )
                    else:
                        payload = json.loads(connection.execute(
                            "SELECT payload_json FROM formal_collection_task WHERE id=?",
                            (task_id,),
                        ).fetchone()[0])
                        payload["exchange"] = "SH"
                        payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
                        connection.execute(
                            """UPDATE formal_collection_task
                            SET payload_json=?, payload_sha256=? WHERE id=?""",
                            (
                                payload_json,
                                hashlib.sha256(payload_json.encode("utf-8")).hexdigest(),
                                task_id,
                            ),
                        )
                    connection.commit()
                with self.assertRaises(ValueError):
                    store.put_formal_universe_snapshot(frozen)
                with closing(sqlite3.connect(path)) as connection:
                    self.assertEqual(
                        connection.execute("SELECT COUNT(*) FROM formal_universe_snapshot").fetchone()[0],
                        0,
                    )

    def test_formal_universe_snapshot_rejects_impossible_verified_source_task_state(self) -> None:
        cases = (
            ("error_json", '{"code":"ghost-error"}'),
            ("lease_worker", "ghost-worker"),
            ("lease_expires_at", "2099-01-01T00:00:00+00:00"),
            ("next_retry_at", "2099-01-01T00:00:00+00:00"),
            ("created_at", "2099-01-01T00:00:00+00:00"),
        )
        for index, (field, value) in enumerate(cases):
            with self.subTest(field=field):
                path = Path(self.tempdir.name) / f"universe-task-state-{index}.sqlite3"
                store, frozen, task_ids = self.task_backed_frozen_universe(
                    label=f"task-state-{index}", db_path=path
                )
                with closing(sqlite3.connect(path)) as connection:
                    connection.execute(
                        f"UPDATE formal_collection_task SET {field}=? WHERE id=?",
                        (value, task_ids["BJ"]),
                    )
                    connection.commit()

                with self.assertRaises(ValueError):
                    store.put_formal_universe_snapshot(frozen)
                with closing(sqlite3.connect(path)) as connection:
                    self.assertEqual(
                        connection.execute(
                            "SELECT COUNT(*) FROM formal_universe_snapshot"
                        ).fetchone()[0],
                        0,
                    )

    def test_formal_universe_getter_and_replay_reject_corrupt_verified_source_task_state(self) -> None:
        cases = (
            ("error_json", '{"code":"ghost-error"}'),
            ("lease_worker", "ghost-worker"),
            ("lease_expires_at", "2099-01-01T00:00:00+00:00"),
            ("next_retry_at", "2099-01-01T00:00:00+00:00"),
        )
        for index, (field, value) in enumerate(cases):
            with self.subTest(field=field):
                path = Path(self.tempdir.name) / f"universe-stored-task-state-{index}.sqlite3"
                store, frozen, task_ids = self.task_backed_frozen_universe(
                    label=f"stored-task-state-{index}", db_path=path
                )
                store.put_formal_universe_snapshot(frozen)
                with closing(sqlite3.connect(path)) as connection:
                    connection.execute(
                        f"UPDATE formal_collection_task SET {field}=? WHERE id=?",
                        (value, task_ids["BJ"]),
                    )
                    connection.commit()

                with self.assertRaises(ValueError):
                    store.get_formal_universe_snapshot_by_input_hash(
                        frozen.frozen_input_hash
                    )
                with self.assertRaises(ValueError):
                    store.put_formal_universe_snapshot(frozen)

    def test_formal_universe_snapshot_rolls_back_late_child_failure(self) -> None:
        store, frozen, _ = self.task_backed_frozen_universe(label="late-rollback")
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                """CREATE TRIGGER fail_universe_status
                BEFORE INSERT ON formal_universe_status
                BEGIN SELECT RAISE(ABORT, 'forced status failure'); END"""
            )
            connection.commit()

        with self.assertRaises(sqlite3.IntegrityError):
            store.put_formal_universe_snapshot(frozen)

        with closing(sqlite3.connect(self.db_path)) as connection:
            self.assertEqual(
                {
                    table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    for table in (
                        "formal_universe_snapshot",
                        "formal_universe_source",
                        "formal_universe_member",
                        "formal_universe_status",
                    )
                },
                {
                    "formal_universe_snapshot": 0,
                    "formal_universe_source": 0,
                    "formal_universe_member": 0,
                    "formal_universe_status": 0,
                },
            )

    def test_formal_universe_getters_and_replay_fail_closed_for_corrupt_existing_graph(self) -> None:
        cases = (
            "header-hash",
            "source-json",
            "missing-member",
            "missing-status",
            "bad-status-hash",
        )
        for index, case in enumerate(cases):
            with self.subTest(case=case):
                path = Path(self.tempdir.name) / f"universe-corrupt-{index}.sqlite3"
                store, frozen, _ = self.task_backed_frozen_universe(
                    label=f"corrupt-{index}", db_path=path
                )
                snapshot_id = store.put_formal_universe_snapshot(frozen)
                with closing(sqlite3.connect(path)) as connection:
                    connection.execute("PRAGMA foreign_keys=OFF")
                    if case == "header-hash":
                        connection.execute(
                            "UPDATE formal_universe_snapshot SET universe_hash=? WHERE id=?",
                            ("0" * 64, snapshot_id),
                        )
                    elif case == "source-json":
                        connection.execute(
                            """UPDATE formal_universe_source SET extraction_json='{}'
                            WHERE universe_snapshot_id=? AND exchange='BJ'""",
                            (snapshot_id,),
                        )
                    elif case == "missing-member":
                        connection.execute(
                            "DELETE FROM formal_universe_status WHERE snapshot_id=? AND security_id='BJ430001'",
                            (snapshot_id,),
                        )
                        connection.execute(
                            "DELETE FROM formal_universe_member WHERE snapshot_id=? AND security_id='BJ430001'",
                            (snapshot_id,),
                        )
                    elif case == "missing-status":
                        connection.execute(
                            "DELETE FROM formal_universe_status WHERE snapshot_id=? AND security_id='BJ430001'",
                            (snapshot_id,),
                        )
                    else:
                        connection.execute(
                            """UPDATE formal_universe_status SET evidence_hash='not-a-hash'
                            WHERE snapshot_id=? AND security_id='BJ430001'""",
                            (snapshot_id,),
                        )
                    connection.commit()

                with self.assertRaises(ValueError):
                    store.get_formal_universe_snapshot_by_input_hash(
                        frozen.frozen_input_hash
                    )
                with self.assertRaisesRegex(ValueError, "frozen_input_hash_conflict"):
                    store.put_formal_universe_snapshot(frozen)

    def test_formal_universe_persistence_does_not_read_or_modify_legacy_snapshots(self) -> None:
        created = self.store.record_snapshot(
            "akshare",
            "stock_list",
            "legacy-request",
            "legacy-payload",
            "data/raw/legacy.json",
            1,
            utc_at(0),
        )
        store, frozen, _ = self.task_backed_frozen_universe(label="legacy-isolation")
        store.put_formal_universe_snapshot(frozen)
        with closing(sqlite3.connect(self.db_path)) as connection:
            legacy = connection.execute(
                "SELECT source,dataset,request_fingerprint,payload_hash FROM source_snapshot"
            ).fetchall()
        self.assertEqual(created[1], True)
        self.assertEqual(
            legacy,
            [("akshare", "stock_list", "legacy-request", "legacy-payload")],
        )


if __name__ == "__main__":
    unittest.main()
