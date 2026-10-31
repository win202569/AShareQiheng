# Task R3 brief

## Global Constraints

冻结时点仍为北京时间 2026-08-31 15:00，即 `2026-08-31T07:00:00+00:00`；SH/SZ/BJ 普通 A 股、五模板、七维权重、指标级同行资格、严格排除和证据门槛全部保持原合同。强池最多 20、等待池最多 50、行业上限 4/10 不变。本阶段不按最终入池资格筛选取证宇宙。

不改写旧 V2–V6 DDL、已有财务公式或已发布字节；不覆盖数据、SQLite、WAL/SHM、进度和历史结果；不自动合并 main 或推送。

以下不属于本阶段：真实生产来源或经济映射审批、生产签名、全市场实爬、定时调度、利润调整后 V 指标适配器、同行重排、最终置信度/分数/等级、选池、正式发布持久化。软件可支持后续增量采集，但本阶段开发验收不运行生产采集。

## R3：V7 四表、租约、快照与收据读取

**Files:** Modify `ashare_pipeline/state_store.py`, `tests/test_state_store.py`; Create `ashare_pipeline/formal_range_store.py`, `tests/test_formal_range_store.py`; Modify `tests/formal_range_fixtures.py`, `ashare_pipeline/formal_range_source.py`（闭包 observation 身份、genuine store 配对及后续请求入口；持久化逻辑仍在 store 模块）。

**Interfaces:**

- Consumes: R2 genuine request/fetch；精确已初始化 StateStore。
- RangeObservation 只证明来源观察、重跑规范化、收据和当前来源版本，不证明冻结日可见。date_only 的有效时间/hash 非空但尚未认证时仍是来源断言，不能仅凭非空 hash 授权；空对也保留。W1 独立认证其依据或记录 visibility_unproven，不借旧单日 Context 引导绑定伪造区间证明。
- store 模块先定义 builder/helpers，末尾导入 source 但不读取部分初始化的 source 属性；source 工厂在真实 Source/Observation 闭包建立后调用 store builder，封存返回的精确 Store 与私有认证重读函数，再向两模块发布同一类型并移除临时 builder/mint。两种导入顺序均须通过，外部重复 builder 不得制造原闭包接受的类型或观察；禁止调用者注册/首次调用捕获。
- `root` 为原始快照存储路径，签名图从精确 StateStore/verifier 重新加载。重启逐项验证真实绑定及已保存父收据链，不能由任意 wire/ordinal 授权请求；历史链可审计但不能授予新执行或 current 资格。
- Produces: `FormalRangeStore(state_store, *, root, signature_verifier, source_factory)`；`source_factory(binding) -> FormalRangeSource` 是构造时捕获的受信任依赖，不是调用者临时 parser。
- `.enqueue(request, *, refresh_generation: str) -> dict`；`.lease_next(worker_id: str, *, lease_seconds: int) -> dict | None`；`.renew(task_id, worker_id, attempt_id, *, lease_seconds) -> dict`；`.fail(task_id, worker_id, attempt_id, *, code, retryable, next_retry_at) -> dict`。
- lease_next 的内存返回字典可增加 genuine request/binding，供 R4 重启执行；不持久化权能、不提供任意 restore。事务外认证当前父链及请求，短事务内重读/CAS 候选，fetch/persist 再认证；历史读取不能授予执行。
- `.persist(task_id, worker_id, attempt_id, *, fetch: RangeFetch) -> RangeObservation` 原始文件已内容寻址落地后，在一个短事务内写 snapshot/receipt 并完成 verified 状态；`.read_verified(task_id: str) -> RangeObservation` 重验收据+原始 bytes；`.select_current(request_fingerprint: str) -> RangeObservation | None`；`.read_history(task_id: str) -> RangeObservation` 不宣称当前资格。
- RangeObservation 只读 `request/document/receipt/snapshot/task/generation` 及 `observation_hash`，具有 `.to_dict()`、`.require_current()`；选择器必须比较来源版本，不按入库自增 ID 选“最新”。同领先版本不同内容失败。
- Observation 的公开证明方法/属性查找/继承替换不能绕过原身份检查；原 source 模块初始化时提供私有 `_range_observation_authority()`，只返回原 observation type/current verifier/wire reader 的不可变 tuple，供 W1 提前封存，不导出 mint 或注册入口。W1 仍须使用本库观察并核对同库/根。
- 来源版本按已认证时点保守比较：双方都有 source_updated 时比较该字段并拒绝公开时点的反向变化；双方均无时才比较可兼容的公开时点。一方缺更新时点或精度不可比，不能为不同来源/内容猜出顺序；同领先版本内容冲突失败。抓取时间、入库顺序和不透明的 upstream/refresh 字符串不用于判新旧。
- 新增 `FormalRangeSource.previous_calendar_request(previous: RangeObservation) -> FormalRangeRequestV1 | None` 和 `.next_page(previous: RangeObservation) -> FormalRangeRequestV1 | None`。只消费 genuine 当前观察，重验其 binding/request/receipt 后使用 R2 内核派生请求；自然日已到 ISO 下界时 previous 返回 None。解析 DTO 或旧观察不能直接派生。
- `RangeStoreFixture(RangeSourceFixture)` 新增 `.range_store/.store/.root`，方法 `.produce_calendar(*, days:dict[str,bool], generation="g1", omit_pages=()) -> tuple[RangeObservation,...]`；必须真实 enqueue/lease/fetch/persist，不直接插入 proof。

