# Task R4 implementation brief


## R4 ruling: typed live-acquisition terminal failures

Do not blanket-catch FormalTerminalSourceError: it is also used by request,
configuration and parent snapshot replay validation. However malformed or
out-of-budget remote responses are real acquisition failures and must be
recordable as terminal_failed, not left perpetually leased. Source ownership
is therefore expanded narrowly beyond the binding accessor to an explicit
range-acquisition terminal subtype of FormalTerminalSourceError. Emit it only
from the live fetch response validation/normalization boundary, never from
snapshot replay or request/parent/config authentication. On the remote-error
path recheck original source/request/binding/parent authority outside the
operational wrapper before classifying the remote error; callback-time integrity
failures must propagate. Keep successful order and R3 typed request rejection.
Worker catches this subtype only around fetch, alongside typed retryable/blocked
errors. Generic terminal/integrity exceptions remain failures. No string matching
or change to formal_sources.py or parser/replay contracts. R4 tests demonstrate
remote malformed/max-pages terminal task diagnosis and base parent replay error
propagation, with no false coverage. If modest source-only separation proves
impossible, report the precise obstacle to the controller before broadening.

Classification refinement approved during self-review: if a registered parser or
normalizer itself raises the new live-acquisition subtype, the shared parser
boundary must normalize it back to the existing base terminal error. Saved
snapshot replay must not inherit a live-only classification; live fetch alone
may deliberately reclassify after its authority checks. Recheck original source
and request after parent verification on the terminal-error path, because parent
replay callbacks can change those dependencies. Add focused regressions; preserve
all existing base error behavior and avoid a general exception framework.

Ready for dispatch. BASE: 3c3b3c12a6a5f8f6c98d054131e4a097cad710c4.
R3 accepted after fix2 scoped32 GREEN and clean independent re-review. Prior full272 remains FAILED with its request-error failures addressed by fix2; no full-project acceptance claim.
Controller-owned unstaged edit: master Stage B plan R3 checkbox. Preserve it; do not stage it.

## Global Constraints

冻结时点仍为北京时间 2026-08-31 15:00，即 `2026-08-31T07:00:00+00:00`；SH/SZ/BJ 普通 A 股、五模板、七维权重、指标级同行资格、严格排除和证据门槛全部保持原合同。强池最多 20、等待池最多 50、行业上限 4/10 不变。本阶段不按最终入池资格筛选取证宇宙。

不改写旧 V2–V6 DDL、已有财务公式或已发布字节；不覆盖数据、SQLite、WAL/SHM、进度和历史结果；不自动合并 main 或推送。

以下不属于本阶段：真实生产来源或经济映射审批、生产签名、全市场实爬、定时调度、利润调整后 V 指标适配器、同行重排、最终置信度/分数/等级、选池、正式发布持久化。软件可支持后续增量采集，但本阶段开发验收不运行生产采集。

区间采集与收据落库在评分读取之外完成；不在跨证券数据库事务内发网络请求。

## R4：有限采集、分页恢复和不重复请求

**Files:** Create `ashare_pipeline/formal_range_worker.py`, `tests/test_formal_range_worker.py`; Modify `tests/formal_range_fixtures.py`。

Controller handoff amendment: additionally allow a minimal source-owned read-only
request-to-binding accessor in `ashare_pipeline/formal_range_source.py`, with its
regression covered in the R4 test module. The approved request is opaque and does
not expose its genuine binding; lease_next provides one only for leased tasks.
Cold resume of a verified page must still construct the source needed to derive
its successor after a crash between persist and enqueue. Preserve the existing
source_factory(binding) signature. Capture the original request validator in the
source owner and expose only authenticated read access to the genuine binding,
never a request/observation mint, caller registration, or JSON-to-authority path.
Reuse an existing authentic accessor if one exists; do not weaken the sealed
request or add arbitrary store queries/graph reconstruction to the worker.
This amendment expands the exact R4 whitelist to four paths, not general Source
refactoring. R3 fix2 source-only exception conversion is accepted and must remain intact.

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
- [ ] **审查并提交白名单。** 本任务原定三个文件，加上述批准的只读 Source 接点共四个文件；提交信息 `feat: resume bounded range collection without refetching verified pages`。


## Pre-dispatch cautions
R3 lease_next in-memory results may contain genuine request/binding handles for
restart execution. Do not emit them as diagnostic wire data or reconstruct them
from arbitrary serialized payload. Use current parent authentication, not history.
R3 exact Store/Observation/lease methods and history/current reconstruction are
pending. Fill actual accepted API before dispatch. The worker must preserve all
stored bytes and use typed transport diagnostics, never mint coverage. No sleep,
unbounded loop, real HTTP or production scheduler. Fixtures are R4-owned only
after R3 acceptance. Source version and refresh generation are not equivalent.

Root will add the accepted predecessor checkpoint and final execution/report
contract before dispatch. This draft is requirements preparation only, not an active task.

## Accepted R3 handoff

R3 is accepted at 3c3b3c1. Its actual lease
DTO includes genuine `request` and `binding` handles only in memory. Execution is
`source_factory(lease["binding"]).fetch_verified(lease["request"])`, followed by
`persist(lease["id"], worker_id, lease["attempt_id"], fetch=fetch)`. Other task DTOs
contain detached `payload` and `attempt_id`, never capabilities. The accepted
terminal R3 report must still be attached before dispatch.

