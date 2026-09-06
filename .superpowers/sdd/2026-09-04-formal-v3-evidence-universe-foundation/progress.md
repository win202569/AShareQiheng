# SDD ledger — plan: docs/superpowers/plans/2026-09-04-formal-v3-evidence-universe-foundation.md

Task 4A: dispatched — isolated V5 schema migration and literal V4 fixture; implementation agent `/root/v5_task4a_implementer`.

Task 4B: read-only contract preflight complete — separate formal state machine/API, canonical idempotency, dependency/lease fencing, and supersession edge-test checklist captured from `/root/v5_task4b_contract_analyst`; resolve the `scope`/`before_generation` interpretation explicitly before implementation.

Task 4C: read-only contract preflight complete — formal raw snapshot writers must call a narrow `FormalSnapshotStore` validation helper; immutable receipt, manifest/path integrity, generation/lease fencing, and source-task completion gates captured from `/root/v5_task4c_contract_analyst`.

Task 4A: implementation submitted — `438900f` (`feat: add formal v5 schema migration`); focused migration 9/9 and legacy StateStore 108/108 pass; fresh independent review dispatched against `3152ad8..438900f`.

Task 4A: complete — `438900f`, independent review PASS with no Critical/Important findings. Deferred minor coverage observation: focused migration assertions cover the required four-table subset, while DDL inspection confirmed all eight V5 tables/FKs/indexes; retain a whole-branch migration coverage audit for final closeout.

Task 4B: dispatched — formal collection-task queue implementation assigned to `/root/v5_task4b_implementer` from `438900f`; binding brief is `task-4b-brief.md` and includes the recorded explicit supersession scope/generation ruling.

Task 4D: read-only contract preflight complete — typed frozen-universe persistence, three-source receipt/task lineage revalidation, immutable replay, finalizer gate, and full status-ledger coverage checklist captured from `/root/v5_task4d_contract_analyst`. Before dispatch, freeze the initial pending reason/evidence-hash formula explicitly.

Task 4D: initial-status ruling frozen for D1/D2 — initial every-member ledger is `pending_evidence`, `reasons=("formal_collection_pending",)`, `veto_flags=()`, and `evidence_hash=SHA256` of canonical UTF-8 sorted/compact JSON `{frozen_input_hash, security_id, status, reasons, veto_flags}`. This makes initial status evidence deterministic rather than placeholder data.

Task 4B: original whole-slice implementation agent was safely interrupted after no persisted diff or stage report; no code was lost. Repartitioned serially as 4B1 enqueue/dependency foundation, then later lease/transitions and supersession, each with its own review gate.

Task 4B1: dispatched to `/root/v5_task4b1_implementer` from `438900f`; strict brief `task-4b1-brief.md`.

Task 4B1: implementation submitted — `34cff9b` (`feat: add formal task enqueue semantics`); RED observed for absent formal-state contract, focused formal tests 10/10 and full StateStore 118/118 pass. Fresh independent review dispatched against `438900f..34cff9b`.

Task 4B1: complete — `34cff9b`, independent review PASS with no Critical/Important findings; reviewer independently reran formal-task tests 10/10. Formal/legacy isolation, canonical idempotency/rollback, tamper fail-closed reads, and leased-child protection were explicitly verified.

Task 4B2: dispatched — formal lease/renew/fail fencing assigned to `/root/v5_task4b2_implementer` from reviewed `34cff9b`; strict brief `task-4b2-brief.md` deliberately defers completion/supersession/receipt work.

Task 4B2: adversarial preflight found a terminal-parent/expired-child stranded-state ambiguity. Ruling in `task-4b2-addendum.md`: only live leases are protected; an expired leased child may be terminal-failed by dependency resolution within a writer transaction. Also record fixed-schema worker-id limitation: V6 callers must use unique worker IDs per lease incarnation because no lease token exists; do not claim same-ID ABA fencing.

Task 4B2: implementation submitted — `f60705c` (`feat: add formal task lease fencing`); RED observed for missing lease/renew/fail APIs and expired-child resolution, focused lease 7/7 + integrated 13/13 + CAS hardening 2/2 pass, full StateStore 131/131 pass, `py_compile` and diff check pass. Fresh independent review dispatched against `34cff9b..f60705c`.

