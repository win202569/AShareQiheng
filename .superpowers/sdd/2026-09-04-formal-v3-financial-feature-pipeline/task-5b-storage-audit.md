# Task 5B storage-boundary audit

Date: 2026-09-05.  Scope: read-only preflight of Task 5B against the current
V6 StateStore.  No product code, tests, database, network resource, or commit
was changed.

## Decision

`formal_context_fact` already has enough physical columns for a safe,
append-only `FormalContextFact` persistence boundary.  It must not be treated
as sufficient by itself: no typed context model or `put_formal_context_facts` /
`list_formal_context_facts` API exists yet, and the table has no constraints
that make the Task 5B invariants true on its own.  The Task 5B API must impose
those invariants transactionally and revalidate them on every read.

The main design ruling is that StateStore may use the persisted root only to
prove a signed root and its immutable child envelopes.  The root manifest is a
hash-pinning envelope, not a declaration of context kinds, source request
shapes, parser configuration, or mappings.  Therefore either

1. `FormalContextFact` construction / the caller-owned verified registry
   runtime must prove that the kind and source configuration are declared by
   the verified bundle, and StateStore must re-check the pinned root; or
2. a narrow, public, injected context-registry validation interface must be
   added to StateStore.

StateStore cannot truthfully satisfy the plan's “context kind declared in the
persisted root registry manifest” requirement from a `FormalContextFact` plus
the current `FormalRegistryManifest` alone.  It must not invent a static
allowlist or parse an untyped child blob as a substitute.  This is the only
material public-API/routing ruling found in the storage boundary.

## Plan requirements reviewed

Task 5B creates typed market, calendar, security-state, industry, regulatory,
event, and consensus facts.  The persistence part requires:

- `StateStore.put_formal_context_facts` and
  `StateStore.list_formal_context_facts` over the V6 table that Task 5 created;
- a verified formal snapshot and, for a task-produced snapshot, its immutable
  raw-fetch receipt;
- exact context identity/as-of/source/content/parser/mapping/root lineage;
- `no_coverage` only when a verified consensus response explicitly says there
  is no valid coverage;
- all versions for distinct refresh generations retained;
- visible-version selection using V5 order: published descending,
  source-updated descending with null last, captured descending, content hash
  ascending; and
- no legacy/third-party fallback, inferred consensus, or unverified/tampered
  source or registry data.

The selected version belongs in `FormalContextRepository`, not in a hidden
“latest” StateStore query.  The StateStore list method should return
deterministically ordered, fresh sealed facts (optionally narrowed by exact
logical-key filters) and retain history; the repository can then apply
`FormalContextVersionView` and report the selected fact's generation, snapshot
ID, and content hash to V7/V8.

## Fields that must be persisted and revalidated

The current table has a direct column for every durable fact field needed by
the planned `FormalContextFact` plus database audit creation time:

| Purpose | Required fields | Current carrier |
|---|---|---|
| Stable scientific/context identity | `id`, `context_kind`, `scope_key`, nullable `security_id`, `as_of_utc` | table columns |
| Typed payload and coverage assertion | canonical `value_json`, `no_coverage` | table columns |
| Point-in-time visibility | `published_at_utc`, `effective_at_utc`, nullable `source_updated_at_utc`, `captured_at_utc` | table columns |
| Immutable source version | `refresh_generation`, `source_snapshot_id`, `source_content_sha256` | table columns plus snapshot row |
| Parser/mapping lineage | `parser_id`, `parser_version`, `mapping_version` | table columns plus snapshot row |
| Registry/evidence lineage | `registry_manifest_hash`, canonical `evidence_json` | table columns; root/blob tables |
| Database insertion audit | first `created_at_utc` only | table column |

