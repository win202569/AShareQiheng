# Formal Policy Stage B3 Window, Evaluation and Batch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用真实来源记录形成日历/行情双轴证据，计算全部政策并原子发布完整冻结宇宙结果。

**Architecture:** 日历和行情工厂消费 B1 收据，F2/F3 提供财务/状态输入；纯计算不拥有证明资格。唯一仓库在受信任 provider 和数据库屏障内重验全部成员及原始文件，成功后发布共享撤销能力的 evidence/result 批次。缺失是可保留的证券结果，完整性失败则撤销整批。

**Tech Stack:** Python、unittest、Decimal、SQLite 短 writer exclusion、现有 `_metric_batch_guard` 和同根 Context 工厂。

**Spec:** [Stage B design](../specs/2026-09-12-formal-policy-stage-b-design.md) §2、3、6、8–10；[总控](2026-09-12-formal-policy-stage-b.md)、[B1](2026-09-12-formal-policy-stage-b1-range-foundation.md)、[B2](2026-09-12-formal-policy-stage-b2-financial-state-evidence.md)。

## Global Constraints

任何否决都不能消除待补。

阶段 B 不给停滞状态额外扣 T 分。

这里不执行适配器、不替换既有 V 分位数、不应用最终维度上限、不重算 C/Sc/B/R。

包括最终回滚/关闭失败在内的任何异常均撤销未完成批次及其派生对象。

---

## 文件图和执行条件

新建 `ashare_pipeline/formal_policy_market.py`（覆盖组合、行情窗口及后续采集请求规划）、`formal_policy_evaluator.py`（纯规则和聚合）、`formal_policy_repository.py`（闭包权能与全批次）。对应新建 `tests/test_formal_policy_market.py`、`test_formal_policy_evaluator.py`、`test_formal_policy_repository.py`、`test_formal_policy_batch_guards.py`、`test_formal_policy_integration.py`。

W1 仅在 R4/F1 接受后执行，修改 `formal_range_source.py` 激活真实日历证明驱动的 market request；W2 在 F3/W1 接受后执行；W3 串行集成各仓库；W4 验证后才可宣布 B 完成。夹具扩展由原所有者协调修改。

## W1：区间日历、行情请求和价格/否决双轴

**Files:** Create `ashare_pipeline/formal_policy_market.py`, `tests/test_formal_policy_market.py`; Modify `ashare_pipeline/formal_range_source.py`, `tests/formal_range_fixtures.py`, `tests/formal_policy_runtime_fixtures.py`。

**Interfaces:**

- Consumes: genuine RangeBinding、RangeObservation、FormalRangeStore；F1 canonical/Decimal 内核。
- Produces: `VerifiedCalendarCoverageV1` 和 `VerifiedMarketWindowV1`，构造器拒绝调用者；两者 `.to_dict()`、`.canonical_bytes()`、`.require_current()`；字段完整包含规格 §3/6 身份，不允许只保留交易日数组。
- `FormalPolicyMarketRepository(range_store)`；`.select_calendar(binding, as_of_utc) -> CalendarSelection`；`.select(security_id, as_of_utc, *, binding) -> MarketSelection`。CalendarSelection 提供 `.coverage`（genuine proof 或 None）、`.pending/.lineage/.selection_hash/.recheck()`；MarketSelection 提供 `.window/.pending/.lineage/.selection_hash/.recheck()`；window 内同时保存价格轴和 20 日轴，即使其状态为 incomplete。
- source 新方法 `.market_requests(security_id, *, calendar_coverage: VerifiedCalendarCoverageV1) -> tuple[FormalRangeRequestV1,...]`，只接受 genuine 同根/交易所证明，按实际交易日及签名自然日上限确定闭区间，第 1 页起步；不能把 covered 以外日期写入行情请求。
- 私有 `_require_calendar_coverage(proof, *, binding) -> dict` 返回当前已认证覆盖的脱离 payload，检查实际原始成员；仅由本模块闭包创建并由 source 的受保护依赖捕获，不接受外部 validator 替换。source 在实例构造时本地导入并捕获它，避免模块顶层循环导入；此时模块类型定义须已完成。私有市场 request mint 内也执行该检查，不能绕过公开方法自行造覆盖 hash。
- `plan_next_window_request(security_id, as_of_utc, *, binding, range_store) -> FormalRangeRequestV1 | None` 是采集计划入口，不联网、不 mint 政策结果。按已证明最新交易日区间先补市场，再决定是否需要更老日历；最新 20 日始终需要可判定，价格可在最近有效日及其后完整时提前停止；无价回溯到 250 实际交易日停止。
- 纯 `evaluate_window(trading_days: tuple[str,...], daily_rows: dict[str,dict]) -> dict`，仅返回非正式 `price_state,price,price_date,stale_days,stale_at_least,veto_state,pending`，其输入必须经调用层验证 sorted/unique/ISO/冻结日/最多250。
- Fixture 新增 `.put_window(security_id, *, trading_days, rows, generation="g1", missing_calendar_dates=(), omit_pages=())`，经真实 R2/R3 生产；不接受 stale_days、veto、confirmed_no_price 参数。`rows` 只含原始 permission/volume/turnover/close 数据。

