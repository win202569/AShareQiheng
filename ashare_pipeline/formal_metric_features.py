"""Pure selected V6 AST evaluation; this module never mints repository proof.

Provider extraction issues have no authenticated universal period/source scope.
Until signed mapping can prove exclusion, every such issue blocks projection.
Calculations deliberately retain the original V6 float semantics.
"""

from .formal_feature_contract import FormalFeatureSlot, FormalFeatureValue
from .formal_financial_features import (
    derive_comparable_quarters, evaluate_formula, select_visible_formal_facts,
)


def _leaves(node):
    if node.op == "fact":
        return {(node.fact_key, node.period_key)}
    children = node.items if node.op in {"median", "minimum"} else (node.left, node.right)
    return set().union(*(_leaves(child) for child in children))


def evaluate_selected_features(*, slots, facts, issues, as_of_utc):
    """Return detached signed-slot values and explicit local blockers."""
    output, all_blockers = [], set()
    issue_blockers = {"formal_fact_issue_" + issue.to_dict()["code"] for issue in issues}
    for supplied_slot in slots:
        slot = FormalFeatureSlot.from_dict(supplied_slot.to_dict())
        namespace, blockers = {}, set(issue_blockers)
        for metric, period in sorted(_leaves(slot.formula)):
            candidates = [fact for fact in facts if fact.metric_key == metric]
            if len(period) == 6 and period.startswith("FY") and period[2:].isdigit():
                end = period[2:] + "-12-31"
                local = select_visible_formal_facts(
                    (fact for fact in candidates if fact.period_kind == "FY" and fact.period_end == end),
                    as_of_utc,
                )
                blockers.update(local.blockers)
                derived = local.facts
            elif len(period) == 6 and period[:4].isdigit() and period[4] == "Q" and period[5] in "1234":
                year, quarter = period[:4], int(period[5])
                ends = ("03-31", "06-30", "09-30", "12-31")
                end = year + "-" + ends[quarter - 1]
                predecessor = year + "-" + ends[quarter - 2] if quarter > 1 else None
                local = select_visible_formal_facts(
                    (fact for fact in candidates if fact.period_end == end
                        or (fact.nature == "duration" and fact.period_end == predecessor)), as_of_utc,
                )
                blockers.update(local.blockers)
                quarters = derive_comparable_quarters(local.facts)
                derived = tuple(fact for fact in quarters.facts if fact.quarter_key == period)
                local_blockers = set(quarters.blockers)
                # Deriving Q4 also attempts Q3. Q3's absent H1 is immaterial
                # only when every requested endpoint is covered by a Q4 proof.
                requested_ids = {fact.id for fact in local.facts if fact.period_end == end}
                covered_ids = {identity for fact in derived for identity in fact.component_fact_ids}
                if requested_ids and requested_ids <= covered_ids:
                    local_blockers.discard("quarter_missing_prerequisite")
                blockers.update(local_blockers)
            else:
                # Signed V6 accepts arbitrary period identifiers; an unsupported
                # identifier has no matching formula namespace, never a guessed FY.
                derived = ()
            if len(derived) > 1:
                blockers.add("formula_fact_ambiguous")
            elif derived:
                namespace[(metric, period)] = derived[0]
        if blockers:
            value = FormalFeatureValue(slot.slot_id, None, slot.unit, "blocked",
                slot.formula_version, (), sorted(blockers)[0])
        else:
            result = evaluate_formula(slot.formula, namespace)
            reason = result.missing_reason
            if reason is None and result.unit != slot.unit:
                reason = "formula_unit_mismatch"
            if reason is not None:
                blockers.add(reason)
                value = FormalFeatureValue(slot.slot_id, None, slot.unit, "missing",
                    slot.formula_version, (), reason)
            else:
                value = FormalFeatureValue(slot.slot_id, result.value, slot.unit, "derived",
                    slot.formula_version, result.evidence, None)
        output.append(value)
        all_blockers.update(blockers)
    return tuple(output), tuple(sorted(all_blockers))
