# W1 independent review — `d2cc8fe`

## Verdict

**REJECT — not specification compliant and not quality approved.**

The committed diff from `a90faf4f67f9371df71adbc63415e702f8f4016c`
to `d2cc8fefafb5043d71b86cb85038cef4bfa8b979` has exactly the amended
13 code/test paths, the worktree was clean when reviewed, and `git diff
--check` was clean. The legacy five-anchor binding authority remains unchanged;
the separate planning authority, owning-Store reconstruction, full semantic
binding comparison, exact reconstructed factory binding, request-kind config
selection, and Worker use of `source.range_config(request)` are structurally
sound. Those positives do not offset the proof-authority and currentness defects
below.

## Critical

1. **Caller-accessible mint functions can register arbitrary calendar and
   market proofs.** `ashare_pipeline/formal_policy_market.py:184-202` accepts an
   arbitrary wire, genuine binding, and caller-supplied `recheck` callback and
   records the result as a genuine proof. The returned mint functions are then
   retained as module globals at `ashare_pipeline/formal_policy_market.py:218-220`
   and are never deleted. A caller with any genuine binding can therefore call
   `_mint_calendar_coverage(...)` with invented trading days and a no-op recheck;
   `_require_calendar_coverage` will recognize that record, and
   `FormalRangeSource.market_requests` will accept it. `_mint_market_window`
   similarly creates arbitrary genuine-looking result proofs. Exclusion from
   `__all__` is not an authority boundary. This directly violates the rulings
   that only the Market owner may mint proofs and that no proof-construction or
   registration API may escape. Keep minting inside a closure owned by the
   repository/assembler and expose only the captured read/current anchors needed
   by Source.

2. **A syntactically valid hash is incorrectly treated as independent temporal
   proof for date-only source data.** `_visible` at
   `ashare_pipeline/formal_policy_market.py:341-350` accepts a date-only record
   whenever `effective_at_utc` and `effective_time_evidence_hash` are non-null
   and the timestamp is before the freeze. The source validator at
   `ashare_pipeline/formal_range_source.py:576-594` proves only that the pair is
   structurally present and the hash is well formed; no referenced evidence is
   resolved, authenticated, bound, or rechecked. Thus an arbitrary 64-hex value
   upgrades date-only input to freeze-visible evidence. The active brief
   expressly requires both null pairs and structurally valid non-null pairs to
   remain `visibility_unproven` without independent temporal proof.

3. **Calendar composition can mint a continuous coverage proof across unknown
   dates and across coverage generations.** Per-page consistency is checked only
   within each request group at `ashare_pipeline/formal_policy_market.py:421-432`.
   Across backwards groups, `ashare_pipeline/formal_policy_market.py:451-457`
   checks overlap and row membership but never checks that coverage intervals
   are adjacent or that their upstream/refresh generations match. The proof then
   publishes the minimum and maximum as one `covered_start`/`covered_end` and
   even records a set of multiple upstream generations at
   `ashare_pipeline/formal_policy_market.py:491-501`. If two authenticated
   request groups cover `[A,B]` and `[D,E]`, the minted proof claims `[A,E]`
   while omitting every natural date in `(B,D)`; those unknown dates can contain
   trading days, corrupting the latest-250 set, stale count, and veto. Design
   §6.1 permits only adjacent, compatible coverage and forbids splicing coverage
   generations.

4. **`require_current()` does not recheck the absences that make a market window
   incomplete.** Missing requests/pages are detected at
   `ashare_pipeline/formal_policy_market.py:526-533` and become genuine missing
   daily records and pending conclusions at
   `ashare_pipeline/formal_policy_market.py:568-610`. The proof recheck at
   `ashare_pipeline/formal_policy_market.py:612-616` revalidates only the
   calendar proof, binding, and observations that already existed. It does not
   recheck that absent market fingerprints/pages remain absent, nor that the
   previous calendar request responsible for `calendar_coverage_missing`
   remains absent. When such evidence is later persisted, the old incomplete
   window can still pass `window.require_current()` and `selection.recheck()`.
   That violates the currentness rule for missing evidence and can admit a stale
   pending window into a later publication barrier. Capture and atomically
   recheck candidate snapshots/absence tokens, or recompute and byte-compare the
   complete selection.