- [ ] **写失败测试。** 先测纯双轴，再测相同场景的 genuine 来源路径。

```python
from datetime import date, timedelta

def test_tail_veto_survives_older_gap(self):
    from ashare_pipeline.formal_policy_market import evaluate_window
    end = date(2026, 8, 31)
    days = tuple((end - timedelta(days=249-i)).isoformat() for i in range(250))
    rows = {day: dict(coverage="covered", exchange_allows_trading=True,
                     volume="0", turnover="0", close={"state": "unavailable",
                     "reason": "source_reports_no_trade"}) for day in days}
    del rows[days[0]]
    result = evaluate_window(days, rows)
    self.assertEqual(result["veto_state"], "proven")
    self.assertEqual(result["price_state"], "incomplete")
    self.assertIsNone(result["price"])
```

这只是纯函数的显式合成日期测试；正式日历不能用 timedelta 推测哪个自然日交易。真实夹具须逐日来源证明，并含法定休市/节假日场景。覆盖矩阵：stale 0/1/19/20/249、窗口外250；尾20缺口无反证→pending；尾20有有效成交但无 close→否决clear/价格incomplete；完整250无成交→confirmed_no_price_250 + proven + market_evidence_missing；20–249旧正价和否决共存；最新有效价之前的缺口不影响已完整近区间。

日历矩阵：每个自然日一个 exact bool；稀疏交易日列表只能在有签名且已实现的完整性合同下补非交易日；请求区间与证明子区间分别保存；整份文档分页未验证不能部分冒充完整；重叠矛盾/错交易所/根/代际/日期重复；来源 date_only 不用 captured/as_of 补成有利时刻；冻结日未被证明交易日为失败而非退到前一天。

- [ ] **运行 RED。** `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_market -v`。
- [ ] **实现完整区间组合和双轴内核。** `.select_calendar` 按完整页面组核验 page_count/record_count/lineage，展开有来源依据的自然日判定；只组合无矛盾、同根同版本同交换所的成员。missing 行不补零，缺公开时点保留待补。所有原始内容/请求/收据作为组合依赖保存并可重验。

