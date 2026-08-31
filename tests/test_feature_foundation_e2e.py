from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import re
import tempfile
from typing import Mapping
import unittest
from unittest.mock import patch
from uuid import UUID

from ashare_pipeline import orchestrator
from ashare_pipeline.deep_worker import (
    STATEMENT_DATASETS,
    enqueue_feature_build,
    load_candidate_context,
    read_verified_feature_bundle,
    run_deep,
)
from ashare_pipeline.feature_contract import CONTRACT_VERSION, FeatureBundle
from ashare_pipeline.financial_features import SHANGHAI
from ashare_pipeline.snapshot_repository import SnapshotRepository
from ashare_pipeline.snapshot_store import SnapshotStore
from ashare_pipeline.sources import FetchBatch, TerminalSourceError
from ashare_pipeline.state_store import StateStore
from tests.feature_fixture_helpers import (
    enqueue_legacy_parent_fixtures,
    latest_feature_set_rows,
    load_calendar_fixture,
    load_statement_fixture_batches,
    write_candidate_fixture_documents,
)


def _fixture_batches(
    candidates: Mapping[str, str], fixture_names: Mapping[str, str]
) -> dict[tuple[str, str], FetchBatch]:
    return load_statement_fixture_batches(candidates, fixture_names)


class FixtureStatementSource:
    def __init__(
        self,
        batches: Mapping[tuple[str, str], FetchBatch],
        missing: set[tuple[str, str]],
    ) -> None:
        self._batches = dict(batches)
        self._missing = set(missing)
        self.calls: list[tuple[str, str]] = []

    def fetch_financial_statement(
        self, symbol: str, dataset: str, report_period: str = "2026-06-30"
    ) -> FetchBatch:
        security_id = symbol.upper()
        if not re.fullmatch(r"(?:SH|SZ)\d{6}", security_id):
            raise AssertionError(
                f"worker supplied non-canonical fixture symbol: {symbol}"
            )
        key = (security_id, dataset)
        self.calls.append(key)
        if key in self._missing:
            raise TerminalSourceError(
                f"fixture statement missing: {security_id}/{dataset}"
            )
        return self._batches[key]

    def replace(self, security_id: str, dataset: str, batch: FetchBatch) -> None:
        self._batches[(security_id, dataset)] = batch


@dataclass(frozen=True)
class ReplayResult:
    bundles: tuple[FeatureBundle, ...]
    bundle_bytes: tuple[bytes, ...]
    feature_set_count: int
    status: Mapping[str, object]


class DeterministicUuid4:
    def __init__(self) -> None:
        self._value = 0

    def __call__(self) -> UUID:
        self._value += 1
        return UUID(int=self._value)