- [ ] **写失败测试。**

```python
def test_verified_replay_retains_one_producer(self):
    from tests.formal_range_fixtures import RangeStoreFixture
    fixture = RangeStoreFixture()
    self.addCleanup(fixture.close)
    observations = fixture.produce_calendar(days={"2026-08-31": True})
    first = observations[0]
    replay = fixture.range_store.read_verified(first.task["id"])
    self.assertEqual(first.observation_hash, replay.observation_hash)
    self.assertEqual(first.receipt["attempt_id"], replay.receipt["attempt_id"])
```

迁移测试覆盖 2–7 每个连续入口及重开、部分对象、旧 DDL 篡改、预置 V7 表/index 同名冲突、回滚保留旧行。任务测试覆盖到期恰好接管、过期旧 owner、同 worker 不同 attempt、并发 CAS、相同自然键不同规范字节、snapshot/receipt 中断原子性、裸 INSERT/孤儿/多 producer、原始字节丢失或被替换、历史读取不成为 current、晚代际同内容合法共存。

- [ ] **运行 RED。** `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_range_store tests.test_state_store.FormalV7RangePersistenceTests -v`。
- [ ] **实现精确迁移与持久化。** 新 `_V7_TABLE_DDL`、`_V7_INDEX_DDL`、`_apply_v7_migration`；SCHEMA_VERSION=7；`initialize` 仍先建对象、`_assert_schema_ddl`、再写迁移 ledger，全在原 BEGIN IMMEDIATE 内。旧 V2–V6 常量不动。四表核心 DDL 如下（payload 字段存储规格要求的全部剩余身份，并在 Python 端封闭验证/重哈希）：

