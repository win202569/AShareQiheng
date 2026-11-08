"""Read-only job diagnostics, never publication authority."""
import sqlite3
import unittest
from ashare_pipeline import state_store as schema


class ReleaseJobQuiescenceTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.addCleanup(self.db.close)
        for table, ddl in (
            ('formal_collection_task', schema._V5_TABLE_DDL),
            ('formal_range_task', schema._V7_TABLE_DDL),
            ('formal_range_attempt', schema._V7_TABLE_DDL),
            ('formal_source_circuit', schema._V6_TABLE_DDL),
        ):
            self.db.execute(ddl[table])
        self.db.execute('BEGIN')

    def read(self):
        from ashare_pipeline.formal_release_jobs import _read_job_quiescence
        return _read_job_quiescence(self.db)

    def task(self, table, status, task_id='t'):
        row = dict(id=task_id, refresh_generation='g', payload_json='{}', status=status,
                   created_at='2026-08-31T07:00:00+00:00', updated_at='2026-08-31T07:00:00+00:00')
        if table == 'formal_collection_task':
            row.update(kind='source', idempotency_key=task_id, payload_sha256='a'*64)
            worker = 'lease_worker'
        else:
            row.update(request_fingerprint=task_id, registry_manifest_hash='a'*64,
                       range_config_id='r', payload_hash='b'*64)
            worker = 'worker_id'
        if status == 'leased':
            row.update({worker: 'worker', 'lease_expires_at': '2000-01-01T00:00:00+00:00'})
        if status == 'verified':
            row['result_json'] = '{"classification":"verified_no_coverage"}'
        if status in ('retryable_failed', 'terminal_failed'):
            row['error_json'] = '{"code":"source_failed"}'
        if status == 'retryable_failed':
            row['next_retry_at'] = '2000-01-01T00:00:00+00:00'
        self.db.execute('INSERT INTO '+table+' ('+','.join(row)+') VALUES ('+
                        ','.join('?' for _ in row)+')', tuple(row.values()))

    def test_empty_snapshot_is_deterministic_and_does_not_write(self):
        before = self.db.total_changes
        first = self.read()
        self.assertEqual(first, self.read())
        self.assertIs(type(first[0]), bytes)
        self.assertEqual(first[1], ())
        self.assertEqual(self.db.total_changes, before)
        self.assertTrue(self.db.in_transaction)

    def test_both_task_queues_block_unfinished_or_failed_work(self):
        for table in ('formal_collection_task', 'formal_range_task'):
            for state in ('pending', 'leased', 'retryable_failed', 'terminal_failed'):
                with self.subTest(table=table, state=state):
                    self.db.execute('SAVEPOINT probe')
                    try:
                        self.task(table, state)
                        self.assertIn(table+':t:'+state, self.read()[1])
                    finally:
                        self.db.execute('ROLLBACK TO probe')
                        self.db.execute('RELEASE probe')

    def test_verified_no_coverage_is_not_a_failed_task(self):
        for table in ('formal_collection_task', 'formal_range_task'):
            self.task(table, 'verified')
        self.assertEqual(self.read()[1], ())

    def test_superseded_work_is_inactive_but_remains_in_commitment(self):
        before = self.read()[0]
        self.task('formal_collection_task', 'superseded')
        raw, reasons = self.read()
        self.assertEqual(reasons, ())
        self.assertNotEqual(raw, before)

    def test_stale_lease_on_verified_collection_task_is_not_quiescent(self):
        self.task('formal_collection_task', 'verified')
        self.db.execute("UPDATE formal_collection_task SET lease_worker='worker'")
        self.assertIn('formal_collection_task:t:residual_lease', self.read()[1])

    def test_expired_open_circuit_still_blocks_until_explicitly_closed(self):
        self.db.execute("INSERT INTO formal_source_circuit VALUES (?, ?, ?, ?, ?, ?, ?)",
                        ('source', 'open', 1, '{}', '2000-01-01T00:00:00+00:00',
                         '2000-01-02T00:00:00+00:00', '2000-01-01T00:00:00+00:00'))
        before, reasons = self.read()
        self.assertIn('formal_source_circuit:source:open', reasons)
        self.db.execute("UPDATE formal_source_circuit SET state='closed'")
        after, reasons = self.read()
        self.assertEqual(reasons, ())
        self.assertNotEqual(before, after)

    def test_unfinished_range_attempt_blocks_even_if_task_is_verified(self):
        self.task('formal_range_task', 'verified')
        self.db.execute("INSERT INTO formal_range_attempt (id,task_id,attempt_no,worker_id,leased_at,lease_expires_at,payload_json,payload_hash) VALUES ('a','t',1,'w','2000-01-01','2000-01-02','{}',?)", ('a'*64,))
        self.assertIn('formal_range_attempt:a:unfinished', self.read()[1])

    def test_snapshot_requires_existing_transaction_and_real_connection(self):
        from ashare_pipeline.formal_release_jobs import _read_job_quiescence
        with self.assertRaises(ValueError):
            _read_job_quiescence(object())
        self.db.commit()
        with self.assertRaises(ValueError):
            self.read()

    def test_missing_table_fails_closed(self):
        self.db.execute('DROP TABLE formal_range_attempt')
        with self.assertRaises(sqlite3.OperationalError):
            self.read()

    def test_unknown_circuit_state_fails_closed(self):
        self.db.execute("INSERT INTO formal_source_circuit VALUES ('s','unknown',0,'{}',NULL,NULL,'t')")
        with self.assertRaisesRegex(ValueError, 'unknown circuit'):
            self.read()

    def test_verified_task_with_unresolved_error_is_blocked(self):
        self.task('formal_collection_task', 'verified')
        self.db.execute("UPDATE formal_collection_task SET error_json='{}'")
        self.assertIn('formal_collection_task:t:inconsistent_verified_result', self.read()[1])

    def test_row_insertion_order_does_not_change_evidence(self):
        self.task('formal_collection_task', 'verified', 'b')
        self.task('formal_collection_task', 'verified', 'a')
        expected = self.read()
        self.db.execute('DELETE FROM formal_collection_task')
        self.task('formal_collection_task', 'verified', 'a')
        self.task('formal_collection_task', 'verified', 'b')
        self.assertEqual(self.read(), expected)


class ReleaseJobDatabaseTests(unittest.TestCase):
    def test_real_v9_database_read_preserves_rows_and_schema(self):
        from contextlib import closing
        from pathlib import Path
        import tempfile
        from ashare_pipeline.state_store import StateStore
        from ashare_pipeline.formal_release_jobs import _read_job_quiescence
        with tempfile.TemporaryDirectory() as folder:
            store = StateStore(Path(folder) / 'state.sqlite')
            store.initialize()
            with closing(store._connect()) as connection:
                before = tuple(connection.iterdump())
                connection.execute('BEGIN')
                self.assertEqual(_read_job_quiescence(connection)[1], ())
                self.assertTrue(connection.in_transaction)
                connection.rollback()
                self.assertEqual(tuple(connection.iterdump()), before)
