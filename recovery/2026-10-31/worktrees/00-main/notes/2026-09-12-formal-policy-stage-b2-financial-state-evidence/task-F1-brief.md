# Task F1 brief

Source: docs/superpowers/plans/2026-09-12-formal-policy-stage-b2-financial-state-evidence.md

## Global Constraints

冻结时点仍为北京时间 2026-08-31 15:00，即 `2026-08-31T07:00:00+00:00`；SH/SZ/BJ 普通 A 股、五模板、七维权重、指标级同行资格、严格排除和证据门槛全部保持原合同。强池最多 20、等待池最多 50、行业上限 4/10 不变。本阶段不按最终入池资格筛选取证宇宙。

不改写旧 V2–V6 DDL、已有财务公式或已发布字节；不覆盖数据、SQLite、WAL/SHM、进度和历史结果；不自动合并 main 或推送。

以下不属于本阶段：真实生产来源或经济映射审批、生产签名、全市场实爬、定时调度、利润调整后 V 指标适配器、同行重排、最终置信度/分数/等级、选池、正式发布持久化。软件可支持后续增量采集，但本阶段开发验收不运行生产采集。


## F1：政策值结构、Decimal 桥与真实运行夹具

**Files:** Create `ashare_pipeline/formal_policy_values.py`, `tests/test_formal_policy_values.py`, `tests/formal_policy_runtime_fixtures.py`。

**Interfaces:**

- Produces: `decimal_context() -> decimal.Context`、`bridge_v6(value: float | int) -> Decimal`、`canonical_bytes(wire: dict) -> bytes`、`digest(wire: dict) -> str`。
- `PolicyPreconditionError`、`PolicyIntegrityError` 为终止类；两者继承 ValueError 以兼容调用者，但不凭旧 ValueError 文本分类。
- 非正式 `PolicyValue.from_dict(wire)` / `.to_dict()` / `.state` / `.value`：wire 严格字段 `state,value,value_type,unit,evidence_hashes,pending`。state 为 value/missing/domain_conflict；value_type 为 decimal/bool/enum/event_record/calendar_record/market_window；非 value 分支 value=null。pending 为 `origin,code,rule_id,evidence_hashes` 四字段条目；runtime 白名单完全复制规格 §9.2；signed_policy 由 W2 对具体规则二次核验。
- decimal 值 wire 用有限规范十进制字符串；bool 为 exact bool；enum 为明确字符串；复杂记录由对应 F3/W1 封闭解析，不允许任意 JSON 当作已证实输入。evidence_hashes 排序去重但不删除底层来源记录。
- `PolicyRuntimeFixture(*, range_enabled=False, templates=None)`：继承 plain `FinancialFixture`，不是 TestCase；保留 `.bundle/.scoring/.vocabulary/.provider/.feature_repository/.context/.store/.root/.frozen` 和原 `.publish_current/.persist_features/.put_industry/.close`；增加 `.policy_registry`。
- `.put_policy_financial(security_id, values, *, fy_end, units, generation="g1", persist=True)` 以真实财务任务/快照/事实/feature 收据生成证据；values 为 fact_key→原数值，units 必须逐 key 提供；fy_end 无默认，不推测 FY0。
- `.policy_financial_values(security_id, *, current_equity=1.0, current_roe=5.0, current_margin=5.0, current_profit=5.0, annual_roe=(1.,2.,3.,4.,5.), annual_margin=(1.,2.,3.,4.,5.), annual_profit=(1.,2.,3.,4.,5.))` 写 FY2021–2025 真实事实及当期 FY2025、发布并保存对应 feature bundle。它只用于合成测试，不证明真实经济意义。

- [ ] **写失败测试。**

```python
from decimal import Decimal, localcontext

def test_bridge_preserves_v6_float_not_original_decimal(self):
    from ashare_pipeline.formal_policy_values import bridge_v6, decimal_context
    value = 0.1 + 0.2
    self.assertEqual(bridge_v6(value), Decimal(str(value)))
    self.assertNotEqual(bridge_v6(value), Decimal("0.3"))
    with localcontext() as ambient:
        ambient.prec = 2
        with localcontext(decimal_context()):
            self.assertEqual(Decimal("4") + Decimal("0.2"), Decimal("4.2"))
    for bad in (True, float("nan"), float("inf")):
        with self.subTest(bad=bad), self.assertRaises(ValueError):
            bridge_v6(bad)
```

增加未知 reason、signed_policy 非当前规则、decimal 非规范串、复制 wire 之后修改原容器不改变 DTO、错误 value_type、缺失分支偷偷携带 value 等测试。真实夹具签名后的改动必须失败；测试图修改必须在签名前完成。

