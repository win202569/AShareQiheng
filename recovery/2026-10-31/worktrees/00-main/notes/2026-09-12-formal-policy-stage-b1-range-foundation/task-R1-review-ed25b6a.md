# R1 independent review (controller-preserved)

Reviewer: /root/stage_b_r1_reviewer, gpt-6-astra/high.
Reviewed head: ed25b6a553f0738c4de24dd88583c28061d196e0.
Spec: issues found. Quality: Needs fixes. No Critical/Minor findings.

## Strengths

- formal_sources.py:649 closed v1/v2 dispatch preserves old parsing/selection.
- formal_range_contract.py:486 derives actual nine-role hashes and active M/C/Bx.
- tests/test_formal_range_contract.py:236 covers calendar identity mixing.
- tests/formal_range_fixtures.py:155 uses genuine signed graph/rehashing.

## Important findings (all accepted)

1. formal_range_contract.py:464: first-use patched policy require_verified and
canonical_bytes become cached trusted interfaces; genuine class unregistered
object accepted and still current after methods restore.
2. formal_range_contract.py:368; formal_sources.py:701,749: mutable RangeConfig
alias can mint replacement types; stable invalid-type fingerprint accepts unsigned
dataset mutation even after alias restore.
3. formal_range_contract.py:184: query/header nonscalar values accepted; null query
raises TypeError and whitespace/control query strings pass. Old source validator
at formal_sources.py:295 requires strings and stricter query safety.
4. formal_range_contract.py:678,818,843: global parent-to-child and child-to-parent
strong records prevent weakref cleanup; both survive dropping caller refs and GC.

## Evidence / scope

Four focused diagnostics confirmed findings; no suite rerun. Named unchanged-code
checks: template parity at source:295; HTTPS parity at source:227 (no extra issue).
Truncated package middle was recovered only; changed implementation hunks were
not separately reread. Fix brief task-R1-fix1-brief.md records exact follow-up.

