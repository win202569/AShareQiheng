"""One-task collection and bounded, authenticated recovery; no coverage proofs."""

from datetime import datetime, timedelta, timezone

from .formal_range_contract import _range_binding_authority
from .formal_range_source import (
    FormalRangeAcquisitionError,
    FormalRangeSource,
    range_request_binding,
)
from .formal_sources import FormalRetryableSourceError, FormalSourceBlocked


_, _require_binding, _calendar_config, _, _ = _range_binding_authority()


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


def retry_delay(base, attempt_no, timeout_seconds):
    if type(attempt_no) is not int or attempt_no < 1:
        raise ValueError("attempt number must be positive")
    return min(base * (2 ** (attempt_no - 1)), timeout_seconds)


class FormalRangeWorker:
    def __init__(self, range_store, *, source_factory, worker_id, lease_seconds=60):
        if not callable(source_factory):
            raise ValueError("range worker source factory must be callable")
        if type(worker_id) is not str or not worker_id or worker_id != worker_id.strip():
            raise ValueError("range worker ID must be nonempty exact text")
        if type(lease_seconds) is not int or lease_seconds <= 0:
            raise ValueError("lease duration must be positive exact integer")
        self.range_store = range_store
        self.source_factory = source_factory
        self.worker_id = worker_id
        self.lease_seconds = lease_seconds

    def _source(self, request):
        binding = range_request_binding(request)
        _require_binding(binding)
        source = self.source_factory(binding)
        if type(source) is not FormalRangeSource:
            raise ValueError("range worker requires a genuine range source")
        return source, _calendar_config(binding)

    def _failure(self, lease, config, *, code, retryable, blocked=False):
        retryable = retryable and lease["attempt_no"] < config.retry_max_attempts
        next_retry_at = None
        if retryable:
            delay = (config.challenge_cooldown_seconds if blocked else
                     retry_delay(config.retry_base_seconds, lease["attempt_no"], config.timeout_seconds))
            next_retry_at = (datetime.fromisoformat(_utc_now()) + timedelta(seconds=delay)).isoformat()
        task = self.range_store.fail(lease["id"], self.worker_id, lease["attempt_id"],
            code=code, retryable=retryable, next_retry_at=next_retry_at)
        return dict(state=task["status"], task_id=task["id"], attempt_no=lease["attempt_no"],
                    code=code, next_retry_at=next_retry_at)

    def run_once(self) -> dict:
        lease = self.range_store.lease_next(self.worker_id, lease_seconds=self.lease_seconds)
        if lease is None:
            return {"state": "idle"}
        source, config = self._source(lease["request"])
        if lease["attempt_no"] > config.retry_max_attempts:
            return self._failure(lease, config, code="attempt_budget_exhausted", retryable=False)
        # Only live source acquisition is operational. Replay, authentication,
        # persistence, continuation and lease failures remain hard failures.
        try:
            fetch = source.fetch_verified(lease["request"])
        except FormalSourceBlocked:
            return self._failure(lease, config, code="source_blocked", retryable=True, blocked=True)
        except FormalRetryableSourceError:
            return self._failure(lease, config, code="source_retryable", retryable=True)
        except FormalRangeAcquisitionError:
            return self._failure(lease, config, code="source_terminal", retryable=False)
        observation = self.range_store.persist(lease["id"], self.worker_id, lease["attempt_id"], fetch=fetch)
        successor = source.next_page(observation)
        next_task = None if successor is None else self.range_store.enqueue(
            successor, refresh_generation=lease["refresh_generation"])
        return dict(state="verified", task_id=lease["id"], attempt_no=lease["attempt_no"],
                    next_task_id=None if next_task is None else next_task["id"])

    def resume(self, request, *, refresh_generation) -> dict:
        source, config = self._source(request)
        # Each successor comes from a current receipt, never from a detached
        # page ordinal. The signed limit also bounds verified-chain replay.
        for _ in range(config.max_pages):
            task = self.range_store.enqueue(request, refresh_generation=refresh_generation)
            if task["status"] != "verified":
                return dict(state=task["status"], task_id=task["id"])
            observation = self.range_store.read_verified(task["id"])
            request = source.next_page(observation)
            if request is None:
                return dict(state="verified", task_id=task["id"])
        raise ValueError("range resume exceeded signed page budget")
