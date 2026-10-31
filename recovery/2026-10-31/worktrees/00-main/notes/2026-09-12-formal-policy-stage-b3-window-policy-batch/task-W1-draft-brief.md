# Task W1 implementation brief

ACTIVE — dispatched from accepted BASE
`a90faf4f67f9371df71adbc63415e702f8f4016c` after R1–R4/F1–F3 and the
P1/P2 diagnostic full-suite gate were accepted. The historical filename is
retained so prior ledger links remain valid.

Work only in
`D:/Projects/AShareQiheng/.worktrees/formal-v3-implementation`. Write the final
implementation report to this plan workspace as `task-W1-report.md`, including
the exact RED and GREEN commands, counts, elapsed times, exit codes, changed-file
list, and remaining limitations. Do not commit, stage, push, merge, or modify
the master plan/ledger; the controller exclusively owns Git and task state.

## Controller interface rulings (supersede original five-file scope)

Read task-W1-interface-audit.md alongside this brief for the concrete unchanged
interface locations. Root verified the audited contract/store/source/worker
boundaries against the accepted R4 and P1/P2 checkpoints. These rulings are now
the active W1 scope and supersede the older pre-dispatch cautions at the end.

The exact W1 code/test whitelist is amended to 13 paths: the original five below,
plus formal_policy_values.py and test_formal_policy_values.py; formal_range_store.py
and test_formal_range_store.py; formal_range_worker.py and test_formal_range_worker.py;
formal_range_contract.py and test_formal_range_contract.py (production files under
ashare_pipeline/, test files under tests/). Changes in these additional files are
limited to the integration boundaries specified here, not general refactoring.

1. Add a separate original-owner binding planning authority returning current
   market/calendar configs and root/source-role/binding/rule/exchange identity.
   It reads original private records and validates current dependencies. Keep
   the existing five-anchor _range_binding_authority return contract unchanged.
2. Add narrow Store.resolve_planning_binding(binding) returning the Store-owned
   reconstructed binding/source. Authenticate caller identity with the owner
   reader; resolve root and all signed roles through this Store's StateStore and
   verifier; compare full authenticated semantic identity. Genuine caller and
   reconstructed bindings may be distinct instances. Factory result must still
   bind by exact object identity to the reconstructed binding. A genuine binding
   whose root is absent from the Store fails preconditions, never domain missing.
   Factor the existing internal load_binding path to a typed identity helper;
   do not manufacture fake task payloads or expose a caller registration hook.
3. Source construction eagerly seals both calendar and market configurations
   and their exact implementations. A source-owned range_config(request) selector
   authenticates the request and binding before selecting already-sealed config.
   Fetch, continuation, replay and Worker retry/page budgets use this same actual
   request-config relationship. No lazy mutable registry/property lookup grants
   authority. Worker calendar tests alone do not establish market budget support.
4. Add strict calendar_record/market_window pure DTO validators inside the F1
   original value owner, covering them in its dependency checker. DTOs never
   become genuine coverage proofs or a proof-construction/registration API.
5. Replace original first-constructor import/capture wording with completed eager
   two-module initialization of original proof type/current/wire anchors. Support
   source-first, market-first and fresh-process imports without mutable first-use
   authority capture. Only the Market owner mints genuine calendar/window proofs.

Mandatory added regression matrix: unchanged five-anchor contract; original-owner
planning identity ignores replaced public properties and rejects forged/stale/
mutated bindings; owning-Store root absent fails; semantically equal distinct
bindings resolve; factory receives reconstructed binding; identity mismatch fails;
distinct calendar/market implementations sealed eagerly; genuine market requests
use distinct signed retry/cooldown/page budgets; import orders and cold restart.

Frozen-membership handoff: Source requests authenticate acquisition parameters,
exchange and genuine calendar lineage, not membership of a particular frozen
universe. The prescribed API has no universe capability. Per design section2,
W3/pre-batch orchestration loads the genuine frozen universe, iterates its exact
canonical security_ids and alone supplies membership authority; W3 binds and
rechecks it at publication. W1 must not claim membership from a canonical ID or
calendar proof. See task-W1-interface-audit.md follow-up and its required W3
nonmember/mutation/missing-Universe tests. Keep current W1 API, no hidden authority.

Final compatibility must also include all newly touched modules (range_contract,
range_worker, policy_values), not only the original four-module command. Develop
using focused TDD, freeze for static review, then run the final combined command
once after review fixes. Preserve logs and exact run status; no duplicate suites,
production network, or weakening authentic checks to shorten execution.

## Global Constraints

