# W1 interface audit — preparation only

Read-only audit by /root/stage_b_w1_interface_audit, refined after controller
question on owning-Store root authentication. No code changes or tests performed.
R4 has not been accepted; W1 is not dispatched. These recommendations must be
incorporated into the final task brief with explicit scope rulings before work.

## Store-owned planning authority

Direct factory(caller_binding) is insufficient. Existing formal_range_store.py
load_binding (112–140 at audited checkpoint) loads the authenticated registry
root and nine roles through its own StateStore/verifier, reconstructs bindings,
selects by exchange/binding hash, then requires source_binding(source) is the
reconstructed binding. Caller and reconstructed bindings can be semantically
equal but distinct objects. Keep exact factory-result identity against the
reconstructed binding, not caller identity.

Recommended internal load_binding_identity(store, *, registry_manifest_hash,
binding_hash, exchange) -> (binding, source). Existing persisted-payload loader
delegates to it; do not fabricate a task payload just to reuse that loader.
Narrow public resolve_planning_binding(binding) authenticates the caller via an
original-owner reader, resolves through owning Store graph, compares full
authenticated identity and returns the Store-reconstructed binding/source for
all minting. A genuine external binding whose root is absent in this Store must
fail preconditions, not fall through to ordinary missing coverage.

## Backward-compatible contract authority

Existing _range_binding_authority has exactly five captured anchors; Source and
Worker unpack five. Do not append fields. Add separate original-owner planning
authority exposing original type plus an immutable owner-read planning view:
market_config, calendar_config, registry_manifest_hash, source_registry_hash,
binding_hash, rule_id, exchange. Authenticate via current _binding_record and
read genuine _BindingRecord/_BindingsRecord, not replaceable public properties.
Identity comparison includes root/source-role/binding hashes, rule and exchange.
Both config snapshots are validated by the current owner check.

## Source selection and Worker budgets

Current Source captures only calendar config and one implementation record.
Market activation must eagerly seal both authenticated calendar and market
config/implementation records at construction. Select only via authenticated
request identity, never lazy reads of mutable registries or public properties.
Recommend range_config(request) returning the authenticated sealed config; the
same selector backs validation, fetch/replay, continuation and Worker budgets.
Worker currently uses calendar config for all requests; W1 must test genuine
market requests with intentionally distinct retry, cooldown and page budgets.

## F1 values and proof initialization

Closed calendar_record/market_window DTO validators belong inside the original
formal_policy_values owner and dependency checker. Values remain pure DTOs,
never proof registration or constructor bypass.
Calendar proof original-type/current/wire anchors must be captured by completed
eager Source/Market module initialization, then copied into each Source record.
No first-constructor lazy capture of replaceable public validators. Cover
source-first, market-first and fresh-process/restart import order.

## Recommended exact file scope (13 paths)

- ashare_pipeline/formal_policy_market.py (new)
- tests/test_formal_policy_market.py (new)
- ashare_pipeline/formal_range_source.py
- tests/formal_range_fixtures.py
- tests/formal_policy_runtime_fixtures.py
- ashare_pipeline/formal_policy_values.py
- tests/test_formal_policy_values.py
- ashare_pipeline/formal_range_store.py
- tests/test_formal_range_store.py
- ashare_pipeline/formal_range_worker.py
- tests/test_formal_range_worker.py
- ashare_pipeline/formal_range_contract.py
- tests/test_formal_range_contract.py

## Named integration checks

- Legacy binding authority remains five anchors.
- Planning authority returns current configs and complete binding identity.
- Replaced public properties cannot change original-owner identity.
- Forged, stale or mutated bindings fail.
- Genuine root absent from owning Store fails before missing classification.
- Semantically identical distinct binding instances resolve correctly.
- Factory receives Store-reconstructed binding; identity mismatch fails.
- Source eagerly seals distinct market/calendar implementations.
- Genuine market Worker uses market retry and page budgets.

The first audit suggested a simpler source_for_planning helper. That suggestion
is superseded by the Store-root-authenticated resolution above.

## Frozen membership boundary follow-up

Spec section2 assigns authenticated frozen-universe enumeration to the sole
FormalPolicyRepository batch entry (design:28–45). Section5.2 request schema
has no universe identity and the prescribed market_requests API accepts only
security_id and calendar proof. Calendar coverage cannot prove membership.
Current FormalMetricContextRepository.load_universe authentically rereads StateStore
and binds frozen_input_hash/universe_hash/security_ids/population_hash/source
receipts (formal_metric_context.py:194–215,256–269); recheck_batch rereads and
byte-compares it with industry evidence (277–287).

Coherent handoff: W3 obtains genuine Universe proof, privately iterates exactly
its canonical security_ids, passes those to W1, binds full universe identity
into evidence/result batch and performs final recheck_batch. Nonmember range
evidence cannot enter formal publication. Pre-batch acquisition/fixture orchestration
also enumerates genuine Universe membership. Lower Source validates security
syntax/exchange/config/calendar/request lineage but its request is acquisition
authority only, never a frozen-membership proof. Do not invent hidden Universe
authority in a calendar proof or infer frozen input from the Store.

If every genuine range request were required itself to attest membership, the
prescribed schema/API would be insufficient and would need an explicit genuine
Universe parameter. Root adopts the existing section2/W3-owned interpretation,
not that alternate contract. No additional W1 paths are needed.

W3 regression obligations: reads only verified universe members; genuine nonmember
range observation cannot enter batch; frozen_input_hash is reloaded, not trusted;
universe mutation during market reads revokes batch; extra stored nonmember data
is not enumerated; missing Universe fails before market selection.
