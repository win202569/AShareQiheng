# Residual Feature-Ready Trust-Boundary Repair Report

## Result

- Baseline: `38037273f4710f4b70cc684884a51502607c1d09`
- Branch: `feature/seven-dimension-foundation`
- Commit: `13aea24` (`fix: enforce financial-ready feature contract`)
- Outcome: implementation and verification complete.
- Scope stayed within the feature contract, the existing period consumer, and focused contract/orchestrator tests. No runtime data, migrations, score logic, pools, network paths, or deferred Minor findings were changed.

## Root cause

`FeatureBundle.validate()` treated self-reported `financial_coverage=1.0`, the absence of self-reported financial blockers, and a classified template ID as sufficient for `financial_ready`. It did not consume the registered template's `financial_slots`, did not bind those slots to all seven required periods, did not inspect G/M/EQ/FS/CA container/value readiness, and did not enforce `specialized_inputs_required` at the public contract boundary. Because file verification, `StateStore.put_feature_bundle()`, verified reads, and progress all trust the same validator, canonical and hash-consistent forged-ready content crossed every downstream boundary.

## TDD RED evidence

Command:

```powershell
$env:TEMP='D:\Projects\AShareQiheng\.worktrees\seven-dimension-foundation\.residual-fix-temp'
$env:TMP=$env:TEMP
$env:TMPDIR=$env:TEMP
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m unittest tests.test_feature_contract.FeatureContractTests.test_public_parse_rejects_ready_missing_or_blocked_financial_inputs tests.test_feature_contract.FeatureContractTests.test_public_parse_rejects_ready_with_registered_slot_period_omitted tests.test_feature_contract.FeatureContractTests.test_public_parse_enforces_specialized_template_blocker tests.test_feature_contract.FeatureContractTests.test_general_ready_bundle_still_has_canonical_public_round_trip tests.test_orchestrator.OrchestratorTestCase.test_forged_ready_cannot_cross_write_or_persistence_boundary_or_count_ready tests.test_orchestrator.OrchestratorTestCase.test_general_ready_round_trips_through_verified_storage_and_progress -v
```

Observed result before production changes:

- `Ran 6 tests in 0.315s`
- `FAILED (failures=11)`
- Every failure was the expected `AssertionError: ValueError not raised`, proving the current public parser/persistence validator accepted the forged payload rather than exposing a test setup or syntax error.
- Failing attacks: missing/blocked financial dimension container, missing/blocked financial value, omitted registered raw slot-period, real-estate/resource specialized ready and blocked states without the required blocker, bank blocked without the required blocker, and the real StateStore persistence boundary.
- The valid general-ready canonical round-trip and valid production persistence/progress tests were already green in the RED run, proving the regression fixtures did not invalidate the compatibility case.

The dimension/value matrix was then expanded to cover each of `G`, `M`, `EQ`, `FS`, and `CA`; it exercises both container status and an actual applicable value status for missing and blocked attacks.

## Minimal implementation

### Registry and period authority

- `FeatureBundle.validate()` imports `TEMPLATES` only inside the method. This is runtime-safe and does not create a module-load cycle.
- Applicable raw slots come only from `TEMPLATES[self.industry.template_id].financial_slots`. No template table, template-ID list, or specialized-template list is copied into `feature_contract.py`.
- The seven fixed financial periods are a feature-contract-wide invariant, not a per-template registry choice. They are now expressed once as `FINANCIAL_PERIODS` in `feature_contract.py`; `financial_features.py` consumes the same tuple as `_REQUIRED_PERIODS`. `FINANCIAL_PERIOD_KEYS` is derived from that tuple for validation. This removes a potential validator/builder period-list drift.

### Ready validation

For `financial_ready`, validation now requires:

- existing coverage/blocker/classification constraints;
- every G/M/EQ/FS/CA container to be `input_ready` or explicitly `not_applicable`;
- no missing or blocked value in those financial dimensions;
- exactly one canonical observed/derived raw feature for every registered `financial_slot × required period` pair.

V and T remain outside financial readiness, preserving their intended current-phase missing containers.

### Specialized validation

Every classified template whose registered definition has `specialized_inputs_required=True` must have both:

- `financial_status="blocked"`; and
- blocker `specialized_financial_inputs_missing`.

