# AShareQiheng V9 发布合同与 V8 衔接设计

日期：2026-10-09。状态：技术衔接设计，尚未实现。
经济规则依据：2026-09-04 正式评分发布合同及已完成 Stage D。
本文只修订发布架构和版本映射，不修改七维、证据门槛、池资格、排序或容量。

## 1. 版本与权威边界

- V8：`formal_final_run` 及其八表，计算运行保持不可变。
- V9：新增发布、验证、准备及发布事件表，旧 V2–V8 DDL、数据和状态不改写。
- V3：经济研究合同版本；不与数据库 V9 或产物 schema 名混用。
- 发布来源仅为 V8 `mode=official_candidate`、`status=preview_ready` 的精确 run。
- `FormalFinalRunSnapshot` 是历史查询数据，不能作为实时证明。
- `formal_final_publication.py` 保持 V8 私有提交职责；文件发布采用独立模块。
- legacy score run、test preview、调用者构造 DTO 或手填 hash 均不能授权发布。

## 2. 重启后的验证路径

选择“无落库的重新计算”，不提供读取快照后直接恢复 live proof 的入口。

`FormalReleaseValidator.validate(run_id)` 从已配置的可信 repositories、registry
loader、coverage auditor 与契约 verifier 取证。调用者只传 run_id，不传 gate、
验证 hash、替代证据或降级选项。过程为：

1. 用 `FormalFinalRunRepository.get_run` 核对原 run 的五产物、八表投影和身份。
2. 要求 official_candidate/preview_ready、冻结时点、当前代码版本、根身份一致。
3. 从正式冻结宇宙和十角色官方签名根重新加载 scoring/policy/valuation contracts。
4. 重新审计全量 SH/SZ/BJ coverage，并调用 `require_official_ready`。
5. 调用 `FormalFinalScoreInputRepository.build_batch(..., expected_purpose='official')`，
   再调用 D2、D3 和 pool producers；不调用 runner，不追加 V8 run。
6. 四份新计算产物的规范字节必须分别等于原 run 的 score_input、scorecard、
   eligibility、pool artifacts；证券、冻结、root、批次来源和依赖身份全部闭合。
7. 保存新 coverage 与源依赖承诺作为本次验证证据；执行所有发布 gates。
8. producer 批次逐次验活，coverage 和 workspace 在准备/发布关键边界重新核对。

原 coverage 仍是原 input_manifest_hash 的组成，不改写、不删除。新 coverage 是
发布复验见证，因 DB/WAL、生成时间等运行信息可不同于原 coverage，不要求二者
规范字节相等。它仍必须完整通过官方门闸，并与相同冻结宇宙、签名根及源依赖闭合。
该差异不允许跳过证券级证据、更正、当前代码或来源校验。

新 D1–D3/pool bytes、源依赖或当前 code_version 与候选不一致时，签入
`candidate_changed` 失败审计，要求新 Stage D official candidate。旧 V8 run 不改。
DB/WAL 文件 hash 不能当作唯一源依赖承诺；计算实际消费的事实、快照、registry、
context、policy、range 和同行依赖必须逐项绑定并复验。

## 3. 发布 gates

required gate names 固定如下；多余、缺失、重复或非 bool passed 值均拒绝：

`candidate_identity`, `official_registry`, `workspace_identity`, `frozen_universe`,
`official_coverage`, `source_identity_temporal`, `replay_equivalence`,
`classification_complete`, `score_formula`, `pool_selection`, `job_quiescence`,
`artifact_renderability`。

- 宇宙冻结于 2026-08-31T07:00:00+00:00，包含 SH/SZ/BJ 全部普通 A 股。
- 每个成员恰有一个最终状态，不能丢证券、重复或用老状态枚举替代。
- producer replay 核对七维、C/S0/Sc/Sbase/B/R_safety、风险暴露、等级与 cap trace。
- pool producers 核对 strong/wait、容量≤20/50、行业≤4/10、互斥、不回填和未舍入排序。
- 正式 source task 的活跃租约、未解释失败和阻断性来源熔断均阻断发布；签名契约
  明确的 verified_no_coverage 不等同错误或缺失。
