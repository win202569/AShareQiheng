"""Authenticated pre-policy scoring; no policy adjustment or pool eligibility."""

from decimal import Context, Decimal, DivisionByZero, InvalidOperation, Overflow, ROUND_HALF_EVEN, localcontext
import hashlib
import json
from types import MappingProxyType
import weakref

from . import formal_score_inputs as score_input_module
from .formal_score_inputs import FormalScoreInput


_DIMENSION_WEIGHTS = (
    ("G", Decimal("0.18")),
    ("V", Decimal("0.18")),
    ("M", Decimal("0.18")),
    ("EQ", Decimal("0.12")),
    ("FS", Decimal("0.08")),
    ("CA", Decimal("0.16")),
    ("T", Decimal("0.10")),
)
_RISK_METRIC_IDS = (
    "M.return_persistence",
    "M.margin_persistence",
    "CA.shareholder_return_and_dilution",
    "CA.capital_discipline",
)
_DIMENSION_SLOT_COUNTS = MappingProxyType({"G": 4, "V": 3, "M": 3, "EQ": 4, "FS": 3, "CA": 4, "T": 4})


def _arithmetic_context():
    return Context(prec=50, rounding=ROUND_HALF_EVEN, Emin=-999999, Emax=999999,
        capitals=1, clamp=0, flags=[], traps=[InvalidOperation, DivisionByZero, Overflow])


def _finite_decimal(value, label, *, minimum=Decimal("0"), maximum=Decimal("100")):
    if type(value) is not Decimal or not value.is_finite() or value < minimum or value > maximum:
        raise ValueError(f"{label} requires a finite Decimal in [{minimum},{maximum}]")
    return value


def _plain(value):
    if isinstance(value, (dict, MappingProxyType)):
        return {key: _plain(item) for key, item in value.items()}
    if type(value) in (tuple, list):
        return [_plain(item) for item in value]
    return str(value) if type(value) is Decimal else value


def _canonical(value):
    return json.dumps(_plain(value), sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), allow_nan=False).encode()


