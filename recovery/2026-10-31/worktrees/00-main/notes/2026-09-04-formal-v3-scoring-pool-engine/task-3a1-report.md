# Task 3A1 report — signed neutral-consensus linkage contract

## Status

DONE. Implementation and focused verification are complete at base `be01e65ef1557943b63b84a80383252963512db7`. No Git index, commit, network, data, main, or push operations were performed.

## Implementation

- `ashare_pipeline/formal_scoring_registry.py`
  - Admits exact `formal-scoring-registry-v2` wrappers with the required five top-level fields while preserving the v1 four-field branch.
  - Reuses `formal_context_schema._descriptor` for every v2 descriptor and its canonical entry-byte function for `descriptor_id` hashing.
  - Rejects duplicate descriptor selection identities and ambiguous descriptor hashes.
  - Validates exact, sorted, unique `input_alternatives` against the already-validated V3 template/metric/feature adapter graph and the linked consensus descriptor semantics.
  - Adds recursively immutable `consensus_no_coverage_links`, including derived `context_kind` and `scope_key`, to the sealed/fingerprinted registry. V1 loads receive an empty immutable mapping.
- `ashare_pipeline/formal_context_schema.py`
  - Adds wrapper admission only for exact v2 scoring wrappers: exact five keys, exact scoring object, exact alternatives list. Existing descriptor, signed graph, source selection, and resolver validation remain unchanged.
- `tests/test_formal_scoring_consensus_registry.py`
  - Adds real byte-sensitive HMAC-signed graph coverage for valid empty/subset/all-five links, canonical descriptor entry hashes, recursive immutability/seals, exact key/version rejection, link and descriptor semantics, feature-key uniqueness, approval/root/byte integrity, and test-purpose separation.
- `tests/test_formal_context_repository.py`
  - Changes only `ScoringWrapperIntegrationTests`: legacy/v1/v2 descriptor identity, linked consensus resolution, v999 unknown-version regression, and v2 alternatives-list shape.

The existing fixture/helper was sufficient; `tests/test_formal_scoring_registry.py` and the original fixture bytes were not edited.

## TDD evidence

### RED 1 — scoring registry v2 admission

Command:

`D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_formal_scoring_consensus_registry -v`

Observed before production change: 1 test, 1 error, unittest duration `0.022s`, exit 1. The genuine signed v2 graph reached `load_formal_registry` and failed because `input_alternatives` was an unknown scoring-wrapper key. This was the intended missing behavior, not an import or fixture error.

### GREEN 1

Same command after minimal v2 registry implementation: 1/1 passed, unittest duration `0.265s`, exit 0.

Expanded scoring contract run after correcting a test-only callback-shadowing error: 10/10 passed, unittest duration `5.251s`, exit 0. The callback error was fixed before treating the expanded run as behavioral RED evidence.

### RED 2 — Context wrapper compatibility

Command:

`D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_formal_context_repository.ScoringWrapperIntegrationTests -v`

Observed before Context production change: 3 tests ran with 1 failure and 1 error, unittest duration `0.919s`, exit 1. Both valid-v2 paths failed at exact wrapper-key admission; malformed/unknown wrapper rejection remained green.

### GREEN 2

Same command after wrapper-only admission: 3/3 passed, unittest duration `1.063s`, exit 0.

## Final focused verification

Command:

`D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_formal_scoring_consensus_registry tests.test_formal_scoring_registry tests.test_formal_context_repository.ScoringWrapperIntegrationTests -v`

Observed: 30/30 passed, unittest duration `18.257s`, exit 0 (tool wall time `18.693s`).

`git diff --check` exited 0. Git emitted only the worktree's configured LF-to-CRLF conversion warnings; no whitespace errors were reported.

## Final SHA-256 hashes

- `ashare_pipeline/formal_scoring_registry.py`: `90ed15ac918f747a17bf9709e9891b7e6c162dad1dd0911206ee9afb0f8d0532`
- `ashare_pipeline/formal_context_schema.py`: `abba4776fcb37ca5f06fa2591e7a4b90e9b3092713a2fa5f6d3eef87faf3ad4c`
- `tests/test_formal_scoring_consensus_registry.py`: `71d5d070f91b63538c8fe166b7465628983864215f3f70c2f3afdbd38d2e5aa0`
- `tests/test_formal_context_repository.py`: `e61722e6a06ed982376fcdcab8efad8ef1a2b7f8056987a70380f4f9a51e3208`
- Unchanged `tests/fixtures/formal_v3_test_registry.json`: `e61b4e20dbfd03396614d392b13b781b59c436ce52676d88308c500cc33174c4`

## Exact-diff self-review

- Scope matches the active 3A1 allowlist plus this required report. The unrelated pre-existing untracked `tmpj4zv9_fq/` directory was not read, modified, or removed.
- V1 parsing and canonical fixture bytes are unchanged; its only new observable is the required empty immutable link mapping.
- V2 validates every descriptor through the existing Context validator and hashes the canonical descriptor entry, never the wrapper.
- Context v2 handling checks wrapper shape only and does not grant scoring semantics.
- The registry seal fingerprints the new outer and nested immutable mappings, so copy/forced replacement cannot establish official proof.
- No source or feature data rewriting, proof minting, neutral numeric value, confidence cap, feature-repository exception, metric calculation, or scorecard behavior was added.
- Mutation review is covered for wrong constants/branches, empty and malformed values, duplicate/unsorted links, missing/extra fields, unknown/cross-template/shared feature keys, descriptor mismatch, and provenance tampering.

## Concerns and boundary notes

No 3A1 implementation concerns. As required, a signed synthetic official-wire graph proves software provenance only. Reverification of a complete same-root no-coverage response and all numeric scoring behavior remain deliberately outside this slice for 3A2/3B.