```python
from decimal import Decimal

def evaluate_window(trading_days, daily_rows):
    days = trading_days[-250:]
    effective = {}
    for day in days:
        row = daily_rows.get(day)
        if row is None or row["coverage"] != "covered":
            effective[day] = None
        else:
            effective[day] = (row["exchange_allows_trading"] is True
                              and Decimal(row["volume"]) > 0
                              and Decimal(row["turnover"]) > 0)
    tail = [effective[day] for day in days[-20:]]
    veto = ("clear" if any(v is True for v in tail) else
            "proven" if len(tail) == 20 and all(v is False for v in tail)
            else "pending")
    result = dict(price_state="incomplete", price=None, price_date=None,
                  stale_days=None, stale_at_least=None, veto_state=veto, pending=[])
    for stale, day in enumerate(reversed(days)):
        active = effective[day]
        if active is None:
            result["pending"].append("market_coverage_missing")
            return result
        if active:
            close = daily_rows[day]["close"]
            if close["state"] != "positive":
                result["pending"].append("market_price_missing")
                return result
            result.update(price_state="positive_close_complete", price=close["value"],
                          price_date=day, stale_days=stale)
            return result
    if len(days) == 250:
        result.update(price_state="confirmed_no_price_250", stale_at_least=250)
        result["pending"].append("market_evidence_missing")
    else:
        result["pending"].append("calendar_coverage_missing")
    return result
```

在该内核前校验 covered 行的 exact permission、有限非负 volume/turnover、明确单位和 positive close>0；不能依赖 Decimal 字符串可解析就接受无穷。具体 domain_conflict 原因由来源层保存，并与上述通用 pending 合并，不被算法早返回删除。前置校验也不得把内核允许的无关更老领域缺口提升为整批错误；真实来源完整性失败仍抛错。

市场计划入口顺序：先验证 binding/当前已存页 → 无日历取首日历请求 → 有日历先补其中尚无有效收据的行情请求 → 两轴已可判定则停止 → 不足 250 且仍需旧价格时取前一个自然日分段 → 未完成分页只补其未完成页。该入口不把领域缺口改成已无成交；任务错误由 R4 处理，避免无限重复同一失败请求。

- [ ] **运行 GREEN。** `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_market tests.test_formal_range_source tests.test_formal_range_store tests.test_formal_context_schema -v`。
- [ ] **审查并提交白名单。** 本任务五个文件；提交信息 `feat: prove calendar coverage and independent market window outcomes`。

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

## W3：唯一全冻结批次入口与失败撤销

**Files:** Create `ashare_pipeline/formal_policy_repository.py`, `tests/test_formal_policy_repository.py`, `tests/test_formal_policy_batch_guards.py`; Modify `tests/formal_policy_runtime_fixtures.py`。

**Interfaces:**

- Consumes: same-store feature/context/range 仓库、FormalMetricCurrentInputProvider、FormalMetricContextRepository、`_metric_batch_guard(provider, store)`、genuine scoring/policy registry；F2/F3/W1 的 current selections。
- Produces: `FormalPolicyRepository(feature_repository, context_repository, range_store, *, registry_signature_verifier)`；`.build_batch(frozen_input_hash, *, scoring_registry, policy_registry) -> VerifiedPolicyResultBatch`。
- 新闭包私有 proof 类型 `VerifiedPolicyEvidenceBatch`、`PolicyDecision`、`PolicyResult`、`VerifiedPolicyResultBatch`：构造器拒绝；`.require_official()`、`.to_dict()`、`.canonical_bytes()`；子结果含所属 batch identity，跨批次组合拒绝。最终 batch 属性 `.security_ids/.results/.evidence_batch/.batch_hash`，results 按 security_ids 顺序 tuple。
- 单证券 PolicyResult 属性 `.security_id/.decisions/.pending_requirements/.dimension_caps/.pool_prohibitions/.states/.normalization_basis/.evidence_state`，纯 W2 字典不能通过其 require_official。
- `PolicyRuntimeFixture(range_enabled=True)` 新增 `.policy_repository`；`.build_policy_batch()` 使用 fixture 当前真实 frozen/scoring/policy；`.populate_policy_evidence()` 为每个冻结成员写 industry、显式清晰状态、F2 财务及 W1 日历/行情，真实小规模 producer receipts；默认不省略证券。

- [ ] **写失败测试。**