`unclassified` keeps its existing dedicated `industry_template_unclassified` behavior, matching the current builder. Existing bank, real-estate, and resource-cycle builder behavior remains valid.

## GREEN and regression evidence

Focused GREEN after implementation:

- Same six-test command: `Ran 6 tests in 0.341s`, `OK`.
- Expanded G/M/EQ/FS/CA matrix: `Ran 6 tests in 0.457s`, `OK`.

Fresh focused/financial consumer run after centralizing the period contract:

```powershell
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m unittest tests.test_feature_contract tests.test_financial_features tests.test_orchestrator.OrchestratorTestCase.test_forged_ready_cannot_cross_write_or_persistence_boundary_or_count_ready tests.test_orchestrator.OrchestratorTestCase.test_general_ready_round_trips_through_verified_storage_and_progress -v
```

- `Ran 78 tests in 1.097s`
- `OK`

Required related suites:

```powershell
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m unittest tests.test_feature_contract tests.test_financial_features tests.test_state_store tests.test_deep_worker tests.test_orchestrator tests.test_feature_foundation_e2e -v
```

- `Ran 250 tests in 63.746s`
- `OK`

Fresh staged full suite:

```powershell
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m unittest discover -s tests -v
```

- `Ran 355 tests in 69.725s`
- `OK`

Diff verification:

- `git diff --check`: exit 0, no whitespace errors.
- `git diff --cached --check`: exit 0, no whitespace errors.
- Staged paths are exactly:
  - `ashare_pipeline/feature_contract.py`
  - `ashare_pipeline/financial_features.py`
  - `tests/test_feature_contract.py`
  - `tests/test_orchestrator.py`

## Real boundary proof

The forged regression starts from a real production-built, valid general-ready bundle, removes the registered `revenue/FY2021` raw input while preserving the forged ready declarations, and then exercises:

1. `StateStore.put_feature_bundle()` revalidation: rejected before any feature-set row is inserted;
2. `write_feature_bundle()` canonical self-parse: rejected before any final JSON is linked;
3. real status/progress: zero feature sets and zero `financial_ready` count.

The companion compatibility regression takes a real production-built general-ready bundle through public parse, canonical file write, verified file read, StateStore persistence, and real status/progress. It is counted once as `financial_ready` while `formal_score_ready=false`, `seven_dimension_ready=false`, and both official pool counts remain zero.

## Self-review

- Mutation check: removing financial container/value checks breaks the G/M/EQ/FS/CA attack matrix; removing the registered slot-period comparison breaks the omission attack; removing the specialized branch breaks the specialized ready/blocked cases; rejecting V/T missing or general-ready bundles breaks the compatibility path.
- No mirrored SQL or duplicate validator logic is used to establish the production boundary result. Tests assert the actual DB row count, real final bundle files, verified read, and public progress output.
- No formal score, seven-dimension readiness, waiting-price pool, or strong-attention pool code was changed; the real progress regressions assert all four gates remain closed.
- No test uses network access or the tracked runtime database. All roots are isolated temporary directories under the required workspace-local TEMP setting.
- No `.superpowers/`, `data/`, `.tmp-tests/`, `.tmp-root-check/`, or temp directory is staged.
- Deferred Minor findings were not touched.

## Concerns

None in the requested code scope. The pre-existing untracked `.tmp-tests/` and inaccessible `.tmp-root-check/` warning remain unrelated and unstaged.

---

# Fix round 1: bind registered raw slots to canonical evidence metadata

Commit: `c799531f8a8a2173c5557db4d1d9afaf6ebd464e`

## Review finding independently reproduced

The review was correct: the first validator revision identified a registered raw
slot using only the mutable feature key, period, and an `observed`/`derived`
status. A derived G/M value could therefore be copied and renamed to an omitted
raw slot such as `g.revenue.FY2021`. The payload still satisfied the slot-period
set and was accepted as `financial_ready`.

## TDD RED evidence

The new regression starts with a real production-built
`general_nonfinancial` ready bundle, removes `g.revenue.FY2021`, and exercises
five adjacent substitutions: a derived value in the wrong dimension, a derived
value in the canonical dimension, an observed value in the wrong dimension, an
observed value with derived-formula metadata, and another observed raw slot
renamed to revenue. A second test sends the derived wrong-dimension variant
through the real file writer, `StateStore`, verified read, and status/progress
path.

