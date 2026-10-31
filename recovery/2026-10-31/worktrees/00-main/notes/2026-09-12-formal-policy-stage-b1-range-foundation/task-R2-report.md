# Task R2 implementation report

## Status

Implemented and locally verified bounded signed calendar-range requests, genuine
range selection, sealed transport/parser/normalizer execution, authenticated raw
fetch manifests, and replay parsing. No Git writes, production network, production
data, database writes, signatures, scoring, merge, or push were performed.

Task base was `f4ed417fe6e64e324e9c725c3b185f7a10c52221`.

## TDD evidence

### Initial RED

Command:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_range_source -v
```

Exit code: `1`.

Output excerpt:

```text
ImportError: Failed to import test module: test_formal_range_source
ModuleNotFoundError: No module named 'ashare_pipeline.formal_range_source'
Ran 1 test in 0.000s
FAILED (errors=1)
```

This was the expected missing-interface failure before production code existed.

### Timing/DTO regression RED

Command:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_range_source.FormalRangeSourceTests.test_late_capture_and_late_publication_are_preserved_as_observations tests.test_formal_range_source.FormalRangeSourceTests.test_unproven_date_only_effective_time_stays_explicitly_unresolved -v
```

Exit code: `1`; `2` tests; `30.148s`.

Output excerpt:

```text
ValueError: parsed range document has unknown or missing keys
Ran 2 tests in 30.148s
FAILED (errors=2)
```

The production change required to pass was the closed source-version/timing schema,
late-observation preservation, and explicit unresolved `date_only` representation.

### Exact implementation-registry identity RED

Command:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_range_source.FormalRangeSourceTests.test_implementation_key_and_method_identities_are_sealed -v
```

Exit code: `1`; `1` test; `23.995s`.

Output excerpt:

```text
AssertionError: FormalTerminalSourceError not raised
Ran 1 test in 23.995s
FAILED (failures=1)
```

The mutation replaced a registered value tuple with a distinct tuple containing
the same parser and normalizer objects. Equality-based snapshot comparison missed
the replacement; exact registered value-object identity was then enforced.

### Targeted GREENs

Timing/DTO command above: exit `0`, `2/2` tests, `26.272s`, `OK`.

Exact implementation identity command above: exit `0`, `1/1` test, `28.311s`,
`OK`.

Focused R2 command:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_range_source -v
```

Exit `0`, `23/23` tests, `420.231s`, `OK`. That run exposed only test-fixture
`TemporaryDirectory` cleanup warnings on deliberately rejected constructors. The
fixture was made wholly in-memory; the final compatibility run below was clean.

### Final prescribed compatibility GREEN

Command on final frozen code:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_range_source tests.test_formal_sources tests.test_formal_range_contract -v
```

Exit code: `0`.

Output summary:

```text
Ran 79 tests in 532.242s
OK
```

No warnings or errors were emitted.

### Import-order/cycle checks

Five independent short processes imported each of these first, then imported both
range source modules:

```text
ashare_pipeline.formal_sources exit=0
ashare_pipeline.formal_range_source exit=0
ashare_pipeline.formal_range_contract exit=0
ashare_pipeline.formal_context_schema exit=0
ashare_pipeline.formal_registry_manifest exit=0
```

The concrete rejected design cycle was:

```text
formal_context_schema (before _descriptor exists)
  -> formal_sources eager reverse import
  -> formal_range_source
  -> formal_range_contract
  -> formal_context_schema._descriptor ImportError
