# V6 Task 1 — injected official source adapter and signed registry boundary

## Starting point and scope

Start from reviewed V5 head `cc4227e`. This task creates a pure, fail-closed configuration/transport/parser boundary. It does **not** collect production data, persist a V6 registry, alter V5 schema/state, or start the worker.

Allowed tracked files only:

- create `ashare_pipeline/formal_sources.py`;
- create `ashare_pipeline/formal_registry_manifest.py`;
- create `tests/test_formal_sources.py`;
- create `tests/test_formal_registry_manifest.py`.

Do not modify V5 evidence/snapshot/store/state/universe code, migrations, worker/financial/feature/context modules, legacy source code, data, SQLite/WAL/SHM, or progress artifacts. Do not import network clients (`requests`, `urllib`, AKShare, BaoStock, `sources.FetchBatch`) in either new production module. All transport is injected.

This task deliberately has no production source registry/endpoints/parsers. Test fixture bytes may exercise an injected verifier, but test-purpose registries must never satisfy an official release gate or become a default configuration.

## Existing V5 contracts to reuse exactly

- Use `OfficialRequest`, `OfficialFetch`, `EvidenceVerification`, `VerifiedCalendarBinding`, `SourcePolicy`, and `verify_official_fetch` from `formal_evidence`; do not create a parallel evidence type.
- Use `resolve_effective_at` and `FORMAL_FREEZE_AT_CN` from `formal_time`; never infer a weekday or next trading session.
- Only `cninfo`, `sse`, `szse`, `bse`, and `csrc` `SourcePolicy` identities are eligible. A signed registry cannot widen this set with a custom source or host.
- V5 `FormalSnapshotRepository` remains the later persistence/replay boundary. Task 1 only creates `OfficialFetch`/verification and re-parses supplied bytes; it never writes a snapshot or direct SQL.

## Explicit scope rulings for plan gaps

These rulings are binding for Task 1 and prevent inventing V5 storage fields or production metadata.

1. **Date-only wire representation.** `ParsedOfficialDocument.published_at_utc` for `published_precision="date_only"` must be the canonical UTC day anchor exactly `YYYY-MM-DDT00:00:00+00:00`. The adapter passes its first ten characters (`YYYY-MM-DD`) to `EffectiveTimeResolver.next_exchange_close`, then calls `resolve_effective_at(..., precision="date_only", verified_next_exchange_close=...)`. Thus V5 receives an aware publication timestamp while effective-time resolution receives a genuine date. Any other date-only representation fails.
2. **Calendar binding ownership and source-root identity.** The adapter constructor receives the loaded root `registry_manifest_hash`, its exact `source_registry_hash`, and `freeze_at_utc` (defaulting only to the approved formal freeze constant). It rejects construction unless `SignedSourceRegistry.registry_hash` exactly equals that root-member hash. For date-only evidence it validates binding manifest, exchange, root, freeze, and the signed selector hash; it also requires a canonical nonblank prerequisite task UUID. The adapter cannot prove that UUID is the caller task's exact dependency because `fetch_verified` intentionally has no task-edge parameter. V6 Task 6 owns that payload-edge comparison before calling this adapter. Do not claim otherwise.
3. **Bootstrap calendar.** A signed `trading_calendar` config with `bootstrap_calendar=true` is accepted only for timestamp precision and no binding. The fact is returned as `ParsedOfficialDocument.bootstrap_calendar`; Task 1 must not add an undocumented V5 raw-manifest/snapshot metadata key. V6 context/worker persistence later records the bootstrap role in typed task/result data.
4. **Shared calendar resolver.** Task 1 verifies the exact binding passed into `verify_official_fetch`. Later persistence must configure its V5 `FormalSnapshotStore` with the same trusted context resolver; Task 1 cannot fabricate that production repository. Tests use a single fixture binding and prove a different otherwise-valid binding fails before transport.
5. **Registry reverse binding without a hash cycle.** The root canonical JSON contains the nine full child SHA-256 values, so a child canonical JSON cannot itself contain the resulting full root hash: doing both would require a cryptographic fixed point. `VerifiedRegistryBlob` therefore carries a separately signed child-binding envelope: `declared_registry_manifest_hash`, `binding_signature`, and `binding_key_id`. For each child, the loader constructs canonical UTF-8 bytes for exactly `{"child_sha256": <child blob SHA-256>, "registry_manifest_hash": <root manifest SHA-256>, "registry_role": <role>}` and verifies `binding_signature` using the injected verifier before accepting it. The envelope fields and signatures are mandatory, strict, and fail closed. This preserves the root-to-child full-hash binding and supplies an independently signed child-to-root declaration without weakening the fixed source-registry wire schema or inventing an impossible recursive hash.

