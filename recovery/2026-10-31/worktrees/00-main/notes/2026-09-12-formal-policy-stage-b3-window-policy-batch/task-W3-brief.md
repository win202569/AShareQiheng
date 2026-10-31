# W3 task brief — sole frozen-universe policy batch publication and revocation

Plan: `docs/superpowers/plans/2026-09-12-formal-policy-stage-b3-window-policy-batch.md`

Original BASE: `2c021fc` (`docs: record accepted W2 policy evaluation milestone`)

Recovery checkpoint: `18c45b31caf4f968de99d9513ed22c67cfffa08d`
(`提交进度`). This commit is already present on the remote branch and contains
the seven-file W3 intermediate implementation described in `task-W3-report.md`.
It is **not** an accepted W3 result. Resume from it; do not discard, rewrite,
amend, or repeat the already-recorded RED. The remaining approved work is:

- implement and test exact-owner/thread nested reuse in
  `formal_metric_batch_guard.py` and `test_formal_metric_batch_guard.py`;
- resolve the genuine populated W3 failure without skipping any F2/F3/W1
  recheck;
- complete the three queued self-review regressions in the report (exact minted
  class binding, captured W1/W2/deepcopy dependencies, and literal close-throws);
- run the focused W3 GREEN and then the mandated four-module compatibility gate;
- update the existing W3 report with fresh terminal evidence and hashes.

The worktree and index were clean and no Python process was running when this
recovery was dispatched. Controller alone performs all further Git writes.

## Scope and files

Create exactly:

- `ashare_pipeline/formal_policy_repository.py`
- `tests/test_formal_policy_repository.py`
- `tests/test_formal_policy_batch_guards.py`

Modify exactly:

- `tests/formal_policy_runtime_fixtures.py`
- `ashare_pipeline/formal_range_store.py`
- `ashare_pipeline/formal_range_source.py`
- `tests/test_formal_range_store.py`
- `ashare_pipeline/formal_metric_batch_guard.py`
- `tests/test_formal_metric_batch_guard.py`

The three range paths above are a controller-approved load-bearing predecessor
interface expansion discovered during W3 preflight. Add only a closure-owned,
read-only private identity validator sufficient for W3 to prove that an exact
genuine `FormalRangeStore` owns the expected exact `StateStore` and exact
signature verifier. It must reuse the range Store's existing private `record`
validation, expose no StateStore/verifier/root/factory object, mint no authority,
and remain absent from `__all__`. Add focused TDD coverage for genuine same-Store
acceptance, cross-Store rejection, verifier mismatch, and copied/forged Store
rejection. Do not otherwise change range behavior.

The two metric-guard paths above are a second controller-approved load-bearing
predecessor expansion discovered by the genuine populated W3 RED. W3's required
final `read_and_recheck` executes inside the outer guard's `BEGIN IMMEDIATE`,
while genuine F2 recheck opens `_metric_batch_guard` again and otherwise attempts
a conflicting second writer transaction. Add only safe nested reuse for the
exact same provider and exact same StateStore, on the exact thread that owns an
already-active finalization. The nested guard must not open a second observer or
writer transaction, must remain covered by the outer epoch/database/finalizing
checks, must not permit reentrant publication, must not authorize another Store
or provider, and must preserve all existing non-nested behavior. Add focused TDD
for successful same-owner nesting plus cross-owner/provider and publication
attacks. Do not skip or weaken any F2/F3/W1 final recheck.

Do not edit any other tracked path. Do not touch production data, SQLite/WAL/SHM,
progress/history, network capture, scoring, pools, merge, or push. Controller
alone performs Git writes. Do not dispatch subagents.

## Interfaces

- Consume same-Store feature/context/range repositories,
  `FormalMetricCurrentInputProvider`, `FormalMetricContextRepository`,
  `_metric_batch_guard(provider, store)`, genuine scoring/policy registries, and
  F2/F3/W1 current selections.
- Produce `FormalPolicyRepository(feature_repository, context_repository,
  range_store, *, registry_signature_verifier)` and
  `.build_batch(frozen_input_hash, *, scoring_registry, policy_registry)
  -> VerifiedPolicyResultBatch`.
- New closure-private proof types: `VerifiedPolicyEvidenceBatch`,
  `PolicyDecision`, `PolicyResult`, `VerifiedPolicyResultBatch`. Their public
  constructors reject callers. Each exposes `.require_verified()`;
  `.require_official()` is only a compatibility alias to the identical
  verification path. Each has `.to_dict()` and `.canonical_bytes()`.