```python
def test_complete_enumeration_includes_pending_security(self):
    from tests.formal_policy_runtime_fixtures import PolicyRuntimeFixture
    fixture = PolicyRuntimeFixture(range_enabled=True)
    self.addCleanup(fixture.close)
    # 完整 universe 已存在，行业/状态/行情仍未覆盖；未分配模板不要求伪造财务。
    batch = fixture.build_policy_batch()
    batch.require_official()
    self.assertEqual(tuple(result.security_id for result in batch.results),
                     tuple(batch.security_ids))
    self.assertEqual(len(batch.results), 3)
    self.assertTrue(all(result.pending_requirements for result in batch.results))
```

增加全图/入口替换、跨库/根/证券/模板/冻结/批次、伪造scoring/policy、缺 universe、配置缺失与歧义、provider 未发布、copy/deepcopy/object.__new__、实例影子方法和类方法替换；未知membership不造五套规则。已赋模板但无 provider 是失败，和上述“模板未知无需取财务”不同。

屏障专例在第一证券读完后修改第二证券、先缺后有、equal-leading ambiguity、provider 重入发布且内部吞错、DB 写入、原始文件改动但 DB 未变、source 配置替换、最终 rollback/close 抛错；任何被测试钩子捕获的未发布子对象均不能通过 require_official。钩子只在测试替换实际依赖，不能添加生产公开 `skip_verify`。

- [ ] **运行 RED。** `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_repository tests.test_formal_policy_batch_guards -v`。
- [ ] **实现闭包和生命周期。** 按 `formal_metric_engine._install_engine` 的精确类/方法/来源依赖捕获模式建立仓库和 proof 记录；不用公共 `verified=True`、可读 nonce 或自报 hash 作为权能。F2/F3/W1 `.recheck()`、context `.recheck_batch()`、九角色源文件重验全部进入最终检查。将值和来源规范 payload 先脱离外部引用，昂贵取证阶段不持有 writer lock。

以下是本任务私有工厂的控制流，`prepare/read_and_recheck/mark_published/revoke` 均在同一闭包内定义，不导出：

```python
def publish_under_guard(provider, store, prepare, read_and_recheck,
                        mark_published, revoke):
    prepared = None
    try:
        with _metric_batch_guard(provider, store) as guard:
            prepared = prepare()
            read_and_recheck(prepared)
            def finalize():
                read_and_recheck(prepared)
                mark_published(prepared)
                return prepared
            result = guard.finalize(finalize)
        return result
    except BaseException:
        if prepared is not None:
            revoke(prepared)
        raise
```

闭包内 prepare 自行读取冻结宇宙、加载 source v2 配对、解析所有行业，逐证券读取适用证据并调用 W2；返回共享初始 false publication 的完整根和子对象。read_and_recheck 检查真实 provider/DB/context/feature/current range selection/原始 bytes 及入口依赖，比较完整身份，也检查缺失仍然缺失。mark_published 只改变闭包 publication；revoke 对同批次全部子对象生效。这些回调不能由公共调用者提供。外层捕获覆盖 context-manager 的关闭异常，不能只在 guard.finalize 内撤销。

批次 hash 计算依赖顺序：各来源/selection payload → 各非正式 rule input/decision payload → evidence batch payload → result batch payload；各自先算无自身 hash 的内容，子对象之后附加所属 batch hash 但不反向改变父身份。保存 parent_link 单独参与资格验证，避免 selfhash/circular hash。

- [ ] **运行 GREEN。** `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_repository tests.test_formal_policy_batch_guards tests.test_formal_metric_batch_guard tests.test_formal_metric_engine -v`。
- [ ] **审查并提交白名单。** 本任务四个文件；提交信息 `feat: publish revocable complete-universe policy result batches`。

## W4：五模板、恢复与旧合同组合验收

**Files:** Create `tests/test_formal_policy_integration.py`; Modify `tests/formal_policy_runtime_fixtures.py`（仅组合夹具）、本轮实现确有测试暴露问题的对应代码/测试。每个修复单独说明和最小范围；禁止顺带重构旧模块。

