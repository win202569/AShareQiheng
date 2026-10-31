# Task 6C source-bootstrap extension ledger

Ruling: user authorized a two-file source-layer extension after independent
root-cause tracing proved the existing bootstrap-calendar preflight rejects
the same signed exchange identity required by Context fact validation.  The
minimal correction permits a signed request exchange while preserving the
unbound config and security-id prohibition.  Cost if wrong: a wrong boundary
could blur exchange isolation; retaining the old rule makes date-only Context
execution impossible.

Ruling: after the source correction exposed the real end-to-end calendar
path, the remaining bootstrap failure was a test fixture with null
period/security placeholders and a missing parser bootstrap flag.  Repair it
only in the worker fixture rather than weakening source validation.  Cost if
wrong: production would accept malformed signed source work or the date-only
dispatch path would remain masked.

Ruling: Context receipt recovery must renew immediately after verified raw
read/hash validation and before parser replay.  A reproduced stale-owner
callback established that the later fence alone was insufficient.  Cost if
wrong: a lost owner can execute parser work even though no stale result is
persisted.

Completion: `e97d3f1 fix: complete formal context calendar execution` commits
only formal worker/source code and their tests.  Source task review, fixture
task review, final security review, and scoped lease-fence re-review were
clean after the fence fix.  Fresh module evidence: worker 83 passed;
source plus Context repository 79 passed; prior combined source/worker 122,
StateStore 208, and Context schema/repository 49 passed.  No data/state file
was staged.  A test-created untracked `tmpj4zv9_fq/` SQLite directory remains
preserved outside the commit.
