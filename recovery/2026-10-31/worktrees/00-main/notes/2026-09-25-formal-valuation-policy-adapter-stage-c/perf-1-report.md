# Perf-1: scoring official proof without repeated slot materialization

## Scope and change

`_parse` still calls `_feature_slots` with full materialization and validates all five templates and their 125 slots. Subsequent `FormalScoringRegistry.require_official` calls still verify the scoring seal, the current bundle's official proof and every child byte/hash, the original scoring bytes, and the same-root feature registry. The scoring trust closure captures the original `require_release_eligible`, checks that its class binding has not changed, calls it once, and then compares the four authenticated feature fields with the bundle. It skips only the unused slot rematerialization on this later path. No public signature, evidence threshold, policy binding inventory, Stage C behavior, or range implementation changed.

## TDD and count evidence

The new profile-based count test failed before the implementation: one warmed `require_official` invoked `slots_for_template` five times. After the change, initial loading still invokes it five times, while one warmed proof invokes `require_release_eligible` once, the feature fingerprint once, and `slots_for_template` zero times.

## Security regression

Warmed proof tests reject feature scalar, signature, canonical-byte, hash, slot, formula, and formula-items mutation, plus scoring child, other child, manifest-root, mixed-root, copied/forged registry, and approval mutation. A follow-up P1 review found that dynamically looking up `require_release_eligible` could be replaced with a no-op, letting the later direct field reads overlook a deep slot mutation in the scoring public API. Two new direct-entry tests first failed on that behavior, then passed after the closure pinned the original verifier. They cover a warmed registry with a replaced verifier and changed slot unit, plus a replacement before first load and a polluted object after restoration. Existing policy guard tests cover replaced scoring helper and upstream feature verifier bindings.

## Verification and commit

- Final scoring registry suite: 22/22 passed.
- Feature contract, scoring registry, and policy guard group: 67/67 passed.
- Range contract group: 17/17 passed.
- The wider 263-test feature/scoring/policy/range run reached the range store/worker stage without a failure marker, then was stopped after one test produced no new result for more than 15 minutes. It had no final summary, so it is not counted as passed; its active test name was unavailable because this run used unittest's non-verbose output.
- Initial optimization commit: `38f18b9`.
- Independent P1 repair commit: `defd528`. Both commits contain only `ashare_pipeline/formal_scoring_registry.py` and `tests/test_formal_scoring_registry.py`.

## Residual risk

The count test establishes eliminated duplicate work, not a wall-clock speedup. The wider run did not finish, and the full repository suite was not run. No policy or range optimization is included.
