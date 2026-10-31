# Final Fix Re-review

- Fix base: `c8c25bfc9c8a8eefc934fd6e95ac1a5063a5fe9f`
- Fix head: `38037273f4710f4b70cc684884a51502607c1d09`
- Scope: 仅复审原最终报告的六项 Important 及本修复提交；三个 deferred Minor 和未改代码均不重新泛审。
- Method: 按要求只打开一次指定 scoped review package，并对其中涉及的 changed production/test regions 用当前文件做只读行级核验。未运行 git 命令、broad suite、网络或数据库操作。因发现一个可具体证伪的 public-parser 疑点，本次仅运行一个 `python -B` 纯内存 focused probe。

## Verdicts

| # | Original Important | Verdict |
|---|---|---|
| 1 | 冻结交易日历没有隔离已经持久化的旧 financial facts | **ADDRESSED** |
| 2 | 交易日历快照没有绑定 BaoStock source 和 exact request | **ADDRESSED** |
| 3 | 房地产与资源周期模板仍可用通用财务槽位达到 `financial_ready` | **ADDRESSED** |
| 4 | gross margin / total accruals / ROIC 给分母增加规格未授权的正数限制 | **ADDRESSED** |
| 5 | 真实持久化 bundle 的缺失原因不会进入 CLI progress 聚合 | **ADDRESSED** |
| 6 | FeatureBundle/进度读取信任边界不足，孤儿或被篡改 feature 记录仍报告成功 | **NOT ADDRESSED** |

## Per-finding review

### 1. Frozen-calendar facts isolation — ADDRESSED

- `ashare_pipeline/deep_worker.py:1125` 仍由 `_normalize_statement_snapshot` 把本次 calendar 推导出的 facts 幂等写入 SQLite，保留审计持久化。
- `ashare_pipeline/deep_worker.py:1273` 收集本次 normalization 返回值；`ashare_pipeline/deep_worker.py:1289` 只把这组 `normalized_facts` 交给 PIT selection，不再按 statement snapshot ID 扫描历史 `financial_fact`。
- calendar 为 null 时 `ashare_pipeline/deep_worker.py:1134` 返回空 facts，旧 calendar facts 不会回流。
- `tests/test_deep_worker.py:543` 和 `tests/test_deep_worker.py:577` 构造同一 statement refs 的旧日历事实，并分别验证不同冻结日历及 null 日历路径；这是生产 normalize→persist→build→verified-read 行为测试，不是镜像断言。

这关闭了原问题，同时满足“current-facts-only 选择但仍可审计持久化”。

### 2. Exact calendar identity — ADDRESSED

- `ashare_pipeline/financial_features.py:161` 集中校验 long-calendar semantic request：只允许 exact `start_date`/`end_date` keys，start 固定为 `2021-01-01`，end 至少覆盖冻结下限；`ashare_pipeline/orchestrator.py:54` 继续按 `max(now+10 days, minimum end)` 动态生成实际 end，没有把 2026-08-29 的具体 end 错硬编码成永久请求。
- `ashare_pipeline/financial_features.py:176` 要求 verified batch 为 exact `baostock/trade_dates`，并继续验证范围、日序列和 flags。
- `ashare_pipeline/snapshot_repository.py:28` 为由 `persist`/`find_exact` 返回的 ref 附带只读 request；默认值保持旧构造兼容，未改 schema。
- `ashare_pipeline/deep_worker.py:520`、`ashare_pipeline/deep_worker.py:534` 将 source、dataset、request 和 fingerprint 写入 frozen payload；`ashare_pipeline/deep_worker.py:958` 在 payload 边界校验；`ashare_pipeline/deep_worker.py:992` 在执行时交叉核对 frozen payload、DB metadata 和 verified batch。
- `ashare_pipeline/orchestrator.py:149` 精确查找当前动态 request；`ashare_pipeline/orchestrator.py:165` 和 `ashare_pipeline/orchestrator.py:471` 在两条 calendar fetch/persist 路径上都于持久化前拒绝 source、dataset 或实际 request 不一致。
- validator 位于 `financial_features`，依赖仍为 orchestrator→deep_worker→financial_features；没有新增反向 import 或循环。

