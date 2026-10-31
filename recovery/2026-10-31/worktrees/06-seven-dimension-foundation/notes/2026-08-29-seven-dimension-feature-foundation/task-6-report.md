# Task 6 Report — Exact Verified Snapshot Repository

## RED

Added the public repository/store tests before production implementation. The first run of:

```powershell
python -m unittest tests.test_snapshot_repository tests.test_snapshot_store -v
```

failed as intended: `ashare_pipeline.snapshot_repository` was missing and
`SnapshotStore` did not expose `read_verified`.

## GREEN and verification

- Snapshot repository plus snapshot store: 18 tests passed.
- StateStore, feature-contract, and sources regression set: 81 tests passed.
- Full `python -m unittest discover -s tests -v` regression run: 176 tests passed.
- `python -m py_compile ashare_pipeline/snapshot_repository.py ashare_pipeline/snapshot_store.py` passed.
- `git diff --check` passed.

The exact-match tests prove source/dataset/request-fingerprint scoping and
revision ordering by `(fetched_at, created_at, payload_hash)`. Additional
tests cover unmatched requests, exact ID lookup, content reuse, payload
tampering, database-hash mismatch, project-relative new paths, legacy absolute
paths, `..` traversal, and resolved symlink/junction escape. The host did not
permit a real link/junction; the test falls back to a narrowly mocked filesystem
resolution result while exercising the repository's real containment check.

## Implementation evidence

- `persist()` writes/verifies content first, then records its path as a POSIX
  project-relative `data/...` path and preserves StateStore's content-identity
  reuse behavior.
- `find_exact()` filters all three identity fields before ordering; it never
  selects a global latest snapshot.
- `read_verified()` validates the on-disk content hash through the public
  `SnapshotStore.read_verified()` API, validates database metadata against the
  verified batch, accepts legacy absolute paths, and rejects unsafe new relative
  paths including escape after resolution.

## Commit

`0e56560 feat: add exact verified snapshot repository` (the report itself is
intentionally not committed).

## Residual risk

The Windows test host denied symbolic-link/junction creation, so the link-escape
branch is exercised with a narrow `Path.resolve()` fallback. A privileged or
Developer Mode Windows environment should additionally run the same test against
a real junction.

## Review remediation — verified snapshot trust gaps

### RED

Added and ran eight review regressions before implementation. The snapshot suite
failed as expected (six assertion failures and one error): it accepted payload
and DB `fetched_at` disagreement, returned a second unverified read, accepted an
injected store rooted elsewhere, wrote before rejecting unsafe source/dataset
components, and accepted mixed-backslash relative DB paths. A further resolved
parent containment regression also failed before its targeted fix.

### GREEN

- Snapshot repository/store: 26 tests passed.
- StateStore, feature-contract, and sources regression set: 81 tests passed.
- Full suite: 184 tests passed.
- `py_compile` passed for both snapshot modules; `git diff --check` passed.

`SnapshotRepository.read_verified()` now compares normalized aware-UTC fetched
times in both directions. `SnapshotStore.read_verified()` reads and verifies one
payload only, returning the same parsed batch. Source/dataset are validated as
safe single components before any path construction or directory creation; the
resolved target parent must remain below the store root, and an injected store
must resolve to exactly the repository data root. New relative DB paths reject
backslashes before POSIX parsing and resolved containment. Legacy absolute paths
remain supported.

### Verified-orphan policy

If a verified, content-addressed file is successfully written but its later DB
recording fails, it is deliberately retained as a verified orphan. It is safe for
same-content reuse and can be reclaimed by a future maintenance process. The
repository does not attempt an unsafe compensating delete that could race with
another writer which has already recorded the same content.

### Remediation commit

`2afd8fa fix: close verified snapshot trust gaps` (the report remains
uncommitted).

## Re-review remediation — concurrent same-target publishing

### RED/GREEN

Added a controlled two-writer regression with identical source, dataset,
request, content, digest, and day but different fetch times. A barrier wraps the
real publish system call so both writers clear their initial lookup; the first
writer is allowed to finish its database record before the second attempts its
publish. Before the fix, the second `os.replace` overwrote the target and the
unique DB row retained the first timestamp, making `read_verified()` fail.

The store now publishes a verified part by `os.link(part, target)`: target
existence makes the loser verify the existing winner and remove only its own
part, while a successful publisher removes its own part after linking. Targets
are never overwritten or deleted as compensation. The repository always reads
and verifies the actual returned winner, checks its canonical content identity
against the requested batch (with fetched-at intentionally outside that identity),
and records winner source/dataset/request/row-count/normalized time. The
controlled test proves both persists return the same ref, the ref and final file
use the first writer's time, and both verified reads succeed.

- Snapshot repository/store: 27 tests passed.
- Full suite: 185 tests passed.
- `py_compile` and `git diff --check` passed.

The cross-date verified-orphan policy is unchanged: a later DB-recording failure
does not delete a content-addressed target, avoiding a race with another writer;
such a verified in-root orphan is safely reusable and may be reclaimed later.

### Re-review commit

`57decb7 fix: publish snapshots without clobbering` (the report remains
uncommitted).
