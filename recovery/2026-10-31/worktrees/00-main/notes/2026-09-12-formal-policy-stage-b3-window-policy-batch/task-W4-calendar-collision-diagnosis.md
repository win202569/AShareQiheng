# W4 同交易所跨模板日历任务冲突：只读诊断

日期：2026-09-24。范围：代码和规格静态追踪；未修改实现、测试、DDL 或 Git，未运行测试。当前工作树已有 W4 的 `tests/formal_policy_runtime_fixtures.py` 修改和未跟踪的 `tests/test_formal_policy_integration.py`，本报告不触碰它们。

## 结论

七成员测试的直接触发是夹具按证券重复调用 `produce_calendar()`。第一个 SH 模板写入日历任务后，第二个 SH 模板的首段日历请求仍有完全相同的请求字节/指纹、根哈希、配置 ID 和 refresh generation `g1`，而任务 payload 中的规则级 `binding_hash` 不同。`enqueue()` 按 V7 自然键找到前一行，随后按完整 payload 比较并在 `formal_range_store.py:428` 拒绝。这是设计的 fail closed 行为，不是 SQLite 误判或哈希碰撞。

根因分两层：W4 失败的近因是夹具错误地把交易所共享的日历抓取放进逐证券生产循环；更深的 API 边界是日历任务 payload 用规则级 binding 来恢复生产者，而日历请求本身没有规则 ID。`RangeBinding` 按 `(rule_id, exchange)` 建立且其哈希明确含 `rule_id`（`formal_range_contract.py:275-290, 434-443`），这一规则级身份本身合理，不能为了消除冲突而让两个规则的证明共用 binding。V7 自然键没有遗漏应新增的 `binding_hash`：Stage B §5.2 固定了日历请求字段及指纹，§5.3 指定自然键为完整请求指纹、根/配置和 refresh generation，并要求同自然键同代际不同 payload 拒绝（规格 `:125-147`）。

同根、同交易所、同配置、同请求区间/页、同 refresh generation 的日历采集应共享**一个任务及其快照/收据**；各市场规则应从该收据各自组装**不同的规则级日历证明**。跨交易所、跨根/配置、跨请求区间/页或新 refresh generation 不共享。日历请求没有 security ID 或 coverage hash（`formal_range_source.py:294-310`）；行情请求另有证券和其绑定的日历 coverage hash，因此本结论不把行情任务合并。

## 证据链

1. Stage B §3 要求批次与证券级身份及实际读取证据内容身份，历史证明需重新检查当前关系（规格 `:51-67`）。§6.1 把日历覆盖锚定根、日历描述符/配置、交易所、请求/收据和代际，允许相邻同根成员组合，但禁止跨交易所/根/选择器/代际拼接（`:153-163`）。§9.3 要求同请求同代际且收据仍真实时不重复抓取（`:261-265`），§10 明列重复请求不重复爬（`:267-286`）。
2. 每条活动市场规则、每个交易所都解析唯一 calendar config；多个模板可引用同一个交易所 bootstrap config（`formal_range_contract.py:180-225`）。binding wire 包含 `rule_id`、market/calendar config、policy calendar selector、根；故两个 SH 模板可有同 `calendar_config.entry_id`、不同 `binding_hash`（`:275-290`）。这不是错误配置。
3. `FormalRangeRequestV1` 的封印记录持有原 binding，但指纹只哈希 request wire（`formal_range_source.py:171-180, 256-276`）。首段日历 wire 只使用日历 config、交易所、冻结时点、区间和根（`:279-317`）；`describe_request()` 另在任务描述中加入 `binding_hash`（`:866-870`）。因此请求相同而任务 payload 不同是确定性结果。
4. `formal_range_store.py:410-435` 以完整 payload 算 task ID，却按 `(request_fingerprint, registry_manifest_hash, range_config_id, refresh_generation)` 查已存在任务并拒绝不同 payload。V7 的 UNIQUE 与查询一致（`state_store.py:93-113`）。现有 store replay 测试只覆盖同一个 binding 的相同 payload（`tests/test_formal_range_store.py:148-156`）。
5. 读取时任务 payload 的 binding hash 重新解析唯一同根规则 binding，恢复原请求并与 request/config/source hash/binding hash 比对；快照、收据、生产者、原始文件再验证（`formal_range_store.py:119-205, 244-309`）。不能简单把新调用者的 binding hash 换进旧任务。`select_current()` 则按请求指纹搜索已验证候选并检查版本/父链（`:311-377, 575-583`），这使同一日历收据可被另一规则的日历选择读取。
6. `FormalPolicyMarketRepository.select_calendar()` 以调用者的 genuine binding 生成日历请求，从 store 按指纹读取已认证观察，最后在 coverage wire 内写入该 binding 的 hash/rule ID，再封印证明（`formal_policy_market.py:490-516, 608-648`）。证明所有者仍严格比较完整 binding 身份与同一个 range store（`:185-212`）；source 的行情请求也要求该 binding/store 的当前 genuine 日历证明（`formal_range_source.py:761-774, 1100-1126`）。所以共享原始日历收据不意味着跨模板证明可直接互换。
7. W4 的 `PolicyRuntimeFixture.populate_policy_evidence()` 在成员循环内依规则设置 `self.binding/self.source`，随后每证券调用 `self.produce_calendar()`（`tests/formal_policy_runtime_fixtures.py:229-255`）；继承的 `produce_calendar()` 总是入队 `g1`（`tests/formal_range_fixtures.py:307-343`）。第一个同 binding 的 SH 证券可 replay；第二个不同模板 SH 证券触发不同 binding payload。当前测试 `tests/test_formal_policy_integration.py:51-59` 提供了该顺序。

