# Formal Policy Stage B1 Range Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付独立的签名区间请求、原始响应、同库收据与可恢复任务，不改变旧单日接口。

**Architecture:** source v2 保留原 configs，另行解析 range_configs；完整图加载器将其绑定活动政策。新传输类型不复用 OfficialRequest，四张 V7 表及独立原始文件仓库提供生产者可追溯读取。日历覆盖与行情请求授权由 B3 消费本层真实记录后完成。

**Tech Stack:** Python、unittest、SQLite、标准库 hashlib/json/datetime；现有 HTTPS 传输与签名验证接口。

**Spec:** [Stage B design](../specs/2026-09-12-formal-policy-stage-b-design.md) §3、5、9、10；[总控计划](2026-09-12-formal-policy-stage-b.md) 固定锚点桥和执行位置。

## Global Constraints

不改写旧 V2–V6 DDL、已有财务公式或已发布字节；不覆盖数据、SQLite、WAL/SHM、进度和历史结果；不自动合并 main 或推送。

source 子项改变意味着根和所有依赖身份更新、重新签名。新版本不能复用旧哈希或签名；测试签名不能作为生产批准。

区间采集与收据落库在评分读取之外完成；不在跨证券数据库事务内发网络请求。

---

## 文件图与交接

新建 `ashare_pipeline/formal_range_format.py`（无政策依赖的封闭格式）、`formal_range_contract.py`（签名配置绑定，兼容重导出格式接口）、`formal_range_request.py`（仅依赖纯格式的封闭请求身份）、`formal_range_source.py`（实时请求资格/安全传输/分页文档）、`formal_range_store.py`（原始内容寻址、收据与读取）、`formal_range_worker.py`（有限任务执行）。仅修改 `formal_sources.py` 的 v2 解析和封闭快照、`state_store.py` 的 V7 迁移及范围记录接点。不要重构这两个大文件。格式、请求身份与图绑定分离，避免循环导入迫使信任方法延迟至首次调用才捕获。

新建 `tests/formal_range_fixtures.py`，以及四个对应 `test_formal_range_*.py`。`tests/test_state_store.py` 增加单独的 `FormalV7RangePersistenceTests`，不替换旧断言。

接口中的 `dict` 均指已校验/脱离原对象的 JSON 树；作为传输 DTO 不自动构成 proof。下列 RangeBinding/Request/Fetch/Observation 的正式资格均由各自工厂私有记录授予，普通反序列化/复制不授予资格。

## R1：source v2 与活动政策的签名区间绑定

**Files:** Create `ashare_pipeline/formal_range_format.py`, `ashare_pipeline/formal_range_contract.py`, `tests/formal_range_fixtures.py`, `tests/test_formal_range_contract.py`; Modify `ashare_pipeline/formal_sources.py`（`configs_from_canonical`、`_RegistryRecord`、配置指纹和 `SignedSourceRegistry`）。

**Interfaces:**

- Consumes: `SignedSourceRegistry.from_signed_bytes(raw, signature, key_id, verifier)`、`VerifiedRegistryBundle.blob(role)`、`FormalPolicyRegistry.require_verified`，旧 Context `_descriptor`。
- Produces: `parse_range_entry(wire: dict) -> RangeConfig`；只读 RangeConfig 提供 `to_dict()`、`entry_id`，字段严格按规格 §5.1；`load_policy_range_bindings(bundle, *, scoring_registry, policy_registry) -> RangeBindings`。
- `RangeBindings.for_rule(rule_id: str, exchange: str) -> RangeBinding`；RangeBinding 提供 `market_config`、`calendar_config`、`policy_calendar_selector`、`registry_manifest_hash`、`binding_hash`、`require_current()`。调用该方法重验实际九角色来源和版本。它不声明覆盖任何日期。
- 新 `SignedSourceRegistry.range_configs` 为不可变 tuple，v1 为 empty tuple；旧 `select` 只检索旧 configs。`select_range(request)` 在 R2 与真实新区间请求类型一起实现，届时只检索新区间项并验证全部身份；R1 不造可接受自由 dict 的请求旁路或未实现桩。
- 测试帮助函数 `range_entry(**changes) -> dict`、`add_range_documents(documents: dict) -> None`、`range_graph(*, mutate=None)`；add_range_documents 仅向已有政策图添加 Bx/configs/range_configs，不重复添加政策。range_graph 使用 policy_graph 的 mutate 接点，返回与 `policy_graph()` 相同五元组，修改图后调用 `rehash_documents`，不得使用 AcceptingVerifier。

