# Formal V9 Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement task-by-task. Steps use checkbox syntax for tracking.

**Goal:** 从精确 V8 official candidate 生成可复验、不可覆盖、可恢复的 V9 发布包。

**Architecture:** 验证器通过现有生产者无落库重算四批次，与历史候选逐字节比较，并重新审计 coverage。V9 repository 独立保存签名验证、准备和发布生命周期；publisher 负责确定性渲染与同卷提交，reporting 只读已发布完整树。

**Tech Stack:** Python standard library、SQLite、unittest、Decimal、canonical JSON、CSV。

**Spec:** `docs/superpowers/specs/2026-10-09-formal-v9-release-design.md`。

## Global Constraints

- V8 run、八表及旧 DDL 不改写；数据库版本只新增 V9。
- 冻结时点 2026-08-31T07:00:00+00:00，SH/SZ/BJ 完整宇宙。
- strong/wait ≤20/50、行业≤4/10，所有算术/排序由既有 producers 决定。
- test root、recovery DTO、旧 score tables 和手填 hash 不形成发布能力。
- 原候选五 artifacts/hash 保留；live coverage 是独立复验见证。
- 生产数据、SQLite、WAL/SHM 和发布包不进入代码提交。

## Review Focus

- coverage 因自身 V9 写入变化不能导致假失败，也不能跳过 source changes。
- 重启必须从正式 producers 取 live proof；快照不能升级。
- 签名验证用途和准备用途严格分域，可信 verifier 从配置固定。
- 并发/过期发布者不能覆盖目录或切换另一个尝试的 preparation。
- 旧候选代码与当前 workspace 不一致必须要求新候选。

## File Structure

`formal_release_types.py`：规范值、gate names、序列化和域分离签名。
`formal_release_repository.py`：V9 写入能力、事务、租约与恢复。
`formal_release_validation.py`：producer replay、live proof 和 gate 集。
`formal_release_rendering.py`：确定性 payload/manifest bytes。
`formal_release.py`：完整树验证、staging、rename 与恢复编排。
`formal_release_reporting.py`：published-only reader。
`formal_cli.py`：正式命令与可信配置连接。
`state_store.py`：仅 additive V9 migration 与表定义。

## Task 1: Canonical values and additive V9 migration

Files: create `formal_release_types.py`;
modify `state_store.py`; create `tests/test_formal_release_types.py`,
`tests/test_formal_release_migration.py`, `tests/fixtures/schema_v8.sql`。

Interfaces: `ValidationGate(name, passed, reason_codes, evidence_hashes)`；
`ReleaseValidationPayload`、`ReleasePreparationPayload`、`ReleaseFile` frozen DTO；
`canonical_validation_bytes(payload)` / `canonical_preparation_bytes(payload)`。
构造 DTO 不授予发布权。规范签名函数检查域、key_id 和原始字节；可信 signer/verifier
配置所有权及写入授权在 Task 3 repository 实现，不创建空的 writer 模块。

- [x] 写值类型 RED：required gates 完整且唯一、bool 精确类型、hash/Decimal 合法、
  未知字段/float/NaN/重复 JSON key、跨域签名、key_id/config mismatch 均拒绝。
- [x] 运行 `python -m unittest -v tests.test_formal_release_types`，确认失败原因来自缺失 API。
- [x] 实现 schema=`formal-release-validation-v1` 与 preparation counterpart 的规范值和校验。
- [x] 写迁移 RED：V8 八表 DDL/rows/hash 不变，V2–V8 连续 ledger 最终为 V9；
  少表、不连续/未来 ledger 失败关闭；空库包含完整旧表和五类新表。
- [x] 实现 V9 五表，外键绑定精确 V8 run，定义 validation/preparation/event 记录结构；
  release 内容 identity unique，publishing/published/blocked 状态受约束。
  append-only 写入生命周期由 Task 3 的可信 API 强制，不宣称本任务 SQL 表本身是发布授权。
- [x] 运行 types/migration tests 与现有 final migration tests，检查暂存仅代码、测试和本轮文档后提交。

Task 1 验证：最终基础/StateStore 243 tests OK（56.802s）；最终 Stage D 受影响
回归 58 tests OK（220.587s）。证据见 `../evidence/formal-v9-release/README.md`。

## Task 2: Producer-backed validator without V8 writes

Files: `formal_release_validation.py`, focused private producer source-guard adapter,
`tests/test_formal_release_validation.py`, `tests/test_formal_release_validation_guards.py`。

Interfaces: configured `FormalReleaseValidator.validate(run_id)` 返回验证诊断与
私有记录中的 live capability；public payload 无 capability constructor。
validator 在内部取得 source guard；必要的 producer 扩展只暴露给已捕获的可信
validator 调用链，不允许 caller 传 callback、guard、skip flag 或伪造 proof。

