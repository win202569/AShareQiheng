# V6 Task 1 report — injected official source adapter and registry boundary

## Scope and commit boundary

Implemented only the four approved tracked files:

- `ashare_pipeline/formal_sources.py`
- `ashare_pipeline/formal_registry_manifest.py`
- `tests/test_formal_sources.py`
- `tests/test_formal_registry_manifest.py`

No production endpoint, parser, HTTP client, registry default, snapshot write, SQL access,
SQLite/data/WAL/SHM, or progress artifact was introduced.  Production source configuration
remains absent and collection is blocked unless a caller injects a valid signed registry,
authoritative policy, parser, transport, resolver, loaded root hash, and source-registry hash.

## TDD evidence

Initial RED command:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_formal_sources tests.test_formal_registry_manifest -v
```

It failed as intended with two import errors because both new modules were absent:
`ModuleNotFoundError: ashare_pipeline.formal_sources` and
`ModuleNotFoundError: ashare_pipeline.formal_registry_manifest`.

One later targeted RED/GREEN cycle caught a concrete transport construction defect: a signed
endpoint that already contained `?fixed=yes` was incorrectly joined with another `?`; the
new test failed with `...?fixed=yes?period=...`, then passed after canonical query joining
was corrected to `...?fixed=yes&period=...`.

Final GREEN session:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_formal_sources tests.test_formal_registry_manifest tests.test_formal_evidence tests.test_sources -v
```

Result: 49 tests passed.

Compilation:

```powershell
.\.venv\Scripts\python.exe -m py_compile ashare_pipeline/formal_sources.py ashare_pipeline/formal_registry_manifest.py tests/test_formal_sources.py tests/test_formal_registry_manifest.py
```

Result: passed.

Post-audit focused verification (`tests.test_formal_sources` and
`tests.test_formal_registry_manifest`) passed 24 tests after the signed-outer-binding,
source-root-hash, bootstrap-scope, replay-tampering, and construction-hardening checks were
added.  The staged scope check contained exactly the four approved tracked files, and
`git diff --check cc4227e..HEAD` passed after commit.

## Wire and trust-boundary rulings implemented

- Source registries are UTF-8, duplicate-key-free canonical JSON signed over their exact
  bytes.  They have no default instance, cannot be directly constructed around an unverified
  dataclass payload, and contain only the five approved official source identities.
- All request transport is injected.  Response bytes are preserved unchanged; redirects,
  hosts, challenge pages, timeouts, and non-2xx outcomes are classified before parsing.
- Date-only publications use exactly `YYYY-MM-DDT00:00:00+00:00`, invoke the injected
  exchange-close resolver, and pass the same verified binding to V5 evidence verification.
  Timestamp documents forbid calendar bindings.
- The adapter validates every objectively available calendar fact: canonical binding hashes,
  root, freeze, exchange, selector hash, and canonical prerequisite UUID.  It cannot prove
  that a valid prerequisite UUID is the caller task's exact stored dependency because its
  public API receives no task-edge parameter; V6's typed worker owns that later edge
  comparison.  It also cannot manufacture a selected calendar snapshot from a selector.
- Bootstrap calendar collection is limited to a signed global timestamp configuration with
  `calendar_selector=None`, `exchange_scope=None`, a null binding, and an `OfficialRequest`
  with null exchange/security identity.
- A loaded root must pass its exact `source_registry_hash` to the adapter, and the adapter
  rejects any mismatch with `SignedSourceRegistry.registry_hash`.
- Child registry canonical bytes deliberately do **not** embed the root hash, since the root
  itself contains each child SHA-256 and doing both would require a cryptographic fixed point.
  Instead `VerifiedRegistryBlob` carries a separately signed outer binding: canonical UTF-8
  JSON `{"child_sha256":...,"registry_manifest_hash":...,"registry_role":...}`.  The loader
  recreates those exact bytes, verifies the injected signature, and requires all three fields
  to match the rehashed child, loaded root, and expected role.  This is a real signed
  bidirectional link without a root/child hashing cycle.
