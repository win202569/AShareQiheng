# Task 2: Signed valuation adapter contract

## Implementation

- Added `ashare_pipeline/formal_valuation_adapter_contract.py`. Its loader accepts only genuine manifest v2 bundles and sealed same-root scoring/policy registries, rereads the signed `valuation_adapter` child, validates exact 15-entry V-metric coverage and exact affected-adapter coverage, and derives root-bound `original_definition_hash` values without serializing those hashes into the child. The registry retains its construction record, canonical bound payload and indexes in a closure; source or adapter mutation invalidates official qualification. It defines contracts only, with no valuation execution or ranking.
- Extracted the metric engine's definition producer unchanged in payload and hash algorithm as `_scoring_metric_definitions`. Both engine and adapter loader capture this function identity. Its digest dependency remains captured as before extraction.
- Extended the policy fixture with a signed ten-role adapter child and explicit manifest controls. Rule IDs come from cyclic registry mapping keys, paired with their rule values.
- Added contract mutation, proof guard, v1 exclusion, fixture guard, and stable metric-hash regressions.

## Files

- `ashare_pipeline/formal_valuation_adapter_contract.py` (new)
- `ashare_pipeline/formal_metric_engine.py`
- `tests/test_formal_valuation_adapter_contract.py` (new)
- `tests/test_formal_metric_engine.py`
- `tests/formal_policy_fixtures.py`

## RED/GREEN evidence

1. The initial adapter test command failed with `ModuleNotFoundError: ashare_pipeline.formal_valuation_adapter_contract` as specified. The metric regression failed because `_scoring_metric_definitions` did not exist.
2. After implementation, the positive contract test exposed a missing tenth role hash in the bound payload. Adding the signed adapter hash made it pass.
3. Self-review added a method-replacement guard test. It failed because the registry accepted a replaced class member, then passed after the closure began checking the class snapshot.
4. Self-review added a digest-replacement regression. It failed when the moved producer read the module's `_digest` dynamically, then passed after capturing the original digest dependency.

## Verification commands and results

- `python -m unittest tests.test_formal_valuation_adapter_contract tests.test_formal_registry_manifest tests.test_formal_scoring_registry tests.test_formal_policy_registry tests.test_formal_policy_registry_guards -q`: **109 tests, OK** (after the class guard change).
- `python -m unittest tests.test_formal_metric_engine -q`: **19 tests, OK** (before the final captured-digest correction).
- `python -m unittest tests.test_formal_metric_engine.MetricClosureTests.test_definition_hash_is_stable_and_engine_captures_shared_producer -v`: **1 test, OK** after the captured-digest correction; pinned pre-refactor hash `96d0cb000910df365d981f826f125c2668bdbb55ca31d864f7a957cdafb4e774` remains unchanged.
- `git diff --check`: no whitespace errors; Git printed only line-ending conversion notices.
- A broader `unittest discover -s tests -q` run was started and then stopped at the task owner's request. It produced no result and is not counted as passing.

## Self-review and concerns

- Confirmed no adapter child field contains `original_definition_hash`; it is derived from the same root and shared metric definition producer.
- Confirmed affected metrics have exactly one adapter, unaffected metrics have none, and child operation, units, profit semantic, cyclic rule, decimal contract, preconditions and declared definition basis are checked against signed scoring and policy data.
- Confirmed manifest v1 cannot load Stage C, v2 scoring fixture wrapper remains on its existing nine-role path, and no runtime arithmetic or ranking was added.
- No known functional concerns in the original C2 scope. Broad full-suite discovery was intentionally stopped; the requested regressions and metric engine suite passed as listed above.

## Independent-review C2 repair — `4f7a612`

Three Important trust-boundary findings in the original candidate `6911834` were repaired in a separate commit:

1. The loader now captures the exact `ValuationAdapterDefinition` constructor and serialization functions. It compares every constructed definition with the already validated signed fields and derived root-bound hash. The canonical payload and later seal fingerprints come from those validated values, rather than trusting a constructor's or serializer's output.
2. The shared metric producer captures the original `FormalScoringRegistry.template_for` method. The adapter loader checks that the class method still has that identity before accepting the scoring graph and on subsequent proof checks.
3. Public registry attribute lookup checks the closure's class snapshot before returning `require_official` or any other method. A guarded metaclass prevents ordinary replacement of `__getattribute__` or inheritance. Thus replacing `require_official` with a no-op cannot make a proof appear official through its public method call.

