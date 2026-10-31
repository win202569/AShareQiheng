# F2 scoped fix round 1 review — 1687440
Reviewer: /root/stage_b_f2_reviewer
Fix base fb4f9a681303dbe5ce53ef2007e69e0cb42ab0fe; head 16874408e9f68886d5a5cf223dd703aa4c1b2915.

- **季度标量叶子的事实归属错误，并遗漏季度版本歧义的完整性失败。** — **ADDRESSED**。formal_policy_financial.py:80–105 现按每个叶子的 period_key 选择季度端点及前期累计事实，复用 V6 季度推导，仅登记对应季度的 component_fact_ids；:90–91 明确将同领先版本歧义作为完整性失败。tests/test_formal_policy_financial.py:335–359 覆盖跨年 Q1/Q2 的叶子归属、组成事实数量及季度版本冲突。
- **任意完整快照 issue 都会阻断所有独立政策槽位。** — **ADDRESSED**。formal_feature_repository.py:645–676 使用同根真实 financial-v1 映射、已签名 mapping ID/source field 与交易所绑定确定指标范围；无法定位的问题仍整体阻断，不从自由 details 推断年份。:785–807 按槽位传入相关 issues，同时保留完整快照。formal_policy_financial.py:130–153 消费对应槽位问题，:299 保存完整及分槽问题身份。tests/test_formal_policy_financial.py:221–310 验证独立权益保留、完整问题变更使旧选择失效，以及未知范围、映射错误和缺少交易所绑定的封闭处理。

## New Breakage in the Fix Diff
无新增 Critical、Important 或 Minor 问题。默认夹具在签名前建立真实结构的合成 financial-v1 映射，符合本轮 root 裁定；生产路径没有占位 schema 回退。tests/formal_policy_runtime_fixtures.py:44–57、:142；formal_feature_repository.py:649–654。
## Out-of-Scope Observations
无新增观察。
## Verdict
All findings addressed, no new Critical/Important breakage.
已核对报告中的最终 12 用例 GREEN 完整输出：211.058 秒，退出码 0；root 另已验证季度冲突单例 GREEN：1 用例／5.139 秒。本轮未重复运行测试或执行任何修改。最终六模块联合运行仍待 root 完成，本结论仅关闭 F2 本轮发现。

