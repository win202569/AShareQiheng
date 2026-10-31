# W2 implementation report — pure policy evaluation and effect aggregation

## Status

Complete. Implemented W2 against base
`b875b053317e872ebf48a8b379345a3f462ad330` without commits or other Git writes.
Only the two authorized tracked paths were created.

## Delivered behavior

- `quantile80` supports only `linear_type7_v1` and `nearest_rank_v1`, requires
  five finite exact `Decimal` values, and performs arithmetic in the independent
  F1 Decimal context.
- `evaluate_rule` validates a detached canonical Stage A rule copy and evaluates
  numeric, boolean, enum, cyclic, and two-axis market rules into the four closed
  decision states.
- Missing selector keys and authenticated `PolicyValue` pending reasons remain
  explicit; a proven clear or matched effect never erases them.
- Cyclic evaluation requires both metric tests, retains the five original profit
  observations and evidence, derives the sorted-third median and minimum profit
  basis, and copies the signed V dependency list without invoking an adapter.
- Market evaluation can release only the signed pool prohibition from an
  independently proven tail-20 veto while the price axis is incomplete. A
  confirmed 250-day no-price result remains matched, retains
  `market_evidence_missing`, and expands the signed both-pool prohibition.
- `aggregate_decisions` returns exactly the seven requested top-level fields,
  takes the minimum cap per dimension, expands both-pool prohibitions, preserves
  every underlying effect trace, retains all pending reasons, and emits no score,
  readiness, or eligibility fields.
- Effects, inputs, pending reasons, decisions, and aggregate reason traces are
  deterministically ordered. Cap values remain signed decimal text so the full
  aggregate is canonical-JSON serializable for W3.

## TDD evidence

### Mandated RED

Command:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_evaluator -v
```

Result before production implementation: expected failure.

- `Ran 13 tests in 0.012s`
- `FAILED (errors=18)`
- Every error was the expected
  `ModuleNotFoundError: No module named 'ashare_pipeline.formal_policy_evaluator'`.
- The tests used fixture-exported rules accepted by the real
  `parse_policy_rule` contract parser; no simplified rule objects were used.

### Focused regression RED/GREEN during self-review

After the initial evaluator GREEN, two integration-sensitive cases were added:
an entirely absent annual selector key and canonical serialization of aggregated
caps.

RED command:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_evaluator -v
```

RED result:

- `Ran 14 tests in 0.029s`
- `FAILED (failures=1, errors=1)`
- Error: absent annual series attempted to iterate `None`.
- Failure: aggregate caps were `Decimal` objects rather than JSON-safe signed
  decimal text.

After the narrow fixes, the same focused command produced:

- `Ran 14 tests in 0.034s`
- `OK`

## Final mandated GREEN