## Important

1. **The next-request planner does not distinguish evidence blockers from a
   genuine need for older history.** After confirming that the first calendar
   page and all of its continuation pages are already present,
   `ashare_pipeline/formal_policy_market.py:636-638` returns that same already
   verified first request when selection is pending because of a visibility or
   internal coverage problem. This can repeatedly plan work that cannot change
   the state. In addition, `ashare_pipeline/formal_policy_market.py:650-660`
   requests an older calendar segment for every incomplete price window shorter
   than 250 days. It therefore scans older history after a recent effective
   trade has an unavailable close, or after a blocking current market gap or
   visibility failure, even though older data cannot establish the latest price
   and must not substitute for the missing close. Older calendar acquisition
   should occur only when the currently proved interval is fully covered, has no
   effective trade, and the price search genuinely needs more trading days.

2. **Authenticated market domain conflicts cannot survive the real repository
   path.** The evaluator can consume a synthetic `domain_conflict` row
   (`ashare_pipeline/formal_policy_market.py:266-270`), but the actual source
   assembly accepts only the ordinary covered-row shape and otherwise creates a
   generic missing row at `ashare_pipeline/formal_policy_market.py:548-577`.
   There is no authenticated representation for a domain conflict or its reason,
   so the real path must either reject it as a shape error or collapse it to
   `market_coverage_missing`; it cannot preserve and merge
   `market_domain_conflict` as required by §6.2 and the active W1 brief.

3. **The mandatory regression matrix is materially incomplete.** The new market
   test module has six pure tests and only four genuine repository/planner tests
   (`tests/test_formal_policy_market.py:34-120` and
   `tests/test_formal_policy_market.py:123-190`). It does not cover non-null
   date-only temporal claims, non-adjacent or mixed-generation calendar groups,
   numbered pagination completeness, stale missing-proof invalidation, the real
   domain-conflict path, wrong exchange/root/generation/duplicate-date cases, or
   market-proof forgery. The Worker test named for distinct retry/cooldown/page
   budgets changes no page budget and, because retry attempts are set to one,
   only asserts terminal failure without exercising either configured cooldown
   or page behavior (`tests/test_formal_range_worker.py:31-56`). There is also no
   new source-first/market-first fresh-process test or a test with genuinely
   distinct calendar and market implementation keys. These omissions are
   acceptance failures and would have exposed several Critical findings above.

## Minor

1. **The supposedly strict `market_window` DTO validator accepts impossible
   state combinations.** `ashare_pipeline/formal_policy_values.py:174-214`
   validates field types but allows `confirmed_no_price_250` without the required
   `market_evidence_missing`, allows `incomplete` with no pending reason, and
   allows complete-price states to carry unrelated pending reasons. The DTO is
   deliberately non-authoritative, so this is not a proof-forgery issue, but it
   does not meet the requested closed semantic validation. The added test at
   `tests/test_formal_policy_values.py:68-88` exercises only the positive-price
   happy path and a few scalar/type mutations.

## Unverifiable items

- Per instruction, this review did not run the expensive suite. The implementation
  report's expanded 147-test run was made before one source test was removed;
  it explicitly says that only the 31-test source module was rerun afterward
  (`.superpowers/sdd/2026-09-12-formal-policy-stage-b3-window-policy-batch/task-W1-report.md:52-66`).
  Therefore there is no fresh combined GREEN for the exact committed checkpoint.
- The reported RED/GREEN timings and exit codes have no preserved logs in the
  reviewed committed diff and could not be independently authenticated here.
- Production acquisition, live-source mappings, and production evidence remain
  intentionally outside W1 and were not verified.
