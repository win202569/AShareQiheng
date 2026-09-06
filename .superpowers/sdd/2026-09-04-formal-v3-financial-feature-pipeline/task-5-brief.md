# V6 Task 5 binding brief — formal persistence, migration, and task ownership

Plan: `docs/superpowers/plans/2026-09-04-formal-v3-financial-feature-pipeline.md`,
Task 5. Tasks 1–4 are accepted through `1eef9a6`.

This brief resolves Task 5 plan/API gaps before implementation. It creates a
strict V6 persistence boundary only. It does not fetch data, parse raw source
documents, create production registries, score, assign a pool, write reports,
or implement Task 5A's typed durable feature-bundle reader.

## Scope and commit boundary

Modify exactly:

1. `ashare_pipeline/state_store.py`
2. `tests/test_state_store.py`

Do not change Tasks 1–4, legacy financial feature code, plans, data,
SQLite/WAL/SHM, or any other tracked file. Do not make network calls. Record
RED/GREEN only in ignored `task-5-report.md`; never stage briefs, reports,
ledgers, data, SQLite/WAL/SHM, or progress files. Initial commit subject:

```text
feat: persist formal v3 facts and features
```

## Compatibility and trust posture

`SCHEMA_VERSION` becomes exactly `6`. Existing V2–V5 tables and APIs retain
their behavior and are never read as formal source evidence. In particular V6
must not query or join legacy `financial_fact`, `feature_set`, `feature_value`,
`source_snapshot`, `job`, `score_run`, or `score_item` to prove formal facts.

Use the Task 1–4 ordinary Python threat model: exact public types, sealed
upstream records, defensive detached snapshots, canonical JSON, canonical UTC,
and deterministic order. General closure-cell reflection remains the accepted
language limitation; ordinary `object.__new__`, public mutation, custom
equality, Mapping/list/string subclasses, malformed SQL rows, insertion order,
and TOCTOU must fail closed.

Every Task 2 fact must be `type(fact) is FormalFinancialFact` and be consumed
through `fact.to_dict()` before reading fields. Every quarter must be exact
`FormalQuarterFact` and be consumed through `.to_dict()`. Every bundle must be
exact `FormalFeatureBundle` and pass `.to_dict()` plus `.canonical_bytes()`.
Every registry root must be exact `FormalRegistryManifest`; every child is the
raw exact `VerifiedRegistryBlob` envelope which is reverified rather than
treated as trusted merely because it has that type.

Extend `StateStore.__init__` compatibly with optional injected
`registry_signature_verifier` and `formal_feature_bundle_store`. Existing
callers supplying only a database path or formal snapshot store remain valid.
Formal registry reads/writes require the verifier; formal bundle writes require
the feature bundle store; a missing dependency raises `ValueError` rather than
accepting a weaker path. The feature store is used only through its public
`read_verified(stored)` method. Never fabricate a `FormalStoredFeatureBundle`,
call private helpers, use closure reflection, or rewrite a bundle to create a
receipt.

## V6 migration and exact DDL

Add `_V6_TABLE_DDL`, `_V6_INDEX_DDL`, and `_apply_v6_migration`. DDL must be
included in the existing exact normalized-schema checks. `initialize()` must
support only continuous ledgers `{2}`, `{2,3}`, `{2,3,4}`, `{2,3,4,5}`, and
`{2,3,4,5,6}`; all earlier valid paths reach V6 under the existing one
immediate transaction. A V6 table/index before ledger version 6, a partial V6
set, any skipped/future version, or a same-name different DDL is an error and
rolls back. On a complete V6 reopen, revalidate V2–V6 DDL without changing any
applied timestamp. Preserve every legacy row byte-for-byte in behavior.

Add these V6 tables (all JSON is canonical UTF-8 JSON text unless noted):

