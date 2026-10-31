# W3 独立审查 — 36f12b2

Base: `2c021fc8b9bd2ae58eb911e35cfd2a47600b8733`  
Head: `36f12b295715e3969b72d542f72f3d4208f7bd9e`  
审查提交：`18c45b3`、`36f12b2`

## Spec Compliance

符合 W3 简报及两项获批前驱接口扩展。`FormalPolicyRepository.build_batch(frozen_input_hash, *, scoring_registry, policy_registry)` 是唯一正式批次入口，未接受预制 evidence、stocks、stale 或 eligible 参数。准备阶段从冻结宇宙的 `security_ids` 逐一生成结果；行业归属未知时保留待补结果且不虚构五模板决策，已归属证券通过 F2 provider 读取。批次及所有子 proof 共享闭包私有发布状态、父链接与批次 hash，伪造、复制、换类和跨批次拼接不能取得资格。参见 `ashare_pipeline/formal_policy_repository.py:121-193,222-324`。

最终重验重读九角色签名源字节和 policy 配置，并调用 context、F2、F3、W1 的当前性检查；准备阶段不持有 writer reservation。发布后若 guard 的 rollback 或 close 抛出异常，外层 `BaseException` 路径仍撤销同批次全部 proof。参见 `ashare_pipeline/formal_policy_repository.py:326-361`。获批的 range seam 只检查真实 range Store 对同一 StateStore/verifier 的拥有关系并返回 `None`；nested metric guard 仅复用当前线程、同 provider、同 StateStore 的外层 observer 与 writer reservation，并保留 epoch、database 和 finalizing 检查。参见 `ashare_pipeline/formal_range_store.py:584-591`、`ashare_pipeline/formal_metric_batch_guard.py:110-196`。

变更范围与简报的九个白名单路径一致；工作树在审查时无未提交改动。实现报告记录 W3 聚焦门槛 26/26、四模块兼容门槛 60/60 通过。本次遵照审查要求未重跑大套件，也没有出现需要单独测试才能回答的具体疑点。

## Strengths

- 使用完整三成员枚举和有证据的全成员 fixture 路径分别验证待补与完成态；测试明确检查证券顺序、结果数和未知归属不产生决策。参见 `tests/test_formal_policy_repository.py:25-59`、`tests/formal_policy_runtime_fixtures.py:198-263`。
- 两次 `read_and_recheck` 覆盖昂贵读取后的变化及最终 writer exclusion 内的变化；原始签名字节、缺失转已存在、第二证券变化、source 配置、数据库变化均有针对性回归。参见 `ashare_pipeline/formal_policy_repository.py:326-356`、`tests/test_formal_policy_batch_guards.py:31-112`。
- close 真正抛出异常的测试捕获已铸造 proof，并验证其后全部失效且后续批次可以恢复；nested guard 的跨 owner 拒绝也有聚焦回归。参见 `tests/test_formal_policy_batch_guards.py:181-224`、`tests/test_formal_metric_batch_guard.py:336-366`。

## Issues

Critical: 无。  
Important: 无。  
Minor: 无。

## Task quality

**Approved.** 基于简报、完整审查包、当前代码及实现报告的测试证据，未发现需要 W3 修复的问题。W4 的五模板组合验收仍按原计划单独进行，不属于本次 W3 接受条件。
