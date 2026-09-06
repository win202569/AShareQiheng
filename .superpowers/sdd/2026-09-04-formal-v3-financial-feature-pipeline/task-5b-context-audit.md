# Task 5B context preflight audit

Date: 2026-09-05.  Scope was read-only except for this requested report.  No
network, source, test, database, or tracked-code changes were made.

## Inputs read in full

- `docs/superpowers/plans/2026-09-04-formal-v3-financial-feature-pipeline.md`,
  Task 5B (§1032–1240).
- `ashare_pipeline/formal_sources.py` and `tests/test_formal_sources.py`.
- `ashare_pipeline/formal_time.py` and `tests/test_formal_time.py`.
- `ashare_pipeline/formal_financial_schema.py` (the existing sealed-record and
  snapshot-lineage implementation used as the closest Context-model precedent).
- Relevant public persistence/evidence/root-boundary code in
  `formal_evidence.py`, `formal_registry_manifest.py`,
  `formal_snapshot_repository.py`, and `state_store.py`.

Current head is `e2b85fe`; the worktree was clean at inspection.  V6 already
has the plan's empty `formal_context_fact` table (with an additional existing
`evidence_json` column) but has no typed Context API.

## Existing public APIs that are safe to reuse

### Root and source registry

Use `FormalRegistryBundleLoader(store, verifier).load(root_hash)` every time a
Context resolver/repository needs authorization.  The loader re-reads the raw
root and all nine raw child envelopes, validates canonical bytes and SHA-256,
child and binding signatures, role/hash/root binding, and official approval
consistency.  Its resulting exact `VerifiedRegistryBundle` provides only:

- `bundle.require_official()` for the release gate;
- `bundle.blob(role)` for an exact named raw child; and
- `bundle.manifest` for the signed root/member hash fields.

`VerifiedRegistryBlob` is intentionally a raw, publicly constructible
envelope.  It is not an authority by itself.  Do not accept an injected child,
use `bundle.blobs` directly, or treat a stored `FormalRegistryManifest` as
enough; reload via the bundle loader.

`SignedSourceRegistry.from_signed_bytes(blob.canonical_json, blob.signature,
blob.key_id, verifier)` is the safe source-child loader.  It verifies canonical
JSON and the child signature and returns a closure-sealed registry.
`SignedSourceRegistry.select(OfficialRequest)` is safe only after that load;
it returns the unique signed `SourceAdapterConfig` for source/dataset and
exchange scope.  `SourceAdapterConfig` already fixes endpoint, parser ID and
version, mapping version, exchange scope, request template, retry semantics,
and an optional exact `CalendarSelector`.  It supplies no context-kind,
context-value, or context-scope mapping.

### Source collection, snapshots, and date-only evidence

`FormalOfficialSourceAdapter` may be reused unchanged.  Construct it only from
the reloaded signed source registry, the exact root/source-child hash, root
hash, authoritative `SourcePolicy`, registered parser mapping, and the Context
repository's effective-time resolver.  It handles transport, parser identity,
URL policy, signed config selection, immutable response/document snapshots,
and replay.

For a date-only config it enforces, before transport, an *exact*
`VerifiedCalendarBinding` with matching selector hash, exchange, adapter
freeze, root hash, and a canonical UUID prerequisite task ID.  It calls
`EffectiveTimeResolver.next_exchange_close`, writes the selected calendar
manifest to `OfficialFetch.effective_time_evidence_hash`, and then calls
`verify_official_fetch`.  Replay (`parse_verified_snapshot`) repeats the same
checks and makes no transport request.  Timestamp configs reject a binding.
Bootstrap `trading_calendar` is the narrow signed timestamp-only exception.

`FormalSnapshotRepository.get_verified_by_manifest()` and
`read_verified_raw()` are the public snapshot provenance boundary.  The former
uses StateStore's receipt-aware verified-reference chain; the latter compares
all reference fields with a freshly verified manifest reference and re-reads
verified bytes.  Use these, rather than trusting a caller's
`OfficialSnapshotRef` or `StateStore.get_formal_snapshot()`.

### Time and version order

Reuse `formal_time.is_visible_at(effective, as_of)` and
`formal_version_sort_key(row)` for the stated ordering: published descending,
source-update descending (null last), captured descending, content-hash
ascending.  `resolve_effective_at` is deliberately only a pure syntax/15:00
helper; it proves neither calendar selection nor source lineage.  Only the
repository-backed effective-time resolver may feed it for a date-only source.

### Existing V6 root/snapshot support

`StateStore.get_formal_registry_manifest/blob` are the public raw repository
methods required by `FormalRegistryBundleLoader`; both revalidate their stored
record before returning.  The new Context StateStore methods may reuse internal
`_formal_verified_snapshot_ref_from_connection` while inside one transaction,
as the existing formal-fact persistence does.  A Context repository outside
StateStore should use `FormalSnapshotRepository`, not StateStore private
methods.