Fresh command run after the last code/test edit:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_evaluator tests.test_formal_policy_values tests.test_formal_policy_contract -v
```

Result:

- Exit code: `0`
- `Ran 67 tests in 36.867s`
- `OK`
- Failures: `0`
- Errors: `0`
- Skips: `0`

No project-wide suite was started, as explicitly required by the W2 brief.

## Changed tracked files and SHA-256

- `ashare_pipeline/formal_policy_evaluator.py`
  - `c360c160152cc6b1a2138e6028ae63df9300f787581e66621fbfccbbb5d27382`
- `tests/test_formal_policy_evaluator.py`
  - `694372d74b383f3916d765c9cbf9791201eb6509659527d4e57674901db0c407`

`git status --short` showed exactly these two untracked implementation paths.
`git diff --check` produced no output.

## Acceptance matrix

- Both explicit quantiles under hostile ambient precision: covered.
- Five numeric comparators and inclusive `gte` boundary: covered.
- Exact boolean and enum behavior: covered.
- Both cyclic metrics required: covered.
- Five-profit median/minimum with zero and negative profit: covered.
- Non-cyclic rule without annual history: covered.
- Unresolved applicability: covered.
- Missing selector key as explicit evidence shortage: covered.
- Per-dimension minimum cap: covered with two valid signed G cap effects.
- Multiple pool prohibition union and both-pool expansion: covered.
- Every underlying effect trace retained: covered.
- Matched decision with a signed pending requirement: covered.
- Proven tail-20 veto plus incomplete price releasing only the pool effect:
  covered with additional valid cap and status effects withheld.
- Confirmed 250-day no-price retaining runtime pending plus both prohibitions:
  covered.
- Proven clear retaining authenticated input pending evidence: covered.
- Aggregate absence of `ready`, `eligible`, and final score fields: covered.

## Self-review

- Re-read the W2 brief and Stage B design sections 8.1–8.2 after implementation.
- Confirmed all Decimal arithmetic that can round uses `decimal_context()`.
- Confirmed cap dimensions/maximums and all other effects come from parsed rule
  effects; no G/M policy default is hard-coded.
- Confirmed no V adapter, score generation, pool generation, repository proof,
  database, network, production data, or source capture is used.
- Confirmed detached input containers are copied into results and canonical
  ordering does not depend on caller insertion order.
- Confirmed the output keeps underlying reasons even when display-level cap keys
  are combined.
- Confirmed no files outside the two tracked paths were modified; this report is
  the requested SDD evidence artifact.

## Concerns

None known. W3 must remain the only layer that authenticates repository
selections and converts them to these detached pure-function parameters.

## Fix Round 1 — closed detached market-result validation

Review addressed:
`task-W2-review-6078c5f.md`, Important finding 1.

Status: complete on reviewed W2 head
`6078c5f7ab9fdc816539f50dda106cebc6442986`.

### Boundary change

- Added four focused regressions for the reviewer's exact malformed detached
  market reproductions: unknown price state, confirmed-no-price without its
  mandatory pending reason, incomplete/proven without any pending reason, and
  an invented runtime pending code.
- Added one boundary helper that extracts the seven closed W1 market-axis fields
  and validates them through F1's existing public `PolicyValue` `market_window`
  DTO contract before any evaluation state or effect is derived.
- Surrounding W1 evidence metadata remains allowed. It is not passed into the
  closed DTO shape and continues to be used only for copied trace references;
  the change grants no source authenticity or proof authority.
- Every accepted incomplete result is now guaranteed by the F1 contract to
  carry at least one valid closed runtime pending reason.

### Focused RED

Command:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_evaluator.MarketRuleValidationTests -v
```

Result before the evaluator change:

- `Ran 4 tests in 0.003s`
- `FAILED (failures=4)`
- Each test failed because the expected `ValueError` was not raised, reproducing
  the review finding exactly.

### Focused GREEN

Same command after the boundary fix:

- `Ran 4 tests in 0.014s`
- `OK`

### Amended evaluator module

Command:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_evaluator -v
```

Result:

- `Ran 18 tests in 0.048s`
- `OK`

### Exact mandatory compatibility GREEN

Command:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_evaluator tests.test_formal_policy_values tests.test_formal_policy_contract -v
```

Result:

- Exit code: `0`
- `Ran 71 tests in 37.844s`
- `OK`
- Failures: `0`
- Errors: `0`
- Skips: `0`

No project-wide suite was started.

### Fix-round file hashes

- `ashare_pipeline/formal_policy_evaluator.py`
  - `c8d239ddede6a60fa0f488d234dee98f62c57c7c0f1446140f1be9f58da31919`
- `tests/test_formal_policy_evaluator.py`
  - `12f13d499a44e639d58b1fc75e698a75a059236115c1cb5df1e6fa72b13dc843`

`git status --short` showed only these two modified W2 paths. `git diff --check`
reported only the repository's LF-to-CRLF checkout warnings and no whitespace
errors.

### Fix-round self-review and concerns

- Validation runs before evidence completeness, decision state, or effect
  selection is derived.
- Unknown `price_state`/`veto_state`, inconsistent price/staleness combinations,
  missing mandatory pending reasons, and unknown runtime reason codes are
  rejected by the same closed F1 contract already used elsewhere.
- Valid outer W1 metadata is deliberately tolerated and cannot alter the closed
  axis validation.
- The review's Minor positive-price branch coverage item remains recorded for
  final-review triage and was not added in this blocking fix round, per explicit
  instruction.
