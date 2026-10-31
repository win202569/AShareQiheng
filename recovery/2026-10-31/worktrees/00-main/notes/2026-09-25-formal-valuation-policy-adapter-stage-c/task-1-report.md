# Task 1 report: Versioned ten-role registry root

## Implementation summary

- Added schema-specific root role maps: v1 remains exactly nine roles; v2 requires exactly ten, adding `valuation_adapter_registry_hash`.
- The signed manifest now exposes `schema_version` and nullable `valuation_adapter_registry_hash`. Both are included in repository snapshots and the private verification fingerprint, so post-verification mutation invalidates the manifest and bundle seals.
- The bundle derives `roles` and accepted blobs from the signed schema. Loading still verifies each child hash, signature, declared role, root binding signature, and approval ID.
- Kept the scoring graph fixture v1 by default. Its v2 mode requires an explicit adapter document. Feature registry root validation includes the tenth hash for v2 so the required fixture can load its signed feature vocabulary.

## Files changed

- `ashare_pipeline/formal_registry_manifest.py`: schema-specific roles, manifest fields/seals, exact-role bundle loading.
- `ashare_pipeline/formal_feature_contract.py`: include the v2 adapter hash in exact sealed-root validation (two-line compatibility fix required by the scoring graph fixture).
- `tests/test_formal_registry_manifest.py`: v1/v2 role, root, child, binding, approval, and seal coverage.
- `tests/test_formal_scoring_registry.py`: default-v1 and explicit-v2 signed graph fixture coverage.

Commit: `5e36b41 feat: version the formal registry root for valuation adapters`. The worktree is clean after the commit.

## RED/GREEN evidence

- RED: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_registry_manifest -v` after test changes: `Ran 22 tests ... FAILED (errors=6)`. V1 failed because `FormalRegistryManifest.schema_version` did not exist. V2 cases failed because the fixed v1 root parser rejected the adapter field as `unknown or missing keys`; existing v1 tests still passed.
- GREEN: same focused command after the registry implementation and test fixture corrections: `Ran 22 tests ... OK`.
- Integration RED: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_registry_manifest tests.test_formal_scoring_registry tests.test_formal_policy_registry tests.test_formal_feature_contract tests.test_formal_sources -v`: `Ran 142 tests ... FAILED (errors=1)`. The new v2 scoring graph test failed in `formal_feature_contract._validate_root` because it supplied nine hashes to the v2 manifest's exact-ten check.
- Integration GREEN: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_scoring_registry.FormalScoringRegistryTests.test_signed_graph_fixture_selects_exact_manifest_role_set -v`: `Ran 1 test ... OK` after the two-line fix.
- Listed regressions GREEN: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_registry_manifest tests.test_formal_scoring_registry tests.test_formal_policy_registry tests.test_formal_feature_contract tests.test_formal_sources -q`: `Ran 142 tests in 55.092s ... OK`.
- Optional full discovery: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest discover -s tests -p 'test_*.py' -q` ran for over 20 minutes in quiet mode without producing a final result. It was cleanly interrupted at the parent task's direction after the plan-required focused and 142-test regression gates passed. The repository-wide suite includes long production-style tests and was not used as C1 acceptance. A first plain `unittest discover -q` invocation returned `Ran 0 tests ... NO TESTS RAN`, so the corrected `-s tests` invocation above was used.
- `git diff --check`: passed; only Git's existing LF-to-CRLF working-copy warnings appeared.

## Self-review

- Verified that v1 roots with an adapter field and unknown v3 schemas fail, and v2 roots without the adapter field, with a malformed adapter hash, or with a duplicate hash fail.
- Verified that a v2 adapter child with missing storage, wrong envelope/declaration role, wrong root binding, wrong approval ID, or bad binding signature cannot load.
- Verified the positive v2 official bundle path and that `object.__setattr__` changes to schema or adapter hash invalidate seals.
- Reviewed the diff for changes outside C1. The feature-contract change is required to make the specified v2 scoring fixture return its signed vocabulary; it does not change feature semantics, which remain anchored to source, mapping, and feature hashes.

## Concerns and handoff

- `ashare_pipeline/formal_financial_features.py:559-560` still supplies nine hashes to `assert_member_hashes`; a v2 manifest will be rejected when building a formal feature bundle. This belongs to later runtime v2 integration.
- `ashare_pipeline/state_store.py:2079-2080` also supplies nine hashes, and its stored root field list is v1-shaped. V2 root persistence needs an explicit versioned storage update in the later task.
- No production data was changed. No push or merge was performed.
