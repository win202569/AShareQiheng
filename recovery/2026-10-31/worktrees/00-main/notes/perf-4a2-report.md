# Perf4a2 implementation report

Implemented current-only owner tickets for policy state, policy financial, policy feature state, calendar, market, and bound range absence. Existing public selectors and `recheck` methods retain their production paths. The journal now accepts the exact linked lower owner for each policy owner and checks every ticket once per phase. Owner tickets hold the actual selection object and canonical selection bytes; lower tickets are issued inside the corresponding first selection, and issuance checks their evidence before returning. Checkpoints reread the captured evidence without invoking policy selectors, feature builders/evaluators, or range parsers.

Range absence requires a genuine sealed request. Its empty candidate snapshot, request description, and any parent candidate/source chain are included in the ticket. A later candidate or parent change revokes it.

Verification performed:

- New targeted ticket tests: state absence and late Context, two-member scope, method replacement, financial absent receipt and return-boundary insertion, market calendar absence, calendar present with market absence, market present with raw-file tamper, range initial and parent-continuation absence. Each ran successfully; the initial six-test group ran in 114.354 seconds.
- Existing `tests.test_formal_batch_read_journal`: 23 tests passed in 193.238 seconds.
- Adjacent old state/financial/market recheck tests: 3 passed in 158.544 seconds.
- Python compilation and `git diff --check` passed for changed implementation files.

Review follow-up (Perf4a2 audit):

- A continuation absence now consumes the candidate and authenticated source token captured inside the same parent `require_current` validation invoked by `require_execution`. A same-leading conflicting parent candidate inserted at the `require_execution` return boundary is rejected before issuance, and the original parent proof's public `require_current` also rejects it.
- Calendar and market selections are now owner-sealed inside the actual implementation selector before its return. The sealed record holds the selection object, fields, proof ownership and canonical wire, binding, request, and lower tickets. Ticket issuance compares the returned object to that record; return-boundary mutation of pending or selection hash is rejected for both selection kinds.
- The checkpoint profile now captures the actual `select` and `select_calendar` implementation code objects during issuance and proves that neither runs during checkpoint, alongside range selection and parser exclusions.
- Static audit: state and financial results already write their canonical bytes into private selection registries inside their selectors before return. Their slot-only public objects do not provide mutable payload fields, so no equivalent return-object baseline read was found.
- Review follow-up targeted suite: 13 tests passed in 289.169 seconds. After adding explicit proof that both return-event injections fired, those two tests passed again. Existing journal regression: 23/23 passed in 382.834 seconds; adjacent old state/financial/market regressions: 3/3 passed in 344.532 seconds. These two old suites were run concurrently, so their durations include resource contention.

Final constructor audit:

- At market owner installation, both selection types' exact identities, `__new__`, `__init__`, field lookup/setter, dataclass field objects and descriptors, and slots are captured. Journal open, selection sealing, and warm checkpoint reject changes to this narrow interface. An unrelated `__repr__` change remains allowed.
- Ticketed selectors use the captured constructors and compare every constructed field with the selector's arguments before sealing. A return-event mutation at either constructor is rejected before it can become a ticket baseline. Existing market/calendar implementation-return mutation tests remain green.
- Focused boundary, constructor, and adjacent old checks: 10/10 passed in 107.914 seconds. Present calendar/market proof paths: 2/2 passed in 110.667 seconds.

The targeted profile checks prohibit policy state/financial/market top-level selectors, feature builder/evaluator, range selection, and registered range parser during checkpoint. No long store/C4 suite was run. C4-owned dirty files were not edited or staged.

Market ticket test-order follow-up:

- Reproduced the reported RED sequence: the preopen constructor replacement test and field/alias test passed, then the present raw-change test failed before ticket issuance with `object.__new__() takes exactly one argument`.
- The cause was test-only process pollution: changing a slots dataclass `__new__` and deleting the temporary class member restored its class dictionary but not its constructor slot behavior. The `__new__` guard probes now run in isolated child processes. Every test-owned method, field, and module-alias replacement uses a `finally` cleanup that restores an original local member or deletes a formerly inherited/missing temporary member. The mutable dataclass-field entry and profiler hooks likewise retain guaranteed cleanup.
- The RED sequence now passes (3/3, 49.533 seconds). The entire market ticket module passes in default order (10/10, 144.877 seconds) and reverse order (10/10, 141.706 seconds). Adjacent present/current and older-segment proof checks pass (2/2, 79.142 seconds).
- After the final cleanup invariant was tightened, the preopen and warm constructor guards passed again (2/2, 13.843 seconds). Test-file compilation and whitespace validation passed.

Subprocess timeout follow-up:

- The isolated `__new__` constructor guard now has a 60-second upper bound. `TimeoutExpired` fails the parent test with the elapsed limit plus captured child stdout/stderr, preserving the exception as its cause.
- A fast simulated-timeout test first failed because no timeout was supplied, then passed after the guard change. Default-order constructor/field/present/timeout subset passed 5/5 in 75.441 seconds; reverse order passed 5/5 in 65.541 seconds. No production or C4/Perf4b files were edited.
