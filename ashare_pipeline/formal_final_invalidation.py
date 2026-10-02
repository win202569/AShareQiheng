"""Detached invalidation arithmetic; this module never grants proof authority.

The repository authenticates both the exact historical artifacts and live D1 /
coverage inputs before calling this core. A returned plan is a description,
not permission to reuse a proof without verifying it again.
"""

from dataclasses import dataclass
import hashlib
import json


@dataclass(frozen=True)
class FormalRebuildPlan:
    full_rebuild: bool
    direct_security_ids: tuple[str, ...]
    expanded_security_ids: tuple[str, ...]
    cohort_keys: tuple[tuple[str, ...], ...]
    d1_rebuild_ids: tuple[str, ...]
    d2_rebuild_ids: tuple[str, ...]
    eligibility_rebuild_ids: tuple[str, ...]
    rescan_pools: bool
    reason_codes: tuple[str, ...]
    prior_manifest_hash: str
    current_manifest_hash: str
    effect_scopes: tuple[str, ...]


_GLOBAL_KEYS = frozenset(("registry_manifest_hash", "frozen_input_hash", "universe_hash",
    "population_hash", "scoring_registry_hash", "policy_contract_hash",
    "valuation_adapter_registry_hash", "industry_batch_hash", "as_of_utc"))
_DIAGNOSTIC_KEYS = frozenset(("diagnostics", "timing_diagnostics", "audit_at_utc",
    "rechecked_at_utc", "display", "display_format"))
_DERIVED_KEYS = frozenset(("entry_hash", "input_hash", "base_input_hash", "result_hash",
    "policy_result_hash", "score_hash", "context_hash", "cohort_hash", "decision_hash",
    "metric_input_hash", "adjusted_input_hash", "full_feature_bundle_hash", "bundle_hash"))
_SCOPES = frozenset(("security", "cohort", "pool", "global"))


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _aggregate_key(key):
    return key == "batch_hash" or key.endswith(("_batch_hash", "_batch_canonical_sha256"))


def _clean(value):
    """Remove enclosing seals and non-economic diagnostics, retaining leaf evidence."""
    if isinstance(value, dict):
        return {key: _clean(child) for key, child in value.items()
            if key not in _DIAGNOSTIC_KEYS | _DERIVED_KEYS and not _aggregate_key(key)}
    if isinstance(value, (list, tuple)):
        return [_clean(child) for child in value]
    return value


def _slot_source(slot):
    if slot is None:
        return None
    result = {key: value for key, value in slot.items()
        if key not in ("value", "metric_score", "valuation_score", "valuation_context",
            "valuation_score_hash", "valuation_context_hash")}
    metric = slot.get("metric_score")
    if metric:
        result["metric_source"] = {key: value for key, value in metric.items()
            if key not in ("percentile", "average_rank", "peer_count", "peer_context")}
    valuation = result.get("valuation_input")
    if valuation:
        # PolicyResult is repeated verbatim inside Stage C. Its individual
        # effects are diffed separately, so a cap is not a V normalization.
        result["valuation_input"] = {key: value for key, value in valuation.items()
            if key != "policy_result"}
    return _clean(result)


def _context(slot):
    if not slot:
        return None
    return slot.get("valuation_context") or (slot.get("metric_score") or {}).get("peer_context")


def _slot_result(slot):
    return _clean({key: value for key, value in (slot or {}).items()
        if key in ("value", "metric_score", "valuation_score", "valuation_context")})


def _hash_dependencies(inputs):
    """Reproduce Task 9's original dependency projection without altering history."""
    rows = []
    def walk(value, sid, path):
        if type(value) is dict:
            for key, child in value.items():
                child_path = path + "." + key
                if key.endswith(("_hash", "_sha256")) and type(child) is str and child:
                    rows.append(dict(security_id=sid, source_kind=key, source_id=child_path,
                        source_hash=child, effect_scope="global" if sid is None else "security",
                        dependent_key="run" if sid is None else sid))
                elif type(child) in (dict, list):
                    walk(child, sid, child_path)
        elif type(value) is list:
            for index, child in enumerate(value):
                walk(child, sid, path + "." + str(index))
    walk({key: value for key, value in inputs.items() if key != "inputs"}, None, "batch")
    for row in inputs["inputs"]:
        walk(row, row["security_id"], "input." + row["security_id"])
    return rows


