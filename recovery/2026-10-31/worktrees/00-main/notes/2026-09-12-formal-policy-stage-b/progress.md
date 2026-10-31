# SDD ledger — plan: docs/superpowers/plans/2026-09-12-formal-policy-stage-b.md

Worktree: D:/Projects/AShareQiheng/.worktrees/formal-v3-implementation
Branch: codex/formal-v3-implementation
Execution base: 7cf6b5996f029e95be9331010c22638c804f40a2
Authority: user continued after the implementation-plan handoff.

## Current checkpoint

Accepted: R1, R2, R3, R4, F1, F2, F3, W1 — 8/11 tasks. W1 is accepted at
checkpoint 31f727e after three reviewed fix rounds and a fresh exact-checkpoint
compatibility gate: 161 tests / 18046.539s / OK / exit 0. All 13 W1 code/test
SHA-256 hashes were unchanged across the run; post-run status and diff checks
were clean and no Python process remained. W2 is now the next dependency-ready
task; W3/W4 remain unstarted. No production capture, scoring, pool publication,
merge or push is claimed.

Historical checkpoint detail follows. F3 code checkpoint d2cc791 has
clean independent review and 144-case full compatibility GREEN with six stable
post-run hashes. R3 fix round 1 at ca71683 has clean scoped re-review. Final
compatibility session 18573 finished: 272 tests / 3109.739s, FAILED (errors=5).
All five errors are the request-record ValueError escaping its typed Source
boundary; the full terminal output is retained in task-R3-report.md. The recovery
agent subsequently hit its usage limit; this was an executor interruption, not
a still-running test. On 2026-09-19 usage permits work again, no Python tests
remained active, and all six R3 code/test hashes matched ca71683 before fix2.
The user-owned documentation/data commit 8385ff6 is preserved untouched.
Fix round 2 at 3c3b3c1 restores source-only exception conversion. Fresh focused
RED reproduced all five errors; complete Source plus parent-correction regression
GREEN: 32 tests /686.364s, OK exit 0. Six frozen hashes checked independently.
Scoped fix2 re-review is clean; previous full272 remains FAILED, not relabeled
GREEN. R3 is accepted at the scoped task gate, not final project acceptance.
R4 accepted: review checkpoint bc1d137, BASE3c3b3c1; one Important review finding.
Fix1 RED32094 finished (3 tests/326.730s/7 expected failures, exit1); focused
GREEN83795 finished (6 tests/868.661s/OK/exit0). Root verified full logs/hashes,
committed exact Source+worker-test fix at ba0def6; independent scoped re-review
stage_b_r4_fix1_review clean. Sole final100 same-process compatibility TERMINAL:
session73320, Python35328/launcher34740, start2026-09-19T14:09:08+04:00 host-local.
Log task-R4-compatibility.log: 100 tests /7067.269s, OK, exit0. Root read the full
terminal log independently; all four frozen code/test hashes match ba0def6 and
the only ordinary worktree edit is the controller's master plan. No duplicate
suite, production change or restart. Task R4: complete at ba0def6 after fix1
scoped review and final100. This is not whole-project or whole-Stage-B acceptance.
W1/W2/W3/W4 not started; W1 read-only interface audit is preparation only.
User selected performance optimization before W1, after final100, and explicitly
approved the bounded in-chat design. P1 now cleared for dispatch from BASE
ba0def62a4ffe45cb5e3bee41537ea1b79ff6de0. P1 is supplemental, not one of the
original11. Original Stage B accepted7/11. Owned paths and verification gates
remain in task-P1-brief.md; no performance implementation accepted yet.
P1 implementer dispatched: /root/feature_parse_reuse_implementer (clean context,
gpt-5.6-sol/high). Owns feature contract and its tests only, report task-P1-report.md.
First handoff is focused TDD, complete owned module and same-operation profile;
full project suite waits until independent task review. Controller alone Git.
P1 checkpoint21746b2990b24c79b93521dc75f5d8e7e4a7f176 contains only the two
owned code/test files. Root read complete saved RED/GREEN/module/profile logs
and checked hashes. RED parser24 versus expected1; focused3GREEN; module22/0.025s
OK exit0. Same probe parser422->1, wall41.591->9.559s, CPU36.141->8.891s;
authority counts286/7/3 unchanged. Bounded measurement, not production throughput.
Independent /root/feature_parse_reuse_review running from complete diff package
task-P1-review-21746b2.diff; review CLEAN (spec compliant, quality approved, no
findings), verdict task-P1-review-21746b2.md. Controller resumes original P1
implementer for sole full-project verification; code/tests frozen. No P1 acceptance
until fresh terminal full-suite result and post-run hash checks.
P1 full-project command TERMINAL: session17770, shell42476,
computing Python42300, launcher42304;
start2026-09-19T12:19:15.9575900Z. Complete incremental log task-P1-full-suite.log.
No competing test/profile or code/test edits. Terminal1403tests/4508.303s,
FAILED(errors=1,skipped=4), exit1, end2026-09-19T13:34:26.3134613Z.
Sole ERROR: test_formal_context_repository.ContextIntegrationTests.
test_date_only_uses_calendar_provenance_without_recursive_self_lookup:
ValueError formal snapshot task lease expired or ownership changed. Stack test629
->put236->state_store1980->formal_context_repository243/65->state_store3156.
Root read full terminal chunk88 and checked both frozen P1 hashes/HEAD; only
controller master-plan edit remains unstaged. P1 not accepted: full suite is RED.
Four Windows symlink privilege skips; no attempt to weaken/reconfigure permissions.
Interim native capture gap17 remains unrecoverable and explicit: final transcript
omits bulk native output. Native chunk88 preserves complete traceback; both logs
preserve terminal aggregate/exit/timing. Raw JSON chunks plus chronological companion
are retained; no synthetic reconstruction or rerun. Implementer final report frozen.
Read-only /root/p1_full_suite_failure_triage dispatched for this exact failure;
no tests, edits or scope expansion authorized. Default fixture lease300s versus
other date-only cases3600s is a hypothesis lead, not proof of which owner predicate
failed. All code remains frozen; no W1 start or production operation.
Read-only triage complete: task-P1-full-suite-triage.md. Failure path does not
consume the modified P1 feature owner; original context bundle/calendar replay is
separate. First persistence gate rejects status/worker/expiry; generic error cannot
prove which predicate. No focused diagnostic rerun yet and no third-file changes.
Current handoff: local optimization implemented/reviewed/profiled, full-project
gate FAILED. User now explicitly authorized expanding to the failing test's
diagnosis and necessary test-only fix, with production rules unchanged. P2 brief
task-P2-brief.md; BASE21746b2990b24c79b93521dc75f5d8e7e4a7f176. Stage1 is a single
unchanged focused diagnostic, evidence checkpoint before any test edit. Stage2
only after controller reviews evidence. No W1 or production scope expansion.
P2 stage1 dispatched /root/context_lease_test_repair (gpt-5.6-sol/high, clean
context), owns diagnostic/report artifacts now; tracked test edits remain gated
on evidence. Controller preparing scoped review/verification while child diagnoses.
No production capture, scoring, pool generation, main merge or push performed.

P2 Stage1 diagnostic terminal: one unchanged target test /50.198s, OK exit0,
session59617, computing PID44452. Original ownership gates all passed; lease
headroom270.697s at final normalization,265.298s at initial persistence,
257.964s at final persistence. Root read complete script/log/report. Historical
failure not reproduced; no predicate cause proved and no tracked repair made.
Controller rejects a speculative lease increase. Same child authorized ONE
unchanged complete context-repository module run in normal discovery order,
with forwarding target-gate observations and per-test timing. This is bounded
order-sensitive diagnosis plus unchanged owner-expiry/rollback coverage, not
the final full-project rerun. No tracked edits until evidence checkpoint.
P2 module diagnostic terminal47/326.644s OK exit0, no skips; root read all
verdicts and target ownership observations. Test hash E61722E6A06ED982376FCDCAB
8EFAD8EF1A2B7F8056987A70380F4F9A51E3208 unchanged. Five expiry/owner/rollback
guards passed. Target initial-persistence headroom274.935s. Loader used qualified
tests.test_formal_context_repository, not historical discover's short module
name; this limitation is explicit. Controller authorized final bounded diagnostic:
full original discovery/imports, then unchanged ordered prefix through target
only, preserving the original full suite references. No full1403 execution or
tracked edits; after terminal stop diagnostic attempts and report uncertainty.
P2 final discovery-prefix diagnostic TERMINAL:236/228.679s OK exit0, no skips,
session41213/computing31988. Original discovery found1403, target index235;
only ordered prefix236 executed, later1167 retained and not run. Root inspected
all235 ordinary pass names, target ownership records/OK and terminal result.
Target initial-persistence headroom276.821s/final268.940s, all predicates true,
original clock retained. Tracked test hash remains unchanged. Single, module and
full-discovery-prefix diagnostics did not reproduce historical failure. Diagnostic
scope concluded with NO tracked repair: no evidence justifies raising lease or
weakening assertions. Instrumentation/object retention/environment are not exact
pristine full-run conditions; these passes do not establish historical cause.
P1 full-project acceptance remains unresolved; prior1403 FAILED stays historical
RED. No new commit, full-project rerun, W1 start, merge, push or production change.
User authorized one diagnostic full-suite revalidation after pushing checkpoint
a90faf4. Full run session4399/computing PID46996, diagnostic session UUID
4342c3f9-e798-496a-9ff9-7c29c8007447, start2026-09-19T14:39:41.793216Z.
Exact original discovery found1403 and unique target index235. Non-PTY unbuffered
runner writes task-P2-full-suite-diagnostic.log incrementally; target-only owner
row/clock/headroom instrumentation forwards the original verdict. Pre-run branch
equals remote, tracked tree clean, no other Python process, seven key hashes saved.
This is the sole full run; no production/test edits or competing workload.
First full diagnostic attempt was stopped at test549/1403 after692.6s because
the diagnostic runner, unlike unittest discovery, retained a second strong tuple
of all1403 TestCase objects. Five weak-reference/isolation-sensitive metric tests
reported ERROR, making that run invalid as compatibility evidence. Preserved as
task-P2-full-suite-diagnostic-invalid-retention.log (SHA256 BE0D226A...). No
production/test file changed. Runner corrected to release flattened/prefix/later
collections before execution while the ordinary discovered suite consumes its
own cases. Syntax check passed; no Python process remains. A clean replacement
full diagnostic run is required; the stopped attempt is not a test verdict.
Second corrected attempt released TestCase collections but installed the three
forwarding diagnostic hooks for the whole suite. It was stopped at roughly530
tests after weak-reference/capability identity tests reported errors: target-only
observation had leaked into later tests. Preserved as task-P2-full-suite-diagnostic-
invalid-hook-lifetime.log (SHA256 7CEA80F3...). Runner fix2 now installs hooks only
in TimingResult.startTest(target) and restores all originals in stopTest(target),
with an explicit restoration marker. It also retains no second TestCase collection.
Syntax passed, no Python process. This is diagnostic harness correction, not a
production/test change and neither stopped run counts as validation evidence.
Final valid replacement full diagnostic run TERMINAL: session97640, PID48900,
UUID118406ec-f9d1-4d7c-8b82-a6829f41e852; start15:03:24.999167Z,
end16:26:32.803490Z. Ran1403/4987.503s, OK(skipped=4), errors0/failures0,
exit0; wrapper4987.812s. Four skips are unchanged Windows file-symlink privilege
WinError1314 cases. No warning/failure/error markers. Target clock genuine; all
owner predicates true, initial persistence headroom278.264s/final271.037s;
TARGET_DIAGNOSTIC_HOOKS_RESTORED=true before remaining tests. Final log SHA256
5D219F119D872625EEF12C0273C603D22963D2711399B68528271BED65E22CC4.
All seven pre/post code/test hashes identical; tracked tree clean/equal remote;
no Python process. P1 supplemental optimization and P2 compatibility diagnostic
are now accepted at the fresh full-project gate. Historical failed1403 and two
stopped harness-interference attempts remain preserved, not relabeled. Original
Stage B remains7/11; W1-W4 unstarted and whole-Stage-B acceptance not claimed.

W1 dispatch checkpoint (2026-09-20): accepted BASE is
a90faf4f67f9371df71adbc63415e702f8f4016c on
codex/formal-v3-implementation. Linked worktree identity was rechecked against
the common Git directory; ordinary status was clean and HEAD matched origin.
The accepted B3 plan, Stage B design, W1 interface audit and task brief were
re-read. W1 is now ACTIVE under the audited 13-path whitelist because the
original five paths cannot safely provide Store-owned planning identity,
market-specific Source/Worker budgets, and closed F1 DTO validation. The
historical task-W1-draft-brief.md is promoted in place to the active brief so
existing ledger links remain stable. A fresh implementer must use TDD and write
task-W1-report.md; it may not perform Git writes, network/production capture,
scoring, pool generation, merge, or push. Controller retains all Git ownership.

