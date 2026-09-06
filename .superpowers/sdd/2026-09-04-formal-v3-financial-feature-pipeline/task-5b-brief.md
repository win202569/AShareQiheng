# Task 5B binding brief — verified official context

Read this entire file before editing. It is the binding specification for
Task 5B and supersedes ambiguous examples in the implementation plan. The
implementation base is commit `e2b85fe`. The task supplies auditable
official market, calendar, industry, status, regulatory, event, and consensus
context to later workers; it does **not** fetch the network, provide a
production endpoint/parser/mapping/default, score a security, or build a
worker.

## Authorized tracked scope

Only these tracked files may change:

1. Create `ashare_pipeline/formal_context_schema.py`
2. Create `ashare_pipeline/formal_context_repository.py`
3. Create `tests/test_formal_context_schema.py`
4. Create `tests/test_formal_context_repository.py`
5. Modify `ashare_pipeline/state_store.py`

Do not change accepted source/time/registry/feature modules or legacy tables.
The existing V6 `formal_context_fact` DDL is immutable: do not add a V6
migration, alter its DDL/index definitions, or reinterpret legacy data.
Exercise the new StateStore APIs through the two new Context test modules.
Do not stage data, SQLite, WAL/SHM, source snapshots, progress files, reports,
briefs, or ledger files. This is a pure code/test commit with subject:

```
feat: add verified formal market and policy context
```

The preflight audits are available beside this brief. They are useful
background but this file is the single implementation authority.

## Non-negotiable trust boundary

Every official Context operation must reload a whole
`VerifiedRegistryBundle` with
`FormalRegistryBundleLoader(StateStore, registry_signature_verifier)`, then
call `bundle.require_official()`. Never trust an injected
`VerifiedRegistryBlob`, a raw root row, a hash alone, a legacy snapshot, or
a fixture dataset name.

The root already has exactly nine pinned child roles. Do not change that
protocol. The canonical Context declaration lives in the verified `scoring`
child:

```json
{
  "schema_version": "formal-context-registry-v1",
  "descriptors": [ ... ]
}
```

The scoring child wrapper/binding signature is the descriptor signature
boundary. Parse its canonical bytes strictly and construct a closure-sealed
`FormalContextRegistry`; no public direct constructor/factory may mint a
trusted registry or a `FormalContextRequest`.

Each descriptor is a canonical object with exactly these fields:

```text
context_kind               one of CONTEXT_KINDS
scope_key                  exact trimmed identifier, no wildcard
security_scope             "none" | "security"
request_security           "none" | "input_security"
period_rule                "none" | "freeze_date_cn"
exchange_rule              "none" | "security_exchange" | "fixed_exchange"
fixed_exchange             null | "SH" | "SZ" | "BJ"
source, dataset            exact signed SourceAdapterConfig identity
parser_id, parser_version, mapping_version
request_version            exact nonempty identifier
normalizer_version         exact nonempty identifier
generation_namespace       exact nonempty identifier
referenced_roles           sorted nonempty unique tuple from root roles
calendar_selector          null | canonical CalendarSelector wire
bootstrap_calendar         exact bool
allowed_regulatory_flags   sorted unique identifier tuple
allowed_event_codes        sorted unique identifier tuple
```

`source`, `dataset`, parser ID/version, mapping version, exchange scope,
calendar selector, and bootstrap flag must exactly agree with the unique
`SignedSourceRegistry.select(OfficialRequest)` configuration selected from
the verified `source` child. `referenced_roles` must include `source`
and `scoring`; each role's hash must equal the root member. Its sorted
`(role, hash)` projection is the request/fact
`relevant_registry_hashes`. The descriptor's canonical ID is the SHA-256 of
its canonical JSON object and must be carried in Context evidence.

There is exactly one descriptor for an exact public
`(context_kind, scope_key, security scope, as-of rule)` request. No
dataset-to-kind inference, descriptor prefix matching, default role, default
endpoint, default field map, default calendar, or third-party fallback is
allowed. The descriptor owns consensus semantics; it may explicitly reference
the industry/status/event role hashes but no new root role is invented.

## Public schema contract

Export:

```python
CONTEXT_KINDS = (
    "trading_calendar", "market_close", "security_state", "industry_snapshot",
    "regulatory_state", "event_calendar", "consensus_snapshot",
)

FormalContextRequest
SignedContextRequestResolver        # concrete sealed resolver, not an instantiable Protocol
FormalContextFact
FormalContextIssue
FormalContextVersionView
FormalContextRegistry               # public loader/type is acceptable; direct trust minting is not
FormalContextNormalizer              # injected trusted semantic-normalization boundary
FormalContextNormalization           # sealed output receipt accepted by StateStore
```