现有动态 end 与 exact fingerprint 是同时成立的：允许不同运行日期产生不同合法 end，但每个已冻结 snapshot 都绑定它实际请求的完整规范 JSON。

### 3. Specialized industry readiness — ADDRESSED

- `ashare_pipeline/industry_templates.py:34`、`ashare_pipeline/industry_templates.py:35` 将房地产和资源周期模板标记为 `specialized_inputs_required=True`。
- `ashare_pipeline/financial_features.py:1085` 实际消费该契约，并在专用输入尚未实现时加入稳定机器 blocker `specialized_financial_inputs_missing`；`ashare_pipeline/financial_features.py:988` 使任何 financial blocker 保持 `blocked`。
- 通用财务槽位仍可作为可见、可审计输入，因此 coverage 可为 1.0，但不能再把这些输入冒充专用 readiness。`tests/test_financial_features.py:1075` 同时覆盖房地产和资源周期这一语义。

生产 bundle builder 的原问题已经关闭。下述 #6 仍允许手工构造的 canonical bundle 绕过此 blocker；该剩余风险归入 public trust boundary，而不是把本项重复判失败。

### 4. Negative nonzero denominators — ADDRESSED

- `ashare_pipeline/financial_features.py:823` 的 gross margin、`ashare_pipeline/financial_features.py:850` 的 accruals、`ashare_pipeline/financial_features.py:865` 的 ROIC 均只拒绝零或非有限分母，负的非零分母正常计算。
- actual tax rate 的独有正数边界未被改动。
- `tests/test_financial_features.py:904` 覆盖真正零平均资产/投入资本失败关闭；`tests/test_financial_features.py:912` 分别手算并断言负收入、负平均资产、负平均投入资本结果 `1.6`、`0.2`、`-2/3`。

实现与绑定规格的分母边界现已一致。

### 5. Missing-reason producer→consumer — ADDRESSED

- producer 继续在 `ashare_pipeline/state_store.py:1055`–`1062` 写规范字段 `reason`；consumer 在 `ashare_pipeline/orchestrator.py:1090`–`1092` 读取同一字段。
- `tests/test_orchestrator.py:1053` 不再手工镜像 DB row，而是走真实 `write_feature_bundle` → `StateStore.put_feature_bundle` → `build_deep_progress`，并断言 reason 聚合以及输出不含 feature key/raw value。

原接口错配已关闭。

### 6. FeatureBundle/progress trust boundary — NOT ADDRESSED

已关闭的子问题：

- `ashare_pipeline/feature_contract.py:25` 起新增 exact-key、类型、SHA、日期、evidence、confidence、industry binding 等验证。
- `ashare_pipeline/deep_worker.py:717` 的 public verified read 会做规范解析和内容哈希验证。
- `ashare_pipeline/orchestrator.py:1052` 每个当前候选只检查最新 feature row；`ashare_pipeline/orchestrator.py:1066`–`1080` 验签文件并与 DB header 交叉核对。文件删除、内容篡改、DB header/summary 损坏均不计 feature success，而有界增加既有 `unknown_failure_count`。不回退旧 row，也不输出 raw values。

仍未关闭的核心问题：

- `ashare_pipeline/feature_contract.py:420`–`431` 对 `financial_ready` 只检查声明的 coverage 等于 1、没有声明的 financial blocker、模板不是 unclassified；它没有核对 G/M/EQ/FS/CA 的实际 dimension/value 状态，也没有根据注册模板要求专用 blocker。
- 因此，规范 JSON 可以把所有财务维度设为 `missing`、同时自报 coverage/confidence 为 1 并通过 `FeatureBundle.from_dict`；房地产模板也可以省略 `specialized_financial_inputs_missing`、自报 `financial_ready` 并通过。
- 同一 `FeatureBundle.validate` 被 `StateStore.put_feature_bundle`（`ashare_pipeline/state_store.py:787`–`799`）、public verified read 和 progress 共同信任。因此这不是只影响一个测试 helper：此类 canonical-but-semantically-invalid bundle 可通过正常写入 API 持久化，文件/hash/DB header 会彼此一致，随后 `ashare_pipeline/orchestrator.py:1081`–`1088` 仍会把它计为 `financial_ready`。

