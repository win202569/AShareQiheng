"""Deterministic, authenticated strong and waiting-price pool selection."""

from __future__ import annotations

import json
import weakref
from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType

from .formal_final_eligibility import FormalEligibilityBatch
from .formal_scoring import _canonical, _digest, _freeze
from .formal_universe import canonical_security_id


_SORT_KEYS = {"Sc", "B", "C", "R_safety", "V"}
_POOL_NAMES = ("strong", "wait")
_DECISIONS = frozenset({"selected", "not_qualified", "industry_cap_reached", "overall_capacity_reached"})


@dataclass(frozen=True)
class _DetachedSelection:
    strong_ids: tuple[str, ...]
    wait_ids: tuple[str, ...]
    strong_decisions: MappingProxyType
    wait_decisions: MappingProxyType


def _validate_row(row, seen, source_hash=None):
    if type(row) is not dict:
        raise ValueError("pool eligibility rows must be detached dictionaries")
    required = {"security_id", "secondary_industry", "state", "strong_qualified", "wait_qualified",
        "sort_fields", "eligibility_hash", "source_entry_hash", "source_batch_hash", "score_batch_hash"}
    if set(row) != required:
        raise ValueError("pool eligibility row has an incomplete or extra field")
    sid = row["security_id"]
    try:
        if canonical_security_id(sid) != sid:
            raise ValueError
    except (TypeError, ValueError) as exc:
        raise ValueError("pool eligibility security id is not canonical") from exc
    if sid in seen:
        raise ValueError("pool eligibility contains duplicate security id")
    seen.add(sid)
    if row["state"] not in {"formal_scored", "pending_evidence", "pool_vetoed", "out_of_scope"}:
        raise ValueError("pool eligibility state is unknown")
    if type(row["strong_qualified"]) is not bool or type(row["wait_qualified"]) is not bool:
        raise ValueError("pool qualification flags must be bool")
    if row["strong_qualified"] and row["wait_qualified"]:
        raise ValueError("pool qualifications must be mutually exclusive")
    industry = row["secondary_industry"]
    if ((type(industry) is not str or not industry)
            and (row["strong_qualified"] or row["wait_qualified"])):
        raise ValueError("qualified pool member requires a nonempty secondary industry")
    fields = row["sort_fields"]
    if (type(fields) is not dict or set(fields) != _SORT_KEYS):
        raise ValueError("pool sort fields are incomplete")
    for key, value in fields.items():
        if type(value) is not Decimal or not value.is_finite():
            raise ValueError("pool sort fields require finite exact Decimal values")
    for key in ("eligibility_hash", "source_entry_hash", "source_batch_hash", "score_batch_hash"):
        if type(row[key]) is not str or not row[key]:
            raise ValueError("pool provenance hash is malformed")
    if source_hash is not None and row["source_batch_hash"] != source_hash:
        raise ValueError("pool rows come from different eligibility batches")
    return row


def _select_detached_rows(rows, *, strong_industry_cap=4, wait_industry_cap=10,
        strong_overall_cap=20, wait_overall_cap=50):
    """Pure selection core over already detached, validated eligibility rows."""
    if type(rows) not in (list, tuple):
        raise ValueError("pool selection rows must be a list or tuple")
    caps = (strong_industry_cap, wait_industry_cap, strong_overall_cap, wait_overall_cap)
    if any(type(cap) is not int or cap < 0 for cap in caps):
        raise ValueError("pool capacities must be nonnegative integers")
    seen, source_hash = set(), None
    checked = []
    for row in rows:
        if source_hash is None:
            source_hash = row.get("source_batch_hash") if type(row) is dict else None
        checked.append(_validate_row(row, seen, source_hash))

    def scan(pool):
        qualified = [r for r in checked if r[pool + "_qualified"] and r["state"] == "formal_scored"]
        keys = (("Sc", "C", "R_safety", "security_id") if pool == "strong"
            else ("B", "C", "V", "security_id"))
        ordered = sorted(qualified, key=lambda r: (
            -r["sort_fields"][keys[0]], -r["sort_fields"][keys[1]],
            -r["sort_fields"][keys[2]], r["security_id"]))
        industry_cap = strong_industry_cap if pool == "strong" else wait_industry_cap
        overall_cap = strong_overall_cap if pool == "strong" else wait_overall_cap
        counts, decisions, selected = {}, {}, []
        for row in checked:
            sid = row["security_id"]
            decisions[sid] = "not_qualified"
        for row in ordered:
            sid, industry = row["security_id"], row["secondary_industry"]
            if len(selected) >= overall_cap:
                decisions[sid] = "overall_capacity_reached"
            elif counts.get(industry, 0) >= industry_cap:
                decisions[sid] = "industry_cap_reached"
            else:
                selected.append(sid)
                counts[industry] = counts.get(industry, 0) + 1
                decisions[sid] = "selected"
        return tuple(selected), MappingProxyType(decisions)

    strong, strong_trace = scan("strong")
    wait, wait_trace = scan("wait")
    return _DetachedSelection(strong, wait, strong_trace, wait_trace)