```sql
CREATE TABLE formal_range_task (
 id TEXT PRIMARY KEY,
 request_fingerprint TEXT NOT NULL,
 registry_manifest_hash TEXT NOT NULL,
 range_config_id TEXT NOT NULL,
 refresh_generation TEXT NOT NULL CHECK(length(refresh_generation)>0),
 payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('pending','leased','verified',
   'retryable_failed','terminal_failed','superseded')),
 worker_id TEXT, lease_expires_at TEXT, attempt_no INTEGER NOT NULL DEFAULT 0,
 next_retry_at TEXT, result_json TEXT, error_json TEXT,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 UNIQUE(request_fingerprint,registry_manifest_hash,range_config_id,refresh_generation),
 CHECK(attempt_no>=0),
 CHECK((status='leased' AND worker_id IS NOT NULL AND lease_expires_at IS NOT NULL)
    OR (status<>'leased' AND worker_id IS NULL AND lease_expires_at IS NULL)),
 CHECK((status='retryable_failed')=(next_retry_at IS NOT NULL)),
 CHECK(status<>'verified' OR (result_json IS NOT NULL AND error_json IS NULL)),
 CHECK(status NOT IN ('retryable_failed','terminal_failed') OR error_json IS NOT NULL)
);
CREATE TABLE formal_range_attempt (
 id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES formal_range_task(id),
 attempt_no INTEGER NOT NULL CHECK(attempt_no>0), worker_id TEXT NOT NULL,
 leased_at TEXT NOT NULL, lease_expires_at TEXT NOT NULL, finished_at TEXT,
 outcome TEXT CHECK(outcome IN ('verified','retryable_failed','terminal_failed','expired')),
 payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL,
 UNIQUE(task_id,attempt_no), CHECK((finished_at IS NULL)=(outcome IS NULL))
);
CREATE TABLE formal_range_snapshot (
 id TEXT PRIMARY KEY,
 task_id TEXT NOT NULL UNIQUE REFERENCES formal_range_task(id),
 request_fingerprint TEXT NOT NULL, registry_manifest_hash TEXT NOT NULL,
 range_config_id TEXT NOT NULL, refresh_generation TEXT NOT NULL,
 content_sha256 TEXT NOT NULL, content_path TEXT NOT NULL,
 manifest_sha256 TEXT NOT NULL UNIQUE, manifest_path TEXT NOT NULL,
 payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL,
 created_at TEXT NOT NULL
);
CREATE TABLE formal_range_normalization_receipt (
 task_id TEXT PRIMARY KEY REFERENCES formal_range_task(id),
 snapshot_id TEXT NOT NULL UNIQUE REFERENCES formal_range_snapshot(id),
 attempt_id TEXT NOT NULL REFERENCES formal_range_attempt(id),
 request_fingerprint TEXT NOT NULL, registry_manifest_hash TEXT NOT NULL,
 range_config_id TEXT NOT NULL, refresh_generation TEXT NOT NULL,
 manifest_sha256 TEXT NOT NULL, content_sha256 TEXT NOT NULL,
 normalization_hash TEXT NOT NULL, payload_json TEXT NOT NULL,
 payload_hash TEXT NOT NULL, recorded_at TEXT NOT NULL
);
CREATE INDEX formal_range_task_ready ON formal_range_task(status,next_retry_at,created_at,id);
CREATE INDEX formal_range_snapshot_request ON formal_range_snapshot(request_fingerprint,refresh_generation);
```

SQLite CHECK 不是证明：每次写/读同时核对 request/config/root/versions/generations/page、规范哈希、当前任务与 attempt、原始文件和收据中的对应字段。enqueue 同键比较完整 payload；租约领取原子递增 attempt_no 并插 attempt；接管时封存旧 attempt 为 expired；更新/完成均以 task+worker+attempt+未过期条件 CAS。调用 `.persist` 已完成任务时仅允许同生产者同字节精确重放，不能抢占 verified。

原始文件采用内容寻址和“不覆盖不同字节”写入；manifest 自身排除自身 hash，包含 request/config/root、source/upstream/refresh generation 和 producer。收据 normalization_hash 对实际重跑输出计算；外部提交的 normalization hash 不可信。数据库异常不清理已落地原始文件，保留可恢复诊断。重用同一 StateStore 的初始化身份跟踪，不把新仓库接到不同 DB。

- [ ] **运行 GREEN。** `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_range_store tests.test_formal_range_source tests.test_state_store -v`。旧迁移测试不能被删去；若其预期最高版本是 6，只更新其“当前最高版本”断言，V6 DDL 内容断言不改。
- [ ] **审查并提交白名单。** 本任务六个文件；提交信息 `feat: persist leased range evidence with immutable receipts`。

## Binding spec excerpts

## 3. 身份、证据对象与读取资格

每个正式批次共同绑定：合同/算法版本、根清单哈希、九角色哈希、policy registry 合同哈希、冻结输入哈希、宇宙/证券集合哈希、冻结时点、行业批次身份，以及全部实际读取证据的内容身份。证券级对象另外绑定证券、交易所、模板和适用规则。缺失标记也必须绑定它所对应的请求和当前代际。

证据分三种，不以一个 `verified=true` 混淆：

- 已验证的值及其来源。
- 对特定当前请求的已验证缺失/领域问题记录；证明“当前证据不足”，不证明该事实为零或为假。
- 无法建立可信读取的失败诊断；不属于可供政策计算消费的证据对象。