`FormalContextRequest` has every displayed plan field (including
`request_version`) plus the immutable descriptor ID
and normalized-context registry provenance required to audit it. Its
`official_request` is an exact `OfficialRequest`, its
`relevant_registry_hashes` is sorted and exact, and it holds either no
binding (timestamp source) or a fresh exact `VerifiedCalendarBinding`.
The resolver derives `refresh_generation` as SHA-256 of canonical
`formal-context-refresh-generation-v1` input containing:

- descriptor ID, fixed `generation_namespace`, and a required caller-supplied
  exact `upstream_generation`;
- full official request identity;
- root registry hash and sorted relevant role hashes; and
- for a date-only source, every signed selector field plus every binding field
  (snapshot ID/manifest, exchange, freeze, root, selector hash, prerequisite
  task ID).

The request must validate the descriptor's security, exchange, and
period/date rules before it reaches a caller. `freeze_date_cn` is the
Asia/Shanghai calendar date of the explicit aware `as_of_utc`; never reuse
legacy 23:59:59 logic. `input_security` requires an exact Formal SH/SZ/BJ
security ID; `none` rejects one. `security_exchange` derives the prefix;
`fixed_exchange` must equal its declared exchange; `none` requires null.
The public resolver uses the plan's `context_kind` keyword (the repository
getter retains its displayed `kind` keyword) and adds required keyword-only
`upstream_generation: str` (no default) to the plan's displayed fields.
Task 6 will prove that generation against its signed source/task payload; Task
5B accepts only an exact nonempty value and records it in request, normalization
receipt, and fact evidence. This is what permits same-root source corrections
to create distinct immutable refresh generations rather than making legitimate
history impossible.
For date-only config, resolve the selected verified calendar binding before
minting the request. Bootstrap calendar descriptors must select a signed
`bootstrap_calendar=True` timestamp config, have no binding, and are the
only bootstrap exception. A timestamp config rejects a binding.

`FormalContextFact` is a sealed canonical record with public
`create(...)`, `from_dict(...)`, `to_dict()`, canonical bytes, and a
SHA-256 `id` over every scientific/provenance field below, excluding only
`created_at_utc` (which is StateStore audit data):

```text
context_kind, scope_key, security_id, as_of_utc, canonical value,
no_coverage, published_at_utc, effective_at_utc, source_updated_at_utc,
captured_at_utc, refresh_generation, source_snapshot_id,
source_content_sha256, parser_id, parser_version, mapping_version,
registry_manifest_hash, canonical evidence
```

Values and evidence must be detached JSON-native canonical trees; reject
aliases, duplicate keys, unsupported leaves, nonfinite floats, loose
int/float equivalence, or post-construction mutation. `to_dict()` must
recheck the seal and return fresh data. Do not retain parser-owned mappings or
lists. `FormalContextIssue` is likewise a detached sealed audit record with
exact `code`, context logical identity, and canonical JSON details; it
records a missing/pending/tamper reason but never converts it into a neutral
fact.

Task 5B deliberately does not ship a production raw parser/normalizer: those
signed production assets do not exist. Make that boundary explicit rather than
pretending a stored Fact semantically reparses raw bytes. Define
`FormalContextNormalizer` as a narrow injected protocol with exact
`normalizer_version` and a method that receives a sealed request, a fresh
verified snapshot reference, and detached verified raw bytes. It returns exact
`FormalContextFact` candidates. `FormalContextRegistry.normalize_verified`
must recheck the request/snapshot/raw SHA-256, require the descriptor's exact
normalizer version, snapshot the candidates, and mint a
closure-sealed `FormalContextNormalization` receipt only after every Fact
matches descriptor/source/request/value requirements. There is no default
normalizer, parser callback, or direct persistence bypass. A fake normalizer
is allowed only in hermetic tests. This is the trusted semantic boundary that
Task 6 will invoke; persistence/repository independently prove raw provenance
but do not claim to derive a meaning from bytes without that injected
normalizer.

Evidence is an exact object containing `descriptor_id`,
`normalizer_version`, `normalization_input_hash`,
`relevant_registry_hashes`, `request_fingerprint`,
`upstream_generation`, and `calendar_binding` (null for timestamp sources;
otherwise the complete binding wire). The input hash is SHA-256 over canonical
`formal-context-normalization-input-v1` data: descriptor ID, normalizer
version, complete request identity, verified snapshot manifest/content, and
the Fact's canonical scientific wire excluding both Fact `id` and the
self-referential `evidence.normalization_input_hash` field. All other
evidence fields remain covered. It must match the verified descriptor, root,
snapshot request, source configuration, and Fact. No arbitrary extra evidence
keys are accepted.

`FormalContextVersionView` exposes the four `FormalVersion` fields
`published_at_utc`, `source_updated_at_utc`, `captured_at_utc`, and
`content_hash`; selection must use `formal_version_sort_key` verbatim.