本次唯一 fresh focused probe：

```powershell
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -B -c "from tests.test_feature_contract import bundle; from ashare_pipeline.feature_contract import FeatureBundle; p=bundle().to_dict(); p['financial_status']='financial_ready'; p['financial_coverage']=1.0; p['confidence_inputs']['data_completeness_ratio']=1.0; [p['dimension_inputs'].__setitem__(d, {'status':'missing','values':[]}) for d in ('G','M','EQ','FS','CA')]; q=bundle().to_dict(); q['financial_status']='financial_ready'; q['financial_coverage']=1.0; q['confidence_inputs']['data_completeness_ratio']=1.0; q['industry']['name']='房地产开发'; q['industry']['template_id']='real_estate_high_leverage'; print('missing_dimensions=' + ('ACCEPTED' if FeatureBundle.from_dict(p) else 'UNREACHABLE')); print('specialized_without_blocker=' + ('ACCEPTED' if FeatureBundle.from_dict(q) else 'UNREACHABLE'))"
```

结果：exit 0，且输出：

```text
missing_dimensions=ACCEPTED
specialized_without_blocker=ACCEPTED
```

影响：public parse 仍可把语义上不具备财务 readiness 的 bundle 当作有效规范包；文件/DB 完全一致时，新增 progress 验签无法识别这种欺骗。原 #6 的 Critical/Important 信任边界仍未完整关闭，因此 verdict 必须为 **NOT ADDRESSED (Important)**。

修法：`FeatureBundle.validate` 至少应在 `financial_ready` 时要求所有适用财务维度不存在 `missing`/`blocked` value，并核对实际适用输入集合能够导出 coverage=1；对 `specialized_inputs_required` 且专用输入尚未实现的模板，必须要求 status 为 blocked 且含 `specialized_financial_inputs_missing`。增加两条 RED/GREEN public-parse 回归，并增加一条真实 write→read→progress 回归证明这种 forged-ready bundle 不会被持久化或计数；同时保留普通非金融 ready bundle 的 round-trip 兼容测试。

## Fix-only regression and required boundaries

- **New Critical introduced by fix:** none found.
- **New Important introduced by fix:** none found.
- **Remaining Important:** original finding #6, as reproduced above.
- Exact calendar dynamic end remains request-derived and fingerprint-bound；未发现循环依赖。
- Current-facts-only 路径继续持久化当前 normalization facts，审计链没有被换成纯内存、不可追溯实现。
- `unknown_failure_count` 的新增 feature corruption 分支每个当前候选最多计一次；只处理当前 candidate/contract/report-period 的最新 row，不回退旧成功记录。
- `ashare_pipeline/orchestrator.py:1163`–`1165` 仍固定 `formal_score_ready=False`、`seven_dimension_ready=False`，两只官方池均为 0；`ashare_pipeline/orchestrator.py:1380` 的 finalize formal gate 仍关闭。

## Verification evidence in final-fix-report.md

以下命令和结果均为实现修复报告中明确记录的既有 RED/GREEN/related/full 证据；本 scoped re-review 没有重新执行它们，也不把它们描述为本次 fresh run。

### Focused

1. Finding #1：

   ```powershell
   D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_deep_worker.DeepWorkerTestCase.test_feature_build_selects_only_facts_normalized_with_its_frozen_calendar tests.test_deep_worker.DeepWorkerTestCase.test_feature_build_with_null_calendar_does_not_reuse_old_calendar_facts -v
   ```

   RED: Ran 2，failures=2。GREEN: Ran 2 in 0.365s，OK。

2. Finding #2：

   ```powershell
   D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_financial_features.TradeCalendarTests.test_calendar_rejects_wrong_dataset_malformed_rows_flags_and_range tests.test_deep_worker.DeepWorkerTestCase.test_feature_payload_freezes_exact_calendar_identity tests.test_deep_worker.DeepWorkerTestCase.test_enqueue_feature_build_rejects_wrong_calendar_identity tests.test_deep_worker.DeepWorkerTestCase.test_feature_executor_rejects_calendar_identity_swapped_after_enqueue tests.test_orchestrator.OrchestratorTestCase.test_calendar_fetch_rejects_wrong_source_dataset_and_exact_request -v
   ```

   RED: Ran 5，failures=10。GREEN: Ran 5 in 0.424s，OK。

