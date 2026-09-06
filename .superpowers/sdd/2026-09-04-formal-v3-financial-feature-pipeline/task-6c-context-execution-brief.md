# Task 6C — lease-fenced formal Context execution

## Scope

This delivery implements execution of already-enqueued `formal_context` tasks.
It may modify **only**:

- `ashare_pipeline/formal_deep_worker.py`
- `tests/test_formal_deep_worker.py`

No StateStore/context-schema/context-repository migrations, production source
defaults, data collection, data/SQLite artifacts, network calls, staging, or
commits are permitted in the implementer phase.

## Binding decisions

1. A Context task is authenticated by re-resolving a fresh sealed
   `FormalContextRequest` with the StateStore-configured registry verifier,
   then requiring the reconstructed payload, `FormalTaskSpec`, canonical
   payload, idempotency key, refresh generation, and prerequisite edges to
   equal the leased row. It must never reconstruct a capability directly from
   persisted JSON.
2. Context generation is resolver-owned
   `formal-context-refresh-generation-v1`; do **not** apply
   `derive_collection_refresh_generation`, which is for statement/universe
   collection semantics and produces a different hash.
3. Normalizers are an explicit trusted injection on
   `FormalWorkerDependencies`, keyed by the freshly sealed request's signed
   `normalizer_version`. The default is an immutable empty mapping for
   backward-compatible statement/feature callers. Missing, duplicate,
   non-exact, or wrong-version entries fail closed; no fallback or direct
   `normalizer.normalize` call is allowed. Load `FormalContextRegistry` only
   using the exact configured StateStore and its configured signature verifier;
   do not add an arbitrary registry loader capability.
4. Dispatcher priority is fixed: ready `formal_statement`, then ready
   `formal_context`, then ready `formal_feature_build`. This preserves 6B1
   statement priority while allowing an unblocked calendar bootstrap to run
   before date-only dependents become leaseable.
5. One Context task represents exactly one declared identity. The sealed
   normalization receipt must contain exactly one fact before persistence.
   Success does not enqueue feature work or alter statement/feature counters.
6. Context completion uses a closed, worker-constructed audit map (no paths,
   raw callback data, or exception text):
   `kind`, `context_kind`, `scope_key`, `security_id`, `as_of_utc`,
   `registry_manifest_hash`, `refresh_generation`, `descriptor_id`,
   `normalizer_version`, `snapshot_id`, `manifest_sha256`,
   `source_content_sha256`, `parser_id`, `parser_version`, `mapping_version`,
   `fact_id`, `normalization_input_hash`.
7. V6 feature input/builds remain context-free. No market/industry/regulatory/
   event/consensus/calendar fact enters a V6 feature payload, generation,
   bundle, or score.

## Required execution ordering

For a leased Context task:

```text
re-resolve sealed request + exact task/spec/payload validation
  -> reload matching official runtime/source configuration
  -> existing receipt: verified snapshot/raw replay only
     no receipt: lease fence -> circuit check/fetch -> leased raw persist
  -> require exact receipt/snapshot/request/generation lineage
  -> verified raw read + signed parser replay
  -> lease fence -> FormalContextRegistry.normalize_verified
  -> exactly one fact -> lease fence -> StateStore.put_formal_context_facts
  -> lease fence -> closed completion result -> complete
```

The normalizer and StateStore already perform their own writer-lease checks;
the worker adds fences before and after externally expensive or mutable stages.
Lost ownership stops immediately with no terminal/retry conversion and leaves
the immutable raw receipt / idempotent context row for the next owner. On
recovery, re-normalize the verified raw evidence and idempotently put the same
fact; do not call public Context reads while the producer is leased.

For date-only Context configurations, fresh request re-resolution must bind
the exact current signed calendar binding and exact prerequisite edge. A
timestamp-only Context request has neither. Missing/mismatched/stale binding,
payload/root/descriptor/source/parser/mapping/generation mismatch, malformed
receipt/raw/parser drift, missing normalizer, wrong normalizer version, empty
or multi-fact normalization, and persistence conflict are terminal with zero
new transport as applicable.

Source blocked/challenge maps to retryable `source_blocked` plus signed circuit
cooldown; transient source failures map to retryable `source_retryable_failed`;
terminal source failures map to `context_terminal_source_error`; local
provenance/normalization/persistence errors map to
`context_validation_failed`. Retain an existing raw receipt on terminal work.
Always renew immediately before a circuit state mutation after a callback.

## Required RED/GREEN tests

- timestamp Context happy path: one remote fetch, one verified context fact,
  exact closed result, no feature task/fact/quarter/bundle mutation;
- raw-receipt replay and DB-before-completion recovery: zero second transport,
  idempotent context persistence, then completion;
- valid date-only bootstrap calendar then dependent Context: exact edge/binding
  and raw-storage binding bridge succeed; missing/substituted binding fails
  before transport;
- malformed payload/spec, stale resolver generation/root/roles, runtime source
  config mismatch, forged receipt or raw/parser drift terminalize before any
  Context fact write;
- normalizer missing/wrong version/empty/multiple/error fail closed, no
  fabricated `no_coverage`;
- source blocked/retryable/terminal mapping and circuit behavior;
- lost lease before fetch/persist, after raw receipt, after normalization,
  after Context DB put, and at completion: no stale terminal/result, next
  owner recovers exactly once;
- two security/scope/template-independent Context tasks cannot consume each
  other's receipt, fact, normalizer or task state; success/failure leaves V6
  financial feature scheduling untouched.

Use hermetic injected transport, signed fixture blobs, and temporary project
directories only. Before any production edit, add/run an execution test that
fails because `formal_context` is not yet leaseable; retain test command/output
in the report. Final checks: focused worker module, context schema/repository
tests, StateStore tests, compilation, and diff check.
