# Task 2B implementation report

Status: DONE_WITH_CONCERNS — implementation and focused verification complete; files frozen for parent regression run and independent review. No Git writes, network access, persistent data changes, metric arithmetic, pool selection, scoring or collection work performed. Existing unrelated `tmpj4zv9_fq/` preserved.

## Files

- `ashare_pipeline/formal_metric_context.py`: new signed industry contract, authenticated repository, closure-owned universe and industry batch proofs.
- `ashare_pipeline/state_store.py`: one new verified frozen-universe getter, no DDL or legacy getter edits.
- `ashare_pipeline/formal_context_repository.py`: one batch getter and constructor-owned Context identity registration consumed only by the new metric boundary. Existing single getter/calendar selection methods unchanged.
- `tests/formal_metric_fixtures.py`: plain helper, one real temporary StateStore/raw store, full nine-role signed graph, genuine producers/receipts/normalization. Imports the existing test module only to invoke its unbound universe helper; does not import or subclass a TestCase into the new test module.
- `tests/test_formal_metric_context.py`: 16 focused integration tests.
- `tests/test_formal_context_repository.py`: five focused batch tests.
- `tests/test_state_store.py`: optional helper parameters only: registry_manifest_hash, source_registry_hash, registry_signature_verifier, formal_snapshot_store, exchange_rows. All existing defaults preserved. Supplied exchange_rows feeds the exact same real JSON raw data and source document per exchange.

## APIs and wire contract

`StateStore.get_verified_formal_frozen_universe(frozen_input_hash)` returns `FormalFrozenUniverseInput | None` through the existing `_formal_universe_from_connection`, within the same read transaction as its exact header lookup. Complete source/raw/receipt/producer/member/status verification is reused. Its structural result is not an authentication token. Legacy `get_formal_universe_snapshot_by_input_hash` is untouched. Original `2026-08-31T15:00:00+08:00` bytes/hashes remain intact.

`FormalContextRepository.get_verified_many(kind, scope_key, security_ids, as_of_utc, registry_manifest_hash)` accepts a nonempty exact sorted unique tuple of canonical SH/SZ/BJ IDs, rejects invalid kinds and trading_calendar without an exchange selector, and returns a detached `MappingProxyType` containing every requested ID. Values are exact freshly reconstructed `FormalContextFact` or actual `None` absence. The implementation takes one verified full-scope candidate snapshot before selection and one after selection, groups requested securities once, and preserves source/timestamp/version/tie validation. Corruption and candidate changes raise instead of becoming absence. Existing single-selection code is unchanged.

`FormalMetricContextRepository(state_store, context_repository, *, registry_signature_verifier)` requires exact dependencies, same StateStore/verifier, an authentic constructor-registered Context repository and the real embedded snapshot repository/raw store. It captures concrete identity/path/verifier state and validates consumed class methods/descriptors and instance overrides at entry/exit. The constructor registration lives in the Context module, so Context objects created before importing the metric module remain valid. Copies/uninitialized Context and metric repositories fail.

Public methods:

- `load_universe(frozen_input_hash, *, scoring_registry)` returns `VerifiedMetricUniverse | None`.
- `resolve_industries(universe_proof)` returns `VerifiedMetricIndustryBatch` for the whole frozen population.
- `recheck_batch(universe_proof, industry_batch)` returns `None` on an unchanged authenticated snapshot; any identity/graph/mapping/selected-fact/absence change raises. The later metric factory must call this after reading every member's features.

Industry child exact keys: `registry_role`, `schema_version`, `purpose`, `classification_system`, `source_version`, `effective_date`, `context_scope_key`, `memberships`, `mapping_sha256`. Fixed values are `industry`, `formal-industry-registry-v1`, `official`, `SW2021`. Parsing occurs only after exact bundle official eligibility and exact sealed same-root scoring registry eligibility. Effective date is canonical ISO and no later than 2026-08-31. Memberships are nonempty, exact-key, canonical-ID sorted/unique records with same-root template IDs and trimmed nonempty primary/secondary identifiers. Mapping digest is recomputed from compact sorted UTF-8 JSON of exactly classification_system/source_version/effective_date/memberships. Out-of-universe signed members never enter the peer population.