## Source public types and APIs (`formal_sources.py`)

Export these names:

```python
FormalSourceError
FormalRetryableSourceError(FormalSourceError)
FormalSourceBlocked(FormalRetryableSourceError)
FormalTerminalSourceError(FormalSourceError)

@dataclass(frozen=True)
class TransportRequest:
    method: Literal["GET", "POST"]
    url: str
    headers: Mapping[str, str]
    body: bytes | None
    timeout_seconds: float

@dataclass(frozen=True)
class TransportResponse:
    status_code: int
    original_url: str
    headers: Mapping[str, str]
    raw_bytes: bytes
    captured_at_utc: str

class OfficialTransport(Protocol):
    def send(self, request: TransportRequest) -> TransportResponse: ...

class RegistrySignatureVerifier(Protocol):
    def verify(self, payload: bytes, *, signature: str, key_id: str) -> bool: ...

class EffectiveTimeResolver(Protocol):
    def next_exchange_close(
        self, *, exchange: str, disclosure_date_cn: str,
        calendar_binding: VerifiedCalendarBinding,
    ) -> str: ...

@dataclass(frozen=True)
class CalendarSelector:
    context_kind: Literal["trading_calendar"]
    scope_key: str
    exchange: Literal["SH", "SZ", "BJ"]
    as_of_rule: Literal["visible_at_freeze"]
    @property
    def selector_hash(self) -> str: ...

@dataclass(frozen=True)
class SourceAdapterConfig:
    source: str
    dataset: str
    endpoint_url: str
    http_method: Literal["GET", "POST"]
    parser_id: str
    parser_version: str
    mapping_version: str
    request_template: Mapping[str, object]
    timeout_seconds: float
    retry_base_seconds: float
    retry_max_attempts: int
    challenge_cooldown_seconds: float
    registry_hash: str
    exchange_scope: Literal["SH", "SZ", "BJ"] | None
    calendar_selector: CalendarSelector | None
    bootstrap_calendar: bool = False

@dataclass(frozen=True)
class ParsedOfficialDocument:
    parser_id: str
    parser_version: str
    declared_security_id: str | None
    declared_period: str | None
    published_at_utc: str
    published_precision: Literal["timestamp", "date_only"]
    source_updated_at_utc: str | None
    rows: tuple[Mapping[str, object], ...]
    accounting_basis: str
    bootstrap_calendar: bool = False

class OfficialDocumentParser(Protocol):
    def parse(
        self, raw_bytes: bytes, *, request: OfficialRequest, config: SourceAdapterConfig
    ) -> ParsedOfficialDocument: ...

class SignedSourceRegistry:
    @classmethod
    def from_signed_bytes(
        cls, registry_bytes: bytes, signature: str, key_id: str,
        verifier: RegistrySignatureVerifier,
    ) -> "SignedSourceRegistry": ...

class FormalOfficialSourceAdapter:
    def __init__(
        self, *, transport: OfficialTransport, registry: SignedSourceRegistry,
        policies: Mapping[str, SourcePolicy], parsers: Mapping[str, OfficialDocumentParser],
        effective_time_resolver: EffectiveTimeResolver,
        registry_manifest_hash: str, source_registry_hash: str,
        freeze_at_utc: str = FORMAL_FREEZE_AT_CN,
    ) -> None: ...

    def fetch_verified(
        self, request: OfficialRequest, *, refresh_generation: str,
        calendar_binding: VerifiedCalendarBinding | None,
    ) -> tuple[OfficialFetch, EvidenceVerification, ParsedOfficialDocument]: ...

    def parse_verified_snapshot(
        self, snapshot_ref: OfficialSnapshotRef, raw_bytes: bytes, *,
        calendar_binding: VerifiedCalendarBinding | None,
    ) -> ParsedOfficialDocument: ...
```

Use exact types at public trust boundaries where V5 does. Strings used as signed IDs/version fields must be already-trimmed, nonempty version identifiers compatible with V5 raw-store validation. Parser map lookup is keyed by signed `parser_id`; the returned document must exactly match signed parser ID **and** version.

## Canonical signed source-registry wire format