Task 4B2: first review dispatch was safely interrupted before initialization after two bounded no-response windows; no review work or code was lost. Fresh focused rereview dispatched to `/root/v5_task4b2_rereviewer` against the same immutable range.

Task 4B2: complete — `f60705c`, focused independent rereview PASS with no Critical/Important findings. Rereview manually confirmed transactional time sampling, candidate/CAS parity, payload rollback, deterministic boundaries, takeover fencing, expired-child terminalization, legacy isolation, and correctly documented same-worker ABA limitation.

Task 4C1: dispatched — strict raw-snapshot manifest/path validation helper assigned to `/root/v5_task4c1_implementer` from reviewed `f60705c`; scope is only `formal_snapshot_store.py` and its focused tests per `task-4c1-brief.md`.

Task 4C2: read-only persistence preflight complete — inject an optional configured `FormalSnapshotStore` into `StateStore` rather than infer any raw root from paths/DB; legacy construction remains compatible while formal snapshot APIs fail closed when unconfigured. Bootstrap writer/getter must persist/revalidate a 4C1 canonical projection, use manifest-first immutable lineage conflicts, and never touch legacy `source_snapshot`.

Task 4C1: implementation submitted — `b4fc8ff` (`feat: validate formal raw snapshot receipts`); RED covered missing helper and noncanonical effective-evidence hash, focused suite 28 pass with 3 Windows symlink-privilege skips, `py_compile`/diff check pass. Fresh independent security review dispatched against `f60705c..b4fc8ff`.

Task 4C1: independent review found Important defects — self-consistent caller-forged `EvidenceVerification` could be accepted, and nested request/parser/mapping fields were not strict type/shape validated. Original implementer must add RED regressions and make a scoped fix; do not start 4C2 implementation.

Task 4C1: fix submitted — `4b77b24` (`fix: harden formal snapshot validation`); RED 2 tests / 12 adversarial subcases, focused suite 31 pass with 3 Windows symlink-privilege skips, `py_compile`/diff check pass. Fresh independent fix rereview dispatched against `b4fc8ff..4b77b24`.

Task 4C1: fix rereview found one remaining Important date-only trust bypass: `_structural_calendar_binding` fabricated a `VerifiedCalendarBinding` from fetch-controlled fields. Ruling: remove this construction; a date-only fetch must obtain its binding from an explicitly injected, trusted context resolver and fail closed when unavailable. Revalidate/write paths must use the same resolver result; arbitrary hash/text can never substitute for a binding.

Task 4C1: second fix submitted — `206afd5` (`fix: require trusted calendar binding`); RED 5 focused tests, focused suite 36 pass with 3 Windows symlink-privilege skips, `py_compile`/diff check pass. Fresh final independent security rereview dispatched against `4b77b24..206afd5`.

Task 4C1: complete — commits `b4fc8ff`, `4b77b24`, `206afd5`; final independent review PASS with no Critical/Important findings and independently reran 36 passing tests (3 expected Windows symlink-privilege skips). Raw snapshot validation now requires trusted injected calendar resolution for date-only evidence and retains forged-verification/nested-field defenses.

Task 4C2: dispatched — optional injected raw store plus immutable bootstrap formal snapshot persistence/getters assigned to `/root/v5_task4c2_implementer` from reviewed `206afd5`; strict brief `task-4c2-brief.md`, no receipt writer/completion work in this slice.

Task 4C2: implementation submitted — `c368ff1` (`feat: persist formal bootstrap snapshots`); RED 9 missing-feature tests, focused 9/9 and full StateStore 140/140 pass, `py_compile`/diff check pass. Fresh independent review dispatched against `206afd5..c368ff1`.

Task 4C2: independent review found Important tamper-fail-open defect — missing receipt row could return `None` despite task-produced formal snapshot(s), and existing receipt did not require exactly one matching producer snapshot. Original implementer must add orphan/extra-producer regressions and scoped fix; do not start 4C3 implementation.

Task 4C2: fix submitted — `8aa169a` (`fix: harden formal receipt lineage`); RED orphan/extra-producer regressions 2/2, focused 5/5 and full StateStore 142/142 pass, `py_compile`/diff check pass. Fresh independent fix rereview dispatched against `c368ff1..8aa169a`.

