# Task R1 brief

Source: docs/superpowers/plans/2026-09-12-formal-policy-stage-b1-range-foundation.md

## Global Constraints

冻结时点仍为北京时间 2026-08-31 15:00，即 `2026-08-31T07:00:00+00:00`；SH/SZ/BJ 普通 A 股、五模板、七维权重、指标级同行资格、严格排除和证据门槛全部保持原合同。强池最多 20、等待池最多 50、行业上限 4/10 不变。本阶段不按最终入池资格筛选取证宇宙。

不改写旧 V2–V6 DDL、已有财务公式或已发布字节；不覆盖数据、SQLite、WAL/SHM、进度和历史结果；不自动合并 main 或推送。

以下不属于本阶段：真实生产来源或经济映射审批、生产签名、全市场实爬、定时调度、利润调整后 V 指标适配器、同行重排、最终置信度/分数/等级、选池、正式发布持久化。软件可支持后续增量采集，但本阶段开发验收不运行生产采集。


## R1：source v2 与活动政策的签名区间绑定

**Files:** Create `ashare_pipeline/formal_range_contract.py`, `tests/formal_range_fixtures.py`, `tests/test_formal_range_contract.py`; Modify `ashare_pipeline/formal_sources.py`（`configs_from_canonical`、`_RegistryRecord`、配置指纹和 `SignedSourceRegistry`）。

**Interfaces:**

- Consumes: `SignedSourceRegistry.from_signed_bytes(raw, signature, key_id, verifier)`、`VerifiedRegistryBundle.blob(role)`、`FormalPolicyRegistry.require_official`，旧 Context `_descriptor`。
- Produces: `parse_range_entry(wire: dict) -> RangeConfig`；只读 RangeConfig 提供 `to_dict()`、`entry_id`，字段严格按规格 §5.1；`load_policy_range_bindings(bundle, *, scoring_registry, policy_registry) -> RangeBindings`。
- `RangeBindings.for_rule(rule_id: str, exchange: str) -> RangeBinding`；RangeBinding 提供 `market_config`、`calendar_config`、`policy_calendar_selector`、`registry_manifest_hash`、`binding_hash`、`require_current()`。调用该方法重验实际九角色来源和版本。它不声明覆盖任何日期。
- 新 `SignedSourceRegistry.range_configs` 为不可变 tuple，v1 为 empty tuple；`select_range(request)` 只检索新区间项并验证全部身份，旧 `select` 只检索旧 configs。
- 测试帮助函数 `range_entry(**changes) -> dict`、`add_range_documents(documents: dict) -> None`、`range_graph(*, mutate=None)`；add_range_documents 仅向已有政策图添加 Bx/configs/range_configs，不重复添加政策。range_graph 使用 policy_graph 的 mutate 接点，返回与 `policy_graph()` 相同五元组，修改图后调用 `rehash_documents`，不得使用 AcceptingVerifier。

- [ ] **写失败测试。** 在夹具中先实现以下纯配置生成器；固定哈希只是独立格式测试值，整图测试必须替换为真实 ENTRY 哈希。

```python
def range_entry(**changes):
    entry = dict(
        schema_version="formal-range-source-config-v1",
        capability="verified_market_window_v1", kind="calendar_range",
        anchor_descriptor_id="a" * 64, calendar_descriptor_id="a" * 64,
        source="cninfo", dataset="fixture-range-calendar",
        endpoint_url="https://www.cninfo.com.cn/fixture/range-calendar.json",
        http_method="GET", parser_id="fixture-range-parser",
        parser_version="fixture-range-v1", mapping_version="fixture-range-map-v1",
        normalizer_version="fixture-range-normalizer-v1",
        request_version="formal-range-request-v1", exchange_scope="SH",
        calendar_anchor_selector=None,
        request_template=dict(query={"start": "{start_date}", "end": "{end_date}",
                                     "exchange": "{exchange}", "page": "{page_index}"},
                              headers={"accept": "application/json"}, body=None),
        pagination="single_response_v1", max_pages=1,
        max_calendar_days_per_request=400, timeout_seconds=3.0,
        retry_base_seconds=1.0, retry_max_attempts=2,
        challenge_cooldown_seconds=15.0,
    )
    entry.update(changes)
    return entry
```

```python
def test_closed_range_contract(self):
    from ashare_pipeline.formal_range_contract import parse_range_entry
    from tests.formal_range_fixtures import range_entry
    self.assertEqual(parse_range_entry(range_entry()).to_dict(), range_entry())
    for changes in ({"max_pages": True}, {"max_pages": 2},
                    {"exchange_scope": None}, {"unapproved": 1}):
        with self.subTest(changes=changes), self.assertRaises(ValueError):
            parse_range_entry(range_entry(**changes))
```

增加测试：v1 顶层多字段拒绝、v2 少字段拒绝、旧 config 多范围字段拒绝、无/重复配对、错根、错来源、错交易所、活动规则授权缺失、M/C/Bx 混用、替换私有/公开 range_configs 后失败；原 `_bind_context` bootstrap 拒绝测试保持通过。

