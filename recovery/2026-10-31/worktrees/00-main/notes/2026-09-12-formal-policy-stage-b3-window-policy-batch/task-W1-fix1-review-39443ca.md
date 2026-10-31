# W1 fix-1 independent review — `39443ca`

## Verdict

**REJECT — not yet specification compliant or quality approved.**

The fix delta from `d2cc8fe` to
`39443caaf18337e31e9474fef0dd57cfc7f080c1` is exactly the reported six
whitelisted paths. The total W1 diff from the accepted base remains exactly the
amended 13 code/test paths, the worktree was clean before this review artifact,
and `git diff --check` was clean.

The fix does close the direct module-global mint leak, rejects unresolved
date-only claims, enforces adjacent/same-generation calendar composition,
recomputes selections for ordinary absence changes, corrects planner branching,
preserves authenticated domain-conflict rows, strengthens Worker/distinct-config
and pagination coverage, and closes the DTO state combinations identified in the
first review. The remaining authority defect below means the mint/currentness
findings are not fully closed under the required ordinary method/field-shadow
threat model.

## Critical

1. **Proof creation and `require_current()` still depend on a caller-mutable,
   subclassable repository owner.** `_MarketRepositoryImplementation` is a normal
   mutable class with a normal instance dictionary and an assignable `_store`
   (`ashare_pipeline/formal_policy_market.py:369-384`). Calendar assembly calls
   the dynamically resolved `self._page_group` before invoking the hidden mint
   (`ashare_pipeline/formal_policy_market.py:386-411` and
   `ashare_pipeline/formal_policy_market.py:526-533`), while market assembly
   dynamically calls `self.select_calendar`
   (`ashare_pipeline/formal_policy_market.py:537-547`). The public repository
   created at `ashare_pipeline/formal_policy_market.py:668-686` has no exact-self
   check, immutable metaclass, sealed dependency record, or protection against
   subclass/instance method shadowing.

   Consequently, an ordinary caller can shadow `_page_group` on an instance (or
   override it in a subclass) so that the genuine hidden calendar mint consumes
   caller-selected genuine observations, including observations from another
   same-root Store. Likewise, overriding `select_calendar` lets the genuine
   market mint consume a caller-selected foreign coverage proof. This does not
   require recovering a mint closure.

   The new currentness callbacks have the same issue: calendar recheck calls
   dynamically replaceable `self.select_calendar` at
   `ashare_pipeline/formal_policy_market.py:528-532`, and market recheck calls
   dynamically replaceable `self.select` at
   `ashare_pipeline/formal_policy_market.py:656-662`. After evidence changes, a
   caller can shadow either method to return a `CalendarSelection` or
   `MarketSelection` containing the old proof/window; the byte comparison then
   succeeds and the stale object's `require_current()` passes without consulting
   the owning Store. Reassigning `_store` is another unsealed dependency path.

   This violates design §3's explicit requirement that ordinary inheritance,
   field shadowing, and method replacement cannot manufacture or preserve formal
   qualification. It also leaves the original proof-authority and
   absence-sensitive-currentness findings only partially fixed. Build and seal
   the repository owner inside the proof closure, reject subclasses, record the
   exact Store/dependencies, and have proof callbacks call captured original
   assembly/check functions rather than dynamically dispatched instance methods.

## Important

1. **The Source boundary still authenticates only semantic binding identity, not
   same-Store provenance for calendar proofs.** `_ProofRecord` stores wire,
   binding identity, and a callback but no owning Store identity
   (`ashare_pipeline/formal_policy_market.py:88-96`), and
   `require_calendar` compares only the semantic binding identity
   (`ashare_pipeline/formal_policy_market.py:204-209`). Source then accepts that
   result at `ashare_pipeline/formal_range_source.py:756-766` and mints market
   requests. A current calendar proof from Store A can therefore be passed to a
   reconstructed Source owned by Store B when both Stores contain the same
   signed graph. The request is genuine and can be enqueued in Store B even
   though its calendar lineage exists only in Store A. This is narrower than the
   Critical repository-shadow path, but it independently violates the required
   same-Store rule. Bind proof records to the exact owning Store and require the
   Store-resolved Source/request path to match it.

2. **The expanded regression matrix does not test the remaining authority
   boundaries.** The import-order test checks only that selected module-global
   names are absent and constructors reject callers
   (`tests/test_formal_policy_market.py:177-208`). The binding test covers
   semantic-equal distinct bindings, wrong exchange, and different roots, but
   not two Stores with the same root or repository instance/class method and
   field replacement (`tests/test_formal_policy_market.py:368-400`). There is no
   test that shadows `_page_group`, `select_calendar`, `select`, or `_store`
   before mint/recheck. The matrix is substantially improved, including real
   pagination and Worker budget exercise, but it does not establish the
   no-trust-widening requirement that the fix relies on.

## Minor

None.

## Unverifiable items

- Per instruction, this review did not run the expensive test suite. The updated
  report records focused GREEN runs, full `tests.test_formal_policy_market`
  (19/19), and full `tests.test_formal_policy_values` (22/22), but explicitly did
  not rerun the final combined W1 compatibility command. Exact-checkpoint
  combined compatibility therefore remains unverified.
- The reported RED/GREEN outputs and timings are report claims; no committed raw
  logs were available for independent authentication.
- Production network acquisition, production mappings, and production evidence
  remain intentionally outside W1 and were not verified.
