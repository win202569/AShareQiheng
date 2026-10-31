# Task 8 修复复审

## 结论

**APPROVED**

复审范围：`17f5865c354649aa5f9e20d50d690ee642be4748..0ec27e0544112e5a1eaa8ae8fe12b655ea326d8b`。

本轮未发现新的 P0–P3 finding。上一轮 P1、P2 均已按最低修复标准关闭，Task 1 合同扩域保持在授权的最小范围内。

## 上轮 finding 关闭证据

### P1 — 证券身份与 mapping 版本隔离：已关闭

- `build_feature_bundle()` 先物化输入事实；任一异证券事实加入稳定 blocker `financial_fact_security_mismatch`，任一旧 mapping 事实加入稳定 blocker `financial_fact_mapping_version_mismatch`。
- 只有同时满足 `fact.security_id == security_id` 与 `fact.mapping_version == MAPPING_VERSION` 的事实进入后续确定性排序和槽位索引。
- 全异证券、正确+异证券混合、全旧 mapping、正确+旧 mapping 混合四种路径均为 `blocked`；不匹配事实被过滤，其 `financial_fact_id` 不会出现在任一 `FeatureValue.evidence`。
- mixed 输入保留合格事实，所以 coverage 可保持 1.0，但 blocker 与 `financial_status=blocked` 阻止 readiness；旧 mapping 路径同时令 `confidence_inputs.mapping_consistent=false`。
- 独立窄复现中，正确事实混入 11 个经旧版 `FinancialFact.create()` 正规生成的旧 mapping 事实，结果为：

  ```text
  financial_status = blocked
  financial_coverage = 1.0
  mapping_consistent = False
  blockers = ('financial_fact_mapping_version_mismatch',
              'formal_industry_mapping_missing')
  old_mapping_evidence_overlap = 0
  ```

### P2 — FY2021 平均口径固定槽：已关闭

- `eq.total_accruals.FY2021` 与 `m.roic.FY2021` 始终显式生成。
- 两者均为 `status="not_applicable"`、`value=null`、`unit="ratio"`、`formula_version="financial-derived-v1"`、空 evidence，并使用稳定原因 `frozen_window_no_opening_period`，符合 `FeatureValue` 契约。
- coverage 明确排除两个 N/A 槽；完整一般行业包的适用槽仍为 361 个，coverage 为 1.0，`financial_status=financial_ready`，M/EQ 均保持 `input_ready`。

## Task 1 最小合同扩域

`DimensionInput(status="input_ready")` 现在只允许以下组合：

- 至少一个 `observed` 或 `derived` 值；
- 可同时包含 `not_applicable`；
- 不得包含 `missing` 或 `blocked`。

独立核对确认：ready 值 + N/A 被接受；missing、blocked、空 values、仅 N/A 均被拒绝。其他维度状态及 `FeatureValue` 校验未放宽。

## 完整范围与回归

- 相对基线只修改四个授权文件：`ashare_pipeline/feature_contract.py`、`ashare_pipeline/financial_features.py`、`tests/test_feature_contract.py`、`tests/test_financial_features.py`。
- 修复相关 7 项聚焦测试：`7/7 OK`。
- 独立完整显式模块套件：`242/242 OK`。
- 四个变更文件 `py_compile`：通过。
- `git diff --check 17f5865..0ec27e0`：通过，无 whitespace error。
- 复审结束时工作树干净；临时测试目录已在确认其为工作树子路径后删除。

## 其余 Task 8 要求复核

上一轮已通过的公式、单位/期间/分母、F2 精确哈希、七维容器、V/T/CA 边界、禁止正式分数、formal blocker、coverage、行业模板、截止时间、确定性及深层不可变行为未被本修复破坏；完整回归未显示 Task 1–7 回归。