3. Finding #3：

   ```powershell
   D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_financial_features.FeatureBundleBuildTests.test_specialized_real_estate_and_resource_templates_never_ready_on_common_inputs tests.test_financial_features.FeatureBundleBuildTests.test_bank_has_zero_applicable_slots_and_no_industrial_debt_or_roic tests.test_financial_features.FeatureBundleBuildTests.test_complete_financial_inputs_are_ready_despite_formal_mapping_blocker -v
   ```

   RED: 房地产和工业金属 subtests 失败。GREEN: Ran 3 in 0.046s，OK。

4. Finding #4：

   ```powershell
   D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_financial_features.FeatureBundleBuildTests.test_negative_nonzero_ratio_denominators_are_hand_calculated tests.test_financial_features.FeatureBundleBuildTests.test_zero_average_assets_and_invested_capital_fail_closed tests.test_financial_features.FeatureBundleBuildTests.test_tax_rate_is_bounded_and_invalid_ratio_denominators_fail_closed -v
   ```

   RED: 负收入 gross margin 等手算断言失败。GREEN: Ran 3 in 0.083s，OK。

5. Finding #5：

   ```powershell
   D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_orchestrator.OrchestratorTestCase.test_progress_aggregates_missing_reason_from_real_persisted_bundle -v
   ```

   RED: Ran 1，failures=1。GREEN: Ran 1 in 0.029s，OK。

6. Finding #6 reported GREEN group：

   ```powershell
   D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_feature_contract.FeatureContractTests.test_public_parse_rejects_canonical_but_semantically_invalid_bundles tests.test_deep_worker.DeepWorkerTestCase.test_verified_feature_read_rejects_canonical_but_invalid_bundle tests.test_orchestrator.OrchestratorTestCase.test_progress_excludes_deleted_and_tampered_bundle_files tests.test_orchestrator.OrchestratorTestCase.test_progress_excludes_bundle_when_database_header_mismatches_file tests.test_orchestrator.OrchestratorTestCase.test_progress_reports_corrupt_database_summary_as_unknown -v
   ```

   Reported result: Ran 5 in 0.129s，OK。该组没有覆盖本复审复现的 `ready + missing dimensions` 或 `specialized ready without blocker`，所以不能关闭 #6。

### Related

```powershell
D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_deep_worker tests.test_financial_features tests.test_orchestrator -v
```

Reported result: Ran 163 tests in 46.863s，OK。

```powershell
D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_feature_contract tests.test_financial_schema tests.test_financial_features tests.test_snapshot_repository tests.test_state_store tests.test_deep_worker tests.test_orchestrator tests.test_feature_foundation_e2e tests.test_reporting -v
```

Reported result: Ran 292 tests in 70.244s，OK。

### Full

```powershell
D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Reported result: Ran 349 tests in 83.083s，OK。

修复报告还记录 `git diff --check` 与 `git diff --cached --check` 均为 0 error；本复审按要求未重跑 git 命令。

## Out of scope

以下三个原 Minor 明确不属于本修复波次；它们未处理不改变上述 scoped verdict，也不在本复审中升级：

1. heartbeat 未覆盖完整 leased execution。
2. legacy absolute snapshot path 绕过 data-root containment。
3. 计划中的 v2 表名 `snapshot`/`export_artifact` 与实际 `source_snapshot`/`artifact` 不一致。

真实网络、bounded online smoke、exact 120/114 运营验收和 `.tmp-root-check/` clean-status deferred 同样不在本 scoped code-fix 复审范围；本文不声称它们已经完成。

## Assessment

**Findings remain open.**

六项中 #1–#5 为 ADDRESSED；#6 为 NOT ADDRESSED，且仍是阻塞合并的 Important。修复 diff 没有引入新的 Critical/Important，但 head `38037273f4710f4b70cc684884a51502607c1d09` 仍不应以“all final findings addressed”合并。关闭上述两类 forged-ready public parse 路径、增加真实 write/read/progress 回归并完成一次 scoped re-review 后，才能把总体结论改为 `All findings addressed`。