- [ ] RED：test/blocked run、DTO 冒充、跨根/冻结/run、旧 code、缺/重复成员均拒绝。
- [ ] 重启夹具：重新 build D1、D2、D3、pool，每份 canonical bytes 与候选相等；
  验证过程不新增 V8 run。current coverage 运行信息不同但官方 gate 成功可以复验。
- [ ] 来源更正改变任一计算字节/依赖时返回 candidate_changed；签名审计保留原 run。
- [ ] 实现完整12 gates、官方 configuration、exact-method authority 捕获和来源 guard。
- [ ] 测试 source/registry/contract/method tamper、活跃 task、严格 pending、zero-pool、
  当前 code identity 和事务内自身 V9 写入前后复验。运行 focused GREEN 后提交。

## Task 3: Signed repository transitions and exclusive attempts

Files: `formal_release_repository.py`, `tests/test_formal_release_repository.py`。

Interfaces: trusted service `begin_publish`, `acquire_attempt`, `append_preparation`,
`complete_publish`, `recover_publish`, `block_publish`, `append_audit`；public reader
`get_release(release_id)` / `list_files(release_id)` 返回 detached DTO。
写操作必须来自配置固定且方法未被替换的可信服务，不能依靠 DTO/signature 单独授权。

- [ ] RED：缺验证、伪签名、跨域/run/identity、过期 fencing token、并发切换准备拒绝。
- [ ] 实现 append-only validation/preparation，独占尝试租约、fencing generation、
  candidate immutable binding 与 published 完整事务。
- [ ] 测试 terminal/retryable 分离、事务故障无 torn rows、published 不变和旧 run 不变。
- [ ] focused GREEN、核对 V8 regression 后提交。

## Task 4: Deterministic rendering and safe filesystem publication

Files: `formal_release_rendering.py`, `formal_release.py`,
`tests/test_formal_release_rendering.py`, `tests/test_formal_release.py`。

Interfaces: `render_release_payloads(verified_context)` 返回不可变 path→bytes；
`FormalReleasePublisher.publish(run_id)` 仅消费 validator 私有活跃能力；
`verify_release_tree(path, signed_preparation)` 返回核对后的只读文件描述。

- [ ] RED：同内容独立 run 相同 release identity/bytes；时间、run_id、随机名不污染文件。
- [ ] 实现固定 CSV/JSON、score/audit lineage、manifest-last、完整文件表和 canonical counts。
- [ ] RED：traversal、casefold collisions、symlink/junction、未知文件/目录和目标冲突拒绝。
- [ ] 实现 owned staging、签名准备持久提交后重新复验、guard 下 no-overwrite rename；
  rename 前 source change、租约失效、目标竞态均失败关闭。
- [ ] pre-rename crash 重试取 fresh proof；post-rename crash 根据 signed preparation
  恢复 exact bytes，即使后来源更正；不得把无目标的旧 preparation 用作恢复捷径。
- [ ] 运行 rendering/publisher/repository suites 后提交。

## Task 5: Published-only reporting and formal CLI

Files: `formal_release_reporting.py`, `formal_cli.py`, narrow changes in
`__main__.py`/`reporting.py`; tests `test_formal_release_reporting.py`, `test_formal_cli.py`。

- [ ] RED：未发布、tampered tree、旧 pool aliases、legacy fallback、缺 BJ 均拒绝。
- [ ] 实现 inspect/quality reader，只读固定 published row、preparation 和完整目标树。
- [ ] 实现 formal-validate/publish/inspect/quality-report：仅 trusted config，发布中 validate
  引导到 publish recovery；不提供直接标记发布或手填 authority hash 命令。
- [ ] 运行 CLI/reporting/legacy regressions 后提交。

## Task 6: Complete acceptance

Files: `tests/test_formal_v9_e2e.py`, `docs/superpowers/evidence/formal-v9-release/README.md`。

- [ ] 隔离官方签名夹具覆盖 SH/SZ/BJ、zero-pool、pending 阻断、source correction、
  跨进程 restart、签名恢复、独立 bytes、publication 竞态和后续审计。
- [ ] 运行 V9 focused suites、V8 runner/repository/coverage regressions 和当前迁移全回归。
  长链测试逐项独立进程并保存日志，不用耗时阈值替代结构验收。
- [ ] 记录 exact revision、完整命令/结果/耗时与生产缺口；检查所有签名与权限边界。
- [ ] 提交验收；生产发布取决于实际证据和已批准配置，不随测试成功自动触发。

## Self-review

设计1–5对应 Tasks1–3；发布包设计6对应 Task4；状态机设计7对应 Tasks3–4；
CLI/验收设计8对应 Tasks5–6。原 coverage 身份保持、live coverage 独立、V8 不写回、
严格 pending 与 zero-pool 分离均有指定测试。新增模块不复写公式，也不复用 V8
private publication coordinator。历史旧 release plan 保留，仅本计划用于后续 V9。