Registry bytes must be UTF-8, duplicate-key-free JSON whose exact bytes equal compact sorted `json.dumps(..., ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)`. Verify the injected signature over those exact bytes before parsing/constructing any config; verifier exceptions, false results, malformed signature/key ID, noncanonical bytes, unknown keys, duplicate keys, NaN/infinite values, and invalid types fail closed.

The exact top-level keys are:

```json
{
  "configs": [ ... ],
  "registry_role": "source",
  "schema_version": "formal-source-registry-v1"
}
```

`registry_hash` is the SHA-256 of the complete canonical signed registry bytes and is computed into every `SourceAdapterConfig`; it is **not** self-embedded in a config.

Every config has exactly these wire keys (with `calendar_selector`, `exchange_scope`, and `bootstrap_calendar` explicit even when null/false):

```text
source, dataset, endpoint_url, http_method, parser_id, parser_version,
mapping_version, request_template, timeout_seconds, retry_base_seconds,
retry_max_attempts, challenge_cooldown_seconds, exchange_scope,
calendar_selector, bootstrap_calendar
```

- Config identity `(source, dataset, exchange_scope)` is unique. A request with an exchange selects exactly one matching scoped config or one unscoped config, never both; a request without exchange selects exactly one unscoped config. Ambiguity or absence fails before transport.
- Endpoint is an absolute HTTPS URL with no userinfo/fragment; its hostname must be authorized by the fixed matching `SourcePolicy`. Response `original_url` must likewise be absolute HTTPS and allowlisted. No redirects to a nonallowlisted host are accepted.
- `request_template` has exactly `query`, `headers`, `body`. `query`/`headers` are mappings of already-trimmed string keys to templated string values; `body` is null or a JSON-like mapping/list/string/null tree. Only `{security_id}`, `{period_or_date}`, and `{exchange}` placeholders are legal; a placeholder with a null request value is invalid. Query substitutions are percent-encoded once, header values reject CR/LF, POST body is canonical compact sorted UTF-8 JSON after template substitution, and GET body must be null. No endpoint/path substitution, dynamic headers, unknown placeholders, or extra template keys.
- `calendar_selector` is null for timestamp-only non-calendar configs. Date-only configs require a nonnull selector and exactly one exchange resolved from request or signed scope. The only unbound exception is `dataset="trading_calendar"` plus `bootstrap_calendar=true`, which must be timestamp-only, have both `calendar_selector` and `exchange_scope` null, and accept only a request with null `exchange`; it has no calendar binding.
- A `universe_listing` config must be global (`security_id` null), exchange-scoped, and its parser is required to emit explicit `security_id`, `security_type`, and `listing_status` in every row. Aggregate multi-exchange listings are rejected at registry/config validation.

## Adapter behavior

Before any transport call, select/validate config, request identity, fixed policy, registered parser, config versions/template, nonempty `refresh_generation`, and calendar conditions. Every preflight rejection has zero transport calls.

For normal date-only configs, require `calendar_binding` and compare its `exchange`, `freeze_at_utc`, `registry_manifest_hash`, and `selector_hash` to the selected config/adapter root/freeze. Require canonical UUID `prerequisite_task_id` and lower-case hashes. A timestamp config requires null binding and null effective-time evidence hash. Bootstrap calendar is the sole timestamp/no-binding exception as defined above; nonbootstrap calendar and all other missing bindings are terminally invalid.

Build the `TransportRequest` only from signed config plus `OfficialRequest`; make exactly one injected transport call. Preserve `TransportResponse.raw_bytes` unchanged. Classify before parsing:

- 403/429, or a response containing a case-insensitive `captcha`/`challenge` marker, raises `FormalSourceBlocked`;
- `TimeoutError`, 408, 425, and 5xx raise `FormalRetryableSourceError`;
- every other non-2xx raises `FormalTerminalSourceError`;
- only a non-challenge 2xx response reaches the parser.

Validate document exact parser ID/version, request declared security/period (including null), row tuple/mapping types, accounting basis, source update timestamp, and publication precision. For timestamp precision preserve its canonical aware publication time as `effective_at_utc`. For date-only use the frozen UTC day-anchor rule and the injected effective-time resolver, validate its close using `resolve_effective_at`, and record the selected binding manifest SHA in `effective_time_evidence_hash`. Construct `OfficialFetch` from raw response bytes/config/generation and call `verify_official_fetch` with the fixed policy and the same binding. Any mismatch fails closed.

