# Task 1 Report

## 变更摘要

新增七维特征基础契约：固定契约版本与维度集合，提供证据引用、特征值、维度输入、行业上下文、置信输入和特征包的冻结 dataclass；实现状态、单位、有限数值、时区、覆盖率、正式评分闸门校验，以及确定性 JSON 序列化和 SHA-256 内容哈希。

## RED

命令：`D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_feature_contract -v`

关键失败：`ModuleNotFoundError: No module named 'ashare_pipeline.feature_contract'`。

## GREEN

命令：`D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_feature_contract -v`

结果：7 个测试全部通过（`OK`）。另执行 `git diff --check`，无输出、通过。

## 提交

- 测试数：7
- 提交哈希：`b23153c3bbd72f500844cc2bbaafee82cf76787f`
- 修改文件：`ashare_pipeline/feature_contract.py`、`tests/test_feature_contract.py`

## 遗留风险

本任务只定义契约层，未实现财务事实提取、行业模板、深抓 worker、数据库迁移或正式评分；这些模块仍需遵守本契约并补充集成测试。映射版本、模板槽位和正式置信度映射由后续任务定义。

## 审查修复轮次

- 修复摘要：对 `dimension_inputs`、`date_precision_counts` 和 `blockers` 做构造期防御性归一化（只读映射/tuple），防止外部嵌套容器改写已构造 bundle；`DimensionInput` 构造期拒绝重复 `(key, period_key)`。
- RED 命令：`D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_feature_contract -v`；新增两个回归测试分别失败（哈希受外部改写影响、重复键未抛错）。
- GREEN 命令：`D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_feature_contract -v`；9 个测试全部通过。
- `git diff --check`：通过。
- 修复提交哈希：`bf5a58fdbb4295b7bf5adc6420d32cb0fd3a3d54`
- 本轮修改文件：`ashare_pipeline/feature_contract.py`、`tests/test_feature_contract.py`