Task 4C2: fix rereview found Important consistency defect — receipt lineage getter used separate autocommit reads and could return a fractured, never-committed-valid graph under concurrent deletion. Ruling: read the complete receipt/producer/task/snapshot graph in one explicit SQLite read transaction/snapshot before validation; add interleaving regression. Do not start 4C3 implementation.

Task 4C2: second fix submitted — `5518c28` (`fix: make formal receipt reads consistent`); deterministic fractured-read RED 1/1, focused 6/6 and full StateStore 143/143 pass, `py_compile`/diff check pass. Fresh final independent rereview dispatched against `8aa169a..5518c28`.

Task 4C2: complete — commits `c368ff1`, `8aa169a`, `5518c28`; final independent review PASS with no Critical/Important findings. Bootstrap lineage reads now fail closed for orphan/multiple producer graphs and validate their complete graph in one explicit consistent SQLite snapshot; reviewer independently ran focused 6/6 and full StateStore 143/143.

Task 4C3: dispatched — active-lease source snapshot/receipt writer assigned to `/root/v5_task4c3_implementer` from reviewed `5518c28`; strict brief `task-4c3-brief.md` defers formal task completion/supersession/universe work.

Task 4C3: implementation submitted — `d4ce87a` (`feat: persist formal task snapshot receipts`); focused writer 6/6, formal snapshot 9/9, receipt integrity 5/5, full StateStore 148/148 pass, `py_compile`/diff check pass. Fresh independent review dispatched against `5518c28..d4ce87a`.

Task 4C3: complete — `d4ce87a`, independent review PASS with no Critical/Important findings. Reviewer confirmed trusted projection, in-transaction source/owner/expiry/generation fences, immutable conflicts, atomic snapshot+receipt rollback, preserved receipts, C2 consistent reads, and independently reran full StateStore 148/148.

Task 4B3: dispatched — formal completion and scoped generation supersession assigned to `/root/v5_task4b3_implementer` from reviewed `d4ce87a`; strict brief `task-4b3-brief.md` intentionally fails universe-finalizer completion closed until Task 4D provides matching-universe proof.

Task 4B3: implementation submitted — `f2a5199` (`feat: complete formal tasks safely`); initial RED 9 tests / 24 expected absent-API errors, focused 10/10 and full StateStore 158/158 pass, plus dedicated receipt-validation-to-expiry RED/GREEN proving final CAS resamples time. Fresh independent review dispatched against `d4ce87a..f2a5199`.

