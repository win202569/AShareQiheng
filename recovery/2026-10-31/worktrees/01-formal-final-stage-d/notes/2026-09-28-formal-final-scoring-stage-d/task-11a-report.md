# Task 11a — D1 fractional canonical decode boundary

## Scope

- Changed only the tracked files `ashare_pipeline/formal_final_score_inputs.py` and `tests/test_formal_final_score_inputs.py`.
- Kept the existing source canonical-byte SHA-256 anchors and upstream proof implementations unchanged.
- Did not run any test that constructs `FinalScoringFixture` or a D1 batch.
- Did not commit or relink the worktree.

## Root cause

`FormalFinalScoreInputRepository.build_batch` authenticated and hashed each source's canonical bytes, but later detached base provenance through `original.to_dict()`. That method uses default `json.loads`, which turns fractional JSON tokens into Python `float`; the V8 repository correctly rejects every `float`.

## TDD evidence

RED:

```text
python -m unittest tests.test_formal_final_score_inputs.FinalScoreInputCanonicalDecodeTests.test_detached_source_payload_preserves_fractional_lexemes_without_float
FAILED (failures=1)
AssertionError: 'detached_source_payload' not found in build_batch closure
Ran 1 test in 0.759s
```

GREEN after the minimal production change:

```text
.
Ran 1 test in 0.374s
OK
```

Review-fix RED:

```text
FAILED (failures=1)
AssertionError: 'policy_result.to_dict()' unexpectedly found in build_batch source
Ran 1 test in 0.605s
```

Review-fix GREEN:

```text
.
Ran 1 test in 0.592s
OK
```

Second-review authority RED:

```text
JSONDecoder.decode mutation escaped the boundary as AssertionError
FAILED (failures=1)
Ran 1 test in 0.212s

json.JSONDecoder module binding replacement did not raise ValueError
FAILED (failures=1)
Ran 1 test in 0.460s
```

Second-review authority GREEN:

```text
.
Ran 1 test in 0.446s
OK
```

Third-review UTF-8 boundary RED:

```text
Stateful json.detect_encoding replacement escaped the boundary as AssertionError
FAILED (failures=1)
Ran 1 test in 0.395s
```

Third-review UTF-8 boundary GREEN:

```text
.
Ran 1 test in 0.204s
OK
```

The pure boundary test proves that the closure helper verifies the source and reads `canonical_bytes()` without calling `to_dict()`, recursively converts project-canonical fractional tokens to exact strings while preserving integers, emits no floats, remains accepted by `_serialize_payload`, and rejects NaN, Infinity, duplicate keys, whitespace/key-order changes, and noncanonical numeric lexemes (`1e2`, `1.2300`, `1E+00`). It also proves a replacement of the module `json.JSONDecoder` entry cannot redirect the captured decoder type.

Lightweight source assertions prove the builder uses detached payloads for the original base row, policy result, Stage C score, context, and adjusted input; derives slots and the final payload from `detached_original`; and contains none of the replaced source-proof `to_dict()` calls.

## Implementation

- Added the closure-captured `detached_source_payload` boundary.
- It captures `json.JSONDecoder`, re-verifies the source, consumes exact canonical bytes, rejects nonfinite constants and duplicate keys, and validates project canonicality with the existing protected encoder before returning `json.loads(raw, cls=decoder_type, parse_float=str, ...)`.
- Installation snapshots the JSON module's decoder bindings, decoder/scanner critical bindings, every `JSONDecoder` class member, decoder inheritance, and mutable `BACKSLASH`/`_CONSTANTS` contents. `interfaces()` checks all snapshots on every direct helper entry, so binding or class-member mutation fails closed before decoding.
- The helper decodes canonical bytes exactly once with built-in UTF-8 decoding, converts invalid UTF-8 to an explicit `ValueError`, and feeds the same text to both captured decoder passes. It therefore has no dependency on mutable `json.detect_encoding`, including for non-ASCII provenance.
- Replaced base, policy-result, Stage C score/context/adjusted `to_dict()` provenance paths with the canonical-byte boundary.
- Base slot copies and the final base payload now derive from `detached_original`, preventing live proof attributes from reintroducing floats.
- Existing `source_bytes`, canonical SHA-256 fields, publication rechecks, and upstream proof code are untouched.

## Verification

```text
Focused pure boundary test: OK (1 test)
Existing V8 decimal boundary test method: OK
AST parse of both changed files: AST OK
git diff --check: exit 0 (only Windows line-ending warnings)
```
