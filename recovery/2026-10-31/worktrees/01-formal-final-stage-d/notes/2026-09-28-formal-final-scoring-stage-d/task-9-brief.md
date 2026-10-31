### Task 9: Persist one append-only Stage D result atomically

**Files:**
- Create: `ashare_pipeline/formal_final_repository.py`
- Create: `ashare_pipeline/formal_final_publication.py`
- Modify: `ashare_pipeline/formal_final_score_inputs.py`
- Modify: `ashare_pipeline/formal_final_scoring.py`
- Modify: `ashare_pipeline/formal_final_eligibility.py`
- Modify: `ashare_pipeline/formal_pool.py`
- Create: `tests/test_formal_final_repository.py`
- Create: `tests/test_formal_final_atomicity.py`

**Interfaces:**
- Consumes: `StateStore`、genuine coverage/D1/D2/D3 batches and shared unpublished Stage D capability。
- Produces: `FormalFinalRunRepository.commit_complete_run(...) -> FormalFinalRunReceipt`；`get_run(run_id) -> FormalFinalRunSnapshot | None`；`list_runs_by_input_manifest(hash) -> tuple[...]`。恢复对象是只读 DTO，不是 proof。
- Internal: `FormalFinalPublicationCoordinator.prepare(...)` 是 D1–D3 sealed prepared adapters 的唯一调用者；它不导出 mint token。事务内 `arm()` 后外部 `require_verified()` 仍失败；SQLite commit 成功后执行已预检、不可失败、无 I/O/分配的 `mark_committed()`，proof 才统一生效。任何 commit 异常调用 `revoke()`。

```python
def commit_complete_run(self, *, mode, coverage_manifest, input_batch,
                        score_batch, eligibility_batch, pool_batch
                        ) -> FormalFinalRunReceipt: ...
```

- [ ] **Step 1: 写 repository RED。** `test_complete_run_persists_exact_universe_and_all_artifact_hashes`、`test_decimals_round_trip_as_canonical_text_without_float`、`test_same_input_allows_two_append_only_replays_with_same_result_hash`、`test_historical_run_cannot_be_updated_or_rebound`、`test_cross_root_or_forged_batch_is_rejected_before_write`、`test_recovery_dto_never_authenticates_as_live_proof`。
- [ ] **Step 2: 写原子故障矩阵 RED。** 对每张子表插入、规范序列化、最终来源复验、集合复验、`arm()` 和 SQLite commit 注入异常；`test_every_commit_failure_leaves_zero_stage_d_rows_and_revokes_children` 断言全无或全有，`test_armed_proofs_remain_invisible_until_commit_returns` 断言无短暂可见窗口，`test_post_commit_mark_committed_is_prevalidated_and_cannot_fail` 固定 flip 合同。另测合法 blocked run 一次性写入且无伪池，并覆盖普通构造/copy/pickle/弱引用重定向/方法替换与撤销攻击。
- [ ] **Step 3: 运行 RED。**

Run: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_repository tests.test_formal_final_atomicity -v`

Expected: repository 不存在。

- [ ] **Step 4: 实现唯一批量写入口。** 事务前完成长计算并预检 committed flip；事务内重验冻结宇宙/根/依赖，写 header、五种 canonical artifacts、全成员 input/status/eligibility/两池 decision、可用 scorecards 和 dependency rows，逐表比较精确 security 集合及 hash，最后只 `arm()` 并提交 SQLite。commit 返回后立即执行不可失败 `mark_committed()`；异常路径 rollback/revoke，绝不先开放 proof。
- [ ] **Step 5: 明确禁止逐表 API。** 不实现 `put_*`、`replace_*`、`mark_ready`；run status 只允许 `preview_ready/blocked`，`validated/published` 留给 V9 release。
- [ ] **Step 6: 运行 GREEN、独立审查并提交。**

Run: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_repository tests.test_formal_final_atomicity tests.test_formal_final_migration -v`

```powershell
git add ashare_pipeline/formal_final_repository.py ashare_pipeline/formal_final_publication.py ashare_pipeline/formal_final_score_inputs.py ashare_pipeline/formal_final_scoring.py ashare_pipeline/formal_final_eligibility.py ashare_pipeline/formal_pool.py tests/test_formal_final_repository.py tests/test_formal_final_atomicity.py
git commit -m "feat: persist atomic formal final runs"
```

