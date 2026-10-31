# Task 2A implementation report

Status: DONE_WITH_CONCERNS. Review round 1 sole Important finding fixed; implementation frozen again. Original 21-case focused run and the 2 new review regressions are GREEN. Conservative extraction-issue scoping and V6 float limitations are documented below. Parent owns independent re-review, combined regression, staging and commit.

## Delivered files

- `ashare_pipeline/formal_feature_repository.py`: narrow shared authenticated receipt reader, unchanged strict public reads, sealed current metric projection endpoint.
- `ashare_pipeline/formal_metric_features.py`: pure selected signed-AST dependency evaluation; no mint authority or storage operations.
- `tests/test_formal_metric_features.py`: real temporary SQLite StateStore, raw source lineage, signed complete registry graph, persisted feature receipts and race/adversarial regressions.

No changes to StateStore, V6 bundle builder/evaluator/contract/schema, context, scoring/industry/universe, pool, runner, or legacy tests. No network, nested agents, staging or commits. Existing `tmpj4zv9_fq/` is untouched.

## API and wire contract

`FormalFeatureRepository.select_current_verified_metric_features(security_id, as_of_utc, *, template_id, registry_manifest_hash, required_feature_keys: tuple[str, ...]) -> VerifiedMetricFeatureProjection | None`

- Requires canonical SH/SZ/BJ identity, one of the five supported templates, exact frozen cutoff `2026-08-31T07:00:00+00:00`, and a nonempty strictly sorted unique tuple resolving to applicable required signed V6 slot IDs.
- Uses the explicitly injected complete provider once. Its identity/batch/completeness, finite fact tuple and finite issue tuple are authenticated and detached. Complete captured facts must equal actual reverified StateStore facts; provider snapshot and persisted facts are rechecked across construction/read/evaluation.
- Rebuilds the unchanged full V6 bundle using all captured inputs, reads its already-persisted exact input hash through full SQL/file/receipt/registry/slot/unit/formula/evidence checks, and requires exact canonical bundle equality. Missing exact current receipt returns `None`; this endpoint never writes or synthesizes a persisted bundle.
- Storage authenticity and full-score completeness are factored in `_read_authenticated_bundle`. Historical and legacy current public reads still pass `require_complete=True`, preserving their existing blocker/required-slot gates.
- Successful projection reads reauthenticate the exact receipt after selected evaluation and then recheck complete current facts and provider snapshot.

`VerifiedMetricFeatureProjection` is not publicly constructible and has no `from_dict` or module-visible mint helper. A closure-private weak reference registry seals exact instances. Forged exact repository instances are not registered; copied proofs and nested or scalar mutation cannot authorize use. Captured store/repository methods, V6/pure-evaluation callable bindings, repository dependencies, embedded store/verifier/provider method identities and storage roots are checked before/after the operation.

Public fields (frozen exact tuples for collections):

`security_id`, `as_of_utc`, `template_id`, `registry_manifest_hash`, `feature_registry_hash`, `input_hash`, `bundle_hash`, `required_feature_keys`, `slots`, `values`, `blockers`, `fact_snapshot_hash`, `issue_snapshot_hash`, `batch_id`, `algorithm_version`, `projection_hash`.

- `slots`: detached signed `FormalFeatureSlot` definitions, in requested key order.
- `values`: corresponding sealed `FormalFeatureValue` instances, each independently `derived`, `missing` or `blocked`, with evidence and missing reason.
- `blockers`: sorted aggregate of local reasons. **An aggregate blocker does not invalidate every value.** Later MetricFactory must recheck the projection seal and inspect only each metric's required slot statuses/evidence. A missing sibling slot does not contaminate a derived slot.
- `fact_snapshot_hash` and `issue_snapshot_hash`: SHA-256 of canonical arrays containing the complete sorted captured fact/issue records, including duplicates in the captured tuple.
- `algorithm_version`: `formal-metric-feature-projection-v1`.
- `projection_hash`: SHA-256 of canonical projection payload excluding the hash field itself. It includes exact stored full bundle input/bundle hashes and provider batch audit label.
- `to_dict()` returns a deeply detached canonical JSON projection; `canonical_bytes()` returns canonical bytes; `require_verified()` rechecks the entire closure seal. Consumers should call the seal check before using attributes.

## Selected formula behavior and limitations

The helper evaluates the original signed V6 AST using public `select_visible_formal_facts`, `derive_comparable_quarters` and `evaluate_formula` APIs. Annual leaves include precisely the requested FY. Quarter leaves include precisely their endpoint and required duration predecessor. The Q4-with-Q3-only regression proves that an unrelated missing H1 required for Q3's own derivation does not exclude a proved Q4. Meaningful mapping/tie/accounting conflicts and ambiguous namespaces remain explicit local blockers.

Missing unrelated signed slots and unrelated global annual/quarter maturity shortage do not exclude an independently evidenced selected slot. Required facts absent, denominator zero, unit mismatch and unresolved extraction issues yield explicit missing/blocked values without numbers or partial evidence. Valid zero and negative calculated values remain intact. Facts first visible after the frozen cutoff cannot fill an earlier missing value.

Conservative approved limitation: `FormalFactIssue` has no universally trustworthy period/source scope, and no existing signed mapping proof in this slice establishes safe exclusion. Consequently all unresolved provider extraction issues block every selected slot, regardless of arbitrary `details` claiming unrelated periods or metrics. Missing another signed feature is not an extraction issue.

