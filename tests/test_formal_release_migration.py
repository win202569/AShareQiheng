"""V9 is additive and refuses partial, foreign or damaged release schemas."""
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from ashare_pipeline import state_store as schema
from ashare_pipeline.state_store import StateStore


TABLES = ('formal_release_validation', 'formal_release', 'formal_release_preparation',
          'formal_release_file', 'formal_release_event')


class ReleaseMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / 'state.sqlite'
        fixture = Path(__file__).with_name('fixtures')
        with closing(sqlite3.connect(self.path)) as connection:
            connection.executescript((fixture / 'schema_v8.sql').read_text(encoding='utf-8'))
            connection.commit()

    def snapshot(self):
        with closing(sqlite3.connect(self.path)) as connection:
            objects = connection.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY name').fetchall()
            rows = {name: connection.execute('SELECT * FROM "'+name+'" ORDER BY rowid').fetchall()
                    for kind,name,_,_ in objects if kind == 'table' and not name.startswith('sqlite_')}
            return objects, rows

    def test_migration_preserves_all_existing_ddl_rows_and_ledger(self):
        before = self.snapshot()
        for name in schema._V8_TABLE_DDL:
            self.assertTrue(before[1][name], 'V8 preservation fixture must populate ' + name)
        StateStore(self.path).initialize()
        after = self.snapshot()
        self.assertEqual([r[0] for r in after[1]['schema_migration']], list(range(2,10)))
        names = {row[1] for row in before[0]}
        self.assertEqual([row for row in after[0] if row[1] in names], before[0])
        for table,rows in before[1].items():
            self.assertEqual(after[1][table][:len(rows)] if table == 'schema_migration'
                             else after[1][table], rows, table)
        self.assertEqual({row[1] for row in after[0] if row[0]=='table'
                          and row[1].startswith('formal_release')}, set(TABLES))
        StateStore(self.path).initialize()
        self.assertEqual(self.snapshot(), after)

    def test_fresh_database_migrates_through_nine(self):
        path = self.root / 'fresh.sqlite'
        StateStore(path).initialize()
        with closing(sqlite3.connect(path)) as connection:
            self.assertEqual(connection.execute('SELECT max(version) FROM schema_migration').fetchone()[0],9)
            self.assertEqual(connection.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_each_v9_ddl_failure_and_ledger_failure_rolls_back(self):
        self.assertTrue(hasattr(schema, '_V9_TABLE_DDL'), 'V9 definitions missing')
        before = self.snapshot()
        definitions = tuple(schema._V9_TABLE_DDL.values()) + tuple(schema._V9_INDEX_DDL.values())
        for count in range(1,len(definitions)+1):
            def fail(connection):
                for sql in definitions[:count]:
                    connection.execute(sql)
                raise RuntimeError('injected migration failure')
            with self.subTest(count=count), patch.object(StateStore,'_apply_v9_migration',side_effect=fail):
                with self.assertRaises(RuntimeError):
                    StateStore(self.path).initialize()
            self.assertEqual(self.snapshot(), before)
        original = StateStore._apply_v9_migration
        def fail_after_ledger(connection):
            original(connection)
            raise RuntimeError('injected ledger failure')
        with patch.object(StateStore,'_apply_v9_migration',side_effect=fail_after_ledger):
            with self.assertRaises(RuntimeError):
                StateStore(self.path).initialize()
        self.assertEqual(self.snapshot(), before)

    def test_foreign_release_objects_rejected_before_and_after_migration(self):
        for applied in (False,True):
            for sql in ('CREATE TABLE FORMAL_RELEASE_UNKNOWN(x TEXT)',
                        'CREATE VIEW formal_release_unknown AS SELECT * FROM score_run',
                        'CREATE TRIGGER formal_release AFTER INSERT ON score_run BEGIN SELECT 1; END',
                        'CREATE INDEX formal_release_unknown ON score_run(id)'):
                with self.subTest(applied=applied,sql=sql):
                    if applied:
                        StateStore(self.path).initialize()
                    with closing(sqlite3.connect(self.path)) as connection:
                        connection.execute(sql)
                        connection.commit()
                    before = self.snapshot()
                    try:
                        with self.assertRaises(RuntimeError):
                            StateStore(self.path).initialize()
                        self.assertEqual(self.snapshot(),before)
                    finally:
                        with closing(sqlite3.connect(self.path)) as connection:
                            kind = sql.split()[1]
                            name = sql.split()[2].split('(')[0]
                            connection.execute('DROP '+kind+' '+name)
                            connection.commit()

    def test_tampered_missing_and_extra_owned_objects_rejected_on_reopen(self):
        self.assertTrue(hasattr(schema, '_V9_TABLE_DDL'))
        for name in TABLES:
            StateStore(self.path).initialize()
            before = self.snapshot()
            with closing(sqlite3.connect(self.path)) as connection:
                connection.execute('ALTER TABLE '+name+' ADD COLUMN foreign_payload TEXT')
                connection.commit()
            damaged = self.snapshot()
            with self.assertRaises(RuntimeError):
                StateStore(self.path).initialize()
            self.assertEqual(self.snapshot(),damaged)
            with closing(sqlite3.connect(self.path)) as connection:
                connection.execute('ALTER TABLE '+name+' DROP COLUMN foreign_payload')
                connection.commit()
            self.assertEqual(self.snapshot(),before)

    def test_noncontiguous_and_future_ledger_rejected(self):
        for sql in ('DELETE FROM schema_migration WHERE version=5',
                    "INSERT INTO schema_migration VALUES (10,'future')"):
            with closing(sqlite3.connect(self.path)) as connection:
                connection.execute(sql)
                connection.commit()
            before = self.snapshot()
            with self.assertRaises(RuntimeError):
                StateStore(self.path).initialize()
            self.assertEqual(self.snapshot(),before)
            with closing(sqlite3.connect(self.path)) as connection:
                if 'DELETE' in sql:
                    connection.execute("INSERT INTO schema_migration VALUES (5,'restored')")
                else:
                    connection.execute('DELETE FROM schema_migration WHERE version=10')
                connection.commit()

    def test_release_foreign_keys_bind_validation_preparation_and_run(self):
        store = StateStore(self.path)
        store.initialize()
        def insert(connection, table, row):
            connection.execute('INSERT INTO '+table+' ('+','.join(row)+') VALUES ('+
                ','.join('?' for _ in row)+')', tuple(row.values()))
        with store._transaction(immediate=True) as connection:
            validation = dict(validation_hash='validation',run_id='retained',release_identity_hash='identity',
                purpose='publish',passed=1,payload_json='{}',signature='signature',key_id='key',created_at='now')
            insert(connection,'formal_release_validation',validation)
            row = dict(release_id='release',release_identity_hash='identity',run_id='retained',
                input_manifest_hash='input',result_hash='result',validation_hash='validation',
                status='publishing',release_path='D:/releases/release',created_at='now')
            for changes in ({'run_id':'absent'}, {'release_identity_hash':'other'},
                            {'status':'published'}, {'status':'blocked'}, {'attempt_token':'only-token'}):
                with self.subTest(changes=changes), self.assertRaises(sqlite3.IntegrityError):
                    insert(connection,'formal_release',dict(row,**changes))
            insert(connection,'formal_release',row)
            prepared = dict(preparation_hash='preparation',release_id='release',run_id='retained',
                release_identity_hash='identity',validation_hash='validation',payload_json='{}',
                signature='signature',key_id='key',manifest_json='{}',manifest_sha256='manifest',manifest_byte_size=1,
                fencing_generation=1,created_at='now')
            for changes in ({'run_id':'absent'}, {'validation_hash':'absent'},
                            {'manifest_byte_size':-1}, {'fencing_generation':0}):
                with self.subTest(changes=changes), self.assertRaises(sqlite3.IntegrityError):
                    insert(connection,'formal_release_preparation',dict(prepared,**changes))
            insert(connection,'formal_release_preparation',prepared)
            file = dict(release_id='release',preparation_hash='preparation',path='scores.csv',sha256='file',byte_size=0)
            insert(connection,'formal_release_file',file)
            for changes in ({'path':'SCORES.csv'}, {'path':'bad.csv','preparation_hash':'absent'},
                            {'path':'bad.csv','byte_size':-1}):
                with self.subTest(changes=changes), self.assertRaises(sqlite3.IntegrityError):
                    insert(connection,'formal_release_file',dict(file,**changes))
            self.assertEqual(connection.execute('PRAGMA foreign_key_check').fetchall(),[])

    def test_commit_failure_rolls_back_v9_objects(self):
        before = self.snapshot()
        class FailingCommit(sqlite3.Connection):
            def commit(self):
                raise sqlite3.OperationalError('injected commit failure')
        def connect():
            connection = sqlite3.connect(self.path,isolation_level=None,factory=FailingCommit)
            connection.execute('PRAGMA foreign_keys=ON')
            return connection
        store = StateStore(self.path)
        with patch.object(store,'_connect',side_effect=connect):
            with self.assertRaises(sqlite3.OperationalError):
                store.initialize()
        self.assertEqual(self.snapshot(),before)

    def test_missing_tables_indexes_and_foreign_attached_objects_rejected(self):
        self.assertTrue(hasattr(schema,'_V9_TABLE_DDL'))
        for kind,name in [('table',n) for n in TABLES]+[('index',n) for n in schema._V9_INDEX_DDL]:
            with self.subTest(kind=kind,name=name):
                path = self.root / (name+'.sqlite')
                StateStore(path).initialize()
                with closing(sqlite3.connect(path)) as connection:
                    connection.execute('DROP '+kind+' '+name)
                    connection.commit()
                with self.assertRaises(RuntimeError):
                    StateStore(path).initialize()
        for sql in ('CREATE INDEX unapproved ON formal_release(status)',
                    'CREATE TRIGGER unapproved AFTER INSERT ON formal_release BEGIN SELECT 1; END'):
            path = self.root / ('extra-'+sql.split()[1]+'.sqlite')
            StateStore(path).initialize()
            with closing(sqlite3.connect(path)) as connection:
                connection.execute(sql)
                connection.commit()
            with self.assertRaises(RuntimeError):
                StateStore(path).initialize()


if __name__ == '__main__':
    unittest.main()