def _digest(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _freeze(value):
    if type(value) is dict:
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if type(value) in (tuple, list):
        result = tuple(_freeze(item) for item in value)
        return value if type(value) is tuple and all(a is b for a, b in zip(value, result, strict=True)) else result
    return value


def grade_for_score(score):
    """Grade an unrounded, higher-is-better score; never grade risk exposure."""
    score = _finite_decimal(score, "grade")
    for boundary, grade in ((Decimal("90"), "A+"), (Decimal("80"), "A"),
            (Decimal("70"), "B"), (Decimal("60"), "C"), (Decimal("50"), "D")):
        if score >= boundary:
            return grade
    return "E"


def _calculate_untrusted_arithmetic(*, dimensions, confidence, metric_values):
    """Return detached raw arithmetic. This helper does not authenticate an input."""
    if type(dimensions) is not dict or tuple(dimensions) != tuple(key for key, _ in _DIMENSION_WEIGHTS):
        raise ValueError("score arithmetic requires exact ordered G,V,M,EQ,FS,CA,T dimensions")
    if type(metric_values) is not dict or tuple(metric_values) != _RISK_METRIC_IDS:
        raise ValueError("risk arithmetic requires exact dimension-qualified metric ids")
    for key, value in dimensions.items():
        _finite_decimal(value, key)
    for key, value in metric_values.items():
        _finite_decimal(value, key)
    _finite_decimal(confidence, "confidence", maximum=Decimal("1"))
    with localcontext(_arithmetic_context()):
        s0 = sum((weight * dimensions[key] for key, weight in _DIMENSION_WEIGHTS), Decimal("0"))
        sc = Decimal("50") + confidence * (s0 - Decimal("50"))
        sbase = sum((weight * dimensions[key] for key, weight in _DIMENSION_WEIGHTS[:-1]), Decimal("0")) / Decimal("0.90")
        base_score = Decimal("50") + confidence * (sbase - Decimal("50"))
        m_persistence = (Decimal("0.40") * metric_values["M.return_persistence"]
            + Decimal("0.30") * metric_values["M.margin_persistence"]) / Decimal("0.70")
        ca_downside = (Decimal("0.20") * metric_values["CA.shareholder_return_and_dilution"]
            + Decimal("0.15") * metric_values["CA.capital_discipline"]) / Decimal("0.35")
        r_safety = (Decimal("0.40") * dimensions["FS"] + Decimal("0.25") * dimensions["EQ"]
            + Decimal("0.20") * m_persistence + Decimal("0.15") * ca_downside)
        return {"S0": s0, "Sc": sc, "Sbase": sbase, "B": base_score,
            "M_persistence": m_persistence, "CA_downside": ca_downside, "R_safety": r_safety,
            "risk_exposure": Decimal("100") - r_safety}


def _calculate_untrusted_confidence(slot_weights, temporal_qualities, *, continuous_fy_count, confidence_cap):
    """Return detached D/P/H/K/C arithmetic. This helper grants no proof authority."""
    if (type(slot_weights) is not dict or not slot_weights or type(temporal_qualities) is not dict
            or tuple(slot_weights) != tuple(temporal_qualities)):
        raise ValueError("confidence arithmetic requires matching nonempty slot maps")
    if type(continuous_fy_count) is not int or continuous_fy_count not in (4, 5):
        raise ValueError("confidence history requires four or five continuous fiscal years")
    for key, weight in slot_weights.items():
        _finite_decimal(weight, f"{key} weight", maximum=Decimal("1"))
        _finite_decimal(temporal_qualities[key], f"{key} temporal quality", maximum=Decimal("1"))
    if confidence_cap is not None:
        _finite_decimal(confidence_cap, "confidence cap", maximum=Decimal("1"))
    with localcontext(_arithmetic_context()):
        d = sum(slot_weights.values(), Decimal("0"))
        if d != Decimal("1"):
            raise ValueError("confidence global slot weights must total one")
        p = sum((slot_weights[key] * temporal_qualities[key] for key in slot_weights), Decimal("0"))
        h = min(Decimal(continuous_fy_count) / Decimal("5"), Decimal("1"))
        k = Decimal("1")
        c = Decimal("0.60") + Decimal("0.40") * (
            Decimal("0.30") * d + Decimal("0.25") * p
            + Decimal("0.25") * h + Decimal("0.20") * k)
        if confidence_cap is not None:
            c = min(c, confidence_cap)
        return {"D": d, "P": p, "H": h, "K": k, "C": c}


def _install_pre_policy_scoring():
    proofs = {}
    module_globals = globals()
    source_module = score_input_module
    source_type = FormalScoreInput
    decimal_context = _arithmetic_context
    finite_decimal = _finite_decimal
    arithmetic = _calculate_untrusted_arithmetic
    confidence_arithmetic = _calculate_untrusted_confidence
    grade = grade_for_score
    plain, encode, digest, freeze = _plain, _canonical, _digest, _freeze
    json_module, hashlib_module, weakref_module = json, hashlib, weakref
    json_loads, json_dumps, sha256, weak_ref = json.loads, json.dumps, hashlib.sha256, weakref.ref
    local_context, decimal_type = localcontext, Decimal
    mapping_proxy_type = MappingProxyType
    context_type, rounding_mode = Context, ROUND_HALF_EVEN
    decimal_traps = (InvalidOperation, DivisionByZero, Overflow)
    dimension_weights, risk_metric_ids, dimension_slot_counts = (
        _DIMENSION_WEIGHTS, _RISK_METRIC_IDS, _DIMENSION_SLOT_COUNTS)

    def resolved_method(cls, name):
        return next((vars(base)[name] for base in cls.__mro__ if name in vars(base)), None)

    def capture_methods(types):
        return tuple((cls, name, resolved_method(cls, name)) for cls in types
            for name in sorted({name for base in cls.__mro__ if base is not object
                for name, value in vars(base).items()
                if callable(value) or isinstance(value, (staticmethod, classmethod))}))

    source_methods = capture_methods((source_type,))
    source_verify = resolved_method(source_type, "require_verified")
    source_canonical = resolved_method(source_type, "canonical_bytes")
    source_getattr = resolved_method(source_type, "__getattr__")

    def methods_unchanged(checks):
        if any(resolved_method(cls, name) is not value for cls, name, value in checks):
            raise ValueError("pre-policy score proof dependency changed")

    def class_members_unchanged(checks):
        for cls, expected in checks:
            current = vars(cls)
            if (set(current) != {name for name, _ in expected}
                    or any(current[name] is not value for name, value in expected)):
                raise ValueError("pre-policy score proof class member changed")

    def dependencies():
        methods_unchanged(source_methods)
        methods_unchanged(own_methods)
        class_members_unchanged(own_members)
        if (score_input_module is not source_module or FormalScoreInput is not source_type
                or score_input_module.FormalScoreInput is not source_type
                or _arithmetic_context is not decimal_context or _finite_decimal is not finite_decimal
                or _calculate_untrusted_arithmetic is not arithmetic
                or _calculate_untrusted_confidence is not confidence_arithmetic
                or grade_for_score is not grade or _plain is not plain or _canonical is not encode
                or _digest is not digest or _freeze is not freeze
                or json is not json_module or hashlib is not hashlib_module or weakref is not weakref_module
                or json.loads is not json_loads or json.dumps is not json_dumps
                or hashlib.sha256 is not sha256 or weakref.ref is not weak_ref
                or localcontext is not local_context or Decimal is not decimal_type
                or MappingProxyType is not mapping_proxy_type
                or Context is not context_type or ROUND_HALF_EVEN is not rounding_mode
                or (InvalidOperation, DivisionByZero, Overflow) != decimal_traps
                or _DIMENSION_WEIGHTS is not dimension_weights or _RISK_METRIC_IDS is not risk_metric_ids
                or _DIMENSION_SLOT_COUNTS is not dimension_slot_counts
                or module_globals.get("PrePolicyScoreCalculation") is not proof_type
                or calculate_pre_policy_score is not calculate):
            raise ValueError("pre-policy score calculation dependency changed")

    def verify_source(source, expected_bytes=None):
        dependencies()
        if type(source) is not source_type:
            raise ValueError("pre-policy scoring requires an exact genuine FormalScoreInput")
        source_verify(source)
        wire = source_canonical(source)
        if type(wire) is not bytes or (expected_bytes is not None and wire != expected_bytes):
            raise ValueError("pre-policy score source input changed or is noncanonical")
        return wire

    def source_field(source, name):
        return source_getattr(source, name)

    def temporal_quality(source, slot):
        metric_id = slot["metric_id"]
        if slot["evidence_kind"] == "registered_consensus_no_coverage":
            actual, rule = slot["context_fact"], slot["registered_rule"]
            if (metric_id != "T.expectation_change" or slot["value"] != decimal_type("50")
                    or slot["metric_score"] is not None or actual != source_field(source, "consensus_context")
                    or rule != source_field(source, "consensus_rule") or rule["metric_id"] != metric_id
                    or actual["no_coverage"] is not True
                    or actual["value"]["coverage_status"] != "no_valid_coverage"
                    or actual["value"]["estimates"]):
                raise ValueError("pre-policy neutral expectation is not the registered actual no-coverage slot")
            return decimal_type("0.8") if actual["evidence"]["calendar_binding"] is not None else decimal_type("1")
        refs = slot["evidence_refs"]
        if (slot["evidence_kind"] != "metric_percentile" or slot["metric_score"] is None
                or slot["context_fact"] is not None or slot["registered_rule"] is not None or not refs):
            raise ValueError("pre-policy verified metric slot evidence is incomplete")
        precisions = tuple(ref["published_precision"] for ref in refs)
        if any(value not in ("timestamp", "date_only") for value in precisions):
            raise ValueError("pre-policy slot has unsupported temporal evidence precision")
        return min(decimal_type("1") if value == "timestamp" else decimal_type("0.8") for value in precisions)

    def build_payload(source, source_bytes):
        slots = source_field(source, "slots")
        if not isinstance(slots, MappingProxyType) or len(slots) != 25:
            raise ValueError("pre-policy score requires all 25 immutable source slots")
        template_id = source_field(source, "template_id")
        cap = source_field(source, "confidence_cap")
        if cap not in (None, decimal_type("0.90")):
            raise ValueError("pre-policy confidence cap is outside the registered contract")
        dimensions, numerators, qualities = {}, {}, {}
        neutral_count = 0
        with local_context(decimal_context()):
            for dimension, dimension_weight in _DIMENSION_WEIGHTS:
                metric_ids = tuple(key for key in slots if key.startswith(dimension + "."))
                if len(metric_ids) != _DIMENSION_SLOT_COUNTS[dimension]:
                    raise ValueError("pre-policy dimension does not retain its exact signed slots")
                internal_total = decimal_type("0")
                dimension_score = decimal_type("0")
                for metric_id in metric_ids:
                    slot = slots[metric_id]
                    definition = slot["definition"]
                    bound = definition["definition"]
                    internal = slot["internal_weight"]
                    value = slot["value"]
                    if (slot["metric_id"] != metric_id or definition["metric_id"] != metric_id
                            or definition["template_id"] != template_id
                            or bound["dimension"] != dimension or dimension + "." + bound["metric_id"] != metric_id
                            or decimal_type(bound["internal_weight"]) != internal
                            or slot["dimension_weight"] != dimension_weight):
                        raise ValueError("pre-policy slot identity or signed weights differ")
                    finite_decimal(internal, metric_id + " internal weight", maximum=decimal_type("1"))
                    finite_decimal(value, metric_id)
                    quality = temporal_quality(source, slot)
                    if slot["temporal_quality"] != quality:
                        raise ValueError("pre-policy temporal quality differs from underlying evidence refs")
                    neutral_count += slot["evidence_kind"] == "registered_consensus_no_coverage"
                    internal_total += internal
                    dimension_score += internal * value
                    numerators[metric_id] = dimension_weight * internal
                    qualities[metric_id] = quality
                if internal_total != decimal_type("1"):
                    raise ValueError("pre-policy dimension internal weights do not total one")
                dimensions[dimension] = dimension_score
            if (cap is None and neutral_count != 0) or (cap is not None and neutral_count != 1):
                raise ValueError("pre-policy confidence cap and actual neutral slot disagree")
            denominator = sum(numerators.values(), decimal_type("0"))
            if denominator != decimal_type("1"):
                raise ValueError("pre-policy global signed weights do not total one")
            global_weights = {key: value / denominator for key, value in numerators.items()}
        confidence = confidence_arithmetic(global_weights, qualities,
            continuous_fy_count=source_field(source, "continuous_fy_count"), confidence_cap=cap)
        risk_values = {key: slots[key]["value"] for key in _RISK_METRIC_IDS}
        scores = arithmetic(dimensions=dimensions, confidence=confidence["C"], metric_values=risk_values)
        source_payload = json_loads(source_bytes)
        payload = dict(schema_version="formal-pre-policy-score-v1", calculation_stage="pre_policy", policy_final=False,
            input_hash=source_field(source, "input_hash"), batch_hash=source_field(source, "batch_hash"),
            metric_batch_hash=source_field(source, "metric_batch_hash"),
            registry_manifest_hash=source_field(source, "registry_manifest_hash"),
            registry_hashes=source_field(source, "registry_hashes"),
            frozen_input_hash=source_field(source, "frozen_input_hash"), universe_hash=source_field(source, "universe_hash"),
            population_hash=source_field(source, "population_hash"), security_id=source_field(source, "security_id"),
            template_id=template_id, as_of_utc=source_field(source, "as_of_utc"),
            source_input=source_payload, source_canonical_sha256=sha256(source_bytes).hexdigest(),
            dimensions=dimensions, dimension_grades={key: grade(value) for key, value in dimensions.items()},
            global_slot_weights=global_weights, confidence=confidence,
            S0=scores["S0"], S0_grade=grade(scores["S0"]), Sc=scores["Sc"], Sc_grade=grade(scores["Sc"]),
            Sbase=scores["Sbase"], Sbase_grade=grade(scores["Sbase"]),
            B=scores["B"], B_grade=grade(scores["B"]),
            M_persistence=scores["M_persistence"], M_persistence_grade=grade(scores["M_persistence"]),
            CA_downside=scores["CA_downside"], CA_downside_grade=grade(scores["CA_downside"]),
            R_safety=scores["R_safety"], R_safety_grade=grade(scores["R_safety"]),
            risk_exposure=scores["risk_exposure"])
        payload["calculation_hash"] = digest(payload)
        return payload

    def proof_record(proof):
        dependencies()
        record = proofs.get(id(proof))
        if type(proof) is not proof_type or record is None or record[0]() is not proof:
            raise ValueError("pre-policy score proof is forged, copied or unregistered")
        verify_source(record[3], record[4])
        return record

    class ProofMeta(type):
        def __setattr__(cls, name, value):
            if name in ("__getattribute__", "__bases__"):
                raise TypeError("pre-policy proof attribute-resolution guard or inheritance cannot be replaced")
            return super().__setattr__(name, value)

        def __delattr__(cls, name):
            if name in ("__getattribute__", "__bases__"):
                raise TypeError("pre-policy proof attribute-resolution guard or inheritance cannot be removed")
            return super().__delattr__(name)

    class Proof(metaclass=ProofMeta):
        __slots__ = ("__weakref__",)

        def __init__(self, *args, **kwargs):
            raise TypeError("pre-policy score proofs require a genuine complete FormalScoreInput")

        def __getattribute__(self, name):
            proof_record(self)
            return object.__getattribute__(self, name)

        def __getattr__(self, name):
            data = proof_record(self)[1]
            if name not in data:
                raise AttributeError(name)
            return data[name]

        def require_verified(self):
            proof_record(self)

        def canonical_bytes(self):
            return proof_record(self)[2]

        def to_dict(self):
            return json_loads(proof_record(self)[2])

        def __copy__(self):
            raise TypeError("pre-policy score proofs cannot be copied")

        def __deepcopy__(self, memo):
            raise TypeError("pre-policy score proofs cannot be copied")

    class PrePolicyScoreCalculation(Proof):
        __slots__ = ()

    proof_type = PrePolicyScoreCalculation

    def calculate(source):
        source_bytes = verify_source(source)
        payload = build_payload(source, source_bytes)
        verify_source(source, source_bytes)
        frozen_payload, canonical_payload = freeze(payload), encode(payload)
        result = object.__new__(proof_type)
        identity = id(result)
        proofs[identity] = (weak_ref(result, lambda _: proofs.pop(identity, None)),
            frozen_payload, canonical_payload, source, source_bytes)
        verify_source(source, source_bytes)
        return result

    own_methods = capture_methods((Proof, proof_type))
    own_members = tuple((cls, tuple(vars(cls).items())) for cls in (Proof, proof_type))
    return proof_type, calculate


PrePolicyScoreCalculation, calculate_pre_policy_score = _install_pre_policy_scoring()
del _install_pre_policy_scoring


__all__ = ["PrePolicyScoreCalculation", "calculate_pre_policy_score", "grade_for_score"]