Task 4B3: complete — `f2a5199`, independent review PASS with no Critical/Important findings; reviewer independently ran StateStore 158/158. Completion uses a receipt gate and last-moment lease CAS; supersession exact-matches canonical scope, preserves audit history, and fences old leases. Universe finalizer remains deliberately fail-closed until D2.
Task 4D1: dispatched — immutable typed frozen-universe graph persistence assigned to `/root/v5_task4d1_implementer` from approved `f2a5199`; strict brief `task-4d1-brief.md`, with D2 status replacement/finalizer intentionally deferred.
Task 4D1: implementation submitted — `5e6dc8a` (`feat: persist formal universe graph`); author observed RED for 21 missing-API paths, then focused 18/18 and full StateStore 166/166 passing. Fresh independent review is required against `f2a5199..5e6dc8a`.
Task 4D1: review package `review-f2a5199..5e6dc8a.diff` generated; fresh independent reviewer `/root/v5_task4d1_reviewer` dispatched.
Task 4D1: independent review FAIL — two Important fail-closed defects: initial `pending_evidence` rows accepted substituted valid-shape evidence hashes without recomputation, and a source task marked `verified` could retain impossible error/lease/retry fields while satisfying universe lineage. Original implementer must add RED regressions and repair both before a fresh rereview.
Task 4D1: fix round 1/5 submitted — `bc34b67` (`fix: harden formal universe integrity`) adds 3 RED methods / 10 failure paths, exact initial-tuple hash recomputation, and strict verified-source-task lifecycle invariants. Author reports focused formal-universe 11/11 and full StateStore 169/169; fresh independent rereview required.
Task 4D1: fix review package `review-5e6dc8a..bc34b67.diff` generated; fresh independent rereviewer `/root/v5_task4d1_fix_rereviewer` dispatched.
Task 4D1: complete — commits `5e6dc8a`, `bc34b67`; final fresh rereview PASS with no Critical/Important/Minor findings. Independently verified focused universe 11/11 and StateStore 169/169, initial-status canonical hash revalidation, verified-task lifecycle invariants, persisted graph replay/getter fences, and future non-initial D2-style status compatibility.
Task 4D2: contract frozen in `task-4d2-brief.md` — a complete typed status replacement is atomically validated/re-read; later-stage evidence hashes stay structural in V5 except for the binding D1 initial tuple. The V6-defined finalizer payload is made an exact V5 StateStore boundary: BJ/SH/SZ source task IDs, immutable dependency edges, header/result/root hashes, full ledger, and final lease CAS must all agree.
Task 4D2: dispatched — typed status ledger and exact finalizer proof assigned to `/root/v5_task4d2_implementer` from reviewed `bc34b67`; strict brief `task-4d2-brief.md`.
Task 4D2: first implementation dispatch safely interrupted after repeated bounded waits produced no checkpoint and no persisted diff; `git status` stayed clean, so no code was lost. Re-dispatch to a fresh implementer is required.
Task 4D2: replacement implementation submitted — `99b0681` (`feat: complete formal universe lifecycle`); author observed RED for absent status-list API, then focused formal-universe 18/18 and full StateStore 176/176 passing (the latter completed normally but slowly in 478s). Fresh independent review required against `bc34b67..99b0681`.
Task 4D2: review package `review-bc34b67..99b0681.diff` generated; fresh independent reviewer `/root/v5_task4d2_reviewer` dispatched.
Task 4D2: independent review FAIL — 0 Critical, 1 Important, 1 Minor. The shared status-graph reader accepts mixed or pre-creation canonical `updated_at` values, letting a tampered ledger pass finalizer proof; it must require one ledger timestamp not earlier than the universe creation time. Whitespace-only reason/veto values are also accepted. Original author must add RED regressions, repair both, and obtain a fresh independent rereview.
Task 4D2: fix round 1 submitted — `988765d` (`fix: harden formal universe status ledger`), scoped to `state_store.py` and its tests. Author added RED proof for eight mixed/pre-header timestamp and blank-token failure paths, then GREEN shared-ledger timestamp and nonblank-token checks; focused formal-universe 21/21 and full StateStore 179/179 passed, with compile/diff checks clean. Fresh independent rereview required against `99b0681..988765d`.
Task 4D2: fix review package `review-99b0681..988765d.diff` generated; fresh independent rereviewer pending dispatch.
Task 4D2: fix round 1 independent rereview FAIL — 0 Critical, 1 Important. The shared timestamp repair is sound (including tail-trigger rollback), but status reason/veto validation rejects only all-whitespace values and still persists padded tokens, contrary to the frozen canonical trimmed/nonblank contract. Add input and persisted-tamper RED regressions that reject `token != token.strip()` for both fields, repair in the same scoped validator, then fresh rereview.
Task 4D2: fix round 2 submitted — `8988719` (`fix: canonicalize formal status tokens`), scoped to `state_store.py` and its tests. Author added ten RED padded-token failure paths and made the shared status validator require nonempty already-trimmed reason/veto strings without silent normalization; focused formal-universe 24/24 and full StateStore 182/182 passed, with compile/diff checks clean.
Task 4D2: complete — commits `99b0681`, `988765d`, `8988719`; final fresh independent rereview PASS with no Critical/Important/Minor findings. Reviewer independently verified shared full-graph timestamp and canonical-token enforcement across listing, replace precheck/tail rollback, finalizer proof/completion, and verified getter; focused formal-universe 24/24 (405.825s), full StateStore 182/182 (794.906s), compile, and diff checks all passed. No data, SQLite, WAL/SHM, or progress artifact was committed.
Task 5: contract preflight complete — `task-5-brief.md` freezes a separate formal-only repository, configured raw-store reuse, exact request/manifest/receipt lineage validation, point-in-time selection, raw-read ref equality, no direct repository SQL, and legacy isolation. Dispatch may begin only after the D2 completion gate, which is now satisfied.
Task 5: implementation submitted — `fcdaefb` (`feat: persist verified formal snapshots`), scoped to `formal_snapshot_repository.py`, narrow formal lookup support in `state_store.py`, and repository tests. Author observed RED for absent module, then 16 focused repository tests and StateStore 182/182 passing; compile/diff checks clean. A duplicated long-output test launch caused temporary local CPU contention but all redundant processes exited naturally; the controlled StateStore run passed 182/182 in 1085.203s. Fresh independent review required against `8988719..fcdaefb`.
Task 5: review package `review-8988719..fcdaefb.diff` generated; fresh independent reviewer pending dispatch.
Task 5: independent review FAIL — 0 Critical, 1 Important. Exact/visible candidate discovery SQL-prefilters on mutable stored `request_fingerprint`, so a tampered newer matching row is invisibly skipped and lookup can fall back to an older snapshot. Candidate discovery must cover/revalidate all formal rows before canonical identity filtering; add exact/visible fingerprint-tamper RED regressions and fresh rereview after repair. Reviewer otherwise found raw-store reuse, lease/receipt graph, PIT ordering, manifest tie-break, immutable raw reads, and legacy isolation sound; independent combined suite 234/234 (3 skipped) passed in 935.805s.
Task 5: fix round 1 submitted — `cc4227e` (`fix: fail closed on formal snapshot identity tampering`), scoped to state-store helper and repository tests. Author added exact/visible fingerprint-tamper RED proof, then made candidate lookup scan/revalidate all formal rows before reconstructed identity filtering; targeted 2/2, repository 18/18, and a single StateStore session 182/182 (620.878s) passed with compile/diff checks clean. Fresh independent rereview required against `fcdaefb..cc4227e`.
Task 5: fix review package `review-fcdaefb..cc4227e.diff` generated; fresh independent rereviewer pending dispatch.
Task 5: complete — commits `fcdaefb`, `cc4227e`; final fresh independent rereview PASS with no Critical/Important/Minor findings. The repository now reuses the configured raw-store/resolver, validates row→manifest/raw→receipt/task lineage in one read transaction, preserves PIT ordering/ref immutability/legacy isolation, and scans/revalidates all formal rows before exact/visible identity selection so fingerprint tampering fails closed. Reviewer independently verified targeted 2/2, repository 18/18, StateStore 182/182 (782.508s), compile, and diff checks. No data, SQLite, WAL/SHM, or progress artifact was committed.
V5 evidence/universe foundation: complete — Tasks 1–5 have passed their scoped implementation and fresh-review gates. The next dependency is the V6 financial feature/collection pipeline; preserve formal-only domain isolation and do not begin scoring/pool release work until its prerequisites are reviewed.

