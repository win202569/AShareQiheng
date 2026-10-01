"""Authenticated final scorecards from complete policy-adjusted D1 inputs."""

from __future__ import annotations

import hashlib
import json
import weakref
from decimal import Decimal, InvalidOperation, localcontext
from types import MappingProxyType

from . import formal_final_score_inputs as input_module
from . import formal_scoring as scoring_module
from .formal_final_score_inputs import PolicyAdjustedScoreInput, PolicyAdjustedScoreInputBatch
from .formal_scoring import (
    _arithmetic_context, _calculate_untrusted_arithmetic,
    _calculate_untrusted_confidence, _canonical, _digest, _freeze,
    grade_for_score,
)


_DIMENSION_WEIGHTS = (
    ("G", Decimal("0.18")), ("V", Decimal("0.18")),
    ("M", Decimal("0.18")), ("EQ", Decimal("0.12")),
    ("FS", Decimal("0.08")), ("CA", Decimal("0.16")),
    ("T", Decimal("0.10")),
)
_DIMENSION_COUNTS = MappingProxyType({
    "G": 4, "V": 3, "M": 3, "EQ": 4, "FS": 3, "CA": 4, "T": 4,
})
_RISK_IDS = (
    "M.return_persistence", "M.margin_persistence",
    "CA.shareholder_return_and_dilution", "CA.capital_discipline",
)
_V_IDS = (
    "V.enterprise_value_or_sustainable_roe", "V.normalized_earnings_yield",
    "V.normalized_free_cash_flow_yield",
)


def _number(value, label, *, maximum=Decimal("100")):
    """Parse one canonical, bounded Decimal without consulting ambient context."""
    if type(value) is not str:
        raise ValueError(f"{label} requires canonical decimal text")
    try:
        result = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{label} requires finite decimal text") from exc
    if (not result.is_finite() or result < 0 or result > maximum
            or abs(result.as_tuple().exponent) > 100
            or len(result.as_tuple().digits) > 50):
        raise ValueError(f"{label} is outside finite bounded decimal range")
    return result


def _cap_trace(wire, *, _decimal=_number, _weights=_DIMENSION_WEIGHTS):
    result = wire.get("policy_result")
    if type(result) is not dict or type(result.get("dimension_caps")) is not dict:
        raise ValueError("final score requires a policy result and exact cap summary")
    known = frozenset(key for key, _ in _weights)
    summary = {}
    for dimension, maximum in result["dimension_caps"].items():
        if type(dimension) is not str or dimension not in known:
            raise ValueError("unknown final score cap dimension")
        summary[dimension] = _decimal(maximum, dimension + " cap")
    decisions = result.get("decisions")
    if type(decisions) is not list:
        raise ValueError("final score policy decisions must be canonical entries")
    derived, trace = {}, []
    for decision in decisions:
        if type(decision) is not dict or type(decision.get("proven_effects")) is not list:
            raise ValueError("final score policy decision is malformed")
        if decision.get("security_id") != wire.get("security_id"):
            raise ValueError("final score cap decision belongs to another security")
        for effect in decision["proven_effects"]:
            if type(effect) is not dict:
                raise ValueError("final score proven effect is malformed")
            if effect.get("kind") != "dimension_cap":
                continue
            dimension = effect.get("dimension")
            if type(dimension) is not str or dimension not in known:
                raise ValueError("unknown final score cap dimension")
            limit = _decimal(effect.get("maximum"), dimension + " cap effect")
            derived[dimension] = min(derived.get(dimension, limit), limit)
            item = {key: decision[key] for key in (
                "rule_id", "role", "semantic_id", "template_id", "security_id",
                "definition_hash", "decision_hash", "trace",
            )}
            item["effect"] = effect
            trace.append(item)
    if summary != derived:
        raise ValueError("final score cap summary differs from proven decisions")
    return summary, trace