The Task 2 record design is the right security pattern for `FormalContextFact`:
an exact sealed type, factory/from-wire validation, `to_dict()` returning fresh
JSON-native data, a canonical identity excluding audit creation time, and
field-type-aware mutation sealing.  `OfficialSnapshotRef` and
`VerifiedCalendarBinding` themselves are frozen records but are not proof of
repository verification; revalidation remains mandatory.

## Required pre-implementation rulings / missing contracts

These are material contract gaps, not implementation details.  Do not infer
them from fixture names, datasets, registry roles, security-code prefixes, or
calendar weekdays.

1. **Signed Context request/configuration wire.**  The source child describes
   how to fetch a dataset, but it does not name `context_kind`, allowed
   `scope_key`/security/as-of shape, which root child authorizes the semantic
   mapping, how to normalize the parsed rows into Context `value`, or an
   authoritative upstream generation.  `SignedContextRequestResolver` cannot
   safely map a public `context_kind` to a SourceAdapterConfig without a new,
   canonical, signed Context request descriptor.  Minimal decision: define a
   `formal-context-registry-v1` child wire (or an exactly named section of an
   existing signed role) with one unique descriptor per `(context_kind,
   scope_key, security-scope, as_of rule)`.  Each descriptor must carry source
   config identity `(source,dataset,parser_id,parser_version,mapping_version,
   exchange_scope)`, exact OfficialRequest derivation/period rule, exact
   permitted root role/hash set, normalization schema/version, upstream
   generation, and optional CalendarSelector.  Its canonical hash must be in
   `relevant_registry_hashes`; no default descriptor or dataset-to-kind lookup.

2. **Role ownership for consensus is not represented by the root.**  The nine
   current roles are source/mapping/feature/scoring/industry/cyclic/redline/
   status/event; there is no `consensus` role.  The descriptor decision must
   explicitly designate which signed child authorizes consensus semantics (or
   add a role, which changes Task 1/V6 root protocol and is not minimal).
   Recommended minimum: place all Context descriptors in the existing signed
   `scoring` child and bind it in `relevant_registry_hashes`; its config must
   explicitly state any referenced industry/status/event child hashes.  This
   gives consensus a signed owner without widening the root schema.

3. **Trading-calendar exchange identity.**  `FormalContextFact` and the V6
   table have no `exchange` column.  A global calendar has `security_id=None`,
   and the existing `CalendarSelector.scope_key` is not exchange-specific
   (the source tests use the same `disclosure` scope for SZ).  Selecting only
   `(kind,scope_key,security_id,as_of,root)` therefore cannot distinguish SH,
   SZ, and BJ calendars.  Do not alter accepted V6 DDL casually.  Minimal
   compatible decision: require canonical `value["exchange"]` for every
   `trading_calendar` Context fact; require the Context fact ID to cover the
   canonical value and filter it by exact exchange only in
   `resolve_verified_calendar_binding`.  The calendar value schema must also
   contain a complete, ordered date-to-trading-day representation and the
   exchange close used by the resolver.  The repository must reject duplicate
   visible candidates for the selector/exchange rather than choose by insertion
   order.  An alternative is an explicit schema migration adding `exchange`,
   but that is not Task 5B's minimal path and changes the accepted V6 DDL.

4. **Source-update cutoff.**  Task 4's accepted point-in-time rule excludes
   source updates after the freeze while allowing late capture.  Task 5B's plan
   names future published/effective checks but omits source-updated filtering.
   Without an explicit `source_updated_at_utc <= as_of_utc` rule (when nonnull),
   a correction published/effective before freeze but updated after it can win
   `formal_version_sort_key` and leak future knowledge.  Recommended ruling:
   insert requires `published_at_utc`, `effective_at_utc`, and nonnull
   `source_updated_at_utc` not after Context as-of; repository repeats it when
   reading.  `captured_at_utc` stays intentionally unrestricted, so late
   capture remains valid.  If the product wants a different source-revision
   rule, it must say so explicitly and test the look-ahead counterexample.

5. **Context value contracts and no-coverage proof.**  The plan narrates
   required fields but supplies no closed wire.  Define exact per-kind JSON
   object keys, primitive types, finite-number/canonical-date requirements,
   and identity coverage before implementation.  Minimum requirements include
   calendar exchange/session/close data; market exchange-trade state, volume,
   turnover, effective-trade flag, valid close/date, stale trading days;
   security status; SW2021 industry/source-version/effective-date/full-map
   hash; source-backed regulatory/event entries; and consensus coverage state.
   `no_coverage=True` must be legal only for a signed `consensus_snapshot`
   normalization that explicitly states `coverage_status=no_valid_coverage`;
   it cannot be derived from empty, failed, missing, future, or unverified data.

