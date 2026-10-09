"""Real source checkpoints distinguish release bookkeeping from source changes.

Storage-only audit rows below are not signed validation proofs or capabilities.
"""
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

from ashare_pipeline.formal_final_score_inputs import _current_source_checkpoint
from ashare_pipeline.formal_metric_batch_guard import FormalMetricCurrentInputProvider
from ashare_pipeline.state_store import StateStore


class ReleaseSourceCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'state.sqlite'
        with closing(sqlite3.connect(self.path)) as connection:
            connection.executescript((Path(__file__).with_name('fixtures') /
                                     'schema_v8.sql').read_text(encoding='utf-8'))
            connection.commit()
        self.store = StateStore(self.path)
        self.store.initialize()
        self.provider = FormalMetricCurrentInputProvider(self.store)
        self.checkpoint = _current_source_checkpoint(self.store, self.provider)

    def test_own_audit_append_does_not_revoke_source_checkpoint(self):
        # Including release row contents in the digest falsely treats an audit
        # append as a correction. Both in-transaction and durable reads must work.
        with closing(self.store._connect()) as connection:
            connection.execute('BEGIN IMMEDIATE')
            connection.execute("""INSERT INTO formal_release_validation
                (validation_hash,run_id,release_identity_hash,purpose,passed,
                 payload_json,signature,key_id,created_at)
                VALUES ('audit','retained','identity','audit',0,'{}',
                        'storage-only','fixture','2026-10-09T00:00:00+00:00')""")
            self.checkpoint.recheck(connection)
            connection.commit()
        self.checkpoint.recheck()

    def test_release_schema_change_still_revokes_checkpoint(self):
        with closing(self.store._connect()) as connection:
            connection.execute('ALTER TABLE formal_release_event ADD COLUMN foreign_field TEXT')
            connection.commit()
        with self.assertRaisesRegex(ValueError, 'evidence changed'):
            self.checkpoint.recheck()

    def test_all_five_bookkeeping_tables_leave_source_checkpoint_current(self):
        with closing(self.store._connect()) as connection:
            connection.execute('BEGIN IMMEDIATE')
            statements = (
                """INSERT INTO formal_release_validation VALUES
                ('audit','retained','identity','audit',0,'{}','storage-only','fixture','now')""",
                """INSERT INTO formal_release
                (release_id,release_identity_hash,run_id,input_manifest_hash,result_hash,
                 validation_hash,status,release_path,created_at)
                VALUES ('release','identity','retained','input','result','audit',
                        'publishing','fixture-only','now')""",
                """INSERT INTO formal_release_preparation VALUES
                ('prep','release','retained','identity','audit','{}','storage-only',
                 'fixture','{}','manifest',2,1,'now')""",
                """INSERT INTO formal_release_file VALUES
                ('release','prep','scores.csv','file',0)""",
                """INSERT INTO formal_release_event VALUES
                ('event','release','retry','audit','{}','detail','now')""",
            )
            for statement in statements:
                connection.execute(statement)
                self.checkpoint.recheck(connection)
            self.assertEqual(connection.execute('PRAGMA foreign_key_check').fetchall(), [])
            connection.commit()
        self.checkpoint.recheck()

    def test_unknown_release_prefixed_table_is_not_excluded(self):
        with closing(self.store._connect()) as connection:
            connection.execute('CREATE TABLE formal_release_source_evidence(value TEXT)')
            connection.execute("INSERT INTO formal_release_source_evidence VALUES ('original')")
            connection.commit()
        checkpoint = _current_source_checkpoint(self.store, self.provider)
        with closing(self.store._connect()) as connection:
            connection.execute("UPDATE formal_release_source_evidence SET value='corrected'")
            connection.commit()
        with self.assertRaisesRegex(ValueError, 'evidence changed'):
            checkpoint.recheck()

    def test_source_change_in_same_transaction_as_audit_remains_blocking(self):
        with closing(self.store._connect()) as connection:
            connection.execute('BEGIN IMMEDIATE')
            connection.execute("""INSERT INTO formal_release_validation VALUES
                ('audit','retained','identity','audit',0,'{}','storage-only','fixture','now')""")
            connection.execute("UPDATE schema_migration SET applied_at='changed' WHERE version=9")
            with self.assertRaisesRegex(ValueError, 'evidence changed'):
                self.checkpoint.recheck(connection)
            connection.rollback()


if __name__ == '__main__':
    unittest.main()
