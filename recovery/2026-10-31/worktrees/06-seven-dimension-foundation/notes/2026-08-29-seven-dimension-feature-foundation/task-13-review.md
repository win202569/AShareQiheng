# Task 13 Review

## 1) Spec Compliance

**❌ Spec Compliance**

允许范围和多数明确契约均已满足，但本任务要求的“确定性重放证明”以及两个 blocker 的“精确断言”没有被测试可靠证明，因此不能判为完整符合。

**⚠️ 仅凭 diff 无法验证：**审查包没有原始测试日志，故无法独立确认报告声称的 3/3 定向测试与 337/337 全量回归结果（`task-13-report.md:53`）。线上 v3 operational acceptance 明确未执行（`task-13-report.md:81`）；这不阻塞 Task 13 的代码完成，但金融数据基础层仍不得宣称已完成线上运营验收。

## 2) Strengths

- 变更范围严格落在 `progress.md`、`tests/feature_fixture_helpers.py`、`tests/test_feature_foundation_e2e.py` 三个允许文件内；审查包未包含生产接口、既有财务 fixture、tracked `data/` 或 ignore 规则变更。
- 两份候选文档分别按自身 `records` 写入 `records_hash=canonical_sha256(records)`，没有错误复用 performance 的哈希（`tests/feature_fixture_helpers.py:89`、`tests/feature_fixture_helpers.py:99`）。
- SQLite 查询使用 `closing(sqlite3.connect(...))`，满足 Windows 下显式关闭连接的约束（`tests/feature_fixture_helpers.py:133`）。
- frozen-job 测试明确传入 `online=False`，并断言 `remote_attempts == 0`、只写一个 feature set、fixture source 零调用（`tests/test_feature_foundation_e2e.py:264`、`tests/test_feature_foundation_e2e.py:268`、`tests/test_feature_foundation_e2e.py:270`）。
- 主路径验证了三个候选均产生 bundle，七维键完整，formal gate 关闭，官方两池为零；已出现的 evidence ref 还会解析到对应 fact 与 verified snapshot（`tests/test_feature_foundation_e2e.py:215`、`tests/test_feature_foundation_e2e.py:219`、`tests/test_feature_foundation_e2e.py:245`、`tests/test_feature_foundation_e2e.py:248`）。
- 根进度文档如实区分 schema/contract 的代码完成与尚未执行的 v3 deep 线上验收，并明确 `formal_score_ready=false`、两池为零及下一阶段工作（`progress.md:60`、`progress.md:62`、`progress.md:63`、`progress.md:64`、`progress.md:65`）。
- 房地产 fixture 的别名逻辑被限制在一个明确的候选与文件组合，并先核验原始顶层身份和三个 request symbol；没有静默开放任意 fixture 改写（`tests/feature_fixture_helpers.py:35`、`tests/feature_fixture_helpers.py:39`、`tests/feature_fixture_helpers.py:44`）。

## 3) Issues

### Critical

无。

### Important

1. **所谓第二次“重放”并没有重新构建，确定性断言基本是对同一持久化结果的再次读取。** Legacy parents 只在 harness 初始化时入队一次（`tests/test_feature_foundation_e2e.py:99`）；`run()` 本身不重新入队任何工作，只执行当前可租赁队列后读取已有 feature rows（`tests/test_feature_foundation_e2e.py:152`、`tests/test_feature_foundation_e2e.py:164`）。测试随后对同一个 harness 连续调用两次（`tests/test_feature_foundation_e2e.py:210`、`tests/test_feature_foundation_e2e.py:211`），并比较相同数据库中的 bundle bytes/count（`tests/test_feature_foundation_e2e.py:213`、`tests/test_feature_foundation_e2e.py:214`）。生产端只展开可租赁的 parent，队列为空即返回（`ashare_pipeline/deep_worker.py:408`、`ashare_pipeline/deep_worker.py:411`），所以第二次调用不会从相同输入重新生成结果。即使一次真实重建已变得不确定，这个测试仍会通过。应使用两个全新 harness 从同一 fixture 各跑一次，或显式重新建立全部任务和输出，并断言第二次确实执行了预期工作量后再比较 canonical bytes/hash。

2. **blocker 测试既可空集合误通过，也没有落实 brief 要求的“精确 blocker”。** 未分类分支使用 `all(...)` 而未先断言 bundle 数量，零 bundle 时会返回 `True`（`tests/test_feature_foundation_e2e.py:294`、`tests/test_feature_foundation_e2e.py:298`）。两个分支都只用成员包含关系，允许任意额外 blocker；balance mismatch 的 `any(...)` 还允许其余 bundle 状态错误（`tests/test_feature_foundation_e2e.py:301`、`tests/test_feature_foundation_e2e.py:305`）。因此 worker 完全不产出未分类 bundle，或同时产生意外 blocker，仍可能被测试接受。应分别断言恰好一个目标 bundle、目标 security、`financial_status == "blocked"`，并按批准契约对 blocker 集合做精确相等断言。

3. **主路径的 evidence traceability 检查可以在没有任何 feature value/evidence 时整体空跑。** 测试确认了三个 bundle ID 和七维键，但没有断言非缺失候选至少产生一个值、fact 或 evidence ref；所有验证均位于三层循环内部（`tests/test_feature_foundation_e2e.py:219`、`tests/test_feature_foundation_e2e.py:224`、`tests/test_feature_foundation_e2e.py:228`、`tests/test_feature_foundation_e2e.py:230`）。若回归导致七个维度全部为空，traceability 部分不会执行且测试仍可能通过，削弱了“财务特征输入端到端证明”的可信度。应对工业与银行候选断言预期的非空事实/evidence 数量或关键 feature/period，并继续逐一校验 snapshot 链路；缺失语义仍应保留为 `None`，不得用默认值填充。

### Minor

1. **报告承认存在未清理的测试/控制器噪声。** `task-13-report.md:80` 记录了 `.tmp-tests/` 和无法访问的 `.tmp-root-check/` warning。按照本 gate 的规则，warning/noise 必须作为 finding；审查包又未附原始输出，因此无法判断该 warning 是否仅为环境噪声、是否影响 test discovery，或是否掩盖未检查路径。应在交付证据中附上可判读的原始结果，或消除/明确隔离该 warning 后再声称干净回归。

2. **SH600002 路径仍不覆盖交易所前缀一致性。** helper 把既有 `SZ000002` fixture 的顶层身份及 request symbol 在内存中重绑为 `SH600002`（`tests/feature_fixture_helpers.py:35`、`tests/feature_fixture_helpers.py:40`、`tests/feature_fixture_helpers.py:47`），而原始行只有无交易所信息的 `SECURITY_CODE=000002`。这满足不修改既有 fixture 的范围要求，也被限制得较安全，但这条端到端路径不能作为 SH/SZ 前缀一致性的证据；该限制应继续保留在项目文档中，并由专门 identity/interface 测试承担。

## 4) Assessment

**Task quality: Needs fixes**

主要实现方向正确，离线和门闸约束也处理得好；但确定性重放、精确 blocker 和非空 evidence 三处都存在测试误通过路径，当前证据不足以信任 Task 13 的核心端到端承诺。修复上述 Important 项后再批准。
