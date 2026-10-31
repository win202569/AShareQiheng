### Task 3: Pure adjustment arithmetic and state machine

**Files:**
- Create: `ashare_pipeline/formal_valuation_adapter.py`
- Create: `tests/test_formal_valuation_adapter.py`

**Interfaces:**
- Consumes: detached canonical dicts for one base metric row, one policy result, one cyclic decision, one dependency and optional adapter definition。
- Produces: `profit_ratio_rescale(original_metric_value: Decimal, original_current_profit: Decimal, normalized_profit: Decimal) -> Decimal`；`evaluate_valuation_adjustment(*, metric: dict, policy_result: dict, cyclic_decision: dict, dependency: dict, adapter: dict | None) -> dict`。纯结果不能自称正式证明。

- [ ] **Step 1: 写数值与状态 RED 测试。**

```python
def test_matched_affected_uses_normalized_profit_ratio(self):
    result = evaluate_valuation_adjustment(
        metric=metric(value="0.20", unit="ratio"),
        policy_result=policy_result(),
        cyclic_decision=decision("matched", current="10", normalized="6"),
        dependency=affected(), adapter=adapter())
    self.assertEqual(result["status"], "adjusted")
    self.assertEqual(result["adjusted_value"], "0.12")

def test_pending_policy_blocks_only_affected_metric(self):
    pending = decision("pending_evidence")
    blocked = evaluate_valuation_adjustment(
        metric=metric(), policy_result=policy_result(), cyclic_decision=pending,
        dependency=affected(), adapter=adapter())
    passed = evaluate_valuation_adjustment(
        metric=metric(), policy_result=policy_result(), cyclic_decision=pending,
        dependency=unaffected(), adapter=None)
    self.assertEqual(blocked["status"], "pending_policy_evidence")
    self.assertIsNone(blocked["adjusted_value"])
    self.assertEqual(passed["status"], "passthrough_unaffected")
```

加入 clear、not_applicable、matched/unaffected、adjusted_no_numeric_change、错误模板/指标/利润语义、缺 normalization basis、多 basis、非 affected 却给 adapter 的精确测试。

- [ ] **Step 2: 写非法操作数 Review Focus 测试并运行 RED。**

```python
def test_invalid_adapter_operands_fail_closed_without_numeric_output(self):
    cases = (("0", "6", "original_current_profit_zero"),
             ("NaN", "6", "metric_value_nonfinite"),
             ("10", "Infinity", "normalized_profit_nonfinite"))
    for current, normalized, reason in cases:
        with self.subTest(reason=reason):
            result = evaluate_valuation_adjustment(
                metric=metric(value="NaN" if reason == "metric_value_nonfinite" else "0.20"),
                policy_result=policy_result(),
                cyclic_decision=decision("matched", current=current, normalized=normalized),
                dependency=affected(), adapter=adapter())
            self.assertEqual(result["status"], "invalid_adapter_operand")
            self.assertEqual(result["reason"], reason)
            self.assertIsNone(result["adjusted_value"])
```

Run: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_valuation_adapter -v`

Expected: FAIL because the module does not exist。

- [ ] **Step 3: 实现固定 Decimal 内核。**

```python
def _arithmetic_context():
    return Context(prec=50, rounding=ROUND_HALF_EVEN, Emin=-999999,
                   Emax=999999, capitals=1, clamp=0, flags=[],
                   traps=[InvalidOperation, DivisionByZero, Overflow])

def profit_ratio_rescale(original_metric_value, original_current_profit,
                         normalized_profit):
    values = (original_metric_value, original_current_profit, normalized_profit)
    if any(type(value) is not Decimal or not value.is_finite() for value in values):
        raise ValueError("valuation adapter requires finite exact Decimals")
    if original_current_profit == 0:
        raise ValueError("valuation adapter original profit cannot be zero")
    with localcontext(_arithmetic_context()):
        return original_metric_value * normalized_profit / original_current_profit
```

状态机先校验所有 detached dict 的精确 keys 和跨对象身份，再根据 decision/dependency 选择透传、待补或 adjustment。输出 Decimal 使用规范字符串，并包含 operation、输入、结果、reason、decision_hash、result_hash、adapter definition hash；不接受调用者提供 status 或 adjusted_value。

- [ ] **Step 4: 验证全局 Decimal 污染和确定性。**

```python
def test_ambient_decimal_context_cannot_change_adjustment(self):
    with localcontext() as ambient:
        ambient.prec = 2
        ambient.rounding = ROUND_DOWN
        first = profit_ratio_rescale(Decimal("0.2"), Decimal("3"), Decimal("2"))
    with localcontext() as ambient:
        ambient.prec = 28
        second = profit_ratio_rescale(Decimal("0.2"), Decimal("3"), Decimal("2"))
    self.assertEqual(first, second)
```

- [ ] **Step 5: 运行 GREEN。**

Run: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_valuation_adapter tests.test_formal_policy_evaluator tests.test_formal_metric_engine -v`

Expected: 全部 PASS。

- [ ] **Step 6: 提交 C3。**

```powershell
git add ashare_pipeline/formal_valuation_adapter.py tests/test_formal_valuation_adapter.py
git commit -m "feat: evaluate deterministic valuation policy adjustments"
```

