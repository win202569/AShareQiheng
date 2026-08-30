import math
import sqlite3
import tempfile
import threading
import unittest
from contextlib import closing
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ashare_pipeline.feature_contract import (
    CONTRACT_VERSION,
    DIMENSIONS,
    ConfidenceInputs,
    DimensionInput,
    EvidenceRef,
    FeatureBundle,
    FeatureValue,
    IndustryContext,
)
from ashare_pipeline.financial_schema import MAPPING_VERSION, FinancialFact
from ashare_pipeline.state_store import FinalizationBlocked, JobSpec, StateStore


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


def valid_feature_bundle(
    *, input_hash: str = "b" * 64,
    as_of_utc: str = "2026-08-29T16:00:00+00:00",
    blockers: tuple[str, ...] = ("formal_industry_mapping_missing",),
) -> FeatureBundle:
    evidence = EvidenceRef(
        "fact-a",
        "snapshot-a",
        "TOTAL_ASSETS",
        "a" * 64,
        "2026-08-20T15:59:59+00:00",
        "2026-08-21T07:00:00+00:00",
    )
    dimensions = {
        dimension: DimensionInput(
            "partial",
            (
                FeatureValue(
                    f"{dimension.lower()}.sample",
                    0.0,
                    "ratio",
                    "2026H1",
                    "observed",
                    "observed-v1",
                    (evidence,),
                    None,
                ),
            ),
        )
        for dimension in DIMENSIONS
    }
    return FeatureBundle(
        1,
        CONTRACT_VERSION,
        "SH600001",
        "2026-06-30",
        as_of_utc,
        "c" * 64,
        IndustryContext(
            "eastmoney-provisional",
            None,
            "包装印刷",
            "general_nonfinancial",
            "template-registry-v1",
            False,
        ),
        input_hash,
        "partial",
        0.5,
        ConfidenceInputs(0.5, {"timestamp": 0, "date_only": 1}, 3, True, None),
        dimensions,
        blockers,
        False,
    )


class StateStoreTestCase(unittest.TestCase):
    """Each test guards a durable public state-transition contract."""

    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "state.sqlite3"
        self.store = StateStore(self.db_path)
        self.store.initialize()

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def create_score_run(self) -> str:
        return self.store.create_score_run(
            "2026-06-30", "2026-08-31T08:00:00+08:00", "rules-v1", "universe-v1", "incremental"
        )

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

    def test_initialize_migrates_literal_v2_database_to_v3_without_changing_existing_rows(self) -> None:
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
                [(2,), (3,)],
            )
            tables = {
                row[0]
                for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
        self.assertTrue({"financial_fact", "feature_set", "feature_value"} <= tables)

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

    def test_initialize_twice_keeps_one_complete_v3_schema_and_ledger(self) -> None:
        self.store.initialize()

        with closing(sqlite3.connect(self.db_path)) as connection:
            self.assertEqual(
                connection.execute("SELECT version FROM schema_migration ORDER BY version").fetchall(),
                [(2,), (3,)],
            )
            counts = dict(
                connection.execute(
                    """SELECT name, COUNT(*) FROM sqlite_master
                    WHERE type = 'table' AND name IN ('financial_fact','feature_set','feature_value')
                    GROUP BY name"""
                )
            )
        self.assertEqual(counts, {"financial_fact": 1, "feature_set": 1, "feature_value": 1})

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

    def test_initialize_rejects_migration_ledgers_other_than_two_or_two_three(self) -> None:
        schema_sql = Path("tests/fixtures/schema_v2.sql").read_text(encoding="utf-8")
        for index, versions in enumerate(((3,), (2, 4), (2, 3, 4))):
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

    def test_initialize_applies_v3_when_migration_ledger_contains_only_v2(self) -> None:
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
                [(2,), (3,)],
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
        bundle = valid_feature_bundle(input_hash="b" * 64)
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
        with self.assertRaisesRegex(ValueError, "non-deterministic feature conflict"):
            self.store.put_feature_bundle(
                conflicting,
                bundle_path="data/curated/formal_features/2026-06-30/SH600001/c.json",
                bundle_hash=conflicting.bundle_hash(),
            )
        stored = self.store.get_feature_bundle_row("SH600001", "2026-06-30", "b" * 64)
        self.assertEqual(stored["bundle_hash"], bundle.bundle_hash())
        with closing(sqlite3.connect(self.db_path)) as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM feature_value").fetchone()[0], 7
            )

    def test_put_feature_bundle_rolls_back_header_and_values_when_one_value_aborts(self) -> None:
        bundle = valid_feature_bundle()
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

    def test_latest_feature_set_filters_exactly_orders_and_parses_json(self) -> None:
        older = valid_feature_bundle(
            input_hash="1" * 64, as_of_utc="2026-08-28T16:00:00+00:00"
        )
        newer = valid_feature_bundle(
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
        self.assertEqual(latest["dimension_status"], {key: "partial" for key in DIMENSIONS})
        self.assertEqual(latest["confidence_inputs"]["history_years_present"], 3)
        self.assertEqual(latest["blockers"], ["a-blocker", "z-blocker"])
        self.assertEqual(latest["missing"], [])
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
            valid_feature_bundle(input_hash="3" * 64),
            valid_feature_bundle(input_hash="4" * 64),
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


if __name__ == "__main__":
    unittest.main()