Proofs have no writable data slots or `__dict__`; immutable canonical bytes reside exclusively in private closure records, with weak identity references and repository ownership. Direct construction, copying, low-level field writes, forged objects and cross-repository reuse fail. `canonical_bytes()`, `to_dict()` (detached), `require_verified()` and read-only public fields are available. Nested public collections are recursively frozen mappings/tuples. There is no public mint helper.

Universe wire fields: schema_version (`formal-metric-universe-v1`), as_of_utc (canonical UTC freeze), frozen_as_of_utc (original CN bytes), registry_manifest_hash, frozen_input_hash, universe_hash, source_audit_hash, industry_registry_hash, mapping_sha256, industry (complete signed child), security_ids (complete sorted population), frozen_universe (complete existing payload), source_receipts (all three verified receipts), population_hash. `population_hash` is SHA256 of the canonical JSON array of complete sorted security IDs; root/frozen/source/mapping identities are separately present and jointly protected by the proof canonical bytes.

Batch wire fields: schema_version (`formal-metric-industry-batch-v1`), registry_manifest_hash, frozen_input_hash, universe_hash, universe_proof_sha256, population_hash, mapping_sha256, industry_registry_hash, entries, selected_context, batch_hash. `batch_hash` hashes the complete canonical payload before adding itself. `selected_context` includes the selected canonical scientific fact plus its ID, or an explicit null marker for every member, including members whose signed mapping is absent or mismatching.

Every entry binds security_id/root/universe_hash/frozen_input_hash. Assigned entries add status=`assigned`, pending_reason=null, template_id, primary_industry, secondary_industry, context_fact_id and context_canonical_sha256. Pending entries have status=`pending` and exactly one reason: `signed_membership_absent`, `context_absent`, or `context_membership_mismatch`; no guessed template/industry is added. Every authentic fact value field is compared: classification_system, primary_industry, secondary_industry, source_version, effective_date, mapping_sha256. Invalid facts, signatures, raw evidence, receipts, ties and races propagate.

## Actual TDD and verification record

Read full test-driven-development SKILL.md and writing-good-tests.md before editing.

1. Batch RED: first invocation encountered expected missing-method AttributeError; changed the test to an explicit availability assertion and reran. Actual RED: `AssertionError: False is not true : verified batch selection is required` (1 test / 0.071s). Added batch implementation; focused GREEN: 4 tests / 1.488s.
2. Universe/metric fixture debugging was not counted as behavioral RED: corrected the legacy getter name, authored one exchange-scoped source config for each exchange, and used Context-representable synthetic identifiers. No bypass or mock success proof was added.
3. Universe getter RED: explicit assertion failed because `get_verified_formal_frozen_universe` did not exist. Added its narrow implementation; getter GREEN verified original CN timestamp/frozen hash and unchanged legacy header, including true absence.
4. Metric prerequisite RED: real signed graph/universe/all three Context facts were successfully persisted, then explicit module-availability assertion failed. Pending and proof-boundary tests also produced actual module-missing assertion failures before implementation. Added sealed metric context module. Initial implementation tests exposed the existing universe extraction audit tuple representation; used existing `_plain_formal_universe_json` to detach that payload without changing old serialization/hashes. Focused GREEN: 3 tests / 6.234s, then 4 tests / 9.759s.
5. Additional concrete RED: `copy.copy(ContextRepository)` was accepted by the new constructor (`ValueError not raised`, 1 test / 0.409s). Added constructor-owned identity registration in the Context module and required it from the metric constructor/entry/exit guard. GREEN for that test plus metadata/digest/root/multi-member coverage: 5 tests / 13.315s.
6. Final focused command ran all 16 new metric tests plus the five new Context batch tests with verbose unittest output: **21 tests / 89.385s / OK**. Additional post-GREEN coverage tests are reported as coverage checks, not as separately observed RED cycles.
7. `git diff --check` passed; Git emitted only existing Windows LF-to-CRLF advisory warnings. No staging or commit performed.

