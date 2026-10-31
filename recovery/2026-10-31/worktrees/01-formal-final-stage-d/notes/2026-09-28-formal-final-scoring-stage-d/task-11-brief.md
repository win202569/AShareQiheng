### Task 11: Wire the offline runner and complete full-chain acceptance

**Files:**
- Create: `ashare_pipeline/formal_final_runner.py`
- Create: `tests/test_formal_final_runner.py`
- Create: `tests/test_formal_final_integration.py`
- Create: `tests/test_formal_final_performance.py`
- Create: `docs/superpowers/evidence/formal-final-stage-d/README.md`

**Interfaces:**
- Consumes: configured repositories、exact frozen input、与 mode 匹配的 authenticated registries 和 `VerifiedCoverageManifest`；`test_preview` 接受 genuine purpose=`test` root，`official_candidate` 只接受带批准身份的 purpose=`official` root；不访问网络。
- Produces: `FormalFinalScoreRunner.run_preview(...) -> FormalFinalRunReceipt`；`.run_official_candidate(...) -> FormalFinalRunReceipt`；`.rebuild_affected(...) -> FormalFinalRunReceipt`；immutable diagnostics DTO。前者写 `mode=test_preview`，后者仅在 official gate 全通过时写 `mode=official_candidate`；两者成功 status 都是 `preview_ready`，均不等于 V9 的 validated/published。runner 不复制公式、不直接 SQL、不发布 V9。

- [ ] **Step 1: 写 runner RED。** `test_runner_closes_root_and_all_batch_identities_before_d1`、`test_preview_accepts_genuine_test_root_and_records_explicit_blockers`、`test_official_candidate_rejects_failed_gates_without_writing_an_official_mode_row`、`test_official_candidate_is_still_preview_ready_and_never_v9_published`、`test_runner_has_no_network_or_legacy_score_input_path`、`test_v1_v2_prepolicy_and_recovery_dtos_cannot_impersonate_stage_d_inputs`、`test_two_independent_runs_have_identical_canonical_result_hash`、`test_rebuild_affected_derives_changes_from_current_verified_manifest`。
- [ ] **Step 2: 写 20/23 genuine integration RED。** 从一个十角色 root 跑 D1→D2→D3→V8，反向核对 frozen/root/B/C/D1/D2/D3/coverage hashes；覆盖 ready、pending、veto、single-pool prohibition、cyclic cap、no-consensus 和同行回退。断言 strong≤20、wait≤50、行业≤4/10、池互斥、完整成员唯一状态。
- [ ] **Step 3: 写攻击与性能 RED。** 对跨根/冻结/证券/批次、DB row tamper、registry/source correction、最终复验撤销执行集成攻击。记录各阶段耗时、完整验证次数、成员/指标/cohort/排序/重建数、状态/reason/veto/资格/池数、cap skip、parse/rederive/recheck 次数；设结构性上限“每个 source batch 每阶段至多一次完整解析、每 cohort 至多一次排序”，不写易波动墙钟硬阈值。
- [ ] **Step 4: 运行 RED。**

Run: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_runner tests.test_formal_final_integration tests.test_formal_final_performance -v`

Expected: runner 不存在或完整链未接通。

- [ ] **Step 5: 实现薄 runner。** 顺序固定：coverage/root/frozen identity closure → B/C 与 D1 prepared → D2 → D3 → final recheck → repository atomic commit。`rebuild_affected` 先调用 trusted diff，再构造全新 append-only run；复用不绕过逐次验活。
- [ ] **Step 6: 运行 Stage D GREEN。**

Run: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_final_fixture tests.test_formal_final_score_inputs tests.test_formal_final_score_input_guards tests.test_formal_final_scoring tests.test_formal_final_scoring_guards tests.test_formal_final_eligibility tests.test_formal_final_eligibility_guards tests.test_formal_pool tests.test_formal_pool_guards tests.test_formal_coverage_manifest tests.test_formal_coverage_guards tests.test_formal_final_migration tests.test_formal_final_repository tests.test_formal_final_atomicity tests.test_formal_final_invalidation tests.test_formal_final_runner tests.test_formal_final_integration tests.test_formal_final_performance -v`

Expected: 全部 PASS，0 failure/error/skip。

- [ ] **Step 7: 运行受影响完整回归。**

Run: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_registry_manifest tests.test_formal_feature_repository tests.test_formal_metric_engine tests.test_formal_metric_context tests.test_formal_score_inputs tests.test_formal_scoring tests.test_formal_policy_repository tests.test_formal_policy_integration tests.test_formal_valuation_batch tests.test_formal_valuation_ranking tests.test_formal_valuation_integration tests.test_state_store -v`

Expected: 全部 PASS，现有 A/B/C proof bytes、V7 range schema 和旧 provisional score tables 均未被改写。

- [ ] **Step 8: 保存验收证据并独立终审。** README 记录精确 commit、命令、计数、耗时、诊断和已知 production blockers；不得保存数据库、WAL/SHM 或原始用户数据。终审必须分别检查 spec coverage、trust boundary、原子性、经济规则、性能结构和 V8/V9 版本边界。
- [ ] **Step 9: 提交 runner 与验收。**

```powershell
git add ashare_pipeline/formal_final_runner.py tests/test_formal_final_runner.py tests/test_formal_final_integration.py tests/test_formal_final_performance.py docs/superpowers/evidence/formal-final-stage-d/README.md
git commit -m "feat: complete formal final scoring stage D"
```

## Definition of Done

- [ ] D1–D4 的所有新测试和受影响回归为 0 failure/error/skip。
- [ ] 冻结宇宙每个成员恰有一个最终状态；当前 ordinary-A 批次 `out_of_scope=0`。
- [ ] 七维、C、S0、Sc、Sbase、B、R、risk exposure、grades 与 cap trace 可从规范输入精确重演。
- [ ] strong/wait 资格、排序、行业 cap、容量、互斥和不回填全部有未舍入 Decimal 边界测试。
- [ ] coverage manifest 对缺失、无覆盖、schema、registry、identity、integrity、temporal、ambiguous 和 dependency 失败关闭。
- [ ] SQLite 从 V2–V7 连续迁移到 V8，V7 range 数据与精确 DDL 保持不变；无 torn Stage D run。
- [ ] 单证券、cohort、policy 和 global 失效范围可解释，所有变化产生新 append-only run。
- [ ] 20/23 genuine 集成通过；全量正式运行仍被带批准身份的 purpose=`official` 生产合同根或完整 SH/SZ/BJ coverage gate 阻断时，两个正式池保持未发布。
- [ ] 每个任务均有独立提交、独立 reviewer 结论和对应 evidence；未提交任何数据、SQLite、WAL/SHM、进度或备份文件。
