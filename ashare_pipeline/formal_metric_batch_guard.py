"""Owned provider publications and a bounded optimistic database read barrier.

The completeness owner explicitly publishes whole current-input records. This
module does not infer missing issues or authenticate numeric facts; existing
feature repository reads still authenticate all published facts and receipts.
"""

from contextlib import contextmanager
import json
import sqlite3
from threading import RLock
import weakref

from .formal_feature_repository import (
    FormalFeatureCurrentInput, FormalFeatureRepository, _fact_snapshot,
    _issue_snapshot, _request,
)
from .formal_feature_contract import _canonical_json_bytes
from .formal_financial_schema import FormalFinancialFact, FormalFactIssue
from .formal_repository_identity import _require_repository_initialization
from .state_store import StateStore


def _owned_provider():
    records = {}
    connect = StateStore._connect
    initialized = _require_repository_initialization
    identity = FormalFeatureRepository._snapshot_identity
    snapshot_facts, snapshot_issues, request_values = _fact_snapshot, _issue_snapshot, _request
    encode = _canonical_json_bytes

    def require(provider, store=None):
        record = records.get(id(provider))
        if type(provider) is not FormalMetricCurrentInputProvider or record is None or record["ref"]() is not provider:
            raise ValueError("complete metric batch requires a genuine owned current-input provider")
        actual = record["store"]
        initialized(actual)
        if (type(actual) is not StateStore or (store is not None and store is not actual)
                or str(actual.db_path) != record["db_path"] or StateStore._connect is not connect
                or "_connect" in vars(actual)):
            raise ValueError("metric provider database dependency changed")
        if any(vars(FormalMetricCurrentInputProvider).get(name) is not method for name, method in methods):
            raise ValueError("metric provider publication dependency changed")
        return record

    class FormalMetricCurrentInputProvider:
        """Trusted completeness owner publishes detached, explicitly complete inputs.

        An unregistered request fails: there is no implicit empty complete input.
        All records and the monotonic publication epoch are closure-private.
        """
        __slots__ = ("__weakref__",)

        def __init__(self, state_store):
            if type(self) is not FormalMetricCurrentInputProvider or id(self) in records:
                raise ValueError("metric provider initialization is exact and single-use")
            if type(state_store) is not StateStore:
                raise ValueError("metric provider requires an exact StateStore")
            initialized(state_store)
            key = id(self)
            records[key] = dict(ref=weakref.ref(self, lambda _: records.pop(key, None)), store=state_store,
                db_path=str(state_store.db_path), lock=RLock(), epoch=0, snapshots={}, finalizing=False)

        def publish(self, snapshot):
            record = require(self)
            if type(snapshot) is not FormalFeatureCurrentInput:
                raise ValueError("metric publication requires an exact current-input snapshot")
            request = request_values(snapshot.security_id, snapshot.as_of_utc, snapshot.template_id,
                snapshot.registry_manifest_hash)
            captured_identity = identity(snapshot, request)
            facts, fact_bytes = snapshot_facts(snapshot.facts, snapshot.security_id)
            issues, issue_bytes = snapshot_issues(snapshot.issues)
            payload = dict(request, batch_id=captured_identity[-1], facts=[item.to_dict() for item in facts],
                issues=[item.to_dict() for item in issues], complete=True)
            canonical = encode(payload)
            if (identity(snapshot, request) != captured_identity
                    or snapshot_facts(snapshot.facts, snapshot.security_id)[1] != fact_bytes
                    or snapshot_issues(snapshot.issues)[1] != issue_bytes):
                raise ValueError("metric publication changed while detaching")
            with record["lock"]:
                require(self)
                record["epoch"] += 1
                if record["finalizing"]:
                    # Reentrant publication cannot hide behind an RLock, even
                    # if its caller catches the rejection inside finalization.
                    raise ValueError("metric provider changed during complete batch finalization")
                record["snapshots"][tuple(request.values())] = canonical

        def resolve_current_inputs(self, *, security_id, as_of_utc, template_id, registry_manifest_hash):
            record = require(self)
            request = request_values(security_id, as_of_utc, template_id, registry_manifest_hash)
            with record["lock"]:
                raw = record["snapshots"].get(tuple(request.values()))
            if raw is None:
                raise ValueError("metric provider has no explicitly complete published request")
            payload = json.loads(raw)
            payload["facts"] = tuple(FormalFinancialFact.from_dict(item) for item in payload["facts"])
            payload["issues"] = tuple(FormalFactIssue(**item) for item in payload["issues"])
            return FormalFeatureCurrentInput(**payload)

        def __copy__(self):
            raise TypeError("metric provider cannot be copied")

        def __deepcopy__(self, memo):
            raise TypeError("metric provider cannot be copied")

    methods = tuple(vars(FormalMetricCurrentInputProvider).items())

    @contextmanager
    def guard(provider, store):
        record = require(provider, store)
        observer = None
        active, finalized = False, False
        try:
            # Both captures precede all universe/context/feature reads. The
            # observer performs no writes; its own data_version is comparable.
            with record["lock"]:
                epoch = record["epoch"]
                observer = connect(store)
                observer.execute("PRAGMA busy_timeout = 1000")
                database_epoch = observer.execute("PRAGMA data_version").fetchone()[0]
            active = True

            class Guard:
                __slots__ = ()

                def finalize(self, mint):
                    nonlocal finalized
                    if not active or finalized:
                        raise ValueError("metric batch guard is closed or already finalized")
                    finalized = True
                    with record["lock"]:
                        require(provider, store)
                        if record["epoch"] != epoch:
                            raise ValueError("metric provider changed during complete batch")
                        record["finalizing"] = True
                        try:
                            # Short writer exclusion closes check-to-mint races;
                            # normal potentially long reads hold no writer lock.
                            observer.execute("BEGIN IMMEDIATE")
                            if observer.execute("PRAGMA data_version").fetchone()[0] != database_epoch:
                                raise ValueError("metric database changed during complete batch")
                            result = mint()
                            if record["epoch"] != epoch:
                                raise ValueError("metric provider changed during complete batch finalization")
                            return result
                        finally:
                            try:
                                observer.rollback()
                            finally:
                                record["finalizing"] = False

            yield Guard()
        except sqlite3.Error as error:
            raise ValueError("metric batch database guard unavailable") from error
        finally:
            active = False
            if observer is not None:
                try:
                    observer.rollback()
                finally:
                    observer.close()

    return FormalMetricCurrentInputProvider, guard


FormalMetricCurrentInputProvider, _metric_batch_guard = _owned_provider()
del _owned_provider

__all__ = ["FormalMetricCurrentInputProvider"]
