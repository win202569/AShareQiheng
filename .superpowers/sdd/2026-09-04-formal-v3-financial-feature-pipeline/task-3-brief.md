# V6 Task 3 binding brief — signed feature contract and immutable storage

Plan: `docs/superpowers/plans/2026-09-04-formal-v3-financial-feature-pipeline.md`, Task 3.

Prerequisite: Task 2 must be accepted before implementation begins. This brief freezes only plan omissions needed to keep the feature contract fail-closed. It creates no production registry, slot, formula, template substitution, data fetch, score, pool, SQLite record, or task.

## Scope and commit boundary

Create or modify exactly these tracked files:

1. `ashare_pipeline/formal_feature_contract.py`
2. `ashare_pipeline/formal_feature_store.py`
3. `tests/test_formal_feature_contract.py`
4. `tests/test_formal_feature_store.py`

Do not modify Task 1/2 modules, `state_store.py`, legacy `feature_contract.py`, legacy snapshot storage, plans, data, SQLite/WAL/SHM, or any other tracked file. Do not collect data or make network calls. The initial code commit subject is `feat: add formal feature contract and storage`. Record RED/GREEN only in ignored `task-3-report.md`; never stage this brief, reports, or ledger.

## Shared security posture

Use the Task 1/2 ordinary Python threat model: exact public type checks, canonical bytes, defensive immutable copies, and closure-private provenance records protect against ordinary constructor calls, `object.__new__`, public field mutation, and exposed module helpers. The injected `RegistrySignatureVerifier` remains the trusted root; do not store or expose it on a public object. General arbitrary same-process reflection into Python function closure cells is an acknowledged language-level limitation shared with accepted Task 1, not a reason to invent a different trust model here.

All canonical JSON inputs reject duplicate keys, non-UTF-8, noncanonical whitespace/key order, `NaN`/infinity, non-JSON leaves, and verifier results other than exact `True` (including verifier exceptions). Text is exact type `str`, nonempty, already trimmed, and control-free where it crosses a lineage/key/path boundary. SHA-256 values are lowercase 64-character hexadecimal strings. UTC timestamps are aware, canonical `+00:00` forms. Security IDs use the exact Task 2 canonical SH/SZ/BJ convention.

## Public surface

`formal_feature_contract.py` produces:

```python
FormulaNode
FormalFeatureSlot
FormalEvidenceRef
FormalFeatureValue
FormalFeatureBundle
SignedFormalFeatureRegistry
load_signed_feature_registry
```

`formal_feature_store.py` produces:

```python
FormalStoredFeatureBundle
FormalFeatureBundleStore
```

Task 3 consumes only Task 2 `FormalFinancialFact` and Task 1 `RegistrySignatureVerifier`/`FormalRegistryManifest`. It does not evaluate formulas, derive quarters, choose visible facts, build score inputs, calculate scores, or persist to SQLite. Task 4 owns evaluation; Task 5 owns database membership and re-reads.

## Signed feature registry and root binding

The canonical signed feature-registry JSON has exactly:

```text
schema_version = "formal-feature-registry-v1"
registry_role = "feature"
contract_version
source_registry_hash
mapping_registry_hash
template_ids
slots
```

There is no `release_eligible` input field, no defaults, no source-field mapping, no template fallback, and no executable content. `template_ids` is an exact sorted tuple/list without duplicates and names only from:

```text
general_nonfinancial, bank, broker, insurance, real_estate
```

Each `slots` member has exactly:

```text
slot_id, template_id, dimension, required, unit, formula, formula_version
```

- slot IDs are global unique safe identifiers and sort ascending;
- template IDs must occur in `template_ids`;
- dimensions are exactly `G`, `V`, `M`, `EQ`, `FS`, `CA`, or `T`;
- `required` is exact `bool`, not an integer;
- formula/unit/version are exact valid values; and
- every template declares at least one slot, and every required slot is explicitly present in this signed child. The root pins this exact child hash; Task 3 must not invent a separate list of production-required slots.

`load_signed_feature_registry(registry_bytes, signature, key_id, verifier, *, registry_manifest=None)` validates canonical bytes and the injected signature before trusted construction. It returns a structurally valid signed child even when it is not release eligible, so test fixtures can exercise it. It must set `release_eligible` to `True` only when all of these are true:

