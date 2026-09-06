# V6 Task 2 binding brief — formal financial facts

Plan: `docs/superpowers/plans/2026-09-04-formal-v3-financial-feature-pipeline.md`, Task 2.

Base: accepted Task 1 at `352223b`. Task 1's source and mapping boundaries are trusted only through their signed loaders; no production mappings, parsers, endpoints, or keys are to be invented.

## Scope and commit boundary

Create and modify exactly these tracked files:

1. `ashare_pipeline/formal_financial_schema.py`
2. `tests/test_formal_financial_schema.py`

Do not modify Task 1 files, `state_store.py`, legacy financial/schema/feature code, plans, data, SQLite/WAL/SHM, progress files, or any other tracked file. Do not collect data or make network calls. Initial commit subject: `feat: add formal financial fact schema`. Reports are ignored under this SDD directory and must never be staged.

## Public types and APIs

The new module consumes only `ParsedOfficialDocument`, `RegistrySignatureVerifier`, `OfficialSnapshotRef`, `canonical_security_id`, `canonical_json_bytes`, and `canonical_sha256`. It produces at least:

```python
@dataclass(frozen=True)
class FormalFactMapping:
    mapping_id: str
    statement: Literal["income", "balance", "cash_flow"]
    metric_key: str
    source_field: str
    unit: Literal["CNY", "shares", "ratio", "CNY_per_share"]
    nature: Literal["instant", "duration"]
    period_kind: Literal["FY", "H1", "Q1", "Q3", "OTHER"]
    accounting_basis: str

@dataclass(frozen=True)
class FormalFactIssue:
    code: str
    mapping_id: str | None
    source_field: str | None
    details: Mapping[str, object]

@dataclass(frozen=True, init=False)
class FormalFinancialFact:
    # The fields named in the Task 2 plan, exactly.
    ...
    @classmethod
    def create(cls, ...) -> "FormalFinancialFact": ...
    def to_dict(self) -> Mapping[str, object]: ...
    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> "FormalFinancialFact": ...

@dataclass(frozen=True)
class FormalFactExtraction:
    facts: tuple[FormalFinancialFact, ...]
    issues: tuple[FormalFactIssue, ...]

class SignedFinancialMappingRegistry:
    @classmethod
    def from_signed_bytes(
        cls, registry_bytes: bytes, *, signature: str, key_id: str,
        verifier: RegistrySignatureVerifier,
    ) -> "SignedFinancialMappingRegistry": ...

def extract_formal_financial_facts(
    document: ParsedOfficialDocument, snapshot_ref: OfficialSnapshotRef,
    registry: SignedFinancialMappingRegistry, created_at_utc: str,
) -> FormalFactExtraction: ...
```

`FormalFinancialFact` has every field in the plan's declaration: id, identity/scientific values, all publication/effective/source lineage, raw-field provenance, parser/mapping provenance, and `created_at_utc`. Its `id` is `canonical_sha256` of every field except `id` and `created_at_utc`; `created_at_utc` never changes identity. `create`/`from_dict` are the only normal construction paths; direct construction must fail. `to_dict` and `from_dict` use exact keys and recompute/verify the ID so a mutated object cannot silently serialize as a valid fact. This is a value-validation boundary, not a claim that Task 2 can prove database membership; Task 5/6 own formal snapshot/task re-reads.

## Signed mapping registry wire contract

Task 2 freezes the missing row-selection contract rather than guessing parser column names.

The signed UTF-8 canonical JSON has exactly:

```text
schema_version = "formal-financial-mapping-registry-v1"
registry_role = "mapping"
row_format = "item_value_v1"
mappings
bindings
```

Duplicate JSON keys, noncanonical bytes, non-finite values, verifier exceptions, or verifier results other than exactly `True` fail closed before a registry object exists. The registry hash is SHA-256 of the original canonical bytes. There is no default registry and no legacy mapping fallback. Like Task 1's trusted registry types, the signed registry must be closure-sealed: ordinary direct construction, `object.__new__`, public-field mutation, and exposed module-level registrar/factory functions must not create or alter a trusted registry. Do not expose a verifier capability on public objects.

Each mapping wire object has exactly the eight `FormalFactMapping` fields. IDs, metric keys, source fields, and accounting basis are exact trimmed strings. Mapping constraints are strict:

- statement is `income`, `balance`, or `cash_flow`;
- unit/nature/period_kind are the declared enums;
- `balance` requires `instant`; `income` and `cash_flow` require `duration`;
- a mapping ID is unique;
- within an applicable binding, `(statement, metric_key, period_kind, accounting_basis)` and `source_field` are unique.

Each binding wire object has exactly:

```text
source, dataset, parser_id, parser_version, mapping_version, exchange_scope, mapping_ids
```