W1 implementation checkpoint d2cc8fefafb5043d71b86cb85038cef4bfa8b979
contains exactly the amended 13 code/test paths. Implementer reported focused
TDD and a 147-test expanded GREEN, but independent review rejected the checkpoint:
4 Critical, 3 Important and 1 Minor finding. Critical defects are escaped proof
mint authority, unverified date-only temporal hashes, non-adjacent/mixed-generation
calendar composition, and stale missing-evidence currentness. Important defects
cover repeated/ineffective request planning, loss of authenticated domain conflicts,
and material gaps in the mandatory attack/import/config regression matrix; the
Minor finding is incomplete DTO semantic validation. Full verdict is retained in
the B3 workspace as task-W1-review-d2cc8fe.md. W1 remains ACTIVE and unaccepted.
The original implementer has been resumed for a focused TDD fix round; no new
commit, W2 start, production operation, merge or push is authorized meanwhile.

W1 acceptance checkpoint (2026-09-20): initial checkpoint d2cc8fe was rejected
by independent review (4 Critical, 3 Important, 1 Minor). Fix checkpoint 39443ca
closed the first defect set but was rejected for mutable/subclassable repository
authority and same-Store currentness gaps. Fix checkpoint ae444d0 closed those
findings but was rejected for one remaining initial-market request cross-Store
enqueue gap. Fix checkpoint 31f727e bound initial market requests to the owning
Store; independent scoped review was CLEAN, specification compliant and quality
approved (`task-W1-fix3-review-31f727e.md`). The frozen-head exact compatibility
command ran once in one process and completed 161/161 tests in 18046.539s, OK,
exit 0: contract 17, source 31, store 32, worker 24, policy values 22, policy
market 25, context schema 10. Full output is in `task-W1-final-compatibility.log`.
All 13 pre/post hashes match in `task-W1-report.md`; `git diff --check` and
`git status --short` were clean, HEAD remained 31f727e, and no Python process
remained. Task W1: complete (commits a90faf4..31f727e, review clean).

W2 dispatch checkpoint (2026-09-20): controller recorded W1 acceptance in pure
documentation commit b875b05; ordinary tracked status is clean. W2 is ACTIVE
from BASE b875b053317e872ebf48a8b379345a3f462ad330. The exact two-path scope,
pure-function authority boundary, mandatory signed-rule-shape TDD matrix, market
partial-effect restrictions, and required focused compatibility command are in
`task-W2-brief.md` (SHA-256
B32FB8BE1A26F577456A2D8B3E8BA33D5E52540C7CEC6A5A077985F2E1E5C4BF).
Fresh implementer owns only `ashare_pipeline/formal_policy_evaluator.py` and
`tests/test_formal_policy_evaluator.py`; controller retains Git ownership. No
project-wide run, network/data operation, scoring, pools, merge or push is
authorized during implementation.

W3 preflight ruling: the accepted `FormalRangeStore` exposes no read-only owner
identity check; same-root planning bindings intentionally do not prove same
StateStore. W3 cannot satisfy its binding same-Store invariant by closure
introspection or root comparison. Scope therefore expands minimally from four
to seven paths: add `formal_range_store.py`, `formal_range_source.py`, and
`test_formal_range_store.py` solely for a closure-owned private validator that
confirms an exact genuine range Store owns the expected exact StateStore and
signature verifier, returns no authority-bearing dependencies, and is not in
`__all__`. Focused TDD must cover genuine/cross-Store/verifier/copy boundaries.
Cost if wrong: three predecessor paths are touched and require W3 plus range
compatibility review; refusing the seam would make W3's same-Store guarantee
unimplementable without an unsafe trust shortcut.
Amended `task-W3-brief.md` SHA-256 after this ruling:
C0084EE07DEB714A98D60661E3486EE1A4EADA84938D496489DCDD0F34EA64EB; it supersedes
the dispatch-time brief hash for W3 review and acceptance.

W3 populated RED ruling: first genuine policy module run completed 23 tests in
2428.164s with 21 pass / 2 errors. One error is owned fixture shape. The other
proves a load-bearing guard composition gap: W3's mandatory final recheck runs
under outer `_metric_batch_guard` `BEGIN IMMEDIATE`; genuine F2 recheck opens the
same guard and its second writer transaction fails locked. Skipping F2 final
recheck is forbidden. Scope expands from seven to nine paths by adding only
`formal_metric_batch_guard.py` and `test_formal_metric_batch_guard.py` for
same-thread, exact-same-provider, exact-same-Store nested reuse of an already
active finalization. Nested reuse opens no second observer/writer, remains under
outer epoch/database/publication checks, and may not authorize another owner or
reentrant publication. Cost if wrong: a shared predecessor guard changes and
requires focused guard plus W3 compatibility review; refusing it makes the
specified final F2 recheck deadlock/fail by construction.
Second-amended `task-W3-brief.md` SHA-256:
E04FC80D428BBC8703CBABF279A0AA7B322256D835125AAE68A9AE3D8F0890EA; this is the
binding brief hash for W3 review and acceptance.

W2 implementation checkpoint 6078c5f77813f649ef09fdcf68ac1a488df9950d
contains exactly the two authorized new code/test paths. Implementer preserved
genuine TDD evidence (13-test missing-module RED, then a focused 14-test
integration-sensitive RED and GREEN) and reported mandatory compatibility
67/67 in 36.867s. Controller independently reran the exact mandatory command:
67/67 in 38.756s, OK, exit 0; no project-wide suite was started. Hashes match
the report and `git diff --check` was clean. Review package
`task-W2-review-b875b05..6078c5f.diff` is 43,929 bytes / 971 lines, SHA-256
EEC3ED2D39D776071655E6F56B7A829CDADEAF43F93B187F8E89615751D8AF66.
Fresh independent W2 task review is ACTIVE; W2 remains unaccepted until both
spec-compliance and quality verdicts are clean.

W2 review at 6078c5f: NOT APPROVED. One Important finding enters fix round 1:
the detached market boundary accepts unknown/inconsistent price states and
unknown runtime pending codes, which can release full-match effects or mark an
actually pending aggregate `complete`. Required fix is closed F1-compatible DTO
validation without granting source authority, plus focused malformed-input
regressions. One Minor is deferred per the SDD protocol: positive-price complete
axis matched/clear branches lack direct focused tests; final review must triage it.
Full verdict: `task-W2-review-6078c5f.md`. Original implementer resumed for
focused TDD fix round 1 from FIX_BASE 6078c5f; only the two W2 paths remain owned.

W2 fix round 1/5 at 68bfe6e: the Important closed-market-input finding is
ADDRESSED and no new Critical/Important breakage was found. Controller's fresh
exact mandatory compatibility run on the fixed bytes completed 71/71 in
40.102s, OK, exit 0. Post-commit hashes exactly match the report
(evaluator C8D239DD..., tests 12F13D49...); HEAD is 68bfe6e, tracked status and
`git diff --check` are clean, and no Python process remains. Scoped verdict:
`task-W2-fix1-review-68bfe6e.md`. The previously recorded positive-price
complete-axis direct-test Minor remains deferred for final-review triage.
Task W2: complete (commits b875b05..68bfe6e, review clean with 1 deferred Minor).
Stage B accepted tasks are now 9/11; W3 is dependency-ready and W4 remains
unstarted. No production capture, scoring, pools, merge or push is claimed.

W3 dispatch checkpoint (2026-09-21): controller recorded W2 acceptance in pure
documentation commit 2c021fc; tracked status is clean. W3 is ACTIVE from BASE
2c021fc8b9bd2ae58eb911e35cfd2a47600b8733. Four-path scope, closure-private
proof authority, full-universe enumeration, same-Store guard, all-source/current
rechecks, rollback/close revocation, fixed hash dependency order, and attack
matrix are frozen in `task-W3-brief.md` (SHA-256
4845A58C3013394C966A99C2B49F1C11660BAE5F728004FBD13BB06F92881ECB).
Fresh implementer owns only the four W3 paths; controller retains Git ownership.
No project-wide run, network/data operation, scoring, pools, merge or push is
authorized during implementation.

## Boundaries

Ruling: R3 fix round 2 uses the scoped fix-loop covering tests (complete Source
module plus parent-correction regression), as prescribed by the SDD fix-loop
instructions; the old 272-case run remains FAILED and is not restated as a fresh
GREEN suite. Project-wide completion verification remains a later gate. The
fix only restores the typed request-error boundary, preserving valid execution
order and keeping parent-integrity failures outside operational conversion.
Cost if this scope misses a regression: later integration/full-suite work must
reopen R3; no production release or final Stage B completion is claimed here.

Implement Stage B only, using the approved spec and three subplans. No production
network, database, signatures, scoring, pool publication, main merge or push.
Keep all data, SQLite/WAL/SHM, progress, history, and tmpj4zv9_fq/. Worktree and
branch were verified; no AGENTS.md was found at worktree/root/ancestor locations.
No dependency install: the existing project venv is available. Fresh initial
baseline passed. First wave R1/F1 is complete after fix round 1 and clean
independent re-reviews; later Stage B tasks remain unimplemented in this run.
The chronological entries below retain that earlier wave status; the current
checkpoint above records the latest accepted tasks.

Ruling: Run independent R1 and F1 implementation workers in parallel, with disjoint
file ownership and controller-only Git writes — user explicitly chose parallel
subagents and approved the plan's parallel boundaries, overriding the skill's
generic serial-implementer default — if wrong, overlapping dependencies may cost
test reruns; never resolve this by discarding another worker's changes.

Ruling: Retain this plan's progress/reports at completion — the user's requirement
to preserve progress/data overrides the skill's scratch-deletion suggestion —
cost if wrong is retained small local audit files, not lost work.

Ruling: Use PowerShell read-only extraction plus apply_patch for brief/package
creation — bash is unavailable and the supplied task-brief recognizes only
Task N headings, whereas the approved plan uses R/F/W headings — cost if wrong is
brief extraction drift, controlled by extracting the original full section.

## Preflight: task self-consistency

| Task | Text/test/file/interface check | Finding / disposition |
| --- | --- | --- |
| R1 | Four-file config/catalog/binding deliverable; exact v1/v2 and M/C/Bx tests | select_range consumes R2 request not yet defined; ruling below |
| R2 | Source/fixture/test, first calendar requests and pure pagination | Later observation factories moved to R3; no stub required |
| R3 | Four-table V7, source continuation, snapshots and receipts | Schema additions do not change V2–V6; all identities rechecked beyond SQL CHECK |
| R4 | Worker + fixture + test; one bounded task per run | No new scheduler or sleep; reused verified files rechecked |
| F1 | Values + runtime fixture + tests | Structured value types belong to later factories; ruling below; range-enabled fixture depends on R1 |
| F2 | Independent policy projection, feature repository installer, tests | Real VerifiedMetricIndustryBatch avoids free applicability bool; old metric gate unchanged |
| F3 | Context selection + fixture/tests | Actual regulatory flag field is active, not value |
| W1 | Market/calendar factory, source request activation, fixture/tests | Source imports private validator only after modules initialize; prevent copy/mint bypass |
| W2 | Pure evaluator + tests | Defaults prohibited; signed_policy reasons need exact rule revalidation |
| W3 | Whole-batch repo/proofs + guard tests | Spec requires require_verified but plan only names require_official; ruling below |
| W4 | Integration + bounded affected regression | Existing passing integration coverage need not manufacture a false RED; actual defects get TDD |

Ruling: R1 delivers range catalog and genuine policy bindings; R2 introduces
select_range together with the real FormalRangeRequestV1 type — preserve the
spec's separate selector without inventing a duck-typed or unimplemented R1
request API — cost if wrong is moving one method between adjacent tasks, not a
different external contract. R1 tests reject catalog/root/anchor bypasses; R2 tests
cover genuine new request selection and old/new separation.

Ruling: F1 implements scalar PolicyValue and explicitly typed missing/conflict
records; nonmissing event/calendar/market values are accepted only when their
producing task supplies the closed validator (F3/W1), never as arbitrary dicts —
the spec forbids fabricated compound evidence and later contracts are not yet
implemented — cost if wrong is a small additional F3/W1 values-module change.

Ruling: Final public proof types expose require_verified per the spec;
require_official may be an equivalent captured alias for plan callers — the spec
is binding and neither name may confer independent weaker authority — cost if
wrong is one compatibility alias and its boundary tests.

## Preflight: every shared-file/interface pair

