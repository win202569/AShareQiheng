# Stage C Task 4 implementation report

Status: C4 complete. Final independent review is clean and the single authorized post-hardening 20-member full-module acceptance passed 2/2. C5 remains pending. This coordination report is intentionally kept in the ignored SDD directory and was not included in any code commit.

## Scope and design

- Added a complete, canonical `PolicyAdjustedValuationBatch` with exactly three V inputs per frozen security and one shared, closure-private publication capability. Single pending/invalid rows remain present; structural identity or proof failures abort the whole batch.
- Reused genuine Stage B `MetricInputBatch` and policy-result publications, C3 pure adjustment evaluation, and a nested shared-provider/Store finalization guard. C4 does not rewrite source facts, receipts, old metric inputs, or scores.
- Preserved C2's exact original-bundle object identity for `require_official`. The new explicit `require_current_bundle` first authenticates the registry against its original bundle and separately authenticates the freshly loaded store bundle through its loader seal; it then compares the full v2 manifest and all ten signed child envelopes. It rejects equal-looking forged objects, cross-root objects, and mutated sealed objects.
- Exposed Stage B's original `read_and_recheck` selection closure as `FormalPolicyRepository.recheck_current(batch)`, bound to the authentic repository and result batch. C4 calls it inside outer finalization, so external source invalidation without a database `data_version` change revokes the entire prepared C4 publication.
- A signed membership lacking an industry Context assignment still emits all three pending V rows. No missing policy decision is fabricated.

## Fixture and performance notes

- The Task 4 plan pseudocode used BJ 1 + SH 19 = 20, but a formal frozen universe requires BJ/SH/SZ all nonempty. With parent approval, the actual 20 securities are BJ430001, SH600000–SH600017, and SZ000001. This changes only test fixture membership, not production rules.
- All 20 members use real Context and market producers, signed one-day range requests, and a genuinely produced current calendar proof reused only within its exchange/rule. Every security still receives its own formal market facts. Only focal BJ430001 receives the five-year financial series needed for a matched cyclic decision; 19 signed noncyclic memberships select `not_applicable` and retain genuine raw V metric facts/features. No MetricInput or PolicyResult is minted directly.
- The earlier 3-member full producer path took 975.574s to finish evidence, with BJ policy at 270.413s and then 13+ minute runs interrupted. After Perf-1, the same unprofiled BJ stage was 233.619s (13.6% improvement). After separately reviewed Perf-2, one BJ-only cProfile probe took 341.172s instrumented wall time: `_derive_graph` fell from the original 86 calls to 2 calls/0.456s, while `_capture_graph_snapshot` took 532 calls/317.791s. The profiled 341.172s is not directly comparable to the unprofiled 233.619s. No further performance probe was run, and C4 did not modify either prerequisite optimization file.

## TDD and verification

- Initial C4 RED: module missing. C2 current-bundle RED: `require_current_bundle` missing. Added genuine source-loss/three-pending-row guards and made each pass after implementation.
- C4 small guard suite: 6 passed in 633.999s. Targeted no-industry test: 1 passed in 26.097s. Targeted source-invalidated-after-preparation test: 1 passed in 115.825s, including unchanged observer `PRAGMA data_version` and revocation of captured prepared C4 batch.
- C2 contract and pure adjustment regression: 33 passed in 87.284s.
- A Metric guard test that profiles a function named `_canonical` fails because the implementation defines the closure as `canonical` and exports an alias. The identical failure was reproduced on a clean, temporary detached checkout of baseline c634d5b6 (6.474s); that checkout was removed. This is pre-existing test debt, not a C4 failure. The remaining 15 Metric guard tests passed in 360.023s. Stage B policy guard and repository regression passed 26/26 in 1318.035s, including the long genuine all-member evidence case.
- New C4 real 3-member coverage separately passed for original base/policy canonical-byte stability, signed-membership/no-Context 3V pending rows, affected-policy pending, unaffected passthrough, and an invalid original metric retaining its row. A new method-replacement test initially left an inherited override attached after cleanup; the resulting two errors were test pollution, and the cleanup was corrected to remove that override. The two affected tests then passed in 198.205s. All C4 small authentic guards are green.

## Single 20-member main acceptance

One unprofiled run of `tests.test_formal_valuation_batch -v` started at approximately 17:45 UTC. It emitted `universe ready`, then authentic policy/market producer progress for BJ430001, every SH600000–SH600017, and SZ000001. It emitted `policy_done`, progress for every member's genuine raw V fact/feature producer, and `metric_done` at approximately 17:58:21 UTC. The next step was `FormalValuationRepository.build_batch` (complete Metric/Policy batches, source closure rechecks, and outer atomic finalization), but it emitted no `adjusted batch finalized` or exception for 30 minutes. At the agreed no-progress limit, it was interrupted at 18:28:26 UTC. No Python process remained. This run is **incomplete, not passed and not a functional failure**; the 20×3 published result and focal `0.12` assertion were not reached. No second 20-member run was started.

