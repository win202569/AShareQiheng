# Operation-scoped range binding read lease

Baseline: `1af0e2bae2cf9819e963532cfdbcb1e34b693cfe`.

Scope: only one market/calendar ticket owner operation shares a current-binding
read lease.  Journal phases, builds, owners, threads, members, and distinct
binding identities never share a lease.  The market operation's mandatory
calendar child ticket stays inside the same outer lease rather than opening a
recursive lease.

## RED evidence

- Real 20-day and 40-day/multi-request fixtures observed 513 complete
  `_capture_graph_snapshot` calls apiece instead of the required two; 1 test
  failed in 116.675 seconds.
- In-place signed source child byte mutation (with unchanged SQLite
  `data_version`) was rejected, but restoration allowed reuse of the same owner
  scope; 1 test failed in 53.359 seconds because the scope was not consumed.
- Two independent journal phases observed 517 and 513 captures while the
  monitor also covered the intervening checkpoint; 1 test failed in 84.838
  seconds.  The final test limits counting to the owner operation itself.
- A lease-entry source mutation showed that entry failures did not consume the
  journal; the focused test failed in 0.990 seconds before the owner wrapper was
  extended around lease opening.
- Final regression exposed a cold Store cache scanning unrelated market-rule
  bindings inside the strict lease.  Existing ticket tests failed closed; the
  Store now resolves the exact sealed hash+exchange binding without probing
  unrelated bindings.
- Follow-up review found that the lightweight read omitted the signed-envelope
  fields.  A real `_read_binding` callback changed `source.signature` to
  `forged` and restored it before the next call; the old implementation issued
  the ticket and the focused test failed in 38.551 seconds.
- A real token closed from another thread was rejected only after its active
  bit had been cleared, so the owning thread could no longer close it.  The
  focused test failed in 38.283 seconds.
- A genuine binding combined with `object()` and `('arbitrary',)` could open a
  lease because entry trusted caller-supplied tuples.  The owner/recursion test
  failed in 27.537 seconds before production changes.

## GREEN behavior

- The range contract owns an opaque, registered, non-copyable,
  non-serializable lease token and a `ContextVar` state bound to the exact
  thread, owner scope, logical binding root/hash/rule/exchange, and operation
  key.
- Entry and exit each perform one complete graph snapshot and require equality
  with the originally sealed graph.  Every read inside the lease still checks
  the exact registered child/parent, manifest object and every sealed manifest
  envelope field, every child object/envelope field/raw byte/hash/manifest
  hash, and both range config canonical byte snapshots.
- In-place source-byte mutation before the next read rejects before market
  ticket issuance, consumes the owner scope, and permits success only with a
  fresh scope after restoration.
- Lease entry now derives the exact owner, unforgeable journal epoch, phase,
  operation key, and allowed call entry from the genuine journal scope and
  real owner frame.  Calendar recursion is rejected; one market operation may
  use exactly one controlled calendar child.  A phase transition invalidates
  the old lease.  Cross-thread close validates before changing token state.
- Final focused lease suite: 7/7 passed in 328.601 seconds.  Capture counts are
  exactly 2 for both the 20-day and 40-day/multi-request operations, and `[2,
  2]` across two independent journal phases.

## Regression and performance evidence

- Warm config/raw/current mutation plus journal replay/cross-owner/cross-thread
  and exact cold binding reconstruction selection: 9/9 passed in 23.695
  seconds.
- Market ticket module: 11/11 passed in 116.926 seconds.
- Final market module: 26/26 passed in 1286.440 seconds.
- C4 three-member four-phase profile: 1/1 passed in 551.380 seconds, with all
  four checkpoints reported.
- Low-overhead three-member build after review hardening: 169.227 seconds, 9
  adjusted rows.
  `_read_binding` remained 1425; complete `_capture_graph_snapshot` fell from
  1577 to 44.  Approximate sampled boundaries were metric preparation 26.8s,
  metric checkpoint 6.7s, policy preparation 72.6s, policy checkpoints 35.0s,
  and final checkpoint 25.0s.

No 20-member run was performed.  The report is ignored and is not part of the
code/test commit.

## Second review hardening