```

The controller-approved solution is `formal_range_request.py`, a pure request
authority depending only on the standard library and `formal_range_format`. Both
consumers capture its exact type and closure verifier at module initialization.
There is no registration callback, no first-call lazy public alias, and therefore
no pre-registration takeover surface.

## Changed task files

1. `ashare_pipeline/formal_range_request.py` (new, approved minimal split)
2. `ashare_pipeline/formal_range_source.py` (new)
3. `ashare_pipeline/formal_sources.py`
4. `ashare_pipeline/formal_range_contract.py` (approved read-only source hash getter)
5. `tests/formal_range_fixtures.py`
6. `tests/test_formal_range_source.py` (new)

This report is the required non-product task artifact. Concurrent F2/root changes
visible in the shared worktree were not edited or included in R2 scope.

## Frozen SHA-256 hashes

Final task files:

```text
ashare_pipeline/formal_range_request.py  980a1c0e3442dc31de20b2df86d4294b9a0476dab99534e86dd8dc5d5bad861e
ashare_pipeline/formal_range_source.py   6405b7cb72a3f28611d6a1e7238ae75261c313eb9340949ca4f63236f8eb6cde
ashare_pipeline/formal_sources.py        4a71b04404c4bccf2dc46b35bb749ec848424394867857d9234483de338291be
ashare_pipeline/formal_range_contract.py b63e16e72e0ac47e3db1b9ccc6063756660db255e9bf8e4cf2b0d30b5299c190
tests/formal_range_fixtures.py           f78604ab0bd889902f95924b7b0e3f9ca0d0bbc3ba6fb48835abbcac26412d3c
tests/test_formal_range_source.py        07954d87fdf34db84d4f1871970df30aa2c4794c9ee69765131312fda265dc66
```

Accepted pure R1 format was not modified:

```text
ashare_pipeline/formal_range_format.py
baseline/current c6f3504f5b65bdbaaf3ed21d8c7d4f3cae58748ea5f449fa2cfcc6b442a2e517
```

Authorized modifications had these task-base hashes:

```text
ashare_pipeline/formal_sources.py        d854aa889eb3143f44f3fbb855dd7f00fb5f078b535f59f83f82b0e6fa6309f4
ashare_pipeline/formal_range_contract.py 5f646aca4332e6a9287e3e7e7fe99dbc7a0487a14d405580776a267fb2898746
tests/formal_range_fixtures.py           12ce3232bef49b6cc59b9ee849692199e205bad4e5f920e3b533a82bb4b80e5b
```

`git diff --check` over modified tracked R2 files exited `0` (only the repository's
line-ending notices were printed).

## Exact R3/W1 handoff contracts

### Request identity

`FormalRangeRequestV1.to_dict()` returns a detached object with exactly:

```text
schema_version, kind, source, dataset, security_id, exchange, as_of_utc,
start_date, end_date, anchor_descriptor_id, calendar_descriptor_id,
range_config_id, registry_manifest_hash, page_index, calendar_coverage_hash
```

`request_fingerprint` is SHA-256 of canonical bytes for all those wire fields.
Construction, copy, subclass substitution, field mutation, stale binding/config,
and source dependency replacement do not mint authority.

The private request seal additionally stores `source_registry_hash`; it is not a
wire field. The request's manifest root is revalidated through its live sealed
`RangeBinding`. `SignedSourceRegistry.select_range` compares its genuine
`registry_hash` to the private source hash, then compares the complete selected
config and anchor identities. A byte-identical complete source blob may be reused
by different valid manifest roots; a changed source blob is rejected even when the
selected ENTRY is byte-identical.

### Implementation registry

Constructor contract:

```text
implementations: exact dict
key: (parser_id, parser_version, mapping_version,
      normalizer_version, request_version)
value: exact (parser, normalizer) tuple
```

Parser call:

```python
parser.parse(raw_bytes, *, request=<detached request dict>,
             config=<detached complete RangeConfig dict>) -> dict
```

Normalizer call:

```python
normalizer.normalize(parsed, *, request=<detached request dict>,
                     config=<detached complete RangeConfig dict>) -> dict
