# W4 independent task review — `9452b31`

Base: `fd648b97125c7d381347605b820b6099ba39c4e4`. Reviewed the complete task brief, implementation report, calendar-collision diagnosis, and supplied diff once, then checked relevant fixture, store, and worker code read-only. No tests were rerun and no Git state was changed.

## Spec Compliance

The implementation covers seven explicit frozen-universe members and all five templates, including a second noncyclic bank, a broker with signed ST state and missing evidence, and an unresolved member. It asserts exact universe order and count, retained pending/vetoed members, template-specific decisions, noncyclic applicability, and absence of final scores, eligibility, and pools. The deterministic rebuild checks canonical bytes and hash; a genuine signed Context `g2` changes identity and makes the old selection fail current recheck. The restart test persists page one, recreates the three runtime objects on the same temporary store, resumes without a second first-page transport call, and compares the final page's canonical request/document and raw bytes to a continuous control. Same-exchange cross-template calendar reuse is based on a store-selected, reverified observation and exact request/generation/coverage/day-row comparison; separate binding proofs are asserted and a crossed proof is rejected. Only the two permitted test paths changed. No production, DDL, scoring, or pool path changed.

The report records integration 3/3 and the final exact 25-module regression command as 791 tests, zero failures, zero errors, one Windows symlink skip, exit 0. This review relies on that recorded test evidence.

## Strengths

- The calendar fixture calls `select_current()` and `require_current()` and checks the full request wire and signed observation content before sharing the underlying receipt. It does not use a Python seen set, exchange-only key, or caught collision text.
- The test checks both sides of the calendar boundary: one shared SH task/snapshot/receipt/transport call and distinct bank/broker binding and coverage hashes. The broker source rejects the bank proof.
- The restart fixture's `restart_worker()` genuinely reconstructs `StateStore`, `FormalRangeStore`, and `FormalRangeWorker`; the resumed worker reads the durable first page and completes the successor.
- Fixture options default to the prior W3 behavior and feed raw signed producer inputs. No test injects a stale flag, a veto outcome, or eligibility.

## Issues

### Critical

None.

### Important

- `tests/test_formal_policy_integration.py:142-146`: The correction test checks that the old and new snapshot IDs are still present, but never compares the old snapshot row with its pre-correction value. An in-place update to the old row would pass, so the required unchanged historical snapshot-row guarantee is not established. Capture the old `formal_source_snapshot` row before `g2`, then compare the complete row after correction while retaining the existing raw-byte check.

### Minor

- `tests/test_formal_policy_integration.py:44-49,166,197-199`: The restart fixture asserts that its database path is inside `TemporaryDirectory`, but the test does not assert that the persisted first-page and resumed/control raw paths are inside their respective temporary roots. The policy fixture likewise checks its generic raw root at line 40 but not the actual range raw paths. A misrouted raw-write path could satisfy the current isolation assertions. Assert containment for each observed `content_path` (including the first page) against the corresponding fixture root.

## Task quality

**Needs fixes** to close the two explicit assertion gaps above. The implementation otherwise matches W4's requested scope, and the recorded long-run evidence need not be repeated for this review.
