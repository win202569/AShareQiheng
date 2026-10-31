# W1 fix-3 independent review — `31f727e`

## Verdict

**CLEAN — specification compliant and quality approved.**

The fix delta from `ae444d0` to
`31f727e7011fe6fede6caf7cb2b5e0f7d509b1a3` is exactly the reported two
whitelisted paths:

1. `ashare_pipeline/formal_range_source.py`
2. `tests/test_formal_policy_market.py`

The total W1 diff from accepted base
`a90faf4f67f9371df71adbc63415e702f8f4016c` remains exactly the amended 13
code/test paths. The worktree was clean before this review artifact, and both
the fix delta and total W1 diff pass `git diff --check`.

The remaining cross-Store initial-market-request gap is closed end to end. The
private request record now carries `owner_store` only for an initial market
request (`ashare_pipeline/formal_range_source.py:171-181`). The private sealing
invariant requires exact Store provenance if and only if the request is an
initial `market_range`; initial calendar requests and every continuation retain
their prior shapes (`ashare_pipeline/formal_range_source.py:256-275`). The
Store-bound Source passes the exact Store that authenticated the calendar proof
into the private market request mint
(`ashare_pipeline/formal_range_source.py:761-774`), and execution rejects a
different destination Store before enqueue or replay can use the request
(`ashare_pipeline/formal_range_source.py:872-882` and
`ashare_pipeline/formal_range_store.py:410-423`).

The new regression exercises the complete chain: Store A resolves its Source
using Store B's semantically equal genuine binding, mints the request from Store
A's proof, successfully enqueues it in Store A, and rejects the same request in
Store B (`tests/test_formal_policy_market.py:290-307`). This preserves the
required separation between semantic binding equality and exact Store
provenance.

There is no wire, fingerprint, or persisted schema change. `owner_store` exists
only in the owner-private `_RequestRecord`; `FormalRangeRequestV1` fields,
`to_dict()`, request fingerprinting, `describe_request()`, and stored task
payloads remain unchanged (`ashare_pipeline/formal_range_source.py:185-217`,
`ashare_pipeline/formal_range_source.py:260-275`, and
`ashare_pipeline/formal_range_source.py:866-870`). Persisted initial market
requests are reconstructed through the authenticated Store-owned Source and are
bound to that Store (`ashare_pipeline/formal_range_source.py:898-923`). Initial
calendar requests still carry no Store capability, while continuations still
derive authority from their authenticated previous observation and retain the
existing StateStore/raw-root provenance check
(`ashare_pipeline/formal_range_source.py:279-317`,
`ashare_pipeline/formal_range_source.py:359-380`, and
`ashare_pipeline/formal_range_source.py:876-894`). No caller-facing authority or
registration hook was added.

## Critical

None.

## Important

None.

## Minor

None.

## Closure of all prior review findings

- Escaped proof mint authority under either import order: closed.
- Date-only visibility without an authenticated resolver: closed; such claims
  remain unproven.
- Nonadjacent or mixed-generation calendar composition: closed.
- Absence-sensitive calendar and market currentness: closed.
- Planner repeat/history blocker semantics: closed.
- Authenticated `domain_conflict` through the real repository path: closed.
- Worker budgets, distinct implementations, pagination, binding boundaries, and
  DTO semantics/regression coverage: closed.
- Mutable/subclassable repository ownership and dynamic dispatch into mint or
  currentness: closed.
- Direct same-root cross-Store proof reuse: closed while same-Store semantic-equal
  bindings remain accepted.
- Same-root cross-Store enqueue of an already-minted initial market request:
  closed by exact private Store provenance and the execution-boundary check.

No trust widening or backward-compatibility regression was found in the two-file
fix or the resulting total W1 implementation.

## Unverifiable items

- Per instruction, this independent review did not run tests. The updated report
  records the new focused RED/GREEN regression, four directly affected
  compatibility tests, and compilation, but it explicitly did not rerun the full
  market module or expanded W1 suite at `31f727e`.
- The reported command outputs and timings are implementation-report claims; no
  committed raw logs were available for independent authentication.
- Production network acquisition, mappings, and production evidence remain
  intentionally outside W1 and were not verified.
