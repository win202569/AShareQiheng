# Residual Feature-Ready Trust-Boundary Repair

## Baseline and authority

- Baseline commit: `38037273f4710f4b70cc684884a51502607c1d09`.
- User explicitly authorized this additional targeted repair after the final-fix re-review reproduced one remaining Important finding.
- This is a new, bounded SDD task. Use test-driven development and an independent task review.

## Problem to close

`FeatureBundle.from_dict()` and `FeatureBundle.validate()` currently accept canonical, hash-consistent bundles that falsely declare `financial_status="financial_ready"` when:

1. the applicable financial dimensions (`G`, `M`, `EQ`, `FS`, `CA`) are missing or blocked; or
2. the registered industry template requires specialized financial inputs that are not implemented, but the bundle omits `specialized_financial_inputs_missing` and declares itself ready.

Because the same validator is trusted by persistence, verified reads, and progress reporting, such a forged bundle can otherwise be written and counted ready.

## Required behavior

1. A bundle declaring `financial_ready` must be rejected unless its actual applicable registered financial inputs support complete readiness:
   - no applicable financial dimension/value is `missing` or `blocked`;
   - the applicable registered slot set, not merely self-reported coverage/confidence, supports full coverage;
   - existing valid `general_nonfinancial` ready bundles continue to round-trip.
2. For a registered template with `specialized_inputs_required=True`, while specialized inputs are not implemented, the canonical bundle must have:
   - `financial_status="blocked"`; and
   - blocker `specialized_financial_inputs_missing`.
   Ready status, or blocked status without that blocker, must be rejected at the public contract boundary.
3. Formal score readiness, seven-dimension readiness, the waiting-price pool, and the strong-attention pool remain closed.
4. Validation must use the actual registered template contract without creating an import cycle. `industry_templates.py` imports canonical hashing from `feature_contract.py`; any dependency back to the registry must therefore be runtime-safe and narrowly designed.

## Required RED/GREEN regressions

Write and observe failing tests before production changes:

1. Public parser rejects a ready bundle whose `G/M/EQ/FS/CA` dimensions/values are missing or blocked.
2. Public parser rejects a specialized template marked ready without `specialized_financial_inputs_missing`, and rejects a specialized blocked bundle missing that blocker.
3. A real production path proves a forged-ready bundle cannot be persisted and then counted by verified read/progress. Prefer proving `StateStore.put_feature_bundle` rejects before a successful file/DB commit; the regression must exercise real producer/consumer boundaries rather than mirror SQL or duplicate validator logic.
4. A valid `general_nonfinancial` financial-ready bundle still survives canonical serialize/parse and persistence/verified-read/progress behavior as applicable.

## Scope guardrails

- Expected production scope: `ashare_pipeline/feature_contract.py`, with only the smallest supporting change if the registered template contract cannot otherwise be consumed safely.
- Expected tests: `tests/test_feature_contract.py` and, only where needed for the real boundary regression, `tests/test_state_store.py`, `tests/test_deep_worker.py`, or `tests/test_orchestrator.py`.
- Do not refactor broadly. Do not alter runtime data, source snapshots, migrations, scoring, pool selection, or network behavior.
- Do not address the three deferred Minor findings: whole-job heartbeat coverage, legacy absolute snapshot containment, or plan table-name typos.
- Do not open or migrate the tracked runtime database. Tests must use isolated temporary roots.

## Verification

- Focused new tests with captured RED then GREEN evidence.
- Related suites: `tests.test_feature_contract tests.test_financial_features tests.test_state_store tests.test_deep_worker tests.test_orchestrator tests.test_feature_foundation_e2e`.
- Full suite: `python -m unittest discover -s tests -v`.
- `git diff --check` and staged diff check.
- Commit only intended source/tests; never stage `.superpowers/`, `data/`, controller temp directories, or unrelated changes.
- Write implementation evidence to `residual-feature-ready-report.md` in this private SDD workspace.