Command before production changes:

```powershell
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m unittest tests.test_feature_contract.FeatureContractTests.test_public_parse_rejects_registered_raw_slot_retag_substitutions tests.test_orchestrator.OrchestratorTestCase.test_derived_retag_cannot_cross_verified_storage_or_count_ready -v
```

Observed:

- `Ran 2 tests in 0.239s`
- `FAILED (failures=6)`
- All five public-parser subtests failed with `AssertionError: ValueError not raised`.
- The real boundary accepted, wrote, persisted, verified, and counted the forged
  bundle: `feature_set_counts` was
  `{'partial': 0, 'financial_ready': 1, 'blocked': 0}` instead of zero.

## Root cause and minimal correction

`financial_schema.py` now owns `RawFinancialSlotDescriptor`, the authoritative
raw-fact contract derived from its existing `_FIELD_RULES`. Each descriptor
binds `metric_key`, canonical financial dimension, `kind='raw_fact'`,
`allowed_statuses=('observed',)`, active mapping/formula version, unit, and
allowed source fields. The existing synthetic/future `share_repurchase_cash`
slot has one explicit descriptor because it is intentionally registered by the
templates but is not yet present in the upstream field mapping table.

Both producer and consumer use that same authority:

- `financial_features.py` no longer owns duplicate raw-dimension/unit tables;
  assembly and observed-value creation resolve the descriptor.
- `FeatureBundle.validate()` runtime-imports the descriptor resolver, avoiding
  the existing `financial_schema -> feature_contract` module-load direction.
  Applicability still comes solely from the registered template's
  `financial_slots`, and periods still come solely from
  `FINANCIAL_PERIOD_KEYS`.
- A registered raw value counts only when its dimension, canonical key, status,
  formula/mapping version, unit, single evidence record, and evidence source
  field match the descriptor.
- A financial fact ID may satisfy only one required raw slot-period. This closes
  cloning one observed primitive into another slot after merely retagging its
  mutable key/evidence label; moving instead of cloning leaves the source slot
  incomplete.

The public bundle format intentionally does not embed an entire `FinancialFact`,
so the parser cannot recompute a fact ID from first principles. Persistence
continues to rely on the canonical evidence reference; the fix binds every
metadata field available at this public boundary without duplicating database
or builder logic.

## GREEN and regression evidence

Focused command above after the minimal implementation:

- `Ran 2 tests in 0.132s`
- `OK`

Focused contract/schema/builder and real-boundary suite:

- `Ran 88 tests in 1.383s`
- `OK`

Required related modules:

```powershell
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m unittest tests.test_feature_contract tests.test_financial_features tests.test_state_store tests.test_deep_worker tests.test_orchestrator tests.test_feature_foundation_e2e
```

- `Ran 252 tests in 64.105s`
- `OK`

Fresh full discovery:

```powershell
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m unittest discover -s tests
```

- `Ran 357 tests in 61.152s`
- `OK`

Fresh staged full discovery immediately before commit:

- `Ran 357 tests in 52.427s`
- `OK`

Diff verification:

- `git diff --check`: exit 0, no whitespace errors.
- `git diff --cached --check`: exit 0, no whitespace errors.
- Staged paths were exactly the three production and three test files listed in
  this fix round; the private report and temporary directories remained
  unstaged.

The valid real general-ready write/read/persist/progress regression remains
green. Specialized/unclassified builder behavior, V/T exclusion, and all four
formal score/seven-dimension/two-pool gate assertions remain unchanged and
closed.

## Fix-round self-review

- The validator consumes template slot applicability, schema raw-slot metadata,
  and the feature-contract seven-period list rather than copying any template ID
  or financial slot table.
- The builder consumes the descriptor's dimension, key, unit, status, mapping
  version, and source-field authority, so producer and public validator cannot
  drift independently on those fields.
- The new public-parser matrix isolates status, dimension, formula metadata, and
  cross-slot observed substitution. The real regression proves the original
  bypass crossed production storage/progress before the fix and is rejected
  before any file or database row afterward.
- No deferred Minor, network, `data/`, runtime database, migration, scoring, or
  pool code was changed.

## Fix-round concerns

None in the requested code scope. The pre-existing untracked `.tmp-tests/` and
inaccessible `.tmp-root-check/` warning remain unrelated and unstaged.