- RED: closing a genuine outer token through `copy_context().run(...)` raised
  only after marking the shared token inactive, so the owner later failed with
  `forged, copied, or closed`; 1 test failed in 34.813 seconds.
- RED: replacing `sys._getframe` with a forwarding fake was accepted and the
  owner operation completed; 1 test failed in 42.190 seconds.
- Close now validates token, thread, current state, owner epoch/phase, and the
  full exit graph before attempting the creating ContextVar token reset.  The
  reset is the context-identity proof and occurs before shared active/child
  state mutation.  Nested calendar leases have their own ContextVar token.
- The installer captures and guards the genuine `sys._getframe` and
  `threading.get_ident`; owner entry calls only the captured frame function.
- Final lease suite: 9/9 passed in 410.723 seconds.  Focused security/cold
  regressions: 9/9 passed in 30.690 seconds.  Ticket: 11/11 in 120.155 seconds;
  market: 26/26 in 1325.520 seconds; C4 four-phase profile: 1/1 in 550.640
  seconds with all four checkpoints.
- Final three-member build: 171.261 seconds, 9 adjusted rows,
  `_capture_graph_snapshot=44`, `_read_binding=1425`.

## Third review hardening

- RED: replacing `threading.get_ident` with `lambda: -1` made range entry fail,
  but also prevented the owner's exception path from closing its journal.  On
  restoration the original journal checkpoint was still accepted; 1 test
  failed in 32.628 seconds.
- The journal installer now captures the genuine thread identity function.
  All normal scope/open paths guard the module member and use the captured
  function; the revocation-only `close` path deliberately uses the captured
  function without the mutable-member guard so an already-open genuine owner
  scope can always be consumed during dependency pollution.
- Final attack test: 1/1 passed in 50.476 seconds.  Lease: 10/10 in 496.089
  seconds; complete journal: 23/23 in 269.459 seconds; security/cold selection:
  9/9 in 32.472 seconds; ticket: 11/11 in 116.700 seconds; focused market owner
  paths: 4/4 in 348.158 seconds; C4 four-phase: 1/1 in 542.365 seconds.
- Final three-member build: 162.487 seconds, 9 adjusted rows,
  `_capture_graph_snapshot=44`, `_read_binding=1425`.

## Shared-request sibling binding regression

- RED on `c7215d8`: a real bank calendar task and a broker request had the
  same canonical SH request fingerprint but different signed binding hashes.
  The broker owner operation failed exact-binding validation after 146.282
  seconds even though SQLite contained exactly one task and one snapshot for
  that request lineage.
- A request-scoped sibling-read capability is now confined to the genuine
  owner lease, thread, journal epoch/phase, owner binding, registry root,
  exchange, source hash, canonical config, request fingerprint, and request
  kind.  Reads retain per-access envelope/raw/hash checks and the owner lease
  retains complete entry/exit graph captures.  No unbound or global same-root
  fallback exists.
- A second RED exposed the shared request's absent next page: the journal key
  was identical, but the absence baseline embedded the binding-specific hash.
  Absence baselines now use the semantic request/config/source/parent identity
  while complete signed request evidence remains unchanged and is rechecked.
- Positive and seven negative sibling cases passed in 110.318 seconds.  The
  negative matrix covers request bytes/fingerprint, config bytes/range config
  ID, source registry hash, registry root, and exchange; each consumes the
  rejected scope and succeeds only with a fresh scope.
- Final affected verification: lease 11/11 in 141.520 seconds; original policy
  integration regression 1/1 in 189.168 seconds; market ticket 11/11 in
  26.060 seconds; market/journal focused 9/9 in 202.183 seconds; sibling plus
  contract security/cold focused 10/10 in 192.237 seconds.

No Step 6/7, 20-member, or 23-test long acceptance run was performed.  This
report remains ignored and is not part of the code/test commit.

## Sibling capability review hardening

- RED: a self-consistent ordinary dict with missing security/date/cutoff
  fields and an arbitrary parent was accepted as a sibling request; 1 test
  failed in 2.130 seconds.
- RED: while the F1 capability was ambient, a nested Store selection of a
  persisted F2 request with `request=None` did not raise the required
  cross-binding rejection; 1 test failed in 245.022 seconds.
