"""Deterministic point-in-time financial features, without scoring or I/O."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import json
import math
import re
import weakref
from typing import Iterable
from zoneinfo import ZoneInfo

from .formal_financial_schema import FormalFinancialFact, FormalFactIssue
from .formal_feature_contract import (
    FormalEvidenceRef, FormalFeatureBundle, FormalFeatureValue, FormulaNode,
    SignedFormalFeatureRegistry,
)
from .formal_registry_manifest import FormalRegistryManifest
from .formal_time import formal_version_sort_key, is_visible_at
from .formal_universe import canonical_security_id


_UNITS = frozenset({"CNY", "shares", "ratio", "CNY_per_share"})
_ENDPOINTS = {"Q1": "03-31", "H1": "06-30", "Q3": "09-30", "FY": "12-31"}
_DERIVATION = "formal-quarter-derivation-v1"
_GROUP = ("security_id", "statement", "metric_key", "period_start", "period_end", "period_kind", "unit", "nature", "accounting_basis")
_ROOT_HASHES = ("source_registry_hash", "mapping_registry_hash", "feature_registry_hash", "scoring_registry_hash", "industry_registry_hash", "cyclic_registry_hash", "redline_registry_hash", "status_registry_hash", "event_registry_hash")
_ISSUES = frozenset({"required_source_field_missing", "duplicate_source_field", "nonnumeric_value", "invalid_row_shape", "unknown_source_field", "mapping_not_applicable"})


def _bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _json(value: object) -> object:
    if value is None or type(value) in (str, bool, int):
        return value
    if type(value) is float and math.isfinite(value):
        return value
    if type(value) is list:
        return [_json(item) for item in value]
    if type(value) is dict and all(type(key) is str for key in value):
        return {key: _json(item) for key, item in value.items()}
    raise ValueError("wire must contain exact finite JSON-native types")


def _text(value: object) -> str:
    if type(value) is not str or not value or value.strip() != value or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError("expected canonical nonempty text")
    return value


def _utc(value: object) -> str:
    if type(value) is not str or not value.endswith("+00:00"):
        raise ValueError("expected canonical UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError("expected canonical UTC timestamp") from error
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed) or parsed.isoformat() != value:
        raise ValueError("expected canonical UTC timestamp")
    return value


def _date(value: object) -> str:
    if type(value) is not str or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is None:
        raise ValueError("expected canonical date")
    if date.fromisoformat(value).isoformat() != value:
        raise ValueError("expected canonical date")
    return value


def _hash(value: object) -> str:
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("expected SHA-256")
    return value


def _security(value: object) -> str:
    if type(value) is not str or canonical_security_id(value) != value:
        raise ValueError("expected canonical security identity")
    return value


def _snapshot_facts(facts: Iterable[FormalFinancialFact]):
    try:
        supplied = tuple(facts)
    except (TypeError, ValueError) as error:
        raise ValueError("facts must be a finite iterable of formal facts") from error
    result = []
    for item in supplied:
        if type(item) is not FormalFinancialFact:
            raise ValueError("expected exact sealed FormalFinancialFact")
        wire = item.to_dict()
        for key in ("published_at_utc", "effective_at_utc", "captured_at_utc", "created_at_utc"):
            _utc(wire[key])
        if wire["source_updated_at_utc"] is not None:
            _utc(wire["source_updated_at_utc"])
        result.append((FormalFinancialFact.from_dict(wire), wire))
    return tuple(result)


def _visible(wire: dict, cutoff: str) -> bool:
    return all(is_visible_at(wire[key], cutoff) for key in ("published_at_utc", "effective_at_utc", "source_updated_at_utc") if wire[key] is not None)


def _group(wire: dict) -> tuple:
    # None is the canonical instant start; text is used only as a sorting sentinel.
    return tuple("" if wire[key] is None else wire[key] for key in _GROUP)


@dataclass(frozen=True, slots=True)
class FormalFactVersionView:
    published_at_utc: str
    source_updated_at_utc: str | None
    captured_at_utc: str
    content_hash: str

    def __post_init__(self):
        _utc(self.published_at_utc)
        if self.source_updated_at_utc is not None:
            _utc(self.source_updated_at_utc)
        _utc(self.captured_at_utc)
        _hash(self.content_hash)


@dataclass(frozen=True, slots=True)
class FormalFactSelection:
    facts: tuple[FormalFinancialFact, ...]
    blockers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FormalQuarterDerivation:
    facts: tuple[FormalQuarterFact, ...]
    blockers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FormalHistoryResult:
    eligible: bool
    annual_endpoints: tuple[str, ...]
    blockers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FormalFormulaResult:
    value: float | None
    unit: str | None
    evidence: tuple[FormalEvidenceRef, ...]
    time_reliability: float | None
    missing_reason: str | None

    def __post_init__(self):
        if self.missing_reason is not None:
            _text(self.missing_reason)
            if self.value is not None or self.unit is not None or type(self.evidence) is not tuple or self.evidence or self.time_reliability is not None:
                raise ValueError("missing formula result must not contain partial evidence")
            return
        if type(self.value) is not float or not math.isfinite(self.value):
            raise ValueError("formula value must be a finite float")
        if type(self.unit) is not str or self.unit not in _UNITS:
            raise ValueError("formula unit is invalid")
        if type(self.time_reliability) is not float or not math.isfinite(self.time_reliability) or not 0 <= self.time_reliability <= 1:
            raise ValueError("formula reliability is invalid")
        if type(self.evidence) is not tuple or not self.evidence:
            raise ValueError("formula evidence is required")
        ids = []
        for ref in self.evidence:
            if type(ref) is not FormalEvidenceRef:
                raise ValueError("formula evidence must be exact")
            ids.append(ref.to_dict()["formal_fact_id"])
        if ids != sorted(set(ids)):
            raise ValueError("formula evidence must be sorted and unique")


def select_visible_formal_facts(facts: Iterable[FormalFinancialFact], as_of_utc: str) -> FormalFactSelection:
    cutoff = _utc(as_of_utc)
    groups = defaultdict(list)
    for fact, wire in _snapshot_facts(facts):
        if _visible(wire, cutoff):
            groups[_group(wire)].append((fact, wire))
    winners, blockers = [], set()
    for key in sorted(groups):
        candidates = groups[key]
        if len({(wire["parser_id"], wire["parser_version"], wire["mapping_version"]) for _, wire in candidates}) != 1:
            blockers.add("fact_mapping_version_conflict")
            continue
        ordered = []
        for fact, wire in candidates:
            view = FormalFactVersionView(wire["published_at_utc"], wire["source_updated_at_utc"], wire["captured_at_utc"], wire["source_content_sha256"])
            ordered.append((formal_version_sort_key(view), _bytes(wire), fact))
        best = min(item[0] for item in ordered)
        tied = {wire: fact for sort, wire, fact in ordered if sort == best}
        if len(tied) != 1:
            blockers.add("fact_selection_tie_conflict")
            continue
        winners.append(next(iter(tied.values())))
    return FormalFactSelection(tuple(winners), tuple(sorted(blockers)))


def _evidence_union(refs: Iterable[FormalEvidenceRef]) -> tuple[FormalEvidenceRef, ...]:
    by_id = {}
    for ref in refs:
        if type(ref) is not FormalEvidenceRef:
            raise ValueError("expected exact evidence")
        wire = ref.to_dict()
        key = wire["formal_fact_id"]
        if key in by_id and _bytes(by_id[key].to_dict()) != _bytes(wire):
            raise ValueError("conflicting evidence for one formal fact")
        by_id[key] = ref
    return tuple(by_id[key] for key in sorted(by_id))


def _make_quarter_type():
    fields = ("id", "security_id", "statement", "metric_key", "quarter_end", "quarter_key", "value", "unit", "nature", "accounting_basis", "mapping_version", "component_fact_ids", "evidence", "derivation_version")
    records = {}

    def validate_wire(value):
        wire = _json(value)
        if type(wire) is not dict or set(wire) != set(fields):
            raise ValueError("quarter wire has invalid fields")
        _hash(wire["id"])
        _security(wire["security_id"])
        for field in ("statement", "metric_key", "accounting_basis", "mapping_version"):
            _text(wire[field])
        for field in ("metric_key", "mapping_version"):
            if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]*", wire[field]) is None:
                raise ValueError("quarter metric/mapping identifiers must be canonical")
        if wire["statement"] not in {"income", "balance", "cash_flow"}:
            raise ValueError("invalid quarter statement")
        if type(wire["nature"]) is not str or type(wire["unit"]) is not str or wire["nature"] not in {"duration", "instant"} or wire["unit"] not in _UNITS:
            raise ValueError("invalid quarter unit/nature")
        if (wire["statement"] == "balance") != (wire["nature"] == "instant"):
            raise ValueError("quarter statement/nature mismatch")
        end = _date(wire["quarter_end"])
        key = wire["quarter_key"]
        if type(key) is not str or re.fullmatch(r"[0-9]{4}Q[1-4]", key) is None:
            raise ValueError("invalid global quarter key")
        if end != key[:4] + "-" + tuple(_ENDPOINTS.values())[int(key[-1]) - 1]:
            raise ValueError("quarter key/end mismatch")
        number = wire["value"]
        if type(number) is not float or not math.isfinite(number) or (number == 0 and math.copysign(1, number) < 0):
            raise ValueError("quarter value must be canonical finite float")
        ids = wire["component_fact_ids"]
        if type(ids) is not list or not ids or any(type(item) is not str for item in ids):
            raise ValueError("quarter requires operand IDs")
        for item in ids:
            _hash(item)
        if ids != sorted(set(ids)):
            raise ValueError("quarter operand IDs must be sorted/unique")
        expected_operands = 1 if wire["nature"] == "instant" or key.endswith("Q1") else 2
        if len(ids) != expected_operands or wire["derivation_version"] != _DERIVATION:
            raise ValueError("quarter derivation shape is invalid")
        if type(wire["evidence"]) is not list:
            raise ValueError("quarter evidence must be JSON array")
        refs = tuple(FormalEvidenceRef.from_dict(item) for item in wire["evidence"])
        if [ref.to_dict()["formal_fact_id"] for ref in refs] != ids:
            raise ValueError("quarter evidence must exactly cover operands")
        if any(ref.to_dict()["mapping_version"] != wire["mapping_version"] for ref in refs):
            raise ValueError("quarter evidence mapping mismatch")
        payload = {key: item for key, item in wire.items() if key not in {"id", "evidence"}}
        payload["schema_version"] = "formal-quarter-fact-v1"
        if hashlib.sha256(_bytes(payload)).hexdigest() != wire["id"]:
            raise ValueError("quarter identity mismatch")
        return wire, refs

    def construct(wire):
        wire, refs = validate_wire(wire)
        item = object.__new__(FormalQuarterFact)
        for key, value in wire.items():
            object.__setattr__(item, key, refs if key == "evidence" else tuple(value) if key == "component_fact_ids" else value)
        identity = id(item)
        records[identity] = (weakref.ref(item, lambda _, identity=identity: records.pop(identity, None)), _bytes(wire))
        return item

    @dataclass(frozen=True, slots=True, weakref_slot=True, init=False)
    class FormalQuarterFact:
        id: str
        security_id: str
        statement: str
        metric_key: str
        quarter_end: str
        quarter_key: str
        value: float
        unit: str
        nature: str
        accounting_basis: str
        mapping_version: str
        component_fact_ids: tuple[str, ...]
        evidence: tuple[FormalEvidenceRef, ...]
        derivation_version: str

        def __init__(self, *args, **kwargs):
            raise TypeError("quarters must be derived or loaded from canonical wire")

        def to_dict(self):
            if type(self) is not FormalQuarterFact:
                raise ValueError("quarter must have exact type")
            record = records.get(id(self))
            if record is None or record[0]() is not self:
                raise ValueError("quarter has no trusted provenance")
            wire = {}
            for key in fields:
                try:
                    value = getattr(self, key)
                except AttributeError as error:
                    raise ValueError("quarter is incomplete") from error
                if key in {"component_fact_ids", "evidence"}:
                    if type(value) is not tuple:
                        raise ValueError("quarter collections must be exact tuples")
                    if key == "evidence":
                        if any(type(ref) is not FormalEvidenceRef for ref in value):
                            raise ValueError("quarter evidence must have exact type")
                        value = [ref.to_dict() for ref in value]
                    else:
                        value = list(value)
                wire[key] = value
            validated, _ = validate_wire(wire)
            if _bytes(validated) != record[1]:
                raise ValueError("quarter was mutated")
            return validated

        @classmethod
        def from_dict(cls, value):
            if cls is not FormalQuarterFact:
                raise ValueError("quarter must have exact type")
            try:
                return construct(value)
            except (RecursionError, TypeError, AttributeError) as error:
                raise ValueError("quarter wire is malformed or too deep") from error

    return FormalQuarterFact, construct


FormalQuarterFact, _construct_quarter = _make_quarter_type()
del _make_quarter_type


def _make_deriver(construct_quarter):
    def derive_comparable_quarters(facts: Iterable[FormalFinancialFact]) -> FormalQuarterDerivation:
        families = defaultdict(list)
        for fact, wire in _snapshot_facts(facts):
            family = tuple(wire[key] for key in ("security_id", "statement", "metric_key", "unit", "nature")) + (wire["period_end"][:4],)
            families[family].append((fact, wire))
        output, blockers = [], set()
        for family in sorted(families):
            candidates = families[family]
            invalid = False
            for fields, reason in ((("accounting_basis",), "quarter_accounting_basis_mismatch"), (("parser_id", "parser_version"), "quarter_parser_version_mismatch"), (("mapping_version",), "quarter_mapping_version_mismatch")):
                if len({tuple(wire[key] for key in fields) for _, wire in candidates}) != 1:
                    blockers.add(reason)
                    invalid = True
            periods = {}
            for fact, wire in candidates:
                kind, year = wire["period_kind"], family[-1]
                if kind not in _ENDPOINTS or wire["period_end"] != year + "-" + _ENDPOINTS[kind] or (wire["nature"] == "duration" and wire["period_start"] != year + "-01-01"):
                    blockers.add("quarter_invalid_period")
                    invalid = True
                if kind in periods:
                    blockers.add("quarter_duplicate_period")
                    invalid = True
                periods[kind] = (fact, wire)
            if invalid:
                continue
            for index, kind in enumerate(_ENDPOINTS):
                if kind not in periods:
                    continue
                fact, wire = periods[kind]
                operands = [(fact, wire)]
                value = wire["value"]
                if wire["nature"] == "duration" and index:
                    previous = tuple(_ENDPOINTS)[index - 1]
                    if previous not in periods:
                        blockers.add("quarter_missing_prerequisite")
                        continue
                    operands.append(periods[previous])
                    value -= operands[-1][1]["value"]
                if not math.isfinite(value):
                    blockers.add("quarter_nonfinite_derivation")
                    continue
                evidence = _evidence_union(FormalEvidenceRef.from_formal_fact(item) for item, _ in operands)
                result = {key: wire[key] for key in ("security_id", "statement", "metric_key", "unit", "nature", "accounting_basis", "mapping_version")}
                result.update(quarter_end=wire["period_end"], quarter_key=family[-1] + f"Q{index + 1}", value=0.0 if value == 0 else float(value), component_fact_ids=sorted(item["id"] for _, item in operands), derivation_version=_DERIVATION)
                result["id"] = hashlib.sha256(_bytes({"schema_version": "formal-quarter-fact-v1", **result})).hexdigest()
                result["evidence"] = [ref.to_dict() for ref in evidence]
                output.append(construct_quarter(result))
        output.sort(key=lambda q: tuple(q.to_dict()[key] for key in ("security_id", "statement", "metric_key", "quarter_end", "unit", "nature", "accounting_basis", "mapping_version", "id")))
        return FormalQuarterDerivation(tuple(output), tuple(sorted(blockers)))
    return derive_comparable_quarters


derive_comparable_quarters = _make_deriver(_construct_quarter)
del _make_deriver, _construct_quarter


def require_formal_history(annual_endpoints, *, comparable_quarter_keys, as_of_utc: str, cyclic: bool) -> FormalHistoryResult:
    cutoff = datetime.fromisoformat(_utc(as_of_utc)).astimezone(ZoneInfo("Asia/Shanghai")).date()
    if type(cyclic) is not bool:
        raise ValueError("cyclic must be an exact bool supplied by verified policy")
    count = 5 if cyclic else 4
    latest_year = cutoff.year if (cutoff.month, cutoff.day) == (12, 31) else cutoff.year - 1
    required = tuple(f"{year:04d}-12-31" for year in range(latest_year - count + 1, latest_year + 1))
    quarter_ends = ("03-31", "06-30", "09-30", "12-31")
    ended = sum(f"{cutoff.year:04d}-{end}" <= cutoff.isoformat() for end in quarter_ends)
    latest_index = cutoff.year * 4 + ended - 1
    expected_quarters = tuple(f"{index // 4:04d}Q{index % 4 + 1}" for index in range(latest_index - 7, latest_index + 1))
    blockers = set()
    try:
        annuals = tuple(annual_endpoints)
        quarters = tuple(comparable_quarter_keys)
        for endpoint in annuals:
            if not _date(endpoint).endswith("-12-31"):
                raise ValueError("annual endpoints must end at year close")
        if annuals != tuple(sorted(set(annuals))) or any(endpoint > cutoff.isoformat() for endpoint in annuals):
            raise ValueError("annual endpoints must be sorted unique and not future")
        if any(type(key) is not str or re.fullmatch(r"[0-9]{4}Q[1-4]", key) is None for key in quarters):
            raise ValueError("invalid quarter keys")
        if not set(required).issubset(annuals):
            blockers.add("history_annual_window_incomplete")
        if quarters != expected_quarters:
            blockers.add("history_quarter_window_incomplete")
    except (TypeError, ValueError):
        blockers.add("history_invalid_input")
    if blockers:
        blockers.add("pending_evidence/history_not_mature")
        return FormalHistoryResult(False, (), tuple(sorted(blockers)))
    return FormalHistoryResult(True, required, ())


def _missing(reason: str) -> FormalFormulaResult:
    return FormalFormulaResult(None, None, (), None, reason)


def _formula_snapshot(node):
    if type(node) is not FormulaNode:
        raise ValueError("formula must have exact type")
    try:
        return FormulaNode.from_dict(node.to_dict())
    except (RecursionError, AttributeError, TypeError) as error:
        raise ValueError("formula is malformed or too deep") from error


def _formula_fact(item):
    if type(item) is FormalFinancialFact:
        _, wire = _snapshot_facts((item,))[0]
        if wire["period_kind"] != "FY" or wire["period_end"] != wire["period_end"][:4] + "-12-31":
            raise ValueError("only raw FY facts belong in the formula namespace")
        key = (wire["metric_key"], "FY" + wire["period_end"][:4])
        refs = (FormalEvidenceRef.from_formal_fact(item),)
    elif type(item) is FormalQuarterFact:
        wire = item.to_dict()
        key = (wire["metric_key"], wire["quarter_key"])
        refs = tuple(FormalEvidenceRef.from_dict(ref) for ref in wire["evidence"])
    else:
        raise ValueError("formula fact must have exact sealed type")
    reliability = min(1.0 if ref.to_dict()["published_precision"] == "timestamp" else .8 for ref in refs)
    return key, wire["security_id"], FormalFormulaResult(wire["value"], wire["unit"], refs, reliability, None)


def _evaluate(node, values, ambiguous=frozenset()):
    if node.op == "fact":
        key = (node.fact_key, node.period_key)
        if key in ambiguous:
            return _missing("formula_fact_ambiguous")
        return values.get(key, _missing("formula_fact_missing"))
    children = [_evaluate(child, values, ambiguous) for child in (node.items if node.op in {"median", "minimum"} else (node.left, node.right))]
    failed = sorted({child.missing_reason for child in children if child.missing_reason is not None})
    if failed:
        return _missing(failed[0])
    numbers = [child.value for child in children]
    units = [child.unit for child in children]
    unit = units[0]
    if node.op == "divide":
        if units[0] == units[1]:
            unit = "ratio"
        elif units == ["CNY", "shares"]:
            unit = "CNY_per_share"
        else:
            return _missing("formula_unit_mismatch")
    elif any(other != unit for other in units):
        return _missing("formula_unit_mismatch")
    try:
        if node.op == "add":
            number = numbers[0] + numbers[1]
        elif node.op == "subtract":
            number = numbers[0] - numbers[1]
        elif node.op == "divide":
            if numbers[1] == 0:
                return _missing("formula_zero_denominator")
            number = numbers[0] / numbers[1]
        elif node.op == "cagr":
            if numbers[0] <= 0 or numbers[1] <= 0:
                return _missing("formula_nonpositive_cagr")
            number = (numbers[1] / numbers[0]) ** (1 / node.intervals) - 1
            unit = "ratio"
        elif node.op == "minimum":
            number = min(numbers)
        else:
            ordered = sorted(numbers)
            half = len(ordered) // 2
            number = ordered[half] if len(ordered) % 2 else (ordered[half - 1] + ordered[half]) / 2
        if not math.isfinite(number):
            return _missing("formula_nonfinite_result")
    except (ArithmeticError, ValueError):
        return _missing("formula_nonfinite_result")
    evidence = _evidence_union(ref for child in children for ref in child.evidence)
    return FormalFormulaResult(0.0 if number == 0 else float(number), unit, evidence, min(child.time_reliability for child in children), None)


def evaluate_formula(node: FormulaNode, facts: dict) -> FormalFormulaResult:
    snapshot = _formula_snapshot(node)
    if type(facts) is not dict:
        raise ValueError("formula facts must be an exact dict")
    values, securities = {}, set()
    for key, item in tuple(facts.items()):
        if type(key) is not tuple or len(key) != 2 or any(type(part) is not str for part in key):
            raise ValueError("formula fact keys must be exact string pairs")
        identity, security, result = _formula_fact(item)
        if key != identity:
            raise ValueError("formula map key does not match fact identity")
        values[key] = result
        securities.add(security)
    if len(securities) > 1:
        raise ValueError("formula facts cannot mix securities")
    try:
        return _evaluate(snapshot, values)
    except RecursionError as error:
        raise ValueError("formula is too deep") from error


def build_formal_feature_bundle(*, security_id: str, as_of_utc: str, template_id: str, facts: Iterable[FormalFinancialFact], issues: Iterable[FormalFactIssue], registry: SignedFormalFeatureRegistry, registry_manifest: FormalRegistryManifest) -> FormalFeatureBundle:
    _security(security_id)
    _utc(as_of_utc)
    if type(template_id) is not str or template_id not in {"bank", "broker", "general_nonfinancial", "insurance", "real_estate"}:
        raise ValueError("invalid formal template")
    raw = _snapshot_facts(facts)
    if any(wire["security_id"] != security_id for _, wire in raw):
        raise ValueError("bundle facts must match security")
    if type(registry) is not SignedFormalFeatureRegistry:
        raise ValueError("bundle requires exact signed registry")
    slots = registry.slots_for_template(template_id)
    if type(registry_manifest) is not FormalRegistryManifest:
        raise ValueError("bundle requires exact sealed root")
    try:
        hashes = {key: getattr(registry_manifest, key) for key in _ROOT_HASHES}
        registry_manifest.assert_member_hashes(**hashes)
    except (AttributeError, TypeError) as error:
        raise ValueError("invalid root manifest") from error
    for root_key, child_key in (("source_registry_hash", "source_registry_hash"), ("mapping_registry_hash", "mapping_registry_hash"), ("feature_registry_hash", "registry_hash")):
        if hashes[root_key] != getattr(registry, child_key):
            raise ValueError("root-child registry hash mismatch")
    official = True
    try:
        registry_manifest.require_official()
    except ValueError:
        official = False
    # All provenance used below is detached before iterating caller-supplied issues.
    eligible = official and registry.release_eligible
    contract_version = registry.contract_version
    feature_hash = registry.registry_hash
    source_hash = registry.source_registry_hash
    mapping_hash = registry.mapping_registry_hash
    root_hash = registry_manifest.manifest_hash
    try:
        supplied_issues = tuple(issues)
    except TypeError as error:
        raise ValueError("issues must be iterable") from error
    issue_wires, blockers = {}, set()
    for issue in supplied_issues:
        if type(issue) is not FormalFactIssue:
            raise ValueError("issues must have exact sealed type")
        wire = issue.to_dict()
        if type(wire["code"]) is not str or wire["code"] not in _ISSUES:
            raise ValueError("issue code is not an extraction issue")
        issue_wires[_bytes(wire)] = wire
        blockers.add("formal_fact_issue_" + wire["code"])
    selection = select_visible_formal_facts((item for item, _ in raw), as_of_utc)
    blockers.update(selection.blockers)
    untrustworthy = bool(blockers)
    quarters = derive_comparable_quarters(selection.facts)
    blockers.update(quarters.blockers)
    values, ambiguous, identities = {}, set(), {}
    selected = _snapshot_facts(selection.facts)
    formula_inputs = [item for item, wire in selected if wire["period_kind"] == "FY"] + list(quarters.facts)
    for item in formula_inputs:
        key, _, result = _formula_fact(item)
        wire = item.to_dict()
        if key in identities and identities[key] != _bytes(wire):
            ambiguous.add(key)
        identities[key] = _bytes(wire)
        if key not in values:
            values[key] = result
    output = []
    if not eligible:
        blockers.add("feature_registry_not_release_eligible")
    for slot in slots:
        slot_wire = slot.to_dict()
        if not eligible or untrustworthy:
            reason = "feature_registry_not_release_eligible" if not eligible else "feature_input_not_trustworthy"
            status, result = "blocked", _missing(reason)
        else:
            result = _evaluate(_formula_snapshot(slot.formula), values, ambiguous)
            if result.missing_reason is None and result.unit != slot_wire["unit"]:
                result = _missing("formula_unit_mismatch")
            status = "derived" if result.missing_reason is None else "missing"
            if status == "missing" and slot_wire["required"]:
                blockers.add("feature_required_slot_missing")
        output.append(FormalFeatureValue(slot_wire["slot_id"], result.value, slot_wire["unit"], status, slot_wire["formula_version"], result.evidence, result.missing_reason))
    candidates = {}
    for _, wire in raw:
        if _visible(wire, as_of_utc):
            record = {key: wire[key] for key in ("id", "source_snapshot_id", "source_content_sha256", "source_refresh_generation")}
            candidates[_bytes(record)] = record
    input_wire = dict(
        schema_version="formal-feature-input-v1",
        security_id=security_id,
        as_of_utc=as_of_utc,
        template_id=template_id,
        contract_version=contract_version,
        registry_manifest_hash=root_hash,
        source_registry_hash=source_hash,
        mapping_registry_hash=mapping_hash,
        feature_registry_hash=feature_hash,
        effective_release_eligible=eligible,
        visible_candidates=[candidates[key] for key in sorted(candidates)],
        selected_fact_ids=sorted({wire["id"] for _, wire in selected}),
        quarter_ids=sorted(q.to_dict()["id"] for q in quarters.facts),
        derivation_version=_DERIVATION,
        issues=[issue_wires[key] for key in sorted(issue_wires)],
    )
    return FormalFeatureBundle(
        schema_version=1,
        contract_version=contract_version,
        security_id=security_id,
        as_of_utc=as_of_utc,
        template_id=template_id,
        registry_manifest_hash=root_hash,
        feature_registry_hash=feature_hash,
        input_hash=hashlib.sha256(_bytes(input_wire)).hexdigest(),
        values=tuple(output),
        history_endpoints=tuple(sorted({wire["period_end"] for _, wire in selected if wire["period_kind"] == "FY"})),
        comparable_quarter_keys=tuple(sorted({q.to_dict()["quarter_key"] for q in quarters.facts})),
        blockers=tuple(sorted(blockers)),
    )


__all__ = ["FormalFactVersionView", "FormalFactSelection", "FormalQuarterFact", "FormalQuarterDerivation", "FormalHistoryResult", "FormalFormulaResult", "select_visible_formal_facts", "derive_comparable_quarters", "require_formal_history", "evaluate_formula", "build_formal_feature_bundle"]
