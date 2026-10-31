# Perf4b policy build journal report

## Scope

- Independent implementation commit: `c89f9da Add composite policy batch read journal`. Its four paths are the policy repository, batch read journal, and two policy-only test modules. Review-fix commit: `4a60f6e Consume owner policy scope on early build failure`, containing only the policy repository and two policy tests. No C4 paths were staged in either commit; the policy repository has no remaining worktree diff.
- Policy preparation uses one composite build-local journal for financial, state, policy feature, Context, market, calendar, and range owner tickets.
- The first selection remains a complete owner selection. Preparation and guarded finalization recheck the same scope in separate phases, while signed registry and universe/industry dependencies are checked at both boundaries.
- The public `recheck_current` retains its independent selection behavior. A private owner-scope build entry returns the policy batch, its all-member coverage ticket, and its revoker for a future enclosing owner; the public build owns and consumes its scope.
- The existing C4 policy `recheck_current` changes were absorbed in this task; no other C4 files were staged.

## Red/green evidence

- The selection-count test failed before implementation with financial/state top-level selector calls `[3, 3]`, then passed for one assigned member with `[1, 1]`. The final three-assigned-member version passed with financial/state `[3, 3]`, three market assemblies, two checkpoints on the same scope, and at least six owner ticket rechecks each.
- A source deletion after the first checkpoint failed when guarded finalization checked only the journal. It passed after finalization also checked signed configuration and universe/industry state.
- A raw source deletion immediately after the second journal checkpoint published a batch before the post-check inspected source state. The added test failed, then passed after checking signed configuration and universe/industry again before publication.
- A reader-method mutation prevented `scope.close()` from revoking a captured scope. The added test failed, then passed after making close validate scope identity and thread without requiring a still-valid owner graph.
- Independent review found that the private owner-scope entry called `_build_batch` before its own exception handler. Two added tests first failed because interface replacement at entry and a nonexistent frozen hash before prepare left the passed scope reusable after recovery. After moving the entire private build into the fail-closed handler, both tests and the earlier private lifecycle test passed (3 tests in 19.204s). The public owned-scope build path was not changed.
- The three-member profile test now records the member and owner at each journal phase and asserts complete financial/state/market coverage in both phases; the focused test passed in 130.240s.
- Public independent recheck and private owner-scope lifecycle tests passed individually. The private test now requires all-member coverage while only one member has lower-level selection tickets, and checks copy, wrong root, cross-owner, cross-thread, and replay rejection.

## Verification

- On the initial implementation commit, policy repository/guard ran 31 tests in 756.689s, all passed. This includes post-prepare and guarded-finalization source invalidation, provider/database races, guard-exit child revocation, writer reservation absence during preparation, public reselect, and owner-scope lifecycle. The earlier three-member market-ticket count test passed separately in 147.362s; the all-member owner ticket and restored-method scope-close test passed separately in 15.942s. The review fix was verified with its two red/green replay tests plus private lifecycle (3/3 in 19.204s), its strengthened phase-by-member count (1/1 in 130.240s), and the final 17/17 market-first integration run below.
- The final-code non-market ticket/journal/metric guard group ran 47 tests in 422.528s: 46 passed and one pre-existing metric test failed. `test_canonical_preparation_does_not_hold_the_writer_reservation` profiles for function code name `_canonical`, while `formal_metric_engine.py` defines `canonical` and aliases it as `_canonical` (also true at HEAD); its `observed` value remains zero on an isolated rerun. The failure does not touch Perf4b files and is not counted as a pass.
- After the market order-pollution repair commits `930e1d2` and `750e091`, the full market ticket suite passed in default order (11 tests in 120.916s). The final review fix passed a same-process market-first integration run: all 11 market ticket tests followed by six Perf4b focused tests, 17/17 in 296.411s. The Perf4b subset covered phase-by-member counts, final-checkpoint raw-source deletion, public reselect, private owner-scope lifecycle, restored-interface replay rejection, and missing-frozen-input replay rejection.
- `git diff --check` passed for the task files.
