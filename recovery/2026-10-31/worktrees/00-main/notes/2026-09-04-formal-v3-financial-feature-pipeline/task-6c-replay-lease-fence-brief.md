# Task 6C — receipt replay lease fence

## Scope

Modify only:

- `ashare_pipeline/formal_deep_worker.py`
- `tests/test_formal_deep_worker.py`

The uncommitted source-bootstrap and fixture changes already present in the
worktree belong to other accepted tasks; do not edit them.  No data/network,
SQLite artifacts, staging, commits, resets, or subagents.

## Confirmed Important finding

In `_execute_context_task`, an existing verified receipt is recovered by
reading verified raw bytes and then invoking `parse_verified_snapshot`.
There is no lease renewal between the raw read/hash check and the parser
callback.  A reproduced case expires the worker lease during the real raw
read; the stale owner then invokes the injected parser once before the next
fence notices loss.  It does not persist/complete, but violates Task 6C's
requirement that lost ownership stop immediately before/after externally
expensive or mutable stages.

## Required TDD repair

Before production edits, add and run a focused regression that:

1. prepares a valid Context receipt/raw evidence owned by an old worker;
2. expires that old lease immediately after the real `read_verified_raw`
   returns during recovery;
3. proves the old worker leaves the task leased with no result/error,
   writes no stale terminal/retry/circuit state, performs no transport, and
   invokes **no parser callback** after lease loss;
4. proves a new owner recovers from the same immutable receipt and completes
   exactly one fact without transport.

The RED must fail because the pre-fix stale owner parser-call count is one.

Then make the smallest worker change: renew the Context task lease after the
verified raw/hash boundary and immediately before parser replay.  Preserve
the existing receipt/replay lineage validation, source error mapping, and
all later fences.  Do not add a catch that converts lost ownership into
terminal/retry work.

Run the focused test, full `tests.test_formal_deep_worker`, and source Context
tests appropriate to this change.  Report exact commands/results and
self-review to `task-6c-replay-lease-fence-report.md` in this directory.

## Ruling

The parser replay is a fenced external callback even when raw evidence was
previously verified.  Cost if wrong: a stale owner can execute arbitrary
parser work after lease loss, undermining the recovery safety boundary.