### Repair RED/GREEN evidence

- Five targeted tests for direct `require_official` replacement, substituted definition constructor, modified dataclass initializer, substituted serializer, and substituted scoring template reader ran against `6911834`: **4 failures and 1 error**, each reproducing a reviewed bypass. After the repair: **5 tests, OK**.
- A sixth targeted test for replacing the new protected attribute lookup failed before the guarded metaclass, then passed after it was added: **1 test, OK**.
- Final C2 compatibility command: `python -m unittest tests.test_formal_valuation_adapter_contract tests.test_formal_registry_manifest tests.test_formal_scoring_registry tests.test_formal_policy_registry tests.test_formal_policy_registry_guards -q` — **114 tests, OK**.
- Final metric engine command: `python -m unittest tests.test_formal_metric_engine -q` — **19 tests, OK**.
- Final `git diff --check` — **exit 0**, line-ending notices only.

### Repair self-review and residual risk

- Verified the producer's payload and hash algorithm did not change, and the 19 metric-engine regressions remain green.
- Verified constructed adapter values are checked against signed fields before publication, and definition mutation is checked against fingerprints based on the validated fields.
- Verified a direct no-op replacement of `require_official` fails on attribute lookup, while swapping the scoring template method fails before it can affect a definition hash.
- No remaining in-scope failing tests or known C2 defects. The previously stopped broad repository discovery was not repeated; the named compatibility and metric-engine suites are the final test evidence. As with the existing Python proof classes, arbitrary code that bypasses normal metaclass assignment using `type.__setattr__` to replace `__getattribute__` itself remains outside this public-entry guard; future consumers should retain an original authentication entry.

## Second independent-review repair — `fddab7c`

The review found that the shared metric producer captured `_digest`, while `_digest` still looked up the module's `_canonical` encoder dynamically. A temporary encoder replacement could therefore publish a wrong `original_definition_hash`; restoring the module binding left the adapter proof apparently official.

- `_digest` now captures the canonical encoder and SHA-256 function in its defaults, preserving the original payload and hash algorithm while removing that dynamic module lookup.
- The public adapter loader and the registry's subsequent official checks verify that the metric module still binds the original canonical encoder. A swapped encoder is rejected before publication; an already loaded registry rejects the swap while it is active.

### RED/GREEN and regressions

- The two public adapter regressions failed on `4f7a612`: one published a poisoned definition hash and still authenticated after the replacement was restored; the other accepted an active encoder swap on an existing registry. Both passed after the fix. The first now rejects at load, so no poisoned proof is published to authenticate later.
- The metric-engine regression failed while a temporary `_canonical` replacement reached `_digest`; it passed after the digest captured its original encoder. The pinned pre-refactor definition hash remains `96d0cb000910df365d981f826f125c2668bdbb55ca31d864f7a957cdafb4e774`.
- Final compatibility command: `python -m unittest tests.test_formal_valuation_adapter_contract tests.test_formal_registry_manifest tests.test_formal_scoring_registry tests.test_formal_policy_registry tests.test_formal_policy_registry_guards -q` — **116 tests, OK**.
- Final metric-engine command: `python -m unittest tests.test_formal_metric_engine -q` — **19 tests, OK**.
- `git diff --check` — **exit 0**, line-ending notices only.

### Self-review and residual risk

- Confirmed the loader checks encoder identity both before definition production and again before publishing the registry; later proof checks repeat the identity check. The producer's digest uses its captured encoder even during a temporary module-name replacement.
- No C3 runtime behavior was added. The existing Python reflection limitation described above remains; no new in-scope C2 test failures are known. Full repository discovery was not rerun, per the task owner's earlier direction.

## Complete dependency-chain repair — `a83668c`

The next review reproduced three further temporary substitutions that contaminated a loaded definition hash and still allowed official authentication after restoration: `formal_metric_engine._plain` changed a direction, `formal_metric_engine.fields` omitted the direction field, and `formal_metric_engine.json` emitted an arbitrary string. They showed that capturing `_digest` and `_canonical` names alone did not close the producer's transitive dependencies.