1. `registry_manifest` is exact sealed `FormalRegistryManifest`, `require_official()` succeeds, and its `feature_registry_hash` exactly equals the child's registry hash;
2. the child `source_registry_hash` and `mapping_registry_hash` exactly equal the root's corresponding pinned hashes;
3. the child's `template_ids` are exactly the five-template set above; and
4. all declared required slots are valid, explicit, and the child is complete for every declared template.

Absent root, test-purpose root, unsealed/forged root, any role/hash mismatch, incomplete template set, or an invalid required-slot declaration yields `release_eligible=False` after structurally valid child loading (except a forged/unsealed root object, which must raise `ValueError`). Do not put `registry_manifest_hash` inside child bytes: root contains the child hash and doing so would create a hash fixed point. The external root-child equality above is the binding.

Like Task 2, ordinary direct construction, `object.__new__`, public field mutation, equality spoofing, and public module construction helpers must not mint or alter a trusted registry. Revalidate the sealed registry before every sensitive read/selection; reconstruct any effective slot configuration from canonical signed bytes rather than mutable public fields. Do not expose the verifier.

## Formula AST

`FormulaNode.from_dict` accepts JSON-shaped dictionaries only, exact keys by operation, and recursively returns frozen nodes. It never evaluates strings or accepts callables.

```text
fact       {op, fact_key, period_key}
add        {op, left, right}
subtract   {op, left, right}
divide     {op, left, right}
cagr       {op, left, right, intervals}
median     {op, items}
minimum    {op, items}
```

- `op` is exactly one listed string;
- fact keys/period keys are nonempty, trimmed safe identifiers;
- binary children are exact node wires, not arbitrary mappings or strings;
- `cagr.intervals` is an exact positive `int` (not bool);
- `median` and `minimum` use a nonempty sorted/position-preserving tuple of at least two exact node wires; and
- no operation accepts extra/missing/null fields, executable strings, arbitrary code, malformed nesting, or cycle-like Python objects.

Task 3 validates syntax only. It does not infer unit compatibility, resolve fact keys, calculate values, or turn a formula into a score.

### Frozen Task 3 interpretation decisions

The plan leaves four mechanical validation details unstated.  To keep this
boundary deterministic and fail-closed, Task 3 uses the following
interpretation:

- slot/value units are exactly the same closed set as formal facts:
  `CNY`, `shares`, `ratio`, and `CNY_per_share`;
- `median` and `minimum` preserve their signed child order only when the child
  canonical JSON bytes are already strictly ascending (duplicates and
  unsorted operands are rejected rather than reordered);
- direct constructors may normalize a finite exact int to float, but every
  `from_dict` wire must round-trip byte-for-byte through the JSON-native
  canonical representation, rejecting `int`/`-0.0` substitutes for a canonical
  float; and
- an existing per-hash lock always fails safely without deletion or waiting.
  A later writer may be idempotent only after a complete existing artifact can
  be independently verified; a caller may otherwise retry after the active
  writer releases its lock.

## Evidence, values, and bundle validation

`FormalEvidenceRef.from_formal_fact(fact)` accepts exact `FormalFinancialFact` only and starts with `fact.to_dict()` so Task 2's seal is rechecked. It copies exactly:

```text
formal_fact_id, source_snapshot_id, source_content_sha256,
source_refresh_generation, source_field, raw_value_sha256,
published_at_utc, published_precision, effective_at_utc, mapping_version
```

It may never accept a legacy fact, generic mapping, or caller-supplied partial lineage. Every construction/serialization path revalidates all fields. Task 5 later re-reads database fact/snapshot membership and generation; Task 3 must not claim that a snapshot/content pair substitutes for refresh generation.

`FormalFeatureValue` has exact status rules:

- `derived`: exact finite non-bool numeric value (normalize to float), nonempty sorted unique evidence, and `missing_reason is None`;
- `missing`, `blocked`, or `not_applicable`: `value is None`, nonempty safe `missing_reason`, and empty evidence;
- `slot_id`, `unit`, and `formula_version` are safe exact text.

