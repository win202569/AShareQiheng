### Task 5: Full-universe peer reranking, diagnostics and acceptance

**Files:**
- Modify: `ashare_pipeline/formal_valuation_engine.py`
- Create: `tests/test_formal_valuation_ranking.py`
- Create: `tests/test_formal_valuation_integration.py`
- Modify: `docs/superpowers/plans/2026-09-25-formal-valuation-policy-adapter-stage-c.md`

**Interfaces:**
- Consumes: genuine published `PolicyAdjustedValuationBatch`。
- Produces: `PolicyAdjustedValuationPeerContext`；`PolicyAdjustedValuationScore`；`valuation_peer_eligible(item) -> bool`；`build_valuation_peer_context(batch, *, metric_id, security_id)`；`score_valuation_percentile(batch, context)`；`FormalValuationRepository.diagnostic_report(batch) -> MappingProxyType`。

- [ ] **Step 1: 写同行语义 RED 测试。**

```python
def test_one_adjustment_reranks_every_member_in_the_cohort(self):
    batch = self.fixture.build_adjusted_batch()
    before = self.fixture.base_percentiles("V.normalized_earnings_yield")
    after = {}
    for security_id in batch.security_ids:
        context = build_valuation_peer_context(
            batch, security_id=security_id,
            metric_id="V.normalized_earnings_yield")
        after[security_id] = score_valuation_percentile(batch, context).percentile
    self.assertNotEqual(after["BJ430001"], before["BJ430001"])
    changed_peers = [sid for sid in batch.security_ids
                     if sid != "BJ430001" and after[sid] != before[sid]]
    self.assertTrue(changed_peers)
```

加入：二级 20、二级 19 回退一级 20、一级仍 19、焦点入样、并列平均秩、lower 只反转分位数、负/零/极值、pending affected 排除、pending unaffected 保留、跨批次 context 拒绝、同 cohort context 共享同一不可变同行 tuple。

- [ ] **Step 2: 写确定性计数和一次排序测试。**

```python
def test_each_cohort_is_grouped_and_sorted_once(self):
    batch = self.fixture.build_adjusted_batch()
    for security_id in batch.security_ids:
        context = build_valuation_peer_context(
            batch, security_id=security_id,
            metric_id="V.normalized_earnings_yield")
        score_valuation_percentile(batch, context)
    counts = self.fixture.repository.diagnostic_report(batch)
    self.assertEqual(counts["group_index_builds"], 1)
    self.assertEqual(counts["sorts_by_cohort"][context.cohort_hash], 1)
    self.assertEqual(counts["full_financial_rederivations"], 0)
    self.assertEqual(counts["registry_full_parses"], 1)
    self.assertEqual(counts["base_batch_full_validations"], 1)
    self.assertEqual(counts["policy_batch_full_validations"], 1)
```

规范 payload 只保存确定性计数；墙钟耗时由 `repository.diagnostic_report(batch)` 的非规范、只读报告返回，并绑定 `batch_hash`。测试不得对毫秒阈值作脆弱断言。

- [ ] **Step 3: 运行 RED。**

Run: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_valuation_ranking -v`

Expected: peer/score API 尚不存在或没有 cohort cache，测试失败。

- [ ] **Step 4: 实现一次分组、一次排序和独立证明。**

```python
def build_groups(rows):
    groups = {}
    for item in rows:
        if not valuation_peer_eligible(item):
            continue
        for scope, industry_id in (
                ("template_secondary_industry", item.secondary_industry),
                ("template_primary_industry", item.primary_industry)):
            key = (item.metric_id, item.template_id, scope, industry_id)
            groups.setdefault(key, []).append(item.security_id)
    return {key: tuple(sorted(ids)) for key, ids in groups.items()}

def rank_values(values, direction):
    ordered = sorted(values)
    ranks = {}
    first = 0
    with localcontext(_arithmetic_context()):
        while first < len(ordered):
            last = first + 1
            while last < len(ordered) and ordered[last] == ordered[first]:
                last += 1
            rank = (Decimal(first + 1) + Decimal(last)) / 2
            percentile = Decimal(100) * (rank - Decimal("0.5")) / len(ordered)
            ranks[ordered[first]] = (rank, Decimal(100) - percentile
                                     if direction == "lower" else percentile)
            first = last
    return MappingProxyType(ranks)