冻结时点仍为北京时间 2026-08-31 15:00，即 `2026-08-31T07:00:00+00:00`；SH/SZ/BJ 普通 A 股、五模板、七维权重、指标级同行资格、严格排除和证据门槛全部保持原合同。强池最多 20、等待池最多 50、行业上限 4/10 不变。本阶段不按最终入池资格筛选取证宇宙。

不改写旧 V2–V6 DDL、已有财务公式或已发布字节；不覆盖数据、SQLite、WAL/SHM、进度和历史结果；不自动合并 main 或推送。

以下不属于本阶段：真实生产来源或经济映射审批、生产签名、全市场实爬、定时调度、利润调整后 V 指标适配器、同行重排、最终置信度/分数/等级、选池、正式发布持久化。软件可支持后续增量采集，但本阶段开发验收不运行生产采集。

区间采集与收据落库在评分读取之外完成；不在跨证券数据库事务内发网络请求。

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


## Pre-dispatch cautions
R3 accepted at3c3b3c1 has source-owned _range_observation_authority(), returning
the immutable tuple (original RangeObservation type, original unbound
RangeObservation.require_current, original unbound RangeObservation.to_dict),
with no mint, for eager capture. Obtain observations through the owned genuine
Store, and enforce same-store/root; a current observation is not freeze visibility.
F3 accepted at d2cc791 (144 tests, clean independent review) now owns
original-module private operations: _policy_value_operations returns
the original parser, explicit unbound serializer and owner dependency checker.
New calendar/market DTO validators must stay inside that owner-initialized check
boundary; do not capture replaced public PolicyValue methods at consumer import.
F3's _read_authenticated_policy_registry reads original closed proof records.
These are trusted private implementation helpers, not caller registration APIs.
R3 observations prove authenticated source bytes, not freeze visibility. Both
unresolved null pairs and structurally valid non-null date-only effective/hash
claims require independent temporal proof in W1; non-null source hash alone is
not proof. Missing proof yields visibility_unproven, not a fabricated instant.
Do not use the old single-day Context bootstrap binding as range authority.
R3 and F3 handoffs are accepted; R4 genuine worker/accessor handoff is pending. Original
constructor-time local import wording must not revive first-use mutable verifier
trust: integrate the genuine calendar proof authority using completed eager
initialization, with source-first/market-first/restart tests and no caller hook.
The master F1/W1 preflight also assigns closed calendar_record/market_window value
validators to W1; final whitelist must include formal_policy_values.py and its
covering tests, not merely accept arbitrary compound dicts. Values remain pure
non-authoritative DTOs. Runtime/range fixtures have one owner in this task, and
F3 must finish shared values/runtime-fixture edits first. No actual scheduler,
network, data capture, production economic mapping or scoring is authorized.

Pre-dispatch interface audit still to resolve with accepted R4: the Market
repository receives only range_store, whereas creating first/previous range
requests currently requires a genuine Source with its configured implementation
registry. Store exposes current lookup by request fingerprint but not its source
factory publicly. Do not invent a fake transport/parser or reconstruct request
authority from saved JSON to bridge this. Check the final R4 accessor/API handoff
and resolve the smallest original-owner read/planning capability before assigning
W1's final whitelist; any added Store helper requires an explicit recorded scope
amendment. This is a preparation finding, not implemented functionality.

Second integration check: R4's initial worker implementation selects the calendar
config for retry/page budgets because only calendar requests exist before W1.
When W1 activates market requests, verify worker execution and resume consume the
actual request's authenticated range config, not a calendar config with different
signed limits. If final R4 still has this calendar-only assumption, amend W1's
worker-file ownership explicitly and test distinct calendar/market budgets using
genuine market requests; do not treat calendar tests as market support evidence.

Root will add complete global constraints and relevant binding spec excerpts
before dispatch. This draft is requirements preparation only, not an active task.


## Binding spec excerpts for W1

## 3. 身份、证据对象与读取资格

每个正式批次共同绑定：合同/算法版本、根清单哈希、九角色哈希、policy registry 合同哈希、冻结输入哈希、宇宙/证券集合哈希、冻结时点、行业批次身份，以及全部实际读取证据的内容身份。证券级对象另外绑定证券、交易所、模板和适用规则。缺失标记也必须绑定它所对应的请求和当前代际。

证据分三种，不以一个 `verified=true` 混淆：

- 已验证的值及其来源。
- 对特定当前请求的已验证缺失/领域问题记录；证明“当前证据不足”，不证明该事实为零或为假。
- 无法建立可信读取的失败诊断；不属于可供政策计算消费的证据对象。

公开对象提供 `require_verified()`、规范字节、只读审计视图和内容哈希。普通构造、复制、继承替换、字段/方法影子或跨仓库拼装不得制造正式资格。仍沿用既有可信 Python 运行时边界，不新增对任意解释器篡改的防御承诺。