`value_json` and `evidence_json` must be canonical UTF-8 JSON, decoded to
detached primitive structures, and compared through the exact sealed
`FormalContextFact.to_dict()` wire—not through a mutable Mapping subclass or
Python object equality.  Store `no_coverage` only as integer 0/1 after exact
bool validation, and enforce the semantic consensus-only / explicit-verified
no-valid-coverage rule in the typed schema/registry validator.  A transport
failure, absent source, or time-unverifiable result is not a no-coverage fact.

`created_at_utc` is database audit time, not part of content identity.  On an
identical replay preserve the first value; an existing ID with any other wire
field different is a conflict.  Because the planned type does not expose a
creation timestamp, StateStore should set and validate it independently, as
the quarter implementation already does.

### Fields deliberately reachable rather than duplicated

The table does not duplicate `source_producing_task_id`, source manifest hash,
source request fingerprint/source/dataset, published precision,
effective-time-evidence hash, or receipt generation.  This is safe only if
each put and list follows `source_snapshot_id` and calls the existing
`_formal_verified_snapshot_ref_from_connection` chain.  That chain:

1. reads the persisted raw content and manifest via
   `FormalSnapshotStore.read_verified_raw`;
2. reconstructs and validates `OfficialFetch` / `EvidenceVerification`, then
   compares every SQL snapshot field to the validated projection;
3. validates the canonical request fingerprint and verification JSON; and
4. for a produced snapshot, requires exactly one matching receipt, one source
   snapshot for its producer, a present source-fetch task, and equal task /
   receipt / snapshot refresh generation.

The fact API must compare its own snapshot ID, content hash, refresh
generation, parser ID/version, mapping version, all publication/effective/
source-update/capture timestamps, and source request identity required by the
typed context request against that fresh reference.  In particular, it should
require a non-bootstrap producer to be a `formal_context` task, not merely any
of the current generic source fetch kinds (`formal_statement`,
`formal_context`, `formal_universe_source`); otherwise a valid statement or
universe receipt could be relabelled as context.  A permitted bootstrap
exception, if truly required by the context design, must be explicit and
independently bound to its signed calendar bootstrap contract—never implicit.

No new duplicate columns are required for this chain.  Adding them without
comparing them to the revalidated source would only create two tamper targets.

## Append-only versions and selection