- Child results carry owning batch identity; cross-batch composition is rejected.
  Final batch attributes are `.security_ids`, `.results`, `.evidence_batch`,
  `.batch_hash`; results are a tuple in exact `security_ids` order.
- Each `PolicyResult` exposes `.security_id`, `.decisions`,
  `.pending_requirements`, `.dimension_caps`, `.pool_prohibitions`, `.states`,
  `.normalization_basis`, `.evidence_state`. A pure W2 dictionary can never pass
  its official/verified check.
- With `range_enabled=True`, `PolicyRuntimeFixture` gains `.policy_repository`.
  `.build_policy_batch()` uses the fixture's genuine current frozen/scoring/
  policy objects. `.populate_policy_evidence()` writes, for every frozen member,
  industry, explicitly clear context/state evidence, F2 financial evidence and
  W1 calendar/market evidence through genuine small producer receipts. Default
  population omits no security.

## Mandatory TDD matrix

Start with failing tests and preserve the exact RED output before production
implementation. The basic complete-enumeration test must prove that a pending
security remains in exact frozen-universe order and the result count is three.

Cover all of these attacks and lifecycle cases:

- full graph/entry replacement;
- cross-Store, signature root, security, template, freeze instant and batch;
- forged scoring/policy registries;
- missing universe, missing/ambiguous configuration, provider unpublished;
- `copy`, `deepcopy`, `object.__new__`, instance-method shadowing and class-method
  replacement;
- unknown membership does not fabricate decisions for all five templates;
- an assigned template without a provider is failure (distinct from unknown
  template membership, which need not fetch financial evidence);
- after reading security one, mutate security two;
- initially missing then present;
- equal-leading ambiguity;
- provider re-enters publication and swallows its inner error;
- database write during guarded evaluation;
- source bytes changed while database stays unchanged;
- source configuration replacement;
- final rollback/close throws;
- every captured unpublished child remains unable to pass
  `.require_official()`/`.require_verified()`.

Test hooks may replace real dependencies in tests only. Never add a production
`skip_verify` or other public bypass.

Required commands:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_repository tests.test_formal_policy_batch_guards -v
```

The command above must first be a genuine RED for missing behavior and later
GREEN. Final focused compatibility command:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_repository tests.test_formal_policy_batch_guards tests.test_formal_metric_batch_guard tests.test_formal_metric_engine -v
```

Do not start a project-wide suite; report any additional narrow compatibility
modules separately.

## Closure and lifecycle implementation constraints

Follow `formal_metric_engine._install_engine`'s exact class/method/dependency
capture pattern. Do not use public `verified=True`, readable nonce, or self-
reported hash as authority. The final verification path must include F2/F3/W1
`.recheck()`, context `.recheck_batch()`, and revalidation of all nine role source
files. Detach values/source-spec payloads before expensive evidence work; do not
hold the writer lock during expensive acquisition.

All of `prepare`, `read_and_recheck`, `mark_published`, and `revoke` are private
callbacks defined in the same closure and cannot be supplied by public callers.
The required control flow is:

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

Inside the closure, `prepare` reads the frozen universe, loads paired source-v2
configuration, parses all industry evidence, reads every applicable evidence
selection and invokes W2. It builds one complete root and all children sharing an
initial unpublished state. `read_and_recheck` validates the genuine provider,
database, context, feature, current range selections, raw bytes and entry
dependencies; it compares full identities and verifies that missing evidence is
still missing. `mark_published` changes only the closure-private publication
state. `revoke` invalidates every child in the batch. The outer `BaseException`
handler must also revoke when context-manager close/rollback itself raises.

Hash dependency order is fixed:

1. source/selection payloads;
2. informal rule-input/decision payloads;
3. evidence-batch payload;
4. result-batch payload.

Each object hashes content without its own hash. Children then carry the owning
batch hash without changing the parent's identity. A separate `parent_link`
participates in eligibility verification to avoid circular/self hashing.

## Report contract

Write the full implementation report to
`.superpowers/sdd/2026-09-12-formal-policy-stage-b3-window-policy-batch/task-W3-report.md`.
Include RED and GREEN commands, exact counts/timings/output summaries, changed
files and SHA-256 hashes, lifecycle/attack coverage, self-review, and concerns.
Return only status, one-line test summary, concerns, and report path. Do not
commit.