class HermeticDeepHarness:
    def __init__(self, candidates, fixture_names, missing_datasets):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project_root = Path(self.temp_dir.name)
        self.data_root = self.project_root / "data"
        self.security_ids = tuple(sorted(candidates))
        self._uuid4 = DeterministicUuid4()
        self.store = StateStore(self.data_root / "state.sqlite3")
        with self.stable_ids():
            self.store.initialize()
            write_candidate_fixture_documents(self.data_root, candidates)
            self.repository = SnapshotRepository(
                self.data_root, self.store, SnapshotStore(self.data_root)
            )
            calendar_batch = load_calendar_fixture("trade_calendar_2021_2026.json")
            self.calendar_ref, _ = self.repository.persist(calendar_batch)
            self.batches = _fixture_batches(candidates, fixture_names)
            missing = {
                (security_id, dataset)
                for security_id, datasets in missing_datasets.items()
                for dataset in datasets
            }
            self.source = FixtureStatementSource(self.batches, missing)
            enqueue_legacy_parent_fixtures(self.store, candidates)

    def stable_ids(self):
        return patch("ashare_pipeline.state_store.uuid.uuid4", new=self._uuid4)

    @classmethod
    def single_general_candidate(
        cls, *, industry: str = "包装印刷", security_id: str = "SH600001"
    ) -> "HermeticDeepHarness":
        return cls(
            candidates={security_id: industry},
            fixture_names={security_id: "general_nonfinancial_statements.json"},
            missing_datasets={},
        )

    def close(self) -> None:
        self.temp_dir.cleanup()

    def force_balance_equation_mismatch(self, security_id: str) -> None:
        original = self.batches[(security_id, "balance_sheet")]
        records = json.loads(json.dumps(original.records, ensure_ascii=False))
        target = next(
            row for row in records if str(row["REPORT_DATE"])[:10] == "2026-06-30"
        )
        target["TOTAL_ASSETS"] = float(target["TOTAL_ASSETS"]) + 2_000_000.0
        changed = FetchBatch(
            original.source,
            original.dataset,
            original.request,
            records,
            original.fetched_at_utc,
            original.source_version,
            original.metadata,
        )
        self.batches[(security_id, "balance_sheet")] = changed
        self.source.replace(security_id, "balance_sheet", changed)

    def enqueue_frozen_feature_job(self) -> str:
        with self.stable_ids():
            refs = {
                dataset: self.repository.persist(
                    self.batches[("SH600001", dataset)]
                )[0]
                for dataset in STATEMENT_DATASETS
            }
            context = load_candidate_context(self.data_root)
            self.source.calls.clear()
            return enqueue_feature_build(
                self.store,
                security_id="SH600001",
                report_period="2026-06-30",
                as_of_utc="2026-09-01T08:00:00+00:00",
                candidate_context=context,
                statement_snapshots=refs,
                trade_calendar_snapshot=self.calendar_ref,
            )

    def run(self) -> ReplayResult:
        with self.stable_ids():
            run_deep(
                self.data_root,
                self.store,
                source=self.source,
                snapshots=self.repository,
                trade_calendar_snapshot=self.calendar_ref,
                now_cn=datetime(2026, 9, 1, 16, 0, tzinfo=SHANGHAI),
                online=True,
                limit=9,
                heartbeat_seconds=0.01,
            )
        rows = latest_feature_set_rows(
            self.store,
            report_period="2026-06-30",
            contract_version=CONTRACT_VERSION,
        )
        latest_rows = tuple(
            self.store.latest_feature_set(
                security_id, "2026-06-30", CONTRACT_VERSION
            )
            for security_id in self.security_ids
        )
        if any(row is None for row in latest_rows):
            raise AssertionError("fixture run did not produce every current bundle")
        bundles = tuple(
            read_verified_feature_bundle(
                self.project_root, row["bundle_path"], row["bundle_hash"]
            )
            for row in latest_rows
        )
        status, exit_code = orchestrator.run_command(
            self.data_root,
            self.store.db_path,
            "status",
            now_cn="2026-09-01T16:00:00+08:00",
        )
        if exit_code != 0:
            raise AssertionError(f"fixture status failed: {exit_code}")
        return ReplayResult(
            bundles=bundles,
            bundle_bytes=tuple(bundle.canonical_bytes() for bundle in bundles),
            feature_set_count=len(rows),
            status=status,
        )


