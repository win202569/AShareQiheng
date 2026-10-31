# Final Fix Report

- Date: 2026-08-31
- Worktree: `D:\Projects\AShareQiheng\.worktrees\seven-dimension-foundation`
- FIX_BASE: `c8c25bfc9c8a8eefc934fd6e95ac1a5063a5fe9f`
- Fix commit: `38037273f4710f4b70cc684884a51502607c1d09`
- Outcome: `DONE_WITH_CONCERNS`（六项 Important 均已关闭；仅保留明确 deferred 的 Minor、预存临时目录审计和未执行的线上运营验收）
- Safety: 未访问真实网络，未打开或迁移 tracked runtime DB，未触碰 `data/` 用户数据或控制器临时目录；测试的 `TEMP`、`TMP`、`TMPDIR` 均指向工作树内本波次新建的 `.final-fix-temp`，验证后已删除。

## 1. 当前冻结 calendar 不得复用历史 calendar facts

### RED

命令：

```powershell
D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_deep_worker.DeepWorkerTestCase.test_feature_build_selects_only_facts_normalized_with_its_frozen_calendar tests.test_deep_worker.DeepWorkerTestCase.test_feature_build_with_null_calendar_does_not_reuse_old_calendar_facts -v
```

结果：Ran 2，`FAILED (failures=2)`。同一 statement refs 先用旧日历持久化 facts 后，当前不同日历和 null calendar 两条路径都从 DB 历史 facts 得到 `observed`，而手工期望均为 `missing`。

### GREEN

最终同命令：Ran 2 in 0.365s，OK。

### 改动与理由

`_execute_feature_job` 现在收集本次 `_normalize_statement_snapshot` 返回的 exact facts，并直接交给 `select_visible_facts`；facts 仍幂等持久化供审计，但 feature selection 不再重新扫描 `financial_fact` 历史。calendar 为 null 时 normalize 返回空 facts，因此不会复用旧 calendar 推导结果。未引入 schema v4。

## 2. calendar 全链 exact identity

### RED

命令：

```powershell
D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_financial_features.TradeCalendarTests.test_calendar_rejects_wrong_dataset_malformed_rows_flags_and_range tests.test_deep_worker.DeepWorkerTestCase.test_feature_payload_freezes_exact_calendar_identity tests.test_deep_worker.DeepWorkerTestCase.test_enqueue_feature_build_rejects_wrong_calendar_identity tests.test_deep_worker.DeepWorkerTestCase.test_feature_executor_rejects_calendar_identity_swapped_after_enqueue tests.test_orchestrator.OrchestratorTestCase.test_calendar_fetch_rejects_wrong_source_dataset_and_exact_request -v
```

结果：Ran 5，`FAILED (failures=10)`。生产 parser 接受 wrong source；冻结 payload 缺 source/dataset/request/fingerprint；入队和执行侧未拒绝相应 identity tamper；fetch 返回 wrong source/dataset/request 仍可进入持久化路径。

### GREEN

最终同命令：Ran 5 in 0.424s，OK。

### 改动与理由

- 新增唯一的 long-calendar semantic request validator：exact `start_date`/`end_date` keys、start 固定 `2021-01-01`、end 不早于 `2026-09-07`；实际 end 与其 request fingerprint 精确绑定。
- `trading_days_from_batch` 现在要求 exact `source=baostock`、`dataset=trade_dates` 和规范请求。
- `SnapshotRef` 对由 `persist`/`find_exact` 返回的 ref 携带只读 request；calendar frozen payload 显式携带 snapshot id/hash/source/dataset/request/fingerprint。
- feature payload 构造/入队校验 identity；执行解冻时交叉核对 frozen payload、DB metadata、verified batch 和 request fingerprint。
- orchestrator 在 fetch 后、persist 前要求返回 `FetchBatch` 与实际调用 request 完全相等，并在 persist 后复验 verified request。
- 保留现有动态 long-calendar end/cache 契约；没有新增 orchestrator→deep_worker 之外的反向依赖或循环。

## 3. 专用行业 readiness 失败关闭

### RED

命令：

```powershell
D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_financial_features.FeatureBundleBuildTests.test_specialized_real_estate_and_resource_templates_never_ready_on_common_inputs tests.test_financial_features.FeatureBundleBuildTests.test_bank_has_zero_applicable_slots_and_no_industrial_debt_or_roic tests.test_financial_features.FeatureBundleBuildTests.test_complete_financial_inputs_are_ready_despite_formal_mapping_blocker -v
```

结果：房地产开发、工业金属两个 subtest 失败；两个模板的 `specialized_inputs_required` 均为 False，通用事实完整时可到 `financial_ready`。

