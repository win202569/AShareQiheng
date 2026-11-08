"""Transactional job-state diagnostics; not an authenticated release gate.

Only the configured validator may bind this data to its owned database and live
source guard. An empty reason tuple alone never grants publication authority.
No task, lease, circuit or retry state is changed here.
"""
import sqlite3
from .formal_release_types import canonical_release_bytes


def _read_job_quiescence(connection):
    """Return deterministic evidence bytes and blockers from an existing transaction.

    Conservative database-wide scope matches the source checkpoint. Pending work
    and expired-but-unreconciled leases remain blocking. No clock-based expiry
    silently closes a circuit or resolves a failed task. Signed no-coverage
    semantics remain the responsibility of the official coverage auditor.
    """
    if type(connection) is not sqlite3.Connection or not connection.in_transaction:
        raise ValueError('job quiescence requires an existing SQLite transaction')
    tables = ('formal_collection_task', 'formal_range_task',
              'formal_range_attempt', 'formal_source_circuit')
    evidence = {}
    reasons = []
    for table in tables:
        cursor = connection.cursor()
        cursor.row_factory = None
        try:
            cursor.execute('SELECT * FROM ' + table)
            columns = tuple(item[0] for item in cursor.description)
            rows = [dict(zip(columns, row, strict=True)) for row in cursor]
        finally:
            cursor.close()
        key = 'source' if table == 'formal_source_circuit' else 'id'
        if any(type(row[key]) is not str or not row[key] for row in rows):
            raise ValueError('job evidence has invalid identifiers')
        evidence[table] = sorted(rows, key=lambda row: row[key])
        for row in evidence[table]:
            prefix = table + ':' + row[key] + ':'
            if table in ('formal_collection_task', 'formal_range_task'):
                state = row['status']
                if state not in ('pending', 'leased', 'verified', 'retryable_failed',
                                 'terminal_failed', 'superseded'):
                    raise ValueError('job evidence has unknown task status')
                if state not in ('verified', 'superseded'):
                    reasons.append(prefix + state)
                worker = 'lease_worker' if table == 'formal_collection_task' else 'worker_id'
                if state != 'leased' and (row[worker] is not None or row['lease_expires_at'] is not None):
                    reasons.append(prefix + 'residual_lease')
                if state == 'verified' and (row['result_json'] is None or row['error_json'] is not None):
                    reasons.append(prefix + 'inconsistent_verified_result')
            elif table == 'formal_range_attempt':
                if row['finished_at'] is None or row['outcome'] is None:
                    reasons.append(prefix + 'unfinished')
            else:
                if row['state'] not in ('open', 'closed'):
                    raise ValueError('job evidence has unknown circuit state')
                if row['state'] == 'open':
                    reasons.append(prefix + 'open')
    raw = canonical_release_bytes(dict(schema='formal-release-job-evidence-v1', tables=evidence))
    return raw, tuple(sorted(reasons))


__all__ = []