- [ ] **写失败测试。** 在夹具中先实现以下纯配置生成器；固定哈希只是独立格式测试值，整图测试必须替换为真实 ENTRY 哈希。

```python
def range_entry(**changes):
    entry = dict(
        schema_version="formal-range-source-config-v1",
        capability="verified_market_window_v1", kind="calendar_range",
        anchor_descriptor_id="a" * 64, calendar_descriptor_id="a" * 64,
        source="cninfo", dataset="fixture-range-calendar",
        endpoint_url="https://www.cninfo.com.cn/fixture/range-calendar.json",
        http_method="GET", parser_id="fixture-range-parser",
        parser_version="fixture-range-v1", mapping_version="fixture-range-map-v1",
        normalizer_version="fixture-range-normalizer-v1",
        request_version="formal-range-request-v1", exchange_scope="SH",
        calendar_anchor_selector=None,
        request_template=dict(query={"start": "{start_date}", "end": "{end_date}",
                                     "exchange": "{exchange}", "page": "{page_index}"},
                              headers={"accept": "application/json"}, body=None),
        pagination="single_response_v1", max_pages=1,
        max_calendar_days_per_request=400, timeout_seconds=3.0,
        retry_base_seconds=1.0, retry_max_attempts=2,
        challenge_cooldown_seconds=15.0,
    )
    entry.update(changes)
    return entry
```

```python
def test_closed_range_contract(self):
    from ashare_pipeline.formal_range_contract import parse_range_entry
    from tests.formal_range_fixtures import range_entry
    self.assertEqual(parse_range_entry(range_entry()).to_dict(), range_entry())
    for changes in ({"max_pages": True}, {"max_pages": 2},
                    {"exchange_scope": None}, {"unapproved": 1}):
        with self.subTest(changes=changes), self.assertRaises(ValueError):
            parse_range_entry(range_entry(**changes))
```

增加测试：v1 顶层多字段拒绝、v2 少字段拒绝、旧 config 多范围字段拒绝、无/重复配对、错根、错来源、错交易所、活动规则授权缺失、M/C/Bx 混用、替换私有/公开 range_configs 后失败；原 `_bind_context` bootstrap 拒绝测试保持通过。

- [ ] **运行 RED。** `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_range_contract -v`；预期新模块/接口尚不存在或断言失败，不以签名夹具构建错误代替有效 RED。
- [ ] **实现最小闭合路径。** 先分派 source 顶层版本，再用原方法解析原 configs；独立解析新条目。深度快照中增加 range 配置的完整规范字节，不能只保存 tuple 的对象身份。锚点按总控 §3 逐项闭合，不修改 `_bind_context`。

```python
def calendar_bridge(selector, exchange):
    # selector 已通过原政策 Context selector 校验；保留全部字段。
    return {"selector": dict(selector), "exchange": exchange}

def pair_key(entry):
    return (entry["capability"], entry["exchange_scope"],
            entry["calendar_descriptor_id"])

def require_pair(market, calendar, selector, exchange):
    if market["kind"] != "market_range" or calendar["kind"] != "calendar_range":
        raise ValueError("range pair kind mismatch")
    if pair_key(market) != pair_key(calendar):
        raise ValueError("range calendar identity mismatch")
    if calendar["anchor_descriptor_id"] != calendar["calendar_descriptor_id"]:
        raise ValueError("calendar anchor must identify itself")
    if market["calendar_anchor_selector"] != calendar_bridge(selector, exchange):
        raise ValueError("policy calendar bridge mismatch")
```