### GREEN

最终同命令：Ran 3 in 0.046s，OK。

### 改动与理由

将 `real_estate_high_leverage`、`resource_cycle` 标记为 `specialized_inputs_required=True`，并让 bundle builder 实际消费该契约：专用输入尚未实现时增加稳定机器原因 `specialized_financial_inputs_missing`，状态保持 blocked。通用槽位继续作为可见、可审计输入，但不能冒充专用公式。`unclassified` 继续只使用既有规范原因 `industry_template_unclassified`，避免重复或误导原因；普通非金融行业完整输入仍可 `financial_ready`。

## 4. 三项公式允许负的非零分母

### RED

命令：

```powershell
D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_financial_features.FeatureBundleBuildTests.test_negative_nonzero_ratio_denominators_are_hand_calculated tests.test_financial_features.FeatureBundleBuildTests.test_zero_average_assets_and_invested_capital_fail_closed tests.test_financial_features.FeatureBundleBuildTests.test_tax_rate_is_bounded_and_invalid_ratio_denominators_fail_closed -v
```

结果：负收入的 gross margin 首先返回 `missing` 而非手算 derived；同一回归还覆盖负平均资产和负平均投入资本。既有测试曾把负投入资本错误固化为 missing。

### GREEN

最终同命令：Ran 3 in 0.083s，OK。

### 改动与理由

gross margin、total accruals、ROIC 的分母判断统一为“有限且不等于零”；负的非零分母按规格计算。手算回归分别断言 `1.6`、`0.2`、`-2/3`。相反测试改为真正的零平均资产/零平均投入资本。actual tax rate 的正数边界未改变，并由同一 focused 组继续验证。

## 5. missing reason 生产者/消费者统一

### RED

命令：

```powershell
D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_orchestrator.OrchestratorTestCase.test_progress_aggregates_missing_reason_from_real_persisted_bundle -v
```

结果：Ran 1，`FAILED (failures=1)`；真实 `write_feature_bundle` → `StateStore.put_feature_bundle` 产生 `reason`，progress 读取 `missing_reason`，实际聚合为 `{}`。

### GREEN

最终同命令：Ran 1 in 0.029s，OK。

### 改动与理由

规范字段采用真实 producer 已写出的 `reason`，progress 消费同一字段。测试不再手工镜像 DB row，而是构造真实 bundle、写文件、调用 `put_feature_bundle` 后调用 `build_deep_progress`；断言稳定 reason 计数，并断言输出不含 feature key/raw value。

## 6. FeatureBundle public trust boundary 与 progress 验签

### RED

初始命令：

```powershell
D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_feature_contract.FeatureContractTests.test_public_parse_rejects_canonical_but_semantically_invalid_bundles tests.test_deep_worker.DeepWorkerTestCase.test_verified_feature_read_rejects_canonical_but_invalid_bundle tests.test_orchestrator.OrchestratorTestCase.test_progress_excludes_deleted_and_tampered_bundle_files tests.test_orchestrator.OrchestratorTestCase.test_progress_excludes_bundle_when_database_header_mismatches_file -v
```

结果：4 个 test method 均 RED；public parse 的 12 个 canonical-but-invalid cases 未被拒绝，verified read 接受语义无效 bundle，删除/篡改文件与 DB header mismatch 仍计入 feature success。

自审新增 RED：

- 非字符串 `as_of_utc` 泄出 `AttributeError`，不是稳定的 `ValueError`/malformed bundle 语义；
- 源行业名称与错误但已注册的 template id 组合仍可通过；
- DB `missing_json` 损坏时在验签 try 边界外抛出 `JSONDecodeError`，而不是有界报告 unknown。

### GREEN

最终命令：

```powershell
D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_feature_contract.FeatureContractTests.test_public_parse_rejects_canonical_but_semantically_invalid_bundles tests.test_deep_worker.DeepWorkerTestCase.test_verified_feature_read_rejects_canonical_but_invalid_bundle tests.test_orchestrator.OrchestratorTestCase.test_progress_excludes_deleted_and_tampered_bundle_files tests.test_orchestrator.OrchestratorTestCase.test_progress_excludes_bundle_when_database_header_mismatches_file tests.test_orchestrator.OrchestratorTestCase.test_progress_reports_corrupt_database_summary_as_unknown -v
```

结果：Ran 5 in 0.129s，OK。

### 改动与理由

