# Task 4D2 report — formal universe status ledger and finalizer proof

## Scope and result

- Modified only `ashare_pipeline/state_store.py` and `tests/test_state_store.py` as tracked files.
- Implemented exact typed complete replacement and canonical listing for `formal_universe_status`.
- Extended `complete_formal_task` to accept `formal_universe_finalize` only after proving the exact V6 payload, exact result, BJ/SH/SZ source-task order, immutable prerequisite set, fully revalidated D1 universe graph, complete status coverage, and current final lease CAS.
- Implemented `get_formal_universe_snapshot_from_task` with the same persisted-task/result/graph proof and strict verified-task lifecycle validation.
- Added no migration, schema, raw-data, worker, or operational database changes.

## RED / GREEN evidence

- First RED: `StateStoreTestCase.test_formal_universe_statuses_replace_complete_typed_ledger_and_list_canonically` failed with the expected missing `list_formal_universe_statuses` `AttributeError`.
- Finalizer RED: the valid V6 finalizer test failed at the reviewed D1 fail-closed finalizer stub with `ValueError: formal universe finalizer requires verified universe proof`.
- Focused GREEN: `python -m unittest tests.test_state_store -k formal_universe -v` — 18 tests, OK in 194.105s.
- Bounded GREEN: `python -m unittest tests.test_state_store -q` — 176 tests, OK in 478.058s.
- Compilation: `python -m py_compile ashare_pipeline/state_store.py tests/test_state_store.py` — exit 0.
- Diff hygiene: `git diff --check` — exit 0.

## Status decisions and limitations

- Replacement accepts only exact `FormalUniverseDecision` instances, materializes input once, and requires exact member coverage with canonical IDs and no duplicates, omissions, foreign members, or extras.
- Reasons and veto flags must be exact tuples of nonempty strings in lexical unique order. Stable minimum semantics are enforced for all four states; pending evidence with a veto remains valid.
- Later-stage evidence hashes remain caller-supplied lowercase SHA-256 references. Only the exact D1 initial pending tuple is rebound to and revalidated against the D1 canonical evidence-hash formula.
- Replacement uses one `BEGIN IMMEDIATE`, validates the whole existing D1 graph before mutation, updates every member deterministically with one timestamp, and re-runs the normal full graph/status reader before commit.
- The finalizer payload is exactly `as_of_utc`, `registry_manifest_hash`, `refresh_generation`, and BJ/SH/SZ `source_task_ids`. Its result is exactly `universe_snapshot_id`, `frozen_input_hash`, `universe_hash`, and `registry_manifest_hash`.
- A complete classified ledger may contain any valid mixture of `out_of_scope`, `pending_evidence`, `pool_vetoed`, and `formal_scored`; finalization does not require all members to be scored.
- No data, SQLite, WAL/SHM, raw snapshot, or migration artifacts were created or staged.

## Review fix round 1

- RED: three focused regression methods produced eight expected `ValueError not raised` failures. A single status row could carry either a different canonical timestamp or a pre-header timestamp without fencing list, replacement, finalizer completion, or verified-task lookup; whitespace-only reasons and veto flags were accepted.
- GREEN focused regressions: the three new methods passed (3 tests, OK in 40.294s).
- GREEN formal-universe slice: `python -m unittest tests.test_state_store -k formal_universe -v` — 21 tests, OK in 207.005s.
- GREEN bounded suite: `python -m unittest tests.test_state_store -q` — 179 tests, OK in 538.390s.
- The shared graph reader now requires the complete status ledger to have one identical canonical UTC `updated_at`, and requires that timestamp not to predate `formal_universe_snapshot.created_at`. Because every status consumer passes through that reader, the invariant fences listing, replacement preflight/tail validation, finalizer completion, and verified-task lookup.
- The shared typed/persisted status validator now treats whitespace-only reason and veto strings as invalid while retaining exact tuple, lexical order, and uniqueness requirements.

## Review fix round 2

- RED: three focused regression methods produced ten expected `ValueError not raised` failures. Padded but nonblank reason/veto tokens were accepted from typed replacements, a triggered replacement-tail mutation, direct persisted reads, finalizer completion proof, and verified-task lookup.
- GREEN focused regressions: the three new methods passed (3 tests, OK in 18.731s).
- GREEN formal-universe slice: `python -m unittest tests.test_state_store -k formal_universe -q` — 24 tests, OK in 327.865s.
- GREEN bounded suite: `python -m unittest tests.test_state_store -q` — 182 tests, OK in 516.408s.
- The shared status validator now requires every reason and veto token to be nonempty and exactly equal to its stripped value. It rejects rather than normalizes padding, preserving the caller-supplied evidence-hash binding.
