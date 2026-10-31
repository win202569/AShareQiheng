# Stage C Task 3: pure valuation adjustment

## Scope and files

- `ashare_pipeline/formal_valuation_adapter.py`: isolated Decimal ratio operation and detached per-metric state evaluation. It validates the closed input shapes, content hashes, metric/decision/dependency/adapter identity, signed operation and units before selecting a passthrough, pending or adjusted state. It returns a content-hashed plain dictionary and grants no proof authority.
- `tests/test_formal_valuation_adapter.py`: ten tests for arithmetic, all seven states, pending by dependency, hash binding, shape and identity rejection, invalid operands and deterministic context.

## RED / GREEN

1. The initial new-module run failed with `ModuleNotFoundError: ashare_pipeline.formal_valuation_adapter`.
2. The first implementation passed eight focused tests. Replacing the fixture's simplified matched operands with the actual Stage B operand shape reproduced an error; accepting the complete closed shape restored GREEN.
3. A new test for an extra field inside a nonfocal dependency failed because that field was accepted, then passed after every dependency entry received exact-key validation.
4. A new test for a mismatched affected profit semantic failed because synchronized detached objects could point away from the cyclic decision, then passed after a direct semantic identity check.

## Verification

- Focused final command: `python -m unittest tests.test_formal_valuation_adapter -q` — 10 tests, PASS.
- First affected command: `python -m unittest tests.test_formal_valuation_adapter tests.test_formal_policy_evaluator tests.test_formal_metric_engine -v` — 45 tests, PASS. It preceded the last two new tests and the semantic check.
- Final affected command: `python -m unittest tests.test_formal_valuation_adapter tests.test_formal_policy_evaluator tests.test_formal_metric_engine -q` — 47 tests, PASS (181.424 seconds).
- An optional project-wide `unittest discover -s tests -p 'test_*.py' -q` run was stopped at the root task's direction after the required 47-test gate passed; it has no result and is not claimed as verification.
- `git diff --cached --check`: exit 0.

## Commit

`228b33f` — `feat: evaluate deterministic valuation policy adjustments`. The commit contains only the new implementation and test files. This report is an ignored coordination artifact outside that completed code commit.

## Residual risk

The evaluator consumes detached dictionaries and returns only a plain, replayable result. Task 3 does not authenticate source batches, issue formal proofs, publish a complete adjusted batch or rebuild peers; those belong to later Stage C tasks. The adapter definition and policy result must come from the upstream verified sources before this helper is called.

## Independent C3 review repair

Three Important findings were reproduced with tests before repair:

1. A live C2 `FormalValuationAdapterRegistry.to_dict()["adapters"][0]` array wire failed C3's tuple-only `preconditions` check. C3 now requires the canonical detached list, matching the signed C2 wire, and hashes that wire directly.
2. A decision, policy result and adapter that shared a nonconventional signed rule ID failed C3's template-name inference. C3 now validates the rule ID as text and binds it through the decision, policy result and adapter references.
3. Malformed Decimal text produced different reasons and result hashes when ambient `InvalidOperation` traps changed. All three operand positions now parse inside the fixed 50-digit local context; the test compares the complete result dictionaries across trap settings.

Repair RED: the three new tests reported two errors (wire and rule ID) and three failing operand subcases (ambient trap). Repair GREEN: all 13 focused tests pass.

Repair verification:

- Focused C3 command: `python -m unittest tests.test_formal_valuation_adapter -v` — 13 tests, PASS.
- Required C3/C2 and affected regression: `python -m unittest tests.test_formal_valuation_adapter tests.test_formal_valuation_adapter_contract tests.test_formal_policy_evaluator tests.test_formal_metric_engine -q` — 70 tests, PASS (346.852 seconds).
- `git diff --cached --check` — exit 0. Final tracked worktree is clean.

Independent repair commit: `5516548` — `fix: accept canonical valuation adapter wire and isolate parsing`. It changes only `ashare_pipeline/formal_valuation_adapter.py` and `tests/test_formal_valuation_adapter.py`.

Residual risk remains the pure helper's intended boundary: the new live C2 wire test checks the adapter representation and cross-object consumption, while formal source authenticity and full batch publication remain later Stage C work.