| Producer / tasks sharing files | Consumer / later tasks | Interface and disposition |
| --- | --- | --- |
| R1 | R2 | RangeBinding/RangeConfig; source selector activation belongs R2 |
| R1 | R3 | Signed binding and shared range fixture; R3 starts after R2 |
| R1 | R4 | Shared range fixture; R4 starts after R3 |
| R1 | F1 | add_range_documents only for range_enabled=True; defer that integration check until R1 accepted |
| R1 | W1 | Shared range fixture + bindings; W1 waits R4 |
| R1 | W3 | Same-root bindings consumed through range store; no alternate loader |
| R2 | R3 | Request/Fetch and source file; R3 adds genuine observation continuations |
| R2 | R4 | Source fetch + shared fixture; serial ownership |
| R2 | W1 | source market_requests factory and private proof validator; no duck types |
| R3 | R4 | RangeStore and lease/attempt identities; serial ownership |
| R3 | W1 | Genuine current observations, shared fixture; all members rechecked |
| R3 | W3 | Same-store range dependencies/receipt/raw reads |
| R3 | W4 | Persistence and resume behavior; W4 only after all implementation |
| R4 | W1 | Bounded worker and next-request planner; no network in scoring |
| R4 | W4 | Restart/idempotency integration, same saved receipt identities |
| F1 | F2 | PolicyValue, Decimal bridge and shared runtime fixture; serial ownership |
| F1 | F3 | Scalar/missing values and shared fixture; compound validation added by producer |
| F1 | W1 | Decimal/canonical helpers and runtime fixture; W1 owns compound market validator |
| F1 | W2 | Decimal context and value/pending vocabulary |
| F1 | W3 | Errors/canonical/fixture, with final proof publication separate |
| F1 | W4 | Shared runtime fixture; integration only at end |
| F2 | F3 | Shared runtime fixture; F3 after F2 |
| F2 | W1 | Runtime fixture shared even if production modules independent; controller serializes fixture edits |
| F2 | W2 | Financial selections converted to pure scalar/annual inputs |
| F2 | W3 | Current financial selection + recheck; same provider/store |
| F2 | W4 | Fixture and optional/annual regression checks |
| F3 | W1 | Runtime fixture is shared: production work may parallelize, fixture writes may not |
| F3 | W2 | Exact boolean/enum/authorized event values; no missing=false |
| F3 | W3 | Current state selections + recheck |
| F3 | W4 | Runtime fixture and state/regulatory regression |
| W1 | W2 | Independent price/veto wire, no pure-function proof |
| W1 | W3 | Current market/calendar members + recheck and shared fixture |
| W1 | W4 | Window boundary/pagination/lineage integration and shared fixture |
| W2 | W3 | Pure rule decisions/aggregation; batch factory grants final qualification |
| W2 | W4 | Determinism, cap/prohibition/pending tests |
| W3 | W4 | Unique public batch API and fixture helpers |

Ruling: F3/W1 parallelism excludes edits to tests/formal_policy_runtime_fixtures.py
and formal_policy_values.py at the same time; coordinate ownership before those
edits — the file map shows shared files despite independent production modules —
cost if wrong is reduced parallel speed, not a merge conflict.

## Task status

- [x] R1 signed range config/catalog/bindings
- [x] R2 range source request/transport/parser
- [x] R3 V7 persistence/receipts
- [x] R4 bounded resume worker
- [x] F1 values/bridge/runtime fixture
- [x] F2 financial/annual policy projection
- [x] F3 state evidence
- [x] W1 calendar/market proofs
- [x] W2 pure policy results
- [ ] W3 whole-universe revocable publication
- [ ] W4 integration/final review

Each code commit is scoped by task path whitelist and serial controller ownership.
Subagents write reports, not Git state; reviewer packages use exact task paths and
recorded BASE, so another parallel task is not accidentally reviewed as this one.

## Initial worker preparation

- R1: /root/stage_b_r1_implementer, gpt-5.6-sol/high, isolated context, read-only
  preparation until baseline completes. Brief/report in the B1 workspace.
- F1: /root/stage_b_f1_implementer, gpt-5.6-sol/high, isolated context, read-only
  preparation until baseline completes. Brief/report in the B2 workspace.
- Baseline session 12861: policy contract/registry/guards with unittest -q;
  observed CPU progress, no error/output yet. No worker may mutate baseline files.

Ruling: R1 calls the actual captured FormalPolicyRegistry.require_verified method,
not the plan's nonexistent require_official name — no need to change the existing
policy registry or its API — cost if wrong is a corrected method reference, with
genuine-type/source verification still mandatory.

Ruling: F1 validates signed_policy pending syntax only; concrete current-rule
authorization remains W2's mandatory semantic gate — PolicyValue is an explicitly
non-authoritative DTO and its from_dict(wire) lacks registry context — cost if
wrong is a W2-boundary test relocation; no DTO is accepted as formal evidence.
F1 rejects malformed code/rule_id, unknown runtime codes, bad hashes/closed keys;
W2 must test non-current-rule and unsigned reason rejection.

Baseline GREEN: session 12861 exited 0, 94 tests in 239.275 seconds, OK.
Both implementers received BASELINE GREEN and may now use TDD in their disjoint
file lists. The task briefs' controller rulings remain authoritative; corresponding
subplan API/test wording has also been corrected in documentation, separate from
worker code. No schema/source production behavior is changed by these doc edits.

Ruling: F1 templates is an exact security_id→template_id map, with matching signed
memberships and frozen exchange rows. Add only an optional exchange_rows keyword
to the existing FinancialFixture helper instead of duplicating its constructor —
the inherited constructor otherwise freezes only three securities, so the plan's
five-template fixture cannot be built — cost if wrong is a test-helper API change;
old default/population fixture behavior must remain covered. F1 whitelist is now
four files, including tests/formal_metric_feature_fixtures.py.

F1 first scalar slice reported 10 GREEN tests; full task remains in progress.
R1 has prepared tests, source initially untouched; workers coordinate source-stable
intervals for F1 fixture runs. No task has been accepted or committed yet.

Ruling: Give current roe/margin/profit slots separate signed test-only
fixture.policy.current.* fact keys, retaining annual fixture.policy.* keys and
explicit FY2025/FY2021–2025 periods — rewriting FY0 to FY2025 otherwise collides
with the annual FY2025 slot while helper arguments permit independent values —
cost if wrong is test-fixture identity churn; no production mapping is approved.
F1 must test differing current/history inputs against distinct actual facts.

R1 reported RED: 9 tests / 14 expected missing-feature errors, exit 1, before
module/v2 implementation. First focused GREEN run started; formal_sources.py is
stable for F1 v1-source fixture tests. R1 will notify before further source edits.
F1 reported initial scalar GREEN plus added huge-int bridge boundary coverage;
fixture failures are being corrected and final evidence is not yet available.

Ruling: F1 policy-only facts must retain the genuinely blocked legacy V6 feature
bundle. Validate distinct signed current/annual ASTs, exact fact periods/units and
values, and authenticate the persisted receipt through require_complete=False,
not merely SQL counts or unverified hashes. The legacy history gate marks every
slot untrustworthy when required old metrics are absent; F2 owns the independent
optional policy projection. Cost if wrong is moving a derived-value assertion
to F2; never weaken the old completeness gate to make fixture tests pass.

R1 reported focused GREEN: 9 tests in 29.248 seconds, exit 0; compatibility run
is in progress. Source is stable for provisional F1 range_enabled integration;
neither task is accepted until its independent review is clean.

Documentation checkpoint d88caf6: three subplans only, clarifying actual APIs,
R1/R2 ownership, F1 scalar authorization and fixture/history boundaries, and W3
proof method naming. Staged whitelist and diff --cached --check verified clean;
Git emitted only its existing LF-to-CRLF worktree conversion notices. No code,
data, progress, or other files entered this commit.

R1 implementation checkpoint ed25b6a553f0738c4de24dd88583c28061d196e0:
112 compatibility tests passed in 285.729 seconds, exit 0; explicit Bx-as-C
extension passed 1 test in 7.304 seconds afterward (test-only addition).
Staged check caught one blank line at EOF in the new fixture, which the worker
removed without semantic changes; rechecked index clean and exact four files.
Fresh independent /root/stage_b_r1_reviewer (gpt-6-astra/high) has the filtered
base 7cf6b59..ed25b6a diff package. R1 is NOT yet accepted.

Ruling: Keep the tested fixture.policy.current.equity key along with the other
three current keys — naming all new current test slots consistently changes no
old static fixture or public contract, and signed AST/fact identity is exact —
cost if wrong is an internal fixture naming adjustment. F2 must consume signed
selectors/AST, not hard-code test fact keys. No redundant test rerun for a mere
clarification with no code change.

F1 implementation checkpoint db093077c57a180499a96c1182a603c50ebdb00e:
85 prescribed tests (16 new F1 tests plus policy registry/legacy metric-feature
regressions) passed in 265.839 seconds, exit 0. All four task files frozen;
staged whitelist/check clean, no data included. Fresh independent
/root/stage_b_f1_reviewer (gpt-5.6-sol/high) has the filtered base 7cf6b59..db09307
package. R1 and F1 remain pending review, not accepted.

R1 review returned four Important findings (see task-R1-fix1-brief.md): first-use
trust-method substitution, mutable RangeConfig construction/type fingerprints,
weakened request-template safety, and global parent/child retention. Root checked
the named trust/capture/fingerprint and reference code; findings accepted.
Original-worker followup failed twice with agent thread limit reached, including
after reviewer completion; no fix work was dispatched by those failed calls.

Ruling: R1 fix may add formal_range_format.py to separate pure parsing from graph
binding, preserving contract exports while removing circular initialization.
Use controlled captured interfaces/private closure authority, never lazy mutable
first-use trust. Do not change old policy registry. Cost is a fifth pure module
and import adjustment; authorization and data semantics do not broaden.

Fresh fix-worker spawn also hit the thread limit. Available completed implementation
seat /root/policy_stage_a_final_fix successfully received the R1 fix1 brief; its old
Stage A task remains complete and untouched. This is the bounded fallback to the
unavailable original R1 implementer, not another review seat. R1 reviewer remains
independent and will re-review only the fix diff. R2/F2 not started while their
prerequisites are unaccepted.

F1 review: two Important findings accepted after root code check: undocumented
ASCII enum grammar; fixture normalization/membership checked too late, allowing
invalid calls to enqueue/persist before failure. Exact fix scope and zero-mutation
negative requirements are in task-F1-fix1-brief.md. No economic rule changed.
Thread limit fallback reuses the completed R1 review seat for F1 implementation;
it must not edit R1, and original F1 reviewer remains independent for fix review.

R1 fix1 worker reported valid RED (16 tests, 26 failures/4 errors, 62.022s) and
focused GREEN (16 tests, 40.798s, exit 0). Production now separates pure format,
uses eager captured closure trust/constructors/private authority, and removes
global object retention. Source/range stable and coordinated with F1; prescribed
four-module compatibility running. No fix commit or re-review yet.

F1 fix1 worker reported RED for both concrete regressions (4 state-mutation
failures / 5 enum errors), then 2 focused tests GREEN in 6.891 seconds. Three-module
compatibility running against coordinated stable R1 source. F1 code is frozen.
Root captured SHA-256 for all nine R1/F1 files and started fresh joint verification
session 85820: python -m unittest tests.test_formal_range_contract
tests.test_formal_policy_values -q. Result pending; this is integration coverage
of the amended pair, not a repeated broad legacy suite.

Root joint GREEN: session 85820 exited 0, 34 tests in 99.500 seconds, OK.
All nine R1/F1 code/test file SHA-256 values match the pre-run frozen capture;
no implementation changes occurred during joint verification. Broad worker
regressions and independent scoped fix re-reviews are still required.

F1 compatibility GREEN: 87 tests in 287.816s, exit 0; no warnings. Fix checkpoint
ceaa89b1b325afd0493643abbfb3062dbafce555 contains exactly three F1 code/test files;
index whitelist/check clean. Independent F1 scoped re-review returned both
findings ADDRESSED, no new breakage or out-of-scope observations. Report preserved
as task-F1-fix1-review-ceaa89b.md. F1 review is clean; final wave closure awaits R1.

R1 compatibility GREEN: 119 tests in 336.446s, exit 0; frozen hashes unchanged.
Fix checkpoint 36f8a780883d744bf0d1a7d32cc1d60a8ebf9aca contains exact four changed
R1 files (including approved format module; original fixture unchanged); staged
check clean. Original R1 reviewer now independently checks filtered fix diff
ed25b6a..36f8a78, after finishing its unrelated F1 fix assignment. R1 not accepted
until that verdict is clean. No data/progress/main/push operations.

## Wave 1 accepted

Task R1: complete (implementation ed25b6a + fix 36f8a78; scoped review clean).
Task F1: complete (implementation db09307 + fix ceaa89b; scoped review clean).
R1 re-review addressed all four findings, with no new breakage/out-of-scope items;
the full verdict is preserved in task-R1-fix1-review-36f8a78.md.
Fresh root joint verification: 34 tests in 99.500s, exit 0, unchanged nine-file
hashes. Worker final compatibility: R1 119 / 336.446s; F1 87 / 287.816s, both exit 0.
Counts overlap and must NOT be added as a unique-test total.

Next safe wave: R2 genuine bounded requests/transport/parser/select_range and F2
independent financial/annual projection. Use current B1/B2 plans and recorded
interface rulings. No new production source mapping, threshold, signature, real
crawl, score/pool output, merge or push has been authorized or performed here.
Do not restart R1/F1 or the initial 94-test baseline merely because context was
compacted. Reuse these committed foundations and retained fixture/report records.
Stage B is 2 of 11 tasks complete, NOT full Stage B or a finished scoring system.

