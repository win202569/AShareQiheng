# F2 independent review — fb4f9a6

Reviewer: /root/stage_b_f2_reviewer (gpt-6-astra/high).

### Spec Compliance

- ❌ 存在两项 Important 规格问题：季度标量未按实际 AST 叶子的期间绑定事实；局部事实问题会抹掉独立政策证据。
- ✅ 四个任务文件均有对应实现；独立政策安装器保留旧指标入口，年度目标固定为 FY2021–FY2025，选择对象没有公开正式发布资格。证据：formal_feature_repository.py:591、formal_policy_financial.py:33、:142。
- ⚠️ 无法仅凭本 diff 确认 W3 发布时的同库 Context 重验或整阶段全局约束；这些仍属于后续集成门禁。最终新鲜联合测试尚待 root 执行，不能把现有证据表述为一次全绿的 100 用例运行。

### Strengths

- 独立安装器捕获真实 provider、原有认证读取路径与完整快照，通过实际收据读取判定缺失，并重读当前依赖；没有用异常文本猜测 current_receipt_absent。formal_feature_repository.py:591。
- 年度观察逐次遍历 AST，保存重复叶子的真实路径、事实 ID、完整期间和会计口径；允许合法前一年期初权益，并拒绝错误目标年份。formal_policy_financial.py:61。
- 原始数值、repr、原投影身份、桥接版本和转换字符串均进入选择身份，避免改写旧 V6 数值语义。formal_policy_financial.py:131。
- 新测试使用真实临时仓库、签名图和收据，覆盖可选政策槽位与旧指标资格隔离。test_formal_policy_financial.py:43。

### Issues

#### Critical

无。

#### Important

1. **季度标量叶子的事实归属错误，并遗漏季度版本歧义的完整性失败。**
formal_policy_financial.py:80–86 仅用整份投影的 evidence ID 与 metric_key 取事实，没有使用当前叶子的 period_key。例如同一指标的 2024Q1 与 2025Q1 同时出现在公式中，两年的事实都会被登记到两个 AST 路径下；不能证明每个叶子的实际期间。此外，季度同领先版本冲突使原 evaluator 返回 blocked 且无 evidence，此分支随后生成普通 financial_input_missing，绕过 FY 分支已有的完整性异常。应按原 V6 季度语义逐叶解析对应季度及真实组成事实，并对版本歧义抛出完整性错误。增加同指标跨季度公式及季度同领先版本冲突回归测试。

2. **任意完整快照 issue 都会阻断所有独立政策槽位。**
formal_policy_financial.py:113–114 将 state["issues"] 非空直接解释为当前观察的 financial_domain_conflict；复用的 evaluator 也在 formal_metric_features.py:24–27 将全部 issue 传播到每个槽位。因此，仅针对 fixture.policy.roe 的 FY2021 问题，也会让已经认证的独立当期权益值消失。这违背保留独立已证实政策影响、仅对受影响规则记录待补的要求；现有 test_full_issue_snapshot_blocks_values_and_recheck 反而固定了这一错误行为。应继续完整保存、哈希和重验 provider issues，但按实际依赖确定各槽位的影响范围；没有可定位范围的整体问题才整体阻断。调整回归测试，验证 ROE 待补而独立权益证据仍可消费。

#### Minor

- 报告中的 git diff --check 有既有 LF→CRLF advisory；不属于本次产品逻辑缺陷，但不能称为完全无警告的验证输出。

### Assessment

Task quality: Needs fixes.
认证收据、封闭对象与年度观察链条总体扎实，但季度事实归属和问题影响范围直接决定证据是否可信、独立有效值是否保留，须修复后通过本任务门禁。

Focused checks: formal_metric_features.py:21–83（问题传播与季度解析）、formal_financial_features.py:182–204（版本歧义返回方式）、formal_policy_registry.py:100–107（选择器与签名 AST 期间绑定）。未运行测试、Git 命令或进行任何修改。

Test evidence: 74 个旧用例通过；100 用例运行有一个测试 SQL 表名错误，修正后的单例通过。root 另已确认四个冻结哈希及 owned-provider 单例通过；没有将这些证据误称为最终联合验收。