规范序列化使用严格 JSON、UTF-8、固定键排序，无 NaN/Infinity；精确区分 bool/int/float/string/null。集合显式去重排序，具有时序含义的交易日、年度和分页序列按合同顺序存储。新 Decimal 结果用无指数、无无意义尾零的十进制字符串，负零规范成 `0`；原 V6 数值字节/身份单独保留，不通过新规范化改写历史记录。哈希字段不包含自身；子对象先形成内容身份，再形成外层批次身份，避免自引用。

运行耗时、重试次数、当前机器时间和日志行不进入语义结果哈希。真实抓取时间、请求/收据和来源代际属于证据身份，必须保留。相同的已验证输入和合同产生相同结果；来源更正产生新身份，即使数值相等也不能冒用旧证明。

历史对象可用于准确的历史审计，不承诺永久代表“当前最新”。进入新的批次或后续阶段 C 时必须重新验证同根、同冻结输入及来源关系；序列化文件或旧进度本身不授予当前资格。


## 6. 日历区间与行情窗口值格式

### 6.1 日历覆盖证明

`VerifiedCalendarCoverageV1` 显式绑定 `formal-calendar-coverage-v1`、registry_manifest_hash、日历 descriptor/config ID、交易所、冻结日、request/parser/mapping/normalizer 版本、有序请求指纹及 snapshot/receipt 身份、upstream/refresh generation、实际请求闭区间，以及另列的 covered_start/covered_end 和其中每天的显式 is_trading_day、升序交易日列表。

covered 区间必须被真实请求区间覆盖；其中每个自然日须恰有一条来源支持的日历判定。相关请求的分页须按签名合同完整验证，不能跳过未验证页面。证明区间内缺日、重复日或无法解释的来源冲突不能形成完整覆盖；普通的区间外领域缺口不使区间内完整覆盖失效，但若其揭示整个来源/请求的完整性失败则仍终止尝试。这样可保留请求范围内已独立证明的较短区间，不强迫最近有效价之前的日历领域缺口成为当前价格的依赖。

可将具有相同根、版本和无矛盾重叠日期的相邻区间组合；组合时重新验证每个成员。日历来源若仅返回交易日列表，只有已签名且已实现的响应完整性合同能证明该请求区间内未列出的日期均非交易日，才可形成上述日历值。不能仅凭数组排序、长度、周一至周五或已有 VerifiedCalendarBinding 证明区间完整。

窗口搜索从冻结日向前，逐步取得经证明的实际交易日。冻结日必须在所属交易所日历中被证明为交易日；否则是冻结输入/日历不一致的失败，不将日期自动改为前一交易日。满窗口取包含冻结日的最近 250 个交易日，尾部否决窗口取最近 20 个。找到有效价格可只保留证明它及其后全部交易日所需的完整日历区间，不强迫继续取得更老行情。

旧 calendar binding 可以提供同根身份锚点或独立交叉核对，但不替代新区间完整性证明。新区间启动不要求先伪造旧 calendar fact。跨交易所、根、选择器或覆盖代际不能拼接。

### 6.2 每日行情证据

`verified_market_window_v1` 的每天记录包括 date、coverage 状态、来源收据引用，以及已覆盖时的 exchange_allows_trading、volume、turnover、close。permission 必须精确 bool，成交量/额为有限非负十进制值；标准化单位固定为 volume=shares、turnover=CNY、close=CNY_per_share。原始手数/金额尺度的转换必须由区间配置所签名的 mapping/normalizer 版本明确授权并已实现，不能凭字段名猜测换算。close 使用 `positive`（严格正数）或 `unavailable`（显式原因）判别。缺行/缺响应不能写为零成交行。

coverage 的封闭状态为 covered、missing、domain_conflict。传输失败属于任务诊断；可导致该日 missing，但失败消息本身不是来源事实。只有真正认证的领域问题可以产生 domain_conflict；原始快照篡改、领先版本歧义等按第 9 节直接中止。

有效成交由工厂计算：exchange_allows_trading 且 volume>0 且 turnover>0。只有真实所需操作数齐全才能把该日作为完整覆盖；不信任旧 is_effective_trade 字段。有效成交但 close 无可信正值时，价格证据待补，不能把它改成“无有效成交”，也不能退回更早价格并声称最近价格已证明。

窗口对象除第 3 节共同身份外，显式绑定 registry_manifest_hash、market/calendar descriptor ID、所用 range_config ID、request/parser/mapping/normalizer 版本、有序请求指纹与 snapshot/receipt 身份、upstream/refresh generation、实际请求范围和 required_trading_days、每日记录、日历证明哈希，以及以下两个相互独立的结果轴。