Final handoff HEAD: f4ed417fe6e64e324e9c725c3b185f7a10c52221, branch unchanged.
Six commits this wave (two implementation, two reviewed fixes, two API/architecture
documentation checkpoints). Exact execution-base..HEAD file inventory: nine code/
test files and three plan documents, no data/SQLite/WAL/SHM/progress/history files.
Final git diff --check clean; index/tracked worktree clean. Only pre-existing
untracked tmpj4zv9_fq/ remains, untouched. All nine final code/test hashes still
match root joint verification. Retained ignored ledgers/reports are local recovery
records, not committed or deleted. No merge/main change/push performed.

## Wave 2 startup — R2 / F2

User continued. BASE f4ed417fe6e64e324e9c725c3b185f7a10c52221, linked worktree and
branch verified, no superproject; index/tracked files clean, same untouched temp
directory. All nine foundation hashes match retained wave1 verification. Fresh
scalar smoke: 11 tests in 0.001s, exit 0. Do not repeat accepted R1/F1/94 baseline.
No AGENTS.md found at workspace and relevant ancestors; existing venv retained.
Main read master, B1/B2/B3 and binding Stage B spec fully; prior all-task/pair
preflight table remains valid except the focused corrections below.

| Pair/task checked | Finding / disposition |
| --- | --- |
| R2 internal consistency | Request/fetch vs persisted observation split remains R2/R3; four-file whitelist; source select_range must avoid circular/lazy trust regressions |
| F2 internal consistency | Method cyclic flag cannot alter already signed graph; constructor-only fixture configuration ruling below |
| R2/F2 source→fixture dependency | Disjoint write lists; coordinate source-stable fixture imports before combined compatibility |
| F2/F3/W3 fixture consumers | No downstream plan calls method-level cyclic; constructor option preserves signatures of production repositories |
| F2 feature repo/provider imports | Existing guard imports feature repo; preserve original identity guard and use controlled installation, not lazy public-method capture |

Ruling: R2/F2 run in parallel with disjoint task whitelists, root-only Git and
source-stable test windows — explicit user parallel preference and accepted
dependency map — cost if wrong is bounded integration reruns, never lost edits.
Ruling: Put test-only cyclic=True configuration on PolicyRuntimeFixture ctor,
derive financial_selection membership with no boolean argument, permit pre-sign
mutate hook for AST tests — a completed signed graph cannot be changed at read
time — cost is a small test-helper API correction, no financial-policy change.
Ruling: R2 implementations is a sealed constructor-time explicit registration
dependency keyed by signed versions, not a per-fetch arbitrary callback or
self-reported version — same trusted runtime boundary, actual methods rechecked —
cost is a minimal local registry contract, no production registration approval.
Task briefs contain full task text, exact spec excerpts and these corrections.

Dispatched fresh isolated workers successfully (no thread-limit fallback needed):
- /root/stage_b_r2_implementer, gpt-5.6-sol/high, R2 four-file whitelist.
- /root/stage_b_f2_implementer, gpt-6-astra/high, F2 four-file whitelist; higher tier
  for annual AST/provenance and independent legacy-guard integration judgment.
Both received BASE f4ed417, genuine dependency handoffs and report paths. No Git
writes delegated. Root updated only B2 plan's impossible method-level cyclic
wording to match the recorded pre-sign test-fixture ruling.

F2 preflight ruling confirmed with worker: define independent installer in feature
repository and invoke it from financial module initialization only after controlled
eager import of completed metric_batch_guard. Capture genuine owned-provider type,
actual resolve and guard then; do not use first-selection public aliases as trust.
Reuse existing genuine repository registration, no __init__ wrapper required, so
pre-existing authentic repositories remain usable. Remove installer export after
installation. Require pre-first-selection provider alias/method replacement tests.
Cost: bounded import-order integration, no mutation of the legacy metric gate.

StateStore has no authoritative list-all-financial-issues API. F2 must compare all
persisted facts plus complete provider-owned issues and rebuilt authenticated V6
receipt, with rereads. Do not invent a database-wide issue history or weaken issue
ownership. This existing storage limitation is explicit in the worker report.

Root docs-only checkpoint 08b8254 records constructor-only pre-sign cyclic fixture
configuration in B2. Verified exact one staged path and clean staged diff check;
Git emitted only the existing Windows LF/CRLF notice. Task BASE remains f4ed417;
review packages will filter task whitelists over that full range. Implementation
files were neither staged nor changed by root, and no data/progress was committed.

R2 worker proposes request authority built before importing formal_sources, with
source select_range installed at module completion and capturing exact request
type/private verifier. Root allowed implementation within four-file whitelist,
conditional on independent-process source-first/range-source-first and transitive
range-contract/context-schema/registry-manifest-first import tests. The same
captured private verifier must authenticate requests in both selection and source;
no first-call public alias establishes authority. No additional files approved.

While workers implement, root captured all ten V2-V6 table/index DDL constant
fingerprints in legacy-ddl-before-v7.md by read-only AST literal extraction.
No project module was imported and no database opened. R3 must retain these exact
canonical values; this is a preparation check, not R3 implementation or acceptance.

R2 indirect import hypothesis reproduced by F2: partially initialized
formal_context_schema -> formal_sources eager range-selection install ->
formal_range_source -> formal_range_contract eager trust capture -> missing
context_schema._descriptor. Root read systematic-debugging and checked the new
import path. R2 proposes one-shot registration as a within-whitelist fix, but root
requires proof against pre-registration hijack: forged __module__/name plus fake
verifier must never confer select_range authority. Awaiting concrete protected
design; pure request-authority split may be considered if needed. F2 instructed
not to repeatedly run known-broken imports; continue disjoint implementation and
wait for explicit source-stable before compatibility. No accepted task regressed
in a commit: R2 edits remain uncommitted development state.

Ruling: Approve one additional pure formal_range_request.py (R2 now five files)
instead of one-shot registration — worker confirmed pre-registration hijack is
real and simple module/name checks do not establish authentic authority — cost
is one small module and an explicit pure/live validation split. Pure module owns
request type/private mint/sealed records; source owns live binding/config/root
checks before/after operations; select_range must still verify same-root identity.
No callback registration retained. Root synchronized B1 and task-R2 brief with
this decision; request public import path remains compatible via source reexport.

Ruling: Source registry authenticates a signed source blob, not an entire manifest
root; identical complete source bytes may be referenced by multiple genuine roots.
Do not invent an absent registry root field. To reject a different source blob
with the same selected ENTRY, approve read-only RangeBinding.source_registry_hash
from existing verified parent role_hashes['source'] and carry it only in private
request records. select_range compares genuine registry_hash plus full config and
anchors. Request wire and binding wire/hash remain unchanged. R2 whitelist now six
files, adding only this getter in formal_range_contract.py. Cost is one additional
getter and focused R1 contract compatibility; request root remains bound to the
real graph and live source checks. Require different-blob/same-ENTRY rejection and
identical-source/multiple-root reuse boundary tests. B1 and brief synchronized;
final compatibility adds test_formal_range_contract, not the full old R1 suite.

F2 status: independent projection/selector implementation and 24 tests authored;
initial RED 7 failures in 24.690s; first GREEN stopped by diagnosed R2 import cycle.
Static compile passed but is not behavioral validation. Waiting for source-stable.

Root B1 architecture documentation checkpoint ce5c592: exact one staged plan
path, clean whitespace check, no implementation/data/progress files. Task BASE
still f4ed417. F2 received R2 source-stable interval and started fresh focused
26-test run; cross-security/template/root case reported GREEN so far. Full run
is pending and no completion claim is made from partial output.

R2 milestone: pure authority split/getter integrated. Five independent import
entrypoints (sources, range_source, range_contract, context_schema,
registry_manifest) all exit 0. Focused behavioral run still pending; one authored
test asserted the raw fixture builder raises rather than invoking the actual
parser and will be corrected. Remaining self-review includes full source identity,
DTO/time exactness, mutation seals, final compatibility and handoff contracts.

Root directed a concrete R3 handoff check: draft R2 document/snapshot parser
rejects capture after freeze, while existing formal_time.is_visible_at depends on
proven effective time, not retrieval cutoff. Worker asked to cover late capture of
proven pre-freeze publication and distinguish date-only unproven visibility as
domain evidence insufficiency. Draft document also lacks explicit upstream/
document source-version metadata needed by R3 current selection; worker asked for
minimal closed wire supplement and real pagination-count basis, never deriving
upstream version from insertion/capture order. Awaiting proposal; not an accepted
behavior or a production-data change. Root did not edit worker implementation.

F2 self-review correction evidence: 3 focused RED tests exposed leading-version
ambiguity and class lookup substitution (2 failures, 47.913s). Five focused GREEN
tests passed in 63.609s, including repeated AST leaves/legitimate FY2020 opening
balance, noncyclic minimal inputs and explicit provider. Stored freeze comparison
now compares instants (+08:00 vs +00:00), not equivalent strings. Four F2 file
hashes captured and frozen before prescribed compatibility; worker running it.

Ruling: Accept minimal R2 document/manifest time/source-version supplement needed
for R3. Include document publication precision, source_updated, effective-time
claim/evidence hash, capture, upstream generation and pagination basis. Cost is
new closed DTO fields and replay equality checks; no change to request wire or
economic policy. Generation tokens are opaque consistency IDs, not sortable
versions. A hash alone does not prove date-only visibility; rows retain independent
time evidence, and no document-time fallback is inferred. Pagination basis is a
label for an actually registered parser contract, not a DTO's authority claim;
source total count and current-page row count must stay distinct.

Workers coordinated: F2 compatibility proceeds on its four frozen files while R2
adds only its own necessary DTO changes. F2 report must identify this integration
state. Root will run fresh joint verification after both branches freeze; do not
rerun full F2 compatibility solely because another task wrote its files. Any real
loading/contract failure remains actionable. Final acceptance is still pending.

R2 metadata change TDD: 2 targeted RED schema-field errors, then 2/2 GREEN in
26.272s. Document total record_count vs page_record_count are distinct; parser
checks pagination_evidence against actual signed/registered contract. Late public/
capture times remain source observations, not visibility proof; unresolved
date_only explicit null effective/evidence fields. Replay binds source version
metadata. Root synchronized these R3 handoff requirements into B1 and R2 brief.

Prepared task-R3-draft-brief.md and task-F3-draft-brief.md as requirements-only
scratch. They explicitly say NOT DISPATCHED and lack BASE/accepted predecessor
handoffs. No R3/F3 work started; do not treat drafts as authorization to bypass
pending R2/F2 independent reviews.

F2 current compatibility surfaced a test-only wrong table identifier
formal_feature_bundle; actual V6 table is formal_feature_set. Root instructed
worker to finish and preserve full output, correct only that test, run focused
case, and report final hashes. Do not attribute other failures to this typo.
Ruling: avoid duplicate worker full compatibility rerun for the single test fix;
root final fresh joint command will include policy_financial, feature_repository,
metric_features, metric_batch_guard and range_source after both freeze. Cost is
one larger root integration run, which provides the required final complete GREEN
instead of claiming the earlier failed command passed. Reviews remain separate.

F2 natural progress confirms no stall: all 26 new cases reached completion,
25 passed and only receipt-tamper table-name setup error; legacy repository API
and first 24 repository cases GREEN, progressing at restart_exact_historical.
metric_features and batch_guard still pending in the same original process. No
duplicate process launched. Root awaits final output/focused correction/report.

F2 natural update: legacy feature_repository and metric_features modules completed
GREEN; final metric_batch_guard module running with only known test-table typo.
R2 focused 23/23 GREEN in 420.231s, but emitted ResourceWarnings from invalid
constructor fixture cleanup. Worker removed that fixture resource leak by making
the fixture wholly in-memory, then froze all six files and began prescribed
range_source/sources/range_contract compatibility. Final pristine output pending;
the warned focused run is not used as the final clean acceptance evidence.

F2 prescribed compatibility completed: 100 tests in 819.768s, exit 1; exactly one
OperationalError for nonexistent formal_feature_bundle in receipt-tamper test.
Other 99 tests passed, including all 74 legacy cases. Worker corrected only that
test SQL table to formal_feature_set and is running the focused case. Production
files remain frozen. Root final joint command still required to record full GREEN.

F2 final corrected receipt test GREEN: 1 test /14.206s, exit 0; full report retained
as task-F2-report.md (worker report SHA256 7414267e7a741d5dbd271f2f911ed467ae1bf7c2eefee5389eeb066df13e0b77).
Root read full report, verified all four final SHA256 values, and independently
ran explicit matching-owned-provider test: 1 /0.968s, exit 0. Exact four-path stage
and diff check passed. Checkpoint fb4f9a681303dbe5ce53ef2007e69e0cb42ab0fe contains
only F2 code/tests (897 insertions,15 deletions); no data/progress/docs.

F2 independent review dispatched to fresh /root/stage_b_f2_reviewer,
gpt-6-astra/high, for subtle receipt/provider/annual AST authenticity judgment.
Package task-F2-review-fb4f9a6.diff is filtered full BASE f4ed417..fb4f9a6, includes
all four files and full U10 context, 56,512 characters, untruncated. Reviewer has
brief/report/template and pending root full-joint verification context; read-only,
no broad crawl or repeated suites. No task completion or acceptance yet.

