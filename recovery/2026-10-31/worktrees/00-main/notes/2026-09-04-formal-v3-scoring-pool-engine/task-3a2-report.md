# Task 3A2 implementation report

Status: implementation frozen for parent independent review and final-source full-suite verification. This is not completion of Task 3 or the overall plan.

Base: `37ab15c6d47213646f88693b975cb5f81eb1fa0e`.
Worktree: `D:/Projects/AShareQiheng/.worktrees/formal-v3-implementation`.
Authority: `task-3a2-brief.md`, including the smaller same-generation composition selected by main. TDD and verification skills were read and used. No nested agents, network, production data edits, schema/persistence changes, Git/index writes, commits, main changes or pushes were performed.

## Final files and SHA-256

All six code/test files are frozen at these hashes (lowercase hexadecimal):

| File | SHA-256 |
| --- | --- |
| `ashare_pipeline/formal_score_inputs.py` | `bcff57506e2f6ce133a2e4fd564d447967cdb0906a076dc287008e66bf8964b1` |
| `ashare_pipeline/formal_metric_context.py` | `d408fe49e959d0aa1767ef968aa13117f5ae61a4b90dcb1a9395400cd45fe513` |
| `tests/formal_score_input_fixtures.py` | `57b11c3a1e9052abde55f99a7f02809f5dafeeb15a34575fc906cc2da809dd5c` |
| `tests/test_formal_score_inputs.py` | `4905d49c3ed250000527a5ca7062f58b8ac8ccbec31509874922e1b6b0c39bb0` |
| `tests/formal_metric_feature_fixtures.py` | `5ae7cffc55469875c09e8bd4c6f6b74f2c7f543db9007a3f7c478db33f6241c7` |
| `tests/formal_metric_fixtures.py` | `47cb0c1122eeb73099d9175c0582f7cb7a8ac480b327b3d4c4eb1b7ca1169fe3` |

The only existing production-file change exports the existing Context closure's `dependencies` function as `_require_authentic_metric_context_repository`. It remains absent from `__all__`; its original transitive validator, source/snapshot/path/verifier checks are unchanged. No new mint authority was exported.

The existing fixture helpers gain optional mutation/calendar-resolver parameters and real financial period/nature parameters, preserving existing defaults. The pre-existing untracked `tmpj4zv9_fq/` was visible before work and was not modified or removed. Test-created temporary resources use the existing worktree-owned temporary-directory helper and its test-owned cleanup.

## Public API and immutable audit payload

```python
FormalScoreInputRepository(feature_repository, context_repository, *, registry_signature_verifier)
repository.build_batch(frozen_input_hash, *, scoring_registry)
# -> FormalScoreInputBatch, or None only for genuine missing frozen universe

batch.security_ids       # complete canonical SH/SZ/BJ tuple
batch.inputs             # ready-only tuple, same security order
batch.pending_reasons    # immutable SID -> nonempty sorted reason tuple
batch.input_for(security_id)  # ready input or None; invalid/spoofed selectors raise

proof.require_verified()
proof.canonical_bytes()
proof.to_dict()          # detached JSON-native tree
```

There are no caller subset, metric subset, raw score, feature bundle, Context, confidence, years, cyclic classification, industry, no-coverage, waiver or override arguments. Repository/proof constructors require exact registered identities, reject reinitialization/copying, and keep state in private weak-reference records.

New versions are `formal-score-input-batch-v1` and `formal-score-input-v1`. Batch payloads bind the full internal metric batch and its hash, complete population/universe/frozen input, exact registry root/role hashes/root manifest, ready input manifests, pending reasons and selected actual consensus facts/absence. Ready inputs bind security/template/current industry, exact full V6 bundle and hash, genuine current feature marker (including provider batch/fact/issue identities), history endpoints/observed quarters/continuous FY count/cyclic classification, every qualified slot definition/weight and precise evidence, plus consensus rule/fact/cap metadata when applicable.

