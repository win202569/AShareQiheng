# W1 fix-2 independent review — `ae444d0`

## Verdict

**REJECT — not yet specification compliant or quality approved.**

The fix delta from `39443ca` to
`ae444d0267936b5f8fa0969fcaa5c7c713d4fce4` is exactly the reported four
whitelisted paths, and the total W1 diff from accepted base
`a90faf4f67f9371df71adbc63415e702f8f4016c` remains exactly the amended 13
code/test paths. The worktree was clean before this review artifact, and both
fix-delta and total-W1 `git diff --check` were clean.

The repository-owner defect from the fix-1 review is closed. The public owner
is built inside the proof closure, is exact-type checked, slot-only,
non-subclassable through its metaclass, and has no caller-settable Store field
(`ashare_pipeline/formal_policy_market.py:223-329`). Its private record captures
the exact Store and original unbound Store, Source, observation, and assembly
operations (`ashare_pipeline/formal_policy_market.py:230-289` and
`ashare_pipeline/formal_policy_market.py:788-803`). Minting and currentness call
the captured `assemble_calendar` / `assemble_market` functions rather than
dynamically dispatching through repository attributes
(`ashare_pipeline/formal_policy_market.py:272-290`,
`ashare_pipeline/formal_policy_market.py:640-645`, and
`ashare_pipeline/formal_policy_market.py:775-783`). Ordinary instance-field,
method-shadow, and subclass attacks therefore no longer reach proof minting or
preserve stale proofs.

Calendar proof records also now retain the exact owning Store and the Source is
bound once to its Store, while semantic binding comparison remains independent
(`ashare_pipeline/formal_policy_market.py:89-96`,
`ashare_pipeline/formal_policy_market.py:185-212`, and
`ashare_pipeline/formal_range_source.py:1003-1018`). This correctly accepts a
semantically equal distinct genuine binding through the same Store and rejects
passing Store A's proof directly to Store B's Source. However, the resulting
market request still loses that provenance at the Store execution boundary, so
the prior same-Store finding is only partially closed.

## Critical

None.

## Important

1. **An initial market request minted from Store A's proof can still be enqueued
   and executed by Store B with the same signed root.** The request owner record
   contains only the binding, wire/config identity, and optional previous/parent;
   it does not retain the Store that authorized the calendar proof
   (`ashare_pipeline/formal_range_source.py:171-180` and
   `ashare_pipeline/formal_range_source.py:255-270`). The newly Store-aware
   Source validates Store A's proof and then calls `restore_market_request`,
   which seals only those Store-free request fields
   (`ashare_pipeline/formal_range_source.py:756-769`).

   At execution, `require_execution()` compares Store provenance only when
   `sealed.previous is not None`; an initial market request has no previous
   observation, so the function returns without any Store check
   (`ashare_pipeline/formal_range_source.py:867-875`).
   `FormalRangeStore.enqueue()` nevertheless treats that check as sufficient and
   then reconstructs the binding from the destination Store's same-root graph
   (`ashare_pipeline/formal_range_store.py:410-423`). Therefore a caller can:

   1. obtain a genuine current calendar proof and genuine market request through
      Store A's bound Source;
   2. pass that already-minted request directly to Store B; and
   3. have Store B enqueue and execute it even though the request's
      `calendar_coverage_hash` was authorized only by Store A's evidence.

   This is the same cross-repository lineage break identified in the fix-1
   review, moved one boundary later. It violates the active same-Store rule and
   design §3's prohibition on cross-repository assembly manufacturing formal
   qualification; it also weakens design §5.2's requirement that a market
   request's calendar hash point to the genuine coverage proof authorizing that
   acquisition. Bind initial market request records to the exact Store that
   validated their calendar proof and require exact Store identity in
   `require_execution()` / `enqueue()`; same-Store semantically equal bindings
   should continue to pass.

## Minor

1. **The new cross-Store regression stops before the vulnerable Store boundary.**
   `test_calendar_proof_rejects_same_root_cross_store_reuse` proves that Store
   B's Source rejects Store A's proof, and that a semantically equal binding is
   accepted through Store A
   (`tests/test_formal_policy_market.py:272-287`). It never mints the market
   request through Store A and asserts that `peer.range_store.enqueue(request,
   ...)` rejects it. No other test covers that initial cross-Store market-request
   path. Add that case, ideally for distinct Store objects with identical signed
   roots, so the proof-to-request-to-enqueue provenance chain is tested end to
   end.

## Closure of prior findings

- Direct proof-mint escape under either import order: closed.
- Date-only claims without a real resolver: closed; they remain unproven.
- Calendar adjacency and same-generation composition: closed.
- Absence-sensitive calendar and market currentness: closed for the sealed
  repository path; rechecks use captured original assembly functions.
- Planner no-repeat / blocker semantics: closed.
- Authenticated `domain_conflict` repository path: closed.
- Worker budgets, distinct implementations, pagination, binding-boundary, and
  DTO regression coverage from fix round 1: closed to the extent statically
  reviewable here.
- Mutable/subclassable repository proof authority: closed.
- Exact same-Store provenance: **not fully closed**, for the initial market
  request execution path described above.

## Unverifiable items

- Per instruction, this review did not run the expensive test suite. The updated
  implementation report records focused fix-2 GREEN runs and compilation, but
  explicitly did not rerun the full market module or expanded W1 suite at the
  exact fix-2 checkpoint.
- The reported RED/GREEN outputs and timings are implementation-report claims;
  no committed raw logs were available for independent authentication.
- Production network acquisition, mappings, and production evidence remain
  intentionally outside W1 and were not verified.