**Interfaces:** Consumes W3 唯一公开入口和 R4 恢复入口；不产生新的公开产品 API。

- [ ] **写完整场景测试。** 五模板映射必须在签名前生成，使用至少五个明确证券 ID；一个非周期同模板证券、一个已证实硬否决兼有缺失输入证券、一个未知 membership 证券。测试断言不以分数/入池截断 universe。

```python
def test_rebuild_is_byte_identical_without_new_input_generation(self):
    from tests.formal_policy_runtime_fixtures import PolicyRuntimeFixture
    fixture = PolicyRuntimeFixture(range_enabled=True)
    self.addCleanup(fixture.close)
    fixture.populate_policy_evidence()
    first = fixture.build_policy_batch()
    second = fixture.build_policy_batch()
    self.assertEqual(first.canonical_bytes(), second.canonical_bytes())
    self.assertEqual(first.batch_hash, second.batch_hash)
```

第二个组合测试在真实 source/task 中添加合法新 generation，更正一个观察并重发完整 provider，断言新批次身份改变、旧字节仍在、旧历史 proof 不满足新消费 current；第三个中断 worker 后重开临时 StateStore，重验已有页不重复 HTTP，最终规范结果与连续运行一致。

- [ ] **运行新增测试，确认其针对真实缺口失败或已有正确实现通过。** 集成任务不为制造 RED 人工破坏代码；如测试已通过，记录这是对已实现行为的新增覆盖。发现缺陷才进行新的 RED→修复→GREEN。
- [ ] **最小修复并核对隔离。** 测试拒绝所有真实网络调用；临时 DB 路径必须在 fixture TemporaryDirectory 内。增加如下测试断言，证明没有偷偷生成最终评分或池：

```python
wire = fixture.build_policy_batch().to_dict()
self.assertNotIn("strong_pool", wire)
self.assertNotIn("wait_pool", wire)
self.assertNotIn("final_scores", wire)
for result in wire["results"]:
    self.assertNotIn("eligible", result)
    self.assertNotIn("final_score", result)
```

- [ ] **运行全受影响回归。** 使用一个完整命令，不重复导入 TestCase 制造用例数：

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_range_contract tests.test_formal_range_source tests.test_formal_range_store tests.test_formal_range_worker tests.test_formal_policy_values tests.test_formal_policy_financial tests.test_formal_policy_state tests.test_formal_policy_market tests.test_formal_policy_evaluator tests.test_formal_policy_repository tests.test_formal_policy_batch_guards tests.test_formal_policy_integration tests.test_formal_policy_contract tests.test_formal_policy_registry tests.test_formal_policy_registry_guards tests.test_formal_sources tests.test_formal_context_schema tests.test_formal_context_repository tests.test_formal_feature_repository tests.test_formal_feature_store tests.test_formal_metric_context tests.test_formal_metric_features tests.test_formal_metric_batch_guard tests.test_formal_metric_engine tests.test_state_store -v
```

若执行较久，保留 session ID，按不超过 60 秒的检查窗口汇报新进展；不反复重启测试。检查 `git diff --check`、所有旧 V2–V6 DDL 变化、真实文件改动清单，以及数据/SQLite/WAL/SHM/进度路径未进入暂存区。

- [ ] **主代理核实并提交。** 记录真实用例数、失败数、耗时和修复说明；独立规格审查/代码审查通过后，仅提交本任务代码与测试白名单，提交信息 `test: verify policy evidence recovery and complete-batch compatibility`。不自动合并 main、推送、实爬或公布股票池。

## 完成报告

仅在以上测试和逐项规格覆盖检查有新证据后报告阶段 B 完成。报告区分“软件已支持”“离线合成测试已通过”“生产证据仍缺失”，不能把任何一个当作另一个。下一阶段是利润正常化后的 V 指标适配与完整同行重排设计/实施，不是给旧分数直接改名。