## Closed values and point-in-time rules

All Context timestamp fields are exact timezone-aware ISO-8601 strings.
`published_at_utc`, `effective_at_utc`, and non-null
`source_updated_at_utc` must each be `<= as_of_utc`. `captured_at_utc`
may be later: this is verified late historical capture, not look-ahead.
Repository reads repeat all three cutoff checks.

The `value` object has a closed schema by context kind:

- `trading_calendar`: exactly `exchange`, `calendar_version`, and
  `trading_days`. Exchange is SH/SZ/BJ; version is a nonempty identifier;
  trading days are a nonempty, strictly increasing, unique tuple of
  ISO dates. This embedded exchange is part of canonical value/ID and is the
  required V6-compatible discriminator for global calendar rows.
- `market_close`: exactly `exchange`, `exchange_allows_trading`,
  `volume`, `turnover`, `is_effective_trade`, `valid_close`,
  `valid_close_date`, and `stale_trading_days`. Decimal quantities are
  canonical finite decimal strings; valid close is positive; stale days is a
  nonnegative exact int. An effective trade has zero stale days and the
  freeze-date valid close; a stale record has positive stale days and a prior
  valid-close date. Absence of a valid close is a pending issue, not a fake
  zero-price fact.
- `security_state`: exactly `is_st`, `is_star_st`, `listing_status`,
  `forced_delist_risk`, and `suspended`; listing status is
  `listed|delisting_arrangement|delisted`.
- `industry_snapshot`: exactly `classification_system`,
  `primary_industry`, `secondary_industry`, `source_version`,
  `effective_date`, and `mapping_sha256`; system is `SW2021`.
- `regulatory_state`: exactly `flags`, a sorted unique tuple of
  `{flag_id, active}` entries. Every ID must be descriptor-authorized.
- `event_calendar`: exactly `events`, a sorted unique tuple of
  `{event_id, event_date, quantified_value, unit}` entries. Every ID is
  descriptor-authorized; date and quantity are explicit. It stores evidence
  only and exposes no score/T value.
- `consensus_snapshot`: exactly `coverage_status` and `estimates`.
  Status is `covered|no_valid_coverage`; estimates are a canonical tuple of
  explicit JSON objects (no arbitrary objects). `no_coverage=True` is legal
  **only** when status is `no_valid_coverage`, the descriptor authorizes
  consensus, and the verified source response proved that status. A failed,
  empty, absent, future, unregistered, or time-unverifiable response is an
  issue/pending state, never no coverage.

Do not calculate scores, T inputs, flags, or interpret missing values in this
task. Unsupported value/normalizer versions fail closed.

## StateStore contract

Add only:

```python
StateStore.put_formal_context_facts(...)
StateStore.list_formal_context_facts(...)
```

The put API accepts only a sealed `FormalContextNormalization` receipt, not
a caller-created tuple of Facts; list returns detached exact
`FormalContextFact` records. Both use the existing V6 table.
At write time, in one immediate transaction:

1. Require a configured registry verifier; load/reverify the full root bundle
   and official gate, then the Context registry from its scoring child.
2. Verify the sealed normalization receipt, then revalidate every fact's
   descriptor/evidence/root roles and derive its expected context
   request/generation rather than trusting a caller claim.
3. Revalidate the linked snapshot through
   `_formal_verified_snapshot_ref_from_connection`: original bytes/manifest,
   verified snapshot, receipt, producing task, and generation must all remain
   valid. Its producer must be `formal_context`, including bootstrap
   calendar. Snapshot request/source/dataset/security/period/exchange,
   content hash, parser/version, mapping, timestamps, and generation must
   equal the fact/request exactly.
4. Enforce the closed value/no-coverage/time rules and append-only collision
   rules. A byte-identical scientific replay is idempotent and retains the
   first creation timestamp. For the same logical key plus implicit calendar
   exchange and refresh generation, a different ID is a deterministic conflict;
   never overwrite or choose insertion order.

`list_formal_context_facts` returns detached exact records in deterministic
ID order and reruns the linked snapshot/receipt/task validation before
returning any row. It does not trust a DB row, load a raw descriptor, use a
legacy table, silently skip corrupt rows, or claim that a list result is
release-authorized.

The sealed normalization receipt is an **in-process write capability**, not a
persisted signature. After restart, reads rederive the deterministic
`normalization_input_hash` and prove raw snapshot/configuration/structural
provenance, but intentionally do not re-run an arbitrary normalizer over raw
bytes. Therefore this task must not claim that a coordinated direct-SQL rewrite
which recomputes every public deterministic field has been semantically
reparsed; approved parser/normalizer code and any stronger external attestation
remain a future release boundary.

## Repository and effective-time contract