公开对象提供 `require_verified()`、规范字节、只读审计视图和内容哈希。普通构造、复制、继承替换、字段/方法影子或跨仓库拼装不得制造正式资格。仍沿用既有可信 Python 运行时边界，不新增对任意解释器篡改的防御承诺。

规范序列化使用严格 JSON、UTF-8、固定键排序，无 NaN/Infinity；精确区分 bool/int/float/string/null。集合显式去重排序，具有时序含义的交易日、年度和分页序列按合同顺序存储。新 Decimal 结果用无指数、无无意义尾零的十进制字符串，负零规范成 `0`；原 V6 数值字节/身份单独保留，不通过新规范化改写历史记录。哈希字段不包含自身；子对象先形成内容身份，再形成外层批次身份，避免自引用。

运行耗时、重试次数、当前机器时间和日志行不进入语义结果哈希。真实抓取时间、请求/收据和来源代际属于证据身份，必须保留。相同的已验证输入和合同产生相同结果；来源更正产生新身份，即使数值相等也不能冒用旧证明。

历史对象可用于准确的历史审计，不承诺永久代表“当前最新”。进入新的批次或后续阶段 C 时必须重新验证同根、同冻结输入及来源关系；序列化文件或旧进度本身不授予当前资格。

### 5.3 原始快照、收据与最小持久化

区间链条使用独立的 `formal-range-task-v1`、`formal-range-snapshot-v1`、`formal-range-normalization-receipt-v1`，不改旧 OfficialRequest、单日期 task 自然键、snapshot manifest 或 ContextFact 格式。

区间任务自然键包含完整新请求指纹、根/配置身份和 refresh generation。原始收据至少绑定任务 ID/请求指纹、配置 ID、manifest/content 哈希、parser/mapping/normalizer 版本、来源/upstream generation 和生产者身份。页和子区间各有自己的任务、快照和收据，不用最后一页代表所有页面。

采用同一 StateStore 的追加式区间记录命名空间：`formal_range_task`、`formal_range_snapshot`、`formal_range_normalization_receipt`、`formal_range_attempt`。新增表的合同版本与旧表隔离；旧 V2–V6 DDL 常量和行格式不改写。表结构必须存储以上逻辑身份/规范 payload，并对请求代际和收据唯一性设约束；同自然键同代际不同字节拒绝，合法更正用新代际。实施计划负责将这些已固定逻辑记录映射到精确 DDL/迁移测试，不借此实现最终分数/发布表。

原始内容继续以内容寻址方式保存并可重验。一个 verified 状态只能在快照和收据持久化、校验成功后产生。区间记录不能由裸 INSERT 后自行声称可信，仍需 producer receipt、来源身份和原始字节检查。数据库外的原始文件同样参与批次最终重验。

### 9.2 封闭失败分类

| 分类 | 例子 | 处理 |
| --- | --- | --- |
| 前置条件/合同失败 | 宇宙不存在、完整 provider 未发布、未知版本、range 配置缺失/歧义、跨根/作用域、签名不符 | 终止批次；不制造普通证券待补来掩盖配置错误 |
| 完整性/选择失败 | 篡改/丢失已登记原始文件、同领先版本歧义、伪造对象、依赖替换、批次内更正 | 终止并撤销本次派生证明 |
| 已认证领域证据不足 | 当前收据未落库、实际事实/旗标/某日覆盖缺失、已记录领域冲突、合法计算的无效分母 | 对受影响规则记录 pending，保留独立已证实影响 |
| 采集操作失败 | 超时、403/429、挑战页、未完成分页 | 任务重试/熔断或终止诊断；不能成为“确认无覆盖/无价格” |

新入口使用类型化错误/缺失结果。不得捕获通用 ValueError 的文本或异常字符串猜测业务缺失；旧接口抛出的可信读取异常保持失败。待补原因区分 runtime 与 signed_policy 来源：runtime 代码固定为 applicability_unresolved、current_receipt_absent、financial_input_missing、financial_domain_conflict、unsupported_unit、invalid_denominator、visibility_unproven、state_entry_missing、calendar_coverage_missing、market_coverage_missing、market_price_missing、market_domain_conflict、market_evidence_missing；signed_policy 只接受当前规则已签名的 reason_code。保留原始诊断但不以自由文本改变行为，未知代码拒绝。