- [ ] **运行 RED。** `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_range_contract -v`；预期新模块/接口尚不存在或断言失败，不以签名夹具构建错误代替有效 RED。
- [ ] **实现最小闭合路径。** 先分派 source 顶层版本，再用原方法解析原 configs；独立解析新条目。深度快照中增加 range 配置的完整规范字节，不能只保存 tuple 的对象身份。锚点按总控 §3 逐项闭合，不修改 `_bind_context`。

```python
def calendar_bridge(selector, exchange):
    # selector 已通过原政策 Context selector 校验；保留全部字段。
    return {"selector": dict(selector), "exchange": exchange}

def pair_key(entry):
    return (entry["capability"], entry["exchange_scope"],
            entry["calendar_descriptor_id"])

def require_pair(market, calendar, selector, exchange):
    if market["kind"] != "market_range" or calendar["kind"] != "calendar_range":
        raise ValueError("range pair kind mismatch")
    if pair_key(market) != pair_key(calendar):
        raise ValueError("range calendar identity mismatch")
    if calendar["anchor_descriptor_id"] != calendar["calendar_descriptor_id"]:
        raise ValueError("calendar anchor must identify itself")
    if market["calendar_anchor_selector"] != calendar_bridge(selector, exchange):
        raise ValueError("policy calendar bridge mismatch")
```

上述为配对内核，不取代原文要求的格式/来源/完整图检查。`range_graph` 先加旧 security_state/configs，再调用 `add_policy_documents`；增加三个 Bx、独立旧 bootstrap config 和六个区间项。最后重哈希 feature 的 source/mapping 依赖、policy_contracts 及九角色根，之后才签名。旧 M/C 不变，policy fixture 的 FY0 此时仍保持静态；F1 创建运行变体。

- [ ] **运行 GREEN 与兼容。** 运行 `tests.test_formal_range_contract tests.test_formal_sources tests.test_formal_policy_registry tests.test_formal_policy_registry_guards`；记录真实结果。
- [ ] **审查并提交白名单。** 四个本任务文件；提交信息 `feat: bind signed policy range source configurations`。

## Controller ruling
R1 implements config/catalog/bindings only. select_range is implemented with genuine FormalRangeRequestV1 in R2, not a duck-typed R1 placeholder. Preserve all old A2 bindings. Follow the exact calendar bridge below.
## 3. 日历锚点的精确定义

代码核对：`formal_policy_registry._bind_context` 要求旧政策日历 C 为 security/input_security/security_exchange，且拒绝 bootstrap。该检查保持原样。`formal_context_schema._descriptor` 允许另一个无证券、固定交易所、无前置 calendar_selector 的 bootstrap 日历 Bx。B1 只增加 Bx，不把 C 改成 Bx。

| 配置字段 | calendar_range | market_range |
| --- | --- | --- |
| anchor_descriptor_id | Bx | 活动规则的旧 market_close 描述符 M |
| calendar_descriptor_id | Bx（自身） | Bx（真实区间采集日历） |
| exchange_scope | X | X |
| calendar_anchor_selector | null | `{"selector": C的完整签名Context选择器, "exchange": X}` |
| source/dataset | 与 Bx 相同 | 与 M 相同 |

上述嵌套 selector 保留政策输入原有八字段（kind、descriptor_id、context_kind、scope_key、field、entry_id、expected_type、expected_unit），外层严格只有 selector/exchange。它不是旧四字段 CalendarSelector，不调用旧日期绑定。加载器逐字节比较活动规则 C 与此签名桥，再按 Bx/X/capability 唯一配对两个区间项。不同证券的范围请求仍分别绑定证券与同一交易所日历证明。

Bx 使用 distinct scope_key，`security_scope=request_security=none`、`exchange_rule=fixed_exchange`、`fixed_exchange=X`、`bootstrap_calendar=true`、`calendar_selector=null`；其新增描述符格式不变。若为完整签名图增加相应旧 bootstrap source config，使用独立 dataset，不能与旧 security-scoped config 形成 null+exact 歧义。所有 M/C 旧 ENTRY 字节保持不变。新增描述符、source v2、feature 依赖及九角色根全部重新计算哈希并签名。

这是规格 §5.1 两种日历身份的实现展开，不改变经济规则或已批准字段。测试必须证明“把 Bx 当 C”“把 C 当 Bx”“SH 使用 SZ 的 Bx”“selector 文本相同但描述符不同”均失败。


## Execution and report contract
Work only in D:/Projects/AShareQiheng/.worktrees/formal-v3-implementation. Python: D:/Projects/AShareQiheng/.venv/Scripts/python.exe. No production data/network, no Git writes, no subagents. Preserve unrelated files. Use apply_patch. Implement with TDD and write report to task-R1-report.md beside this brief. Report RED/GREEN exact commands and output, changed files, self-review and concerns. Return only status, short test summary, concerns, report path. Read skills/test-driven-development and writing-good-tests before editing. Root performs the independent task review and commit. Request controller context for a real contract ambiguity rather than weakening validation.

## Implementation preflight API correction

The actual FormalPolicyRegistry method is require_verified(), not require_official().
Capture and call the real method; do not edit formal_policy_registry.py or add a
new alias. Both genuine type and actual source/root checks remain mandatory.