日历和行情两类对象的历史读取必须使用其精确保存的全部成员；当前批次则重新选择并核验各成员的领先身份。真实但旧的覆盖对象不能仅凭相同交易日列表或相同价格充当当前代际证据。

### 6.3 价格与停滞两个结果轴

| 价格状态 | 必须满足 | 值与限制 |
| --- | --- | --- |
| positive_close_complete | 找到窗口内最近有效成交日及实际正 close，并证明其后直到冻结日每个交易日均无有效成交 | 保存 actual_close/date 和按实际交易日推导的 stale_days；不用 preclose |
| confirmed_no_price_250 | 完整证明最近 250 个交易日均被覆盖且无有效成交 | 无 price，增加 market_evidence_missing；不生成价格依赖的最终分数 |
| incomplete | 搜索/日历/来源领域证据不齐，或有效成交日缺可信正价 | 无可供最终价格计算的 value；允许保存明确标为未完成的候选观察，不授予有效价格资格 |

窗口外旧价格不作为输入。最近有效交易在满窗口第一日时 stale_days=249，仍是窗口内价格；再早一日已在窗口外，不得把 stale=250 的价格挪进窗口。

停滞否决状态为 proven、clear、pending：最近 20 个交易日全部覆盖且无有效成交为 proven；在尾部 20 日内有已验证有效成交即可证明“连续 20 日无成交”为假；其余为 pending。价格 complete 与否不替代这个状态。有效成交日没有 close 也能反证“无有效成交”，但仍不能产生有效价格。

停滞天数只在最近有效成交日及其后连续区间已证明时给出精确值；在完整 250 日无成交时保留 `at_least=250`，不伪造精确停牌长度。stale=0 必须为冻结日真实有效成交；1–19 保留真实旧 close；20–249 可同时保留有效价格证明和已触发的双池否决。

最近 20 日已证明无成交而更老区间有缺口时，保留 proven 否决与 incomplete 价格。最近 20 日中有缺口且没有反证时不得猜否决。确认 250 日无价格同时带有已证明的 20 日否决和 market_evidence_missing。任何否决都不能消除待补。

新区间描述符是旧市场/日历选择器的能力锚点，不要求先存在一个旧正价 market_close 才能表达“确认无价格”；旧对象也不自动升级为完整窗口。阶段 B 不给停滞状态额外扣 T 分。


### 9.2 封闭失败分类

| 分类 | 例子 | 处理 |
| --- | --- | --- |
| 前置条件/合同失败 | 宇宙不存在、完整 provider 未发布、未知版本、range 配置缺失/歧义、跨根/作用域、签名不符 | 终止批次；不制造普通证券待补来掩盖配置错误 |
| 完整性/选择失败 | 篡改/丢失已登记原始文件、同领先版本歧义、伪造对象、依赖替换、批次内更正 | 终止并撤销本次派生证明 |
| 已认证领域证据不足 | 当前收据未落库、实际事实/旗标/某日覆盖缺失、已记录领域冲突、合法计算的无效分母 | 对受影响规则记录 pending，保留独立已证实影响 |
| 采集操作失败 | 超时、403/429、挑战页、未完成分页 | 任务重试/熔断或终止诊断；不能成为“确认无覆盖/无价格” |

新入口使用类型化错误/缺失结果。不得捕获通用 ValueError 的文本或异常字符串猜测业务缺失；旧接口抛出的可信读取异常保持失败。待补原因区分 runtime 与 signed_policy 来源：runtime 代码固定为 applicability_unresolved、current_receipt_absent、financial_input_missing、financial_domain_conflict、unsupported_unit、invalid_denominator、visibility_unproven、state_entry_missing、calendar_coverage_missing、market_coverage_missing、market_price_missing、market_domain_conflict、market_evidence_missing；signed_policy 只接受当前规则已签名的 reason_code。保留原始诊断但不以自由文本改变行为，未知代码拒绝。

### 9.3 增量恢复与数据保留

区间任务沿用 pending、leased、verified、retryable_failed、terminal_failed、superseded 的状态语义和有限退避/租约检查。只重取未完成、缺失或实际已变化的请求；同请求/同代际且原始收据仍真实的已验证数据不重复抓取。单证券/来源失败不妨碍其他独立采集任务推进；跨证券政策批次仍须保持一致，不能把不同尝试拼成一个批次。

保存实际请求、尝试、失败码、收据和完成进度；不删除或覆盖旧快照。重启可复用通过重验的原始字节，必须重新认证和组装完整冻结批次。游标和完成勾选仅用于工作调度，不证明当前有效性。语义内容相同但无证据代际变化时重算结果确定；有来源更正时新身份与旧历史共存。