- [ ] **运行 RED。** `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_values -v`。
- [ ] **实现数值内核和夹具。**

```python
import hashlib
import json
import math
from decimal import Context, Decimal, DivisionByZero, InvalidOperation, Overflow, ROUND_HALF_EVEN

def decimal_context():
    return Context(prec=50, rounding=ROUND_HALF_EVEN, Emin=-999999, Emax=999999,
                   capitals=1, clamp=0, flags=[],
                   traps=[InvalidOperation, DivisionByZero, Overflow])

def bridge_v6(value):
    if type(value) not in (float, int) or not math.isfinite(value):
        raise ValueError("finite V6 numeric value required")
    return Decimal(str(value))

def canonical_bytes(wire):
    return json.dumps(wire, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")

def digest(wire):
    return hashlib.sha256(canonical_bytes(wire)).hexdigest()
```

夹具配置顺序固定：现有 FinancialFixture 的基础 industry/metrics → 新增 security_state descriptor 和三个旧 config → `add_policy_documents` → 将当期 selector 和 AST 的 FY0 同时改为 FY2025 → 如果 range_enabled 则调用 R1 `add_range_documents` → `rehash_documents` → 构造真实签名 bundle。逐年槽位保持各自 FY2021–2025。保存 financial fact 时沿用原真实 fetch/task 路径，但使用明确 units：权益/利润 CNY，ROE/利润率 ratio；不得直接把默认 CNY 的事实当 ratio。

默认 fixture 用三个证券和小数据集；五模板组合测试传 templates 明确映射，不把每条格式单测扩大到全体证券。旧 `tests/formal_policy_fixtures.py` 的 FY0 静态用例不改。

- [ ] **运行 GREEN。** `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_values tests.test_formal_policy_registry tests.test_formal_metric_features -v`。
- [ ] **审查并提交白名单。** 本任务三个文件；提交信息 `feat: define policy values and explicit V6 decimal bridge`。

## Controller ruling
F1 implements scalar values and typed missing/conflict records. Reject nonmissing arbitrary compound dicts; producer-specific compound validators arrive in F3/W1. range_enabled=True integrates R1 add_range_documents and is tested after R1 is accepted; default false scalar/financial fixtures work independently. Decimal wire must obey spec section 3 (fixed notation, strip meaningless zeros, negative zero -> 0), without ambient rounding or changing original V6 values.

## Execution and report contract
Work only in D:/Projects/AShareQiheng/.worktrees/formal-v3-implementation. Python: D:/Projects/AShareQiheng/.venv/Scripts/python.exe. No production data/network, no Git writes, no subagents. Preserve unrelated files. Use apply_patch. Implement with TDD and write report to task-F1-report.md beside this brief. Report RED/GREEN exact commands and output, changed files, self-review and concerns. Return only status, short test summary, concerns, report path. Read skills/test-driven-development and writing-good-tests before editing. Root performs the independent task review and commit. Request controller context for a real contract ambiguity rather than weakening validation.

## Implementation preflight rulings

1. signed_policy in F1 is syntax-only; validate code/rule_id and closed shape,
   and unknown runtime reasons. W2 checks concrete current-rule authorization;
   the plan's non-current-rule test belongs W2, not this context-free DTO.
2. templates is dict[canonical_security_id, template_id] and determines the exact
   frozen ID set and signed membership rows, not only the inherited three IDs.
   Whitelist expands to tests/formal_metric_feature_fixtures.py for a minimal
   optional exchange_rows=None keyword and forwarding via local rows. Preserve
   existing population/default behavior. This avoids copying the entire base
   constructor. Add five-template genuine fixture coverage and old regression.
3. Current roe/margin/profit use separate signed fixture.policy.current.* fact
   keys; annual slots retain fixture.policy.*. Test independently differing
   current and annual FY2025 values without changing their explicit periods.
4. Policy-only facts intentionally produce a blocked legacy V6 feature bundle.
   Verify exact signed AST/facts/units and authenticate the persisted blocked
   receipt with the existing require_complete=False path. Do not weaken the old
   completeness gate or require policy-derived values from it; F2 implements
   the independent optional projection. R1 source stability permits provisional
   range_enabled integration now, but both tasks still require clean reviews.
5. The new fixture may consistently name all four current slots (including
   equity) fixture.policy.current.*. Prior wording identified only the three
   colliding annual keys, not an equity naming restriction. Signed AST/fact
   identities must match; the old static fixture remains unchanged. F2 consumes
   signed selectors/AST rather than guessing test-only fact keys.