def _install_pool_proofs():
    proofs = {}
    eligibility_type = FormalEligibilityBatch
    eligibility_verify = eligibility_type.require_verified
    eligibility_to_dict = eligibility_type.to_dict

    def verify_source(source):
        if type(source) is not eligibility_type:
            raise ValueError("pool selection requires a genuine FormalEligibilityBatch")
        eligibility_verify(source)
        wire = eligibility_to_dict(source)
        if _canonical(wire) != source.canonical_bytes():
            raise ValueError("eligibility publication changed")
        return wire

    class ProofMeta(type):
        def __setattr__(cls, name, value):
            if name in ("__getattribute__", "__bases__"):
                raise TypeError("pool proof guard cannot be replaced")
            super().__setattr__(name, value)

    class Proof(metaclass=ProofMeta):
        __slots__ = ("__weakref__",)

        def __init__(self, *args, **kwargs):
            raise TypeError("pool proofs require genuine eligibility")

        def __getattribute__(self, name):
            if name not in ("__class__", "__weakref__"):
                record(self, type(self))
            return object.__getattribute__(self, name)

        def __getattr__(self, name):
            data = record(self, type(self))[1]
            if name not in data:
                raise AttributeError(name)
            return data[name]

        def require_verified(self):
            record(self, type(self))

        def canonical_bytes(self):
            return record(self, type(self))[2]

        def to_dict(self):
            return json.loads(record(self, type(self))[2])

        def __copy__(self):
            raise TypeError("pool proofs cannot be copied")

        def __deepcopy__(self, memo):
            raise TypeError("pool proofs cannot be copied")

    class PoolSelectionDecision(Proof):
        __slots__ = ()

    class PoolSelectionBatch(Proof):
        __slots__ = ()

        def decision_for(self, security_id, pool):
            saved = record(self, PoolSelectionBatch)
            if type(security_id) is not str or pool not in _POOL_NAMES:
                raise ValueError("pool selector is malformed")
            decision = saved[4].get((security_id, pool))
            if decision is None:
                raise ValueError("pool selector is outside the frozen universe")
            decision.require_verified()
            return decision

    def record(item, cls):
        saved = proofs.get(id(item))
        if type(item) is not cls or saved is None or saved[0]() is not item:
            raise ValueError("pool proof is forged or revoked")
        source, source_bytes = saved[3], saved[5]
        wire = verify_source(source)
        if source_bytes != source.canonical_bytes() or _canonical(wire) != source_bytes:
            raise ValueError("pool source publication changed")
        if _canonical(saved[1]) != saved[2]:
            raise ValueError("pool proof payload was tampered")
        return saved

    def mint(cls, payload, source, *, decision_map=None):
        result = object.__new__(cls)
        identity = id(result)
        canonical = _canonical(payload)
        proofs[identity] = (weakref.ref(result, lambda _: proofs.pop(identity, None)),
            _freeze(payload), canonical, source, decision_map, source.canonical_bytes())
        return result

    def build(eligibility):
        wire = verify_source(eligibility)
        ids = tuple(wire.get("security_ids", ()))
        rows = wire.get("eligibilities")
        if type(ids) is not tuple or type(rows) is not list or tuple(r.get("security_id") for r in rows) != ids:
            raise ValueError("eligibility universe is malformed")
        detached = [{key: row.get(key) for key in (
            "security_id", "secondary_industry", "state", "strong_qualified",
            "wait_qualified", "sort_fields", "eligibility_hash", "source_entry_hash",
            "source_batch_hash", "score_batch_hash")} for row in rows]
        if any(row["source_batch_hash"] != wire.get("source_batch_hash") for row in detached):
            raise ValueError("eligibility rows are not bound to the published batch")
        selected = _select_detached_rows(detached)
        decisions = []
        decision_map = {}
        for sid in ids:
            for pool, trace in (("strong", selected.strong_decisions), ("wait", selected.wait_decisions)):
                payload = {"schema_version": "formal-pool-decision-v1", "security_id": sid,
                    "pool": pool, "decision": trace[sid], "eligibility_hash": next(r["eligibility_hash"] for r in detached if r["security_id"] == sid),
                    "source_batch_hash": eligibility.batch_hash}
                payload["decision_hash"] = _digest(payload)
                decision = mint(PoolSelectionDecision, payload, eligibility)
                decisions.append(payload)
                decision_map[(sid, pool)] = decision
        payload = {"schema_version": "formal-pool-batch-v1", "security_ids": ids,
            "source_batch_hash": eligibility.batch_hash, "strong_security_ids": selected.strong_ids,
            "wait_security_ids": selected.wait_ids, "counts": {"strong": len(selected.strong_ids), "wait": len(selected.wait_ids)},
            "decisions": tuple(decisions)}
        payload["batch_hash"] = _digest(payload)
        result = mint(PoolSelectionBatch, payload, eligibility, decision_map=decision_map)
        result.require_verified()
        return result

    def public(eligibility):
        return build(eligibility)

    return PoolSelectionDecision, PoolSelectionBatch, public


PoolSelectionDecision, PoolSelectionBatch, select_formal_pools = _install_pool_proofs()
del _install_pool_proofs

__all__ = ["PoolSelectionDecision", "PoolSelectionBatch", "select_formal_pools"]