```

The dict, every registered value tuple, selected objects, and their actual method
anchors are captured at construction and rechecked before and after execution.
Self-reported versions and per-call callbacks confer no authority.

### ParsedRangeDocumentV1 wire

`ParsedRangeDocumentV1.from_dict(wire)` is intentionally unprivileged and
`.to_dict()` returns a detached copy. Its exact top-level keys are:

```text
schema_version, request_fingerprint, source, dataset, security_id, exchange,
start_date, end_date, parser_id, parser_version, mapping_version,
normalizer_version, request_version, published_at_utc, published_precision,
source_updated_at_utc, effective_at_utc, effective_time_evidence_hash,
captured_at_utc, upstream_generation, pagination_evidence, page_index,
page_count, record_count, page_record_count, coverage, rows
```

`record_count` is the source-declared total; `page_record_count` must equal the
actual ordered row count. `pagination_evidence` is accepted as
`signed_single_response_v1` only for a signed single-response config and as
`source_declared_numbered_pages_v1` only for a registered numbered-page parser.
The DTO cannot self-authorize a pagination basis.

`coverage` has exact keys `start_date/end_date/complete`. Empty rows cannot claim
complete coverage. Every row preserves
`published_at_utc/published_precision/effective_at_utc/effective_time_evidence_hash/captured_at_utc`
and forbids `effective_trade/stale_days/pool_veto/confirmed_no_price`.

Late capture and late publication remain authenticated observations; R2 does not
turn them into freeze-visible facts. `date_only` may preserve an unresolved
`effective_at_utc=None/effective_time_evidence_hash=None` pair. R3 must revalidate
calendar/effective-time evidence and classify visibility/pending. Document-level
times are not defaults for rows. `upstream_generation` is opaque identity; R3 must
use source-declared `published_at_utc`/`source_updated_at_utc` semantics for leading
version selection, never lexical generation, capture time, or insertion order.

### RangeFetch manifest

`RangeFetch` is closure-minted and sealed. `to_manifest()` returns exact fields:

```text
schema_version, request_fingerprint, range_config_id, registry_manifest_hash,
source, dataset, original_url, content_sha256, captured_at_utc, parser_id,
parser_version, mapping_version, normalizer_version, request_version,
published_at_utc, published_precision, source_updated_at_utc, effective_at_utc,
effective_time_evidence_hash, upstream_generation, pagination_evidence,
record_count, page_record_count, page_count
```

Replay checks content hash, URL host, request/config/root/source identities, all
implementation versions, capture time, and every document source-version/pagination
field against a fresh execution of the sealed parser and normalizer.

## Self-review and concerns

- The request constructor and fetch constructor are closed; the parsed DTO is not
  authority by design.
- Exact bool/int, canonical ISO lower bound, frozen end, request/config/anchor/source
  identity, redirects, 403/429/challenge/retryable statuses, pagination limits,
  counts, range/security mismatches, request copying/mutation, and implementation
  replacement are covered by behavior tests using real graph objects.
- Network I/O occurs only after binding/config/template preflight and no database
  transaction is opened by this layer.
- R2 intentionally does not mint previous chunks, next pages, or market requests.
  R3/W1 must use the same private request-authority module rather than add a public
  arbitrary request factory.
- `upstream_generation` is preserved but is not intrinsically sortable. R3 needs
  source-specific leading-version rules based on authenticated source timestamps.
- Visibility and effective-time proof remain downstream evidence decisions. A
  successfully parsed observation is not by itself a current receipt or policy fact.

## Fix round 1 — review `38644671691e244164c267b07732d9756a06142e`

This section supersedes the earlier description of request authority living in a
pure standalone module. Under the controller's fix-round ruling,
`formal_range_source` now owns the genuine request type, request registry, private
first-calendar mint closure, and the closure-installed `select_range` method.
`formal_range_request` is compatibility re-export only. No public or private
callable arbitrary request/fetch mint remains after source-module initialization.

### RED evidence

The four review exploits plus exact bound mutation were first exercised together:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest `
  tests.test_formal_range_source.FormalRangeSourceTests.test_module_private_mint_cannot_authorize_arbitrary_bounds_or_boolean_page `
  tests.test_formal_range_source.FormalRangeSourceTests.test_genuine_request_seal_rejects_every_out_of_contract_bound `
  tests.test_formal_range_source.FormalRangeSourceTests.test_source_instance_rejects_other_manifest_root_even_for_shared_source_blob `
  tests.test_formal_range_source.FormalRangeSourceTests.test_source_instance_rejects_other_complete_source_blob_with_same_selected_entry `
  tests.test_formal_range_source.FormalRangeSourceTests.test_instance_parse_shadow_cannot_bypass_registered_fetch_implementation `
  tests.test_formal_range_source.FormalRangeSourceTests.test_instance_parse_shadow_cannot_bypass_registered_replay_implementation `
  tests.test_formal_range_source.FormalRangeSourceTests.test_range_fetch_seal_distinguishes_boolean_from_every_integer_manifest_field -v