上述为配对内核，不取代原文要求的格式/来源/完整图检查。`range_graph` 先加旧 security_state/configs，再调用 `add_policy_documents`；增加三个 Bx、独立旧 bootstrap config 和六个区间项。最后重哈希 feature 的 source/mapping 依赖、policy_contracts 及九角色根，之后才签名。旧 M/C 不变，policy fixture 的 FY0 此时仍保持静态；F1 创建运行变体。

- [ ] **运行 GREEN 与兼容。** 运行 `tests.test_formal_range_contract tests.test_formal_sources tests.test_formal_policy_registry tests.test_formal_policy_registry_guards`；记录真实结果。
- [ ] **审查并提交白名单。** 五个本任务文件；提交信息 `feat: bind signed policy range source configurations`。

## R2：独立请求、可信传输和有来源依据的分页

**Files:** Create `ashare_pipeline/formal_range_request.py`, `ashare_pipeline/formal_range_source.py`, `tests/test_formal_range_source.py`; Modify `tests/formal_range_fixtures.py`, `ashare_pipeline/formal_sources.py`（genuine select_range 接点）、`ashare_pipeline/formal_range_contract.py`（仅增加只读 source_registry_hash）。

**Interfaces:**

- Consumes: R1 RangeBinding；原 `OfficialTransport`/来源主机安全与响应分类函数，仅复用其安全职责。
- Produces: `FormalRangeRequestV1`（规格 §5.2 全部字段）和 `RangeFetch`，均禁止外部铸造；`ParsedRangeDocumentV1.from_dict(wire)` 是无权 DTO；`.to_dict()` 返回脱离副本。
- 在本任务向 `SignedSourceRegistry` 新增 `select_range(request: FormalRangeRequestV1) -> RangeConfig`，仅接受 genuine 新请求、检索 range_configs 并核验其完整配置/根/锚点身份；不调用旧 `select`。相应 `formal_sources.py` 修改由同一 B1 负责人执行，并进入 R2 白名单。
- `FormalRangeSource(binding, *, transport, implementations)` 构造时封闭精确传输及实现注册表依赖；实现键为 `(parser_id,parser_version,mapping_version,normalizer_version,request_version)`，变化即失败。
- `first_calendar_request(as_of_utc: str) -> FormalRangeRequestV1`；本任务实现下文的纯 `backward_interval` 和 `page_successor`，不声明可接受已持久化观察的外部后续请求入口。R3 在真实收据类型可用后一次性新增后续请求方法，R2 不留抛 NotImplementedError 的桩。
- `fetch_verified(request: FormalRangeRequestV1) -> RangeFetch`；`parse_verified_snapshot(request, *, raw_bytes: bytes, manifest: dict) -> ParsedRangeDocumentV1` 重跑已登记实现，不接收已算好的政策结论。
- `formal_range_request.py` 只依赖纯格式/标准库，持有真实请求类型、私有 mint 与闭包登记校验；来源模块在初始化时封存这些真实接口，不提供可抢先劫持的注册回调。`formal_range_source.py` 在 mint/fetch 前后重验真实 binding/config/root，兼容重导出请求类型。W1 增加行情 request 工厂时复用该私有 mint；R2 不提供公开 arbitrary range request 构造器。
- `RangeBinding.source_registry_hash` 从已验证父记录的 source 角色哈希读取，不更改绑定 wire/hash。来源封存真实 getter，将该值保存在请求私有记录中，固定 request wire 不增字段。`select_range` 除 ENTRY/锚点外比较完整 source blob 哈希；`SignedSourceRegistry` 本身没有 manifest-root 身份，同一个完整 source blob 被多个真实根引用可以复用，但不同 source blob 不能仅凭所选 ENTRY 相同混用。请求的 manifest-root 仍由真实 binding 绑定及重验。
- 新测试 `RangeSourceFixture`：构造真实 range_graph/RangeBinding、捕获请求的 FakeTransport、已登记 JSON fixture parser；属性 `.source/.transport/.binding`，方法 `.reply(wire:dict)`、`.close()`。仅临时原始内容，不创建生产文件。