```text
formal_financial_fact:
  id PRIMARY KEY; all Task2 FormalFinancialFact wire fields; source_snapshot_id
  FK formal_source_snapshot; nullable period_start,
  effective_time_evidence_hash, source_updated_at_utc, source_producing_task_id.

formal_quarter_fact:
  id PRIMARY KEY; all FormalQuarterFact wire scientific fields;
  component_fact_ids_json, evidence_json, derivation_version, created_at_utc.

formal_feature_set:
  id PRIMARY KEY (canonical bundle hash); schema_version, contract_version,
  security_id, as_of_utc, template_id, registry_manifest_hash,
  feature_registry_hash, input_hash UNIQUE, history_endpoints_json,
  comparable_quarter_keys_json, blockers_json, bundle_hash,
  bundle_manifest_hash, bundle_path, manifest_path, created_at_utc.

formal_feature_value:
  feature_set_id FK, slot_id, value, unit, status, formula_version,
  evidence_json, missing_reason, PRIMARY KEY(feature_set_id,slot_id).

formal_context_fact:
  exactly the plan's empty V6 table only; no Task5 put/list API.

formal_registry_manifest:
  manifest_hash PRIMARY KEY; purpose, approval_id, canonical_json BLOB,
  signature, key_id, the nine root role hashes, created_at_utc.

formal_registry_blob:
  registry_hash PRIMARY KEY; registry_role, canonical_json BLOB, signature,
  key_id, approval_id, declared_registry_manifest_hash, binding_signature,
  binding_key_id, created_at_utc.

formal_source_circuit:
  source PRIMARY KEY, state, failure_count, reason_json, opened_at_utc,
  retry_after_utc, updated_at_utc.
```

The three binding fields in `formal_registry_blob` are mandatory Task 1
protocol fields. One hash maps to exactly one immutable root binding; trying to
reuse equal child canonical bytes under another root is a conflict, not an
overwrite or "latest" selection. Add only indexes required for deterministic
formal fact/security lookup, formal quarter/security lookup, formal feature
header lookup, and formal task/circuit operations; freeze names and column
order in tests through exact DDL validation.

`FormalFinancialFact.id` deliberately excludes `created_at_utc`. On an
identical scientific fact replay, preserve the already stored first audit
creation time and treat every other wire field as the content identity. A
different scientific/lineage field under an existing ID is a conflict. Quarter
creation time likewise belongs only to the first database insertion, because
the Task4 quarter wire has no creation field. Every insertion batch is one
transaction: a single invalid or conflicting record leaves no partial rows.

## Formal source, fact, and quarter persistence

`insert_formal_financial_facts(facts)` and
`list_formal_financial_facts(*, security_id: str | None = None)` use only V5
`formal_source_snapshot`, `formal_collection_task`, and
`formal_task_snapshot_receipt` as the source boundary. The list result is a
deterministic tuple sorted by canonical scientific identity and returns fresh
sealed facts; it revalidates every stored row and its raw snapshot lineage.

For each fact insertion and each list/read, use the existing
`_formal_verified_snapshot_ref_from_connection` chain to re-read verified raw
bytes, manifest, canonical request fingerprint, verification JSON, source
receipt, producer task and generation. Then compare every claimed source
lineage value to the revalidated reference: source security ID and requested
period, content hash, refresh generation, producing task ID, parser ID/version,
mapping version, publication timestamp/precision, effective timestamp/evidence
hash, source update, and capture time. A legacy snapshot ID, missing/corrupt
receipt, wrong task kind, substituted request/security/period, parser/version,
generation, or raw/manifest mismatch rejects the entire batch.

This layer verifies formal record provenance, not a new reparse of a raw
financial value. `FormalFinancialFact.create()` is publicly available and Task
5 has neither a signed mapping runtime nor parser callback. Re-executing raw
parsing/field mapping is Task 6 responsibility; Task5 must never claim it did
so or invent a mapping/default. It does reject any claim inconsistent with the
already verified snapshot and Task2 sealed wire.

`insert_formal_quarter_facts(quarters)` and
`list_formal_quarter_facts(*, security_id: str | None = None)` are append-only
and deterministic. For every quarter, retrieve exactly its sorted component
fact IDs from `formal_financial_fact`, rebuild/revalidate those facts and their
snapshots, call `derive_comparable_quarters(component_facts)`, and require a
derived quarter whose full `.to_dict()` is byte-for-byte equal to the submitted
wire. Do not select newest facts from the database and do not merely validate a
recomputed quarter ID: historical reports may legitimately have older source
lineage, while a canonical standalone quarter wire cannot prove its arithmetic.
Any missing component, altered evidence/value/unit/basis/parser/mapping, wrong
operand set, or no exact rederivation rejects. An existing ID is idempotent
only with equal stored scientific/evidence JSON; changed source components get
a distinct quarter ID and coexist for audit.

