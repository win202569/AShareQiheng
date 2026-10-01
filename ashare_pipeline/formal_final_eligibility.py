"""Authenticated final states and two-pool eligibility from matching D1/D2 proofs."""

from __future__ import annotations

import hashlib
import inspect
import json
import weakref
from decimal import Decimal
from types import MappingProxyType

from .formal_final_score_inputs import PolicyAdjustedScoreInputBatch
from .formal_final_scoring import FinalScoreCardBatch
from .formal_scoring import _canonical, _digest, _freeze


_HARD_VETO_SEMANTICS = frozenset({
    "st", "star_st", "delisting_arrangement", "forced_delist_risk",
    "governance_red", "nonpositive_equity", "audit_adverse",
    "audit_disclaimer", "audit_qualified", "no_effective_trade_20d",
})


def _threshold_breakdown(*, Sc, B, C, M, EQ, FS, T):
    values = {"Sc": Sc, "B": B, "C": C, "M": M, "EQ": EQ, "FS": FS, "T": T}
    if any(type(value) is not Decimal or not value.is_finite()
           for value in values.values()):
        raise ValueError("eligibility thresholds require finite exact Decimal values")
    common = {"C": C >= Decimal(".75"), "M": M >= Decimal("45"),
              "EQ": EQ >= Decimal("45"), "FS": FS >= Decimal("45")}
    return {"strong": {"Sc": Sc >= Decimal("70"), **common, "T": T >= Decimal("55")},
            "wait": {"B": B >= Decimal("65"), **common, "T": T < Decimal("55")}}


def _state_for(pending, hard_veto, strong_prohibited, wait_prohibited, *, out_of_scope=False):
    if out_of_scope:
        return "out_of_scope"
    if pending:
        return "pending_evidence"
    if hard_veto or (strong_prohibited and wait_prohibited):
        return "pool_vetoed"
    return "formal_scored"


def _validate_scorecard_coverage(security_ids, wire):
    """Check the canonical D2 partition before interpreting any member."""
    if type(wire) is not dict or type(wire.get("cards")) is not list or type(wire.get("pending")) is not dict:
        raise ValueError("final scorecard coverage is malformed")
    ids = tuple(security_ids)
    if len(ids) != len(set(ids)) or ids != tuple(sorted(ids)) or tuple(wire.get("security_ids", ())) != ids:
        raise ValueError("final scorecard universe differs from D1")
    card_ids = [card.get("security_id") for card in wire["cards"] if type(card) is dict]
    if len(card_ids) != len(wire["cards"]) or len(card_ids) != len(set(card_ids)):
        raise ValueError("final scorecards contain a malformed or duplicate member")
    pending_ids = set(wire["pending"])
    if (set(card_ids) & pending_ids or set(card_ids) | pending_ids != set(ids)
            or len(card_ids) + len(pending_ids) != len(ids)
            or card_ids != sorted(card_ids)):
        raise ValueError("final scorecards are missing, duplicated or outside the universe")


def _validate_ready_card_provenance(card_wire, row_wire, security_id, input_batch_hash):
    # D2 batch cards are raw rows. Their proof-only score_batch_hash is
    # authenticated separately by the selector canonical-byte check.
    if (card_wire["security_id"] != security_id
            or card_wire["source_entry_hash"] != row_wire["entry_hash"]
            or card_wire["source_batch_hash"] != input_batch_hash
            or card_wire["secondary_industry"] != row_wire["secondary_industry"]):
        raise ValueError("eligibility card and input provenance mismatch")