F2 review returned spec issues/Needs fixes: two Important findings (quarter AST
period attribution plus quarter leading-conflict classification; indiscriminate
global issue impact). Full review retained in task-F2-review-fb4f9a6.md. Root read
actual FormalFactIssue fields and issue extraction plus the affected projection
branches. Followed receiving-code-review process; no controller code edits.
Task F2: fix round 1/5 started with original /root/stage_b_f2_implementer, BASE
fb4f9a6. New quarter/scoped-issue regressions and focused amended-code runs required.

Ruling: Complete issue authentication/identity is distinct from domain impact.
Keep full provider issues bound and reread, leave old V6/metric behavior untouched,
but independently evaluate provably unaffected policy dependencies. Impact scope
must be authenticated from actual mapping/dependencies, never guessed from free
details strings or source_field==fact_key; unknown scope remains conservative.
Worker to propose minimal safe scheme before implementing that part. Cost is a
scoped policy-only projection plus extra tests, not new provider/storage authority.

Task F2: minor (recorded): Git LF/CRLF advisory remains in diff-check output; root
and worker reports explicitly distinguish it from clean test output. No code fix
needed for existing platform line-ending policy.
Reviewer cannot-verify items: W3 same-store Context recheck and global Stage B
publication remain explicit future W3/W4 gates, not F2 authority. Root final joint
test remains pending and will be run after fixes/final source freeze. F2 is NOT
complete; do not dispatch dependent F3 from the draft yet.

F2 issue-scope fix design accepted: same-root genuine SignedFinancialMappingRegistry,
exact signed mapping_id/source_field and request-exchange binding may scope only
field-level extraction codes required_source_field_missing, duplicate_source_field,
nonnumeric_value to actual AST metric dependencies. No year/source-occurrence
identity exists in FormalFactIssue, so do not trust details['period']; a scoped
annual-ROE issue conservatively affects every ROE annual slot but not independent
equity. Unlocatable issues remain global. Full issues still bound/rechecked;
internal slot_issues exposes authenticated per-slot impact lists. Use unchanged
evaluator per slot. Legitimate schema without financial mapping capability remains
conservative; malformed/invalid declared financial schema is integrity/contract
failure, never an exception-text fallback. New mapping trust methods captured at
initialization and rechecked. Same four-file whitelist; no public signature change.

R2 self-review found equality-equal replacement of an implementation value tuple
escaped the registry seal. New RED: 1 failure /23.995s; exact tuple identity fix
GREEN: 1 /28.311s. Production changed, so worker restarted full prescribed 79-test
compatibility on newly frozen six files. Root joint verification has not started,
so no root run was invalidated. Final compatibility/report still pending.

Root synchronized B2 and task-F2 brief: internal slot_issues, authenticated impact
scoping, exact quarter component attribution and tie integrity, plus accurate
persisted-facts/provider-owned-issues wording for the existing storage API. This
is the previously recorded ruling made explicit, not an added storage capability.

F2 fix RED observed: Q1/Q2 leaf attribution duplicates (2 vs1,4 vs2), quarter tie
not rejected, malformed mapping not rejected, mapping alias/method substitution
not rejected; independent-current-value local-issue assertion also failed before
fix. Worker added captured signed mapping scope and exact quarter components.

Ruling (supersedes the hypothetical legitimate no-financial-schema fallback):
Inspection found fixture-v1 only as a synthetic placeholder, not an approved
production no-capability schema. Do not hardcode fixture-v1 into production.
Policy mapping reads must use the supported genuine financial v1 loader; unknown,
claimed v2 or malformed versions fail. Promote PolicyRuntimeFixture's default
mapping to a genuine synthetic signed financial v1 graph using its existing
helper, preserving default values/members. All issue tests then use real signed
mapping; unlocatable issues remain conservative within that valid contract. Cost
is a test-fixture realism change and adding test_formal_policy_values to root's
final joint compatibility. No edits to external old metric fixtures/V6 permitted;
no new production schema whitelist or economic mapping approved.

R2 final rerun natural progress: first 21/23 source tests GREEN, including exact
implementation-value identity, independent imports, late/date-only observations,
source-blob equality, redirects and parser seals. Last two source cases then
legacy sources/range_contract follow in the same 79-case process. All six R2
files unchanged during this run; full result still pending.
F2 accepted removal of production fallback and real signed default test mapping;
new claimed-financial-v2 RED: 1 failure /8.192s. Existing seven-case amended run
progresses with quarter and scoped-issue cases GREEN; final fix report pending.

R2 final compatibility GREEN: 79 tests /532.242s, exit 0, no warnings/errors.
Root read complete task-R2-report.md including exact request/DTO/manifest/runtime
registry handoff; matched all six frozen SHA256 values; independently ran pure
interval/page boundary tests, 2 /0.000s, exit 0. Exact six-path staged check passed.
Checkpoint 38644671691e244164c267b07732d9756a06142e contains only R2 code/tests,
1399 insertions/1 deletion; no data/progress/docs or F2 changes.

R2 review dispatched fresh /root/stage_b_r2_reviewer, gpt-6-astra/high for source
authority and replay judgment. Package task-R2-review-3864467.diff contains all six
paths over full f4ed417..3864467, full U10 context, 72,398 characters, untruncated.
Reviewer read-only; no duplicate suites/broad crawl; exact brief/report/rulings
supplied. R2 not accepted until verdict and final root joint gate are satisfied.

F2 fix1 final 12-case amended process progressing GREEN through quarter facts,
scoped/unscoped issues and placeholder/malformed schema rejection. Final mapping
substitution/exchange/version checks plus three old boundaries still pending;
four amended file hashes captured with no subsequent worker changes.

F2 fix1 final amended run GREEN: 12 tests /211.058s, exit 0, no warnings.
Root read complete appended report and matched all four final hashes (report
e56f9551f97350a045b40224b72d8be4ded57e1b2cdeed4f38330dd7d698bf9e).
Root independent quarter-leading-conflict regression GREEN: 1 /5.139s, exit 0.
Exact four-path stage/diff check passed; existing LF/CRLF advisory recorded.
Checkpoint 16874408e9f68886d5a5cf223dd703aa4c1b2915 contains only F2 fix code/tests
(249 insertions,20 deletions), no docs/data/progress. Scoped re-review resumed
original /root/stage_b_f2_reviewer, package task-F2-fix1-review-1687440.diff:
fb4f9a6..1687440, four paths, full U10, 35,908 chars, untruncated. Two findings
pending verdict. Final root six-module joint verification still required.

R2 initial review returned four Important confirmed authority failures: arbitrary
root_guard callback request minting with invalid bounds/bool page; instance _parse
shadow bypassing registered parser and normalizer; cross-root and cross-source-blob
request execution; bool/int fetch seal mutation. Full report retained in B1
task-R2-review-3864467.md. Root read complete report and inspected all affected
branches; no conflict with approved spec. Reviewer focused in-memory probe exit 0
reproduced all four, no code writes or repeated suites.
Task R2: fix round 1/5 started with original /root/stage_b_r2_implementer,
review BASE 38644671691e244164c267b07732d9756a06142e, same six-file whitelist.
New RED regressions and amended-code/import compatibility required. Request mint
authority must derive from genuine binding, not caller registration/guard claims;
request execution must match actual source binding root AND full source hash.
R3 receipt/file authentication and coverage/final visibility remain explicit
downstream gates, not claims conferred by R2 RangeFetch. R2/F2 NOT accepted yet.

Task F2: fix round 1/5 (2 addressed, 0 open; commits fb4f9a6..1687440).
Scoped original reviewer returned all findings addressed, no new breakage or
out-of-scope observations. Full report retained as task-F2-fix1-review-1687440.md.
Review gate clean; completion line intentionally waits for fresh root joint run.
Root docs checkpoint 0b1ce9ee5e7abf376b5efb661db36125e4218452 records previously
ledgered B1 timing/pagination and B2 issue-scope/mapping/actual-storage rulings;
exact two plan files only, diff check exit 0 with known EOL advisory, no data.

R2 fix1 RED: 7 tests /141.184s, exit 1, 8 failures+2 errors. Worker reproduced
all four exploit classes including three numeric fetch fields; genuine-request
post-mint mutation seal already passed. No production edits made before ruling.

Ruling: Supersede the pure-only formal_range_request authority placement for R2.
The eager formal_sources -> request -> genuine RangeBinding graph is cyclic;
exporting a temporary mint/capability/installer from the pure module permits
direct-import theft before a binding exists, even if deleted after initialization.
Accept the smallest six-file dependency inversion: formal_range_source eagerly
loads the genuine completed RangeBinding then owns request type/registry/private
mint in its closure; formal_range_request is only a compatibility re-export.
formal_sources must no longer eagerly depend on request authority. Source module
initialization installs its closure-captured select_range implementation on the
genuine SignedSourceRegistry, without exported caller registration/first-use alias
capture. Genuine registry reads must use captured authentic original methods;
no duck type or caller guard can mint. Wire/public APIs and complete source hash
semantics unchanged. Why: resolve the demonstrated mint bypass without adding a
second weaker authority or broad graph refactor. Cost if wrong: import/lifetime
compatibility risk; cover fresh-process import orders, pre-first-use substitution,
and replay/source selection regressions, then independent scoped review. No new
module or whitelist expansion is authorized. Source/contract original-class
substitution must fail safely; absence of select_range before range initialization
must not produce a weaker temporary entry point.

F3 preflight (not dispatched): inspected existing PolicyValue present-compound
rejection and actual Context event shape. The prior F1/F3 ruling remains required:
F3 will add the closed event_record validator and covering values tests; actual
fields are event_id,event_date,quantified_value,unit, not a bare decimal. Draft
brief now records that final whitelist must expand from three to five files to
execute this already-assigned responsibility. No F3 code changed or task started.

R2 fix1 focused amended GREEN: 7/7 tests /103.067s, exit 0. Worker self-review
also found module-visible request/fetch mint handles: new RED 1/0.000s, then
private-closure mint fix GREEN 1/0.000s. Functionally frozen, fresh imports and
compatibility/report still pending. Root offered deduplicated final verification:
if worker full R2 compatibility has not started, worker does focused imports and
normal-path checks then report/review; root final joint adds formal_sources and
range_contract to the existing six modules, covering both branches in one run.
If worker full command already started it completes and original six-module root
gate remains. Await worker confirmation before changing the recorded final gate.

Worker clarified only full test_formal_range_source (33 cases), not 80+ source/
contract compatibility, was already started. It continues without interruption.
Ruling: Final stable-code acceptance uses that complete worker range_source run
plus one fresh root seven-module joint command: policy_financial,policy_values,
feature_repository,metric_features,metric_batch_guard,formal_sources,
formal_range_contract. Root verifies all ten path hashes against both runs and
includes exact full output/exit status in one acceptance record. This replaces
the earlier six/eight-module command proposals; no coverage is removed, only the
duplicate 33-case module is omitted from root rerun. Why: current run already
includes import orders/substitution/normal paths on final code. Cost if wrong:
cross-module ordering gap; root joint runs related consumers in one process and
any subsequent reviewed production changes invalidate affected prior evidence.