`input.slots` is an immutable mapping keyed by all 25 qualified metric identities, preserving both `M.return_persistence` and `CA.return_persistence`. Each slot carries its signed definition, dimension/internal weights, value, temporal quality, exact contributing financial evidence refs, full feature values, metric-score audit data or separate actual Context/rule. Attribute values/weights/quality/cap use exact Decimal values; canonical serialization uses exact Decimal strings with no display quantization. Normal values are the genuine percentile; neutral values are `Decimal('50')`, with `metric_score=None` and a distinct `registered_consensus_no_coverage` evidence kind. The input carries `confidence_cap=Decimal('0.90')` only for that branch.

Hashes are acyclic: ready manifests receive input hashes before the batch manifest is hashed; the outer batch hash is subsequently attached to ready proofs, without hashing a manifest into itself. No dimension/confidence/grade/card/policy/pool arithmetic or persistence is implemented.

## Provenance/readiness implementation

- One owned metric repository and a genuine metric Context repository are created privately from the supplied exact same-store feature/Context repositories and verifier. The existing Context checker is constructed first so an uninitialized Context object fails through its established validation boundary.
- The outer owned-provider generation/database guard begins before the internally built all-metric/all-universe batch. The metric batch performs its existing provider/current fact/issue/source/root/universe/industry/rebuild closure checks.
- Classified present full bundles are read through the captured original `_read_authenticated_bundle(require_complete=False, input_hash=marker.input_hash)`. The marker comes only from that genuine internal batch. Full bundle hash, input/root/feature/security/template/cutoff identity must match; disappearance/mismatch raises.
- Full signed slots are inspected independently of the selected metric projection. Every non-exempt required slot must derive; optional slots retain derived/missing restrictions. Normal readiness also requires no full blockers. Neutral readiness requires the genuine empty issue hash, acceptable full statuses, at least one derived non-exempt required slot, and the same history gates. No arbitrary blocker-string filtering is used.
- Existing `require_formal_history` receives actual history endpoints and the last eight observed quarter keys at the fixed cutoff. Cyclic classification comes from actual current secondary industry and the signed cyclic set; the five-FY gate applies. Continuous count walks backward from FY2025 and caps at five.
- Every normal metric gets the existing genuine peer context and percentile. Company-level pending/history/neutral status never filters the metric cohort. `N<20` produces pending; nothing supplies an invented metric score.
- Actual consensus reads group sorted IDs by the registered scope, verify exact linked descriptor and root/security/cutoff/kind/scope identities, and preserve absence. Only verified explicit no-valid-coverage with empty estimates supplies the separate neutral branch. Missing actual Context never falls back to a derived expectation feature. Actual timestamp/calendar-bound date-only Context determines neutral temporal quality; normal temporal quality is the minimum precision of exact contributing financial refs.
- Full bytes and selected consensus/absence closure are reread after assembly. Canonical serialization/ranking/freezing happen outside the writer fence. Captured dependency checks run before/after reads and at publication. Filesystem guarantees remain bounded authenticated immutable reads, not an OS-wide atomic snapshot.
- All outer batches/children share one private revocable publication capability. Any finalization, rollback, context-exit or final dependency failure revokes all outer proofs, including tentatively leaked children. The inner metric proof's independent historical validity is deliberately preserved. Detached successful children have no strong owner/cache cycle.
- Dependency capture resolves methods through the MRO for each concrete consumed proof type, preventing both base replacement and newly added subclass shadows. It covers metric/universe/industry/feature-marker proof methods and genuine calculation helpers, in addition to reusing the existing transitive repository checks.

Final diagnostic correction: an unclassified member now reports `invalid_template`/`invalid_industry` without falsely claiming `current_receipt_absent`; the latter is emitted only for a classified member with genuine absent current receipt.

## Real fixtures and test efficiency

All official proof paths use genuine byte-sensitive HMAC-signed registry graphs, leased producer tasks, persisted raw snapshots, financial facts, feature bundles, frozen universe and actual Context normalization receipts. No fake proof minting or always-true verifier is used. Pure readiness/consensus/quality helpers never mint and are not public factory override paths.