The bottleneck is localized to the final full-batch build/publication stage; the real 20-member evidence-production stages completed. A safe follow-up should instrument or optimize the complete-batch recheck path separately before repeating main acceptance, rather than weaken proof or producer requirements in C4.

## Perf3 follow-up and single post-fix retry

The separately reviewed Perf3 prerequisite was committed as baseline `0a252fb`; C4 did not edit its files. A temporary unprofiled wrapper ran the existing 3-member authentic pending/affected/unaffected/invalid-row test once. It passed in 70.197s total, with `build_adjusted_batch` final build/closure taking 53.122s (about 17.075s fixture preparation). The temporary wrapper was removed. This was materially shorter than prior 115–198s targeted cases and the 633.999s six-guard run, but it did not establish 20-member scaling.

One new unprofiled 20-member main acceptance run started around 18:51 UTC. It again emitted complete authentic policy/market producer progress for BJ430001, SH600000–SH600017, and SZ000001, then genuine raw V fact/feature progress for all 20 members and `metric_done` at 19:00:36 UTC. `FormalValuationRepository.build_batch` produced neither `adjusted batch finalized` nor an exception during the next 30 minutes. At the agreed limit it was interrupted at 19:30:40 UTC; no Python process remained. Thus the post-Perf3 full-population retry is also **incomplete, not passed and not a functional failure**. No additional 20-member run was started. The observed bottleneck remains in final complete-batch build/closure, not producer evidence creation.

Current handoff: C4 changes remain uncommitted by coordination decision; both full-population attempts and the 3-member gate are documented above. No push and no C5 work.

## Perf4c owner-journal implementation and 2026-09-26 acceptance

Perf4c added the authentic C4 build-local scope over the existing Perf4b policy owner journal, private three-V-per-member metric feature tickets, and a final outer checkpoint over metric, policy, adapter, and signed root. Focused gates passed: C2/pure adjustment 36/36, affected Stage B/Metric/journal 6/6, C4 guard and source closure 10/10, plus V-only raw/bundle/manifest/receipt tampering at unchanged SQLite `data_version` and the three-member selector/three-phase `sys.setprofile` checks. The detailed evidence and stopped probe accounting are in `.superpowers/sdd/perf-4c-report.md`.

One unprofiled 20-member acceptance ran on 2026-09-26 for 1643.110 seconds. All real policy and V fact/feature producers completed, `metric_done` appeared by 13:27:11 UTC, and `C4 adjusted batch finalized` appeared before the final 30-minute no-output threshold. The canonical row/source-authority test passed. The business test then failed at line 39 because `no_effective_trade_20d` was actually `clear`, not its expected `pending_evidence`. Review showed the fixture produces *all* one-day market request slices, yielding a complete 20-trading-day window; the policy evaluator correctly returns `clear`. The Stage C Task 4 brief does not require that independent market rule to be pending. The fixture comment and focal/peer test expectations were corrected without modifying production code, and a genuine three-member producer/policy-wire focused test passed 1/1 in 185.390 seconds with `clear` for all three members. At that point C4 remained uncommitted, with no second 20-member run yet started.

Independent review then approved the expectation correction and one additional unprofiled 20-member full-module acceptance. It started about 13:59 UTC on 2026-09-26; all policy and genuine V producers completed, `metric_done` appeared by 14:03:35 UTC, and `C4 adjusted batch finalized` appeared before 14:26:13 UTC, within the 30-minute final-closure no-output threshold. Both tests passed, 2/2 in 1627.657 seconds. They verify the canonical 60-row batch/source binding, focal `0.12` cyclic adjustment, noncyclic passthrough, and the correct `clear` independent market decisions. No production code was changed between the two 20-member runs. The first failed assertion is retained above for auditability.

The isolated C4/Perf4c implementation and tests were committed as `493e88d` after checking the exact 14-file staged list and a clean staged whitespace check. Neither ignored report nor data, SQLite, WAL, SHM, or progress files entered the commit. The tracked worktree is clean; no push or C5 work was performed.

## Post-acceptance independent review hardening

An independent review of `493e88d` required four fixes before final acceptance: captured C4 digest identity/use; a private C3 evaluator dependency guard; a metric-own evidence/coverage checkpoint before private base publication; and scope consumption for all private metric entry failures. All four have been implemented test-first. The journal now has four complete phases (metric, policy prepare, policy finalize, C4 outer). Four targeted attacks are green; the 3-member call-only phase/profile test passed 1/1 in 640.221s. The V-only unchanged-`data_version` closure and all 13 C4 guard cases each printed `ok` in a combined run. One later cross-scope case in that combined run was stopped after 15 silent minutes because of an unnecessary full-market class fixture; after limiting that fixture to its actual three signed members, cross-scope/replay and provider-epoch cases passed 2/2 in 140.247s. C2/C3 regressions passed 36/36 and affected Stage B/Metric/journal regressions passed 6/6. The separate negative incomplete V-ticket coverage test passed 1/1 in 79.311s. The prior 20-member 2/2 result belongs to `493e88d` and has not been rerun on these review fixes; independent re-review must precede that decision. The detailed audit is in `.superpowers/sdd/perf-4c-report.md`.

