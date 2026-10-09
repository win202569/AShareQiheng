# Formal V9 Release Implementation Preflight

> **For agentic workers:** Use superpowers:executing-plans to implement task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Adapt the existing release design to the completed V8 Stage D chain before implementing release persistence or publication.

**Architecture:** Retain immutable V8 computation runs. Add a separate V9 release lifecycle linked to an exact Stage D run and fresh producer-verified evidence. Historical snapshots remain inspection data; publication authority comes from current verified producers and the official coverage gate.

**Tech Stack:** Python standard library, SQLite, unittest, canonical JSON, Decimal, same-volume directory rename.

**Spec:** `docs/superpowers/specs/2026-09-04-formal-scoring-release-contract-design.md` and `docs/superpowers/specs/2026-09-28-formal-final-scoring-stage-d-design.md`.

## Global Constraints

- Freeze stays at 2026-08-31 15:00:00 Asia/Shanghai.
- Pool identifiers remain `strong` and `wait`; capacities remain at most 20 and 50.
- V8 final runs remain append-only and `preview_ready`, including official candidates.
- Test-purpose roots, recovery snapshots and legacy scoring rows cannot authorize publication.
- SH/SZ/BJ exact frozen membership, official signed root, approval identity and live coverage remain required.
- Generated releases and databases remain retained project data and are excluded from code commits.

## Verified compatibility findings

1. `state_store.SCHEMA_VERSION` is already 8. The old release plan's V8 migration must become additive V9, preserving the exact V8 Stage D DDL and rows.
2. The old plan consumes V7 `formal_score_run`; the new source is `FormalFinalRunRepository`, its five canonical artifacts and eight V8 tables. No legacy conversion is permitted.
3. `FormalFinalRunSnapshot` is explicitly detached, non-authoritative history. `get_run` verifies persisted bytes/projections but cannot substitute for live producer proof or official coverage checks.
4. `formal_final_publication.py` is the private V8 atomic computation coordinator, not a filesystem release publisher. Its authority must not be repurposed.
5. The existing Stage D specification contains historical V7/V8 wording. Current implementation and the later Stage D plan establish computation V8 and release V9; this mapping must be explicit in the revised release specification.
6. The current performance acceptance is complete on `66d2561`. Production readiness and historical combined-wide-command acceptance remain separate questions.

## Review Focus

- Restarts: recovery data must never become live proof merely by parsing persisted JSON.
- Corrections: validation and publishing must bind identical run, input and result hashes; later corrected inputs produce a new run/release.
- Crashes: filesystem rename and SQLite commit require a durable signed preparation and an exact recovery path.
- Existing targets: conflicts, extra files, symlinks and junctions fail closed without overwriting the target.
- Official status: fully classified zero-score releases are distinct from incomplete evidence gates; legality follows the signed contract.

## Next implementation sequence

### Task 1: Revise the release contract and task plan

Files: create a dated V9 release design and implementation plan; preserve the old release plan as historical documentation.

- [ ] Map every old V7 score input to exact V8 Stage D artifacts and producer interfaces.
- [ ] Define validator construction with configured trusted producers and an exact run identifier. A returned history DTO or caller-supplied validation hash cannot authorize release.
- [ ] Define fresh producer replay versus retained live receipt validation, including restart semantics and source-change rejection. Select one explicit implementation path before schema work.
- [ ] Define V9 validation/preparation signatures, immutable release identity, validation expiry/rechecks, and database/filesystem recovery states.
- [ ] Specify behavior when current source generation differs from the candidate: block that release and require a new Stage D candidate, preserving historical rows.
- [ ] Name required gates and deterministic artifact schemas, including seven dimensions, grades, risk, pool decisions and audit evidence lineage.
- [ ] Self-review coverage against both referenced designs and current repository authority boundaries.

### Task 2: V9 persistence and canonical release values

Files: `ashare_pipeline/formal_release_types.py`, `ashare_pipeline/state_store.py`, migration fixtures and focused tests.

- [ ] Write tests for V8-to-V9 preservation, complete historical migration ledgers, invalid signatures, missing gates and immutable release rows.
- [ ] Implement additive release tables and transactional preparation/completion APIs using the revised contract.
- [ ] Run focused migration/authority tests and inspect exact V8 DDL preservation before committing.

### Task 3: Validator and filesystem publisher

Files: `ashare_pipeline/formal_release.py`, focused validator/publication tests.

- [ ] Verify live official identity, exact universe, evidence completeness, canonical results, pool rules and current workspace before release preparation.
- [ ] Test forged/cross-run proofs, changed sources, duplicate/missing members, stale coverage and post-validation tampering.
- [ ] Implement deterministic rendering, manifest-last staging, signed preparation, exact target verification and same-volume rename.
- [ ] Test pre/post-rename crashes, equal retries, conflicts and refusal to overwrite targets.

### Task 4: Reporting, CLI and end-to-end acceptance

Files: `ashare_pipeline/formal_release_reporting.py`, `ashare_pipeline/formal_cli.py`, narrow CLI/reporting integration and hermetic tests.

- [ ] Readers require a published V9 row and verify the complete target tree and hashes.
- [ ] CLI validation/publish paths use trusted configuration and recovery semantics, with no manually supplied authority hashes.
- [ ] Test SH/SZ/BJ, zero-score contract cases, rejection of test roots, deterministic bytes and corrections preserving earlier releases.
- [ ] Record exact revisions, commands and acceptance results before any production release action.

This preflight is not a completed V9 design or implementation. Task 1 resolves the live proof and signed recovery interfaces before later tasks modify code or schema.