The initial fixture supplied 25 duration FY values plus their cumulative prerequisites for the focal company; initial fixture/first-implementation runs were slow but passed. After main's explicit test-efficiency guidance, the final fixture retains all 25 independent signed slots/metric definitions while 24 toy formulas share the explicit `score_leaf` synthetic FY balance fact, expectation has a separate fact, and a separate genuine duration series supplies history with all required cumulative predecessors. This is declared test-only synthetic semantics, not a production feature-algorithm change. One response supplies the two FY peer facts. Only the focal company has mature history. The full population stays at 22 SH/SZ/BJ members; small negative/race cases use the existing genuine three-member frozen population.

The date-only neutral fixture additionally persists a real trading-calendar producer receipt and uses the signed calendar selector/resolver/binding through actual Context normalization and reads. Its smoke check returned a real non-null calendar binding and signed cyclic membership `['fixture-cyclic', 'machinery']`.

## Actual RED/GREEN evidence and exact verification boundaries

All commands ran in the worktree above, using `D:/Projects/AShareQiheng/.venv/Scripts/python.exe`. Tool-return delay was not treated as a reason to duplicate an active run. Every named session below has been collected and closed.

1. Initial real behavior RED:

   `D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_score_inputs -v`

   Session `58811`: **2 tests, 115.047 s, exit 1, FAILED (failures=2)**. Both failed at `assertIsNotNone(find_spec(...))` with `complete score input repository must own all provenance`, after successful genuine fixture construction. Earlier fixture setup errors (instant statement spelling/type) were corrected and were not counted as RED.

2. First implementation integration GREEN, before helper extraction/final dependency refinements:

   Same command, session `49654`: **2 tests, 567.152 s, exit 0, OK**. Normal complete all-25 input and registered missing-expectation neutral paths passed. This is explicitly **pre-final** source evidence.

3. Small helper RED then GREEN:

   `D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_score_inputs.ScoreInputGateTests.test_consensus_absence_requires_context_and_unlinked_cannot_neutralize tests.test_formal_score_inputs.ScoreInputGateTests.test_temporal_quality_is_minimum_actual_ref_precision -v`

   **2 tests, 0.004 s, exit 1, FAILED (failures=2)** for missing required helper capabilities. After private helper implementation/wiring, `... -m unittest tests.test_formal_score_inputs.ScoreInputGateTests -v` passed **4 tests, 1.079 s, exit 0, OK**.

4. Earlier expanded small suite, session `69821`, same gate-class command: **6 tests, 117.955 s, exit 0, OK**. Includes genuine missing-to-present consensus race and outer context-exit revocation. This predates final fixture/dependency/diagnostic refinements.

5. Inherited concrete proof shadowing regression:

   `... -m unittest tests.test_formal_score_inputs.ScoreInputGateTests.test_concrete_proof_cannot_shadow_inherited_verification -v`

   RED **1 test, 1.263 s, exit 1** (`ValueError not raised`) when a new concrete `MetricInputBatch.require_verified` shadow was accepted. GREEN after MRO-resolution capture: **1 test, 0.388 s, exit 0**; expanded to inherited `require_verified`, `canonical_bytes`, `to_dict`, `__getattr__` shadows.

6. Transitive universe proof regression:

   `... -m unittest tests.test_formal_score_inputs.ScoreInputGateTests.test_transitive_universe_proof_verification_cannot_be_replaced -v`

   RED **1 test, 1.061 s, exit 1** (`ValueError not raised`). GREEN after capturing transitive universe/industry/feature-marker methods: **1 test, 0.443 s, exit 0**, including twelve class/method replacement permutations.

7. Optimized integration and expanded tests, session `55663`:

   `D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_score_inputs -v`

   **9 tests, 792.595 s, exit 0, OK**. All three full integrations passed: normal complete 25-slot input with pending eligible peers/detached proofs; missing expectation plus actual registered neutral coverage; derived expectation plus actual calendar-bound date-only no coverage, signed cyclic five-FY history, reentrant outer publication failure revoking children while the inner metric batch survives. The remaining six tests passed as printed. This run imported before the final inherited/transitive capture changes, constructor order change and last diagnostic correction; it is **pre-final source coverage**, not final-source full-suite verification. Profiling the real publication failure was particularly expensive; observed worker CPU rose during the run, rather than indicating a blocked SQLite operation.