```

Output: `Ran 7 tests in 141.184s`; `FAILED (failures=8, errors=2)`;
exit code `1`. The arbitrary module mint was accepted; both cross-root/source
fetch attempts reached transport; instance `_parse` shadows replaced registered
dispatch on fetch and replay; and all three integer manifest fields accepted
boolean mutation. The genuine sealed-request bound mutations were already rejected.

The first implementation also exposed a partial-initialization substitution:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_range_source.FormalRangeSourceTests.test_source_initialization_uses_genuine_registry_and_binding_anchors -v
```

Output: `Ran 1 test in 0.185s`; `FAILED (failures=1)`; exit code `1`.
The fresh process reached the substituted `FakeBinding` and failed with its missing
`calendar_config`, proving public class/method aliases were still trusted.

Finally, after moving mint authority into source-owned closures, the external-mint
regression was tightened to require both mint globals to disappear:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_range_source.FormalRangeSourceTests.test_range_fetch_cannot_be_externally_minted -v
```

Output: `Ran 1 test in 0.000s`; `FAILED (failures=1)`; exit code `1`, because
`_mint_fetch` remained callable before final closure capture/deletion.

### GREEN evidence

The seven exploit/bound tests above were rerun with the identical command.
Output: `Ran 7 tests in 103.067s`; `OK`; exit code `0`.

The genuine-anchor fresh-process regression was rerun with its identical command.
Output: `Ran 1 test in 6.058s`; `OK`; exit code `0`.

The mint-visibility regression was rerun with its identical command.
Output: `Ran 1 test in 0.000s`; `OK`; exit code `0`.

The final frozen R2 module run was:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_range_source -v
```

Output: `Ran 31 tests in 643.039s`; `OK`; exit code `0`. This run includes
fresh-process first imports of `formal_sources`, `formal_range_request`,
`formal_range_source`, `formal_range_contract`, `formal_context_schema`, and
`formal_registry_manifest`; pre-first-use public class/method substitution; normal
select/fetch/replay paths; both cross-root source-instance boundaries; parser shadow
resistance; exact request bounds; and numeric seal mutation. Per controller ruling,
no additional compatibility suite was started; root owns the final seven-module
joint run against these frozen hashes.

### Findings disposition and authority boundary

- **Arbitrary guard mint authority — fixed.** The only request mint is a closure
  captured by the genuine `FormalRangeSource` factory. It accepts an exact genuine
  live `RangeBinding`, computes freeze/start/end/page values itself, records the
  complete signed config, manifest root, and source blob hash, and revalidates the
  captured genuine binding anchors. `formal_range_request` cannot register or mint.
- **Mutable `self._parse` bypass — fixed.** Fetch and replay call the class's
  constructor-time captured parser dispatcher; instance shadowing cannot replace it.
  Registered parser/normalizer objects and method identities remain checked around
  execution.
- **Missing source-instance root/source match — fixed.** Registry selection still
  permits a byte-identical complete source blob to be referenced by different valid
  manifest roots. Source execution is stricter: both fetch and replay require the
  request's sealed manifest root and full source registry hash to match the receiving
  source binding before transport/parsing, while live binding checks also run during
  parser/normalizer execution.
- **Boolean/integer fetch seal equality — fixed.** Every sealed `RangeFetch` slot is
  compared by exact type and value, so `True` cannot stand in for integer `1` in
  `record_count`, `page_record_count`, or `page_count`.

The genuine `SignedSourceRegistry` and `RangeBinding` types plus their original
verification/getter methods are captured by closure authorities immediately after
their factories complete. `formal_range_source` consumes those anchors eagerly and
installs a closure-captured `select_range` only on the genuine registry class; there
is no installer, registration callback, weak temporary method, or first-call alias
capture. Request wire fields and public APIs remain unchanged.

