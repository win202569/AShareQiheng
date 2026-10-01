"""V8 migration preserves released schemas and fences the Stage D result graph."""

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import ashare_pipeline.state_store as schema
from ashare_pipeline.state_store import StateStore


TABLES = (
    "formal_final_run", "formal_final_artifact", "formal_final_input",
    "formal_final_scorecard", "formal_final_status", "formal_final_eligibility",
    "formal_final_pool_decision", "formal_final_dependency",
)
RANGE_TABLES = (
    "formal_range_task", "formal_range_attempt", "formal_range_snapshot",
    "formal_range_normalization_receipt",
)


class FormalFinalMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "v7.sqlite"
        with closing(sqlite3.connect(self.path)) as connection:
            connection.executescript(
                Path(__file__).with_name("fixtures").joinpath("schema_v7.sql").read_text(encoding="utf-8")
            )

    def snapshot(self, path=None):
        with closing(sqlite3.connect(path or self.path)) as connection:
            return (
                connection.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY name").fetchall(),
                connection.execute("SELECT * FROM schema_migration ORDER BY version").fetchall(),
                {name: connection.execute(f"SELECT * FROM {name} ORDER BY rowid").fetchall()
                 for name in (*RANGE_TABLES, "score_run", "score_item")},
            )

    def test_v7_range_schema_and_rows_survive_v8_migration_exactly(self):
        before = self.snapshot()
        StateStore(self.path).initialize()
        after = self.snapshot()
        self.assertEqual([row[0] for row in after[1]], [2, 3, 4, 5, 6, 7, 8])
        self.assertEqual(after[1][:6], before[1])
        self.assertEqual(after[2], before[2])
        self.assertTrue(all(rows for name, rows in before[2].items() if name in RANGE_TABLES))
        self.assertEqual([row for row in after[0] if row[1] in {r[1] for r in before[0]}], before[0])

    def test_fresh_database_records_contiguous_versions_2_through_8(self):
        path = self.root / "fresh.sqlite"
        store = StateStore(path)
        store.initialize()
        before = self.snapshot(path)
        StateStore(path).initialize()
        self.assertEqual(self.snapshot(path), before)
        self.assertEqual([row[0] for row in before[1]], [2, 3, 4, 5, 6, 7, 8])
        self.assertEqual({row[1] for row in before[0] if row[0] == "table" and row[1].startswith("formal_final_")}, set(TABLES))

    def test_v8_migration_is_atomic_and_reopen_verifies_exact_ddl(self):
        self.assertEqual(schema.SCHEMA_VERSION, 8)
        before = self.snapshot()
        definitions = tuple(schema._V8_TABLE_DDL.values()) + tuple(schema._V8_INDEX_DDL.values())
        for fail_after in range(1, len(definitions) + 1):
            with self.subTest(fail_after=fail_after):
                def fail_migration(connection):
                    for statement in definitions[:fail_after]:
                        connection.execute(statement)
                    raise RuntimeError("injected DDL failure")
                with patch.object(StateStore, "_apply_v8_migration", side_effect=fail_migration):
                    with self.assertRaisesRegex(RuntimeError, "injected DDL failure"):
                        StateStore(self.path).initialize()
                self.assertEqual(self.snapshot(), before)
        StateStore(self.path).initialize()
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("ALTER TABLE formal_final_run ADD COLUMN unexpected TEXT")
            connection.commit()
        damaged = self.snapshot()
        with self.assertRaisesRegex(RuntimeError, "v8 schema"):
            StateStore(self.path).initialize()
        self.assertEqual(self.snapshot(), damaged)

    def test_partial_or_extra_v8_object_rejects_without_advancing_ledger(self):
        for sql in (
            "CREATE TABLE formal_final_run(foreign_payload TEXT)",
            "CREATE TABLE formal_final_unknown(foreign_payload TEXT)",
            "CREATE INDEX formal_final_unknown_index ON score_item(security_id)",
            "CREATE VIEW formal_final_unknown_view AS SELECT * FROM score_run",
            "CREATE TRIGGER formal_final_unknown_trigger AFTER INSERT ON score_run BEGIN SELECT 1; END",
        ):
            with self.subTest(sql=sql):
                path = self.root / (str(len(list(self.root.iterdir()))) + ".sqlite")
                with closing(sqlite3.connect(path)) as connection:
                    connection.executescript(Path(__file__).with_name("fixtures").joinpath("schema_v7.sql").read_text(encoding="utf-8"))
                    connection.execute(sql)
                    connection.commit()
                before = self.snapshot(path)
                with self.assertRaises(RuntimeError):
                    StateStore(path).initialize()
                self.assertEqual(self.snapshot(path), before)

    def test_legacy_score_run_and_score_item_are_not_repurposed(self):
        before = self.snapshot()
        StateStore(self.path).initialize()
        after = self.snapshot()
        self.assertEqual([row[0] for row in after[1]], [2, 3, 4, 5, 6, 7, 8])
        for table in ("score_run", "score_item"):
            self.assertTrue(before[2][table])
            self.assertEqual(after[2][table], before[2][table])
            self.assertEqual([row for row in after[0] if row[2] == table], [row for row in before[0] if row[2] == table])

    @staticmethod
    def insert(connection, table, row):
        connection.execute(
            f"INSERT INTO {table} ({','.join(row)}) VALUES ({','.join('?' for _ in row)})",
            tuple(row.values()),
        )

    @staticmethod
    def run_row(run_id):
        return dict(run_id=run_id, mode="test_preview", status="preview_ready",
            input_manifest_hash="same-input", result_hash="same-result",
            registry_manifest_hash="root", frozen_input_hash="frozen", universe_hash="universe",
            coverage_manifest_hash="coverage", as_of_utc="2026-09-28T00:00:00Z",
            code_version="revision", contract_version="formal-final-v1", created_at=run_id)

    def test_v8_constraints_preserve_decimal_text_replays_and_same_run_members(self):
        self.assertEqual(schema.SCHEMA_VERSION, 8)
        store = StateStore(self.path)
        store.initialize()
        decimal = "0.1234567890123456789012345678901234567890123456789"
        with store._transaction(immediate=True) as connection:
            for run_id in ("first", "replay"):
                self.insert(connection, "formal_final_run", self.run_row(run_id))
            for field, invalid in (("mode", "preview"), ("status", "published")):
                row = dict(self.run_row("invalid"), **{field: invalid})
                with self.assertRaises(sqlite3.IntegrityError):
                    self.insert(connection, "formal_final_run", row)
            member = dict(run_id="first", security_id="SH600001", entry_hash="entry", payload_json="{}", payload_hash="input")
            self.insert(connection, "formal_final_input", member)
            child = dict(run_id="first", security_id="SH600001", payload_json="{}", payload_hash="child")
            rows = {
                "formal_final_artifact": dict(run_id="first", artifact_kind="input_manifest", payload_json="{}", artifact_hash="artifact"),
                "formal_final_scorecard": dict(child, card_hash="card", S0=decimal, Sc=decimal,
                    Sbase=decimal, B=decimal, R_safety=decimal, C=decimal, grade="A"),
                "formal_final_status": dict(child, state="formal_scored", reason_codes_json="[]"),
                "formal_final_eligibility": dict(child, eligibility_hash="eligibility", strong_qualified=1,
                    wait_qualified=0, hard_veto=0, strong_prohibited=0, wait_prohibited=0),
                "formal_final_pool_decision": dict(child, pool_name="strong", decision="selected",
                    selected_ordinal=1, decision_hash="decision"),
                "formal_final_dependency": dict(child, source_kind="snapshot", source_id="source",
                    source_hash="source-hash", effect_scope="security", dependent_key="SH600001"),
            }
            for table, row in rows.items():
                self.insert(connection, table, row)
                invalid = dict(row, run_id="missing" if table == "formal_final_artifact" else "replay")
                with self.subTest(table=table), self.assertRaises(sqlite3.IntegrityError):
                    self.insert(connection, table, invalid)
                with self.subTest(duplicate=table), self.assertRaises(sqlite3.IntegrityError):
                    self.insert(connection, table, row)
            self.assertEqual(tuple(connection.execute(
                "SELECT Sc,typeof(Sc),S0,Sbase,B,R_safety,C FROM formal_final_scorecard"
            ).fetchone()), (decimal, "text", decimal, decimal, decimal, decimal, decimal))
            for table in TABLES:
                self.assertNotIn("REAL", {row[2].upper() for row in connection.execute(f"PRAGMA table_info({table})")})
            self.insert(connection, "formal_final_input", dict(member, security_id="SH600002"))
            self.insert(connection, "formal_final_eligibility", dict(rows["formal_final_eligibility"], security_id="SH600002"))
            for field, invalid in (("pool_name", "other"), ("decision", "qualified"),
                                   ("selected_ordinal", None), ("selected_ordinal", 0), ("selected_ordinal", 1.5)):
                with self.subTest(field=field, invalid=invalid), self.assertRaises(sqlite3.IntegrityError):
                    self.insert(connection, "formal_final_pool_decision", dict(rows["formal_final_pool_decision"],
                        security_id="SH600002", **{field: invalid}))
            with self.assertRaises(sqlite3.IntegrityError):
                self.insert(connection, "formal_final_pool_decision", dict(rows["formal_final_pool_decision"], security_id="SH600002"))
            for decision in ("not_qualified", "overall_capacity_reached", "industry_cap_reached"):
                row = dict(rows["formal_final_pool_decision"], security_id="SH600002", decision=decision, selected_ordinal=None)
                self.insert(connection, "formal_final_pool_decision", row)
                connection.execute("DELETE FROM formal_final_pool_decision WHERE security_id='SH600002'")
            self.insert(connection, "formal_final_pool_decision", dict(rows["formal_final_pool_decision"],
                security_id="SH600002", pool_name="wait"))
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_v8_missing_tampered_and_extra_objects_fail_on_reopen(self):
        self.assertEqual(schema.SCHEMA_VERSION, 8)
        mutations = [f"ALTER TABLE {table} ADD COLUMN foreign_payload TEXT" for table in TABLES]
        mutations += [f"DROP TABLE {table}" for table in TABLES]
        mutations += [f"DROP INDEX {name}" for name in schema._V8_INDEX_DDL]
        mutations += [
            "CREATE INDEX unapproved_index ON formal_final_run(result_hash)",
            "CREATE TRIGGER unapproved_trigger AFTER INSERT ON formal_final_run BEGIN SELECT 1; END",
            "CREATE TABLE formal_final_extra(payload TEXT)",
        ]
        for number, sql in enumerate(mutations):
            with self.subTest(sql=sql):
                path = self.root / f"tampered-{number}.sqlite"
                StateStore(path).initialize()
                with closing(sqlite3.connect(path)) as connection:
                    connection.execute(sql)
                    before = connection.execute("SELECT * FROM schema_migration ORDER BY version").fetchall()
                    connection.commit()
                with self.assertRaises(RuntimeError):
                    StateStore(path).initialize()
                with closing(sqlite3.connect(path)) as connection:
                    self.assertEqual(connection.execute("SELECT * FROM schema_migration ORDER BY version").fetchall(), before)

    def test_v8_ledger_insert_and_commit_failure_roll_back_all_schema_objects(self):
        self.assertEqual(schema.SCHEMA_VERSION, 8)
        before = self.snapshot()
        original = StateStore._apply_v8_migration
        def fail_after_ledger(connection):
            original(connection)
            raise RuntimeError("after ledger")
        with patch.object(StateStore, "_apply_v8_migration", side_effect=fail_after_ledger):
            with self.assertRaisesRegex(RuntimeError, "after ledger"):
                StateStore(self.path).initialize()
        self.assertEqual(self.snapshot(), before)

        class FailingCommit(sqlite3.Connection):
            def commit(self):
                raise sqlite3.OperationalError("commit failure")
        def failing_connection():
            connection = sqlite3.connect(self.path, isolation_level=None, factory=FailingCommit)
            connection.execute("PRAGMA foreign_keys=ON")
            return connection
        store = StateStore(self.path)
        with patch.object(store, "_connect", side_effect=failing_connection):
            with self.assertRaisesRegex(sqlite3.OperationalError, "commit failure"):
                store.initialize()
        self.assertEqual(self.snapshot(), before)

    def test_v8_namespace_rejects_case_variant_extra_objects_before_and_after_migration(self):
        for migrated in (False, True):
            with self.subTest(migrated=migrated):
                path = self.root / f"case-{migrated}.sqlite"
                with closing(sqlite3.connect(path)) as connection:
                    connection.executescript(Path(__file__).with_name("fixtures").joinpath("schema_v7.sql").read_text(encoding="utf-8"))
                if migrated:
                    StateStore(path).initialize()
                with closing(sqlite3.connect(path)) as connection:
                    connection.execute("CREATE TABLE FORMAL_FINAL_UNKNOWN(payload TEXT)")
                    connection.commit()
                before = self.snapshot(path)
                with self.assertRaises(RuntimeError):
                    StateStore(path).initialize()
                self.assertEqual(self.snapshot(path), before)


if __name__ == "__main__":
    unittest.main()