class FeatureFoundationEndToEndTests(unittest.TestCase):
    def test_three_security_replay_is_traceable_deterministic_and_nonformal(self):
        replay_inputs = {
            "candidates": {
                "SH600001": "包装印刷",
                "SZ000001": "银行",
                "SH600002": "房地产开发",
            },
            "fixture_names": {
                "SH600001": "general_nonfinancial_statements.json",
                "SZ000001": "bank_statements.json",
                "SH600002": "real_estate_statements.json",
            },
            "missing_datasets": {"SH600002": {"cash_flow_sheet"}},
        }
        harness = HermeticDeepHarness(**replay_inputs)
        independent = HermeticDeepHarness(**replay_inputs)
        self.addCleanup(harness.close)
        self.addCleanup(independent.close)

        first = harness.run()
        second = independent.run()

        self.assertNotEqual(harness.project_root, independent.project_root)
        self.assertEqual(len(first.bundles), 3)
        self.assertEqual(len(second.bundles), 3)
        self.assertEqual(first.bundle_bytes, second.bundle_bytes)
        self.assertEqual(first.feature_set_count, second.feature_set_count)
        bundles_by_security = {
            bundle.security_id: bundle for bundle in first.bundles
        }
        self.assertEqual(set(bundles_by_security), {"SH600001", "SZ000001", "SH600002"})
        industrial_facts = harness.store.list_financial_facts("SH600001")
        bank_facts = harness.store.list_financial_facts("SZ000001")
        industrial_values = [
            value
            for dimension in bundles_by_security["SH600001"].dimension_inputs.values()
            for value in dimension.values
        ]
        industrial_refs = [
            ref for value in industrial_values for ref in value.evidence
        ]
        self.assertGreater(len(industrial_facts), 0)
        self.assertGreater(len(bank_facts), 0)
        self.assertGreater(len(industrial_values), 0)
        self.assertGreater(len(industrial_refs), 0)
        all_refs = []
        for bundle in first.bundles:
            self.assertFalse(bundle.is_formal_score_ready)
            self.assertEqual(
                set(bundle.dimension_inputs), {"G", "V", "M", "EQ", "FS", "CA", "T"}
            )
            facts_by_id = {
                fact.id: fact
                for fact in harness.store.list_financial_facts(bundle.security_id)
            }
            for dimension in bundle.dimension_inputs.values():
                for value in dimension.values:
                    for ref in value.evidence:
                        all_refs.append(ref)
                        self.assertIn(ref.financial_fact_id, facts_by_id)
                        fact = facts_by_id[ref.financial_fact_id]
                        self.assertEqual(ref.source_snapshot_id, fact.source_snapshot_id)
                        snapshot = harness.repository.get(ref.source_snapshot_id)
                        self.assertIsNotNone(snapshot)
                        harness.repository.read_verified(snapshot)
        self.assertGreater(len(all_refs), 0)

        missing = next(
            item for item in first.bundles if item.security_id == "SH600002"
        )
        self.assertEqual(missing.financial_status, "blocked")
        self.assertIn("reported_but_statement_missing", missing.blockers)
        self.assertNotIn("S0", repr(first.bundles))
        self.assertNotIn("Sc", repr(first.bundles))
        self.assertFalse(first.status["formal_score_ready"])
        self.assertFalse(first.status["seven_dimension_ready"])
        self.assertEqual(
            first.status["official_pool_counts"],
            {"waiting_price": 0, "strong_attention": 0},
        )

    def test_frozen_feature_job_rebuilds_with_online_false(self):
        harness = HermeticDeepHarness.single_general_candidate()
        self.addCleanup(harness.close)
        harness.enqueue_frozen_feature_job()

        summary = run_deep(
            harness.data_root,
            harness.store,
            source=None,
            snapshots=harness.repository,
            trade_calendar_snapshot=harness.calendar_ref,
            now_cn=datetime(2026, 9, 1, 16, 0, tzinfo=SHANGHAI),
            online=False,
            limit=1,
        )

        self.assertEqual(summary.remote_attempts, 0)
        self.assertEqual(summary.feature_sets_written, 1)
        self.assertEqual(harness.source.calls, [])
        rows = latest_feature_set_rows(
            harness.store, "2026-06-30", CONTRACT_VERSION
        )
        self.assertEqual(len(rows), 1)
        bundle = read_verified_feature_bundle(
            harness.project_root, rows[0]["bundle_path"], rows[0]["bundle_hash"]
        )
        self.assertEqual(bundle.security_id, "SH600001")

    def test_unclassified_and_balance_mismatch_are_blocked(self):
        unclassified = HermeticDeepHarness.single_general_candidate(
            industry="不存在行业"
        )
        mismatch = HermeticDeepHarness.single_general_candidate(
            security_id="SH600001"
        )
        self.addCleanup(unclassified.close)
        self.addCleanup(mismatch.close)
        mismatch.force_balance_equation_mismatch("SH600001")

        unclassified_result = unclassified.run()
        mismatch_result = mismatch.run()

        self.assertEqual(len(unclassified_result.bundles), 1)
        unclassified_bundle = unclassified_result.bundles[0]
        self.assertEqual(unclassified_bundle.security_id, "SH600001")
        self.assertEqual(unclassified_bundle.financial_status, "blocked")
        self.assertEqual(
            unclassified_bundle.blockers,
            ("formal_industry_mapping_missing", "industry_template_unclassified"),
        )
        self.assertEqual(len(mismatch_result.bundles), 1)
        mismatch_bundle = mismatch_result.bundles[0]
        self.assertEqual(mismatch_bundle.security_id, "SH600001")
        self.assertEqual(mismatch_bundle.financial_status, "blocked")
        self.assertEqual(
            mismatch_bundle.blockers,
            ("balance_equation_mismatch", "formal_industry_mapping_missing"),
        )


if __name__ == "__main__":
    unittest.main()
