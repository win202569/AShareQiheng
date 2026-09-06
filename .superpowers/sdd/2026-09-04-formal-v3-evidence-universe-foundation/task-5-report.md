# Task 5 report — verified formal snapshot repository

## Scope and result

- Created `ashare_pipeline/formal_snapshot_repository.py` and
  `tests/test_formal_snapshot_repository.py`.
- Narrowly extended `ashare_pipeline/state_store.py` with the configured formal
  raw-store accessor and single-read-transaction verified lookup helpers.
- Committed the three allowed tracked files as `fcdaefb feat: persist verified
  formal snapshots`.
- Did not change migrations, schemas, raw-store/evidence/time/universe/finalizer
  behaviour, worker code, legacy snapshot APIs, data, SQLite files, WAL/SHM, or
  pipeline progress.

## RED / GREEN evidence

- RED: `python -m unittest tests.test_formal_snapshot_repository -v` initially
  failed with the expected `ModuleNotFoundError` for
  `ashare_pipeline.formal_snapshot_repository`.
- GREEN: the new focused repository suite contains 16 contract tests.  Its
  aggregate and targeted runs completed without a test failure; individual
  boundary groups reported `OK`.
- StateStore regression: `python -m unittest tests.test_state_store -q` —
  **182 tests, OK, 1085.203s, exit code 0**.
- Compilation after the final test additions:
  `python -m py_compile ashare_pipeline/formal_snapshot_repository.py
  ashare_pipeline/state_store.py tests/test_formal_snapshot_repository.py` —
  exit 0.
- Diff hygiene before staging: `git diff --check` — exit 0.

The requested combined command was initiated before the dedicated StateStore
verification.  The Windows long-output transport detached while its test
processes continued; repeated invocations caused redundant concurrent test
groups, which all naturally exited.  No process was terminated.  The clean,
captured StateStore result above is the authoritative regression result; no
additional tests were started after that cleanup diagnosis.

## Invariants implemented

- The repository accepts only an exact `StateStore` with its already-configured
  `FormalSnapshotStore`, and requires the same resolved root.  It never creates
  a second raw store, preserving a date-only resolver identity.
- Persistence validates exact fetch/verification types and a paired,
  already-trimmed producer/worker identity before any raw write.  It writes raw
  evidence first, then calls only the bootstrap or leased StateStore transition.
- Every repository lookup runs through one explicit StateStore read transaction.
  Candidate rows are revalidated from formal row plus manifest/raw bytes before
  filtering, and task-produced snapshots require exactly one coherent receipt
  and one producer row; bootstrap rows require no receipt.
- Visible selection uses `is_visible_at`, has no capture-time cutoff, adapts
  `OfficialSnapshotRef.content_sha256` to `formal_version_sort_key`, and uses
  manifest SHA ascending as the final tie-breaker.
- Raw reads require an exact immutable `OfficialSnapshotRef`, re-fetch the
  verified manifest projection, compare every reference field, and reconstruct
  `FormalStoredSnapshot` only from that revalidated projection.
- Tests cover date-only resolver reuse, bootstrap/leased persistence, wrong and
  expired leases, exact and point-in-time selection, all sort dimensions,
  insertion-order independence, canonical-row/raw/manifest/path/reference
  tamper, receipt fractures, legacy isolation, and a real
  `formal_universe_source` receipt path.

## Review fix round 1 — identity-tamper fail-closed behavior

- The review found that candidate discovery for exact and visible lookups used
  the mutable database `request_fingerprint` as an SQL predicate.  Changing a
  newer matching row to a different valid lowercase SHA-256 could therefore
  hide its corruption and allow an older row (or no row) to be returned.
- RED: two new focused regressions changed a newer same-request row to
  `"0" * 64`; both exact and point-in-time lookup initially failed because no
  `ValueError` was raised (2 failures / 2 tests).
- The helper now scans every `formal_source_snapshot` row inside the existing
  read transaction, fully revalidates each row, manifest/raw evidence, and
  receipt/task graph, and only then filters rebuilt references against the
  caller's canonical identity.
- GREEN: the two regressions passed (2 tests / 3.832s), the focused repository
  suite passed (18 tests / 34.174s), and the single StateStore regression run
  passed (182 tests / 620.878s).
- Compilation passed for the repository, StateStore, and focused test module;
  `git diff --check fcdaefb` passed.  This fix changes only
  `ashare_pipeline/state_store.py` and
  `tests/test_formal_snapshot_repository.py`; no data, SQLite, WAL/SHM, or
  progress artifact was staged.  It was committed as
  `cc4227e fix: fail closed on formal snapshot identity tampering`.