Verified public Store surface (read-only handoff check on 2026-09-19):
`enqueue(request, *, refresh_generation)` returns a detached task with `id`,
`status`, and task `payload`; verified replay authenticates its receipt.
`lease_next(worker_id, *, lease_seconds)` returns None or a task DTO augmented
with genuine in-memory request/binding and `attempt_id`.
`renew(task_id, worker_id, attempt_id, *, lease_seconds)` and
`fail(task_id, worker_id, attempt_id, *, code, retryable, next_retry_at)` enforce
the current owner under the write lock. `persist(..., fetch=fetch)` returns a
genuine Observation. `read_verified(task_id)` authenticates current evidence;
`read_history(task_id)` is audit-only, not execution authority.
`select_current(request_fingerprint)` authenticates current candidates, but is
not a substitute for exact request/refresh-generation recovery.
Source continuation APIs are `next_page(observation)` and
`previous_calendar_request(observation)`; only the former belongs in worker
pagination. Both enforce current genuine observations. No public DTO factory
can mint execution requests or evidence.

Typed operational handling belongs around source fetching, not around the whole
run. `FormalSourceBlocked` is a subclass of `FormalRetryableSourceError`, so apply
its signed cooldown distinctly. Signature/configuration, lease ownership, raw/
receipt integrity, or persistence exceptions must remain failures; even a typed
source exception raised while replaying persisted evidence must not be relabeled
as an ordinary transport retry. Do not catch exception text to choose behavior.
Diagnostic `verified` is a task outcome only, never range/calendar coverage.

Recovery must authenticate the exact request and refresh generation. Same-request
evidence in a different refresh generation does not by itself suppress a requested
refresh. An authentic already-verified page may be reused without transport;
its continuation comes only from the genuine current observation and actual signed
pagination, never ordinal arithmetic on detached JSON. A crash after persisting a
page but before enqueueing its successor must remain recoverable without refetching
that verified page. Terminal/incomplete pages never establish complete coverage.

## Binding spec excerpts

### 9.2 封闭失败分类

| 分类 | 例子 | 处理 |
| --- | --- | --- |
| 前置条件/合同失败 | 宇宙不存在、完整 provider 未发布、未知版本、range 配置缺失/歧义、跨根/作用域、签名不符 | 终止批次；不制造普通证券待补来掩盖配置错误 |
| 完整性/选择失败 | 篡改/丢失已登记原始文件、同领先版本歧义、伪造对象、依赖替换、批次内更正 | 终止并撤销本次派生证明 |
| 已认证领域证据不足 | 当前收据未落库、实际事实/旗标/某日覆盖缺失、已记录领域冲突、合法计算的无效分母 | 对受影响规则记录 pending，保留独立已证实影响 |
| 采集操作失败 | 超时、403/429、挑战页、未完成分页 | 任务重试/熔断或终止诊断；不能成为“确认无覆盖/无价格” |

新入口使用类型化错误/缺失结果。不得捕获通用 ValueError 的文本或异常字符串猜测业务缺失；旧接口抛出的可信读取异常保持失败。

### 9.3 增量恢复与数据保留

区间任务沿用 pending、leased、verified、retryable_failed、terminal_failed、superseded 的状态语义和有限退避/租约检查。只重取未完成、缺失或实际已变化的请求；同请求/同代际且原始收据仍真实的已验证数据不重复抓取。单证券/来源失败不妨碍其他独立采集任务推进；跨证券政策批次仍须保持一致，不能把不同尝试拼成一个批次。

保存实际请求、尝试、失败码、收据和完成进度；不删除或覆盖旧快照。重启可复用通过重验的原始字节，必须重新认证和组装完整冻结批次。游标和完成勾选仅用于工作调度，不证明当前有效性。语义内容相同但无证据代际变化时重算结果确定；有来源更正时新身份与旧历史共存。

## Execution and report contract

Work ONLY in D:/Projects/AShareQiheng/.worktrees/formal-v3-implementation on
codex/formal-v3-implementation. Python:
D:/Projects/AShareQiheng/.venv/Scripts/python.exe. PowerShell is available;
bash is not. Edit via apply_patch. No dependency installation. No subagents.
Controller alone owns Git writes, staging only the exact four-file task whitelist;
do not commit, stage, reset, merge, push, or modify unrelated files yourself.
The user-owned tmpj4zv9_fq directory and all data/SQLite/WAL/SHM/history/progress
are preserved. Tests create only their own temporary fixtures; no real HTTP,
production database, signing, crawl, scoring, or stock pool publication.

Use TDD on this task's real behavior. Iterate focused tests first. Do the planned
four-module compatibility command once on the final frozen implementation, not
after every small edit. Existing tests can be expensive: persist incremental
output with process/session identity and explicit running/terminal status. Do
not launch duplicate suites or silently abandon a running process. A process
using CPU is only a liveness observation, not proof the code is correct or will
finish. Preserve actual RED/GREEN command, outputs, counts, exit codes and hashes.
Do not label a partial run or prior predecessor run as this task's completed run.

Full report belongs at
.superpowers/sdd/2026-09-12-formal-policy-stage-b1-range-foundation/task-R4-report.md.
Include current checkpoint first; actual implementation, TDD evidence, verification,
owned-file hashes, self-review and concerns. Return only status DONE /
DONE_WITH_CONCERNS / BLOCKED / NEEDS_CONTEXT, concise test summary, concerns and
report path. If a concrete ambiguity or missing predecessor API prevents progress,
send the exact issue to the controller instead of broadening the implementation.
Do not reread the entire master plan or repeat accepted predecessor work.