- 当前 official candidate 已严格拒绝 pending_evidence/out_of_scope；V9 保留此规则。
  “零入池”合法；“零正式分数”必须同时满足上游官方 gate，不因旧合同允许全分类
  就绕过现有严格门槛。若全 pending，则只能诊断，不能由 V9 创造发布许可。
- gate 失败可持久化审计，不签发可发布能力。

## 4. 三种身份

候选身份：原 V8 `input_manifest_hash`, `result_hash`, 四计算 artifact hashes、
原 coverage hash、frozen/root/universe、code/contract versions。不得重新定义 V8 hash。

release 身份：canonical JSON 的 SHA256，绑定 schema=`formal-release-identity-v1`、
经济合同版本、freeze、candidate input_manifest_hash/result_hash 与 renderer_version。
`release_id='20260831-formal-v3-'+完整64位identity hash`；run_id 不进入内容身份。
相同内容只能对应一个 release；首次发布所绑定 run_id 成为稳定 provenance。
另一个同内容 run 重试可读取既有发布，不能改写 provenance。

validation 身份：精确 run_id、release identity、候选 hashes、新 coverage hash、
源依赖承诺、gate 集、当前 schema/code、审计用途；规范字节 hash 与独立签名。
created_at、进程耗时单列审计元数据，不进入确定性 payload 文件。
validation 不凭时间 TTL 维持有效；每次发布尝试重新取得 live proof。

## 5. 值类型、签名和存储

规范 JSON UTF-8、sort_keys、紧凑分隔符、无 NaN/float；Decimal 用有限十进制字符串。
payload 类型采用冻结 DTO，DTO 本身不构成能力。签名由验证器私有签发；存储端使用
配置中固定的可信 verifier/key_id 独立验签，不接受调用者指定 verifier。
签名域分离：`formal-release-validation-v1` 与 `formal-release-preparation-v1`。
签名覆盖原始规范 bytes、schema、用途、key_id 与完整绑定；拒绝跨域/跨根/跨 run。
测试 signer/verifier 只存在隔离夹具；生产 signer 配置不得自动回退测试密钥。

V9 表：

- `formal_release_validation`：append-only signed validation/audit，含规范 bytes/hash。
- `formal_release`：唯一 release identity，精确 candidate run，状态 publishing/published/blocked。
- `formal_release_preparation`：按 preparation_hash 追加不可变 signed preparation，含完整 payload 文件表、manifest
  原始 bytes/hash/size、候选/validation hashes、受约束目标路径和 renderer_version。
  每次重试可追加新的验证/准备见证；release 的 active_preparation_hash 在 publishing
  阶段可通过受控事务切换，rename 尝试选定后禁止并发切换，published 后永远固定。
- `formal_release_file`：published manifest 对应的完整 payload 文件表。
- `formal_release_event`：append-only 可重试错误与恢复审计，不污染候选状态。

验证与发布状态不写回 V8 run。release mutation APIs 为可信服务私有写入边界；
持有正确 hash 或签名验证记录也不能通过 public mark-published 绕过目标树检查。

## 6. 发布包与确定性

固定 payload：`universe_status.csv`, `scores.csv`, `strong_attention.csv`,
`waiting_price.csv`, `evidence_manifest.json`, `quality_report.md`，以及每个有完整
scorecard 的证券 `audit_cards/<security_id>.json`。manifest 最后生成。
CSV UTF-8 无 BOM、LF、固定列顺序、标准 CSV 引号；JSON 使用上节规范形式。
证券行按 security_id；池行按 producer ordinal，不二次按显示分数排序。
pool 字段值仅 strong/wait，文件名不充当 machine pool key。

scores 固定携带 security_id、模板/行业、G/V/M/EQ/FS/CA/T、C/S0/Sc/Sbase/B、
R_safety/risk_exposure、各等级、card/input hashes 与 cohort 引用。
audit cards 完整引用证据谱系、source hashes、公式/registry、cap/redline/policy trace。
evidence_manifest 固定为候选的证据谱系；validation/recheck 当前时间和 DB/WAL hash
在数据库审计中保存，不混入可复现 payload。
manifest schema=`formal-release-manifest-v1`，包含内容身份、candidate hashes、renderer、
完整 payload 相对路径/hash/byte_size 表、冻结/root/universe 和精确计数。
manifest 不把自身 hash 放进自身；它的原始 hash 保存于 signed preparation 和 release row。
run_id、生成时间、随机 staging 名、validation signature 不进入确定性文件。

