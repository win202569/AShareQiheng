# Task 4 independent review package

Review range: `f121506..44b974a`.

Author scope is exactly `ashare_pipeline/formal_financial_features.py` and `tests/test_formal_financial_features.py`. The binding contract is `task-4-brief.md`; review against it, not merely against the tests. This is read-only: do not edit, stage, commit, fetch, or change data/state artifacts. Report only concrete Blocker/Important/Minor findings with reproduction path, or PASS. Re-run appropriate tests independently.

```diff
diff --git a/ashare_pipeline/formal_financial_features.py b/ashare_pipeline/formal_financial_features.py
new file mode 100644
index 0000000..ddeaa5e
--- /dev/null
+++ b/ashare_pipeline/formal_financial_features.py
@@ -0,0 +1,650 @@
+"""Deterministic point-in-time financial features, without scoring or I/O."""
+
+from __future__ import annotations
+
+from collections import defaultdict
+from dataclasses import dataclass
+from datetime import date, datetime, timezone
+import hashlib
+import json
+import math
+import re
+import weakref
+from typing import Iterable
+from zoneinfo import ZoneInfo
+
+from .formal_financial_schema import FormalFinancialFact, FormalFactIssue
+from .formal_feature_contract import (
+    FormalEvidenceRef, FormalFeatureBundle, FormalFeatureValue, FormulaNode,
+    SignedFormalFeatureRegistry,
+)
+from .formal_registry_manifest import FormalRegistryManifest
+from .formal_time import formal_version_sort_key, is_visible_at
+from .formal_universe import canonical_security_id
+
+
+_UNITS = frozenset({"CNY", "shares", "ratio", "CNY_per_share"})
+_ENDPOINTS = {"Q1": "03-31", "H1": "06-30", "Q3": "09-30", "FY": "12-31"}
+_DERIVATION = "formal-quarter-derivation-v1"
+_GROUP = ("security_id", "statement", "metric_key", "period_start", "period_end", "period_kind", "unit", "nature", "accounting_basis")
+_ROOT_HASHES = ("source_registry_hash", "mapping_registry_hash", "feature_registry_hash", "scoring_registry_hash", "industry_registry_hash", "cyclic_registry_hash", "redline_registry_hash", "status_registry_hash", "event_registry_hash")
+_ISSUES = frozenset({"required_source_field_missing", "duplicate_source_field", "nonnumeric_value", "invalid_row_shape", "unknown_source_field", "mapping_not_applicable"})
+
+
+def _bytes(value: object) -> bytes:
+    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
+
+
+def _json(value: object) -> object:
+    if value is None or type(value) in (str, bool, int):
+        return value
+    if type(value) is float and math.isfinite(value):
+        return value
+    if type(value) is list:
+        return [_json(item) for item in value]
+    if type(value) is dict and all(type(key) is str for key in value):
+        return {key: _json(item) for key, item in value.items()}
+    raise ValueError("wire must contain exact finite JSON-native types")
+
+
+def _text(value: object) -> str:
+    if type(value) is not str or not value or value.strip() != value or any(ord(c) < 32 or ord(c) == 127 for c in value):
+        raise ValueError("expected canonical nonempty text")
+    return value
+
+
+def _utc(value: object) -> str:
+    if type(value) is not str or not value.endswith("+00:00"):
+        raise ValueError("expected canonical UTC timestamp")
+    try:
+        parsed = datetime.fromisoformat(value)
+    except ValueError as error:
+        raise ValueError("expected canonical UTC timestamp") from error
+    if parsed.utcoffset() != timezone.utc.utcoffset(parsed) or parsed.isoformat() != value:
+        raise ValueError("expected canonical UTC timestamp")
+    return value
+
+
+def _date(value: object) -> str:
+    if type(value) is not str or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is None:
+        raise ValueError("expected canonical date")
+    if date.fromisoformat(value).isoformat() != value:
+        raise ValueError("expected canonical date")
+    return value
+
+
+def _hash(value: object) -> str:
+    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
+        raise ValueError("expected SHA-256")
+    return value
+
+
+def _security(value: object) -> str:
+    if type(value) is not str or canonical_security_id(value) != value:
+        raise ValueError("expected canonical security identity")
+    return value
+
+
+def _snapshot_facts(facts: Iterable[FormalFinancialFact]):
+    try:
+        supplied = tuple(facts)
+    except (TypeError, ValueError) as error:
+        raise ValueError("facts must be a finite iterable of formal facts") from error
+    result = []
+    for item in supplied:
+        if type(item) is not FormalFinancialFact:
+            raise ValueError("expected exact sealed FormalFinancialFact")
+        wire = item.to_dict()
+        for key in ("published_at_utc", "effective_at_utc", "captured_at_utc", "created_at_utc"):
+            _utc(wire[key])
+        if wire["source_updated_at_utc"] is not None:
+            _utc(wire["source_updated_at_utc"])
+        result.append((FormalFinancialFact.from_dict(wire), wire))
+    return tuple(result)
+
+
+def _visible(wire: dict, cutoff: str) -> bool:
+    return all(is_visible_at(wire[key], cutoff) for key in ("published_at_utc", "effective_at_utc", "source_updated_at_utc") if wire[key] is not None)
+
+
+def _group(wire: dict) -> tuple:
+    # None is the canonical instant start; text is used only as a sorting sentinel.
+    return tuple("" if wire[key] is None else wire[key] for key in _GROUP)
+
+
+@dataclass(frozen=True, slots=True)
+class FormalFactVersionView:
+    published_at_utc: str
+    source_updated_at_utc: str | None
+    captured_at_utc: str
+    content_hash: str
+
+    def __post_init__(self):
+        _utc(self.published_at_utc)
+        if self.source_updated_at_utc is not None:
+            _utc(self.source_updated_at_utc)
+        _utc(self.captured_at_utc)
+        _hash(self.content_hash)
+
+
+@dataclass(frozen=True, slots=True)
+class FormalFactSelection:
+    facts: tuple[FormalFinancialFact, ...]
+    blockers: tuple[str, ...]
+
+
+@dataclass(frozen=True, slots=True)
+class FormalQuarterDerivation:
+    facts: tuple[FormalQuarterFact, ...]
+    blockers: tuple[str, ...]
+
+
+@dataclass(frozen=True, slots=True)
+class FormalHistoryResult:
+    eligible: bool
+    annual_endpoints: tuple[str, ...]
+    blockers: tuple[str, ...]
+
+
+@dataclass(frozen=True, slots=True)
+class FormalFormulaResult:
+    value: float | None
+    unit: str | None
+    evidence: tuple[FormalEvidenceRef, ...]
+    time_reliability: float | None
+    missing_reason: str | None
+
+    def __post_init__(self):
+        if self.missing_reason is not None:
+            _text(self.missing_reason)
+            if self.value is not None or self.unit is not None or type(self.evidence) is not tuple or self.evidence or self.time_reliability is not None:
+                raise ValueError("missing formula result must not contain partial evidence")
+            return
+        if type(self.value) is not float or not math.isfinite(self.value):
+            raise ValueError("formula value must be a finite float")
+        if type(self.unit) is not str or self.unit not in _UNITS:
+            raise ValueError("formula unit is invalid")
+        if type(self.time_reliability) is not float or not math.isfinite(self.time_reliability) or not 0 <= self.time_reliability <= 1:
+            raise ValueError("formula reliability is invalid")
+        if type(self.evidence) is not tuple or not self.evidence:
+            raise ValueError("formula evidence is required")
+        ids = []
+        for ref in self.evidence:
+            if type(ref) is not FormalEvidenceRef:
+                raise ValueError("formula evidence must be exact")
+            ids.append(ref.to_dict()["formal_fact_id"])
+        if ids != sorted(set(ids)):
+            raise ValueError("formula evidence must be sorted and unique")
+
+
+def select_visible_formal_facts(facts: Iterable[FormalFinancialFact], as_of_utc: str) -> FormalFactSelection:
+    cutoff = _utc(as_of_utc)
+    groups = defaultdict(list)
+    for fact, wire in _snapshot_facts(facts):
+        if _visible(wire, cutoff):
+            groups[_group(wire)].append((fact, wire))
+    winners, blockers = [], set()
+    for key in sorted(groups):
+        candidates = groups[key]
+        if len({(wire["parser_id"], wire["parser_version"], wire["mapping_version"]) for _, wire in candidates}) != 1:
+            blockers.add("fact_mapping_version_conflict")
+            continue
+        ordered = []
+        for fact, wire in candidates:
+            view = FormalFactVersionView(wire["published_at_utc"], wire["source_updated_at_utc"], wire["captured_at_utc"], wire["source_content_sha256"])
+            ordered.append((formal_version_sort_key(view), _bytes(wire), fact))
+        best = min(item[0] for item in ordered)
+        tied = {wire: fact for sort, wire, fact in ordered if sort == best}
+        if len(tied) != 1:
+            blockers.add("fact_selection_tie_conflict")
+            continue
+        winners.append(next(iter(tied.values())))
+    return FormalFactSelection(tuple(winners), tuple(sorted(blockers)))
+
+
+def _evidence_union(refs: Iterable[FormalEvidenceRef]) -> tuple[FormalEvidenceRef, ...]:
+    by_id = {}
+    for ref in refs:
+        if type(ref) is not FormalEvidenceRef:
+            raise ValueError("expected exact evidence")
+        wire = ref.to_dict()
+        key = wire["formal_fact_id"]
+        if key in by_id and _bytes(by_id[key].to_dict()) != _bytes(wire):
+            raise ValueError("conflicting evidence for one formal fact")
+        by_id[key] = ref
+    return tuple(by_id[key] for key in sorted(by_id))
+
+
+def _make_quarter_type():
+    fields = ("id", "security_id", "statement", "metric_key", "quarter_end", "quarter_key", "value", "unit", "nature", "accounting_basis", "mapping_version", "component_fact_ids", "evidence", "derivation_version")
+    records = {}
+
+    def validate_wire(value):
+        wire = _json(value)
+        if type(wire) is not dict or set(wire) != set(fields):
+            raise ValueError("quarter wire has invalid fields")
+        _hash(wire["id"])
+        _security(wire["security_id"])
+        for field in ("statement", "metric_key", "accounting_basis", "mapping_version"):
+            _text(wire[field])
+        for field in ("metric_key", "mapping_version"):
+            if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]*", wire[field]) is None:
+                raise ValueError("quarter metric/mapping identifiers must be canonical")
+        if wire["statement"] not in {"income", "balance", "cash_flow"}:
+            raise ValueError("invalid quarter statement")
+        if type(wire["nature"]) is not str or type(wire["unit"]) is not str or wire["nature"] not in {"duration", "instant"} or wire["unit"] not in _UNITS:
+            raise ValueError("invalid quarter unit/nature")
+        if (wire["statement"] == "balance") != (wire["nature"] == "instant"):
+            raise ValueError("quarter statement/nature mismatch")
+        end = _date(wire["quarter_end"])
+        key = wire["quarter_key"]
+        if type(key) is not str or re.fullmatch(r"[0-9]{4}Q[1-4]", key) is None:
+            raise ValueError("invalid global quarter key")
+        if end != key[:4] + "-" + tuple(_ENDPOINTS.values())[int(key[-1]) - 1]:
+            raise ValueError("quarter key/end mismatch")
+        number = wire["value"]
+        if type(number) is not float or not math.isfinite(number) or (number == 0 and math.copysign(1, number) < 0):
+            raise ValueError("quarter value must be canonical finite float")
+        ids = wire["component_fact_ids"]
+        if type(ids) is not list or not ids or any(type(item) is not str for item in ids):
+            raise ValueError("quarter requires operand IDs")
+        for item in ids:
+            _hash(item)
+        if ids != sorted(set(ids)):
+            raise ValueError("quarter operand IDs must be sorted/unique")
+        expected_operands = 1 if wire["nature"] == "instant" or key.endswith("Q1") else 2
+        if len(ids) != expected_operands or wire["derivation_version"] != _DERIVATION:
+            raise ValueError("quarter derivation shape is invalid")
+        if type(wire["evidence"]) is not list:
+            raise ValueError("quarter evidence must be JSON array")
+        refs = tuple(FormalEvidenceRef.from_dict(item) for item in wire["evidence"])
+        if [ref.to_dict()["formal_fact_id"] for ref in refs] != ids:
+            raise ValueError("quarter evidence must exactly cover operands")
+        if any(ref.to_dict()["mapping_version"] != wire["mapping_version"] for ref in refs):
+            raise ValueError("quarter evidence mapping mismatch")
+        payload = {key: item for key, item in wire.items() if key not in {"id", "evidence"}}
+        payload["schema_version"] = "formal-quarter-fact-v1"
+        if hashlib.sha256(_bytes(payload)).hexdigest() != wire["id"]:
+            raise ValueError("quarter identity mismatch")
+        return wire, refs
+
+    def construct(wire):
+        wire, refs = validate_wire(wire)
+        item = object.__new__(FormalQuarterFact)
+        for key, value in wire.items():
+            object.__setattr__(item, key, refs if key == "evidence" else tuple(value) if key == "component_fact_ids" else value)
+        identity = id(item)
+        records[identity] = (weakref.ref(item, lambda _, identity=identity: records.pop(identity, None)), _bytes(wire))
+        return item
+
+    @dataclass(frozen=True, slots=True, weakref_slot=True, init=False)
+    class FormalQuarterFact:
+        id: str
+        security_id: str
+        statement: str
+        metric_key: str
+        quarter_end: str
+        quarter_key: str
+        value: float
+        unit: str
+        nature: str
+        accounting_basis: str
+        mapping_version: str
+        component_fact_ids: tuple[str, ...]
+        evidence: tuple[FormalEvidenceRef, ...]
+        derivation_version: str
+
+        def __init__(self, *args, **kwargs):
+            raise TypeError("quarters must be derived or loaded from canonical wire")
+
+        def to_dict(self):
+            if type(self) is not FormalQuarterFact:
+                raise ValueError("quarter must have exact type")
+            record = records.get(id(self))
+            if record is None or record[0]() is not self:
+                raise ValueError("quarter has no trusted provenance")
+            wire = {}
+            for key in fields:
+                try:
+                    value = getattr(self, key)
+                except AttributeError as error:
+                    raise ValueError("quarter is incomplete") from error
+                if key in {"component_fact_ids", "evidence"}:
+                    if type(value) is not tuple:
+                        raise ValueError("quarter collections must be exact tuples")
+                    if key == "evidence":
+                        if any(type(ref) is not FormalEvidenceRef for ref in value):
+                            raise ValueError("quarter evidence must have exact type")
+                        value = [ref.to_dict() for ref in value]
+                    else:
+                        value = list(value)
+                wire[key] = value
+            validated, _ = validate_wire(wire)
+            if _bytes(validated) != record[1]:
+                raise ValueError("quarter was mutated")
+            return validated
+
+        @classmethod
+        def from_dict(cls, value):
+            if cls is not FormalQuarterFact:
+                raise ValueError("quarter must have exact type")
+            try:
+                return construct(value)
+            except (RecursionError, TypeError, AttributeError) as error:
+                raise ValueError("quarter wire is malformed or too deep") from error
+
+    return FormalQuarterFact, construct
+
+
+FormalQuarterFact, _construct_quarter = _make_quarter_type()
+del _make_quarter_type
+
+
+def _make_deriver(construct_quarter):
+    def derive_comparable_quarters(facts: Iterable[FormalFinancialFact]) -> FormalQuarterDerivation:
+        families = defaultdict(list)
+        for fact, wire in _snapshot_facts(facts):
+            family = tuple(wire[key] for key in ("security_id", "statement", "metric_key", "unit", "nature")) + (wire["period_end"][:4],)
+            families[family].append((fact, wire))
+        output, blockers = [], set()
+        for family in sorted(families):
+            candidates = families[family]
+            invalid = False
+            for fields, reason in ((("accounting_basis",), "quarter_accounting_basis_mismatch"), (("parser_id", "parser_version"), "quarter_parser_version_mismatch"), (("mapping_version",), "quarter_mapping_version_mismatch")):
+                if len({tuple(wire[key] for key in fields) for _, wire in candidates}) != 1:
+                    blockers.add(reason)
+                    invalid = True
+            periods = {}
+            for fact, wire in candidates:
+                kind, year = wire["period_kind"], family[-1]
+                if kind not in _ENDPOINTS or wire["period_end"] != year + "-" + _ENDPOINTS[kind] or (wire["nature"] == "duration" and wire["period_start"] != year + "-01-01"):
+                    blockers.add("quarter_invalid_period")
+                    invalid = True
+                if kind in periods:
+                    blockers.add("quarter_duplicate_period")
+                    invalid = True
+                periods[kind] = (fact, wire)
+            if invalid:
+                continue
+            for index, kind in enumerate(_ENDPOINTS):
+                if kind not in periods:
+                    continue
+                fact, wire = periods[kind]
+                operands = [(fact, wire)]
+                value = wire["value"]
+                if wire["nature"] == "duration" and index:
+                    previous = tuple(_ENDPOINTS)[index - 1]
+                    if previous not in periods:
+                        blockers.add("quarter_missing_prerequisite")
+                        continue
+                    operands.append(periods[previous])
+                    value -= operands[-1][1]["value"]
+                if not math.isfinite(value):
+                    blockers.add("quarter_nonfinite_derivation")
+                    continue
+                evidence = _evidence_union(FormalEvidenceRef.from_formal_fact(item) for item, _ in operands)
+                result = {key: wire[key] for key in ("security_id", "statement", "metric_key", "unit", "nature", "accounting_basis", "mapping_version")}
+                result.update(quarter_end=wire["period_end"], quarter_key=family[-1] + f"Q{index + 1}", value=0.0 if value == 0 else float(value), component_fact_ids=sorted(item["id"] for _, item in operands), derivation_version=_DERIVATION)
+                result["id"] = hashlib.sha256(_bytes({"schema_version": "formal-quarter-fact-v1", **result})).hexdigest()
+                result["evidence"] = [ref.to_dict() for ref in evidence]
+                output.append(construct_quarter(result))
+        output.sort(key=lambda q: tuple(q.to_dict()[key] for key in ("security_id", "statement", "metric_key", "quarter_end", "unit", "nature", "accounting_basis", "mapping_version", "id")))
+        return FormalQuarterDerivation(tuple(output), tuple(sorted(blockers)))
+    return derive_comparable_quarters
+
+
+derive_comparable_quarters = _make_deriver(_construct_quarter)
+del _make_deriver, _construct_quarter
+
+
+def require_formal_history(annual_endpoints, *, comparable_quarter_keys, as_of_utc: str, cyclic: bool) -> FormalHistoryResult:
+    cutoff = datetime.fromisoformat(_utc(as_of_utc)).astimezone(ZoneInfo("Asia/Shanghai")).date()
+    if type(cyclic) is not bool:
+        raise ValueError("cyclic must be an exact bool supplied by verified policy")
+    count = 5 if cyclic else 4
+    latest_year = cutoff.year if (cutoff.month, cutoff.day) == (12, 31) else cutoff.year - 1
+    required = tuple(f"{year:04d}-12-31" for year in range(latest_year - count + 1, latest_year + 1))
+    quarter_ends = ("03-31", "06-30", "09-30", "12-31")
+    ended = sum(f"{cutoff.year:04d}-{end}" <= cutoff.isoformat() for end in quarter_ends)
+    latest_index = cutoff.year * 4 + ended - 1
+    expected_quarters = tuple(f"{index // 4:04d}Q{index % 4 + 1}" for index in range(latest_index - 7, latest_index + 1))
+    blockers = set()
+    try:
+        annuals = tuple(annual_endpoints)
+        quarters = tuple(comparable_quarter_keys)
+        for endpoint in annuals:
+            if not _date(endpoint).endswith("-12-31"):
+                raise ValueError("annual endpoints must end at year close")
+        if annuals != tuple(sorted(set(annuals))) or any(endpoint > cutoff.isoformat() for endpoint in annuals):
+            raise ValueError("annual endpoints must be sorted unique and not future")
+        if any(type(key) is not str or re.fullmatch(r"[0-9]{4}Q[1-4]", key) is None for key in quarters):
+            raise ValueError("invalid quarter keys")
+        if not set(required).issubset(annuals):
+            blockers.add("history_annual_window_incomplete")
+        if quarters != expected_quarters:
+            blockers.add("history_quarter_window_incomplete")
+    except (TypeError, ValueError):
+        blockers.add("history_invalid_input")
+    if blockers:
+        blockers.add("pending_evidence/history_not_mature")
+        return FormalHistoryResult(False, (), tuple(sorted(blockers)))
+    return FormalHistoryResult(True, required, ())
+
+
+def _missing(reason: str) -> FormalFormulaResult:
+    return FormalFormulaResult(None, None, (), None, reason)
+
+
+def _formula_snapshot(node):
+    if type(node) is not FormulaNode:
+        raise ValueError("formula must have exact type")
+    try:
+        return FormulaNode.from_dict(node.to_dict())
+    except (RecursionError, AttributeError, TypeError) as error:
+        raise ValueError("formula is malformed or too deep") from error
+
+
+def _formula_fact(item):
+    if type(item) is FormalFinancialFact:
+        _, wire = _snapshot_facts((item,))[0]
+        if wire["period_kind"] != "FY" or wire["period_end"] != wire["period_end"][:4] + "-12-31":
+            raise ValueError("only raw FY facts belong in the formula namespace")
+        key = (wire["metric_key"], "FY" + wire["period_end"][:4])
+        refs = (FormalEvidenceRef.from_formal_fact(item),)
+    elif type(item) is FormalQuarterFact:
+        wire = item.to_dict()
+        key = (wire["metric_key"], wire["quarter_key"])
+        refs = tuple(FormalEvidenceRef.from_dict(ref) for ref in wire["evidence"])
+    else:
+        raise ValueError("formula fact must have exact sealed type")
+    reliability = min(1.0 if ref.to_dict()["published_precision"] == "timestamp" else .8 for ref in refs)
+    return key, wire["security_id"], FormalFormulaResult(wire["value"], wire["unit"], refs, reliability, None)
+
+
+def _evaluate(node, values, ambiguous=frozenset()):
+    if node.op == "fact":
+        key = (node.fact_key, node.period_key)
+        if key in ambiguous:
+            return _missing("formula_fact_ambiguous")
+        return values.get(key, _missing("formula_fact_missing"))
+    children = [_evaluate(child, values, ambiguous) for child in (node.items if node.op in {"median", "minimum"} else (node.left, node.right))]
+    failed = sorted({child.missing_reason for child in children if child.missing_reason is not None})
+    if failed:
+        return _missing(failed[0])
+    numbers = [child.value for child in children]
+    units = [child.unit for child in children]
+    unit = units[0]
+    if node.op == "divide":
+        if units[0] == units[1]:
+            unit = "ratio"
+        elif units == ["CNY", "shares"]:
+            unit = "CNY_per_share"
+        else:
+            return _missing("formula_unit_mismatch")
+    elif any(other != unit for other in units):
+        return _missing("formula_unit_mismatch")
+    try:
+        if node.op == "add":
+            number = numbers[0] + numbers[1]
+        elif node.op == "subtract":
+            number = numbers[0] - numbers[1]
+        elif node.op == "divide":
+            if numbers[1] == 0:
+                return _missing("formula_zero_denominator")
+            number = numbers[0] / numbers[1]
+        elif node.op == "cagr":
+            if numbers[0] <= 0 or numbers[1] <= 0:
+                return _missing("formula_nonpositive_cagr")
+            number = (numbers[1] / numbers[0]) ** (1 / node.intervals) - 1
+            unit = "ratio"
+        elif node.op == "minimum":
+            number = min(numbers)
+        else:
+            ordered = sorted(numbers)
+            half = len(ordered) // 2
+            number = ordered[half] if len(ordered) % 2 else (ordered[half - 1] + ordered[half]) / 2
+        if not math.isfinite(number):
+            return _missing("formula_nonfinite_result")
+    except (ArithmeticError, ValueError):
+        return _missing("formula_nonfinite_result")
+    evidence = _evidence_union(ref for child in children for ref in child.evidence)
+    return FormalFormulaResult(0.0 if number == 0 else float(number), unit, evidence, min(child.time_reliability for child in children), None)
+
+
+def evaluate_formula(node: FormulaNode, facts: dict) -> FormalFormulaResult:
+    snapshot = _formula_snapshot(node)
+    if type(facts) is not dict:
+        raise ValueError("formula facts must be an exact dict")
+    values, securities = {}, set()
+    for key, item in tuple(facts.items()):
+        if type(key) is not tuple or len(key) != 2 or any(type(part) is not str for part in key):
+            raise ValueError("formula fact keys must be exact string pairs")
+        identity, security, result = _formula_fact(item)
+        if key != identity:
+            raise ValueError("formula map key does not match fact identity")
+        values[key] = result
+        securities.add(security)
+    if len(securities) > 1:
+        raise ValueError("formula facts cannot mix securities")
+    try:
+        return _evaluate(snapshot, values)
+    except RecursionError as error:
+        raise ValueError("formula is too deep") from error
+
+
+def build_formal_feature_bundle(*, security_id: str, as_of_utc: str, template_id: str, facts: Iterable[FormalFinancialFact], issues: Iterable[FormalFactIssue], registry: SignedFormalFeatureRegistry, registry_manifest: FormalRegistryManifest) -> FormalFeatureBundle:
+    _security(security_id)
+    _utc(as_of_utc)
+    if type(template_id) is not str or template_id not in {"bank", "broker", "general_nonfinancial", "insurance", "real_estate"}:
+        raise ValueError("invalid formal template")
+    raw = _snapshot_facts(facts)
+    if any(wire["security_id"] != security_id for _, wire in raw):
+        raise ValueError("bundle facts must match security")
+    if type(registry) is not SignedFormalFeatureRegistry:
+        raise ValueError("bundle requires exact signed registry")
+    slots = registry.slots_for_template(template_id)
+    if type(registry_manifest) is not FormalRegistryManifest:
+        raise ValueError("bundle requires exact sealed root")
+    try:
+        hashes = {key: getattr(registry_manifest, key) for key in _ROOT_HASHES}
+        registry_manifest.assert_member_hashes(**hashes)
+    except (AttributeError, TypeError) as error:
+        raise ValueError("invalid root manifest") from error
+    for root_key, child_key in (("source_registry_hash", "source_registry_hash"), ("mapping_registry_hash", "mapping_registry_hash"), ("feature_registry_hash", "registry_hash")):
+        if hashes[root_key] != getattr(registry, child_key):
+            raise ValueError("root-child registry hash mismatch")
+    official = True
+    try:
+        registry_manifest.require_official()
+    except ValueError:
+        official = False
+    # All provenance used below is detached before iterating caller-supplied issues.
+    eligible = official and registry.release_eligible
+    contract_version = registry.contract_version
+    feature_hash = registry.registry_hash
+    source_hash = registry.source_registry_hash
+    mapping_hash = registry.mapping_registry_hash
+    root_hash = registry_manifest.manifest_hash
+    try:
+        supplied_issues = tuple(issues)
+    except TypeError as error:
+        raise ValueError("issues must be iterable") from error
+    issue_wires, blockers = {}, set()
+    for issue in supplied_issues:
+        if type(issue) is not FormalFactIssue:
+            raise ValueError("issues must have exact sealed type")
+        wire = issue.to_dict()
+        if type(wire["code"]) is not str or wire["code"] not in _ISSUES:
+            raise ValueError("issue code is not an extraction issue")
+        issue_wires[_bytes(wire)] = wire
+        blockers.add("formal_fact_issue_" + wire["code"])
+    selection = select_visible_formal_facts((item for item, _ in raw), as_of_utc)
+    blockers.update(selection.blockers)
+    untrustworthy = bool(blockers)
+    quarters = derive_comparable_quarters(selection.facts)
+    blockers.update(quarters.blockers)
+    values, ambiguous, identities = {}, set(), {}
+    selected = _snapshot_facts(selection.facts)
+    formula_inputs = [item for item, wire in selected if wire["period_kind"] == "FY"] + list(quarters.facts)
+    for item in formula_inputs:
+        key, _, result = _formula_fact(item)
+        wire = item.to_dict()
+        if key in identities and identities[key] != _bytes(wire):
+            ambiguous.add(key)
+        identities[key] = _bytes(wire)
+        if key not in values:
+            values[key] = result
+    output = []
+    if not eligible:
+        blockers.add("feature_registry_not_release_eligible")
+    for slot in slots:
+        slot_wire = slot.to_dict()
+        if not eligible or untrustworthy:
+            reason = "feature_registry_not_release_eligible" if not eligible else "feature_input_not_trustworthy"
+            status, result = "blocked", _missing(reason)
+        else:
+            result = _evaluate(_formula_snapshot(slot.formula), values, ambiguous)
+            if result.missing_reason is None and result.unit != slot_wire["unit"]:
+                result = _missing("formula_unit_mismatch")
+            status = "derived" if result.missing_reason is None else "missing"
+            if status == "missing" and slot_wire["required"]:
+                blockers.add("feature_required_slot_missing")
+        output.append(FormalFeatureValue(slot_wire["slot_id"], result.value, slot_wire["unit"], status, slot_wire["formula_version"], result.evidence, result.missing_reason))
+    candidates = {}
+    for _, wire in raw:
+        if _visible(wire, as_of_utc):
+            record = {key: wire[key] for key in ("id", "source_snapshot_id", "source_content_sha256", "source_refresh_generation")}
+            candidates[_bytes(record)] = record
+    input_wire = dict(
+        schema_version="formal-feature-input-v1",
+        security_id=security_id,
+        as_of_utc=as_of_utc,
+        template_id=template_id,
+        contract_version=contract_version,
+        registry_manifest_hash=root_hash,
+        source_registry_hash=source_hash,
+        mapping_registry_hash=mapping_hash,
+        feature_registry_hash=feature_hash,
+        visible_candidates=[candidates[key] for key in sorted(candidates)],
+        selected_fact_ids=sorted({wire["id"] for _, wire in selected}),
+        quarter_ids=sorted(q.to_dict()["id"] for q in quarters.facts),
+        derivation_version=_DERIVATION,
+        issues=[issue_wires[key] for key in sorted(issue_wires)],
+    )
+    return FormalFeatureBundle(
+        schema_version=1,
+        contract_version=contract_version,
+        security_id=security_id,
+        as_of_utc=as_of_utc,
+        template_id=template_id,
+        registry_manifest_hash=root_hash,
+        feature_registry_hash=feature_hash,
+        input_hash=hashlib.sha256(_bytes(input_wire)).hexdigest(),
+        values=tuple(output),
+        history_endpoints=tuple(sorted({wire["period_end"] for _, wire in selected if wire["period_kind"] == "FY"})),
+        comparable_quarter_keys=tuple(sorted({q.to_dict()["quarter_key"] for q in quarters.facts})),
+        blockers=tuple(sorted(blockers)),
+    )
+
+
+__all__ = ["FormalFactVersionView", "FormalFactSelection", "FormalQuarterFact", "FormalQuarterDerivation", "FormalHistoryResult", "FormalFormulaResult", "select_visible_formal_facts", "derive_comparable_quarters", "require_formal_history", "evaluate_formula", "build_formal_feature_bundle"]
diff --git a/tests/test_formal_financial_features.py b/tests/test_formal_financial_features.py
new file mode 100644
index 0000000..bdd4a57
--- /dev/null
+++ b/tests/test_formal_financial_features.py
@@ -0,0 +1,406 @@
+"""Point-in-time financial derivation regression and hostile-boundary tests."""
+import hashlib
+import itertools
+import math
+import unittest
+from collections import UserDict
+
+from ashare_pipeline.formal_financial_schema import FormalFinancialFact, FormalFactIssue
+from ashare_pipeline.formal_feature_contract import FormulaNode, SignedFormalFeatureRegistry
+from ashare_pipeline.formal_registry_manifest import FormalRegistryManifest
+from ashare_pipeline.formal_financial_features import (
+    FormalQuarterFact, select_visible_formal_facts, derive_comparable_quarters,
+    require_formal_history, evaluate_formula, build_formal_feature_bundle,
+)
+from tests.test_formal_feature_contract import (
+    formal_fact, canonical_bytes, feature_registry_bytes, registry_manifest,
+    load_registry, slot_wire, TEMPLATES,
+)
+
+CUTOFF = "2026-08-31T07:00:00+00:00"
+WINDOW = ("2024Q3", "2024Q4", "2025Q1", "2025Q2", "2025Q3", "2025Q4", "2026Q1", "2026Q2")
+ANNUALS = tuple(f"{year}-12-31" for year in range(2022, 2026))
+
+
+def fact(kind="FY", value=100.0, year=2025, **changes):
+    end = {"Q1": "03-31", "H1": "06-30", "Q3": "09-30", "FY": "12-31", "OTHER": "05-31"}[kind]
+    values = dict(period_start=None if kind == "OTHER" else f"{year}-01-01", period_end=f"{year}-{end}", period_kind=kind, value=value)
+    values.update(changes)
+    return formal_fact(**values)
+
+
+def leaf(metric="revenue", period="FY2025"):
+    return FormulaNode(op="fact", fact_key=metric, period_key=period)
+
+
+def bundle(facts=(), *, purpose="official", slots=None, issues=(), **changes):
+    if slots is None:
+        slots = [slot_wire("general_nonfinancial", unit="CNY", formula=leaf().to_dict())]
+    all_slots = slots + [slot_wire(template) for template in TEMPLATES if template != "general_nonfinancial"]
+    raw = feature_registry_bytes(slots=sorted(all_slots, key=lambda slot: slot["slot_id"]))
+    root = registry_manifest(raw, purpose=purpose)
+    values = dict(security_id="SH600001", as_of_utc=CUTOFF, template_id="general_nonfinancial", facts=facts, issues=issues, registry=load_registry(raw, root), registry_manifest=root)
+    values.update(changes)
+    return build_formal_feature_bundle(**values)
+
+
+class SelectionTests(unittest.TestCase):
+    def test_generator_mutation_rejected_and_selection_detached(self):
+        original = fact()
+        result = select_visible_formal_facts([original], CUTOFF)
+        self.assertIsNot(original, result.facts[0])
+        object.__setattr__(original, "value", 999.0)
+        self.assertEqual(result.facts[0].to_dict()["value"], 100.0)
+        original = fact()
+        def hostile():
+            yield original
+            object.__setattr__(original, "value", 999.0)
+            yield fact(metric_key="profit")
+        with self.assertRaises(ValueError):
+            select_visible_formal_facts(hostile(), CUTOFF)
+
+    def test_date_only_effective_cutoff_and_future_conflict_exclusion(self):
+        delayed = fact(published_precision="date_only", published_at_utc="2026-08-31T00:00:00+00:00", effective_at_utc="2026-09-01T07:00:00+00:00", effective_time_evidence_hash="c" * 64, source_updated_at_utc=None)
+        self.assertEqual(select_visible_formal_facts([delayed], CUTOFF).facts, ())
+        old = fact()
+        future_parser = fact(parser_version="future", source_updated_at_utc="2026-09-01T00:00:00+00:00")
+        result = select_visible_formal_facts([old, future_parser], CUTOFF)
+        self.assertEqual(result.facts, (old,))
+        self.assertEqual(result.blockers, ())
+
+    def test_tied_lineage_not_only_fact_id_and_low_level_forgery(self):
+        original = fact()
+        later_created = fact(created_at_utc="2026-09-05T00:00:00+00:00")
+        self.assertEqual(original.id, later_created.id)
+        self.assertIn("fact_selection_tie_conflict", select_visible_formal_facts([original, later_created], CUTOFF).blockers)
+        forged = object.__new__(FormalFinancialFact)
+        for key, value in original.to_dict().items():
+            object.__setattr__(forged, key, value)
+        for consumer in (lambda: select_visible_formal_facts([forged], CUTOFF), lambda: derive_comparable_quarters([forged]), lambda: evaluate_formula(leaf(), {("revenue", "FY2025"): forged}), lambda: bundle([forged])):
+            with self.assertRaises(ValueError):
+                consumer()
+
+    def test_cutoff_revision_capture_and_equality(self):
+        at = fact(published_at_utc=CUTOFF, effective_at_utc=CUTOFF, source_updated_at_utc=CUTOFF)
+        future = fact(value=999.0, source_updated_at_utc="2026-08-31T07:00:01+00:00")
+        self.assertEqual(select_visible_formal_facts([future, at], CUTOFF).facts, (at,))
+        self.assertGreater(at.captured_at_utc, CUTOFF)
+        later = fact(published_at_utc="2026-08-31T07:00:01+00:00", effective_at_utc="2026-08-31T07:00:01+00:00", source_updated_at_utc=None)
+        self.assertEqual(select_visible_formal_facts([later], CUTOFF).facts, ())
+
+    def test_every_version_level_and_permutations(self):
+        base = fact(source_updated_at_utc=None)
+        updated = fact(source_updated_at_utc="2026-03-20T08:30:00+00:00")
+        captured = fact(captured_at_utc="2026-09-05T00:00:00+00:00")
+        hashed = fact(captured_at_utc="2026-09-05T00:00:00+00:00", source_content_sha256="0" * 64)
+        published = fact(published_at_utc="2026-03-21T08:00:00+00:00", effective_at_utc="2026-03-21T08:00:00+00:00", source_updated_at_utc=None)
+        for candidates, winner in (([base, updated], updated), ([updated, captured], captured), ([captured, hashed], hashed), ([hashed, published], published)):
+            for order in itertools.permutations(candidates):
+                self.assertEqual(select_visible_formal_facts(order, CUTOFF).facts, (winner,))
+
+    def test_mapping_conflicts_tie_and_duplicate(self):
+        original = fact()
+        for field in ("parser_id", "parser_version", "mapping_version"):
+            result = select_visible_formal_facts([original, fact(**{field: "other"})], CUTOFF)
+            self.assertEqual(result.facts, ())
+            self.assertIn("fact_mapping_version_conflict", result.blockers)
+        result = select_visible_formal_facts([original, fact(value=101.0), fact(metric_key="profit")], CUTOFF)
+        self.assertEqual(len(result.facts), 1)
+        self.assertIn("fact_selection_tie_conflict", result.blockers)
+        self.assertEqual(select_visible_formal_facts([original, original], CUTOFF).facts, (original,))
+
+    def test_untrusted_inputs_and_noncanonical_time(self):
+        for value in (object(), {}, 1):
+            with self.assertRaises(ValueError):
+                select_visible_formal_facts([value], CUTOFF)
+        mutated = fact()
+        object.__setattr__(mutated, "value", 1.0)
+        with self.assertRaises(ValueError):
+            select_visible_formal_facts([mutated], CUTOFF)
+        for cutoff in (CUTOFF.replace("+00:00", "Z"), "2026-08-31T15:00:00+08:00", 1):
+            with self.assertRaises(ValueError):
+                select_visible_formal_facts([], cutoff)
+
+
+class QuarterTests(unittest.TestCase):
+    def test_missing_h1_preserves_q4_and_year_unit_isolation(self):
+        result = derive_comparable_quarters([fact("Q1", 10), fact("Q3", 45), fact("FY", 70)])
+        self.assertEqual([(q.quarter_key, q.value) for q in result.facts], [("2025Q1", 10), ("2025Q4", 25)])
+        self.assertIn("quarter_missing_prerequisite", result.blockers)
+        units = derive_comparable_quarters([fact("Q1", unit="CNY"), fact("H1", unit="shares")])
+        self.assertEqual(len(units.facts), 1)
+        self.assertIn("quarter_missing_prerequisite", units.blockers)
+        years = derive_comparable_quarters([fact("Q1", year=2024), fact("H1", year=2025)])
+        self.assertEqual([q.quarter_key for q in years.facts], ["2024Q1"])
+
+    def test_quarter_identity_changes_and_order_is_stable(self):
+        raw = [fact("Q1", 10), fact("H1", 30)]
+        baseline = derive_comparable_quarters(raw)
+        self.assertEqual([q.to_dict() for q in baseline.facts], [q.to_dict() for q in derive_comparable_quarters(raw[::-1]).facts])
+        revised = derive_comparable_quarters([raw[0], fact("H1", 30, source_refresh_generation="revision")])
+        self.assertNotEqual(baseline.facts[1].id, revised.facts[1].id)
+        cash = derive_comparable_quarters([fact("Q1", statement="cash_flow")])
+        self.assertEqual(cash.facts[0].statement, "cash_flow")
+
+    def test_quarter_zero_and_exact_wire_boundaries(self):
+        q = derive_comparable_quarters([fact("Q1", 0)]).facts[0]
+        wire = q.to_dict()
+        for change in ({"value": -0.0}, {"value": False}, {"nature": []}, {"unit": []}, {"component_fact_ids": tuple(wire["component_fact_ids"])}, {"evidence": [{**wire["evidence"][0], "mapping_version": "different"}]}):
+            with self.assertRaises(ValueError):
+                FormalQuarterFact.from_dict({**wire, **change})
+        self.assertEqual(math.copysign(1, q.value), 1)
+        cycle = {}
+        cycle["nested"] = cycle
+        with self.assertRaises(ValueError):
+            FormalQuarterFact.from_dict(cycle)
+
+    def test_duration_instant_and_full_evidence(self):
+        raw = [fact(kind, value) for kind, value in zip(("Q1", "H1", "Q3", "FY"), (10, 30, 45, 70))]
+        result = derive_comparable_quarters(raw)
+        self.assertEqual([q.value for q in result.facts], [10, 20, 15, 25])
+        self.assertEqual([q.quarter_key for q in result.facts], [f"2025Q{i}" for i in range(1, 5)])
+        self.assertEqual(result.facts[1].component_fact_ids, tuple(sorted([raw[0].id, raw[1].id])))
+        self.assertEqual(tuple(e.formal_fact_id for e in result.facts[1].evidence), result.facts[1].component_fact_ids)
+        instant = [fact(kind, value, statement="balance", nature="instant", period_start=None) for kind, value in zip(("Q1", "H1", "Q3", "FY"), (10, 30, 45, 70))]
+        self.assertEqual([q.value for q in derive_comparable_quarters(instant).facts], [10, 30, 45, 70])
+
+    def test_mismatches_duplicate_other_missing_and_negative(self):
+        for field, reason in (("accounting_basis", "quarter_accounting_basis_mismatch"), ("parser_id", "quarter_parser_version_mismatch"), ("parser_version", "quarter_parser_version_mismatch"), ("mapping_version", "quarter_mapping_version_mismatch")):
+            changed = "separate" if field == "accounting_basis" else "different"
+            result = derive_comparable_quarters([fact("Q1"), fact("H1", **{field: changed})])
+            self.assertEqual(result.facts, ())
+            self.assertIn(reason, result.blockers)
+        for raw, reason in (([fact("Q1"), fact("Q1")], "quarter_duplicate_period"), ([fact("OTHER")], "quarter_invalid_period"), ([fact("H1")], "quarter_missing_prerequisite")):
+            result = derive_comparable_quarters(raw)
+            self.assertEqual(result.facts, ())
+            self.assertIn(reason, result.blockers)
+        result = derive_comparable_quarters([fact("Q1", 30), fact("H1", 10)])
+        self.assertEqual(result.facts[1].value, -20.0)
+        huge = derive_comparable_quarters([fact("Q1", -1e308), fact("H1", 1e308)])
+        self.assertIn("quarter_nonfinite_derivation", huge.blockers)
+
+    def test_roundtrip_identity_and_forgery(self):
+        q = derive_comparable_quarters([fact("Q1")]).facts[0]
+        wire = q.to_dict()
+        self.assertEqual(FormalQuarterFact.from_dict(wire).to_dict(), wire)
+        identity = {k: v for k, v in wire.items() if k not in {"id", "evidence"}}
+        identity["schema_version"] = "formal-quarter-fact-v1"
+        self.assertEqual(q.id, hashlib.sha256(canonical_bytes(identity)).hexdigest())
+        with self.assertRaises(TypeError):
+            FormalQuarterFact()
+        forged = object.__new__(FormalQuarterFact)
+        for key in wire:
+            object.__setattr__(forged, key, getattr(q, key))
+        with self.assertRaises(ValueError):
+            forged.to_dict()
+        for changed in ({"value": 100}, {"id": "0" * 64}, {"quarter_key": "Q1"}, {"evidence": []}):
+            with self.assertRaises(ValueError):
+                FormalQuarterFact.from_dict({**wire, **changed})
+        object.__setattr__(q, "value", 101.0)
+        with self.assertRaises(ValueError):
+            q.to_dict()
+
+
+class HistoryTests(unittest.TestCase):
+    def test_shanghai_date_boundary_and_extra_history(self):
+        result = require_formal_history(("2020-12-31", "2021-12-31") + ANNUALS, comparable_quarter_keys=WINDOW, as_of_utc=CUTOFF, cyclic=False)
+        self.assertEqual(result.annual_endpoints, ANNUALS)
+        at_quarter_end = require_formal_history(ANNUALS, comparable_quarter_keys=WINDOW[1:] + ("2026Q3",), as_of_utc="2026-09-29T16:00:00+00:00", cyclic=False)
+        self.assertTrue(at_quarter_end.eligible)
+        for quarters in (WINDOW + WINDOW[-1:], WINDOW[::-1], ("2024Q0",) + WINDOW[1:], (1,) + WINDOW[1:]):
+            self.assertFalse(require_formal_history(ANNUALS, comparable_quarter_keys=quarters, as_of_utc=CUTOFF, cyclic=False).eligible)
+
+    def test_current_four_and_five_year_windows(self):
+        self.assertTrue(require_formal_history(ANNUALS, comparable_quarter_keys=WINDOW, as_of_utc=CUTOFF, cyclic=False).eligible)
+        self.assertFalse(require_formal_history(ANNUALS, comparable_quarter_keys=WINDOW, as_of_utc=CUTOFF, cyclic=True).eligible)
+        self.assertTrue(require_formal_history(("2021-12-31",) + ANNUALS, comparable_quarter_keys=WINDOW, as_of_utc=CUTOFF, cyclic=True).eligible)
+        for annuals, quarters in ((ANNUALS[::-1], WINDOW), (ANNUALS + ANNUALS[-1:], WINDOW), (ANNUALS, WINDOW[:-1]), (ANNUALS, ("2024Q2",) + WINDOW[:-1]), (ANNUALS + ("2026-12-31",), WINDOW), (("invalid",), WINDOW)):
+            result = require_formal_history(annuals, comparable_quarter_keys=quarters, as_of_utc=CUTOFF, cyclic=False)
+            self.assertFalse(result.eligible)
+            self.assertIn("pending_evidence/history_not_mature", result.blockers)
+        with self.assertRaises(ValueError):
+            require_formal_history(ANNUALS, comparable_quarter_keys=WINDOW, as_of_utc=CUTOFF, cyclic=1)
+
+
+class FormulaTests(unittest.TestCase):
+    def test_economic_units_and_arithmetic_failure(self):
+        left, right = leaf("revenue"), leaf("shares")
+        mapping = {("revenue", "FY2025"): fact(value=100), ("shares", "FY2025"): fact(metric_key="shares", unit="shares", value=20)}
+        result = evaluate_formula(FormulaNode(op="divide", left=left, right=right), mapping)
+        self.assertEqual((result.value, result.unit, result.time_reliability), (5.0, "CNY_per_share", 1.0))
+        for op in ("add", "subtract", "cagr", "median", "minimum"):
+            node = FormulaNode(op=op, items=(left, right)) if op in {"median", "minimum"} else FormulaNode(op=op, left=left, right=right, **({"intervals": 2} if op == "cagr" else {}))
+            result = evaluate_formula(node, mapping)
+            self.assertEqual(result.missing_reason, "formula_unit_mismatch")
+            self.assertEqual((result.value, result.unit, result.evidence, result.time_reliability), (None, None, (), None))
+        reverse = evaluate_formula(FormulaNode(op="divide", left=right, right=left), mapping)
+        self.assertEqual(reverse.missing_reason, "formula_unit_mismatch")
+        huge = {("revenue", "FY2024"): fact(year=2024, value=1e308), ("revenue", "FY2025"): fact(value=1e308)}
+        result = evaluate_formula(FormulaNode(op="add", left=leaf(period="FY2024"), right=leaf()), huge)
+        self.assertEqual(result.missing_reason, "formula_nonfinite_result")
+
+    def test_cagr_direction_and_negative_endpoints(self):
+        node = FormulaNode(op="cagr", left=leaf(period="FY2023"), right=leaf(), intervals=2)
+        mapping = {("revenue", "FY2023"): fact(year=2023, value=100), ("revenue", "FY2025"): fact(value=121)}
+        self.assertAlmostEqual(evaluate_formula(node, mapping).value, .1)
+        for start, end in ((-100, 121), (100, -121), (0, 121), (100, 0)):
+            mapping[("revenue", "FY2023")] = fact(year=2023, value=start)
+            mapping[("revenue", "FY2025")] = fact(value=end)
+            self.assertEqual(evaluate_formula(node, mapping).missing_reason, "formula_nonpositive_cagr")
+
+    def test_quarter_reliability_all_operands_and_malformed_nodes(self):
+        date_q1 = fact("Q1", 10, published_precision="date_only", published_at_utc="2026-03-20T00:00:00+00:00", effective_at_utc="2026-03-21T07:00:00+00:00", effective_time_evidence_hash="c" * 64)
+        q2 = derive_comparable_quarters([date_q1, fact("H1", 30)]).facts[1]
+        result = evaluate_formula(leaf(period="2025Q2"), {("revenue", "2025Q2"): q2})
+        self.assertEqual((result.value, result.time_reliability, len(result.evidence)), (20, .8, 2))
+        cyclic = FormulaNode(op="add", left=leaf(), right=leaf())
+        object.__setattr__(cyclic, "left", cyclic)
+        with self.assertRaises(ValueError):
+            evaluate_formula(cyclic, {})
+        with self.assertRaises(ValueError):
+            evaluate_formula({}, {})
+        self.assertEqual(evaluate_formula(leaf(period="FY0"), {}).missing_reason, "formula_fact_missing")
+
+    def test_custom_keys_and_mutated_quarters_rejected(self):
+        class Text(str):
+            pass
+        class Pair(tuple):
+            pass
+        for key in ((Text("revenue"), "FY2025"), Pair(("revenue", "FY2025"))):
+            with self.assertRaises(ValueError):
+                evaluate_formula(leaf(), {key: fact()})
+        q = derive_comparable_quarters([fact("Q1")]).facts[0]
+        object.__setattr__(q, "component_fact_ids", ())
+        with self.assertRaises(ValueError):
+            evaluate_formula(leaf(period="2025Q1"), {("revenue", "2025Q1"): q})
+
+    def test_binary_operations_cagr_and_units(self):
+        mapping = {("revenue", "FY2024"): fact(year=2024, value=100), ("revenue", "FY2025"): fact(value=200)}
+        left, right = leaf(period="FY2024"), leaf()
+        for op, expected in (("add", 300), ("subtract", -100), ("divide", .5), ("cagr", 1.0)):
+            node = FormulaNode(op=op, left=left, right=right, **({"intervals": 1} if op == "cagr" else {}))
+            result = evaluate_formula(node, mapping)
+            self.assertEqual(result.value, expected)
+            self.assertEqual(len(result.evidence), 2)
+        mapping[("revenue", "FY2025")] = fact(value=0)
+        for op in ("divide", "cagr"):
+            result = evaluate_formula(FormulaNode(op=op, left=left, right=right, **({"intervals": 1} if op == "cagr" else {})), mapping)
+            self.assertIsNone(result.value)
+            self.assertEqual(result.evidence, ())
+
+    def test_aggregate_evidence_and_reliability(self):
+        date_fact = fact(value=40, published_precision="date_only", published_at_utc="2026-03-20T00:00:00+00:00", effective_at_utc="2026-03-21T07:00:00+00:00", effective_time_evidence_hash="c" * 64)
+        mapping = {("revenue", "FY2024"): fact(year=2024, value=10), ("revenue", "FY2025"): date_fact}
+        nodes = (leaf(period="FY2024"), leaf())
+        for op, value in (("median", 25), ("minimum", 10)):
+            result = evaluate_formula(FormulaNode(op=op, items=nodes), mapping)
+            self.assertEqual(result.value, value)
+            self.assertEqual(result.time_reliability, .8)
+            self.assertEqual(len(result.evidence), 2)
+
+    def test_namespace_and_hostile_mapping(self):
+        q = derive_comparable_quarters([fact("Q1", 10)]).facts[0]
+        self.assertEqual(evaluate_formula(leaf(period="2025Q1"), {("revenue", "2025Q1"): q}).value, 10)
+        for mapping in (UserDict(), {("profit", "FY2025"): fact()}, {("revenue", "2025Q1"): fact("Q1")}, {("revenue", "FY2024"): fact(year=2024), ("profit", "FY2025"): fact(metric_key="profit", security_id="SZ000001")}):
+            with self.assertRaises(ValueError):
+                evaluate_formula(leaf(), mapping)
+        missing = evaluate_formula(FormulaNode(op="add", left=leaf(), right=leaf("absent")), {("revenue", "FY2025"): fact()})
+        self.assertEqual(missing.missing_reason, "formula_fact_missing")
+        self.assertEqual(missing.evidence, ())
+
+
+class BundleTests(unittest.TestCase):
+    def test_issue_iterator_cannot_mutate_facts_or_registry_snapshots(self):
+        slots = sorted([slot_wire(template, unit="CNY", formula=leaf().to_dict()) for template in TEMPLATES], key=lambda item: item["slot_id"])
+        raw = feature_registry_bytes(slots=slots)
+        root = registry_manifest(raw)
+        registry = load_registry(raw, root)
+        original = fact()
+        expected = bundle([original], registry=registry, registry_manifest=root)
+        def hostile():
+            object.__setattr__(original, "value", 999.0)
+            object.__setattr__(root, "manifest_hash", "e" * 64)
+            object.__setattr__(registry, "contract_version", "tampered")
+            return
+            yield
+        result = bundle([original], registry=registry, registry_manifest=root, issues=hostile())
+        self.assertEqual(result.to_dict(), expected.to_dict())
+
+    def test_official_child_with_test_root_and_unbound_child_blocks(self):
+        slots = sorted([slot_wire(template, unit="CNY", formula=leaf().to_dict()) for template in TEMPLATES], key=lambda item: item["slot_id"])
+        raw = feature_registry_bytes(slots=slots)
+        official = registry_manifest(raw)
+        test = registry_manifest(raw, purpose="test")
+        registry = load_registry(raw, official)
+        self.assertTrue(registry.release_eligible)
+        result = bundle([fact()], registry=registry, registry_manifest=test)
+        self.assertEqual(result.values[0].status, "blocked")
+        self.assertIn("feature_registry_not_release_eligible", result.blockers)
+        self.assertEqual(bundle([fact()], registry=load_registry(raw), registry_manifest=official).values[0].status, "blocked")
+
+    def test_ambiguous_metric_fact_is_missing_and_others_survive(self):
+        raw = [fact(), fact(statement="cash_flow", value=80), fact(metric_key="profit", value=20)]
+        slots = [slot_wire("general_nonfinancial", suffix="a", unit="CNY", formula=leaf().to_dict()), slot_wire("general_nonfinancial", suffix="b", unit="CNY", formula=leaf("profit").to_dict())]
+        result = bundle(raw, slots=slots)
+        self.assertEqual(result.values[0].missing_reason, "formula_fact_ambiguous")
+        self.assertEqual((result.values[1].status, result.values[1].value), ("derived", 20))
+        self.assertEqual(result.input_hash, bundle(raw[::-1], slots=slots).input_hash)
+
+    def test_quarter_blocker_propagation_and_slot_unit_binding(self):
+        result = bundle([fact("H1")])
+        self.assertIn("quarter_missing_prerequisite", result.blockers)
+        self.assertEqual(result.values[0].status, "missing")
+        result = bundle([fact()], slots=[slot_wire("general_nonfinancial", unit="ratio", formula=leaf().to_dict())])
+        self.assertEqual(result.values[0].missing_reason, "formula_unit_mismatch")
+
+    def test_root_registry_and_issue_low_level_forgery(self):
+        for target in ("registry", "registry_manifest"):
+            forged = object.__new__(SignedFormalFeatureRegistry if target == "registry" else FormalRegistryManifest)
+            with self.assertRaises(ValueError):
+                bundle(**{target: forged})
+        issue = FormalFactIssue("nonnumeric_value", None, None, {})
+        object.__setattr__(issue, "code", "unknown_source_field")
+        with self.assertRaises(ValueError):
+            bundle(issues=[issue])
+
+    def test_derived_required_optional_and_nonrelease(self):
+        result = bundle([fact()])
+        self.assertEqual(result.values[0].status, "derived")
+        self.assertEqual(result.history_endpoints, ("2025-12-31",))
+        self.assertNotIn("feature_required_slot_missing", result.blockers)
+        for purpose in ("test",):
+            result = bundle([fact()], purpose=purpose)
+            self.assertEqual(result.values[0].status, "blocked")
+            self.assertIn("feature_registry_not_release_eligible", result.blockers)
+        self.assertIn("feature_required_slot_missing", bundle().blockers)
+        optional = [slot_wire("general_nonfinancial", required=False, unit="CNY", formula=leaf().to_dict())]
+        self.assertNotIn("feature_required_slot_missing", bundle(slots=optional).blockers)
+
+    def test_issues_conflicts_and_hash_inputs(self):
+        issue = FormalFactIssue("nonnumeric_value", None, None, {})
+        result = bundle([fact()], issues=[issue])
+        self.assertEqual(result.values[0].status, "blocked")
+        self.assertIn("formal_fact_issue_nonnumeric_value", result.blockers)
+        with self.assertRaises(ValueError):
+            bundle(issues=[FormalFactIssue("arbitrary", None, None, {})])
+        a, b = fact(), fact(value=101)
+        result = bundle([a, b])
+        self.assertEqual(result.values[0].status, "blocked")
+        self.assertEqual(result.input_hash, bundle([b, a]).input_hash)
+        self.assertNotEqual(result.input_hash, bundle([a]).input_hash)
+        self.assertNotEqual(bundle([a]).input_hash, bundle([fact(source_refresh_generation="new")]).input_hash)
+        future = fact(source_updated_at_utc="2026-09-01T00:00:00+00:00")
+        self.assertEqual(bundle([a]).input_hash, bundle([a, future]).input_hash)
+
+    def test_root_binding_and_foreign_facts(self):
+        raw = feature_registry_bytes(template_ids=("general_nonfinancial",))
+        with self.assertRaises(ValueError):
+            bundle([fact()], registry_manifest=registry_manifest(raw))
+        with self.assertRaises(ValueError):
+            bundle([fact(security_id="SZ000001")])
+        with self.assertRaises(ValueError):
+            bundle(registry=object())
+
+
+if __name__ == "__main__":
+    unittest.main()

```

