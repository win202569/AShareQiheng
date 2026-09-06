# Task 2 Report — Byte-Preserving Formal Snapshot Store

## Result

Implemented and committed `f69709a` (`feat: add byte-preserving formal snapshot store`).
The commit contains only the requested production module and hermetic tests:

- `ashare_pipeline/formal_snapshot_store.py`
- `tests/test_formal_snapshot_store.py`

This report is deliberately uncommitted because the task required the commit to contain only Task 2 code/tests.

## Implementation

`FormalSnapshotStore` consumes Task 1's `OfficialFetch` and
`EvidenceVerification`, refusing unverified or content-hash-mismatched evidence.
It writes the fetched bytes unchanged at:

`<root>/data/raw/formal/<source>/<dataset>/<content_sha256>.bin`

The store writes a separate canonical JSON envelope at:

`<root>/data/raw/formal/<source>/<dataset>/<manifest_sha256>.manifest.json`

The raw byte field is represented by the separately stored content and its
`content_sha256`; the manifest contains the complete remaining fetch metadata,
the complete request, verification status/reasons/effective time, optional task
provenance, and the content hash.  The manifest hash is calculated from the
canonical payload before adding its `manifest_sha256` envelope field, avoiding a
self-hash.  Thus identical bytes share only a `.bin`, while a new refresh
generation or producing task produces a distinct lineage manifest.

Both content and manifests use sibling `.part` files, binary flush plus
`fsync`, validation before publish, and `os.replace` for atomic replacement.
Failure cleanup removes only the owned `.part`.  Reads validate the selected
content and selected manifest paths, both stored hash values, the derived
canonical manifest payload hash, expected source/dataset/hash filenames, and
verified manifest status.  The module has no network operations and does not
import or couple to legacy `SnapshotStore`.

## Tests and TDD Evidence

Before the production module existed, I added the focused tests and ran:

```powershell
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m unittest tests.test_formal_snapshot_store -v
```

RED result: expected `ModuleNotFoundError: No module named
'ashare_pipeline.formal_snapshot_store'` while importing the missing store.

After the minimal implementation, the same command was GREEN: 6 tests passed.
They cover non-UTF-8 binary round trip without JSON re-encoding, content and
manifest tamper rejection, `.part` absence after the corrupt-content read,
content deduplication with distinct generation manifests, manifest provenance,
and rejection of invalid/mismatched verification.

Required focused regression:

```powershell
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m unittest tests.test_formal_snapshot_store tests.test_snapshot_store -v
```

GREEN result: 16 tests passed.

Full-suite verification was run twice (verbose then quiet only to capture a
clean result):

```powershell
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m unittest discover -s tests -v
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m unittest discover -s tests -q
```

Both completed successfully with no failures.  The verbose result was too long
for the command-output capture but showed the new suite and existing suites
passing; the quiet repeat emitted no failure output.

## Self-review

- `git diff --cached --check` passed before commit.
- Path components and supplied stored paths are constrained to the store root.
- Existing content/manifests are verified rather than silently overwritten.
- No real `data/` or status artifacts were created: all storage tests use
  `TemporaryDirectory`.
- No concerns remain for this task.  The only intentionally uncommitted file is
  this required report.

## Commit

```text
f69709a feat: add byte-preserving formal snapshot store
```

## Fix round 1 — integrity review findings

Committed the review repair as `56ddfb9` (`fix: harden formal snapshot integrity`).
Only Task 2 production code and tests were changed.

### Repairs

- `_write_content` and `_write_manifest` now resolve and constrain their exact
  targets to the store root before any `exists`, read, or reuse branch.  This
  closes acceptance of an existing `.bin` or `.manifest.json` whose final path
  is a symlink outside the store.
- `_read_manifest` now reads raw bytes exactly once, parses with a duplicate-key
  rejecting object hook, and requires the raw byte sequence to be identical to
  the canonical envelope serialization before checking the lineage hash.

### New behavioral regressions

- Existing content and manifest filename symlinks to outside-root files must be
  rejected during `write_verified`.
- Pretty-printed manifest JSON that is semantically unchanged must be rejected.
- A duplicate manifest key that normal JSON parsing would otherwise silently
  overwrite must be rejected.

### TDD evidence

The expanded focused test command was first run against the pre-fix code:

```powershell
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m unittest tests.test_formal_snapshot_store -v
```

RED result: the pretty-printed and duplicate-key manifest tests failed because
no `ValueError` was raised.  The two direct file-symlink tests were skipped on
this Windows account because `WinError 1314` denies file-symlink creation; they
remain real behavioral regressions for environments that permit symlinks.

After the production correction, the same focused command was GREEN: 10 tests
ran, 8 passed and the same 2 privilege-bound symlink tests skipped.  The stated
legacy regression command also passed:

```powershell
& 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe' -m unittest tests.test_formal_snapshot_store tests.test_snapshot_store -v
```

Result: 20 tests ran, 18 passed, 2 skipped for the documented Windows symlink
privilege limitation, with zero failures.

### Review

`git diff --check` passed.  No legacy files, real data, or status artifacts
were touched.  The only limitation is local execution of the two direct
file-symlink regressions under this account's OS privilege policy; the store's
target resolution checks are present before each existing-target branch.