## Session setup

- Worktree: `D:/Projects/AShareQiheng/.worktrees/formal-v3-implementation`
- Branch: `codex/formal-v3-implementation`
- Base commit: `5117a6d` (`docs: add formal V3 implementation plans`)
- Binding spec: `docs/superpowers/specs/2026-09-04-formal-scoring-release-contract-design.md`
- Baseline: `D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest discover -s tests -q` passed on the unmodified worktree.

## Task checklist

- [ ] Task 1 — Official Evidence Contract and Source Policy
- [ ] Task 2 — Byte-Preserving Formal Snapshot Store
- [ ] Task 3 — Formal Time and Full-Universe Pure Contract
- [ ] Task 4 — Additive SQLite V5 Formal Evidence and Universe Tables
- [ ] Task 5 — Verified Formal Snapshot Repository

## Preflight interface and consistency scan

| Producing task / plan | Consuming task / plan | Contract checked | Finding / ruling |
| --- | --- | --- | --- |
| V5 Task 1 | V5 Tasks 2, 3, 4, 5 | `OfficialFetch`, `EvidenceVerification`, `OfficialSnapshotRef`, `VerifiedCalendarBinding` | No type cycle: Task 1 owns immutable types; later tasks consume them. |
| V5 Task 1 → Task 2 | V5 Task 5 | `FormalStoredSnapshot` plus verified manifest lineage | No conflict: raw bytes are written before the StateStore returns a row-derived `OfficialSnapshotRef`. |
| V5 Task 3 | V5 Task 4 | `FormalFrozenUniverseInput` and three exchange-scoped source extractions | No conflict: Task 3 is pure ingress; Task 4 is the sole persistence owner. |
| V5 Tasks 1–3 | V5 Task 4 | verified source snapshot / task-receipt lineage | Ruling: V5 Task 4 tests will build typed test snapshots and receipts through the new V5 writer, never fabricate a bare universe input that bypasses provenance. This preserves the formal lineage contract; the cost if wrong is more fixture setup, not weaker evidence checks. |
| V5 Task 3 sample code | V5 Task 1 identity contract / binding spec | security-ID regex | Ruling: use ASCII `[0-9]{6}`, not Python `\d{6}`. The sample conflicts with the fixed formal identity boundary; the cost if wrong is changing a plan-derived test fixture, versus permitting noncanonical A-share IDs. |
| V5 Task 3 sample test | V3 §3.1 / V6 calendar resolver | date-only effective time | Ruling: `resolve_effective_at` requires a caller-provided, verified next-exchange-close value for `date_only`; tests inject it. It must not guess a weekday/session merely because the abbreviated sample omits that argument. The cost if wrong is a slightly expanded pure-function signature, versus a forward-looking calendar assumption. |
| V5 Task 3 | V5 Task 4 | `FormalFrozenUniverseInput.frozen_input_hash` | Ruling: Task 3's formula (freeze, registry manifest, universe hash, and each source manifest/extraction hash) is authoritative. Task 4 independently validates members → universe hash and then recomputes precisely that formula. The cost if wrong is adapting a Task 4 test helper, versus rejecting a valid typed frozen input. |
| V5 Task 2 | V5 Task 4 | “signed manifest” wording | Ruling: V5 means the Task 2 canonical, hash-verified immutable manifest; no invented cryptographic signing scheme is added. StateStore must revalidate the exact manifest bytes, hashes, paths, fetch, verification, and task linkage through a safe raw-store helper rather than trusting `FormalStoredSnapshot`. The cost if wrong is adding a narrow raw-store API, versus treating caller-provided paths as evidence. |
| V5 Task 4 | V5 Tasks 4–5 / V6 | large shared `state_store.py` surface | Ruling: split Task 4 into serial reviewed subunits: 4A migration/fixture, 4B formal task queue, 4C formal snapshot/receipt persistence, 4D typed universe/status persistence. They remain one plan task but are separate agent/review gates because they share a high-conflict file. The cost if wrong is additional commits and review packages, versus an unreviewable migration change. |
| V5 Task 4 | V5 Task 5 / V6 | `StateStore` V5 migration, formal task lease, snapshot APIs | Sequential dependency; V6 must not start until V5 is reviewed and committed. |
| V6 (financial plan) | V7 / V8 | formal bundles, context, frozen universe | P0 prerequisite only, not a V5 blocker: downstream implementation begins after V5 and V6 task reviews are clean. |
| V7 Task 1 | V7 Tasks 3–5 / V8 | weights and numeric representation | Ruling: the V3 spec is authoritative. Registry values use `Decimal` and buy-point T has weight `0.10`; the stray V7 float expectation and “15 percent slot” wording are corrected in implementation/tests. The cost if wrong is updating plan-derived fixtures, versus publishing mathematically incorrect scores. |
| V6 Tasks 2–5B | V6 Task 6 / V7 | effective-time provenance, registry lineage, context evidence | Ruling: before V6 persistence/worker work, make the snapshot reference the source of a fact's effective time, carry all signed child registry hashes into the feature input hash, make release eligibility manifest-bound, and define typed context evidence. These resolve documented P1 interface gaps under the binding evidence contract; cost if wrong is narrow API adaptation before V7. |
| V8 Task 4 | formal CLI entrypoint and trusted store construction | publication command wiring | Ruling: add a dedicated package entrypoint or explicitly extend a newly created `__main__.py` during V8, with explicit database path and verifier construction; never route a formal finalize through legacy orchestration. The cost if wrong is a small CLI surface change, versus an unauditable release path. |
| V8 Task 6 | sensitivity analysis | reproducible release comparison | Ruling: create a named formal sensitivity module/API that operates on immutable scored inputs and emits preview-only comparisons; do not overload reporting or mutate a published release. The cost if wrong is one additional narrow module, versus an acceptance requirement with no implementable owner. |