- 所有 public `from_dict` 路径要求 exact keys 和明确的容器/值类型；时间类型错误稳定转为 `ValueError`。
- 强化 schema/version、SH/SZ security id、canonical date、lowercase SHA-256、evidence、feature/dimension、blocker 字符串/去重等不变量。
- industry 强制 provisional source、registered template、唯一模板版本，并复用现有精确 name→template registry 验证绑定。
- confidence 强制 exact count keys、非负整数、非负 history、真实 bool mapping、formal confidence null；coverage 与 confidence completeness 必须一致。
- `financial_ready` 强制 coverage=1、非 unclassified、无财务 blocker；formal score 仍不可 ready。
- `read_verified_feature_bundle` 继续作为唯一真实 canonical parse/hash 边界，没有复制第二套 parser。
- progress 对每个候选只评估最新 DB feature row；先读取 bundle file、校验 hash/canonical/semantic contract，再用 `StateStore._feature_bundle_content` 的生产 canonical header 与 DB content columns 逐项交叉核对。删除、文件篡改、header mismatch、损坏 summary 均不计 success，并稳定增加既有 `unknown_failure_count`；不回退到旧 row，不输出 raw feature values。

## Verification commands and exact counts

所有 Python 命令均使用 `D:\Projects\AShareQiheng\.venv\Scripts\python.exe`，且运行前设置：

```powershell
$env:TEMP='D:\Projects\AShareQiheng\.worktrees\seven-dimension-foundation\.final-fix-temp'
$env:TMP=$env:TEMP
$env:TMPDIR=$env:TEMP
```

1. #1 focused：2 tests，0.365s，OK。
2. #2 focused：5 tests，0.424s，OK。
3. #3 focused：3 tests，0.046s，OK。
4. #4 focused：3 tests，0.083s，OK。
5. #5 focused：1 test，0.029s，OK。
6. #6 focused：5 tests，0.129s，OK。
7. Calendar/deep/orchestrator related：

   ```powershell
   D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_deep_worker tests.test_financial_features tests.test_orchestrator -v
   ```

   Ran 163 tests in 46.863s，OK。

8. 最终跨接口 related：

   ```powershell
   D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_feature_contract tests.test_financial_schema tests.test_financial_features tests.test_snapshot_repository tests.test_state_store tests.test_deep_worker tests.test_orchestrator tests.test_feature_foundation_e2e tests.test_reporting -v
   ```

   Ran 292 tests in 70.244s，OK。

9. 完整套件：

   ```powershell
   D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest discover -s tests -v
   ```

   Ran 349 tests in 83.083s，OK。

10. `git diff --check` 与 `git diff --cached --check`：均为 0 error（仅 Git 的既有 LF→CRLF 提示）。

## Commit and staged scope

Commit：`38037273f4710f4b70cc684884a51502607c1d09` (`fix: close final feature foundation review gaps`)，parent 精确为 FIX_BASE `c8c25bfc9c8a8eefc934fd6e95ac1a5063a5fe9f`。

仅提交以下 10 个文件：

- `ashare_pipeline/deep_worker.py`
- `ashare_pipeline/feature_contract.py`
- `ashare_pipeline/financial_features.py`
- `ashare_pipeline/industry_templates.py`
- `ashare_pipeline/orchestrator.py`
- `ashare_pipeline/snapshot_repository.py`
- `tests/test_deep_worker.py`
- `tests/test_feature_contract.py`
- `tests/test_financial_features.py`
- `tests/test_orchestrator.py`

未 stage `.superpowers/`、`.tmp-tests/`、`.tmp-root-check/` 或 `data/`。

## Self-review

- 已按 review 串联检查 `calendar fetch → exact freeze → normalize → current facts-only PIT select → bundle canonical write/read → DB header cross-check → bounded progress`。
- 未增加 schema v4；未产生 orchestrator↔deep_worker 循环。
- `formal_score_ready=False`、`seven_dimension_ready=False`、`official_pool_counts.waiting_price=0`、`official_pool_counts.strong_attention=0` 的生产常量未改变；完整套件中的 formal coverage、zero pool 和 finalize fail-closed 回归全部通过。
- progress 新增的失败关闭只使用既有 `unknown_failure_count`，不打开 formal gates，也不写出 raw values。
- 三个 Minor（heartbeat execution 覆盖、legacy absolute snapshot path、计划表名笔误）按指令未处理。

## Remaining concerns

1. 三个 Minor 明确 deferred，未纳入本波次。
2. 未运行真实网络、bounded online smoke 或 exact 120/114 运营验收；本报告只证明 hermetic 代码与契约修复完成，不声称生产运营已验收。
3. 工作树原有 `?? .tmp-tests/`；`git status` 仍对 `.tmp-root-check/tmp6f_w9td4/` 报 permission denied。两者均未触碰、未 stage，仍需 merge operator/controller 按既有 deferred 要求确认。
4. 代码层面未发现其他未关闭的 Important/Critical concern。
