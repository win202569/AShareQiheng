# Task 4C1 — validate immutable formal raw snapshots

This is the first serial slice of Task 4C.  It may start only after Task 4B2 is independently reviewed.  Read the V5 plan/spec, Task 4C preflight notes in the ledger, `formal_snapshot_store.py`, `formal_evidence.py`, and existing formal snapshot-store tests.  Scope is strictly:

- `ashare_pipeline/formal_snapshot_store.py`
- `tests/test_formal_snapshot_store.py`

Do not modify `StateStore`, schema/migrations, queue state semantics, universe code, legacy repositories, data/SQLite files, or any runtime artifacts.

## Deliver

Add one narrow public validation/inspection helper to `FormalSnapshotStore` for a `FormalStoredSnapshot` paired with an exact `OfficialFetch`, verified `EvidenceVerification`, and expected `producing_task_id`.  The helper name and returned immutable/canonical projection may be selected for clarity, but it must be documented, reusable by StateStore in 4C2, and must not accept arbitrary manifest paths or return unvalidated caller metadata.

It must re-use/extend the existing strict manifest parser and path checks and fail closed unless all of the following are true:

- inputs have exact expected types; verification is `verified`; expected producer matches manifest (nullable bootstrap producer allowed only when explicitly expected);
- raw bytes, fetch, stored object, manifest content hash, and verification content hash all agree; every SHA-256 is lowercase 64-hex;
- manifest bytes are duplicate-key-free and exact canonical JSON (UTF-8, sorted keys, compact separators, `ensure_ascii=False`, finite); manifest SHA is recomputed excluding its envelope field and matches its hash-derived filename;
- raw binary hash and filename match; manifest/raw files are sibling files under a safe `data/raw/formal/<source>/<dataset>/` path; source/dataset are safe single components; absolute normalized paths, inferred root, resolved paths, traversals, symlink/junction escapes are rejected;
- the canonical request exactly matches dataset/exchange/period-or-date/security-id/source; every fetch timestamp, URL, declared identity, generation, parser/mapping field, verification field, and producer match exactly;
- raw bytes rehash correctly.

“Signed manifest” here means canonical, SHA-verified Task 2 manifest—do not add cryptographic signing.  Existing byte-preserving snapshot writes remain compatible.

## TDD

Add RED tests first, then minimal implementation.  Include success, wrong types/status/producer, manifest/raw content mismatch, forged hashes/filenames, duplicate/noncanonical manifest JSON, tampered raw bytes, traversal/relative/different-directory/unsafe components, available symlink escapes, request/fetch/verification/generation/parser/mapping mismatch, and bootstrap vs task-produced producer rules.  Preserve existing formal snapshot-store tests.

Run `D:\\Projects\\AShareQiheng\\.venv\\Scripts\\python.exe -m unittest -v tests.test_formal_snapshot_store tests.test_formal_evidence`.  Do not run unbounded project E2E.  Commit only scoped files as:

`feat: validate formal raw snapshot receipts`

Write `task-4c1-report.md` in this SDD directory with RED/GREEN proof, exact test counts, public helper contract, and limitations.  No subagents/reviewers.