## Registry persistence

Provide `put_formal_registry_blob(blob)` / `get_formal_registry_blob(hash)`
and `put_formal_registry_manifest(manifest)` /
`get_formal_registry_manifest(hash)`. All require the injected verifier when a
record is read or written. A get of a nonexistent row may return `None`; it may
not fabricate a trusted object.

Blob writes snapshot exact primitive fields, require canonical bytes and their
SHA-256, verify both the child signature and the canonical binding signature
over exactly:

```json
{"child_sha256":"...","registry_manifest_hash":"...","registry_role":"..."}
```

with the injected verifier, and require the child wire to declare the same
role. Existing hash rows are accepted only when every stored envelope field is
identical. Blob reads revalidate that raw envelope before returning the public
raw `VerifiedRegistryBlob`; it is intentionally not promoted to a trusted
bundle by the StateStore.

Manifest writes snapshot/closure-validate the exact sealed manifest, re-load
its signed canonical bytes with `FormalRegistryManifest.from_signed_bytes`,
compare every public field, then use an in-transaction raw repository adapter
and `FormalRegistryBundleLoader` to verify all nine persisted child envelopes,
roles, hashes, independent bindings and approval consistency before inserting
the root. Any missing/wrong child or verifier/canonical/signature/binding/
approval mismatch rolls back. A manifest replay is idempotent only if every
stored field is identical. Manifest reads reconstruct via
`FormalRegistryManifest.from_signed_bytes`, compare all stored columns to the
reconstructed sealed root, and return that fresh sealed root; the Task1 loader
will reverify it and every child again on bundle load.

## Formal feature-bundle audit persistence

Define exactly:

```python
put_formal_feature_bundle(
    self, bundle: FormalFeatureBundle, stored: FormalStoredFeatureBundle
) -> tuple[str, bool]
get_formal_feature_bundle_row(self, input_hash: str) -> dict[str, object] | None
```

The getter returns only detached canonical database metadata/value rows for an
exact input hash; it never constructs a trusted `FormalFeatureBundle` from SQL.
Blocked and missing bundles are valid audit records but later Task5A decides
whether a bundle is usable.

Before writing, require exact sealed bundle snapshots and call the injected
store's `read_verified(stored)`. Its returned bundle must have identical
canonical bytes to the supplied bundle; snapshot the live receipt fields only
after that verification. This is the sole receipt/path authority. Require its
bundle hash, manifest hash, deterministic paths, and bytes to agree with the
bundle and receipt; do not use a string-prefix path check as a substitute.

Load the persisted registry root/children through the formal loader, require
the root hash and feature child hash to equal the bundle header, construct the
signed feature child from that verified envelope, and ensure every persisted
slot/header/value is a signed applicable slot with matching unit and formula
version. For every feature evidence reference, retrieve the matching formal
fact, revalidate the fact/source lineage, and require exact equality to
`FormalEvidenceRef.from_formal_fact(fact)`. Its visibility follows Task4:
published/effective/source-update must not exceed the bundle cutoff while a
late capture remains allowed. No partial or legacy evidence is accepted.

`input_hash` is globally unique. An existing input hash is idempotent only when
every feature-set header, every canonical value/evidence row, receipt paths,
bundle hash and manifest hash match exactly; otherwise fail, never overwrite.
No security/as-of/template/root uniqueness is added, because changed formal
lineage must create a separate immutable input. Store and return the canonical
bundle hash as `formal_feature_set.id`.

Task4's input hash contains extraction issues and all visible candidates. The
V6 tables do not persist a full input manifest or extraction issues, so Task5A
must not pretend it can recompute historical Task4 input hashes with
`issues=()`. Durable receipt reconstruction/verified read is explicitly
deferred to Task5A with a public FeatureBundleStore recovery API; do not bypass
the Task3 receipt seal in Task5.

