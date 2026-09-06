# Task 5B implementation-plan audit

Date: 2026-09-05.  Scope: read-only preflight of plan Task 5B
(`docs/superpowers/plans/2026-09-04-formal-v3-financial-feature-pipeline.md`,
lines 1032--1240), its Task 5/5A/6 interfaces, the global constraints, and
the V3 release contract.  I read, but did not change,
`ashare_pipeline/formal_sources.py`, `ashare_pipeline/formal_time.py`, and
`ashare_pipeline/state_store.py`.  No network operation, database mutation,
test execution, product-code edit, staging, or commit occurred.

## Verdict

Task 5B has a sound persistence destination and a sound fail-closed intent,
but it is **not yet self-sufficient for a safe implementation**.  The largest
missing contract is the signed translation from a requested context identity to
one allowed official request and one typed normalized value.  The current
source registry cannot express that translation.  Resolve the rulings below
before implementing a production-capable resolver/worker; until then the
production path must deterministically block rather than guess an endpoint,
scope, parser interpretation, or market value.

The existing V6 table is sufficient physically.  It is not a reason to weaken
the read/write boundary: the context API must re-read the linked verified
formal snapshot, raw bytes/manifest, receipt/task graph, and signed root on
every put and read.

## Exact planned interface and ownership boundary

Task 5B creates:

* `ashare_pipeline/formal_context_schema.py` and
  `ashare_pipeline/formal_context_repository.py`;
* tests `tests/test_formal_context_schema.py` and
  `tests/test_formal_context_repository.py`; and
* typed `StateStore.put_formal_context_facts` and
  `StateStore.list_formal_context_facts` over Task 5's pre-created V6 table.

Its named public surface is `FormalContextRequest`,
`SignedContextRequestResolver`, `FormalContextFact`, `FormalContextIssue`,
`FormalContextRepository.resolve_verified_calendar_binding`,
`build_effective_time_resolver`, and the two StateStore methods.  The stated
repository API is:

```python
FormalContextRepository(store: StateStore, snapshots: FormalSnapshotRepository)
get_verified(*, kind: str, scope_key: str, security_id: str | None,
             as_of_utc: str, registry_manifest_hash: str) -> FormalContextFact
resolve_verified_calendar_binding(*, selector: CalendarSelector,
             exchange: Literal["SH", "SZ", "BJ"], as_of_utc: str,
             registry_manifest_hash: str) -> VerifiedCalendarBinding
```

`FormalContextRequest` carries the context identity, explicit as-of, an
`OfficialRequest`, request/upstream/refresh generations, root hash, sorted
relevant role hashes, and an optional `VerifiedCalendarBinding`.  A
`FormalContextFact` carries its immutable identity/value/coverage assertion,
the four visibility/version fields, refresh generation, snapshot/content,
parser/mapping, and root hash.

Task 5B owns normalized official context evidence only: trading calendar,
market close/effective trade, security state, SW2021 industry snapshot,
regulatory/delisting state, event calendar, and consensus/no-coverage.  It
must not score, select peers, build a V6 financial feature bundle, infer a
weekday, use a third-party source as formal proof, or translate failure into
consensus no coverage.  Task 6 owns transport, leasing, retry/circuit behavior,
receipt persistence, and turning an already verified raw context response into
exactly one context fact.  V7/V8 own score-run context fingerprinting and
release evidence consumption.

## Confirmed implementation facts

* `formal_time.py` already fixes the release close at
  `2026-08-31T15:00:00+08:00`, supplies the required V5 ordering helper, and
  deliberately refuses to infer a date-only next close.
* `formal_sources.py` already checks source/parser/config identity,
  date-only `VerifiedCalendarBinding`, response host, raw hash, and replayed
  snapshot consistency.  A raw `OfficialSnapshotRef` already exposes request
  fingerprint/source/dataset/exchange, effective-time evidence hash, parser
  and mapping identity, generation, and producer task.
* Task 5's V6 `formal_context_fact` table has every planned persisted field:
  immutable `id`; logical identity; canonical value/coverage; timing;
  generation; formal-snapshot FK; content/parser/mapping/root lineage; evidence
  JSON; and creation audit time.  It deliberately has no typed APIs yet.
* The omitted request, receipt, source manifest, published precision, and
  effective-time-evidence columns need not be duplicated in the context table.
  They are safely reachable through `source_snapshot_id` **only if** the new
  API revalidates that full chain on both put and list.  Duplicating them
  without equality checks would create a second tamper surface.
* The persisted root is a hash-pinning envelope for the roles `source`,
  `mapping`, `feature`, `scoring`, `industry`, `cyclic`, `redline`, `status`,
  and `event`; it is not itself a context request or value-schema registry.

## Dependencies and required sequencing

