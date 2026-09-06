# V6 Task 5A binding brief — verified typed formal-feature repository

Plan: `docs/superpowers/plans/2026-09-04-formal-v3-financial-feature-pipeline.md`,
Task 5A. Tasks 1–5 are accepted through `3938b16`.

This task makes a persisted formal feature bundle safely readable after a
process restart. It does not collect data, parse documents, score securities,
write pools/reports, or implement Task 5B/Task 6. It must never manufacture a
trusted bundle from SQL JSON or use reflection/private closure state to forge a
Task 3 receipt.

## Scope and commit boundary

The plan lists the two new repository files. Its accepted Task 5 binding brief
also explicitly deferred a *public* durable Task 3 receipt-recovery API to
Task 5A. The scope is therefore exactly:

1. Create `ashare_pipeline/formal_feature_repository.py`.
2. Create `tests/test_formal_feature_repository.py`.
3. Modify `ashare_pipeline/formal_feature_store.py`.
4. Modify `tests/test_formal_feature_store.py`.

Do not modify `state_store.py`, Tasks 1–4, plans, data, SQLite/WAL/SHM, or
any other tracked file. Do not fetch or make network calls. Record RED/GREEN
only in the ignored `task-5a-report.md`; never stage reports, briefs,
ledgers, data, or progress artifacts. The pure-code commit subject is:

```text
feat: read verified formal feature bundles
```

## Public durable receipt recovery

Add this public method to the exact Task 3 `FormalFeatureBundleStore`:

```python
def recover_verified_receipt(
    self,
    *,
    bundle_path: str,
    manifest_path: str,
    bundle_hash: str,
    manifest_hash: str,
) -> FormalStoredFeatureBundle: ...
```

It is recovery of an existing immutable receipt, never a write. It accepts only
exact primitive canonical strings and lowercase SHA-256 hashes. It derives the
only valid paths from `self._paths(bundle_hash)` and requires byte-for-byte
string equality with both supplied paths. It constructs the sealed receipt
*inside the store's existing closure-private minting boundary*, immediately
calls public `read_verified(receipt)`, and returns it only after that complete
bundle/manifest/path/hash/canonical-header verification succeeds. It does not
write, repair, rename, replace, or create a file. A caller cannot pass paths
outside the configured root or use a matching filename under another root.

The repository may call this method and then `read_verified`; it must never
call a private store helper, `object.__new__`, closure reflection, or rewrite
content to obtain a receipt. A receipt recovered from a separate new
`FormalFeatureBundleStore` instance for the same root is valid only after the
same verification.

## Repository dependencies and current-input boundary

Export `FormalFeatureRepository`, `FormalFeatureCurrentInput`, and
`FormalFeatureCurrentInputProvider` from the new module. The repository is
constructed with exact `StateStore` and `FormalFeatureBundleStore`
instances, an explicit registry signature verifier, and an optional current
input provider:

```python
class FormalFeatureCurrentInputProvider(Protocol):
    def resolve_current_inputs(
        self,
        *,
        security_id: str,
        as_of_utc: str,
        template_id: str,
        registry_manifest_hash: str,
    ) -> FormalFeatureCurrentInput: ...

@dataclass(frozen=True, slots=True)
class FormalFeatureCurrentInput:
    security_id: str
    as_of_utc: str
    template_id: str
    registry_manifest_hash: str
    batch_id: str
    facts: tuple[FormalFinancialFact, ...]
    issues: tuple[FormalFactIssue, ...]
    complete: bool

class FormalFeatureRepository:
    def __init__(
        self,
        store: StateStore,
        bundle_store: FormalFeatureBundleStore,
        *,
        registry_signature_verifier: object,
        current_input_provider: FormalFeatureCurrentInputProvider | None = None,
    ) -> None: ...
```

The provider is an explicit injected trust dependency for **current** selection.
V6 deliberately did not persist the full Task 4 extraction-issue/input
manifest, so the repository cannot independently prove issue completeness. A
provider must give one finite, same-generation, complete candidate-fact and
issue snapshot; it must not provide an input hash or a prebuilt bundle.
`complete is True` is mandatory, and absence of a provider or an incomplete
snapshot is an error. There is no fallback to `issues=()`, latest SQL row,
or a guessed input hash.

The snapshot repeats all four request identity fields plus a nonempty canonical
`batch_id`; the repository requires exact equality to its request before it
reads any facts. The batch identifier supports auditing a one-generation
provider snapshot but is not treated as cryptographic proof of completeness.

The repository snapshots facts through their sealed `to_dict()` boundary and
requires their canonical multiset to equal exactly the current
`store.list_formal_financial_facts(security_id=...)` result, both before and
after the expected-bundle calculation. Thus the provider cannot hide,
substitute, duplicate, or invent persisted facts. Issues are checked as exact
sealed `FormalFactIssue` instances and re-read through their public
serialization boundary before building. Their exhaustiveness remains the
provider's explicit responsibility until a later task persists an input
manifest; a malicious or unavailable provider causes a fail-closed current
lookup rather than a fabricated current conclusion.

The verifier is required because the repository uses the public
`StateStore.get_formal_registry_manifest/blob` methods as the raw repository
for `FormalRegistryBundleLoader`. StateStore's own configured verifier must
also be present; the repository re-loads the exact root and all nine children
with the injected verifier, never accesses StateStore private attributes.

## Exact historical lookup

Implement:

```python
def get_verified_formal_feature_bundle(
    self, *, input_hash: str
) -> FormalFeatureBundle | None: ...
```