## Notes

- Main checkout has a user-owned unstaged `data/status/pipeline_status.json`; it is outside this worktree and must remain absent from all implementation commits.
- All new behavior follows TDD: a focused test must fail for the intended missing behavior before its production implementation is written.

Task 1: dispatched (base `5117a6d`) to a fresh implementer; report target `task-1-report.md`.
Task 1: implementation reported complete (`afaeea1 feat: add formal official evidence contract`); review package `review-5117a6d..afaeea1.diff` sent to a fresh task reviewer.
Task 1: review found Critical custom-policy third-party verification and Important non-ASCII identity acceptance; fix round 1/5 dispatched to the original implementer.
Task 1: fix round 1/5 (2 addressed, 0 open — closed custom-policy third-party verification; restricted identity to ASCII digits; commits `afaeea1..03aec55`).
Task 1: complete (commits `5117a6d..03aec55`, review clean).
Task 2: dispatched (base `03aec55`) to a fresh implementer; report target `task-2-report.md`.
Task 2: implementation reported complete (`f69709a feat: add byte-preserving formal snapshot store`); review package `review-03aec55..f69709a.diff` sent to a fresh task reviewer.
Task 2: review found Important existing-symlink root-escape acceptance and noncanonical/duplicate-key manifest acceptance; fix round 1/5 dispatched to the original implementer.
Task 2: minor (deferred): add failure-injection coverage proving `.part` cleanup after atomic-write validation/replacement failure; final whole-branch review must triage it.
Task 2: fix round 1/5 (2 addressed, 0 open — reject existing target symlink escapes; require strict canonical duplicate-key-free manifest bytes; commits `f69709a..56ddfb9`).
Task 2: out-of-scope (deferred): run direct symlink regressions in a symlink-capable CI environment; current Windows account skips them due to `WinError 1314`.
Task 2: out-of-scope (deferred): assess descriptor-relative I/O or comparable hardening if the formal raw-store threat model includes concurrent local filesystem attackers; current resolve-before-read checks do not remove all TOCTOU windows.
Task 2: complete (commits `03aec55..56ddfb9`, review clean with deferred observations).
Task 3: dispatched (base `56ddfb9`) to a fresh implementer with recorded ASCII-identity and injected-calendar rulings; report target `task-3-report.md`.
Task 3: implementation reported complete (`dabb95d feat: add formal time and universe contracts`); review package `review-56ddfb9..dabb95d.diff` sent to a fresh task reviewer.
Task 3: review found Critical mutable accepted raw rows and Important direct frozen-input / non-listing-dataset ingress bypasses; fix round 1/5 dispatched to the original implementer.
Task 3: fix round 1/5 review resolved immutable rows and closed listing dataset, but self-consistent fabricated source/audit graphs can still use the public frozen-input constructor; fix round 2/5 dispatched.
Task 3: minor (deferred): replace public-input `assert` in `FormalUniverseMember.__post_init__` with deterministic `ValueError`; final whole-branch review must triage it.
Task 3: Ruling: the full-suite `test_second_statement_failure_preserves_first_snapshot_and_partial_bundle` failure is a pre-existing, load-sensitive legacy lease-loss path (2-second wall-clock lease/heartbeat) reached before Task 3 modules are imported. Do not modify deep-worker logic in this task; rerun the suite once under low contention and record the result. Cost if wrong: an unrelated latent lease timing defect remains visible, but changing it here would conflate scope and bypass its own test/review loop.
Task 3: fix round 1/5 (2 addressed, 1 open — immutable accepted raw JSON and closed listing dataset repaired; forged source/audit graph remains; commits `dabb95d..4a734d4`).
Task 3: fix round 2/5 (1 addressed, 0 open — public frozen-input construction rejected; only ingestor private factory can create it; commits `4a734d4..3152ad8`).
Task 3: complete (commits `56ddfb9..3152ad8`, review clean; one deferred minor and one documented non-causal legacy full-suite timing flake).