### Frozen file hashes and self-review

SHA-256 after the final 31-test run:

```text
ashare_pipeline/formal_range_request.py  26127464DD54F1FAD00E1882FED639835F5FD44BDB42D6EFB08CBA6F37DD9759
ashare_pipeline/formal_range_source.py   F852E8B769944948CCEBAA43000E8F257B31C428F17C5D9BAC1D2F91DC02F0D5
ashare_pipeline/formal_sources.py        A326D149C748216C72FF9ACFBA54AD791064ECD3C0A8432F0B90837E3C36EB08
ashare_pipeline/formal_range_contract.py E1BA8CF8FDF16EA60CE2B7D8EF6D9993CC431F3CBDB3C26F46854734AD5F8D66
tests/formal_range_fixtures.py           F78604AB0BD889902F95924B7B0E3F9CA0D0BBC3BA6FB48835ABBCAC26412D3C
tests/test_formal_range_source.py        21D9F719F1FA8D2AF78FD585DFEFB27C222C646BE98F2720DC8CD194477E2835
```

`git diff --check` over all six whitelisted files exited `0`; its only output was
the existing Windows LF-to-CRLF conversion warnings. Five files differ from the
review base (`formal_range_fixtures.py` is unchanged), with `467 insertions` and
`216 deletions`. Read-only diff review found no remaining instance-dispatch,
cross-binding, bool/int-equality, arbitrary-mint, import-cycle, wire-shape, or public
API regression. The six files are frozen for root's independent review/joint run.

### Captured complete final run output

The following is the retained combined stdout/stderr from the final 31-case command,
collated in order from the original yielded process chunks (not rerun):

