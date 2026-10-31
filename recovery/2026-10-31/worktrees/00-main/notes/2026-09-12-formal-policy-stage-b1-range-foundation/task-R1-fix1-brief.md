# R1 fix round 1

Reviewed head: ed25b6a553f0738c4de24dd88583c28061d196e0.
Fix baseline: db093077c57a180499a96c1182a603c50ebdb00e (F1-only commit after R1).
Read original task-R1-brief.md and task-R1-report.md in this directory.

## Important review findings

1. First-use method replacement defeats registry provenance (formal_range_contract.py:464).
Lazy capture before first load can trust patched FormalPolicyRegistry.require_verified
and canonical_bytes. An unregistered object.__new__(FormalPolicyRegistry) passes,
and require_current still passes after methods restore. Capture genuine trust
interfaces during controlled initialization; regression must attack before first load.
2. Replacement RangeConfig types disable deep checks (contract.py:368;
formal_sources.py:701,749). Parser mints mutable module alias, unexpected-type
fingerprint returns stable invalid marker. Replacing alias with a plain class
lets genuine source factory register it; unsigned dataset mutation remains accepted.
Capture real constructor; reject unexpected parser result before registration or
fingerprinting. Test before/after alias restoration.
3. Request template weakens old safety (contract.py:184). Query/header lists,
dicts/null allowed; null query throws TypeError; query whitespace/newlines pass.
Old formal_sources.py:295 requires strings and safe query whitespace/control rules.
Use the same constraints with new placeholder vocabulary; consistently ValueError.
4. Global strong-reference leak (contract.py:678,818,843). Parent record owns
children; child records own parent; weakref callbacks never fire. Drop all caller
references and gc.collect leaves both alive. Remove global retention while a live
child retains verification context. Add GC and child-lifetime regressions.

## Controller ruling and scope

May ADD ashare_pipeline/formal_range_format.py as a fifth whitelist file to
separate pure RangeConfig/parser from graph binding and break source -> contract
-> policy/context -> source import cycle. Keep public RangeConfig/parse_range_entry
exports compatible, source imports pure format module. Capture genuine types,
constructors and trust methods at controlled initialization in closures, not
mutable lazy first-use cache. Keep authority records private to closure. No edits
to formal_policy_registry.py or old trust gates. Cost: pure-module move/import
adjustment, no new external behavior. Original four files plus this optional fifth
only; F1 files frozen and off-limits. No Git writes, subagents, production data,
network, DB, scoring, merge, push. All edits use apply_patch.

Use TDD for all actual defects, read test-driven-development skill and its
writing-good-tests reference fully before edits. Append exact RED/GREEN commands,
output, self-review, concerns to task-R1-report.md. Freeze after final prescribed
four-module regression: tests.test_formal_range_contract tests.test_formal_sources
tests.test_formal_policy_registry tests.test_formal_policy_registry_guards.
Avoid redundant reruns of unchanged code. Root commits and supplies scoped fix diff
for independent re-review. Return status, summary, report path, concerns only.

