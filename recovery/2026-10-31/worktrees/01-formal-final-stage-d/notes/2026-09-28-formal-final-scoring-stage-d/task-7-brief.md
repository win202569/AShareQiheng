### Task 7: Audit production coverage and enforce fail-closed gates

**Files:**
- Create: `ashare_pipeline/formal_coverage_manifest.py`
- Create: `tests/test_formal_coverage_manifest.py`
- Create: `tests/test_formal_coverage_guards.py`

**Interfaces:**
- Consumes: verified frozen universe、registry bundle、repository validation callbacks、数据库/工作区只读身份和每项 `(frozen_input_hash, security_id, domain, selector_hash, period_or_window, exchange)` 需求。
- Produces: `VerifiedCoverageManifest`；`FormalCoverageAuditor.audit(...)`；`.require_preview_ready()`；`.require_official_ready()`；规范 member requirement rows、blockers、manifest hash 和非规范 timing diagnostics。

- [ ] **Step 1: 写 coverage class RED。** 允许值严格为规格 15 类。精确测试名：`test_absent_record_is_blocked_not_verified_no_coverage`、`test_verified_no_coverage_requires_authenticated_explicit_source_statement`、`test_missing_table_is_blocked_schema_not_zero_rows`、`test_exchange_calendar_cannot_be_reused_across_sh_sz_bj`、`test_every_required_member_domain_key_is_unique_and_enumerated`、`test_sql_counts_are_diagnostic_only_and_never_grant_readiness`、`test_audit_time_and_timing_diagnostics_do_not_change_canonical_hash`。
- [ ] **Step 2: 写 gate/guard RED。** 覆盖 registry purpose、approval、签名/哈希、temporal cutoff、units、parser/mapping version、ambiguous duplicate、source correction、DB/status stale mismatch；缺 production contract 时 preview 可审计但 official 阻断。另加 `test_coverage_proof_rejects_plain_construction_copy_pickle_weakref_redirect_method_replacement_and_revocation` 及旧 v1/v2 普通对象冒充测试。
- [ ] **Step 3: 运行 RED。**

Run: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_coverage_manifest tests.test_formal_coverage_guards -v`

Expected: 新模块不存在。

- [ ] **Step 4: 实现验证器。** 每个 formal domain 必须调用所属 repository 验证入口；记录 source/dataset/request/refresh/task/snapshot/content/manifest/parser/mapping/timestamps/units/class/reasons/evidence hashes。`audit_at_utc` 与 timing diagnostics 不进入规范结果 hash。
- [ ] **Step 5: 运行 GREEN、独立审查并提交。**

Run: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_coverage_manifest tests.test_formal_coverage_guards tests.test_formal_snapshot_repository tests.test_formal_universe -v`

```powershell
git add ashare_pipeline/formal_coverage_manifest.py tests/test_formal_coverage_manifest.py tests/test_formal_coverage_guards.py
git commit -m "feat: audit formal production coverage"
```

