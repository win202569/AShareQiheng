# Task W3 draft brief

DRAFT — NOT DISPATCHED. W1/W2 acceptance, actual APIs, final BASE and full global/spec excerpts required before execution.

## W3：唯一全冻结批次入口与失败撤销

**Files:** Create `ashare_pipeline/formal_policy_repository.py`, `tests/test_formal_policy_repository.py`, `tests/test_formal_policy_batch_guards.py`; Modify `tests/formal_policy_runtime_fixtures.py`。

**Interfaces:**

- Consumes: same-store feature/context/range 仓库、FormalMetricCurrentInputProvider、FormalMetricContextRepository、`_metric_batch_guard(provider, store)`、genuine scoring/policy registry；F2/F3/W1 的 current selections。
- Produces: `FormalPolicyRepository(feature_repository, context_repository, range_store, *, registry_signature_verifier)`；`.build_batch(frozen_input_hash, *, scoring_registry, policy_registry) -> VerifiedPolicyResultBatch`。
- 新闭包私有 proof 类型 `VerifiedPolicyEvidenceBatch`、`PolicyDecision`、`PolicyResult`、`VerifiedPolicyResultBatch`：构造器拒绝；按规格提供 `.require_verified()`，`.require_official()` 只可作为同一验证路径的兼容别名；另有 `.to_dict()`、`.canonical_bytes()`；子结果含所属 batch identity，跨批次组合拒绝。最终 batch 属性 `.security_ids/.results/.evidence_batch/.batch_hash`，results 按 security_ids 顺序 tuple。
- 单证券 PolicyResult 属性 `.security_id/.decisions/.pending_requirements/.dimension_caps/.pool_prohibitions/.states/.normalization_basis/.evidence_state`，纯 W2 字典不能通过其 require_official。
- `PolicyRuntimeFixture(range_enabled=True)` 新增 `.policy_repository`；`.build_policy_batch()` 使用 fixture 当前真实 frozen/scoring/policy；`.populate_policy_evidence()` 为每个冻结成员写 industry、显式清晰状态、F2 财务及 W1 日历/行情，真实小规模 producer receipts；默认不省略证券。

- [ ] **写失败测试。**

```python
def test_complete_enumeration_includes_pending_security(self):
    from tests.formal_policy_runtime_fixtures import PolicyRuntimeFixture
    fixture = PolicyRuntimeFixture(range_enabled=True)
    self.addCleanup(fixture.close)
    # 完整 universe 已存在，行业/状态/行情仍未覆盖；未分配模板不要求伪造财务。
    batch = fixture.build_policy_batch()
    batch.require_official()
    self.assertEqual(tuple(result.security_id for result in batch.results),
                     tuple(batch.security_ids))
    self.assertEqual(len(batch.results), 3)
    self.assertTrue(all(result.pending_requirements for result in batch.results))
```

增加全图/入口替换、跨库/根/证券/模板/冻结/批次、伪造scoring/policy、缺 universe、配置缺失与歧义、provider 未发布、copy/deepcopy/object.__new__、实例影子方法和类方法替换；未知membership不造五套规则。已赋模板但无 provider 是失败，和上述“模板未知无需取财务”不同。

屏障专例在第一证券读完后修改第二证券、先缺后有、equal-leading ambiguity、provider 重入发布且内部吞错、DB 写入、原始文件改动但 DB 未变、source 配置替换、最终 rollback/close 抛错；任何被测试钩子捕获的未发布子对象均不能通过 require_official。钩子只在测试替换实际依赖，不能添加生产公开 `skip_verify`。

- [ ] **运行 RED。** `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_repository tests.test_formal_policy_batch_guards -v`。
- [ ] **实现闭包和生命周期。** 按 `formal_metric_engine._install_engine` 的精确类/方法/来源依赖捕获模式建立仓库和 proof 记录；不用公共 `verified=True`、可读 nonce 或自报 hash 作为权能。F2/F3/W1 `.recheck()`、context `.recheck_batch()`、九角色源文件重验全部进入最终检查。将值和来源规范 payload 先脱离外部引用，昂贵取证阶段不持有 writer lock。

以下是本任务私有工厂的控制流，`prepare/read_and_recheck/mark_published/revoke` 均在同一闭包内定义，不导出：

```python
def publish_under_guard(provider, store, prepare, read_and_recheck,
                        mark_published, revoke):
    prepared = None
    try:
        with _metric_batch_guard(provider, store) as guard:
            prepared = prepare()
            read_and_recheck(prepared)
            def finalize():
                read_and_recheck(prepared)
                mark_published(prepared)
                return prepared
            result = guard.finalize(finalize)
        return result
    except BaseException:
        if prepared is not None:
            revoke(prepared)
        raise
```

闭包内 prepare 自行读取冻结宇宙、加载 source v2 配对、解析所有行业，逐证券读取适用证据并调用 W2；返回共享初始 false publication 的完整根和子对象。read_and_recheck 检查真实 provider/DB/context/feature/current range selection/原始 bytes 及入口依赖，比较完整身份，也检查缺失仍然缺失。mark_published 只改变闭包 publication；revoke 对同批次全部子对象生效。这些回调不能由公共调用者提供。外层捕获覆盖 context-manager 的关闭异常，不能只在 guard.finalize 内撤销。

批次 hash 计算依赖顺序：各来源/selection payload → 各非正式 rule input/decision payload → evidence batch payload → result batch payload；各自先算无自身 hash 的内容，子对象之后附加所属 batch hash 但不反向改变父身份。保存 parent_link 单独参与资格验证，避免 selfhash/circular hash。

- [ ] **运行 GREEN。** `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_repository tests.test_formal_policy_batch_guards tests.test_formal_metric_batch_guard tests.test_formal_metric_engine -v`。
- [ ] **审查并提交白名单。** 本任务四个文件；提交信息 `feat: publish revocable complete-universe policy result batches`。


## Membership handoff ruling to carry into final brief

Per design section2, W3 owns authentic frozen membership: load the genuine Universe via FormalMetricContextRepository using frozen_input_hash only as locator; absence is precondition failure. Private iteration must use its complete canonical security_ids, never caller subset or all stored market rows. W1 genuine range requests/selections prove acquisition and calendar lineage, not universe membership. Reject nonmember selections from formal batch; bind frozen_input_hash/universe_hash/population_hash and ordered IDs; recheck universe and industry before publication. Pre-batch collection likewise enumerates a genuine Universe proof. See task-W1-interface-audit.md for verified interface references.

Required tests: reads market only for verified Universe members; genuine nonmember range observations cannot enter batch; hash locator is reloaded not trusted; universe mutation during market reads revokes entire batch; extra stored nonmember data is not enumerated; missing Universe fails before market selection. No hidden membership authority in calendar coverage, security ID strings or Store inference.

Keep v1 signed policy unchanged: existing signed bool/enum event flags only. Quantified event consumption remains an explicit capability gap, not a fabricated nonexistent-rule pending decision. No production capture/signing/scoring/selection, database/history deletion, main merge or push.