def _calculate_untrusted_final(wire, *, _context=_arithmetic_context,
                               _confidence=_calculate_untrusted_confidence,
                               _arithmetic=_calculate_untrusted_arithmetic,
                               _grade=grade_for_score, _caps=_cap_trace,
                               _decimal=_number, _weights=_DIMENSION_WEIGHTS,
                               _counts=_DIMENSION_COUNTS, _risk_ids=_RISK_IDS,
                               _v_ids=_V_IDS):
    """Calculate detached final arithmetic; this helper grants no proof."""
    if type(wire) is not dict or wire.get("schema_version") != "policy-adjusted-score-input-v1":
        raise ValueError("final arithmetic requires a detached D1 entry wire")
    if wire.get("status") != "ready" or wire.get("reasons") != []:
        raise ValueError("pending D1 entry cannot produce a scorecard")
    slots = wire.get("slots")
    if type(slots) is not dict or len(slots) != 25:
        raise ValueError("final score requires exactly 25 final slots")
    if sum(slot.get("evidence_kind") == "policy_adjusted_valuation"
           for slot in slots.values() if type(slot) is dict) != 3:
        raise ValueError("final score requires exactly three Stage C valuation slots")
    raw, numerators, qualities = {}, {}, {}
    with localcontext(_context()):
        for dimension, dimension_weight in _weights:
            mids = tuple(mid for mid in slots if mid.startswith(dimension + "."))
            if len(mids) != _counts[dimension]:
                raise ValueError("final score dimension lacks its signed slots")
            internal_total = Decimal("0")
            dimension_total = Decimal("0")
            for mid in mids:
                slot = slots[mid]
                if type(slot) is not dict or slot.get("metric_id") != mid:
                    raise ValueError("final score slot identity is malformed")
                definition = slot.get("definition")
                if type(definition) is not dict or type(definition.get("definition")) is not dict:
                    raise ValueError("final score signed slot definition is missing")
                bound = definition["definition"]
                if (definition.get("metric_id") != mid
                        or definition.get("template_id") != wire.get("template_id")
                        or bound.get("dimension") != dimension
                        or dimension + "." + str(bound.get("metric_id")) != mid):
                    raise ValueError("final score slot differs from signed definition")
                internal = _decimal(slot.get("internal_weight"), mid + " internal weight",
                    maximum=Decimal("1"))
                if (internal != _decimal(bound.get("internal_weight"), mid + " signed weight",
                        maximum=Decimal("1"))
                        or _decimal(slot.get("dimension_weight"), mid + " dimension weight",
                            maximum=Decimal("1")) != dimension_weight):
                    raise ValueError("final score slot weights differ from signed definition")
                value = _decimal(slot.get("value"), mid + " value")
                quality = _decimal(slot.get("temporal_quality"), mid + " temporal quality",
                    maximum=Decimal("1"))
                if mid in _v_ids and slot.get("evidence_kind") != "policy_adjusted_valuation":
                    raise ValueError("final score V slot lacks Stage C provenance")
                if mid not in _v_ids and slot.get("evidence_kind") == "policy_adjusted_valuation":
                    raise ValueError("Stage C valuation provenance appears outside V")
                internal_total += internal
                dimension_total += internal * value
                numerators[mid] = dimension_weight * internal
                qualities[mid] = quality
            if internal_total != Decimal("1"):
                raise ValueError("final score dimension internal weights do not total one")
            raw[dimension] = dimension_total
        if len(numerators) != 25 or set(numerators) != set(slots):
            raise ValueError("final score slot membership is incomplete")
        denominator = sum(numerators.values(), Decimal("0"))
        if denominator != Decimal("1"):
            raise ValueError("final score global signed weights do not total one")
        weights = {mid: value / denominator for mid, value in numerators.items()}
        cap_summary, cap_trace = _caps(wire)
        dimensions = {dimension: min(raw[dimension], cap_summary[dimension])
            if dimension in cap_summary else raw[dimension] for dimension, _ in _weights}
    neutral = tuple(mid for mid, slot in slots.items()
        if slot["evidence_kind"] == "registered_consensus_no_coverage")
    confidence_cap = wire.get("confidence_cap")
    if (confidence_cap is None and neutral
            or confidence_cap is not None and (neutral != ("T.expectation_change",)
                or _decimal(confidence_cap, "confidence cap", maximum=Decimal("1")) != Decimal("0.90"))):
        raise ValueError("final score confidence cap differs from neutral consensus slot")
    confidence = _confidence(weights, qualities,
        continuous_fy_count=wire.get("continuous_fy_count"),
        confidence_cap=None if confidence_cap is None else Decimal("0.90"))
    risk_values = {mid: _decimal(slots[mid]["value"], mid + " risk value") for mid in _risk_ids}
    arithmetic = _arithmetic(
        dimensions=dimensions, confidence=confidence["C"], metric_values=risk_values)
    result = dict(raw_dimensions=raw, dimension_caps=cap_summary,
        cap_trace=cap_trace, dimensions=dimensions,
        dimension_grades={key: _grade(value) for key, value in dimensions.items()},
        global_slot_weights=weights, confidence=confidence, risk_metric_values=risk_values,
        **arithmetic)
    for key in ("S0", "Sc", "Sbase", "B", "M_persistence", "CA_downside", "R_safety"):
        result[key + "_grade"] = _grade(result[key])
    return result