### 9.3 增量恢复与数据保留

区间任务沿用 pending、leased、verified、retryable_failed、terminal_failed、superseded 的状态语义和有限退避/租约检查。只重取未完成、缺失或实际已变化的请求；同请求/同代际且原始收据仍真实的已验证数据不重复抓取。单证券/来源失败不妨碍其他独立采集任务推进；跨证券政策批次仍须保持一致，不能把不同尝试拼成一个批次。

保存实际请求、尝试、失败码、收据和完成进度；不删除或覆盖旧快照。重启可复用通过重验的原始字节，必须重新认证和组装完整冻结批次。游标和完成勾选仅用于工作调度，不证明当前有效性。语义内容相同但无证据代际变化时重算结果确定；有来源更正时新身份与旧历史共存。

## Prior interface cautions

Root's legacy-ddl-before-v7.md in the master Stage B workspace records all ten V2–V6
canonical DDL fingerprints. Verify exact preservation after adding V7. Do not rewrite
old DDL literals or delete tests. R2 source/request/document/manifest handoff is accepted;
use the exact fields in the R2 report and its fix1 update. Source version and refresh generation
are distinct; opaque generation strings are not inherently sortable. New receipt-driven
methods may not authenticate observations via caller-controlled public verifier aliases.

## Execution/report contract

Task BASE c7fb672bfe47d2831bb4c1e850d6397407b9464b. Prerequisites R1/R2/F1/F2 accepted with clean reviews and stable 213-case combined coverage.
Work only D:/Projects/AShareQiheng/.worktrees/formal-v3-implementation on codex/formal-v3-implementation.
Use D:/Projects/AShareQiheng/.venv/Scripts/python.exe. No dependency install, production
network/data/DB/signature/scoring, main merge or push. No Git writes or subagents.
Root stages exact task paths only after report; preserve tmpj4zv9_fq/ and all data/progress.
All file edits via apply_patch. Read complete TDD skill and writing-good-tests before
implementation. Observe real RED, implement minimally, focus tests while iterating,
then run prescribed compatibility on frozen files. Ask root about concrete contract
ambiguities/import cycles before widening the file list. Do not introduce first-use
public alias trust or one-shot callback registration that can be hijacked.
Write full report beside this brief as task-R3-report.md: exact RED/GREEN commands,
outputs, exit codes, counts, elapsed times, changed paths, frozen hashes, self-review,
actual API handoff and concerns. Return short status only. Independent review is root's job.



## Accepted predecessor handoff and concurrency
R2 at deb02d2 has clean scoped review. Read only task-R2-report.md sections
Exact R3/W1 handoff contracts and Fix round 1 for actual request/document/manifest
shapes and corrected ownership. formal_range_source owns request registry/private
mint after authentic RangeBinding capture; formal_range_request is type re-export,
not an authority module. No arbitrary request/fetch mint is exported. select_range
is installed at source initialization using genuine registry/binding anchors.
Do not resurrect removed root_guard/callback/private mint globals to add page/chunk
requests. Resolve any concrete observation/source import knot with root before
adding an authority path or widening the whitelist. Existing getters/hooks must
remain authenticated before first use, not trust public mutable aliases.

The six task files are exactly state_store.py, formal_range_store.py,
formal_range_source.py under ashare_pipeline, and test_state_store.py,
test_formal_range_store.py, formal_range_fixtures.py under tests. StateStore V7
changes require checking all ten immutable V2–V6 fingerprints against master
.superpowers/sdd/2026-09-12-formal-policy-stage-b/legacy-ddl-before-v7.md.

F3 runs independently on policy_state,policy_values,policy runtime fixture and
its tests. It never owns your files. Your StateStore/source/fixture import changes
can affect its test setup: notify root before such edits, keep each patch import-
coherent, announce source/schema stable before long compatibility runs. Root will
coordinate final stable cross-branch verification; do not rewrite another worker's
fixture or tests. No real production data, signatures, HTTP or SQLite are opened.
Opaque upstream/refresh generation strings are not sortable source versions. If
source publication/update timestamps conflict or do not establish order, propose
precise fail-closed selection semantics to root before inventing a tie-breaker.