- RED: the three standalone absence-ticket tests regressed because every
  bound request attempted to open an owner capability even when no market or
  calendar owner lease existed; 0/3 passed in 8.262 seconds.
- The range-source request authority now exposes a captured sealed proof that
  authenticates the exact registered `FormalRangeRequestV1`, object fields,
  canonical request bytes, fingerprint, parent, config, source root, and
  binding hash without borrowing an ambient current-binding decision.
- Contract installation seals that prover plus the exact Store selector,
  read, observation-current, and ticket-recheck code entries.  Direct dict or
  callback calls cannot open capabilities.  Store reads carry a nested target
  context containing the actual persisted fingerprint/task; sibling reads
  require that target or the exact sealed parent task.
- Request, persisted-observation, and ticket-evidence capabilities are opened
  only for their fixed Store segments, nested with ContextVar tokens, and
  closed in LIFO order.  No-request reads remain exact-binding.  Standalone
  absence reads open no owner capability and retain the original full checks.
- Final shared positive, F2 attack, and eight mismatch cases: 1/1 passed in
  279.727 seconds.  Lease module: 12/12 in 651.911 seconds.  Absence plus the
  original policy integration regression: 4/4 in 397.933 seconds.  Ticket,
  market, and journal focused regression: 20/20 in 309.108 seconds.  Contract
  security/cold selection: 9/9 in 2.461 seconds.

No Step 7 or other long acceptance run was performed.  This report remains
ignored and is not part of the code/test commit.

## Exact-only nested selection and genuine mismatch matrix

- RED: during a real broker F1 owner operation, a nested unbound Store
  selection (`request=None`) borrowed the ambient same-fingerprint sibling
  capability and succeeded instead of enforcing exact binding; the focused
  test failed in 154.405 seconds.
- Unbound selection and ticket-recheck segments now install a sealed,
  thread/owner-lease-bound exact-only ContextVar mask.  The mask disables only
  sibling reads, preserves exact binding reads, is nested and exception safe,
  and is removed in `finally` blocks.
- The eight mismatch cases now travel through a genuine Store observation and
  sealed request path rather than directly invoking the private capability
  opener.  The first run reached all seven explicit field checks; only the
  malformed self-consistent request shape remained accepted, so the focused
  test failed in 327.785 seconds.  Capability minting now also requires the
  exact formal request field set and exact sealed-parent shape.
- Final shared positive, same-F1 unbound attack, F1-to-F2 attack, and all eight
  genuine mismatch cases passed in 302.281 seconds.  Lease module: 12/12 in
  701.636 seconds.  Absence plus policy integration: 4/4 in 336.978 seconds.
  Ticket, market, and journal focused regression: 20/20 in 624.385 seconds.

No Step 7 or long acceptance run was performed.  This report remains ignored
and is not part of the code/test commit.

## Copied-context capability retirement

- RED on `7dd8139`: a genuine shared bank/broker operation copied the active
  owner lease, sibling request, target, and exact-only contexts.  After the
  original operation closed, the first copied owner-lease context still
  accepted `binding.require_current`; the focused test failed in 175.311
  seconds.
- Every ContextVar state now carries its sealed capability identity and a
  unique generation.  Binding reads validate the shared record identity,
  generation, active state, owner lease, thread, epoch, and phase before using
  lease, sibling, target, or exact-only authority.  Successful owner-context
  closes reset their ContextVar token and retire the shared record; a close in
  a copied context fails token reset before it can retire the genuine record.
  Retired records are removed, while object and generation identity prevent an
  old copied state from colliding with a later capability.
- The genuine attack test captures all four active contexts, proves copied
  closes are rejected without disturbing the owner, proves the original
  tokens are closed, then rejects exact and cross-binding replays.  It passed
  after the fix in 292.125 seconds and, after the explicit closed-token
  assertions, in 257.169 seconds.
- Lease module: 12/12 in 757.862 seconds.  Absence plus policy integration:
  4/4 in 478.354 seconds.  Ticket, market, and journal focused regression:
  20/20 in 466.398 seconds.

No Step 7, 20-member, or 23-test long acceptance run was performed.  This
report remains ignored and is not part of the code/test commit.