def _derive_plan(*, prior_inputs, current_inputs, prior_coverage, current_coverage,
                 prior_dependencies, prior_identity, current_identity):
    """Pure diff for already authenticated wires; intentionally private, no mint."""
    dependencies = [dict(row) for row in prior_dependencies]
    if any(row.get("effect_scope") not in _SCOPES for row in dependencies):
        raise ValueError("unknown formal dependency effect scope")
    canonical = lambda rows: sorted(_digest(row) for row in rows)
    if canonical(dependencies) != canonical(_hash_dependencies(prior_inputs)):
        raise ValueError("prior dependencies differ from the exact canonical manifest")
    old = {row["security_id"]: row for row in prior_inputs["inputs"]}
    new = {row["security_id"]: row for row in current_inputs["inputs"]}
    ids = set(old) | set(new)
    direct, d1, d2, eligibility, cohorts, reasons = set(), set(), set(), set(), set(), set()
    localized_sources = set()
    full = False

    def global_change(reason):
        nonlocal full
        full = True
        reasons.add(reason)

    if (set(old) != set(new) or prior_inputs["security_ids"] != current_inputs["security_ids"]):
        global_change("universe_changed")
        direct.update(set(old) ^ set(new))
    for key in _GLOBAL_KEYS:
        if prior_inputs.get(key) != current_inputs.get(key):
            global_change("global_context_changed:" + key)
    current_dependencies = _hash_dependencies(current_inputs)
    old_global = {row["source_id"]: row["source_hash"] for row in dependencies
        if row["source_kind"] in _GLOBAL_KEYS}
    new_global = {row["source_id"]: row["source_hash"] for row in current_dependencies
        if row["source_kind"] in _GLOBAL_KEYS}
    if any(old_global[key] != new_global[key] for key in old_global.keys() & new_global.keys()):
        global_change("global_dependency_changed")
    for key in ("mode", "code_version", "contract_version"):
        if prior_identity.get(key) != current_identity.get(key):
            global_change("run_contract_changed:" + key)
    for sid in set(old) & set(new):
        for key in ("template_id", "primary_industry", "secondary_industry"):
            if old[sid].get(key) != new[sid].get(key):
                global_change("industry_or_template_changed")

    def security_change(sid, reason, *, score=True):
        direct.add(sid)
        d1.add(sid)
        eligibility.add(sid)
        if score:
            d2.add(sid)
        reasons.add(reason)

    def expand(sid, mid):
        found = False
        for members in (old, new):
            focal = members.get(sid)
            if focal is None:
                continue
            for consumer, row in members.items():
                context = _context(row.get("slots", {}).get(mid))
                if not context:
                    continue
                peers = set(context["peer_security_ids"])
                if not peers <= set(members):
                    raise ValueError("cohort contains a security outside the manifest")
                if consumer != sid and sid not in peers:
                    continue
                found = True
                scope = context.get("scope")
                industry = row.get("secondary_industry" if scope == "template_secondary_industry"
                    else "primary_industry")
                cohorts.add(tuple(str(value or "") for value in (mid, row.get("template_id"),
                    scope, industry, context.get("definition_hash"), context.get("direction"))))
                affected = peers | {consumer, sid}
                d1.update(affected)
                d2.update(affected)
                eligibility.update(affected)
        if not found:
            global_change("unlocalizable_cohort_change")

    for sid in sorted(set(old) & set(new)):
        previous, current = old[sid], new[sid]
        before_slots, after_slots = previous.get("slots", {}), current.get("slots", {})
        for mid in sorted(set(before_slots) | set(after_slots)):
            before, after = before_slots.get(mid), after_slots.get(mid)
            if _slot_source(before) != _slot_source(after):
                security_change(sid, "metric_evidence_changed")
                localized_sources.add("valuation" if mid.startswith("V.") else "base")
                if mid.startswith("V.") and _clean((before or {}).get("valuation_input", {}).get("original_metric")) != _clean((after or {}).get("valuation_input", {}).get("original_metric")):
                    localized_sources.add("base")
                if mid.startswith("V.") or _context(before) or _context(after):
                    expand(sid, mid)
            # Membership and percentile changes affect existing consumers too,
            # even when their own raw evidence did not change.
            elif _slot_result(before) != _slot_result(after):
                d1.add(sid)
                d2.add(sid)
                eligibility.add(sid)
                reasons.add("peer_result_changed")
                expand(sid, mid)

        old_policy, new_policy = previous.get("policy_result", {}), current.get("policy_result", {})
        effect_keys = ("dimension_caps", "normalization_basis", "pool_prohibitions", "states",
            "pending_requirements", "evidence_state")
        effect_changed = False
        for key in effect_keys:
            if _clean(old_policy.get(key)) == _clean(new_policy.get(key)):
                continue
            effect_changed = True
            localized_sources.add("policy")
            security_change(sid, "policy_changed:" + key, score=key not in ("pool_prohibitions", "states"))
            if key == "normalization_basis":
                metrics = {mid for mid in set(before_slots) | set(after_slots) if mid.startswith("V.")}
                if not metrics:
                    global_change("unlocalizable_cohort_change")
                for mid in metrics:
                    expand(sid, mid)
        if not effect_changed and _clean(old_policy) != _clean(new_policy):
            localized_sources.add("policy")
            security_change(sid, "policy_evidence_changed")

        excluded = {"slots", "policy_result", "policy_pending_requirements"}
        left = _clean({key: value for key, value in previous.items() if key not in excluded})
        right = _clean({key: value for key, value in current.items() if key not in excluded})
        if left != right:
            localized_sources.add("base")
            security_change(sid, "security_evidence_changed")

    def coverage_rows(manifest):
        grouped = {}
        for row in manifest["rows"]:
            grouped.setdefault(row["security_id"], []).append(_clean(row))
        return {sid: sorted(_digest(row) for row in rows) for sid, rows in grouped.items()}
    old_coverage, new_coverage = coverage_rows(prior_coverage), coverage_rows(current_coverage)
    for sid in set(old_coverage) | set(new_coverage):
        if old_coverage.get(sid) != new_coverage.get(sid):
            if sid not in ids:
                raise ValueError("coverage security lies outside the manifest")
            security_change(sid, "coverage_evidence_changed")
    coverage_meta = lambda manifest: _clean({key: value for key, value in manifest.items()
        if key not in ("rows", "manifest_hash", "blockers")})
    if coverage_meta(prior_coverage) != coverage_meta(current_coverage):
        global_change("coverage_context_changed")

    # Aggregate seals bind whole source batches. They cannot identify which
    # omitted pending input changed; do not invent member IDs in that case.
    previous_aggregates = {row["source_id"]: row["source_hash"] for row in dependencies
        if row["security_id"] is None and _aggregate_key(row["source_kind"])
        and row["source_kind"] != "batch_hash"}
    current_aggregates = {row["source_id"]: row["source_hash"] for row in current_dependencies
        if row["security_id"] is None and _aggregate_key(row["source_kind"])
        and row["source_kind"] != "batch_hash"}
    # Stage C seals include both base and policy batches, even when their
    # changes do not affect numeric V inputs (for example a policy cap).
    if localized_sources & {"base", "policy"}:
        localized_sources.add("valuation")
    for path in previous_aggregates.keys() | current_aggregates.keys():
        if previous_aggregates.get(path) != current_aggregates.get(path):
            source = path.removeprefix("batch.").split("_", 1)[0]
            if source not in localized_sources:
                global_change("unlocalizable_upstream_change")
    if full:
        d1.update(new)
        d2.update(new)
        eligibility.update(new)
    # Departed members explain invalidation but are not current build targets.
    d1.intersection_update(new)
    d2.intersection_update(new)
    eligibility.intersection_update(new)
    expanded = d1 | d2 | eligibility
    scopes = set()
    if direct:
        scopes.add("security")
    if cohorts:
        scopes.add("cohort")
    if full:
        scopes.add("global")
    if expanded:
        scopes.add("pool")
    return FormalRebuildPlan(full, tuple(sorted(direct)), tuple(sorted(expanded)),
        tuple(sorted(cohorts)), tuple(sorted(d1)), tuple(sorted(d2)), tuple(sorted(eligibility)),
        bool(expanded), tuple(sorted(reasons)), _digest(prior_identity), _digest(current_identity),
        tuple(sorted(scopes)))


__all__ = ["FormalRebuildPlan"]