| Dependency | What Task 5B needs | Consequence if absent |
|---|---|---|
| Foundation/V5 | `OfficialRequest`, verified formal snapshots/receipts, `VerifiedCalendarBinding`, source policy, `FormalSnapshotRepository`, and formal task dependencies | No admissible formal raw evidence or calendar proof. |
| Task 1 | Verified root bundle/loader, signed source registry/config, parser identity, `FormalOfficialSourceAdapter`, `CalendarSelector`, and effective-time protocol | No signed request selection or safe replay parsing. |
| Task 5 | V6 table plus source/receipt/task/root revalidation primitives and formal task ownership | No durable append-only context lineage. |
| Task 5A | No direct implementation dependency; both are siblings on Task 5.  They are jointly required by downstream score work. | Do not make context lookup depend on feature-bundle rows. |
| Task 6 | Must follow the complete Task 5B schema/repository.  It imports `FormalContextFact`, receives `FormalContextRepository`, creates `FormalContextTaskPayload`, revalidates date-only bindings, writes typed facts, and deliberately does not rebuild V6 feature bundles from context. | Worker cannot safely enqueue/execute/recover context work. |
| V7/V8 (downstream) | Need selected context generation/snapshot/content in input/evidence manifests. | Context may exist but cannot be made release-auditable. |

## Rulings required before implementation

### R1 — Signed context request and normalization registry (blocker)

`SignedContextRequestResolver` is only a Protocol.  Current
`SignedSourceRegistry` accepts exactly `formal-source-registry-v1`, whose
configs are keyed only by `(source, dataset, exchange_scope)` and contain no
`context_kind`, scope rule, security cardinality, market date rule, context
value schema, normalizer, or context mapping.  The existing root likewise has
no `context` child role.  Therefore it cannot prove the plan's claim that a
kind is declared by the persisted root or map a `(kind, scope, security,
as_of)` tuple to exactly one `OfficialRequest`.

**Minimum ruling:** add one signed, versioned context declaration boundary
(preferably a root-pinned `context` child registry; alternatively an explicitly
versioned signed extension to the source registry).  Each declaration must bind
kind, permitted scope/security form, source/dataset/exchange, exact request
derivation, parser+mapping/normalizer identity, required value schema, relevant
roles, date-only selector policy, and no-coverage semantics.  Loader and
StateStore must revalidate it; absent/ambiguous configuration is terminal or
pending with zero transport.

**Cost of no ruling:** an implementation must hard-code an endpoint, accept an
unregistered string kind, or choose between ambiguous signed configs.  Each
permits unauditable or wrong-source official context evidence.

### R2 — Formalize `FormalContextIssue` and non-success result contract

The plan names `FormalContextIssue` but specifies neither its fields/codes nor
how `get_verified` reports absent, pending, future, conflict, and tampered
evidence.  Its declared return type has only `FormalContextFact`.

**Minimum ruling:** define a frozen machine-readable issue (at least stable
code, logical key, root/as-of, and safe evidence/task reference) and choose one
uniform boundary: a typed result union, or an exact typed exception carrying
that issue.  Explicitly distinguish `pending_evidence`, source retry/terminal
failure, absent configuration, and integrity conflict.  Never map any of these
to `no_coverage`.

**Cost of no ruling:** V6/V7 callers will collapse a proof failure into an
ad-hoc exception or false neutral consensus, violating the V3 pending-evidence
contract.

### R3 — Bootstrap calendar construction and exchange/cardinality semantics

Task 5B says to resolve a binding after a bootstrap calendar; Task 6 says a
coordinator first enqueues it and tests name `enqueue_calendar_bootstrap`, but
neither task declares that public function/spec or its canonical idempotency
key.  Existing source policy requires a bootstrap calendar config to be a
global, unbound `trading_calendar` request; `CalendarSelector`, however, is
exchange-specific.  `FormalContextFact` has no separate exchange field and the
plan does not say whether `scope_key` encodes exchange, whether one raw calendar
covers all exchanges, or what parsed calendar rows prove each exchange.

**Minimum ruling:** define `formal_calendar_bootstrap_task_spec` (or an equally
explicit resolver operation), its signed config eligibility, fixed identity/
generation, and one canonical model: (a) one global verified raw snapshot with
explicit SH/SZ/BJ rows and three typed facts, or (b) one typed fact and source
snapshot per exchange.  Define NULL/non-NULL security, scope, exchange, and
row requirements for every `CONTEXT_KINDS` member, especially global versus
per-security event/regulatory/industry contexts.

**Cost of no ruling:** date-only work either deadlocks with no bootstrap task
or reaches transport without a proven calendar; cross-exchange close reuse can
make an input visible at the wrong time.

### R4 — Typed value schemas, canonical fact identity, and append-only conflict rule

`value: Mapping[str, object]` plus prose/examples does not define a validation
schema.  There is no canonical `FormalContextFact.id` derivation, equality wire
format, same-logical-key/same-generation conflict behavior, or required
`evidence_json` shape.  The table has only `id` PK and no lookup index/unique
constraint.  That is acceptable only when the API enforces the contract.

