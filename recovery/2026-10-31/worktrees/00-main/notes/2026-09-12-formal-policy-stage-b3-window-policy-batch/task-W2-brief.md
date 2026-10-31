# W2 task brief — pure policy evaluation and effect aggregation

Plan: `docs/superpowers/plans/2026-09-12-formal-policy-stage-b3-window-policy-batch.md`

BASE: `b875b05` (`docs: record accepted W1 market window milestone`)

## Scope and files

Create exactly:

- `ashare_pipeline/formal_policy_evaluator.py`
- `tests/test_formal_policy_evaluator.py`

Do not modify any other tracked path. Do not touch production data, SQLite,
WAL/SHM, progress/history, network capture, scoring, pools, merge, or push.
Controller alone performs Git writes. Do not dispatch subagents.

## Interfaces

- Consumes F1 `PolicyValue`, detached F2/F3/W1 inputs, and a canonical-byte
  copy of Stage A rules. These are pure function parameters, never source
  eligibility or proof authority.
- Produce:
  - `quantile80(values: tuple[Decimal, ...], method: str) -> Decimal`
  - `evaluate_rule(rule: dict, *, security_id: str, applicability: str,
    values: dict, annual: dict, market: dict | None) -> dict`
  - `aggregate_decisions(decisions: tuple[dict, ...]) -> dict`
- `applicability` is closed to `applicable`, `not_applicable`, `unresolved`.
  `values` and `annual` are indexed by selector hash. Missing keys are explicit
  missing evidence, never false. Only W3 may convert genuine industry proof to
  the pure applicability argument.
- A decision has the exact Stage B design §8.1 fields. Aggregation is closed to
  `decisions`, `dimension_caps`, `pool_prohibitions`, `states`,
  `normalization_basis`, `pending_requirements`, `evidence_state`.
  `pool_prohibitions` expands `strong` and `wait` and preserves every effect's
  complete rule/evidence trace. Do not add final scores or `ready`/`eligible`.

## Mandatory TDD matrix

Start with failing tests and preserve the RED output before implementation.
Tests must use the real signed shapes exported by `tests/formal_policy_fixtures.py`
or a parsed rule graph, not hand-made simplified rule shapes.

Cover:

- both explicit quantile methods under hostile ambient Decimal precision;
- all five comparison operators, exact bool/enum, and inclusive `>=` boundary;
- two metrics both required;
- five-profit median/minimum logic, negative profit and zero;
- non-cyclic rules not requiring annual values;
- unresolved applicability producing pending evidence;
- per-dimension cap minimum;
- union of multiple pool prohibitions;
- preservation of every trace;
- a matched decision that itself carries pending requirements;
- market tail-20 proven with incomplete price: overall pending, but only the
  pool prohibition authorized by that 20-day proof may be released; do not
  release cap/status/profit-replacement effects that require a full match;
- `confirmed_no_price_250` retaining runtime/market evidence missing and both
  pool prohibitions;
- an unmatched rule not clearing already-authenticated input pending evidence.

Required quantile example:

```python
from decimal import Decimal, localcontext

def test_two_explicit_quantiles_do_not_share_a_default(self):
    from ashare_pipeline.formal_policy_evaluator import quantile80
    values = tuple(Decimal(i) for i in range(1, 6))
    with localcontext() as ambient:
        ambient.prec = 1
        self.assertEqual(quantile80(values, "linear_type7_v1"), Decimal("4.2"))
        self.assertEqual(quantile80(values, "nearest_rank_v1"), Decimal("4"))
    with self.assertRaises(ValueError):
        quantile80(values, "default")
```

## Implementation constraints

Use an independent F1 Decimal context for all Decimal arithmetic. Keep the four
decision states as explicit branches. Bind each effect to the evidence that
actually authorizes it.

```python
from decimal import Decimal, ROUND_CEILING, localcontext
from .formal_policy_values import decimal_context

def quantile80(values, method):
    if len(values) != 5 or any(type(v) is not Decimal or not v.is_finite() for v in values):
        raise ValueError("five finite Decimal annual observations required")
    ordered = sorted(values)
    with localcontext(decimal_context()):
        if method == "nearest_rank_v1":
            rank = int((Decimal(len(ordered)) * Decimal("0.8")).to_integral_value(rounding=ROUND_CEILING))
            return ordered[rank - 1]
        if method == "linear_type7_v1":
            h = Decimal(len(ordered) - 1) * Decimal("0.8")
            lower = int(h)
            return ordered[lower] + (h - lower) * (ordered[lower + 1] - ordered[lower])
    raise ValueError("unsupported signed quantile method")

def combine_caps(caps):
    result = {}
    for dimension, limit in caps:
        result[dimension] = min(result.get(dimension, limit), limit)
    return result
```

When a cyclic rule matches, `normalization_basis` must retain the original
current profit, all five original annual values/evidence, the sorted third-value
median, the `minimum_current_and_five_fy_median_v1` result, and the signed V
dependency list. Do not call a V adapter. Cap values and allowed dimensions come
from parsed effects; do not hard-code original cyclic G/M=80 as a policy default.
Canonicalize sorting for effects/traces. Deduplicate display keys only; preserve
every underlying reason.

## Required commands and report

RED:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_evaluator -v
```

GREEN:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_evaluator tests.test_formal_policy_values tests.test_formal_policy_contract -v
```

Run the focused suite while iterating. Because the broader project suite is very
expensive, do not start a project-wide run; report the exact required GREEN and
any additional focused compatibility modules you ran. Controller/reviewer will
decide the final compatibility gate.

Write the complete report to
`.superpowers/sdd/2026-09-12-formal-policy-stage-b3-window-policy-batch/task-W2-report.md`.
Include RED and GREEN commands, exact counts/timings/output summaries, changed
files, hashes, self-review, and concerns. Return only status, one-line test
summary, concerns, and report path. Do not commit.