It validates the hash before any database/path access. It returns `None` only
when no V6 row exists. It re-reads the detached metadata row, recovers a
verified receipt using all four receipt fields, calls `read_verified`, then
re-reads the exact metadata row and requires byte-for-byte-equivalent canonical
metadata before returning a typed exact `FormalFeatureBundle`.

Compare the verified file bundle with every persisted header/value projection:
schema/contract/security/as-of/template/root/feature hashes/input hash,
history endpoints, comparable quarters, blockers, each sorted feature
value/evidence/missing field, bundle hash, manifest hash, and deterministic
paths. Re-load the stored registry root plus all children using
`FormalRegistryBundleLoader`; require the root hash, feature child hash and
the signed feature registry's source/mapping bindings, template slots, units,
and formula versions to agree with the file bundle and SQL projection. The
loader alone does not make a graph release-approved: explicitly require the
reloaded graph's official gate and the signed feature registry's release
eligibility. A structurally complete, validly signed test root or non-release
feature registry is never a typed score-eligible return.

For every file-bundle evidence entry, re-read
`store.list_formal_financial_facts(security_id=...)`, build an ID map, and
require exact equality to `FormalEvidenceRef.from_formal_fact(fact).to_dict()`.
Those StateStore reads revalidate the evidence fact, raw snapshot, receipt,
producer task, and lineage. Require evidence published/effective/source-update
times to be no later than the bundle cutoff (late capture remains allowed).
Missing, altered, duplicated, cross-security, future, or unverifiable evidence
rejects the typed read even if its SQL feature projection and stored JSON file
still agree.

“Stale manifest” means the stored root or any required child is absent,
tampered, unverified, wrongly bound, or incompatible with the returned bundle.
It does **not** mean a newer different root exists: a valid old immutable input
must remain readable by its exact historical `input_hash`.

This is a score-eligible typed read, not an audit metadata read. Reject a
bundle with nonempty blockers, any `blocked` slot, a required signed slot
that is not `derived`, a missing/unexpected signed slot, or an
`not_applicable` slot for an applicable Task 4 template slot. An optional
signed slot may be `missing` only with its canonical no-partial-evidence
contract. Blocked/missing audit rows remain in V6 but are never silently
promoted by this API.

The exact historical path verifies immutable storage, registry release
configuration, and each emitted source evidence chain. It cannot reconstruct
the complete historical Task 4 candidate set or extraction-issue manifest:
those were deliberately not persisted in V6. It must not claim that a
historical value has been freshly re-derived from every then-visible candidate
or use a fabricated empty issue list. Fresh semantic reauthentication belongs
to current selection below, which supplies a complete trusted input snapshot
to the unchanged Task 4 builder. This limitation is explicit in tests/report;
do not broaden the task with a new migration or invent historical defaults.

## Current lineage selection

Implement:

```python
def select_current_verified_formal_feature_bundle(
    self,
    security_id: str,
    as_of_utc: str,
    *,
    template_id: str,
    registry_manifest_hash: str,
) -> FormalFeatureBundle | None: ...
```

Before calling the provider or database, reject any template outside exactly
`bank`, `broker`, `general_nonfinancial`, `insurance`, and
`real_estate`, and exact-validate security, cutoff, and root hash. Load the
persisted verified root/all-child graph, construct the signed feature registry
from its verified feature child, and require source/mapping/feature root
binding. Invoke the provider once, snapshot its complete facts/issues, and
call the existing public `build_formal_feature_bundle` unchanged. Do not
copy Task 4's hash algorithm or select a latest row by timestamp.

The resulting bundle's `input_hash` is the one current expected identity.
Recheck the persisted fact multiset after construction; if it changed, reject
rather than race-select a mixed generation. Delegate to exact historical
lookup, require the returned bundle canonical bytes to equal the rebuilt
expected bundle, **then recheck the persisted fact multiset once more before
returning**. A correction that lands during exact file/SQL lookup therefore
rejects instead of returning a bundle that has become non-current. Return
`None` when that exact current input is not yet persisted. Multiple immutable
rows in the same security/as-of/template/root scope are historical lineages,
never duplicates.

## Required RED/GREEN proof

Start with absent recovery/repository APIs and record RED. Tests must cover:

1. public recovery after a new store instance, exact deterministic paths/hashes,
   no filesystem write, and rejection of forged/mutated receipt data, wrong
   root, noncanonical strings, path substitution, bundle tamper, manifest
   tamper, and header/hash mismatch;
2. exact historical typed retrieval and `None` for an absent input; full
   database-versus-file projection comparison, database reread race/tamper,
   evidence-fact/raw-snapshot/receipt deletion or tamper after persistence,
   root/child role/signature/binding/approval failures, valid-signature
   test-root/non-release child rejection, and retained old valid historical
   input after a later authoritative correction;
3. rejection of blocked bundles, blockers, required missing slots, unexpected
   slots/statuses, wrong unit/formula/evidence, and all legacy V1
   `FeatureBundle` paths;
4. current selection's template rejection before provider/database lookup,
  missing/incomplete provider failure, fact multiset mismatch/fact mutation
   rejection, request/batch mismatch, no default empty issues, full builder input-hash reuse, current
   correction selection, a correction during exact lookup caught by the final
   persisted-fact recheck, and missing expected input returning `None`; and
5. defensive snapshots/type/aliasing behavior for repository inputs and no
   private/reflective receipt construction.

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_formal_feature_repository tests.test_formal_feature_contract tests.test_formal_feature_store tests.test_state_store -v
```

Then compile all four scoped files and run `git diff --check`. Do not claim
the provider solves historical issue reconstruction; that is explicitly out of
scope and remains fail-closed.