Final command:

```text
D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_metric_context tests.test_formal_context_repository.ContextIntegrationTests.test_batch_selection_preserves_single_result_and_actual_absence tests.test_formal_context_repository.ContextIntegrationTests.test_batch_rejects_invalid_identity_instead_of_absence tests.test_formal_context_repository.ContextIntegrationTests.test_batch_corruption_does_not_become_absence tests.test_formal_context_repository.ContextIntegrationTests.test_batch_detects_correction_between_scope_snapshots tests.test_formal_context_repository.ContextIntegrationTests.test_batch_preserves_leading_tie_failure -v
```

Observed call-count evidence: using `sys.setprofile` to observe genuine function calls without replacing trusted dependencies, final recheck over three actual assignments made exactly **1 verified universe getter call, 1 get_verified_many call, 2 full-scope list calls**. Per-source validation and its registry verification still occur; this does not claim every source cost is eliminated.

Coverage includes valid SH/SZ/BJ with late captured verified prefreeze sources; multiple ordinary-A members in one exchange; canonical/digest/population bytes; preserved legacy header; missing exchange/member/status/receipt/raw; wrong scoring root/copy, signed schema/purpose/digest/template/order/duplicate/extra fields/date/identifier/version; actual absence vs authenticated mismatch; out-of-universe membership; copied/forged/mutated proof and copied Context; source reader/validator substitutions; local Context correction race; equal leading tie; global signature corruption; final earlier-member correction and changed absence markers.

## Concerns / review notes

- Existing Context schema restricts industry value text to identifier syntax. The signed child intentionally follows this task's broader trimmed-text contract. A signed label that no authentic Context fact can represent or match cannot receive an assignment; missing/mismatching facts stay pending. Fixture labels such as `banks` are synthetic identifiers, **not claims of real SW2021 industry codes**. Display-name/schema expansion is out of scope and was not attempted.
- This slice captures evidence only. Consumers must perform `recheck_batch` after feature work; it grants no indefinite latest-state validity or publication authority.
- No independent constructor provenance seal was added to StateStore/FormalSnapshotRepository/FormalSnapshotStore. The new boundary requires exact classes, complete matching initialized attributes, genuine read methods, same object dependencies, fixed paths/verifiers and real persisted verification. Context and metric repository objects have explicit constructor identity seals. The narrower StateStore/snapshot boundary follows existing authentic read behavior; independent review should assess whether the brief intends additional constructor-seal requirements for those underlying classes, which would require discussing the allowlist before changing their constructors.
- The focused tests cover instance reader/validator substitutions. Guards also inspect original class methods/descriptors; broad adversarial exploration beyond the concrete cases was left for independent review as directed.
- Parent owns affected existing StateStore universe, Context/calendar and Task 2A regressions and review. Those broader suites were not rerun by this worker. Parent reported the old universe baseline separately; this report does not count it as worker verification.

Files frozen after this report for parent review/regressions.

## Review round 1 — copied underlying dependency constructors

Reviewer finding: shallow copies of the genuine StateStore, FormalSnapshotRepository and FormalSnapshotStore could be aligned, passed through a normal Context constructor, and accepted by the metric factory. The resulting proof still authenticated real persisted evidence; this was the explicit copied-repository contract gap, not acceptance of fabricated facts. Parent approved the narrow constructor-bookkeeping allowlist expansion.

Fix-only changes:

