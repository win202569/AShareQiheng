from __future__ import annotations

from contextlib import closing
from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import sqlite3
import tempfile
from types import MappingProxyType
import unittest

from ashare_pipeline.deep_worker import (
    STATEMENT_DATASETS,
    CandidateContext,
    build_candidate_context,
    deep_statement_key,
    expand_deep_parents,
    feature_build_key,
    load_candidate_context,
    statement_job_specs,
)
from ashare_pipeline.feature_contract import canonical_json_bytes, canonical_sha256
from ashare_pipeline.financial_schema import FINANCIAL_REQUEST_VERSION
from ashare_pipeline.state_store import StateStore


REPORT_PERIOD = "2026-06-30"
REFRESH_DATE = "2026-08-29"


def performance_row(
    security_id: str,
    *,
    industry: str = "包装印刷",
    announcement_date: str = "2026-08-20",
) -> dict[str, object]:
    return {
        "security_id": security_id,
        "industry": industry,
        "announcement_date": announcement_date,
        "revenue": 100.0,
    }


def candidate_documents(
    candidates: dict[str, str],
    *,
    prefilter_input_hashes: dict[str, object] | None = None,
    performance_rows: list[dict[str, object]] | None = None,
) -> tuple[dict[str, object], dict[str, object]]:
    rows = performance_rows or [
        performance_row(security_id, industry=industry)
        for security_id, industry in sorted(candidates.items())
    ]
    prefilter_records = [
        {"security_id": security_id, "industry": industry}
        for security_id, industry in sorted(candidates.items())
    ]
    prefilter = {
        "schema_version": 2,
        "input_hashes": prefilter_input_hashes
        or {"performance": "a" * 64, "prefilter_rules": "b" * 64},
        "records": prefilter_records,
        "records_hash": canonical_sha256(prefilter_records),
    }
    performance = {
        "schema_version": 2,
        "input_hashes": {"fixture": "c" * 64},
        "records": rows,
        "records_hash": canonical_sha256(rows),
    }
    return prefilter, performance


def candidate_context(members: set[str]) -> CandidateContext:
    ordered = sorted(members)
    return CandidateContext(
        candidate_set_hash="c" * 64,
        members=frozenset(ordered),
        performance_input_hashes={item: "d" * 64 for item in ordered},
        industries={item: "包装印刷" for item in ordered},
        reported_target_period={item: True for item in ordered},
    )


class DeepWorkerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.project_root = Path(self.tempdir.name)
        self.data_root = self.project_root / "data"
        self.store = StateStore(self.data_root / "state.sqlite3")
        self.store.initialize()

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_old_parent_expands_to_three_dated_unique_statement_jobs(self) -> None:
        context = candidate_context({"SH600001"})
        parent_id = self.store.enqueue_job(
            "deep_financial",
            "legacy:SH600001",
            {
                "security_id": "SH600001",
                "report_period": REPORT_PERIOD,
                "input_hash": "a" * 64,
            },
        )

        summary = expand_deep_parents(
            self.store,
            context,
            as_of_cn_date=REFRESH_DATE,
            worker_id="planner",
        )

        self.assertEqual(summary, {"expanded": 1, "superseded": 0, "children": 3})
        self.assertEqual(
            self.store.get_job(parent_id)["result"],
            {"outcome": "expanded", "child_count": 3},
        )
        children = self.store.list_jobs(["deep_statement"])
        self.assertEqual(
            {job["idempotency_key"] for job in children},
            {
                "deep_statement:v1:SH600001:balance_sheet:2026-06-30:2026-08-29",
                "deep_statement:v1:SH600001:profit_sheet:2026-06-30:2026-08-29",
                "deep_statement:v1:SH600001:cash_flow_sheet:2026-06-30:2026-08-29",
            },
        )
        self.assertEqual(
            {job["payload"]["candidate_set_hash"] for job in children},
            {context.candidate_set_hash},
        )

    def test_reexpansion_is_idempotent_and_120_parents_make_360_children(self) -> None:
        context = candidate_context({f"SH{index:06d}" for index in range(1, 121)})
        for security_id in context.members:
            self.store.enqueue_job(
                "deep_financial",
                f"legacy:{security_id}",
                {"security_id": security_id, "report_period": REPORT_PERIOD},
            )

        first = expand_deep_parents(
            self.store,
            context,
            as_of_cn_date=REFRESH_DATE,
            worker_id="planner",
        )
        second = expand_deep_parents(
            self.store,
            context,
            as_of_cn_date=REFRESH_DATE,
            worker_id="planner",
        )

        self.assertEqual(first, {"expanded": 120, "superseded": 0, "children": 360})
        self.assertEqual(second, {"expanded": 0, "superseded": 0, "children": 0})
        self.assertEqual(len(self.store.list_jobs(["deep_statement"])), 360)

    def test_removed_parent_is_superseded_without_children(self) -> None:
        parent_id = self.store.enqueue_job(
            "deep_financial",
            "legacy:SH600999",
            {"security_id": "SH600999", "report_period": REPORT_PERIOD},
        )

        summary = expand_deep_parents(
            self.store,
            candidate_context({"SH600001"}),
            as_of_cn_date=REFRESH_DATE,
            worker_id="planner",
        )

        self.assertEqual(summary, {"expanded": 0, "superseded": 1, "children": 0})
        self.assertEqual(
            self.store.get_job(parent_id)["result"],
            {"outcome": "superseded", "child_count": 0},
        )
        self.assertEqual(self.store.list_jobs(["deep_statement"]), [])

    def test_child_insert_failure_rolls_back_all_children_and_parent_completion(self) -> None:
        parent_id = self.store.enqueue_job(
            "deep_financial",
            "legacy:rollback",
            {"security_id": "SH600001", "report_period": REPORT_PERIOD},
        )
        with closing(sqlite3.connect(self.store.db_path)) as connection:
            connection.execute(
                """CREATE TRIGGER reject_profit_child BEFORE INSERT ON job
                WHEN NEW.kind='deep_statement'
                 AND json_extract(NEW.payload_json, '$.dataset')='profit_sheet'
                BEGIN SELECT RAISE(ABORT, 'reject profit child'); END"""
            )
            connection.commit()

        with self.assertRaises(sqlite3.IntegrityError):
            expand_deep_parents(
                self.store,
                candidate_context({"SH600001"}),
                as_of_cn_date=REFRESH_DATE,
                worker_id="planner",
            )

        self.assertEqual(self.store.get_job(parent_id)["status"], "running")
        self.assertEqual(self.store.list_jobs(["deep_statement"]), [])

    def test_candidate_hash_is_order_independent_and_has_exact_dependencies(self) -> None:
        inputs = {"rules": "1" * 64, "performance": "2" * 64}
        rows = [
            performance_row("SZ000002", industry="银行", announcement_date="2026-08-22"),
            performance_row("SH600001", announcement_date="2026-08-21"),
            performance_row("SH600999", announcement_date="2026-08-23"),
        ]
        prefilter, performance = candidate_documents(
            {"SZ000002": "银行", "SH600001": "包装印刷"},
            prefilter_input_hashes=inputs,
            performance_rows=rows,
        )

        first = build_candidate_context(prefilter, performance)
        shuffled_prefilter = dict(prefilter)
        shuffled_prefilter["input_hashes"] = dict(reversed(tuple(inputs.items())))
        shuffled_prefilter["records"] = list(reversed(prefilter["records"]))
        shuffled_prefilter["records_hash"] = canonical_sha256(
            shuffled_prefilter["records"]
        )
        shuffled_performance = dict(performance)
        shuffled_performance["records"] = list(reversed(rows))
        shuffled_performance["records_hash"] = canonical_sha256(
            shuffled_performance["records"]
        )
        second = build_candidate_context(shuffled_prefilter, shuffled_performance)

        expected_pairs = [
            ["SH600001", canonical_sha256(rows[1])],
            ["SZ000002", canonical_sha256(rows[0])],
        ]
        expected = canonical_sha256(
            {
                "prefilter_input_hashes": inputs,
                "performance_input_hashes": expected_pairs,
            }
        )
        self.assertEqual(first.candidate_set_hash, expected)
        self.assertEqual(second.candidate_set_hash, expected)
        self.assertEqual(
            dict(first.performance_input_hashes), dict(expected_pairs)
        )

    def test_candidate_hash_changes_with_prefilter_or_selected_performance_input(self) -> None:
        prefilter, performance = candidate_documents({"SH600001": "包装印刷"})
        original = build_candidate_context(prefilter, performance).candidate_set_hash

        changed_prefilter = json.loads(json.dumps(prefilter))
        changed_prefilter["input_hashes"]["performance"] = "9" * 64
        changed_row = json.loads(json.dumps(performance))
        changed_row["records"][0]["announcement_date"] = "2026-08-21"
        changed_row["records_hash"] = canonical_sha256(changed_row["records"])

        self.assertNotEqual(
            build_candidate_context(changed_prefilter, performance).candidate_set_hash,
            original,
        )
        self.assertNotEqual(
            build_candidate_context(prefilter, changed_row).candidate_set_hash,
            original,
        )

    def test_selected_candidate_without_performance_record_fails_closed(self) -> None:
        prefilter, performance = candidate_documents(
            {"SH600001": "包装印刷"},
            performance_rows=[performance_row("SH600002")],
        )

        with self.assertRaisesRegex(ValueError, "performance record"):
            build_candidate_context(prefilter, performance)

    def test_context_defensively_copies_and_freezes_all_member_mappings(self) -> None:
        performance_hashes = {"SH600001": "a" * 64}
        industries = {"SH600001": "包装印刷"}
        reported = {"SH600001": True}
        context = CandidateContext(
            candidate_set_hash="b" * 64,
            members=frozenset({"SH600001"}),
            performance_input_hashes=performance_hashes,
            industries=industries,
            reported_target_period=reported,
        )

        performance_hashes["SH600001"] = "c" * 64
        industries["SH600001"] = "银行"
        reported["SH600001"] = False
        self.assertEqual(context.performance_input_hashes["SH600001"], "a" * 64)
        self.assertEqual(context.industries["SH600001"], "包装印刷")
        self.assertTrue(context.reported_target_period["SH600001"])
        for mapping in (
            context.performance_input_hashes,
            context.industries,
            context.reported_target_period,
        ):
            self.assertIsInstance(mapping, MappingProxyType)
            with self.assertRaises(TypeError):
                mapping["SH600001"] = "changed"
        with self.assertRaises(FrozenInstanceError):
            context.candidate_set_hash = "d" * 64

    def test_load_candidate_context_reads_curated_documents_without_mutating_them(self) -> None:
        prefilter, performance = candidate_documents({"SH600001": "包装印刷"})
        curated = self.data_root / "curated"
        curated.mkdir(parents=True)
        prefilter_bytes = canonical_json_bytes(prefilter)
        performance_bytes = canonical_json_bytes(performance)
        (curated / "prefilter.json").write_bytes(prefilter_bytes)
        (curated / "performance.json").write_bytes(performance_bytes)

        loaded = load_candidate_context(self.data_root)

        self.assertEqual(loaded.members, frozenset({"SH600001"}))
        self.assertTrue(loaded.reported_target_period["SH600001"])
        self.assertEqual((curated / "prefilter.json").read_bytes(), prefilter_bytes)
        self.assertEqual((curated / "performance.json").read_bytes(), performance_bytes)

    def test_statement_specs_have_fixed_order_and_first_enqueue_audit_payload(self) -> None:
        context = candidate_context({"SH600001"})

        specs = statement_job_specs(
            context,
            security_id="SH600001",
            report_period=REPORT_PERIOD,
            as_of_cn_date=REFRESH_DATE,
        )

        self.assertEqual(STATEMENT_DATASETS, ("balance_sheet", "profit_sheet", "cash_flow_sheet"))
        self.assertEqual(tuple(spec.payload["dataset"] for spec in specs), STATEMENT_DATASETS)
        for spec in specs:
            self.assertEqual(spec.kind, "deep_statement")
            self.assertEqual(spec.payload, {
                "security_id": "SH600001",
                "dataset": spec.payload["dataset"],
                "report_period": REPORT_PERIOD,
                "candidate_set_hash": context.candidate_set_hash,
                "performance_input_hash": context.performance_input_hashes["SH600001"],
                "request_version": FINANCIAL_REQUEST_VERSION,
                "refresh_date": REFRESH_DATE,
            })

    def test_same_date_candidate_change_reuses_first_enqueued_child_payload(self) -> None:
        old_context = candidate_context({"SH600001"})
        for spec in statement_job_specs(
            old_context,
            security_id="SH600001",
            report_period=REPORT_PERIOD,
            as_of_cn_date=REFRESH_DATE,
        ):
            self.store.enqueue_job(spec.kind, spec.idempotency_key, spec.payload)
        changed_context = CandidateContext(
            candidate_set_hash="e" * 64,
            members=frozenset({"SH600001"}),
            performance_input_hashes={"SH600001": "f" * 64},
            industries={"SH600001": "银行"},
            reported_target_period={"SH600001": True},
        )
        parent_id = self.store.enqueue_job(
            "deep_financial",
            "legacy:changed-context",
            {"security_id": "SH600001", "report_period": REPORT_PERIOD},
        )

        summary = expand_deep_parents(
            self.store,
            changed_context,
            as_of_cn_date=REFRESH_DATE,
            worker_id="planner",
        )

        self.assertEqual(summary["expanded"], 1)
        self.assertEqual(self.store.get_job(parent_id)["status"], "succeeded")
        self.assertEqual(
            {job["payload"]["candidate_set_hash"] for job in self.store.list_jobs(["deep_statement"])},
            {old_context.candidate_set_hash},
        )

    def test_keys_and_documents_reject_malformed_security_dates_and_digests(self) -> None:
        for call in (
            lambda: deep_statement_key("600001", "balance_sheet", REPORT_PERIOD, REFRESH_DATE),
            lambda: deep_statement_key("SH600001", "unknown", REPORT_PERIOD, REFRESH_DATE),
            lambda: deep_statement_key("SH600001", "balance_sheet", "2026-02-30", REFRESH_DATE),
            lambda: deep_statement_key("SH600001", "balance_sheet", REPORT_PERIOD, "20260829"),
            lambda: feature_build_key("SH600001", REPORT_PERIOD, "not-a-digest"),
        ):
            with self.subTest(call=call), self.assertRaises(ValueError):
                call()

        with self.assertRaises(ValueError):
            CandidateContext(
                candidate_set_hash="bad",
                members=frozenset({"SH600001"}),
                performance_input_hashes={"SH600001": "a" * 64},
                industries={"SH600001": "包装印刷"},
                reported_target_period={"SH600001": True},
            )

    def test_prefilter_document_requires_records_hash(self) -> None:
        prefilter, performance = candidate_documents({"SH600001": "包装印刷"})
        del prefilter["records_hash"]

        with self.assertRaisesRegex(ValueError, "prefilter records_hash"):
            build_candidate_context(prefilter, performance)

    def test_prefilter_document_rejects_malformed_records_hash(self) -> None:
        prefilter, performance = candidate_documents({"SH600001": "包装印刷"})
        prefilter["records_hash"] = "not-a-digest"

        with self.assertRaisesRegex(ValueError, "prefilter records_hash"):
            build_candidate_context(prefilter, performance)

    def test_prefilter_document_rejects_mismatched_records_hash(self) -> None:
        prefilter, performance = candidate_documents({"SH600001": "包装印刷"})
        prefilter["records_hash"] = "0" * 64

        with self.assertRaisesRegex(ValueError, "records_hash"):
            build_candidate_context(prefilter, performance)

    def test_performance_document_requires_records_hash(self) -> None:
        prefilter, performance = candidate_documents({"SH600001": "包装印刷"})
        del performance["records_hash"]

        with self.assertRaisesRegex(ValueError, "performance records_hash"):
            build_candidate_context(prefilter, performance)

    def test_performance_document_rejects_malformed_records_hash(self) -> None:
        prefilter, performance = candidate_documents({"SH600001": "包装印刷"})
        performance["records_hash"] = "not-a-digest"

        with self.assertRaisesRegex(ValueError, "performance records_hash"):
            build_candidate_context(prefilter, performance)

    def test_performance_document_rejects_mismatched_records_hash(self) -> None:
        prefilter, performance = candidate_documents({"SH600001": "包装印刷"})
        performance["records_hash"] = "0" * 64

        with self.assertRaisesRegex(ValueError, "performance records_hash"):
            build_candidate_context(prefilter, performance)

    def _assert_existing_statement_mismatch_fails_closed(
        self,
        *,
        payload_field: str | None = None,
        replacement: object | None = None,
        existing_kind: str = "deep_statement",
    ) -> None:
        context = candidate_context({"SH600001"})
        requested = statement_job_specs(
            context,
            security_id="SH600001",
            report_period=REPORT_PERIOD,
            as_of_cn_date=REFRESH_DATE,
        )[0]
        existing_payload = requested.payload
        if payload_field is not None:
            existing_payload[payload_field] = replacement
        self.store.enqueue_job(
            existing_kind,
            requested.idempotency_key,
            existing_payload,
        )
        parent_id = self.store.enqueue_job(
            "deep_financial",
            f"legacy:mismatch:{payload_field or 'kind'}",
            {"security_id": "SH600001", "report_period": REPORT_PERIOD},
        )

        with self.assertRaisesRegex(ValueError, "existing deep statement"):
            expand_deep_parents(
                self.store,
                context,
                as_of_cn_date=REFRESH_DATE,
                worker_id="planner",
            )

        self.assertEqual(self.store.get_job(parent_id)["status"], "running")
        self.assertEqual(
            len(self.store.list_jobs(["deep_statement"])),
            0 if existing_kind != "deep_statement" else 1,
        )

    def test_existing_statement_security_must_match_requested_key(self) -> None:
        self._assert_existing_statement_mismatch_fails_closed(
            payload_field="security_id", replacement="SH600002"
        )

    def test_existing_statement_dataset_must_match_requested_key(self) -> None:
        self._assert_existing_statement_mismatch_fails_closed(
            payload_field="dataset", replacement="profit_sheet"
        )

    def test_existing_statement_period_must_match_requested_key(self) -> None:
        self._assert_existing_statement_mismatch_fails_closed(
            payload_field="report_period", replacement="2025-12-31"
        )

    def test_existing_statement_refresh_date_must_match_requested_key(self) -> None:
        self._assert_existing_statement_mismatch_fails_closed(
            payload_field="refresh_date", replacement="2026-08-28"
        )

    def test_existing_statement_kind_must_match_requested_spec(self) -> None:
        self._assert_existing_statement_mismatch_fails_closed(
            existing_kind="feature_build"
        )


if __name__ == "__main__":
    unittest.main()