6. **Identity and task linkage.**  Freeze `FormalContextFact.id` as SHA-256 of
   all scientific/provenance fields (including canonical `value`, no-coverage,
   logical key, as-of, all source times, snapshot ID/content hash, parser and
   mapping versions, refresh generation, and root hash), excluding only
   `created_at_utc`.  A logical lookup key is
   `(context_kind, scope_key, security_id, as_of_utc, registry_manifest_hash)`
   plus exact exchange when resolving a calendar.  `put_formal_context_facts`
   must require the newly revalidated snapshot's ID/content/parser/version/
   mapping/generation/timestamps to equal every claim; if it has a producing
   task, require the immutable receipt and ensure the task is a source-fetch
   task with the same generation.  The Context descriptor/root must authorize
   the kind before insertion.  Equal scientific replay is idempotent preserving
   first creation time; any same-ID difference is a conflict.

## Minimal repository and persistence decision

Keep the existing Task 5B file scope.  Introduce two sealed records in
`formal_context_schema.py`:

- `FormalContextRequest`: resolver output only, exact request/root/role tuple,
  selected signed source config identity, upstream+derived refresh generations,
  and an optional exact binding.  Its construction should be internal to the
  descriptor resolver; public direct construction must not mint an authorized
  request.
- `FormalContextFact`: sealed canonical fact with `create`, `from_dict`,
  `to_dict`, and an identity as above.  Snapshot Context parser output before
  validation; never retain parser mappings/lists or let arbitrary JSON objects
  participate in equality.

`FormalContextRepository(store, snapshots, verifier)` should first reload the
entire root bundle.  On `get_verified`, it should ask StateStore for detached
candidate wires, rebuild sealed facts, re-fetch each source reference by
manifest through `snapshots`, read verified bytes (or at minimum use that
method to revalidate all fields), compare complete snapshot lineage, apply the
cutoff/descriptor/value rules, then choose exactly one candidate with
`formal_version_sort_key`.  It should fail closed on no candidate, ambiguous
calendar, corrupted row, unregistered kind, mismatch, or unverified source;
never use legacy tables, a raw Context row, a default calendar, or third-party
data.

`resolve_verified_calendar_binding` must query the selected calendar Context
using the signed selector's exact kind/scope/exchange/root/as-of, verify its
source snapshot/receipt and raw bytes, ensure the calendar context is visible,
and return a *fresh* exact `VerifiedCalendarBinding` carrying the revalidated
snapshot ID/manifest plus selector hash and prerequisite task ID.  The
prerequisite must come from verified task/receipt lineage, not caller input.
`build_effective_time_resolver(repository)` should expose only
`next_exchange_close`; on every invocation it reruns this selection and derives
the next valid exchange session from the selected calendar data.  It must not
call `market_close_as_of`, use a weekday heuristic, cache a prior binding, or
accept an otherwise verified different manifest.

StateStore needs only append-only typed `put_formal_context_facts` and detached
deterministic `list_formal_context_facts`; it remains the place where a single
transaction can call its private receipt-aware snapshot verification chain.
The list API should not call a root loader or claim typed trust: it returns
fresh validated/sealed Context facts or context wires for the repository to
revalidate.  The repository remains the root/descriptor/point-in-time gate.

## Test implications

Add focused RED/GREEN cases beyond the plan examples:

- same selector scope/root/as-of with SH/SZ/BJ calendar facts; only requested
  exchange binds, and another verified calendar manifest cannot be substituted;
- binding snapshot/manifest/root/selector/prerequisite mismatches fail both
  binding resolution and the effective-time resolver before it returns a close;
- weekend/holiday/next-session logic comes only from a verified calendar value;
  no calendar, malformed calendar, or duplicate visible calendar fails closed;
- timestamp source forbids a binding; date-only source requires the selected
  binding and its manifest in the fetch evidence hash; replay stays transport
  free;
- post-freeze `source_updated_at_utc` rejection with late `captured_at_utc`
  acceptance, and ordering tie breaks exactly matching `formal_version_sort_key`;
- forged/mutated Context fact, JSON value, root/role tuple, snapshot ref,
  descriptor, or parser/mapping/generation claim cannot cross the seal;
- same context key with two authorized refresh generations retains both audit
  rows and chooses only the visible canonical winner; a same-ID altered replay
  rolls back;
- consensus empty/failed/unverified/future evidence is not no-coverage;
  only signed explicit no-valid-coverage can produce the neutral state; and
- regression: `test_formal_context_schema`, `test_formal_context_repository`,
  `test_formal_sources`, and `test_formal_time` run with no transport/network.

## Conclusion

The existing source, root, snapshot, and time surfaces are sufficient for a
minimal secure Task 5B implementation once the six rulings above are frozen.
The two most consequential are the signed Context descriptor (including the
consensus role owner) and exchange-qualified calendar identity.  Proceeding
without them would force an unauthorized dataset-to-context mapping or an
ambiguous SH/SZ/BJ calendar selection; proceeding without the source-update
cutoff risks point-in-time look-ahead.