- Added `ashare_pipeline/formal_repository_identity.py`: one small closure-private constructor identity record shared by the three dependency types. `_track_repository_constructor` wraps a class's own normal `__init__`; it records a weak object identity and that exact wrapper only after the original constructor returns successfully. `_require_repository_initialization` checks the exact live object and constructor wrapper identity. There is no instance eligibility flag or public mutable registry. A helper-created wrapper around some unrelated function cannot authenticate a copied dependency because its wrapper identity does not match the dependency's concrete class constructor. Explicit failed reinitialization removes any earlier registration; successful legitimate reinitialization remains valid.
- `state_store.py`, `formal_snapshot_repository.py`, `formal_snapshot_store.py`: each adds the helper import and decorator directly on its own constructor (three added lines per existing file in this review round). No constructor body/read/calendar/DDL logic changed.
- `formal_metric_context.py`: captures the authentic private initialization checker, invokes it on all three concrete dependencies at every existing entry/exit validation, and includes the StateStore constructor descriptor in its existing method guard. Exact-class, same-object/store/verifier, path, class-descriptor, instance-override and real persisted-read checks remain in force.
- `tests/test_formal_metric_context.py`: four added tests cover the exact combined-copy reproduction, six individual copy/fabricated-handle cases, normal pre-metric-import construction in a fresh process, and legitimate repeated `__init__` followed by complete metric resolution/recheck. Existing Context identity tracking was inspected and left unchanged. No Task 2A source edits.

Public API/wire formats are unchanged. These constructor records are required only at the new metric proof boundary; legacy APIs do not start rejecting copied/unconfigured objects merely because of this bookkeeping. Repeated database `initialize()` and configured stores reopening an existing database without rerunning `initialize()` remain supported.

Actual RED:

```text
python -m unittest
  tests.test_formal_metric_context.FormalMetricContextTests.test_combined_copied_stores_cannot_mint_a_universe
  tests.test_formal_metric_context.FormalMetricContextTests.test_individual_copied_or_fabricated_dependencies_cannot_mint -v
Ran 2 tests in 1.854s
FAILED (failures=7)
```

All seven failures were the intended `AssertionError: ValueError not raised`: the combined copy plus StateStore/SnapshotRepository/SnapshotStore separately through both `copy.copy` and `object.__new__` with copied dictionaries. Those tests exercised the genuine persisted fixture and attempted actual proof loading.

Focused GREEN after the fix:

```text
python -m unittest
  tests.test_formal_metric_context.FormalMetricContextTests.test_combined_copied_stores_cannot_mint_a_universe
  tests.test_formal_metric_context.FormalMetricContextTests.test_individual_copied_or_fabricated_dependencies_cannot_mint
  tests.test_formal_metric_context.FormalMetricContextTests.test_genuine_dependencies_constructed_before_metric_import_are_accepted
  tests.test_formal_metric_context.FormalMetricContextTests.test_legitimate_dependency_reinitialization_preserves_metric_reads -v
Ran 4 tests in 3.040s
OK
```

Focused constructor/read compatibility GREEN:

```text
python -m unittest
  tests.test_formal_snapshot_repository.FormalSnapshotRepositoryTests.test_constructor_requires_the_configured_authoritative_raw_store
  tests.test_formal_snapshot_repository.FormalSnapshotRepositoryTests.test_constructor_reuses_the_configured_date_only_calendar_resolver
  tests.test_state_store.StateStoreTestCase.test_initialize_twice_keeps_one_complete_v5_schema_and_ledger
  tests.test_formal_metric_context.FormalMetricContextTests.test_complete_signed_industries_preserve_all_exchanges_and_late_capture
  tests.test_formal_metric_context.FormalMetricContextTests.test_changed_real_read_dependencies_cannot_mint_or_recheck -v
Ran 5 tests in 3.328s
OK
```

All commands used `D:/Projects/AShareQiheng/.venv/Scripts/python.exe` from the assigned worktree. Fresh-process direct-first import smoke `python -c "import ashare_pipeline.formal_metric_context"` exited 0 with no output, independently of the fixture's import order. `git diff --check` passed with only Windows line-ending advisory messages. No full suites or Git writes were performed in this review round.

The initial report's concern about missing underlying constructor provenance is resolved by this round. Remaining notes are the already documented Context identifier compatibility and mandatory final recheck; full regressions and scoped independent re-review remain parent-owned. Files frozen again after this appendix. No running tests and no new unresolved implementation blocker.