**Minimum ruling:** the signed context declaration must give exact canonical
schemas.  At minimum market facts require exchange state, volume, turnover,
effective-trade flag, valid close/date and stale days; industry requires both
levels, source version/effective date/full mapping hash; consensus requires
one verified coverage state and the exact explicit no-valid-coverage marker.
Define a canonical identity/wire (excluding DB `created_at`), equal replay as
no-op preserving initial creation time, changed same-ID or same logical
key+generation as conflict, distinct valid generations retained, and NULL-safe
logical lookup/filtering by kind/scope/security/as-of/root.  Repository ranking
then uses exactly published DESC, source-updated DESC NULL last, captured DESC,
content hash ASC.  If the selected newest candidate cannot revalidate, fail
closed rather than silently promoting an older row.

**Cost of no ruling:** malformed or partial market facts can enter V7; replay
can overwrite audit history or selection becomes nondeterministic.

### R5 — Explicit lineage checks at the context boundary

Task 5B says “verified formal source snapshot” and “when it has a producing
task, receipt,” but this must not be implemented as merely accepting any V5/V6
source-fetch receipt.  A verified financial statement or universe listing can
otherwise be relabelled as context.

**Minimum ruling:** `put_formal_context_facts` accepts an exact sealed fact and
requires its snapshot to revalidate against its source content/manifest,
verification JSON, request fingerprint, root/config declaration, timing,
content hash, generation, parser/mapping, and receipt/task graph.  For ordinary
facts producer kind must be `formal_context`; a bootstrap-calendar exception,
if retained, must be explicit and bound to R3.  Do not require producer status
already `verified`: Task 6 legitimately writes after receipt persistence but
before completion.  Batch writes must be one immediate transaction and re-read
their inserted projections before commit.

**Cost of no ruling:** valid but unrelated raw material can acquire a context
label, or a crash/retry loses a valid receipt / creates duplicate facts.

### R6 — Freeze parameter and timestamp policy

The V3 contract fixes 2026-08-31 15:00 Asia/Shanghai (07:00 UTC).  Task 5B
accepts arbitrary strings named `as_of_utc`; source adapter defaults to the
CN form.  The plan must state whether this pipeline is only for that frozen
release (then reject any different instant) or is release-parameterized (then
the root/task/adapter/fact must carry and compare the same explicit release
freeze).  The current hybrid permits accidental mismatch.

**Minimum ruling:** choose one model and require canonical aware timestamps;
for the present V3 release, canonicalize/compare both spellings as the same
instant and reject all others.  Preserve date-only effective-time proof through
the linked calendar binding, not a 23:59:59 fallback.

**Cost of no ruling:** a correct snapshot may be selected under a wrong cutoff,
creating forward-looking market/context inputs.

## Production and test boundary

Production has no supplied endpoint, document parser, raw context-field map,
normalizer, signed context registry, or signing authority.  This is an
intentional release-gate absence in the approved contract, so production must
remain a deterministic blocked/pending-evidence path and must not introduce a
default endpoint, industry template, market close, consensus state, or missing
value imputation.

Tests may supply only hermetic fixture signed bytes, accepting fake verifier,
fake parser, in-memory raw bytes, fake transport, temporary local snapshot
store/SQLite, and a fixture calendar resolver.  Required negative tests include
unregistered/ambiguous kind; wrong source/dataset/request/security/exchange;
missing or alternate root/config/selector/binding; legacy snapshot; corrupted
raw/manifest/receipt; wrong producer kind/generation; post-freeze/invalid
effective time; malformed newest version; no-coverage forgery; equal replay,
conflict, and distinct correction; and lost-lease receipt replay with zero
additional transport.  No test may use AkShare, BaoStock, live exchange URLs,
or a production registry default.

## Existing tests versus required coverage

The plan's Step 1 examples prove only happy-path resolution, a few market and
consensus checks, a foreign calendar binding, exact lookup, two-generation
selection, and legacy snapshot rejection.  They do not prove R1--R6, batch
atomicity, root/config revalidation, receipt producer-kind isolation, malformed
newest fail-closed behavior, canonical JSON/type-subclass rejection, or
bootstrap scheduling.  Add those tests before implementation, then execute the
declared context/source/time suite and the Task 6 worker regression.

## Safe execution order after rulings

1. Freeze the signed context declaration and calendar model (R1/R3/R6), then
   write red tests for resolver/schema/StateStore/repository.
2. Implement sealed schema + canonical issue/result; implement StateStore
   append-only put/list with full snapshot/receipt/root revalidation (R2/R4/R5).
3. Implement exact repository selection and effective-time resolver using the
   revalidated calendar fact.
4. Only then implement Task 6 context task specs/bootstrap/worker normalization
   and recovery.  Do not wire a context refresh into V6 feature builds; Task 6
   correctly reserves context hashes for V7 score-run manifests.

