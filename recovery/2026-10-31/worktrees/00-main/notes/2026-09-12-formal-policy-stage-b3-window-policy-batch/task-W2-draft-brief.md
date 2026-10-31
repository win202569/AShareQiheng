# Task W2 draft brief

DRAFT — NOT DISPATCHED. F3/W1 accepted handoff, final BASE and execution contract must be added before implementation. This is exact task extraction for preparation, not authorization to skip W1.

## Global constraints

任何否决都不能消除待补。阶段 B 不给停滞状态额外扣 T 分。这里不执行适配器、不替换既有 V 分位数、不应用最终维度上限、不重算 C/Sc/B/R。保持 v1 签名规则不变，量化事件消费缺口显式保留。不联网、生产签名、实爬、评分、选池、覆盖数据、合并 main 或推送。

## W2：纯政策判定、正常化依据和效果聚合

**Files:** Create `ashare_pipeline/formal_policy_evaluator.py`, `tests/test_formal_policy_evaluator.py`。

**Interfaces:**

- Consumes: F1 PolicyValue、脱离来源的 F2/F3/W1 输入、阶段 A 规则的规范字节副本；这些是纯函数参数，不是来源资格。
- Produces: `quantile80(values: tuple[Decimal,...], method: str) -> Decimal`；`evaluate_rule(rule: dict, *, security_id: str, applicability: str, values: dict, annual: dict, market: dict | None) -> dict`；`aggregate_decisions(decisions: tuple[dict,...]) -> dict`。
- applicability 限定 applicable/not_applicable/unresolved；values/annual 按 selector hash 索引；缺键是显式 missing，不默认为 false。仅 W3 能把真实行业证明转换到纯 applicability 参数。
- decision 固定规格 §8.1 字段；聚合固定 `decisions,dimension_caps,pool_prohibitions,states,normalization_basis,pending_requirements,evidence_state`。pool_prohibitions 展开 strong/wait，保留每个效果全部 rule/evidence trace；无最终分数或 ready/eligible 字段。

- [ ] **写失败测试。**

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

其余测试使用 `numeric_rule/boolean_rule/cyclic_rule/market_rule` 的实际签名形状（从 `tests/formal_policy_fixtures.py` 导出的规则或已解析图取得，不自行造简化版）：比较五运算符、exact bool/enum、>=边界、两个指标必须同时达标、五利润中位数/取低、负利润与零、非周期不要求年度、归属未知pending、多维cap取min、多禁池union、所有trace保留、matched 自身附带 pending。

市场专例：尾20已证实而价格incomplete，整体pending但仅释放由该20日证明授权的 pool_prohibition；不能同时释放其他依赖整体命中的 cap/status/利润替换。confirmed_no_price_250 必须同时保留 runtime/market_evidence_missing 和双池否决。未命中也不清除输入层已认证的待补。

- [ ] **运行 RED。** `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_evaluator -v`。
- [ ] **实现。** Decimal 运算始终用 F1 独立 context；四个判定状态明确分支；作用效果逐条绑定实际证明输入。算法内核如下：

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

当周期命中时，normalization_basis 保存原当期利润、五年原值/证据、排序第三值 median、minimum_current_and_five_fy_median_v1 结果及已签名 V dependency 清单；不调用 V adapter。cap 数值与允许维度从已解析效果读取，原周期 G/M=80 由合同验证，不硬编码成任意政策默认值。所有 effect/trace 排序规范化，去重仅作用显示键，底层理由全部保留。

- [ ] **运行 GREEN。** `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_evaluator tests.test_formal_policy_values tests.test_formal_policy_contract -v`。
- [ ] **审查并提交白名单。** 本任务两个文件；提交信息 `feat: evaluate policy decisions without erasing pending evidence`。


## Binding spec excerpt

## 8. 政策执行和结果结构

### 8.1 规则判定

每个模板活动规则恰有一条 `PolicyDecision`：rule_id、role、semantic_id、template_id、security_id、definition_hash、input/evidence 引用、实际操作数/阈值/算法版本、evaluation_state、proven_effects、pending_requirements、trace。没有模板时证券结果记录适用性待补而不伪造五套模板判定。

evaluation_state 只有 matched、clear、not_applicable、pending_evidence。clear 表示本条有足够证据证明未命中，不表示公司整体安全。not_applicable 需要已验证适用性依据，不以输入缺失替代。

规则执行顺序不影响结果，具体行为为：

| 规则族 | 执行 |
| --- | --- |
| numeric_redline | 对真实标量执行签名 lt/lte/gt/gte/eq 与同单位阈值；非正权益固定 lte/0 |
| boolean_state / enum_state | 精确类型匹配显式 expected/values；缺失不能作 false |
| cyclic_protection | 清单内且完整证据下，当前 ROE 与利润率分别 >= 自身五年 80 分位才命中；二者必须同时满足 |
| market_liquidity | 分别消费价格轴和 20 日否决轴，不以价格缺失推出无成交 |

周期 quantile_method 只能使用规则显式登记的 linear_type7_v1 或 nearest_rank_v1：五值升序，前者 h=(n-1)*0.8 并线性插值，后者取一基 ceil(n*0.8)；五年利润中位数取排序第三个。命中时正常化利润=min(当期利润,五年利润中位数)，记录 G/M 各 80 分上限、cyclic_top 状态和已签名池限制。未命中保留判定轨迹，不输出利润替换或封顶。不存在默认生产分位数算法。

一般规则缺少必需操作数时不得执行未证明的 on_match 效果。市场规则是明确的双轴组合：价格或否决轴待补时整体判定为 pending_evidence，仍可保留独立 20 日证明允许的 pool_prohibition；不能把其他依赖整体匹配的附加效果一起放行。两个轴齐全时，按 20 日否决谓词判为 matched 或 clear，并只产生已签名的相应效果。

某条已命中规则的 on_match 本身可要求 pending_evidence；此时 matched 与待补要求可以同时存在。证券证据完整度检查所有 pending_requirements，而不是只看 evaluation_state。

### 8.2 聚合与输出权限

`PolicyResult` 包含：所有规则判定、同维最严 cap、strong/wait 禁止集合、带所有理由的独立状态、完整利润正常化依据、待补清单和证券级证据状态。多个 cap 取最小上限，池禁止取并集，重复效果可合并显示但其全部规则/证据来源必须保留。待补不能被已知否决、去重或早返回移除。

`VerifiedPolicyResultBatch` 包含完整冻结证券清单、各证券结果和真实 evidence batch；允许其中有待补证券。完整枚举/完整性验证成功与每证券证据齐全是两个概念。计数等审计摘要从结果导出，不接受人工输入“ready/eligible”覆盖字段。

正常化依据保存原利润、五年值及年度证据、median、实际取低结果和签名 V 依赖清单。这里不执行适配器、不替换既有 V 分位数、不应用最终维度上限、不重算 C/Sc/B/R。阶段 C 必须在全冻结宇宙重建受影响指标的完整同行样本，包含非周期同行；不能拿本阶段结果给旧分数改名。


## Pending handoff checks

Obtain W1 accepted actual DTO/value shapes and F1/F3 original-owner pure-value operations. Pure evaluator inputs are never proof capabilities. Rules must retain actual signed shapes; no simplified alternate schema, implied defaults or quantified-event activation. F3's accepted user ruling is: v1 consumes only existing signed boolean/enum event flags; closed event_record DTO support is not quantified-event policy consumption. Do not invent pending decisions for nonexistent quantified-event rules; record the capability gap separately. Confirm complete runtime and signed-policy pending codes and trace identities at handoff. Shared context precision must not affect computations. No implementation started.