`FormalFeatureBundle` uses exact plan fields and frozen nested tuples. Freeze `schema_version` to exact integer `1`; `contract_version` is safe text; `template_id` is one of the five names; `registry_manifest_hash`, `feature_registry_hash`, and `input_hash` are canonical SHA-256 values. Values are unique and sorted by `slot_id`; endpoints are sorted unique ISO dates; comparable keys are sorted unique `YYYYQ[1-4]`; blockers are sorted unique safe text. Bundle validation rejects nonfinite values, bools, duplicate/unsorted leaves, mutable/custom leaves, unknown keys, noncanonical types, and direct low-level mutation before every `to_dict`, `canonical_bytes`, or `bundle_hash` result. It must serialize and parse through exact JSON-native `to_dict`/`from_dict` wires.

`bundle_hash()` is SHA-256 of `canonical_bytes()`. The bundle's supplied `input_hash` is syntactically validated here; Task 4 owns computing it from selected facts/quarters and registry/as-of inputs. No Task 3 API assigns a score, pool, peer percentile, confidence, or release decision for a security.

## Immutable content-addressed store

`FormalFeatureBundleStore(root)` resolves and owns only:

```text
<root>/data/formal/features/<bundle_hash>.json
<root>/data/formal/features/<bundle_hash>.manifest.json
```

`FormalStoredFeatureBundle` is an exact immutable receipt with absolute canonical paths plus lowercase `bundle_hash` and `manifest_hash`; direct construction/low-level mutation is revalidated by `read_verified`.

The bundle file is exactly `bundle.canonical_bytes()`. The canonical manifest file has exactly these immutable header fields, with no path or clock field:

```text
schema_version = 1
kind = "formal_feature_bundle"
bundle_hash
input_hash
security_id
as_of_utc
template_id
registry_manifest_hash
feature_registry_hash
bundle_schema_version
contract_version
```

`manifest_hash` is SHA-256 of the complete canonical manifest bytes and is returned in the receipt; it is not self-embedded, avoiding another hash fixed point. On every read, parse/canonicalize the manifest, hash its actual bytes, recompute/reparse the bundle, recompute its hash, and require every manifest header to exactly equal the typed bundle and every receipt field/path to be the canonical derived value.

Writing is fail-closed and no-clobber:

1. validate bundle and derive paths exclusively from `bundle_hash` below the resolved root;
2. reject absolute/relative receipt substitution, wrong filenames, path traversal, symlinks/junctions, external parents, and `.part` files as trust inputs;
3. take a per-bundle filesystem lock using exclusive creation; an already-held or stale lock fails safely rather than overwriting another writer;
4. write same-directory uniquely named `.part` bytes, flush, `fsync`, reread and hash/canonical-validate them, then atomically replace final targets while holding the lock;
5. write bundle before manifest, because a verified manifest is the completion marker; and
6. when a final target exists, accept only byte-identical content with its exact expected hash; otherwise raise a deterministic conflict without overwriting it.

If the bundle is correct but its manifest is absent after a crash, a later identical write may validate the bundle then finish only the manifest. A partial bundle, orphan `.part`, manifest-first state, mismatched bundle/manifest pair, tampered bytes, forged receipt, or any write/flush/replace failure is never readable through `read_verified` and must leave no trusted result. Concurrent identical writers are idempotent; conflicting writers do not silently replace a prior artifact.

## Required TDD proof

Start RED because both modules are absent. Add focused tests for:

1. signature false/exception, duplicate/noncanonical JSON, wrong role/schema, no default registry, direct/forged/mutated/equality-spoofed registry, root-child role/hash/template binding, and incomplete fixture false eligibility;
2. all formula wire variants and exact-key failures, including executable strings/callables, malformed children, zero/bool/negative `cagr` intervals, duplicates, and nonfinite values;
3. exact sealed fact-to-evidence copying of every field, especially refresh generation, plus fact/evidence mutation and legacy/generic source rejection;
4. all feature value status/value/reason/evidence combinations, ordering/duplicates, canonical bundle roundtrip/tamper, SH/SZ/BJ/UTC/hash checks, and no scoring side effects;
5. content-addressed write/read roundtrip, tampered bundle/manifest, header mismatch, path escape/symlink/forged receipt, idempotence, existing conflict with no overwrite, orphan/partial states, failure cleanup, and concurrent same-hash behavior; and
6. plan-required regression:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_formal_feature_contract tests.test_formal_feature_store tests.test_feature_contract tests.test_snapshot_store -v
```

Run compilation and `git diff --check` before commit. Record exact RED/GREEN output in ignored `task-3-report.md`; no data/state artifact may be staged.