The four review fixes and focused tests were separately committed as `8e43eb9`. Exactly five authorized production/test files were staged, `git diff --cached --check` passed, and no ignored report, fixture data, SQLite, WAL, SHM, or progress file was committed. No push or 20-member rerun was performed.

## Second P1 review hardening (in progress)

The next independent review found two P1 gaps: C4's uncaptured public Decimal conversion and missing proof/public-value coherence, plus lack of a metric-owner coverage token for signed members without a template. Tests failed on both old behaviors, then Decimal's two targeted attacks passed 2/2 after capture and proof checks. Genuine four-member build with one unmatched signed member produces 12 C4 rows and preserves public metric canonical equality; owner-only invalid-template token coverage was observed in all four phases. Forgery, signed mapping change, and missing-one-V-row attacks reject, while C2/C3 regressions pass 36/36. The three-member phase/profile rerun passed 1/1 in 564.962s; final small regressions and commit remain pending. Detailed evidence is in the ignored Perf4c report. No 20-member acceptance or push was run.

The final affected selection (poisoned row, Perf4b policy 2, Metric 2, Context/Feature journal 2) passed 7/7 in 430.161s. The four-member mapping-change-after-adjusted-mint revocation test passed 1/1 in 68.721s and preserved base/policy proofs. A final focused rerun after tightening the poisoned-row test, plus the separate four-member four-phase profile, passed 2/2 in 231.256s. All second-review focused gates are complete; no 20-member rerun was performed.

The second P1 review fixes were separately committed as `2434712` with exactly three authorized production and two test/fixture files. The staged whitespace check passed. The ignored reports and all data/SQLite/WAL/SHM/progress artifacts remain outside the commit. No push; independent re-review is required before deciding on 20-member acceptance.

## Third local review hardening

The third re-review of `2434712` found that adjusted child Decimal pollution could leave a returned batch with only that child rejected on read, that ordinary batch reads repeatedly decoded/traversed every child, and that two invalid-template owner tokens repeated full Context/base rechecks separately at each of four phases. The new tests first failed on all three. C4 now fully validates every unpublished child and public Decimal against its canonical row before the final checkpoint; any failure rejects the build and revokes the common adjusted capability. Published ordinary reads use sealed constant-cost bindings; the private index is copied into a read-only mapping. The metric owner performs a single shared signed Context/base validation for all no-template members at initial issuance and each checkpoint phase, then verifies each member’s exact three V row identities/status. The journal authenticates tickets once per phase and routes the invalid-template group together.

The initial three targeted tests passed 3/3 in 327.729s; seven affected C4 cases passed in a 3-item and 4-item split after updating two observation hooks to the grouped checker (the four-item run took 480.467s). C2/C3 regressions passed 36/36 in 47.911s. An immutable-index focused addition and the three target tests passed together 4/4 in 380.289s. Two Context journal phase/replay checks passed 2/2 in 12.577s and again 2/2 in 12.335s on final journal code. Final-code four-member four-phase profile and five-member/two-invalid-template counts passed 2/2 in 241.321s, and final-code three-member call-only four-phase profile passed 1/1 in 667.760s. Final-code V-only source closure passed 1/1 in 855.978s, covering raw/bundle content and raw/feature manifest deletion at unchanged SQLite `data_version`; each subcase emitted progress inside the 15-minute silence ceiling. No 20-member rerun or push was performed. Detailed red/green and stopped-probe accounting are in the ignored Perf4c report.

The third-round local fix commit is `a3984ed9035c1f346c47ae0d3c41ae7845125c25`. Its staged whitespace check passed; only three authorized production files and the C4 guard test file were committed. The tracked worktree is clean, the ignored reports remain outside Git, and no data/DB/progress artifact or push occurred. Independent re-review, not a 20-member rerun, is next.

## Final range-lease hardening and acceptance

The final C4 implementation/hardening chain is `493e88d`, `8e43eb9`,
`2434712`, `a3984ed`, `1af0e2b`, `bf0f694`, `a484cfe`, `ae3828d`,
`237b907`. The range-current performance work culminated in an operation-scoped
owner read lease with full entry/exit graph authentication, per-read sealed
envelope checks, exact owner/journal phase binding, copy-context and cross-thread
closure protection, captured frame/thread dependencies, and reliable genuine
journal revocation during thread-identity pollution. The final independent
review of `237b907` and the complete lease boundary returned **Clean**.

Exactly one final 20-member acceptance was started on `237b907`:
`python -u -m unittest tests.test_formal_valuation_batch -v`. All 20 authentic
policy and metric producers completed; `policy_done` and `metric_done` were
observed at approximately 8.5 minutes. Final closure emitted
`C4 adjusted batch finalized` after approximately 29 minutes of monitored
closure time, inside the agreed 30-minute final-closure threshold. Both tests
passed, 2/2, with exit code 0 in 2409.766 seconds. No capture/read counters were
printed by this acceptance command.

Final state: C4 is complete; C5 is pending. HEAD is `237b907`, the tracked
worktree is clean, reports/ledger remain ignored, and no commit in this chain
has been pushed by this workstream.