## 最小安全修复建议与 TDD

**W4 当前失败的最小修复**：仅改 `tests/formal_policy_runtime_fixtures.py` 的日历生产调度，并在 `tests/test_formal_policy_integration.py` 增加断言。按日历请求身份（至少完整 request fingerprint + root/config + generation，不能只按交易所字符串）每个共享请求只生产一次；后续规则仍调用 `FormalPolicyMarketRepository.select_calendar(其自身 binding, FREEZE)`，取得自己的 proof，再生产各证券行情。若已有已验证任务，走 `select_current()` 以重验收据和原始文件；缺失、篡改或代际不同不能被一个 Python `seen` 集合伪装成完成。若夹具需支持多段/分页，按每个请求/页去重，而不只标记首段完成。不要对 `range task natural key conflicts` 做字符串捕获后跳过。

先写失败测试：七成员五模板同一 SH 日历配置的完整集成测试；核查同 SH 日历 request+generation 只有一个 task、一个 snapshot、一个 normalization receipt，日历 transport 只发送一次；两个不同 SH 模板的 calendar coverage 均 genuine、各有不同 `binding_hash/coverage_hash`、共享相同底层日历 lineage，且各自能生成并消费自己证券的行情请求。然后改夹具并运行该单个测试。另在 `tests/test_formal_policy_market.py` 增加窄测试：第二 binding 从第一 binding 的真实已验证日历收据组装 coverage；交叉使用第一 binding 的 proof 仍被拒；更正/原始文件丢失会使两份证明失效。`tests/test_formal_range_store.py` 应保持不同 payload 同自然键拒绝的回归，并增加跨 binding 的有意碰撞测试，以固定 V7 合同。

**生产调度边界另需明确**：`FormalRangeWorker.resume()` 直接 `enqueue()`（`formal_range_worker.py:79-90`），因此若两个规则独立提交相同日历请求，第二个调用仍会冲突，即使第一个任务已验证；若第一个仍 pending，`select_current()` 也尚无可返回观察。W4 fixture 修复只能解除本次验收路径，不能声称这个入口已实现跨规则任务复用。要满足 §9.3 的任意跨模板调度，建议另做明确的同请求任务查询/共享调度路径，范围为 `ashare_pipeline/formal_range_store.py`、`ashare_pipeline/formal_range_worker.py`（或实际调用它的采集协调器）及各自测试；只允许经当前 signed graph 验证的同根、同交易所、同日历配置且**完全相同请求和 generation**复用既有任务，保留原任务 owner/payload/收据。针对 pending、leased、verified、restart、correction 逐一写 TDD；非日历或 parent 不同的同键不同 payload 仍拒绝。若设计要求 `enqueue()` 本身对不同 binding 成功，则必须先修订 §5.3 的“同键不同字节拒绝”合同和任务 payload 语义，不能静默放宽。

## DDL、恢复和证明影响

不改已发布 V7 DDL。给 UNIQUE 追加 `binding_hash` 会把一个共享日历请求拆成两任务/两收据，导致重复爬、同领先版本的内容冲突风险，并改写 `select_current()` 的跨规则候选集合；且 V7 schema 由精确 DDL 校验（`formal_range_store.py:401-404`），原位更改会使旧库无法正常打开。若未来规格正式选择独立任务，需新版本迁移（V8）和兼容读取，不能编辑 `_V7_TABLE_DDL`；当前证据不支持这条路线。

去重须保留任务 owner 的真实 raw/snapshot/receipt；重启读取仍由 `read_verified()` 重验，不能靠缓存标记跳过。新来源更正只能以新 generation 追加，`select_current()` 的领先版本和父链校验不变。W1 的 genuine 同 binding/同 store coverage 校验及按收据组合不放松；W3 的最终 recheck 仍应重读两条规则实际使用的同一个底层收据，并在更正/篡改时撤销整批。对已通过的 W1/W3 单规则证明，本建议不修改格式或权能；本次新增跨模板路径需要上述窄测试验证。范围外风险是 `resume()` 直接入队的跨绑定碰撞，不能以 W4 集成测试转绿来宣称完全解决。