## 7. 发布和恢复状态机

1. 若已 published：只核对固定 identity、durable preparation、manifest、完整目标树；
   一致返回 already_published，冲突记录 signed audit 后报错，不改发布内容。
2. 若 publishing 且目标存在：只走 post-rename recovery，依据可信签名 preparation
   校验 exact target tree；一致在事务内完成 published。不要求重算后来更正的源，
   因为这是已完成 rename 的提交恢复，不是新计算的发布。
3. 若无目标：每次取得新的实时验证；无 intent 时创建 publishing，已有同身份 intent
   则复用。blocked 不恢复；有失败审计则按 terminal/retryable 原因处理。
4. 在 releases root 内创建明确拥有的同卷 staging，写 payload、验 hash、写 manifest。
   完整树仅允许声明 regular files 和隐含父目录；拒绝 traversal、绝对/重复/casefold
   冲突路径、symlink、Windows junction/reparse point、未知目录和额外文件。
5. 在源 guard 下、发布服务所持数据库写事务内复验 candidate、四批次、官方 coverage
   和任务静默状态，持久化 signed preparation。签名 preparation 是每个实际发布尝试
   的持久见证；恢复不能凭孤立 DTO 或磁盘 manifest。
6. 写入自身 V9 rows 可能改变 DB/WAL；按照 V8 的 postwrite 原则检查 workspace、
   provenance、精确 source dependency，不把自己的事务写入误判为证据更正。
7. 同一 source guard 持续至 no-overwrite rename 和 published 提交；任何 guard/最终
   gate 失败不得 rename。SQLite IMMEDIATE 保护数据库 writer，guard 必须覆盖文件源
   和非 DB authority 的变更；仅持有 DB 锁不够。
   同一 release 的发布尝试使用服务端独占租约（持有者随机 token、明确到期时间），
   preparation 切换、rename 和完成均核对租约及 fencing generation；恢复先取得新租约。
   已过期持有者不能继续 rename。不能仅靠磁盘 lock 文件作为授权。
   最终 fencing 核对和 rename 位于同一个 IMMEDIATE 事务内；租约重新取得也必须
   使用同一数据库写锁，因此不能在核对后被另一发布者抢走租约再执行旧 rename。
8. rename 后提交失败：保留目标、preparation、publishing intent，下一次走步骤2。
   rename 前 renderer/IO 错误：保留 intent，记录 retryable event，仅清理自有 staging。
9. 已有目标冲突：不得覆盖/删除。publishing intent 可依据 signed terminal audit 标记
   blocked；published release 仍不可变。不能使用会替换已有目录的 replace 操作。

签名 preparation 的事务必须在 rename 前已提交；随后新发布事务再次复验来源并
执行 no-overwrite rename。跨此间隙有源变化时，preparation 保留审计但不允许 rename。
post-rename recovery 验证的是已持久化授权的相同 bytes，不采用 current/latest pointer。

## 8. CLI、报告及验收

`formal-validate --run-id`：无 active publishing 时实时验证并保存审计，不渲染；
active intent 指向 formal-publish；published 仅允许 audit，不改正式文件。
`formal-publish --run-id`：新尝试取 live proof，post-rename 走 signed recovery。
`formal-inspect`/`formal-quality-report --release-id`：published-only 树和 hash 核对。
root 只来自固定配置或隔离测试；命令无手工改分、gate、validation hash 参数。

验收涵盖：完整迁移保留，伪造/跨域/跨 run，重启无 proof、coverage 运行信息变化、
源更正、旧候选 code 不一致、自己 V9 写入、活跃 task、SH/SZ/BJ、严格 pending 阻断、
零入池、确定性文件、原子 rename 竞态、pre/post-rename crash、未知树与 junction。
夹具 official roots 使用隔离注入 verifier，不伪装成已批准生产配置。
实际首个正式 release 仍取决于生产全量证据就绪；实现完成不自动发布生产池。