```

cohort hash 必须覆盖 adjusted batch hash、metric、definition、adapter registry、direction、scope 和同行 ID；score hash 覆盖焦点 adjusted input hash、平均秩、分位数和完整 peer context。所有证明复用 batch publication capability，不能脱离所属 batch 使用。

- [ ] **Step 5: 写端到端与诊断验收。**

```python
def test_signed_policy_to_adjusted_value_to_peer_score_is_replayable(self):
    first = self.fixture.build_adjusted_batch()
    score1 = self.fixture.score(first, "BJ430001",
                                "V.normalized_earnings_yield")
    second = self.fixture.build_adjusted_batch()
    score2 = self.fixture.score(second, "BJ430001",
                                "V.normalized_earnings_yield")
    self.assertEqual(first.canonical_bytes(), second.canonical_bytes())
    self.assertEqual(score1.canonical_bytes(), score2.canonical_bytes())
    report = self.fixture.repository.diagnostic_report(second)
    self.assertEqual(report["batch_hash"], second.batch_hash)
    self.assertEqual(report["security_count"], 20)
    self.assertEqual(report["valuation_row_count"], 60)
```

集成测试还要从 score 反向核对 peer context、adjusted row、policy decision、normalization basis、base metric input、adapter definition 和根角色哈希；证明没有 G/M cap、Sc/B/R、eligibility 或 pool 字段。

- [ ] **Step 6: 运行 Stage C GREEN。**

Run: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_valuation_adapter_contract tests.test_formal_valuation_adapter tests.test_formal_valuation_batch tests.test_formal_valuation_batch_guards tests.test_formal_valuation_ranking tests.test_formal_valuation_integration -v`

Expected: 全部 PASS，0 failure，0 error。

- [ ] **Step 7: 运行受影响完整回归并保存诊断。**

Run: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_registry_manifest tests.test_formal_scoring_registry tests.test_formal_policy_contract tests.test_formal_policy_registry tests.test_formal_policy_registry_guards tests.test_formal_policy_evaluator tests.test_formal_policy_repository tests.test_formal_policy_batch_guards tests.test_formal_policy_integration tests.test_formal_metric_context tests.test_formal_metric_features tests.test_formal_metric_engine tests.test_formal_metric_batch_guard tests.test_formal_score_inputs tests.test_formal_scoring tests.test_formal_valuation_adapter_contract tests.test_formal_valuation_adapter tests.test_formal_valuation_batch tests.test_formal_valuation_batch_guards tests.test_formal_valuation_ranking tests.test_formal_valuation_integration -v`

Expected: 全部 PASS；把模块数、测试数、耗时、失败/错误/跳过、五个分阶段耗时、cohort/排序/待补计数写入 `.superpowers/sdd/2026-09-25-formal-valuation-policy-adapter-stage-c/task-C5-report.md`。报告不纳入正式证明哈希。

- [ ] **Step 8: 独立审查、修复并作根级新鲜复验。**

审查白名单为本计划列出的生产、测试、fixture、spec 和 plan 文件。审查必须核对：v1/v2 兼容边界、证明伪造面、跨根/跨批次、pending affected/unaffected、Decimal 失败关闭、整组重排、缓存失效、外层回滚和无最终评分越界。每个审查发现用单独失败测试复现后修复；修复后重跑 Step 6、Step 7，并在最终 HEAD 上由根代理再跑 Stage C 六模块验收。

- [ ] **Step 9: 更新计划证据并提交 C5。**

```powershell
git add ashare_pipeline/formal_valuation_engine.py tests/test_formal_valuation_ranking.py tests/test_formal_valuation_integration.py docs/superpowers/plans/2026-09-25-formal-valuation-policy-adapter-stage-c.md
git commit -m "feat: rerank policy-adjusted valuation peers"
```

最终完成条件：所有计划框勾选；工作区无意外文件；提交不含生产数据、SQLite、WAL/SHM 或进度文件；未获用户单独授权时不推送、不合并 main、不开始 Stage D。