Export `FormalContextRepository` and `build_effective_time_resolver`.
The repository constructor takes an exact `StateStore`, a
`FormalSnapshotRepository`, and a registry verifier. It loads/revalidates
the full official root/Context registry at every public entry. It treats a
missing/corrupt row, unregistered descriptor, identity mismatch, future
source/update/effective time, invalid value, or corrupted source lineage as
a fail-closed error — never as a legacy/default/third-party fallback.

Within one synchronous public call only, private code may reuse the
closure-sealed descriptor already minted in a seal-checked
`FormalContextRequest`; this prevents repeated full-root reloads for the
same Fact. It must not be exposed, cached across calls, or accepted from a
forged/mutated request, and it never replaces snapshot/receipt/task lineage
or calendar binding revalidation.

`get_verified(kind, scope_key, security_id, as_of_utc, registry_manifest_hash)`
returns exactly the one visible, validated non-calendar Context fact. It
re-lists/re-snapshots candidates before and after source/root verification to
detect a correction race; it validates complete snapshot identity through
`FormalSnapshotRepository.get_verified_by_manifest` and
`read_verified_raw`, descriptor/evidence binding, source time cutoff, and
the descriptor's normalizer/value. Select with `formal_version_sort_key`;
if the leading version is invalid/tampered, fail closed rather than falling
back. Multiple equal leading candidates are an explicit conflict.

Historical lookup does **not** re-run `FormalOfficialSourceAdapter` parsing
or an injected normalizer: that would make a date-only source recursively
depend on the very calendar Context being resolved and would treat a mutable
runtime normalizer as historical proof. It proves the raw source chain through
the two snapshot-repository calls above and compares the persisted Fact,
normalization-input hash, and descriptors. Calendar bootstrap evidence is a
signed timestamp source and is selected directly through that same
non-recursive chain.

`resolve_verified_calendar_binding(selector, exchange, as_of_utc,
registry_manifest_hash)` selects only a visible `trading_calendar` value
with exact selector scope, root, as-of, and embedded exchange. It revalidates
snapshot/raw receipt/task, descriptor, root, selector hash, source
`effective_time_evidence_hash`, and prerequisite task ID. It returns a
fresh `VerifiedCalendarBinding`, never a caller-provided one. A different
manifest (even verified), root, selector, exchange, task, stale row,
duplicate leading calendar, or unavailable next session fails closed.

`build_effective_time_resolver(repository)` returns an
`EffectiveTimeResolver` implementation with only
`next_exchange_close(exchange, disclosure_date_cn, calendar_binding)`.
Every call re-resolves/revalidates the binding and chooses the first verified
calendar trading day strictly after the disclosure date at
`15:00:00 Asia/Shanghai`. It cannot cache a binding, infer weekdays, call
the legacy market-close helper, or accept another verified calendar manifest.

## Required RED/GREEN tests

Start by writing failing tests in the two new modules. Include at least:

1. canonical request resolution from one signed descriptor; reject missing,
   duplicate, role/source/parser/mapping/period/security/exchange mismatch,
   request-version mismatch, alias/mutation, missing/mismatched normalizer,
   direct-persistence bypass, and no production default;
2. per-kind closed value validation; canonical fact/issue sealing, object
   forgery/mutation, canonical ID, and no-coverage negative cases;
3. StateStore write/list through verified snapshot → raw bytes → receipt →
   `formal_context` task → generation chain; reject legacy/statement/universe
   source, incorrect root/descriptor/request/lineage/times, collisions, DB
   tamper, raw/manifest/receipt/task tamper, and preserve history;
4. historical version selection using `formal_version_sort_key`, inclusive
   published/effective/source-update cutoff, allowed late capture, two
   distinct explicit upstream generations under one root, and final recheck
   against correction races; include a forged/mutated request regression for
   any private descriptor-reuse fast path;
5. SH/SZ/BJ calendar separation, bootstrap/date-only path, binding/root/
   selector/manifest/task substitutions, malformed/duplicate/no-next-session
   failures, and no weekday inference;
6. market close state/stale-price rules; industry SW2021; status, regulatory,
   event descriptor allowlists; and consensus explicit verified no coverage
   versus empty/failed/future/unverified evidence;
7. no network access and regression:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_formal_context_schema tests.test_formal_context_repository tests.test_formal_sources tests.test_formal_time -v
```

Before commit also run `py_compile` on all five tracked files,
`git diff --check`, inspect status, and self-review the diff. Do not submit
until all relevant tests pass. Write the detailed RED/GREEN/rulings/test
report to `.superpowers/sdd/2026-09-04-formal-v3-financial-feature-pipeline/task-5b-report.md`
(ignored).

## Binding rulings

17. Event quantity: event_calendar.quantified_value accepts a canonical finite signed decimal; market_close.volume and market_close.turnover remain canonical finite non-negative decimals.
