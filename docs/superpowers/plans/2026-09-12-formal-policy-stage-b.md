# Formal Policy Stage B Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现可恢复的政策证据采集与全冻结宇宙政策结果，不产生最终分数或股票池。

**Architecture:** 保持阶段 A 静态合同、旧单日取证和 V6 财务语义不变。新增区间来源与四张持久化表，独立构建财务/状态和日历/市场证据；唯一政策仓库在整批重验后发布结果。三个子计划以接口和测试为交接边界，不以人工构造的证明对象相互交接。

**Tech Stack:** Python、unittest、SQLite、Decimal；Windows PowerShell；现有字节敏感签名测试图。

**Spec:** [Stage B design](../specs/2026-09-12-formal-policy-stage-b-design.md)，用户已于本轮以“是”确认书面规格。

## Global Constraints

冻结时点仍为北京时间 2026-08-31 15:00，即 `2026-08-31T07:00:00+00:00`；SH/SZ/BJ 普通 A 股、五模板、七维权重、指标级同行资格、严格排除和证据门槛全部保持原合同。强池最多 20、等待池最多 50、行业上限 4/10 不变。本阶段不按最终入池资格筛选取证宇宙。

不改写旧 V2–V6 DDL、已有财务公式或已发布字节；不覆盖数据、SQLite、WAL/SHM、进度和历史结果；不自动合并 main 或推送。

以下不属于本阶段：真实生产来源或经济映射审批、生产签名、全市场实爬、定时调度、利润调整后 V 指标适配器、同行重排、最终置信度/分数/等级、选池、正式发布持久化。软件可支持后续增量采集，但本阶段开发验收不运行生产采集。

---

## 1. 执行位置与当前状态

工作目录固定为 `D:/Projects/AShareQiheng/.worktrees/formal-v3-implementation`，分支 `codex/formal-v3-implementation`，代码基线 `76997add2241bcc2edc6d83b313b35645dc2ff9c`。不在主检出目录实施。不动既有未跟踪目录 `tmpj4zv9_fq/`。

本文件及子计划是待执行计划；复选框不代表测试已经运行。既有阶段 A 不重新实施。测试只创建自己的 TemporaryDirectory，不打开生产数据库，不调用真实 HTTP。

PowerShell 每个测试命令在上述工作目录执行：

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_contract -v
```

每个任务先写测试、观察预期失败，再实现、复测、独立规格审查和代码审查。记录实际命令、退出码、用例数及改动文件。Git 由主代理按任务列出的路径白名单暂存；禁止 `git add .`。是否需要沙箱升级由工具权限决定，计划不是绕过权限的授权。不得夹带数据、SQLite、WAL/SHM、输出或进度文件。

## 2. 子计划与文件所有权

| 子计划 | 任务 | 主要文件及职责 | 接受条件 |
| --- | --- | --- | --- |
| [B1 区间基础](2026-09-12-formal-policy-stage-b1-range-foundation.md) | R1–R4 | `formal_range_contract.py` 合同/配对；`formal_range_source.py` 传输/解析；`formal_range_store.py` 原始文件/收据；`formal_range_worker.py` 租约采集；`state_store.py` 仅 V7 增量 | 真签名合成请求→租约→原始字节→收据→可信读取与恢复 |
| [B2 财务与状态](2026-09-12-formal-policy-stage-b2-financial-state-evidence.md) | F1–F3 | `formal_policy_values.py` 非正式值结构/运算；`formal_policy_financial.py` 财务读取；`formal_policy_state.py` Context 读取 | optional 不改变旧门槛；年度实际叶子与显式状态值可追踪 |
| [B3 窗口与整批](2026-09-12-formal-policy-stage-b3-window-policy-batch.md) | W1–W4 | `formal_policy_market.py` 日历/双轴窗口；`formal_policy_evaluator.py` 纯规则；`formal_policy_repository.py` 唯一发布入口 | 五模板全枚举、完整重验、失败撤销、旧行为兼容 |

测试夹具分别归 B1 的 `tests/formal_range_fixtures.py`、B2 的 `tests/formal_policy_runtime_fixtures.py` 所有。B3 消费这些接口；需要新增夹具方法时先由该文件负责人完成，不能多人同时编辑。`formal_sources.py` 和 `state_store.py` 只由 B1 负责人编辑；其他任务不能为了绕过信任检查修改它们。

任务依赖：R1 → R2 → R3 → R4；F1 → F2 → F3；R4 + F1 → W1；F3 + W1 → W2；W2 → W3 → W4。F1/F2 可与 R1–R4 并行；F3 与 W1 可并行。共享签名根改变后各支路测试必须重建根，不复用旧签名。

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

## 4. 跨计划接口约定

所有新非正式 wire 使用 UTF-8 JSON、sort_keys=True、ensure_ascii=False、separators=(",", ":")、allow_nan=False；Decimal 以规范字符串保存，bool 不冒充整数。新 proof 的构造器拒绝外部调用；哈希从不含自身哈希的 payload 计算。

R1 的 `RangeBinding` 是配置证明，不是数据覆盖；R2 的 `RangeFetch` 是已认证传输，不是持久化证明；R3 的 `RangeObservation` 只能从同库收据与实际原始文件读取产生。F2/F3 的选择结果是内部当前证据，不能公开伪装成正式批次。W3 才发布 `VerifiedPolicyResultBatch`，其内部 evidence/results 共用一个闭包私有可撤销 publication。

公共正式入口唯一为：

```text
FormalPolicyRepository.build_batch(
    frozen_input_hash,
    *,
    scoring_registry,
    policy_registry,
) -> VerifiedPolicyResultBatch
```

不得添加接收预制 evidence batch、stocks、stale_days、ready、eligible、pool_veto 的正式入口。纯计算接口可以接收普通值，但其结果永远不满足 proof 校验。

## 5. 验收覆盖索引

| 规格 | 落点 |
| --- | --- |
| §1/2 范围、唯一工厂、完整宇宙 | W3/W4 |
| §3 身份、封闭对象、当前与历史 | R1/R3、F2/F3、W1/W3 |
| §4 optional、收据、年度实际 AST、Decimal 桥 | F1/F2 |
| §5 v2、模板、分页、四表、收据 | R1–R4 |
| §6 自然日覆盖、实际 250/20 日、价格双轴 | W1 |
| §7 bool/enum/flag/event | F3 |
| §8 判定、部分效果、聚合与正常化依据 | W2 |
| §9 代际屏障、撤销、分类、重启 | R3/R4、W3/W4 |
| §10 五模板、攻击/兼容/确定性测试 | 各任务负例 + W4 组合回归 |
| §11 子代理并行、共享写入串行 | 本文件 §2 |

## 6. 执行勾选

- [ ] R1 签名区间合同与锚点配对。
- [ ] R2 独立请求、传输和解析。
- [ ] R3 四表迁移、租约、原始快照和收据。
- [ ] R4 有界离线采集与恢复。
- [ ] F1 值合同、数值桥与运行夹具。
- [ ] F2 政策财务投影和逐年证明。
- [ ] F3 Context 状态证据。
- [ ] W1 日历、行情请求激活和双轴窗口。
- [ ] W2 纯政策判定与聚合。
- [ ] W3 全冻结批次与失败撤销。
- [ ] W4 综合验收与代码/测试范围核对。

任何生产来源映射、量化阈值或签名需要新决定时，记录准确缺口，不用测试数据补成生产批准。本计划完成执行也不等于已有可投资的 20/50 股票池。