R2 actual full module has 31 methods (33 was worker's provisional count), last
reported 19/31 ok with process active and no failure. To reduce serial wait, root
captured ten final path hashes and began the seven-module joint command while
worker finishes that already-frozen module. Root session 76526; exact command
and pre-run hashes in wave2-joint-acceptance.md. R2 reviewer still pending; this
run is provisional until reviews and after hashes confirm stable accepted code.
Workers notified to preserve freeze or signal before any required change.
Root docs-only authority placement checkpoint: 76f2d0192154a87a3312c78ea66adb74b541c22e.

R2 fix1 complete full module GREEN: 31 /643.039s, exit 0, OK. Root read entire
appended fix report and the retained complete stdout/stderr, matched all six
file hashes to the running joint baseline, and independently ran external-fetch
mint regression GREEN 1/0.000s. Stage/diff check passed for exact whitelist (five
changed, fixture unchanged); EOL advisories recorded separately from test output.
Checkpoint deb02d287e03442002d6e6182e4a68e033c74e01: 5 code/test files,
467 insertions/216 deletions, no docs/data/progress. Original R2 reviewer resumed
scoped fix1 review, BASE 3864467..deb02d2, full U10 six-path package
task-R2-fix1-review-deb02d2.diff, 48,731 chars, untruncated. Four findings pending
verdict; joint session 76526 still progressing with no failure as of this entry.

Task R2: fix round 1/5 (4 addressed, 0 open; commits 3864467..deb02d2).
Original scoped reviewer returned all four addressed, no new breakage or outside
observations. Full substantive verdict retained as task-R2-fix1-review-deb02d2.md.
R2 and F2 review gates both clean. Joint run financial module all 34 cases GREEN;
values and legacy compatibility still running. No completion line until terminal
joint status and post-run ten-file hashes are verified.

Root joint terminal GREEN: 182 tests /1034.031s, exit 0, OK, no warnings/errors.
All ten after hashes exactly match before hashes and both implementer final hashes.
Together with full R2 31 /643.039s, accepted stable code covers 213 cases across
eight modules. Exact command/full output/hash baseline and acceptance retained in
wave2-joint-acceptance.md. Old failed F2 100-case run is NOT the acceptance claim;
this fresh complete root command supersedes that incomplete gate.
Task R2: complete (commits f4ed417..deb02d2, review clean).
Task F2: complete (commits f4ed417..1687440, review clean).
Stage B completion now 4/11 (R1,R2,F1,F2). R3/F3 next; no production operation.

F3 task specification synchronized with the existing F1/F3 preflight ruling:
five-path whitelist now explicitly includes closed event_record values and their
tests; GREEN adds policy_values. Actual four-field Context event identity retained,
no dynamic validator registration and no DTO proof authority. Master checklist
marks only R1,R2,F1,F2 complete, backed by ledger acceptance above.

Wave 3 dispatch BASE c7fb672bfe47d2831bb4c1e850d6397407b9464b (docs-only F3 scope
and acceptance checklist checkpoint). Final task-R3-brief.md and task-F3-brief.md
created from full draft task/spec sections with accepted real R2/F2 handoffs;
stale pending-handoff text removed. Drafts retained, not dispatched.
R3: /root/stage_b_r3_implementer, gpt-6-astra/high, exact six-file whitelist.
F3: /root/stage_b_f3_implementer, gpt-6-astra/high, exact five-file whitelist.
Model rationale: both require new sealed authority/receipt integration with
nontrivial failure and mutation boundaries, not mechanical transcription. Fresh
isolated workers; no subagents/Git/data/network; root reviews and stages only.
Disjoint implementations parallel by user-approved plan; source/StateStore test
setup changes announced through root and long verification uses stable hashes.
Task R3: implementation started. Task F3: implementation started. 4/11 accepted.

R3 initial prescribed RED: 3 tests /0.024s, 3 expected assertion failures
(missing range fixture, schema 6 rather than 7, absent V7 DDL), exit 1.
Worker additive V7 migration focused GREEN: 2 /0.523s. Source/authority not yet
implemented; no production DB opened. Worker announced source/schema edit phase.

Ruling: R3 RangeObservation authority may live beside source-owned request
authority, with exact type reexported by formal_range_store while persistence
implementation remains there. Genuine store type and private authenticated reread
paths must be eagerly paired/captured before usable factories; no caller callback,
public one-shot installer, lazy alias capture or exported mint. A fresh builder
invocation cannot create types accepted by the genuine closures. Worker must send
concrete initialization order before integration. Why: source continuations need
real receipt observations and restart needs real requests without circular trust.
Cost if wrong: initialization/lifetime complexity and import regression; enforce
same six-file boundary, fresh import orders and direct-forgery tests. Filesystem
root is storage path, not freely supplied manifest proof. Restart reloads signed
StateStore rows through genuine loaders/binding and verifies parent receipt chain;
wire fields or an ordinal alone cannot authorize a continuation request.

Ruling: R3 current-source ordering is conservative. If both source_updated fields
exist, compare authentic source updates and reject contrary publication movement;
if both absent, compare compatible publication observations. Asymmetric update
absence/incomparable precision cannot silently become a known order for differing
upstream/content. Equal leading source version with different content fails.
Never use capture time, insertion IDs, refresh or lexical upstream labels. Why:
these labels are opaque and capture does not prove upstream chronology. Cost if
wrong: fail-closed rejection of genuinely ordered but inadequately described data,
which requires a source-specific contract rather than a guessed tie-breaker.

Ruling: F3 may reuse an internal genuine FormalMetricContextRepository companion
and its captured _require_authentic_metric_context_repository solely as the
existing owned same-store/raw/verifier dependency guard. Root read constructor,
state and dependencies; constructor does not fetch universe/industry. Actual state
reads still use captured Context.get_verified_many, no alternate state factory or
additional universe requirement. Why: reuse the existing complete authenticity
checks without a copied guard. Cost if wrong: extra strict dependency coupling;
cover original alias/method/store boundaries, do not edit old metric code.

F3 acceptance gap confirmed by root: formal_policy_contract.parse_policy_rule
permits feature numeric, bool, enum, cyclic, market/calendar inputs, but no rule
accepts event_record despite the descriptor field type existing. A genuine signed
quantified-event selector therefore cannot reach state.select under current v1.
Root asked user asynchronously whether to preserve v1 and explicitly retain this
gap, or first add a new specification. No authority granted to alter policy
contract/registry or invent a rule. F3 proceeds with supported security/regulatory/
event flags and pure DTO checks; quantified-event acceptance remains unresolved.

R3 concrete initializer sequence approved: store module defines builder/helpers
before bottom importing source without dereferencing partial source. Source's
factory creates Source/Observation authority, imports the available store builder,
invokes once with private genuine anchors/mint, captures exact Store/private
rereads, then publishes exact classes into both modules and removes temporary
builder/mint names. Source-first/store-first subprocess tests and forged/cross-store
observation tests required. Persistence stays in formal_range_store; source owns
request/observation authority. No new file or caller installation route.

User decision received: "保持 v1，本轮记录缺口（建议）". F3 quantified-event
consumption is explicitly deferred, not a hidden pending result or implemented
capability. Keep existing v1 contract/registry unchanged; implement supported
security/regulatory/event bool/enum flags with genuine reads. Closed event DTO
tests remain pure format tests only. Replace impossible genuine-event selection
test with unchanged-contract rejection plus date/unit/numeric DTO boundary tests.
No unrequested descriptor read, fake signed selector, invented rule, activation
stub or manufactured pending rule. Future quantified event activation requires
separate versioned specification. F3 worker notified; scope no longer blocked.

Prepared requirements-only R4 and W1 drafts, not dispatched. R4 awaits accepted
R3 lease/receipt APIs. W1 draft explicitly flags original constructor-time lazy
calendar-validator wording against the now-established eager source authority,
and existing F1/W1 responsibility to add closed calendar/market PolicyValue
validators with values tests (future whitelist correction before dispatch).
Both drafts still require actual BASE/global excerpts/accepted handoffs.

Root early V7 preservation check: read-only AST (Assign and AnnAssign literals,
no StateStore import/DB) confirms all ten V2–V6 TABLE/INDEX constants have exactly
the baseline object counts and canonical hashes. Current declared schema is 7.
This is an early code check, not R3 migration acceptance; final tests/review and
frozen-code recheck still required. Initial AST probe saw nine because typed
_V4_INDEX_DDL uses AnnAssign; corrected probe covers all ten, no code defect.
Ruling: F3 internal lineage retains the complete selected Context Fact plus exact
signed descriptor/selector and read identity. This is a transitive authenticated
source/receipt reference, not an embedded OfficialSnapshotRef/receipt export or a
standalone proof. Root verified _normalization_input_hash binds full request,
manifest/content hashes and Fact; get_verified_many revalidates producer, receipt,
raw bytes and historical-calendar capability. Preserve that historical boundary,
no current-only snapshot reread or new API. Receipt/raw loss must revoke selection;
W3 must recheck actual dependencies, never grant authority to serialized lineage.

Ruling: R3 source continuation binds the genuine signed RangeBinding; destination
enqueue additionally requires parent observation's exact StateStore identity and
resolved snapshot root. Reopening the range repository on the same StateStore/root
is valid; cross-DB/root splices fail. Original StateStore module-completion closure
authority may be added within its existing whitelist to avoid first-import alias
substitution; preserve old DDL and verify subprocess substitution negative cases.

Ruling: R3 RangeObservation authenticates source observation/normalization/receipt
and current source version, not freeze visibility. Structurally valid date_only
non-null effective-time/hash fields remain source assertions until independently
proved, just as unresolved null pairs remain observations. Do not discard them
solely for absent proof, accept a hash alone, or import old single-day Context
bootstrap authority into the range path. W1 must authenticate the basis or return
visibility_unproven. This clarifies the older R2 report's overbroad R3 visibility
handoff; final temporal classification belongs to W1. Malformed structure fails.

Root docs checkpoint 8b8bd89319ec0c8f6b5ece627ad156990c21d903 contains only the
two lineage/visibility clarification lines in B1/B2 plans; no implementation,
data or progress files. R3/F3 task BASE remains c7fb672, not this docs checkpoint.

F3 frozen compatibility exposed a sequence-local copyreg cache mutation:
copy.copy on the slotted repository added __slotnames__, poisoning the full-class
identity guard. Isolated producer case passed, so not R3/lease regression.
Worker explicit copy/deepcopy rejection plus original-usability regression GREEN
2 /30.103s, exit 0. Earlier failed full run retained, not accepted; fresh final
run and frozen hashes still required. Root did not implement production fixes.

Ruling: R3 lease_next may augment its in-memory result with genuine request and
binding handles needed by R4 after restart. Persisted payload remains canonical
data, never these capabilities; no arbitrary restore/mint API. Authenticate the
execution request/current parent chain outside the short writer transaction,
reread/CAS exact candidate inside it, and revalidate again at fetch/persist.
Historical parent audit cannot grant execution. R4 must keep handles out of its
diagnostic wire response; store factory still captures exact parser authority.

F3 original failed compatibility session 58268 was gracefully interrupted only
after preserving emitted evidence; exit 1. Legacy historical-calendar revision
case passed before interruption, no demonstrated deadlock. Corrected frozen run
81809 began; its result is not accepted until terminal status/hash verification.

Root then reproduced an independent pre-import authority defect: after creating
a genuine runtime fixture, replacing formal_policy_registry.FormalPolicyRegistry
with a plain fake returning copied policy wire BEFORE importing policy_state
allowed select AND recheck (13 inputs). Isolated subprocess exit 0 /2.7803881s;
exact command/output in B2 task-F3-root-preimport-probe.md. Ordinary matching wire
cannot replace a signed registry seal. Implementer notified to add RED/fix;
current final run becomes diagnostic, not acceptance. Root did not fix product.
Fresh read-only /root/stage_b_f3_authority_audit (gpt-6-astra/high) investigates
minimal existing genuine authority path/required file scope and analogous DTO
capture issue while root records evidence and R3 continues independently. No
Git/production edits or additional agents allowed for that bounded audit.

Second root probe confirmed pre-import PolicyValue public alias can turn absent
factors into 12 present true bool values and survive recheck (session 84709,
exit 0); complete command/output in task-F3-root-preimport-value-probe.md. No
root production edits. Independent bounded audit confirmed both findings and
recommended original module-owned private reader/validator anchors consistent
with existing sources/range authority helpers, not a registry/runtime import pair.

F3 scope ruling: six files, original five plus formal_policy_registry.py ONLY for
an original closed proof_record/loads-based private authenticated reader. Original
PolicyValue parser/serializer/type/helper checks are established at values-module
initialization (already owned), consumed eagerly by state with explicit genuine
serialization. Public pre-import type/parser/serializer substitutions cannot mint
state evidence. Original private helper implementation remains the trusted runtime
boundary; no arbitrary interpreter/private-helper replacement defense claimed.
No signed v1 rule/contract changes, Context changes, callback registration, or
registry-to-runtime eager import pairing. Tests remain existing state/value files;
prescribed compatibility adds existing policy_registry module. Wave3 review input
whitelist updated; task BASE stays c7fb672. Worker proposal approved, implementation
and fresh GREEN pending. Task still 4/11 accepted overall.

F3 scope docs checkpoint 37b25ccea61f7d27e203775b7882a8de43f8f04e modifies only
B2 plan (four insertions/three deletions), no code/data/progress. Owner helper
implementation now has four focused fresh-process GREEN cases /10.430s, exit 0:
registry public alias, value public alias, original parser/serializer/lookup
replacement, and genuine state-first import. Six files refrozen; amended five-
module final compatibility started. Report/review/final exit still pending.

R3 cancelled obsolete focused sessions 30716/88794 with Ctrl-C, both exit 1 and
retained partial evidence only; current focused 10750 remains. Do not count old
partial successes as final acceptance. Root requested at most one active current
verification process per implementer lane, avoiding overlapping superseded runs.

Bounded read-only range performance audit by reused authority auditor found no
exponential/cyclic parent path: historical ancestry linear, current ancestry
quadratic with one version per request, and approximately eleven full signed
binding derivations per simple cached no-parent read. Static counts are not a
measured timing cause or throughput claim. Root forbids broad cache/graph rewrite
in R3; only adjacent duplicate load_binding current check may be collapsed if
captured source_binding already validates current authority and returns the exact
cached binding, with relevant mismatch/correction regression. All raw, receipt,
ancestor-current and post-callback checks remain. If not worth scope/test cost,
retain and report performance limitation. Auditor made no edits or test runs.

R3 current-candidate race ruling: exact candidate identity set is captured and
recompared after replay/parent checks (including empty-to-present); any concurrent
correction/status/payload/result change fails, not None/pending. Persist compares
prepared parent-candidate identity again under the short writer lock, with no
expensive parser/graph callback inside. Source continuation fetch also rechecks
parent-current after transport/parser callbacks before returning genuine fetch.
Real interleaving tests required. Fetch consumption must use original source-owned
registration checker and prevent original to_manifest from dispatching a replaced
_require; precheck alone is insufficient if the shadow can execute afterward.
No new public mint/API, historical evidence and all prior raw records preserved.

F3 review checkpoint d2cc791829b76aecf0b5a6d69e3290b603e96704 contains exact six
code/test files, 802 insertions/11 deletions, no docs/data/SQLite/progress. Root
read full report (including truncated-output continuation), checked diff --check,
verified six actual hashes match report, and confirmed 26 state +21 values tests
emitted OK in current amended suite. Full registry/Context terminal gate pending.
Full BASE c7fb672..d2cc791 scoped U10 package task-F3-review-d2cc791.diff retained,
56,876 chars, commit list/stat/full diff complete. Fresh independent reviewer
/root/stage_b_f3_reviewer (gpt-6-astra/high) dispatched read-only for spec+quality;
no redundant suites, no Git/subagents/edits. Private-helper trust boundary, v1 gap,
historical lineage clarification and pending compatibility explicitly supplied.
F3 remains review/verification pending, not complete; overall 4/11 accepted.

F3 independent review returned spec compliant and task quality Approved, no
Critical/Important/Minor issues. Full substantive verdict retained in B2
task-F3-review-d2cc791.md. Named outside-diff checks verified companion same-store
Context/raw/verifier/Fact serialization guard and stable Fact export; no tests,
Git or writes by reviewer. Final compatibility remains a separate pending gate.
Current amended suite 67219 passed 26 state +21 values +40 registry +10 schema
cases (97), then continued historical ContextRepository tests without failures
as last reported. Six code hashes unchanged; no final exit/count claimed yet.

F3 FINAL ACCEPTANCE: current amended session 67219 completed 144 tests in
621.686s, OK, exit 0 (26 state,21 values,40 registry,10 schema,47 repository).
Root read complete final output and counted 144 individual OK test lines, checked
terminal summary, independently compared all six SHA256s against checkpoint and
report, and confirmed zero working diff on the six files. Independent review at
d2cc791 is clean. Full output/command/timing/post-run confirmation retained in
task-F3-report.md; root hashes also retained in controller state. Earlier aborted
runs remain diagnostic only and are superseded by this complete stable GREEN.
Task F3: complete (commits c7fb672..d2cc791, review clean). 5/11 accepted.
User-approved unchanged-v1 quantified-event consumption gap stays explicit; pure
event DTO and existing bool/enum flags do not claim that missing capability.

F3 acceptance checkbox docs-only checkpoint 5c40dd86466cc706691ff65784fe88599591ae8f
changes one master-plan checkbox, no code/data/progress. All five accepted tasks
remain separate from active R3 and undispatched downstream work.

R3 proof handoff ruling: close public RangeObservation method/lookup/inheritance
shadowing within its original proof class. Source-owned module-init private
_range_observation_authority returns an immutable tuple of original observation
type/current verifier/wire reader for W1 eager capture, no mint or registration.
W1 must still obtain observations through its owned genuine Store and preserve
same-store/root requirements. Original private helper implementation is trusted,
not a new arbitrary-interpreter-tamper defense. Both import orders remain required.

R3 reported latest pre-race correctness focus GREEN 4 /659.443s; subsequent
four-case RED confirmed intended rejection gaps for forged-fetch checker, current
selection correction, and mid-fetch parent correction. Corresponding fixes were
applied only after each RED; last parent-persist RED still running on original
imported code. Single R3 process retained. No final R3 freeze/acceptance yet.
Worker separately confirmed ten legacy DDL AST hashes unchanged; root final
frozen-code DDL and combined compatibility checks remain required later.

R3 sealed-fetch consumption ruling: original source-owned authority captures the
registered manifest and immutable raw bytes once before callbacks. Store derives
all consumed identities from that sealed manifest/snapshot, uses the same bytes
for replay/hash/write/receipt, and never rereads mutable fetch slots afterward.
Original type and registration checks precede capture; manifest construction must
not dispatch mutable instance methods. A real parser-callback byte-mutation test
must prove either original valid detached bytes are committed or rejection occurs
before database commit, never an invalid verified row followed by read failure.
Source/config/parent final fences remain. No new public API or mint; six-file scope.

Recovery checkpoint: user reported apparent stall and requested continuation.
Live-agent inventory now contains root only; previous R3 worker is unavailable.
Get-Process -Name python returned no process; WMI process-command query was denied,
so no claim is made about the underlying application interruption cause. Existing
R3 report/code remain intact and report still says final verification pending.
Recovered R3 with /root/stage_b_r3_recovery under the SDD recovery procedure, same
six files and original BASE, no completed tasks redispatched. Preserve past RED
evidence; reconcile actual pending fixes before one frozen compatibility run.

R3 recovery reproduced callback mutation as post-commit typed integrity ERROR
(1 /65.253s), then explicit wrong committed hash RED (1 /46.809s). Sealed original
manifest/raw snapshot fix passed focused mutation+authority/import GREEN 4 /86.584s,
exit 0. Root read full report and independently matched all six frozen SHA256s;
ten legacy DDL AST constants match baseline. Required Store+Source+StateStore run
is sole session 54286, terminal outcome pending. Original completed sessions are
not still running and must not be polled or repeated.

R3 code-only review checkpoint e6c551d7e36819d38563511fd139ecdaa7a01e58 includes
six authorized code/test paths, 1494 additions/22 deletions; root B1 documentation
line remains unstaged. Full original BASE c7fb672..e6c551d six-file U10 review
package retained as task-R3-review-e6c551d.diff (114222 chars). Fresh read-only
/root/stage_b_r3_task_review dispatched for independent spec+quality review;
full terminal compatibility is an explicit separate gate. Overall remains 5/11.

R3 independent review at e6c551d: spec issues / Needs fixes, two Important findings:
renew/fail sample lease time before writer-lock acquisition; final child parent
fence checks task candidate rows but not parent receipt/snapshot/producer/raw changes
across child parser callbacks. Full report retained as task-R3-review-e6c551d.md.
Task R3: minor (deferred): explicit naked verified INSERT, multiple-producer and
canonical natural-key-conflict adversarial regression coverage remains incomplete;
carry to whole-branch review. Existing related tests do not cover those exact cases.
Task R3: fix round 1/5 starting (0 addressed, 2 open), FIX_BASE e6c551d.
Ruling: accept both Important findings and repair mutation-time fences within the
existing six-file scope — required expiry and dependency invariants are concrete,
not scope expansion — wrong fix would risk rejecting valid work or stale evidence,
so real lock-wait/callback regressions and scoped re-review are required.

R3 fix round 1 implementation: sole superseded full session 54286 stopped with
Ctrl-C exit 1, eight completed OK cases retained as partial diagnostic only.
New real SQLite lock-wait and parent raw callback regressions RED 2 /107.935s,
four intended assertions; minimal store fix GREEN 2 /108.098s, OK exit 0.
Read collects authenticated detached ancestor row/content identities; final writer
rechecks these without graph/parser callbacks. renew/fail time sampled after lock.
Root read full fix evidence and verified all six hashes; four unchanged files
retain prior hashes. Two-file checkpoint ca71683561c96dea1d1eb3f1e6e34624fb4e2284,
120 additions/21 deletions. Full e6c551d..ca71683 package task-R3-fix1-ca71683.diff
(24757 chars) dispatched to original reviewer for scoped re-review. No active
tests while awaiting this gate; full compatibility restarts only after clean
scoped review to avoid repeatedly testing versions known to need changes.

Task R3: fix round 1/5 (2 addressed, 0 open Important; e6c551d..ca71683), scoped
re-review clean with no new breakage. Full verdict retained in
task-R3-fix1-review-ca71683.md. Original Minor coverage note remains deferred.
Root instructed same recovery implementer to run the required complete compatibility
once on ca71683, preserve incremental output and verify frozen hashes afterward.
Task acceptance remains pending that terminal gate; overall still 5/11.

Full ca71683 run 18573 emitted 21 OK cases by elapsed 1068.8s, no failure yet.
Observed performance concern: parent raw mutation case took substantially longer
in the combined run than the earlier entire two-case focus (108.098s). Output is
buffered between polls, so exact individual duration is not known. Its actual OK
now establishes completion; CPU growth alone was only liveness/computation evidence,
not proof against an infinite loop. Cause of combined-run slowdown is unconfirmed;
no caching/proof weakening or performance rewrite authorized in this correctness
round. Preserve this observation for later performance assessment, separate from
the pending functional compatibility gate.

Full 18573 passed all 30 Store cases, then reported Source test
test_genuine_request_seal_rejects_every_out_of_contract_bound ERROR (page_index
subcase initially). Root/worker read-only inspection identifies new fetch_verified
request_record(request).previous before the original ValueError-to-
FormalTerminalSourceError boundary. This rejects tamper but breaks the existing
typed exception contract. Keep current full run frozen to collect complete trace
and all errors; no fix or extra suite started yet. Parent-evidence ValueError must
retain integrity semantics; later minimal request-only conversion should preserve
the valid execution and parent-check ordering.

## 2026-09-19 recovery of R3 terminal result

Session 18573 actually completed on the frozen ca71683 code: 272 tests in
3109.739s, FAILED (errors=5). Its complete terminal trace is already saved in
task-R3-report.md under Final compatibility after clean fix1 re-review. Root
independently counted 30 Store, 29 Source, and 211 StateStore passing test methods;
two Source methods produced the five errors. All five tracebacks are the same
request_record ValueError boundary defect, not five unrelated defects. A later
agent usage-limit failure interrupted the handoff. Current usage permits work.

Preserved external HEAD 8385ff6529cd27749fd9f4cc1a36cbd58dd397f3; its documentation
and tmpj4zv9_fq data changes are user-owned. The six R3 code/test files are
unchanged from ca71683, and the worktree/index were initially clean. Do not
revert, amend, delete, or include those data files in a new task commit.

Task R3: fix round 2/5 started, original recovery agent resumed. Fresh RED
20206: 2 test methods /14.954s, FAILED (errors=5), exit 1. Source-only narrow
exception conversion applied; sole GREEN session 52942 covers the whole Source
module plus the parent-correction-during-fetch regression. Report retains each
output chunk. No source scoring rule, production data, or dependency change.

Ruling: R4 may add a minimal source-owned read-only genuine request-to-binding
accessor, with R4 tests, expanding its whitelist from three to four files — its
opaque request and verified-page resume lack a binding for source_factory after
a cold restart, and crash-after-persist-before-enqueue must recover a successor.
The original request validator must stay captured in the source owner; expose
only authenticated binding access, not a mint or JSON authority reconstruction.
Preserve source_factory(binding) and reuse an existing authentic accessor if
available. Cost if wrong: one small interface amendment to revert/rework; no new
production permission or evidence qualification. R3 fix2 scope is unchanged.

R3 fix2 frozen checkpoint 3c3b3c12a6a5f8f6c98d054131e4a097cad710c4, only
formal_range_source.py (4 insertions/1 deletion). Root read all32 result lines,
terminal OK/exit0, fresh RED traceback, full working diff, and independently
checked all six file hashes; five unchanged and Source now
33c586bd62f48ebde290e1bdffc0bdfe31a196104b5f4192e0564a9389e740d0.
Index was empty before exact one-file staging/commit. No data/progress files
staged. Original reviewer resumed with complete scoped8385ff6..3c3b3c1 package
task-R3-fix2-3c3b3c1.diff. No active tests; acceptance awaits scoped verdict.

Task R3: fix round 2/5 (1 addressed, 0 open Important; 8385ff6..3c3b3c1).
Scoped re-review clean; complete verdict saved as task-R3-fix2-review-3c3b3c1.md.
Original Minor coverage remains deferred. The full272 result remains historically
FAILED; unchanged Store/StateStore evidence plus fresh32 covering GREEN and clean
fix review supports this task gate only. Final project verification remains later.
Task R3: complete (commits c7fb672..3c3b3c1, review clean).
Accepted tasks now6/11; R4 handoff follows from this code checkpoint.

Task R4: implementation dispatched to /root/stage_b_r4_implementer from
BASE3c3b3c12a6a5f8f6c98d054131e4a097cad710c4. Complete brief task-R4-brief.md
contains actual accepted API, four-file ownership amendment, error/retry scope,
exact-generation resume and crash-before-successor requirement, execution and
report contract. Master plan R3 checkbox is a controller-owned unstaged doc edit;
it must not be mixed into the four-file R4 code/test checkpoint. No other writers.

Ruling: R4 Source amendment also permits an explicit live-acquisition terminal
subtype of FormalTerminalSourceError — the existing base class combines remote
document failures with request/config/parent-replay integrity failures, so a
blanket worker catch would violate the closed failure categories. Emit the new
subtype only around live response validation/normalization, with original
source/request/binding/parent authority rechecked outside the wrapper on its
error path. Keep base replay/authentication failures propagating; worker records
only the distinct acquisition subtype as terminal_failed. Preserve successful
ordering and R3 error contract; no formal_sources.py change or exception-text
classification. Cost if wrong: small additional source-boundary rework, controlled
by remote max-pages vs parent replay regressions and independent task review.
Brief/report handoff includes this ruling; no extra production authority.

R4 initial RED:16 tests/18 expected missing-implementation assertions, exit1.
First implementation owns only the four approved paths. Root handoff check found
one concrete signed-budget risk: lease takeover increments attempts independently
of explicit retry failure, so repeated expiry might permit extra transport calls.
Worker added a dedicated regression: session91837,1test/121.459s, expected FAILED
because attempt3 became verified with retry_max_attempts2. First focused9061 is
being explicitly superseded as partial (2 completed OK, not acceptance), before
applying a minimal authenticated pre-send budget guard. Final allowed attempt
must remain available; expiry/crash cannot bypass the signed transport budget.
Fixture scheduling clocks may be controlled, but actual evidence verification
must not be bypassed to accelerate tests. See task-R4-report.md for live state.

R4 focused8215: both expiry-budget and final-permitted-attempt cases emitted OK;
parent callback classification case still running, not terminal acceptance.
Ruling: normalize only the new acquisition-terminal subtype back to the existing
base error inside shared registered parser/normalizer handling — saved replay
must never inherit live-only classification merely because a parser raises that
public subtype. Live fetch may deliberately wrap after authentic rechecks. Also
recheck original source/request after parent verification on the terminal path,
since parent replay callbacks may change them. Cost if wrong: localized error
boundary rework; focused negative tests and independent review are required.
No broad exception framework, original base-contract change or extra file scope.

R4 focused8215 terminal:3 tests/367.565s, FAILED(failures1), exit1; expiry2OK,
parent callback recheck RED. Separate snapshot-subtype RED13355:1test/18.912s,
FAILED, exit1. Minimal shared parser subtype normalization and post-parent
source/request rechecks applied only after both terminal outputs were saved.
Focused GREEN39023 covers subtype, callback and subprocess cold resume. The
prescribed4-module compatibility currently collects97 tests; collection is not
execution or acceptance. W1 draft records two remaining pre-dispatch API checks
(authentic Source access from Store; calendar-only worker budget selection when
market requests become active). No W1 work dispatched.

Ruling: after focused39023 GREEN and self-review, freeze the four R4 paths for
an independent code/spec review checkpoint before launching final97 — the earlier
long-suite restart cost shows review findings should be fixed before expensive
compatibility verification. Root may commit this explicitly provisional code
checkpoint with the focused evidence; it is not R4 acceptance, a full-suite pass
or a release. Any review fixes require focused verification, then final97 runs
once on the clean reviewed freeze. Cost if wrong: scoped test coverage misses a
defect until the mandatory compatibility gate, which must reopen the task. No
completion claim or production use occurs before both gates are resolved.

R4 static review bc1d137: spec issues, quality Needs fixes; one Important finding,
no Critical/Minor. Saved full verdict task-R4-review-bc1d137.md. Callback mutation
followed by transport timeout/typed retryable or blocked response can reach worker
retry handling without source/request/parent reauthentication. Root inspected
fetch_verified and shared _parse; finding agrees with the closed error contract.
Fix round1/5 resumes original implementer with exact finding, focused RED/GREEN,
then scoped re-review. Final97 remains unstarted, not an abandoned suite.
Fix1 RED32094 now running: three new methods cover source mutation plus timeout/
typed retry/blocked, original request mutation plus blocked/retryable response,
and genuine persisted parent corruption plus blocked response. No production
edits while RED is active. Full command/output live in task-R4-report.md/log.
RED32094 subsequently finished:3tests326.730s,7expectedfailures,exit1. Root read
complete output. Minimal Source-owner require_acquisition_authority helper now
checks source/request before and after current-parent replay on generic/typed
transport errors and classified retryable/blocked responses, shared with the
existing terminal path. GREEN83795 is the sole active test run: new3 plus normal
timeout limit, blocked cooldown and prior post-parent callback regression. No
extra files or production use; independent fix re-review follows terminal GREEN.
GREEN83795 subsequently finished:6tests868.661s,OK,exit0. Root read complete output,
matched four file hashes, verified empty index/whitespace check0 and staged only
Source+worker-test paths. Fix checkpoint ba0def62a4ffe45cb5e3bee41537ea1b79ff6de0;
full scoped bc1d137..ba0def6 package task-R4-fix1-ba0def6.diff. Independent reviewer
/root/stage_b_r4_fix1_review dispatched. Master plan remains unstaged, no data
included. Original implementer remains the owner for final100 after clean review.

Runtime diagnostic31853 TERMINAL exit0, no active test competition: only in-memory
RangeSourceFixture construction plus one first_calendar_request, no fetch/worker/
DB/network. cProfile recorded76,092,272calls (74,623,706primitive),40.825s profile,
41.591s wall/36.141s process CPU. Feature registry parser called422times, scoring
require_official25times (37.340s cumulative), _derive_graph7times (33.912s).
This directly supports repeated authenticity/feature-graph parsing as the dominant
cost for this bounded operation, not proof of all pipeline/runtime behavior.
Profiler adds overhead; no performance rewrite/cache/proof weakening performed.
Full output preserved in task-R4-tiny-profile.log and diagnostic note updated.
Cannot-verify items: four-file checkpoint has no policy/data changes; root exact
staging whitelist and Git diff establish task scope. Historical user-owned data
commit remains untouched. Whole-branch compatibility and real lease throughput
remain later gates/explicit limitations, not inferred from focused test clocks.

Ruling: W1 final file ownership expands from the original five to thirteen exact
code/test paths as listed in task-W1-draft-brief.md — audited predecessor APIs
do not yet expose Store-owned planning identity, market-specific sealed Source
configuration/Worker budgets, or the closed F1 value validators. The original
five-file plan cannot implement those integration obligations safely. Add a
separate binding-owner planning reader (preserve legacy five anchors); resolve
planning roots/roles through owning Store, comparing semantic identities while
retaining exact factory binding identity; eagerly seal both Source configurations
and select by genuine request; update Worker budgets and original value validators.
Cost if wrong: additional focused integration rework in these bounded modules;
independent W1 review and expanded final compatibility must catch it. No registry
registration escape, production source/signing, schema rewrite or extra feature.
The read-only audit and root checked interface locations are saved in
task-W1-interface-audit.md. W1 remains undispatched pending R4 acceptance.

Ruling: clarify spec5.2's frozen-universe source of security IDs as section2/W3
orchestration responsibility — prescribed Source request schema/API has no
universe capability, while the sole W3 batch entry authentically reloads and
enumerates it. Root verified design28–45 and existing Context load/recheck APIs.
Source acquisition authority is not membership authority; W3 and pre-batch
orchestration must use genuine canonical Universe members, reject nonmember
range selections and recheck all identities before publication. No hidden proof
from calendar/ID strings or extra W1 argument. Cost if this interpretation is
wrong: request-level membership would require explicit versioned API/schema
revision; current formal batch still must reject all nonmembers. W3 regression
obligations saved in task-W1-interface-audit.md and must be carried to its brief.

R4 focused39023 TERMINAL:3 tests/1100.321s, FAILED(failures1), exit1. Snapshot
subtype and actual subprocess cold-resume tests passed. Parent callback raised
the intended hard error; its subsequent SQL result assertion failed solely on
tied-created_at ordering (leased/verified reversed), not missing rejection.
Three paginated tests now order explicitly by page_index; no production edit.
Fail-fast77497 rechecks those three affected cases (callback, base parent replay,
missing-page retention). Cold-resume pass is retained, not rerun at this checkpoint.
Full97 still awaits clean static review. Record substantial observed runtime
(this focused3 took18.3min) as a separate performance concern; cause not profiled
and no performance rewrite/proof weakening has been performed.

R4 focused77497 TERMINAL: 3 tests/521.178s, OK, exit0. Root read the full saved
output and matched all four report hashes to disk; whitespace check exit0 and
index empty. Exact four code/test paths committed as provisional review checkpoint
bc1d137d5eb40b1b56538ab3da905e6ad96fd368. Master plan checkbox remains unstaged;
no data, database, progress or historical artifacts were committed. Complete
BASE3c3b3c1..bc1d137 review package saved as task-R4-review-bc1d137.diff.
Independent reviewer /root/stage_b_r4_task_review dispatched with brief, report,
full package and global constraints. No tests active; mandatory final97 awaits
clean review. This checkpoint is NOT R4 acceptance or complete-suite GREEN.

Task R4: fix round1/5 (1 addressed,0open; bc1d137..ba0def6). Independent scoped
re-review clean; full verdict task-R4-fix1-review-ba0def6.md. No new breakage or
Minor findings. Original worker resumes now for final100 same-process four-module
compatibility, with code frozen. No default60s lease/production throughput or
Stage B completion claim; runtime diagnostic separately preserved.

Final100 launched once by original implementer, session73320, PID35328 (launcher
34740), start2026-09-19T14:09:08+04:00. Exact four-module command in R4 report;
incremental task-R4-compatibility.log. First5OK; incomplete until terminal counts
and exit code. All code/tests frozen, root only maintains ignored task artifacts.

User decision: prioritize repeated-validation performance optimization after the
current100-case run, before W1. Main read brainstorming/TDD guidance and classified
it bounded to existing feature registry flow, no public API/schema redesign.
Short in-chat design presented for explicit approval: retain owner-private parsed
results from authenticated bytes, recheck current object/fields/bytes/hash each
read, never memoize current validity, return detached slot values, protect existing
tamper/forgery/cross-root/clone behavior and benchmark the same bounded operation.
Only formal_feature_contract.py and its tests envisioned; no implementation yet.
Writing-plans skill inspected but no formal plan created for this bounded path.

User then explicitly approved the exact bounded design. P1 may implement only
after R4 final100 acceptance; prepare task-P1-brief.md now, no code or competing
tests. Original runtime diagnostician performs a bounded read-only cache/return
isolation check while root prepares requirements. Preserve current fingerprint,
signature/root provenance and hash checks; no current-validity or global hash-only
proof cache. Complete original11-task Stage B plan resumes with W1 after P1.

## 2026-09-24 W3 recovery

Current branch/remote HEAD is clean at 18c45b31caf4f968de99d9513ed22c67cfffa08d.
W1 and W2 are accepted in the master plan. Commit 18c45b3 is a user-pushed W3
intermediate checkpoint, not acceptance: seven W3 files are present, the initial
18-test RED is preserved, and the report records a genuine nested metric-guard
deadlock/interface gap plus three queued self-review regressions. No Python test
process remained. Resume W3 from this checkpoint with a recovery implementer;
do not redo W1/W2 or claim W3 complete until focused GREEN, the four-module
compatibility gate, and independent review are clean.

W3 recovery implementation completed on top of 18c45b3. TDD evidence: exact-
owner nested guard RED (database locked) then GREEN 1/1; three self-review
regressions RED with five expected failures then GREEN 3/3. Narrow metric guard
16/16, genuine populated W3 1/1, required focused W3 26/26, and four-module
compatibility 60/60 all passed. Only five approved tracked paths changed; exact
files committed by controller as 36f12b295715e3969b72d542f72f3d4208f7bd9e.
No data/progress artifact was staged and no push was performed. Full scoped
2c021fc..36f12b2 review package saved as task-W3-review-36f12b2.diff; fresh
independent reviewer /root/stage_b_w3_reviewer dispatched. W3 remains pending
review acceptance.

W3 independent review at 36f12b2 is clean: spec compliant, task quality
Approved, zero Critical/Important/Minor findings. Root verified the full verdict,
clean tracked status and exact local commit. W3 is accepted (10/11 original plan
tasks); master/B3 plan checkboxes updated. Next task is W4 combined acceptance
and code/test scope audit. No production evidence or final score/pool was run.

Task W4 prepared from clean BASE fd648b97125c7d381347605b820b6099ba39c4e4.
Brief task-W4-brief.md limits initial ownership to the new integration module and
test-only runtime fixture, requires five-template/unknown/noncyclic/veto+pending
enumeration, deterministic rebuild plus append-only correction, and real worker
restart without duplicate transport. Any production defect requires a preserved
RED and controller-approved scope expansion. The final 26-module affected suite
must run once on frozen code, with no production crawl/scoring/pools.

W4 complete. Calendar collision root-cause audit found the Store/V7 contract was
correct and fixture scheduling was redundantly reproducing an exchange-shared
calendar; no production/DDL expansion was made. Integration3/3 GREEN in5353.997s.
The plan's exact command contains25 modules (not shorthand26):791 tests passed in
26771.845s,0 failures,0 errors,1 expected Windows symlink privilege skip,exit0.
Initial review found1 Important+1 Minor test gap; fix1 commit bba7e0f compares
full historical snapshot/task/receipt/fact rows and strict-resolves actual raw/
manifest paths under each temporary root. Re-review Approved with zero findings.
Root fresh final verification on bba7e0f ran the two affected tests together:
2 tests/804.601s,OK,exit0. W4 accepted; all11/11 Stage B tasks are checked.
Known non-blocking boundary remains recorded: FormalRangeWorker.resume does not
coordinate concurrent cross-binding enqueue of the same calendar natural key;
the tested supported path replans/reuses verified evidence sequentially. Stage B
still makes no production crawl, scores, levels, eligibility or pools.