def _install_eligibility():
    proofs = {}
    d2_record = inspect.getclosurevars(FinalScoreCardBatch.require_verified).nonlocals["record"]

    def d2_source(scores):
        # D2 seals its genuine D1 source in a private proof record. Capture that
        # authority rather than resolving a replaceable module global at use time.
        return d2_record(scores, FinalScoreCardBatch)[3]

    def record(item, cls):
        saved = proofs.get(id(item))
        if type(item) is not cls or saved is None or saved[0]() is not item or saved[4] is not cls:
            raise ValueError("formal eligibility proof is forged or revoked")
        inputs, scores, input_bytes, score_bytes = saved[2]
        inputs.require_verified()
        scores.require_verified()
        if (inputs.canonical_bytes() != input_bytes or scores.canonical_bytes() != score_bytes
                or d2_source(scores) is not inputs):
            raise ValueError("formal eligibility source publication changed")
        return saved

    class SealedMeta(type):
        def __setattr__(cls, name, value):
            raise TypeError("formal eligibility types are immutable")

    class Proof(metaclass=SealedMeta):
        __slots__ = ("__weakref__",)

        def __init__(self, *args, **kwargs):
            raise TypeError("formal eligibility requires matching genuine D1/D2 batches")

        def __getattribute__(self, name):
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
            return record(self, type(self))[3]

        def to_dict(self):
            return json.loads(record(self, type(self))[3])

        def __copy__(self):
            raise TypeError("formal eligibility proofs cannot be copied")

        def __deepcopy__(self, memo):
            raise TypeError("formal eligibility proofs cannot be copied")

        def __reduce_ex__(self, protocol):
            raise TypeError("formal eligibility proofs cannot be reconstructed")

    class FormalEligibility(Proof):
        __slots__ = ()

    class FormalEligibilityBatch(Proof):
        __slots__ = ()

        def eligibility_for(self, security_id):
            saved = record(self, FormalEligibilityBatch)
            if type(security_id) is not str or security_id not in saved[5]:
                raise ValueError("eligibility selector is outside the frozen universe")
            result = saved[5][security_id]
            result.require_verified()
            return result

    def mint(cls, payload, sources, *, index=None, attributes=None):
        result = object.__new__(cls)
        key = id(result)
        data = dict(payload)
        data.update(attributes or {})
        proofs[key] = (weakref.ref(result, lambda _: proofs.pop(key, None)),
            _freeze(data), sources, _canonical(payload), cls, MappingProxyType(index or {}))
        return result

    def build(inputs, scores):
        if type(inputs) is not PolicyAdjustedScoreInputBatch or type(scores) is not FinalScoreCardBatch:
            raise ValueError("eligibility requires genuine D1 and D2 batches")
        inputs.require_verified()
        scores.require_verified()
        if d2_source(scores) is not inputs:
            raise ValueError("eligibility D1/D2 publications do not match")
        input_bytes, score_bytes = inputs.canonical_bytes(), scores.canonical_bytes()
        input_wire = inputs.to_dict()
        score_wire = scores.to_dict()
        ids = tuple(inputs.security_ids)
        if (_canonical(input_wire) != input_bytes or _canonical(score_wire) != score_bytes
                or tuple(input_wire.get("security_ids", ())) != ids
                or tuple(row.get("security_id") for row in input_wire.get("inputs", ())) != ids):
            raise ValueError("eligibility D1 canonical member snapshot is incomplete")
        _validate_scorecard_coverage(ids, score_wire)
        input_batch_hash, score_batch_hash = inputs.batch_hash, scores.batch_hash
        if (input_wire["batch_hash"] != input_batch_hash
                or score_wire["batch_hash"] != score_batch_hash
                or score_wire["source_batch_hash"] != input_batch_hash
                or score_wire["source_canonical_sha256"] != hashlib.sha256(input_bytes).hexdigest()):
            raise ValueError("eligibility D2 batch is not bound to D1")
        for key in ("registry_manifest_hash", "frozen_input_hash", "universe_hash"):
            if input_wire[key] != score_wire[key]:
                raise ValueError("eligibility D1/D2 root or frozen universe mismatch")
        input_rows = MappingProxyType({row["security_id"]: _freeze(row)
            for row in input_wire["inputs"]})
        card_rows = MappingProxyType({row["security_id"]: _freeze(row)
            for row in score_wire["cards"]})
        if len(input_rows) != len(ids) or len(card_rows) != len(score_wire["cards"]):
            raise ValueError("eligibility member snapshot is duplicated")
        # Validate every genuine selector once, then use only the immutable,
        # canonical batch snapshot for derivation. DTOs never enter this API.
        for sid in ids:
            selected = inputs.input_for(sid)
            if selected.canonical_bytes() != _canonical(dict(input_rows[sid],
                    batch_hash=input_batch_hash)):
                raise ValueError("eligibility D1 selector differs from canonical snapshot")
            selected_card = scores.card_for(sid)
            if selected_card is None:
                if sid not in score_wire["pending"]:
                    raise ValueError("eligibility missing D2 pending member")
            elif (sid not in card_rows or selected_card.canonical_bytes() !=
                    _canonical(dict(card_rows[sid], score_batch_hash=score_batch_hash))):
                raise ValueError("eligibility D2 selector differs from canonical snapshot")
        sources = (inputs, scores, input_bytes, score_bytes)
        rows, index = [], {}
        for sid in ids:
            row_wire = input_rows[sid]
            card_wire = card_rows.get(sid)
            if row_wire["status"] not in ("ready", "pending_evidence"):
                raise ValueError("D1 cannot declare out of scope or unknown states")
            policy = row_wire["policy_result"]
            pools = policy["pool_prohibitions"]
            strong_prohibited = bool(pools.get("strong"))
            wait_prohibited = bool(pools.get("wait"))
            hard_veto = any(decision["semantic_id"] in _HARD_VETO_SEMANTICS
                and any(effect["kind"] == "pool_prohibition" for effect in decision["proven_effects"])
                for decision in policy["decisions"])
            pending = row_wire["status"] == "pending_evidence"
            if pending != (card_wire is None):
                raise ValueError("D1 status and D2 scorecard partition disagree")
            if card_wire is not None:
                _validate_ready_card_provenance(card_wire, row_wire, sid, input_batch_hash)
                fields = {"Sc": Decimal(card_wire["Sc"]),
                    "C": Decimal(card_wire["confidence"]["C"]),
                    "R_safety": Decimal(card_wire["R_safety"]),
                    "B": Decimal(card_wire["B"]),
                    "V": Decimal(card_wire["dimensions"]["V"])}
                gates = _threshold_breakdown(Sc=fields["Sc"], B=fields["B"],
                    C=fields["C"], M=Decimal(card_wire["dimensions"]["M"]),
                    EQ=Decimal(card_wire["dimensions"]["EQ"]),
                    FS=Decimal(card_wire["dimensions"]["FS"]),
                    T=Decimal(card_wire["dimensions"]["T"]))
            else:
                fields = None
                gates = {"strong": dict.fromkeys(("Sc", "C", "M", "EQ", "FS", "T"), False),
                    "wait": dict.fromkeys(("B", "C", "M", "EQ", "FS", "T"), False)}
            state = _state_for(pending, hard_veto, strong_prohibited, wait_prohibited)
            strong = state == "formal_scored" and not strong_prohibited and all(gates["strong"].values())
            wait = state == "formal_scored" and not wait_prohibited and all(gates["wait"].values())
            if strong and wait:
                raise ValueError("formal strong and wait eligibility must be mutually exclusive")
            reasons = list(row_wire["reasons"] if pending else ())
            if hard_veto:
                reasons.append("hard_veto")
            if strong_prohibited:
                reasons.append("strong_prohibited")
            if wait_prohibited:
                reasons.append("wait_prohibited")
            for pool, checks in gates.items():
                reasons.extend(pool + ":" + key + "_below_threshold" for key, passed in checks.items()
                    if not passed)
            payload = dict(schema_version="formal-eligibility-v1", security_id=sid,
                state=state, source_entry_hash=row_wire["entry_hash"], source_batch_hash=input_batch_hash,
                score_batch_hash=score_batch_hash,
                card_hash=None if card_wire is None else card_wire["card_hash"],
                secondary_industry=None if card_wire is None else row_wire["secondary_industry"],
                sort_fields=fields, pending_reasons=tuple(row_wire["reasons"] if pending else ()),
                hard_veto=hard_veto, strong_prohibited=strong_prohibited,
                wait_prohibited=wait_prohibited, thresholds=gates,
                strong_qualified=strong, wait_qualified=wait,
                reason_codes=tuple(sorted(set(reasons))))
            payload["eligibility_hash"] = _digest(payload)
            rows.append(payload)
            index[sid] = mint(FormalEligibility, payload, sources)
        batch_payload = dict(schema_version="formal-eligibility-batch-v1",
            security_ids=ids, source_batch_hash=input_batch_hash,
            score_batch_hash=score_batch_hash, eligibilities=rows)
        batch_payload["batch_hash"] = _digest(batch_payload)
        result = mint(FormalEligibilityBatch, batch_payload, sources, index=index,
            attributes={"eligibilities": tuple(index[sid] for sid in ids)})
        result.require_verified()
        return result

    return FormalEligibility, FormalEligibilityBatch, build, d2_source


FormalEligibility, FormalEligibilityBatch, build_formal_eligibility_batch, _d2_source = _install_eligibility()
del _install_eligibility

__all__ = ["FormalEligibility", "FormalEligibilityBatch", "build_formal_eligibility_batch"]
