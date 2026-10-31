### Task 5: Owned Leases and Atomic Follow-Up Jobs

**Files:**
- Modify: `ashare_pipeline/state_store.py:156-252`
- Modify: `tests/test_state_store.py`

**Interfaces:**
- Consumes: existing job table and lease state machine.
- Produces: `JobSpec`, `renew_job_lease()`, `complete_job_with_followups()`, `fail_job_with_followups()`, and filtered `list_jobs()`. Existing `complete_job()`/`fail_job()` remain compatible.

- [ ] **Step 1: Add failing owner, renewal, and atomicity tests**

```python
def test_renew_job_lease_requires_current_unexpired_owner(self):
    job_id = self.store.enqueue_job("deep_statement", "statement-a", {})
    self.store.lease_next_job(["deep_statement"], "worker-a", 60, utc_at(0))
    expiry = self.store.renew_job_lease(job_id, "worker-a", 120, utc_at(30))
    self.assertEqual(expiry, utc_at(150))
    with self.assertRaisesRegex(ValueError, "lease owner"):
        self.store.renew_job_lease(job_id, "worker-b", 120, utc_at(31))


def test_statement_completion_and_feature_followup_are_one_transaction(self):
    job_id = self.store.enqueue_job("deep_statement", "statement-b", {})
    self.store.lease_next_job(["deep_statement"], "worker-a", 60, utc_at(0))
    followup = JobSpec("feature_build", "feature-b", {"security_id": "SH600001"})
    with sqlite3.connect(self.db_path) as connection:
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
    job = self.store.get_job(job_id)
    self.assertEqual(job["status"], "running")
    self.assertEqual(self.store.list_jobs(["feature_build"]), [])
```

Mirror the transaction test for `fail_job_with_followups()`. Add tests that a wrong worker cannot complete/fail a deep job, expired/completed jobs cannot renew, repeated follow-up insertion is idempotent, and legacy calls without `worker_id` still pass existing tests.

- [ ] **Step 2: Run the new lease tests to verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_state_store.StateStoreTestCase.test_renew_job_lease_requires_current_unexpired_owner tests.test_state_store.StateStoreTestCase.test_statement_completion_and_feature_followup_are_one_transaction -v
```

Expected: FAIL with missing renewal/follow-up APIs.

- [ ] **Step 3: Implement JobSpec and transactional transitions**

```python
@dataclass(frozen=True)
class JobSpec:
    kind: str
    idempotency_key: str
    payload: dict[str, object]


def renew_job_lease(
    self,
    job_id: str,
    worker_id: str,
    lease_seconds: int,
    now_utc: str | None = None,
) -> str:
    if lease_seconds <= 0:
        raise ValueError("lease_seconds must be positive")
    now = _utc_iso(now_utc)
    expiry = datetime.fromtimestamp(
        datetime.fromisoformat(now).timestamp() + lease_seconds,
        timezone.utc,
    ).isoformat()
    with self._transaction(immediate=True) as connection:
        cursor = connection.execute(
            """UPDATE job SET lease_expires_at=?,updated_at=?
            WHERE id=? AND status='running' AND lease_worker=?
              AND lease_expires_at>?""",
            (expiry, now, job_id, worker_id, now),
        )
        if cursor.rowcount != 1:
            raise ValueError("job is not held by the current unexpired lease owner")
    return expiry
```

Implement `complete_job_with_followups(job_id, worker_id, result, followups)` and `fail_job_with_followups(job_id, worker_id, error, retryable, next_retry_at, followups)` with one `BEGIN IMMEDIATE`: verify running status and owner, `INSERT OR IGNORE` each follow-up by idempotency key, then update the parent/statement state. Existing methods delegate with empty follow-ups; only deep-worker calls require explicit owner.

- [ ] **Step 4: Run all state-store tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_state_store -v
```

Expected: PASS.

- [ ] **Step 5: Commit job-state extensions**

```powershell
git add -- ashare_pipeline/state_store.py tests/test_state_store.py
git commit -m "feat: add owned leases and atomic follow-up jobs"
```

---