def _install_final_scoring():
    proofs = {}
    source_batch_type, source_row_type = PolicyAdjustedScoreInputBatch, PolicyAdjustedScoreInput
    source_batch_verify = source_batch_type.require_verified
    source_batch_bytes = source_batch_type.canonical_bytes
    source_input_for = source_batch_type.input_for
    source_row_verify = source_row_type.require_verified
    source_row_bytes = source_row_type.canonical_bytes
    source_row_wire = source_row_type.to_dict
    helpers = (_arithmetic_context, _calculate_untrusted_arithmetic,
        _calculate_untrusted_confidence, grade_for_score, _canonical, _digest, _freeze,
        _calculate_untrusted_final)
    core = _calculate_untrusted_final
    core_defaults = dict(core.__kwdefaults__)
    cap_defaults = dict(_cap_trace.__kwdefaults__)
    constants = (_DIMENSION_WEIGHTS, _DIMENSION_COUNTS, _RISK_IDS, _V_IDS)
    owner = globals()
    input_owner = vars(input_module)
    scoring_owner = vars(scoring_module)
    encode, digest, freeze = _canonical, _digest, _freeze
    sha256, decode, reference = hashlib.sha256, json.loads, weakref.ref

    def dependencies():
        if (owner.get("PolicyAdjustedScoreInputBatch") is not source_batch_type
                or owner.get("PolicyAdjustedScoreInput") is not source_row_type
                or input_owner.get("PolicyAdjustedScoreInputBatch") is not source_batch_type
                or input_owner.get("PolicyAdjustedScoreInput") is not source_row_type
                or any(owner.get(name) is not value for name, value in zip((
                    "_arithmetic_context", "_calculate_untrusted_arithmetic",
                    "_calculate_untrusted_confidence", "grade_for_score", "_canonical",
                    "_digest", "_freeze", "_calculate_untrusted_final"), helpers, strict=True))
                or any(scoring_owner.get(name) is not value for name, value in zip((
                    "_arithmetic_context", "_calculate_untrusted_arithmetic",
                    "_calculate_untrusted_confidence", "grade_for_score", "_canonical",
                    "_digest", "_freeze"), helpers[:7], strict=True))
                or source_batch_type.require_verified is not source_batch_verify
                or source_batch_type.canonical_bytes is not source_batch_bytes
                or source_batch_type.input_for is not source_input_for
                or source_row_type.require_verified is not source_row_verify
                or source_row_type.canonical_bytes is not source_row_bytes
                or source_row_type.to_dict is not source_row_wire
                or core.__kwdefaults__ != core_defaults
                or _cap_trace.__kwdefaults__ != cap_defaults
                or (_DIMENSION_WEIGHTS, _DIMENSION_COUNTS, _RISK_IDS, _V_IDS) != constants
                or any(tuple(vars(cls).items()) != members for cls, members in own_members)):
            raise ValueError("final score authority dependency changed")

    def verify_source(batch):
        dependencies()
        if type(batch) is not source_batch_type:
            raise ValueError("final scoring requires a genuine PolicyAdjustedScoreInputBatch")
        source_batch_verify(batch)
        raw = source_batch_bytes(batch)
        if type(raw) is not bytes:
            raise ValueError("final score source batch canonical bytes are invalid")
        return raw

    def record(proof, cls):
        dependencies()
        saved = proofs.get(id(proof))
        if (type(proof) is not cls or saved is None or saved[0]() is not proof
                or saved[5] is not cls):
            raise ValueError("final score proof is forged, copied or unregistered")
        source_batch, source_bytes, source_row, row_bytes = saved[3], saved[4][0], saved[4][1], saved[4][2]
        if verify_source(source_batch) != source_bytes:
            raise ValueError("final score source batch has changed or been revoked")
        if source_row is not None:
            source_row_verify(source_row)
            if source_row_bytes(source_row) != row_bytes:
                raise ValueError("final score source row has changed or been revoked")
            if source_input_for(source_batch, saved[1]["security_id"]) is not source_row:
                raise ValueError("final score source row belongs to another batch")
        return saved

    class SealedMeta(type):
        def __setattr__(cls, name, value):
            raise TypeError("final score proof types are immutable")

        def __delattr__(cls, name):
            raise TypeError("final score proof types are immutable")

    open_subclass = [True]

    class Proof(metaclass=SealedMeta):
        __slots__ = ("__weakref__",)

        def __init_subclass__(cls, **kwargs):
            if not open_subclass[0]:
                raise TypeError("final score proof types cannot be inherited")

        def __init__(self, *args, **kwargs):
            raise TypeError("final score proofs require a verified D1 batch")

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
            return record(self, type(self))[2]

        def to_dict(self):
            return decode(record(self, type(self))[2])

        def __copy__(self):
            raise TypeError("final score proofs cannot be copied")

        def __deepcopy__(self, memo):
            raise TypeError("final score proofs cannot be copied")

        def __reduce_ex__(self, protocol):
            raise TypeError("final score proofs cannot be reconstructed")

    class FinalScoreCard(Proof):
        __slots__ = ()

    class FinalScoreCardBatch(Proof):
        __slots__ = ()

        def card_for(self, security_id):
            saved = record(self, FinalScoreCardBatch)
            if type(security_id) is not str or security_id not in saved[6]:
                raise ValueError("final score selector is outside the canonical universe")
            card = saved[6][security_id]
            if card is not None:
                card_state = record(card, FinalScoreCard)
                if (card_state[3] is not saved[3]
                        or card_state[1]["security_id"] != security_id
                        or card_state[1]["score_batch_hash"] != saved[1]["batch_hash"]):
                    raise ValueError("final score card belongs to another batch")
            return card

        def pending_for(self, security_id):
            saved = record(self, FinalScoreCardBatch)
            if type(security_id) is not str or security_id not in saved[6]:
                raise ValueError("final score selector is outside the canonical universe")
            return saved[7].get(security_id)

    open_subclass[0] = False

    def mint(cls, payload, source_batch, source_bytes, source_row=None, row_bytes=None,
             *, cards=None, pending=None):
        result = object.__new__(cls)
        key = id(result)
        data = dict(payload)
        if cards is not None:
            data["cards"] = tuple(card for card in cards.values() if card is not None)
        proofs[key] = (reference(result, lambda _: proofs.pop(key, None)), freeze(data),
            encode(payload), source_batch, (source_bytes, source_row, row_bytes), cls,
            MappingProxyType(cards or {}), MappingProxyType(pending or {}))
        return result

    def build(inputs):
        source_bytes = verify_source(inputs)
        security_ids = tuple(inputs.security_ids)
        if len(security_ids) != len(set(security_ids)) or security_ids != tuple(sorted(security_ids)):
            raise ValueError("final score D1 universe is not canonical")
        rows, row_proofs, pending = [], {}, {}
        for sid in security_ids:
            row = source_input_for(inputs, sid)
            if type(row) is not source_row_type:
                raise ValueError("final score requires genuine D1 entries")
            source_row_verify(row)
            row_bytes = source_row_bytes(row)
            wire = source_row_wire(row)
            if (wire.get("security_id") != sid or wire.get("batch_hash") != inputs.batch_hash
                    or encode(wire) != row_bytes):
                raise ValueError("final score D1 row binding changed")
            if wire.get("status") == "pending_evidence":
                if not wire.get("reasons"):
                    raise ValueError("pending D1 row has no reasons")
                pending[sid] = freeze(dict(security_id=sid, reasons=tuple(wire["reasons"]),
                    base_pending_reasons=tuple(wire["base_pending_reasons"]),
                    policy_pending_requirements=wire["policy_pending_requirements"],
                    valuation_pending_reasons=wire["valuation_pending_reasons"],
                    source_entry_hash=wire["entry_hash"]))
                row_proofs[sid] = None
                continue
            if wire.get("status") != "ready":
                raise ValueError("final score D1 row has unknown status")
            calculation = core(wire)
            provenance = {key: value for key, value in wire.items()
                if key.endswith("_hash") or key.endswith("_sha256")}
            payload = dict(schema_version="formal-final-score-card-v1",
                calculation_stage="policy_final", policy_final=True,
                security_id=sid, template_id=wire["template_id"],
                primary_industry=wire["primary_industry"],
                secondary_industry=wire["secondary_industry"],
                as_of_utc=wire["as_of_utc"], source_input=wire,
                **provenance, **calculation)
            payload.update(source_entry_hash=wire["entry_hash"],
                source_batch_hash=inputs.batch_hash,
                source_canonical_sha256=sha256(row_bytes).hexdigest())
            payload["card_hash"] = digest(payload)
            rows.append(payload)
            row_proofs[sid] = (payload, row, row_bytes)
        common = {key: value for key, value in inputs.to_dict().items()
            if key.endswith("_hash") or key.endswith("_sha256")}
        batch_payload = dict(schema_version="formal-final-score-card-batch-v1",
            security_ids=security_ids, source_batch_hash=inputs.batch_hash,
            source_canonical_sha256=sha256(source_bytes).hexdigest(),
            cards=rows, pending={sid: dict(item) for sid, item in pending.items()},
            **common)
        batch_payload["batch_hash"] = digest(batch_payload)
        cards = {}
        for sid, saved in row_proofs.items():
            if saved is None:
                cards[sid] = None
            else:
                payload, row, row_bytes = saved
                cards[sid] = mint(FinalScoreCard,
                    dict(payload, score_batch_hash=batch_payload["batch_hash"]),
                    inputs, source_bytes, row, row_bytes)
        result = mint(FinalScoreCardBatch, batch_payload, inputs, source_bytes,
            cards=cards, pending=pending)
        verify_source(inputs)
        if source_batch_bytes(inputs) != source_bytes:
            raise ValueError("final score D1 batch changed during calculation")
        return result

    own_members = tuple((cls, tuple(vars(cls).items())) for cls in
        (Proof, FinalScoreCard, FinalScoreCardBatch))
    return FinalScoreCard, FinalScoreCardBatch, build


FinalScoreCard, FinalScoreCardBatch, build_final_score_card_batch = _install_final_scoring()
del _install_final_scoring

__all__ = ["FinalScoreCard", "FinalScoreCardBatch", "build_final_score_card_batch"]
