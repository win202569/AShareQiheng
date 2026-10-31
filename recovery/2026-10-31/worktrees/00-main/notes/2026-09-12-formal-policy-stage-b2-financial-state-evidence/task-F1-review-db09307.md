# F1 independent review (controller-preserved)

Reviewer: /root/stage_b_f1_reviewer, gpt-5.6-sol/high.
Reviewed head: db093077c57a180499a96c1182a603c50ebdb00e.
Spec: issues found. Quality: Needs fixes. No Critical/Minor findings.

## Strengths

- formal_policy_values.py:54-74 isolated context and exact V6 bridge.
- values:114-145 canonical finite fixed Decimal and negative zero handling.
- values:155-180 closed pending shapes/runtime list and detached hashes.
- values:194-236 strict wires/types, typed shortfalls, compound rejection.
- runtime fixture:94-137 pre-sign graph mutations and exact frozen memberships.
- runtime fixture:201-237 genuine task/snapshot/fact/receipt with explicit units;
  tests authenticate blocked receipt without weakening the old gate.
- tests/test_formal_policy_values.py:40-211 broad numerical/mutation negatives.

## Important findings (all accepted)

1. formal_policy_values.py:220-221: undocumented ASCII identifier grammar rejects
valid exact string enums (spaces/Unicode/punctuation). Preserve exact str identity;
no invented allowlist or normalization in the nonauthoritative DTO.
2. tests/formal_policy_runtime_fixtures.py:149,230-234: canonical_security_id result
discarded and actual frozen membership not checked before writes. Normalized alias
can enqueue before failure; SH600099 inserts a fact before StopIteration. Validate
exact spelling/membership first, with zero-mutation negatives.

## Evidence / scope

Named unchanged check formal_universe.py:81-87 establishes case/space normalization.
Focused diagnostics confirmed writes before invalid-security failure.
Cannot verify R1 add_range_documents correctness from F1 diff; F1 integration
call/test present (fixture:112-114, tests:240-246); separate R1 review covers it.
Fix brief task-F1-fix1-brief.md records exact follow-up.