```text
test_backward_interval_is_inclusive_and_stops_at_iso_floor (tests.test_formal_range_source.FormalRangeSourceTests.test_backward_interval_is_inclusive_and_stops_at_iso_floor) ... ok
test_empty_response_does_not_claim_complete_coverage (tests.test_formal_range_source.FormalRangeSourceTests.test_empty_response_does_not_claim_complete_coverage) ... ok
test_fetch_and_snapshot_parse_bind_content_and_manifest (tests.test_formal_range_source.FormalRangeSourceTests.test_fetch_and_snapshot_parse_bind_content_and_manifest) ... ok
test_first_calendar_request_needs_no_existing_calendar (tests.test_formal_range_source.FormalRangeSourceTests.test_first_calendar_request_needs_no_existing_calendar) ... ok
test_genuine_request_seal_rejects_every_out_of_contract_bound (tests.test_formal_range_source.FormalRangeSourceTests.test_genuine_request_seal_rejects_every_out_of_contract_bound) ... ok
test_identical_source_blob_can_be_reused_by_a_different_manifest_root (tests.test_formal_range_source.FormalRangeSourceTests.test_identical_source_blob_can_be_reused_by_a_different_manifest_root) ... ok
test_implementation_key_and_method_identities_are_sealed (tests.test_formal_range_source.FormalRangeSourceTests.test_implementation_key_and_method_identities_are_sealed) ... ok
test_import_orders_have_no_registration_hook_or_partial_cycle (tests.test_formal_range_source.FormalRangeSourceTests.test_import_orders_have_no_registration_hook_or_partial_cycle) ... ok
test_instance_parse_shadow_cannot_bypass_registered_fetch_implementation (tests.test_formal_range_source.FormalRangeSourceTests.test_instance_parse_shadow_cannot_bypass_registered_fetch_implementation) ... ok
test_instance_parse_shadow_cannot_bypass_registered_replay_implementation (tests.test_formal_range_source.FormalRangeSourceTests.test_instance_parse_shadow_cannot_bypass_registered_replay_implementation) ... ok
test_late_capture_and_late_publication_are_preserved_as_observations (tests.test_formal_range_source.FormalRangeSourceTests.test_late_capture_and_late_publication_are_preserved_as_observations) ... ok
test_module_private_mint_cannot_authorize_arbitrary_bounds_or_boolean_page (tests.test_formal_range_source.FormalRangeSourceTests.test_module_private_mint_cannot_authorize_arbitrary_bounds_or_boolean_page) ... ok
test_old_and_new_request_placeholders_cannot_cross (tests.test_formal_range_source.FormalRangeSourceTests.test_old_and_new_request_placeholders_cannot_cross) ... ok
test_page_successor_requires_source_backed_exact_page_identity (tests.test_formal_range_source.FormalRangeSourceTests.test_page_successor_requires_source_backed_exact_page_identity) ... ok
test_parser_cannot_mutate_config_or_request_during_execution (tests.test_formal_range_source.FormalRangeSourceTests.test_parser_cannot_mutate_config_or_request_during_execution) ... ok
test_parser_output_identity_page_and_counts_must_match (tests.test_formal_range_source.FormalRangeSourceTests.test_parser_output_identity_page_and_counts_must_match) ... ok
test_range_fetch_cannot_be_externally_minted (tests.test_formal_range_source.FormalRangeSourceTests.test_range_fetch_cannot_be_externally_minted) ... ok
test_range_fetch_seal_distinguishes_boolean_from_every_integer_manifest_field (tests.test_formal_range_source.FormalRangeSourceTests.test_range_fetch_seal_distinguishes_boolean_from_every_integer_manifest_field) ... ok
test_redirect_challenge_and_blocking_statuses_are_not_evidence (tests.test_formal_range_source.FormalRangeSourceTests.test_redirect_challenge_and_blocking_statuses_are_not_evidence) ... ok
test_request_cannot_be_constructed_copied_or_mutated_into_authority (tests.test_formal_range_source.FormalRangeSourceTests.test_request_cannot_be_constructed_copied_or_mutated_into_authority) ... ok
test_request_dates_and_freeze_are_closed (tests.test_formal_range_source.FormalRangeSourceTests.test_request_dates_and_freeze_are_closed) ... ok
test_rows_require_visibility_fields_and_forbid_policy_conclusions (tests.test_formal_range_source.FormalRangeSourceTests.test_rows_require_visibility_fields_and_forbid_policy_conclusions) ... ok
test_select_range_accepts_only_matching_genuine_request (tests.test_formal_range_source.FormalRangeSourceTests.test_select_range_accepts_only_matching_genuine_request) ... ok
test_select_range_rejects_changed_source_blob_even_when_entry_is_identical (tests.test_formal_range_source.FormalRangeSourceTests.test_select_range_rejects_changed_source_blob_even_when_entry_is_identical) ... ok
test_select_range_rejects_different_config_and_root_identity (tests.test_formal_range_source.FormalRangeSourceTests.test_select_range_rejects_different_config_and_root_identity) ... ok
test_source_initialization_uses_genuine_registry_and_binding_anchors (tests.test_formal_range_source.FormalRangeSourceTests.test_source_initialization_uses_genuine_registry_and_binding_anchors) ... ok
test_source_instance_rejects_other_complete_source_blob_with_same_selected_entry (tests.test_formal_range_source.FormalRangeSourceTests.test_source_instance_rejects_other_complete_source_blob_with_same_selected_entry) ... ok
test_source_instance_rejects_other_manifest_root_even_for_shared_source_blob (tests.test_formal_range_source.FormalRangeSourceTests.test_source_instance_rejects_other_manifest_root_even_for_shared_source_blob) ... ok
test_transport_request_uses_only_new_placeholders_and_signed_bounds (tests.test_formal_range_source.FormalRangeSourceTests.test_transport_request_uses_only_new_placeholders_and_signed_bounds) ... ok
test_unproven_date_only_effective_time_stays_explicitly_unresolved (tests.test_formal_range_source.FormalRangeSourceTests.test_unproven_date_only_effective_time_stays_explicitly_unresolved) ... ok
test_unregistered_or_self_reported_implementation_is_rejected (tests.test_formal_range_source.FormalRangeSourceTests.test_unregistered_or_self_reported_implementation_is_rejected) ... ok

----------------------------------------------------------------------
Ran 31 tests in 643.039s

OK
```