- [ ] **写失败测试。**

```python
def test_first_calendar_request_needs_no_existing_calendar(self):
    from tests.formal_range_fixtures import RangeSourceFixture
    fixture = RangeSourceFixture()
    self.addCleanup(fixture.close)
    request = fixture.source.first_calendar_request("2026-08-31T07:00:00+00:00")
    wire = request.to_dict()
    self.assertEqual(wire["end_date"], "2026-08-31")
    self.assertEqual(wire["start_date"], "2025-07-28")
    self.assertEqual(wire["page_index"], 1)
    self.assertIsNone(wire["security_id"])
    self.assertIsNone(wire["calendar_coverage_hash"])
```

增加 exact bool/int、合法 ISO 下界、冻结后 end、old/new 占位符串线、URL 重定向/挑战/403/429、分页页数/总数/范围/证券不一致、伪造后续页、复制 request、替换 normalizer 或其方法等负例。解析 wire 至少封闭绑定 request_fingerprint、source/dataset/security/exchange/start/end、版本、page_index/page_count/record_count、coverage 声明、有序 rows 及规格时点字段；不能有 effective_trade/stale_days/pool_veto。

- [ ] **运行 RED。** `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_range_source -v`。预期缺失新接口。
- [ ] **实现。** 使用已签名 L 从冻结自然日向前分段，不假定交易日；先完成安全模板及验证，再发请求，网络操作不占数据库事务。实现中的日期内核：

```python
from datetime import date, timedelta

def backward_interval(end_text, limit):
    if type(limit) is not int or limit <= 0:
        raise ValueError("range limit must be a positive exact integer")
    end = date.fromisoformat(end_text)
    distance = min(limit - 1, (end - date.min).days)
    return (end - timedelta(days=distance)).isoformat(), end.isoformat()

def page_successor(document, max_pages):
    page, count = document["page_index"], document["page_count"]
    if type(page) is not int or type(count) is not int:
        raise ValueError("page identity must use exact integers")
    if not 1 <= page <= count or count > max_pages:
        raise ValueError("unverified or out-of-budget pagination")
    return page + 1 if page < count else None
```

`page_successor` 只在请求身份、实际来源分页声明和 R3 收据已认证后调用；超过上限保留未完成，不能调用本函数截断。无后续合法自然日时返回有原因的采集终止，不日期下溢。单页合同只允许 page_count=page_index=1；空响应不自动满足 coverage。

- [ ] **运行 GREEN。** `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_range_source tests.test_formal_sources tests.test_formal_range_contract -v`。
- [ ] **审查并提交白名单。** 本任务六个文件，提交信息 `feat: authenticate bounded calendar range requests`。

## R3：V7 四表、租约、快照与收据读取

**Files:** Modify `ashare_pipeline/state_store.py`, `tests/test_state_store.py`; Create `ashare_pipeline/formal_range_store.py`, `tests/test_formal_range_store.py`; Modify `tests/formal_range_fixtures.py`, `ashare_pipeline/formal_range_source.py`（仅接通 genuine observation 消费入口）。

**Interfaces:**

- Consumes: R2 genuine request/fetch；精确已初始化 StateStore。
- Produces: `FormalRangeStore(state_store, *, root, signature_verifier, source_factory)`；`source_factory(binding) -> FormalRangeSource` 是构造时捕获的受信任依赖，不是调用者临时 parser。
- `.enqueue(request, *, refresh_generation: str) -> dict`；`.lease_next(worker_id: str, *, lease_seconds: int) -> dict | None`；`.renew(task_id, worker_id, attempt_id, *, lease_seconds) -> dict`；`.fail(task_id, worker_id, attempt_id, *, code, retryable, next_retry_at) -> dict`。
- `.persist(task_id, worker_id, attempt_id, *, fetch: RangeFetch) -> RangeObservation` 原始文件已内容寻址落地后，在一个短事务内写 snapshot/receipt 并完成 verified 状态；`.read_verified(task_id: str) -> RangeObservation` 重验收据+原始 bytes；`.select_current(request_fingerprint: str) -> RangeObservation | None`；`.read_history(task_id: str) -> RangeObservation` 不宣称当前资格。
- RangeObservation 只读 `request/document/receipt/snapshot/task/generation` 及 `observation_hash`，具有 `.to_dict()`、`.require_current()`；选择器必须比较来源版本，不按入库自增 ID 选“最新”。同领先版本不同内容失败。
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

