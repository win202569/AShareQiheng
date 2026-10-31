# F1 fix round 1

Reviewed head / fix baseline: db093077c57a180499a96c1182a603c50ebdb00e.
Read task-F1-brief.md and task-F1-report.md in this directory.

## Accepted Important findings

1. formal_policy_values.py:220-221 applies undocumented ASCII _IDENTIFIER grammar
for enum. Contract requires exact str, not identifier syntax. Valid strings with
spaces/Unicode/punctuation must preserve exact identity. Remove extra grammar;
reject non-exact-str types. Do not strip, normalize or invent enum allowlists;
current-rule enum authorization belongs later producers/evaluator.
2. tests/formal_policy_runtime_fixtures.py:149,230-234 discards normalization result
from canonical_security_id and accepts nonmembers before writes. Input
" sh600000 " can enqueue before verification fails; SH600099 can insert a fact
before publish_current raises StopIteration. Require exact canonical spelling and
membership in the fixture's actual frozen universe before enqueue/persistence.
Regression asserts no task/fact/snapshot/receipt state changes on either rejection,
not just an exception. Preserve valid canonical-member path.

## Scope and process

Use only the existing F1 four-file whitelist (see task brief), preferably just
values module, runtime fixture, and tests. All edits apply_patch, no Git writes,
subagents, production data/network/scoring. Read TDD skill and writing-good-tests
fully; implement RED/GREEN. Append exact commands, outputs, checks and concerns to
task-F1-report.md. Python D:/Projects/AShareQiheng/.venv/Scripts/python.exe.
Final prescribed compatibility: tests.test_formal_policy_values
 tests.test_formal_policy_registry tests.test_formal_metric_features.

R1 fix simultaneously changes only range/source modules. Coordinate a source-stable
window with /root/policy_stage_a_final_fix before any full fixture integration
run; scalar tests may run independently. Do not modify or review R1 code during
this implementation task. Freeze final files and return report path/results.
Original F1 reviewer independently re-reviews only the fix diff.