## V5 task ownership reuse and source circuits

Do not replace V5 `formal_collection_task`, dependencies, receipts, or their
state model. Reuse the existing exact APIs and semantics for enqueue, lease,
renew, complete, fail, supersede and dependency resolution. Existing generic
payload mappings (including `{}`) remain valid; Task6 owns typed worker payload
validation. `before_generation` in `supersede_formal_tasks` continues to mean
"different from current generation", not lexical age.

Keep V5 states exactly `pending`, `leased`, `verified`, `retryable_failed`,
`terminal_failed`, and `superseded`; retain deterministic ready/retry/expired
lease semantics and compare-and-set owner checks. Add only these narrow
hardening changes:

1. `put_formal_snapshot_for_leased_task` must resample canonical current time
   immediately before an identical-receipt return, before a new insert, and
   after final graph validation. If validation crosses lease expiry, reject and
   roll back; do not return/insert under a stale sampled owner.
2. `_formal_task_snapshot_receipt_from_connection` must reject a receipt whose
   producer task is not one of the formal source-fetch kinds.
3. Lease readiness and its CAS update must treat a missing dependency parent
   in externally corrupted storage as not verified rather than letting an
   `INNER JOIN` hide it. Valid generic verified parents remain valid.

Add deterministic `list_formal_tasks(*, kinds: Sequence[str] | None = None,
statuses: Sequence[str] | None = None) -> list[dict[str, object]]`. Absent
filters mean all; explicitly empty filters return `[]`; kinds/statuses are exact
canonical strings. Kinds are exact nonempty trimmed/control-free strings, not a
new finite runtime-kind allowlist, because V5 formal tasks deliberately retain
generic discoverability; statuses are the closed six-state set. Return the existing detached task public projection
with sorted prerequisites in `(created_at, id)` order from one consistent read
transaction. It never consults legacy `job`.

Add `get_formal_source_circuit(source)` and `set_formal_source_circuit(...)`.
Use only states `closed` and `open`. `closed` requires zero failure count, an
empty canonical reason mapping, and null opened/retry times. `open` requires a
positive non-bool integer failure count, nonempty finite canonical reason
mapping, canonical UTC opened/retry timestamps with retry not before opened.
An equal full replay is a true no-op, including unchanged `updated_at`; a
changed record gets one fresh canonical update time. Getter revalidates stored
canonical JSON/types and returns a detached mapping; it returns `None` if no
row. A source's circuit change never changes another source or any task.
Circuit policy remains worker-owned; SQL leasing never silently blocks a task
based on a circuit row.

## Required TDD proof

Begin RED from absent V6 APIs/DDL and record it in the ignored report. Tests
must cover at least:

1. all initialize entrances to V6, exact V2–V6 ledger/table/index validation,
   partial/tampered V6 rollback, and unchanged legacy rows;
2. exact source fact lineage checks field-by-field, legacy/missing/tampered raw
   snapshot/receipt/task rejection, batch rollback, replay/created-time
   behavior and deterministic sealed listing;
3. quarter rederivation, forged canonical-but-wrong arithmetic/evidence,
   historic lineage coexistence, component ordering and tampered database rows;
4. all nine child/root registry signature, hash, role, binding and approval
   cases across restart; missing verifier fails closed; child hash/root-binding
   conflict; no forged trusted root;
5. live verified bundle receipt requirements, root/feature slot/evidence
   checks, cutoff visibility, path/manifest/hash/header/value conflict,
   idempotent input-hash replay, and getter as non-typed metadata;
6. receipt expiry crossing/replay fencing, corrupted missing dependency parent,
   wrong source task receipt, task listing filters/order/detachment, and
   source-circuit open/closed/idempotence/isolation; and
7. required regression:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_state_store tests.test_formal_financial_schema tests.test_formal_feature_contract tests.test_formal_feature_store -v
```

Run compilation and `git diff --check` before commit. Report unresolved public
API impossibilities rather than inventing defaults or expanding the file scope.