## R4：有限采集、分页恢复和不重复请求

**Files:** Create `ashare_pipeline/formal_range_worker.py`, `tests/test_formal_range_worker.py`; Modify `tests/formal_range_fixtures.py`。

**Interfaces:**

- Consumes: R2 source、R3 store。
- Produces: `FormalRangeWorker(range_store, *, source_factory, worker_id, lease_seconds=60)`；`.run_once() -> dict`，严格状态 idle/verified/retryable_failed/terminal_failed；`.resume(request, *, refresh_generation) -> dict` 重验已有 verified，未完成才入队。返回诊断 DTO，不是日历/行情证明。
- `RangeWorkerFixture(RangeStoreFixture)` 新增 `.worker`，`.transport.calls` 可计数；`enqueue_calendar()` 返回 genuine 首请求；只有测试 FakeTransport 在 fixture 中可设置响应，不开启真实 HTTP。

- [ ] **写失败测试。**

```python
def test_resume_does_not_fetch_verified_bytes_twice(self):
    from tests.formal_range_fixtures import RangeWorkerFixture
    fixture = RangeWorkerFixture()
    self.addCleanup(fixture.close)
    request = fixture.enqueue_calendar()
    self.assertEqual(fixture.worker.run_once()["state"], "verified")
    calls = len(fixture.transport.calls)
    fixture.worker.resume(request, refresh_generation="g1")
    self.assertEqual(len(fixture.transport.calls), calls)
```

另测超时/403/429/挑战页不会成为 coverage；重启后已有页不重取；第 2 页缺失保留第 1 页；超过 max_pages 不标完成；一个失败任务不阻止独立任务；原始文件校验失败不静默删旧证据或自动相信 verified 标志；旧 worker 租约失效不能完成任务。

- [ ] **运行 RED。** `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_range_worker -v`。
- [ ] **实现。** 每次只执行一个任务，释放数据库事务后联网；依次验证 binding→请求→fetch→persist。成功收据才派生下一页，日历下一分段由 W1 的窗口需求决定，不在 worker 无限回溯。错误类别沿用类型化 transport 分类，不从任意异常文本猜测覆盖。

```python
def retry_delay(base, attempt_no, timeout_seconds):
    if type(attempt_no) is not int or attempt_no < 1:
        raise ValueError("attempt number must be positive")
    return min(base * (2 ** (attempt_no - 1)), timeout_seconds)
```

仅在 attempt_no < retry_max_attempts 时安排 retryable_failed；挑战页使用签名 challenge_cooldown_seconds；达到上限 terminal_failed，保留所有尝试。退避上限取签名 timeout_seconds；不新设生产配置。`run_once` 不含 sleep，调度者以后按 next_retry_at 调用，本阶段不建调度服务。

- [ ] **运行 GREEN。** `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_range_contract tests.test_formal_range_source tests.test_formal_range_store tests.test_formal_range_worker -v`。
- [ ] **审查并提交白名单。** 本任务三个文件；提交信息 `feat: resume bounded range collection without refetching verified pages`。

## B1 交接

交付真实签名的 R1 配对、R2 请求、R3 收据和 R4 有界执行；交接同时列出实际测试结果。不得把一页来源观察标成 20/250 日完整覆盖。W1 必须重新验证所有组合成员，才有权建立覆盖与行情窗口。