The arithmetic is exactly V6 float arithmetic. This work does not recover original arbitrary decimal precision; the later Decimal engine must convert the canonical spelling of verified V6 values. This capability authenticates selected signed feature evidence, not frozen universe membership, industry eligibility, peer cohort eligibility, percentile scores or pool admission.

## TDD and verification evidence

Working directory: `D:/Projects/AShareQiheng/.worktrees/formal-v3-implementation`.
Python: `D:/Projects/AShareQiheng/.venv/Scripts/python.exe`.
Read and applied `superpowers/test-driven-development/SKILL.md` and its complete `writing-good-tests.md` reference.

1. Initial RED: `python -m unittest tests.test_formal_metric_features.MetricProjectionTests.test_valid_projection_is_deterministic_and_binds_receipt -v` -> `FAILED (failures=1)`, 1 test / 0.448s. Correct assertion: `metric projection endpoint is missing`.
2. Core GREEN: `python -m unittest tests.test_formal_metric_features -v` -> `OK`, 12 tests / 29.410s.
3. Dependency RED: `python -m unittest tests.test_formal_metric_features.MetricProjectionTests.test_replaced_evaluation_dependency_cannot_supply_numeric_override -v` -> `FAILED (failures=1)`, 1 test / 0.623s. A forged numeric evaluator was initially accepted (`ValueError not raised`); original calculation bindings are now checked.
4. Extended GREEN: `python -m unittest tests.test_formal_metric_features -v` -> `OK`, 18 tests / 65.231s, including actual execution races during provider return, full bundle construction, receipt read and selected derivation. Race scheduling uses profiling callbacks, retaining real production execution and real source/SQLite writes rather than replacing proof functions.
5. Embedded dependency RED: `python -m unittest tests.test_formal_metric_features.MetricProjectionTests.test_store_trust_dependencies_cannot_be_replaced_after_repository_creation -v` -> `FAILED (failures=1)`, 1 test / 0.766s (`ValueError not raised`). Embedded StateStore verifier/storage dependencies are now captured and rechecked.
6. Final GREEN: `python -m unittest tests.test_formal_metric_features -v` -> `OK`, **21 tests / 78.316s**, exit 0.
7. `git diff --check` -> exit 0; only the repository's LF-to-CRLF informational warning. Parent will run affected legacy regression after file freeze; no long full repository regression was started by this agent.

The 21 focused tests cover receipt binding/determinism, missing sibling feature, metric-local annual/quarter history, missing facts/predecessors, zero denominator, unit mismatch, negative/zero values, tie/mapping/annual namespace/quarter accounting conflicts, explicit provider issues, constructor/copy/low-level mutation, missing current receipt, mixed identity/key boundaries, complete-provider tuple/identity boundaries, SQL/bundle/raw-source corruption, after-freeze facts, correction races, late provider/source/receipt mutation, and changed evaluator/embedded store dependencies.

## Handoff

Code/test files are frozen. Please review independently and run the existing FormalFeatureRepository suite; the parent-owned baseline was 30 tests / 84.082s OK. Subsequent integration should consume `values` by slot, with a seal check, and must not treat the projection's aggregate `blockers` as a blanket rejection of every sibling slot.

## Review round 1 — embedded source-store validation dependency

The independent reviewer found one Important issue. The existing dependency guard covered StateStore, feature bundle store and repository methods but omitted the embedded `FormalSnapshotStore`. The actual StateStore path calls `read_verified_raw` followed by `validate_stored_snapshot`; replaying cached authentic returns from both instance methods could hide subsequently corrupted physical source bytes and still mint a sealed value of 100.0. Parent confirmed the call path and reported no other Critical/Important/Minor finding.

Read and applied the complete `receiving-code-review/SKILL.md`, inspected the actual StateStore/source-store validation path, then reproduced the issue with the real fixture before changing production code.

Fix is confined to the existing metric projection guard in `formal_feature_repository.py`: capture trusted `FormalSnapshotStore` class methods, retain staticmethod/classmethod descriptors in the descriptor identity check (a callable-only scan misses classmethod descriptors), reject embedded source instance overrides, and require the exact trusted source-store type for this new endpoint. The existing before/after dependency checks now cover both physical raw reads and their validation path. No change to legacy strict endpoint execution or pure metric evaluation.

Added two focused tests in `test_formal_metric_features.py`: one caches authentic real raw/validated results, corrupts the actual raw file, overrides both source instance readers and requires rejection; the other verifies class reader and classmethod validator replacement rejection. The fixture still exercises real SQLite facts, signed graph, stored receipts and source files.

- Round 1 RED command: `python -m unittest tests.test_formal_metric_features.MetricProjectionTests.test_cached_source_readers_cannot_hide_actual_raw_file_tamper tests.test_formal_metric_features.MetricProjectionTests.test_source_reader_class_and_classmethod_replacement_rejects -v` -> `FAILED (failures=3)`, **2 tests / 1.544s**. All three failure sites reported `ValueError not raised`, including the successful sealed result after real raw tamper.
- Same round 1 command after fix -> **OK, 2 tests / 0.820s**, exit 0.
- `python -m py_compile ashare_pipeline/formal_feature_repository.py tests/test_formal_metric_features.py` and `git diff --check` -> exit 0 (normal LF/CRLF informational warnings only).
- Prior to this round, parent independently verified **85 legacy/foundation + 21 new = 106 passing tests**, compilation and diff checks. The new combined projection suite has **23 tests**; parent will run its changed-suite regression and scoped independent re-review after this freeze.

No further findings explored or unrelated code changes made. The source validation bypass is the sole round 1 fix.