All text is exact/trimmed; `exchange_scope` is exactly SH/SZ/BJ; `mapping_ids` is a nonempty sorted tuple/list of unique IDs. Binding identity `(source, dataset, parser_id, parser_version, mapping_version, exchange_scope)` is unique. Across bindings, IDs must reference declared mappings without ambiguity and mappings used by the registry must be covered. A document/snapshot selects exactly one binding by exact source, dataset, parser ID/version, mapping version, and canonical security exchange prefix. No global, nearest-name, cross-exchange, parser-version, or mapping-version fallback is allowed.

`row_format="item_value_v1"` means every financial document row is exactly:

```json
{"ITEM":"<trimmed signed source_field>","VALUE":<raw JSON scalar>}
```

No extra/missing keys, aliases, display-name matching, nearby-field lookup, or inferred value column is permitted. Parsers must normalize their output to this wire shape before Task 2.

## Extraction and lineage contract

Before processing any row, reject hard (not an issue) unless all are true:

- `document` is exact `ParsedOfficialDocument`, `snapshot_ref` is exact `OfficialSnapshotRef`, and the registry seal is valid;
- the document is non-bootstrap, its declared canonical security and period are nonnull, and both exactly match the snapshot; snapshot exchange, when nonnull, equals the security prefix;
- snapshot is verified and has canonical content hash, formal snapshot ID, nonempty refresh generation, parser ID/version, mapping version, source/dataset, and canonical request fingerprint; recompute that fingerprint from its exact `OfficialRequest` five-tuple and require equality;
- document parser ID/version, publication timestamp/precision, and source-updated timestamp exactly agree with the snapshot lineage; all copied timestamps are canonical aware UTC values;
- timestamp precision has null effective-time evidence and `effective_at_utc == published_at_utc`; date-only precision uses Task 1's exact UTC day anchor, a nonempty canonical evidence SHA-256, and `effective_at_utc > published_at_utc`;
- `created_at_utc` is canonical aware UTC.

The selected binding is then filtered to mappings whose `accounting_basis` exactly equals the document's basis and whose `period_kind` matches the declared period's canonical kind (Q1=03-31, H1=06-30, Q3=09-30, FY=12-31, otherwise OTHER). Non-applicable mappings are not missing. If no mapping is applicable, return no facts and one `mapping_not_applicable` issue.

For each applicable mapping, accept exactly one matching `ITEM`. A raw number is an exact finite int/float other than bool, or a strict ASCII decimal string with no whitespace, comma, locale, NaN, or infinity spelling. Normalize zero to `+0.0`; preserve `raw_value_sha256=sha256(canonical_json_bytes(original_raw_scalar))`. A matched mapping creates a fact; unknown items, missing applicable fields, repeated fields, and nonnumeric values create only sorted `FormalFactIssue` entries and never a guessed numeric fact. A repeated field is a conflict even if display text looks similar. Facts sort by `id`; issues sort by an explicit code priority then mapping/source field and canonical details hash so missing-required is deterministically first when paired with an unknown row.

For facts: normalize with `canonical_security_id` (SH/SZ/BJ), use mapping statement/unit/nature/accounting basis and signed source field, derive `period_start` as January 1 of the period year for duration Q1/H1/Q3/FY and null for instant/OTHER, copy all time/source/parser/mapping fields from the validated document/snapshot, and validate finite value plus all canonical hashes/text/times. A fact can never accept a legacy `FinancialFact`, a legacy snapshot row, a generic dict as a source object, or third-party mapping output.

`FormalFactIssue.details` must contain only JSON-safe immutable copied values such as mapping ID/source field/row index/raw value SHA; never a raw parser mapping/object. Its serialization is canonical and it must not retain parser row identity.

## Required TDD proof

Start with RED (`tests.test_formal_financial_schema` fails because module is absent), then test and implement:

1. signed canonical mapping load, verifier false/exception, duplicate keys, noncanonical bytes, wrong role/schema/row format, mapping/binding duplicates, and sealed-registry forgery/mutation rejection;
2. exact binding choice and all source/dataset/parser/version/mapping/exchange mismatches hard-fail before extraction;
3. BJ (`BJ430001`) duration fact extraction with full verified source lineage and correct raw scalar hash;
4. document/snapshot identity, request fingerprint, parser, source lineage, time/precision/evidence, bootstrap, and created-time failures hard-fail;
5. exact item/value row shape; unknown/missing/duplicate/nonnumeric/applicability issues, with no legacy or fuzzy fallback and deterministic facts/issues;
6. numeric raw type distinction, finite behavior, fact identity stability across created time and sensitivity to every scientific/evidence field;
7. fact `to_dict`/`from_dict` canonical roundtrip, exact-key/type/tampered-ID rejection, and direct-construction/mutation serialization rejection;
8. immutable issue details/no parser row sharing and legacy `FinancialFact` or legacy mapping isolation.

Run both:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_formal_financial_schema -v
.\.venv\Scripts\python.exe -m unittest tests.test_formal_financial_schema tests.test_financial_schema tests.test_financial_features -v
```

Record RED/GREEN/results in ignored `task-2-report.md`; do not stage it.