The primary key `id` supports immutable individual facts, and it is correct
that there is no uniqueness rule on security/as-of/template-like context scope:
an official correction must coexist with an older lineage.  There is also no
table-level logical-key/refresh-generation uniqueness rule.  Thus the put API
must explicitly query a context's logical key with NULL-safe `security_id IS
?` semantics and reject a non-identical reuse of the same declared identity /
refresh generation before inserting.  It must not issue UPDATE/REPLACE.

For reads, filter first by the exact logical key—at minimum kind, scope,
security (NULL-safe), as-of, and registry root—then revalidate every candidate
before the repository ranks it.  Visibility/ranking must be deterministic:

```
published_at_utc DESC,
source_updated_at_utc DESC (NULL last),
captured_at_utc DESC,
source_content_sha256 ASC
```

If the first row in this order cannot be normalized or cannot prove its source
lineage, fail closed; do not silently skip it and promote an older candidate.
This preserves audit history while preventing an attacker from turning a
corrupt newer version into an older fallback.

The existing V6 context DDL has no context lookup index.  That is a performance
gap, not a correctness blocker.  An optional deterministic index would cover
the logical filter and ranking columns.  However V6 DDL is currently frozen in
exact normalized-schema tests, so adding an index changes the V6 schema
contract and needs an explicit migration/version decision.  Task 5B can remain
correct without it; do not silently create an untracked index at runtime.

## Transaction, concurrency, and tamper requirements

- Validate input type with `type(fact) is FormalContextFact`; consume a sealed
  snapshot via `.to_dict()` before field access.  Reject empty/noncanonical
  collections and duplicate submitted IDs/logical-generation keys.
- Run the whole batch in one `BEGIN IMMEDIATE` transaction.  Revalidate source
  files, source row, receipt/task graph, and registry root inside that
  transaction; then check existing conflicts and insert.  Re-read every
  inserted row through the same reconstruction path before commit.  Any bad
  fact, race, SQLite integrity failure, or revalidation failure rolls back the
  entire batch.
- For every list/read use a read transaction, rebuild an exact sealed fact from
  canonical database fields, re-run source and root validation, and return a
  fresh deterministic tuple/list.  Never return SQL dictionaries as trusted
  context facts, cache a past verification result, or accept stored JSON merely
  because SQLite returned it.
- Re-load the registry root through existing verifier-backed manifest/blob
  APIs.  Check the fact root hash exactly; let the typed context validation
  prove the signed configuration/kind relationship noted in the ruling above.
  Missing verifier, root, child, signature, binding, approval, or canonical
  bytes is an error, not a weaker read path.
- Reject malformed SQL rows: noncanonical JSON, wrong primitive types,
  noncanonical UTC, invalid canonical security ID, invalid SHA-256, non-0/1
  coverage, foreign/missing snapshot, snapshot raw/manifest mismatch, absent
  receipt, wrong producer task/kind/generation, altered root hash, or any fact
  wire/source mismatch.
- Do not require the producer task already be `verified`: Task 6 writes a
  context fact after receipt persistence and before task completion.  The
  receipt/task ownership rules and worker lease checks remain responsible for
  that transition; StateStore must still verify the immutable receipt graph.

## Existing DDL verdict and minimal gaps

**Can carry the data:** yes.  All planned persisted context fields are
present, foreign-key linkage to `formal_source_snapshot` exists, and the
existing formal source snapshot/receipt/task graph plus formal root/blob tables
can provide the missing provenance at verification time.

**Must be added in Task 5B:** the typed schema and two StateStore APIs; exact
canonical encode/decode/rebuild helpers; append-only replay/conflict handling;
source/ref/receipt/task/root revalidation on both put and list; and repository
level visible-version selection.  Current `tests/test_state_store.py` only
mentions `formal_context` as a generic task kind and checks the table's
existence—there is no persistence/tamper coverage to reuse.

**Minimum unresolved specification/API gap:** a root manifest alone does not
declare a permitted context kind or source/parser/mapping configuration.  The
implementation needs an explicit trusted validation boundary supplied by the
new context schema/repository/verified bundle runtime, or an injected public
validator.  Until that is settled, `put_formal_context_facts` must fail closed
rather than accept a string kind merely because the root exists.

**Not necessary to add physically:** producer task ID, manifest hash, receipt
generation, source request fields, or a “latest” flag.  Each is already
reachable through the verified snapshot chain; duplicating it would be weaker
unless checked again.  A context version lookup index is advisable only after a
deliberate V6 schema/migration ruling.

## Tests required before implementation

1. Exact type/sealed-wire/canonical JSON and UTC checks; malicious Mapping,
   list/string subclasses, altered DB JSON, bool-as-int coverage, and detached
   return values.
2. Batch atomicity and replay: first creation time remains fixed; equal replay
   is no-op; changed same-ID or same logical-generation lineage conflicts;
   distinct valid generations coexist.
3. Source proof failures: legacy ID, missing/altered raw content or manifest,
   verification JSON/fingerprint mismatch, missing/corrupt receipt, wrong task
   kind, producer/generation mismatch, and relabelled statement/universe
   snapshot.
4. Root/configuration proof: missing verifier/root/blob, tampered root or
   binding, fact root mismatch, undeclared kind, source/dataset/parser/mapping
   mismatch, and no synthetic default registry/configuration.
5. `no_coverage` only for explicit verified consensus; failed, missing, future,
   or unverified responses remain pending/error rather than coverage-free.
6. Repository selection keeps both audit versions and implements the stated
   four-key V5 ordering; null source-update is last; invalid selected newest
   row fails rather than falling back.
7. Concurrent/restart behavior: two writers contend on identical/conflicting
   identity, no partial rows leak, and every later read rechecks raw files,
   snapshot/receipt/task lineage, root envelopes, and database columns.