The shared definition producer now lives in one closure with its conversion, canonical encoding, digest, and definition construction functions. It captures the field reader; mapping, decimal, sequence and dictionary types; the recursive conversion function; JSON `dumps`; SHA-256; and `FormalScoringRegistry.template_for`. The recursive converter calls its closure-local function, never the module `_plain` binding. A single dependency snapshot checks the producer's module bindings and the owning JSON, hash, and scoring method bindings. The adapter loader captures that snapshot checker and invokes it before loading and during every proof check.

### RED/GREEN and regressions

- Two new public-boundary tests, with three substitutions each, ran RED on `fddab7c`: **six failing subcases**. In each load case, restoring the substituted binding left the contaminated registry officially accepted; in each active-proof case, the existing registry accepted the substituted dependency. After the closure and snapshot repair: **2 tests, all six subcases OK**.
- Final C2 command: `python -m unittest tests.test_formal_valuation_adapter_contract tests.test_formal_registry_manifest tests.test_formal_scoring_registry tests.test_formal_policy_registry tests.test_formal_policy_registry_guards -q` — **118 tests, OK**.
- Final metric-engine command: `python -m unittest tests.test_formal_metric_engine -q` — **19 tests, OK**; the pinned pre-refactor definition hash remains unchanged.
- `git diff --check` — **exit 0**, line-ending notices only.

### Final self-review and residual risk

- Checked the producer's call path for dynamic module lookups: field enumeration, value conversion, recursive conversion, JSON serialization, SHA-256, and template selection all use captured closure values. The adapter verifies their module bindings before publishing and on later authentication.
- A temporary replacement now fails at the public loader. If a dependency is replaced after publication, `require_official` fails while it remains replaced. The producer itself cannot read the substituted module names, so a restoration cannot leave behind a poisoned hash produced during that interval.
- No C3 behavior, push, or merge was performed. The Python reflection limitation already recorded above remains the residual risk; no other dynamic global dependency was found in this metric-definition chain. Full repository discovery was not rerun because the task owner directed verification to the complete C2 and metric suites.

## JSON encoder primitive boundary — `aaa06e9`

The latest review found a normal binding below the captured `json.dumps` function: `json.dumps` looks up `json.JSONEncoder` when invoked with the producer's explicit canonical options. Replacing that class temporarily contaminated a definition hash; after restoration, the originally published adapter still authenticated.

The central dependency snapshot now includes the `json.JSONEncoder` and `json.encoder.JSONEncoder` bindings, the complete encoder class member set and inheritance, `__init__`, `encode`, `iterencode`, and `default`, the selected string encoder, both `c_make_encoder` and `_make_iterencode` branches, and their relevant encoder-module primitives. It also checks the mutable `ESCAPE_DCT` contents. The producer's canonical call and hash algorithm were left unchanged, preserving existing bytes and definition hashes.

### RED/GREEN and final verification

- Three new public-boundary tests failed RED on `a83668c`: the loader accepted a replaced `JSONEncoder`, an existing registry allowed reads during the replacement, and a registry published during replacement remained official after restoration. All three passed GREEN by rejecting at load or proof read.
- A fourth test produced **six failing subcases** for replaced encoder methods, string encoding, and C/Python iteration bindings; all passed after the primitive snapshot.
- Self-review found a further ordinary class lookup route. Injecting `JSONEncoder.__getattribute__` failed a fifth RED test, then passed after the snapshot covered the entire class member set.
- Final C2 command: `python -m unittest tests.test_formal_valuation_adapter_contract tests.test_formal_registry_manifest tests.test_formal_scoring_registry tests.test_formal_policy_registry tests.test_formal_policy_registry_guards -q` — **123 tests, OK**.
- Final metric-engine command: `python -m unittest tests.test_formal_metric_engine -q` — **19 tests, OK**, including the pinned pre-refactor definition hash.
- `git diff --check` — **exit 0**, line-ending notices only.

### Encoding-path audit and residual risk

- Audited the selected `json.dumps` path: the explicit nondefault canonical options bypass `_default_encoder`; `JSONEncoder.encode` calls `iterencode`; `iterencode` selects the captured string encoder and either C or Python iteration. Ordinary module bindings on those paths and the complete encoder class member set are now checked before adapter publication and on proof reads. The Python fallback string encoder's `ESCAPE` binding and `ESCAPE_DCT` contents are covered.
- No canonical payload or digest rule changed. No C3 runtime behavior, push, or merge was added. The general Python reflection limitation noted above remains; no ordinary binding left unchecked was found on the audited encoder path.