8. Three new real negative checks:

   `... -m unittest tests.test_formal_score_inputs.ScoreInputGateTests.test_absence_and_same_store_dependency_boundary tests.test_formal_score_inputs.ScoreInputGateTests.test_actual_source_sql_and_signed_root_tamper_fail_closed tests.test_formal_score_inputs.ScoreInputGateTests.test_actual_linked_absence_and_small_cohort_stay_pending -v`

   Session `62874`: **3 tests, 44.665 s**, the latter two passed; the first exposed an `AttributeError` from the existing metric constructor when Context was uninitialized. Constructing the genuine metric Context checker first resolved the error shape without catching/classifying corruption. Focused rerun: **1 test, 0.468 s, exit 0, OK**.

9. Broad small-suite coverage before the last diagnostic correction:

   `D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_score_inputs.ScoreInputGateTests -v`

   Session `88198`: **11 tests, 109.556 s, exit 0, OK**. This includes actual source-file/SQL/signed-root tamper, actual linked missing Context despite derived expectation, real N<20 after actual neutral coverage, exact initialization/subset boundaries, inherited/transitive substitutions, absence race and context-exit revocation. The production implementation at that point differs from final only by the last truthful-absence diagnostic condition described next; therefore this is also labeled **pre-final correction coverage**.

10. Last self-review correction, final-source focused RED/GREEN:

    `D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_score_inputs.ScoreInputGateTests.test_dependencies_reject_substitution_even_with_no_classified_members -v`

    RED **1 test, 1.090 s, exit 1**: `'current_receipt_absent' unexpectedly found in ('current_receipt_absent', 'invalid_industry', 'invalid_template')`.
    Final-source GREEN **1 test, 1.391 s, exit 0, OK** after restricting absence diagnostics to classified members. No code/test edits occurred after this final GREEN and the hashes above were recomputed.

`git diff --check` completed without whitespace errors. Its only output was the repository's standard LF/CRLF advisory for existing tracked files. Current test file contains 14 tests. Per main's explicit coordination instruction, no duplicate final full-suite run was launched: parent will run the complete final-source suite once after this frozen report, with independent code review before any commit. Historical intermediate source hashes were not snapshotted; they are not represented as the final hashes above.

## Self-review and remaining verification limits

Self-reviewed the actual new implementation and allowed existing-file diffs for public scope, typed provenance, full-slot rather than projection readiness, fixed cutoff/history/cyclic behavior, unchanged metric eligibility/cohorts, linked consensus provenance/absence, exact decimals, acyclic hashes, weak ownership, preparation outside writer fences and revocation across exception/exit paths. The two dependency regressions and final misleading-absence diagnostic were found during this review, reproduced before fixing, and are now covered.

Remaining limits are verification scope, not a claim of completed final review:

- Parent still must run the entire 14-test file against the exact final six hashes and perform independent review/regression selection. The pre-final full integrations and final focused GREEN are deliberately distinguished above.
- Required extra-slot/optional-blocked/other-missing/cyclic-four-year/quarter-gap/empty-issue permutations are focused pure diagnostic checks, combined with genuine full-input integration and the existing unchanged V6/metric provenance tests. This new file does not rebuild a full 22-member fixture for every corruption/global-conflict permutation.
- Actual date-only provenance is exercised through the registered consensus path; mixed normal financial-ref precision is exercised at the pure minimum-quality boundary. The new normal ready integration uses the unlinked feature path; covered/absent/malformed consensus branch decisions additionally have focused tests, and actual linked missing Context/N<20 use real stores.
- The accepted filesystem contract remains bounded authenticated immutable reads. No OS-wide filesystem lock or new provenance subsystem is introduced.
- A future Task 3B must consume the genuine sealed complete input and preserve the outer proof/publication semantics when creating descendants; this task intentionally provides no scorecard or raw-object mint path.

No known arithmetic/policy/pool implementation has slipped into scope. No runtime/test sessions remain active after collection of the evidence above. All six files are frozen for handoff.