`parse_verified_snapshot` makes zero transport calls. It requires an exact `OfficialSnapshotRef`, raw SHA matching `content_sha256`, signed config/source/dataset/request/parser/version/mapping identity matching the ref, then reparses and performs the same publication/effective/binding checks. Date-only replays must reproduce the ref effective time and evidence manifest; timestamp snapshots require no binding. It returns only the validated document.

## Signed root manifest and bundle loader (`formal_registry_manifest.py`)

Implement the plan's `FormalRegistryManifest`, `VerifiedRegistryBlob`, `VerifiedRegistryBundle`, `FormalRegistryBundleRepository` protocol, and `FormalRegistryBundleLoader` public APIs exactly. Import the single `RegistrySignatureVerifier` protocol from `formal_sources`; do not create a duplicate or circular import.

The root canonical JSON has exactly:

```text
schema_version="formal-registry-manifest-v1", purpose, approval_id,
source_registry_hash, mapping_registry_hash, feature_registry_hash,
scoring_registry_hash, industry_registry_hash, cyclic_registry_hash,
redline_registry_hash, status_registry_hash, event_registry_hash
```

No root hash is self-embedded: `manifest_hash=SHA256(canonical_json)`. `purpose` is exactly `test` or `official`; official requires an already-trimmed nonempty `approval_id`, while test has null approval ID. `require_official` rejects anything else. `assert_member_hashes` accepts exactly the nine named role fields, rejects missing/extra/noncanonical values, and rejects mismatch.

Child role names are exactly `source`, `mapping`, `feature`, `scoring`, `industry`, `cyclic`, `redline`, `status`, `event`, mapped one-to-one to those root fields. A child blob's canonical JSON must self-describe matching `registry_role`; the source child follows the exact source-registry format above. The loader must re-read repository objects and reconstruct/reverify root and every child from their raw canonical bytes/signature/key ID; never trust an already-constructed dataclass. It checks exact canonical bytes, SHA-256, signature, role, the separately signed declared-root envelope defined above, uniqueness, and blob hashes. It returns a bundle only when every one of nine roles is present and exact. Hash swaps, role swaps, duplicate/unknown roles, verifier exceptions, noncanonical bytes, or tampering after storage fail closed. An in-memory repository is test-only; StateStore persistence is a later V6 task.

## Required TDD proof

Write failing tests first, then implement. Cover at least:

1. timestamp BJ fetch preserves exact raw bytes, config parser ID/version, generation, response URL, and verified identity;
2. unsigned/noncanonical/duplicate-key source registry, unknown/ambiguous config, missing parser, invalid endpoint/policy/template/version/rate values fail before transport;
3. injected transport status/challenge/timeout classification and zero parsing on errors;
4. date-only canonical day anchor plus exact selected binding succeeds; missing, wrong manifest/root/freeze/exchange/selector/prerequisite, resolver bad close, or timestamp-with-binding fails before transport;
5. bootstrap calendar only accepts signed timestamp/no-binding calendar config and surfaces document bootstrap fact without mutating V5 snapshot metadata;
6. parser document identity/version/rows/publication mismatch fails closed; universe listing type/status/global-scope violations fail;
7. replay uses zero network and rejects ref/raw SHA/source/dataset/request/parser/version/mapping/effective/binding tamper;
8. request template substitution/canonicalization and placeholder/header/body rejection;
9. manifest/root and child canonical bytes/signature/hash/role tamper, root member swap (including scoring hash), unknown/duplicate roles, test purpose official gate, and verifier exception all fail;
10. loader re-reads in-memory stored envelopes and returns only exact nine-role bundle; no default production registry exists;
11. existing `test_formal_evidence` and `test_sources` stay green.

Run RED first:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_formal_sources tests.test_formal_registry_manifest -v
```

Then run in one controlled session:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_formal_sources tests.test_formal_registry_manifest tests.test_formal_evidence tests.test_sources -v
.\.venv\Scripts\python.exe -m py_compile ashare_pipeline/formal_sources.py ashare_pipeline/formal_registry_manifest.py tests/test_formal_sources.py tests/test_formal_registry_manifest.py
git diff --check cc4227e..HEAD
```

Verify only the four allowed tracked files changed. Commit only them with:

```text
feat: add injected formal official source adapter
```

Write ignored `task-1-report.md` with the wire-format rulings, RED/GREEN proof, and explicit statement that production source configuration remains absent/blocked. Do not spawn subagents/reviewers.
