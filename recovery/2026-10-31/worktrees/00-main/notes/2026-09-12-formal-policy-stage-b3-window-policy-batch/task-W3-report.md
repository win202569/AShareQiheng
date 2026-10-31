# W3 implementation report

Status: RECOVERY COMPLETE; awaiting controller review. No Git writes or production/network operations.

## Scope

BASE: 2c021fc8b9bd2ae58eb911e35cfd2a47600b8733.
The controller approved the three-path read-only range ownership seam in the amended task-W3-brief.md. Original four W3 files plus formal_range_store.py, formal_range_source.py and test_formal_range_store.py only.

## TDD evidence

Required initial RED command:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_repository tests.test_formal_policy_batch_guards -v
```

Exit 1; 18 tests; 0.089s; 18 expected assertion failures for the absent W3 authority. Production implementation did not exist at this point. Exact unittest output:

```text
test_complete_enumeration_includes_pending_security (tests.test_formal_policy_repository.PolicyRepositoryTests.test_complete_enumeration_includes_pending_security) ... FAIL
test_configuration_missing_and_ambiguous_fail_before_publication (tests.test_formal_policy_repository.PolicyRepositoryTests.test_configuration_missing_and_ambiguous_fail_before_publication) ... FAIL
test_entry_and_dependency_replacement_fail_closed (tests.test_formal_policy_repository.PolicyRepositoryTests.test_entry_and_dependency_replacement_fail_closed) ... FAIL
test_foreign_signature_root_rejected (tests.test_formal_policy_repository.PolicyRepositoryTests.test_foreign_signature_root_rejected) ... FAIL
test_forged_scoring_and_policy_registries_are_rejected (tests.test_formal_policy_repository.PolicyRepositoryTests.test_forged_scoring_and_policy_registries_are_rejected) ... FAIL
test_genuine_all_member_evidence_reaches_complete_results (tests.test_formal_policy_repository.PolicyRepositoryTests.test_genuine_all_member_evidence_reaches_complete_results) ... FAIL
test_missing_universe_is_failure (tests.test_formal_policy_repository.PolicyRepositoryTests.test_missing_universe_is_failure) ... FAIL
test_proofs_reject_construction_copy_shadowing_and_cross_batch_composition (tests.test_formal_policy_repository.PolicyRepositoryTests.test_proofs_reject_construction_copy_shadowing_and_cross_batch_composition) ... FAIL
test_provider_unpublished_assigned_fails_unknown_membership_does_not_fetch (tests.test_formal_policy_repository.PolicyRepositoryTests.test_provider_unpublished_assigned_fails_unknown_membership_does_not_fetch) ... FAIL
test_same_root_foreign_store_range_and_context_are_rejected (tests.test_formal_policy_repository.PolicyRepositoryTests.test_same_root_foreign_store_range_and_context_are_rejected) ... FAIL
test_unknown_membership_never_fabricates_five_template_decisions (tests.test_formal_policy_repository.PolicyRepositoryTests.test_unknown_membership_never_fabricates_five_template_decisions) ... FAIL
test_after_first_security_read_second_security_provider_changes (tests.test_formal_policy_batch_guards.PolicyBatchGuardTests.test_after_first_security_read_second_security_provider_changes) ... FAIL
test_database_write_during_evaluation_rejects (tests.test_formal_policy_batch_guards.PolicyBatchGuardTests.test_database_write_during_evaluation_rejects) ... FAIL
test_equal_leading_state_ambiguity_rejects (tests.test_formal_policy_batch_guards.PolicyBatchGuardTests.test_equal_leading_state_ambiguity_rejects) ... FAIL
test_final_reentrant_publication_or_cleanup_failure_revokes_every_child (tests.test_formal_policy_batch_guards.PolicyBatchGuardTests.test_final_reentrant_publication_or_cleanup_failure_revokes_every_child) ... FAIL
test_initially_missing_industry_then_present_rejects (tests.test_formal_policy_batch_guards.PolicyBatchGuardTests.test_initially_missing_industry_then_present_rejects) ... FAIL
test_prepare_has_no_writer_reservation_and_children_are_unpublished (tests.test_formal_policy_batch_guards.PolicyBatchGuardTests.test_prepare_has_no_writer_reservation_and_children_are_unpublished) ... FAIL
test_source_raw_bytes_change_without_database_write_rejects (tests.test_formal_policy_batch_guards.PolicyBatchGuardTests.test_source_raw_bytes_change_without_database_write_rejects) ... FAIL

======================================================================
FAIL: test_complete_enumeration_includes_pending_security (tests.test_formal_policy_repository.PolicyRepositoryTests.test_complete_enumeration_includes_pending_security)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\tests\test_formal_policy_repository.py", line 13, in setUp
    self.assertIsNotNone(importlib.util.find_spec("ashare_pipeline.formal_policy_repository"),
AssertionError: unexpectedly None : W3 complete policy publication is missing

======================================================================
FAIL: test_configuration_missing_and_ambiguous_fail_before_publication (tests.test_formal_policy_repository.PolicyRepositoryTests.test_configuration_missing_and_ambiguous_fail_before_publication)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\tests\test_formal_policy_repository.py", line 13, in setUp
    self.assertIsNotNone(importlib.util.find_spec("ashare_pipeline.formal_policy_repository"),
AssertionError: unexpectedly None : W3 complete policy publication is missing

======================================================================
FAIL: test_entry_and_dependency_replacement_fail_closed (tests.test_formal_policy_repository.PolicyRepositoryTests.test_entry_and_dependency_replacement_fail_closed)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\tests\test_formal_policy_repository.py", line 13, in setUp
    self.assertIsNotNone(importlib.util.find_spec("ashare_pipeline.formal_policy_repository"),
AssertionError: unexpectedly None : W3 complete policy publication is missing

======================================================================
FAIL: test_foreign_signature_root_rejected (tests.test_formal_policy_repository.PolicyRepositoryTests.test_foreign_signature_root_rejected)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\tests\test_formal_policy_repository.py", line 13, in setUp
    self.assertIsNotNone(importlib.util.find_spec("ashare_pipeline.formal_policy_repository"),
AssertionError: unexpectedly None : W3 complete policy publication is missing

======================================================================
FAIL: test_forged_scoring_and_policy_registries_are_rejected (tests.test_formal_policy_repository.PolicyRepositoryTests.test_forged_scoring_and_policy_registries_are_rejected)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\tests\test_formal_policy_repository.py", line 13, in setUp
    self.assertIsNotNone(importlib.util.find_spec("ashare_pipeline.formal_policy_repository"),
AssertionError: unexpectedly None : W3 complete policy publication is missing

======================================================================
FAIL: test_genuine_all_member_evidence_reaches_complete_results (tests.test_formal_policy_repository.PolicyRepositoryTests.test_genuine_all_member_evidence_reaches_complete_results)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\tests\test_formal_policy_repository.py", line 13, in setUp
    self.assertIsNotNone(importlib.util.find_spec("ashare_pipeline.formal_policy_repository"),
AssertionError: unexpectedly None : W3 complete policy publication is missing

======================================================================
FAIL: test_missing_universe_is_failure (tests.test_formal_policy_repository.PolicyRepositoryTests.test_missing_universe_is_failure)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\tests\test_formal_policy_repository.py", line 13, in setUp
    self.assertIsNotNone(importlib.util.find_spec("ashare_pipeline.formal_policy_repository"),
AssertionError: unexpectedly None : W3 complete policy publication is missing

======================================================================
FAIL: test_proofs_reject_construction_copy_shadowing_and_cross_batch_composition (tests.test_formal_policy_repository.PolicyRepositoryTests.test_proofs_reject_construction_copy_shadowing_and_cross_batch_composition)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\tests\test_formal_policy_repository.py", line 13, in setUp
    self.assertIsNotNone(importlib.util.find_spec("ashare_pipeline.formal_policy_repository"),
AssertionError: unexpectedly None : W3 complete policy publication is missing

======================================================================
FAIL: test_provider_unpublished_assigned_fails_unknown_membership_does_not_fetch (tests.test_formal_policy_repository.PolicyRepositoryTests.test_provider_unpublished_assigned_fails_unknown_membership_does_not_fetch)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\tests\test_formal_policy_repository.py", line 13, in setUp
    self.assertIsNotNone(importlib.util.find_spec("ashare_pipeline.formal_policy_repository"),
AssertionError: unexpectedly None : W3 complete policy publication is missing

======================================================================
FAIL: test_same_root_foreign_store_range_and_context_are_rejected (tests.test_formal_policy_repository.PolicyRepositoryTests.test_same_root_foreign_store_range_and_context_are_rejected)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\tests\test_formal_policy_repository.py", line 13, in setUp
    self.assertIsNotNone(importlib.util.find_spec("ashare_pipeline.formal_policy_repository"),
AssertionError: unexpectedly None : W3 complete policy publication is missing

======================================================================
FAIL: test_unknown_membership_never_fabricates_five_template_decisions (tests.test_formal_policy_repository.PolicyRepositoryTests.test_unknown_membership_never_fabricates_five_template_decisions)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\tests\test_formal_policy_repository.py", line 13, in setUp
    self.assertIsNotNone(importlib.util.find_spec("ashare_pipeline.formal_policy_repository"),
AssertionError: unexpectedly None : W3 complete policy publication is missing

======================================================================
FAIL: test_after_first_security_read_second_security_provider_changes (tests.test_formal_policy_batch_guards.PolicyBatchGuardTests.test_after_first_security_read_second_security_provider_changes)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\tests\test_formal_policy_batch_guards.py", line 13, in setUp
    self.assertIsNotNone(importlib.util.find_spec("ashare_pipeline.formal_policy_repository"),
AssertionError: unexpectedly None : W3 atomic policy publication is missing

======================================================================
FAIL: test_database_write_during_evaluation_rejects (tests.test_formal_policy_batch_guards.PolicyBatchGuardTests.test_database_write_during_evaluation_rejects)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\tests\test_formal_policy_batch_guards.py", line 13, in setUp
    self.assertIsNotNone(importlib.util.find_spec("ashare_pipeline.formal_policy_repository"),
AssertionError: unexpectedly None : W3 atomic policy publication is missing

======================================================================
FAIL: test_equal_leading_state_ambiguity_rejects (tests.test_formal_policy_batch_guards.PolicyBatchGuardTests.test_equal_leading_state_ambiguity_rejects)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\tests\test_formal_policy_batch_guards.py", line 13, in setUp
    self.assertIsNotNone(importlib.util.find_spec("ashare_pipeline.formal_policy_repository"),
AssertionError: unexpectedly None : W3 atomic policy publication is missing

======================================================================
FAIL: test_final_reentrant_publication_or_cleanup_failure_revokes_every_child (tests.test_formal_policy_batch_guards.PolicyBatchGuardTests.test_final_reentrant_publication_or_cleanup_failure_revokes_every_child)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\tests\test_formal_policy_batch_guards.py", line 13, in setUp
    self.assertIsNotNone(importlib.util.find_spec("ashare_pipeline.formal_policy_repository"),
AssertionError: unexpectedly None : W3 atomic policy publication is missing

======================================================================
FAIL: test_initially_missing_industry_then_present_rejects (tests.test_formal_policy_batch_guards.PolicyBatchGuardTests.test_initially_missing_industry_then_present_rejects)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\tests\test_formal_policy_batch_guards.py", line 13, in setUp
    self.assertIsNotNone(importlib.util.find_spec("ashare_pipeline.formal_policy_repository"),
AssertionError: unexpectedly None : W3 atomic policy publication is missing

======================================================================
FAIL: test_prepare_has_no_writer_reservation_and_children_are_unpublished (tests.test_formal_policy_batch_guards.PolicyBatchGuardTests.test_prepare_has_no_writer_reservation_and_children_are_unpublished)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\tests\test_formal_policy_batch_guards.py", line 13, in setUp
    self.assertIsNotNone(importlib.util.find_spec("ashare_pipeline.formal_policy_repository"),
AssertionError: unexpectedly None : W3 atomic policy publication is missing

======================================================================
FAIL: test_source_raw_bytes_change_without_database_write_rejects (tests.test_formal_policy_batch_guards.PolicyBatchGuardTests.test_source_raw_bytes_change_without_database_write_rejects)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\tests\test_formal_policy_batch_guards.py", line 13, in setUp
    self.assertIsNotNone(importlib.util.find_spec("ashare_pipeline.formal_policy_repository"),
AssertionError: unexpectedly None : W3 atomic policy publication is missing

----------------------------------------------------------------------
Ran 18 tests in 0.089s

FAILED (failures=18)
```

Range seam RED command:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_range_store.FormalRangeStoreTests.test_private_owner_check_accepts_only_genuine_same_store_and_verifier -v
```

Exit 1; Ran 1 test in 0.341s; FAILED (failures=1). Assertion: `False is not true : W3 range owner identity validator is missing`.
Same command GREEN: Exit 0; Ran 1 test in 8.038s; OK.

Additional TDD regression command:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_repository.PolicyRepositoryTests.test_market_recheck_class_replacement_cannot_disable_final_verification -v
```

RED: Exit 1; Ran 1 test in 16.190s; FAILED (failures=1); `AssertionError: ValueError not raised`.
GREEN after capturing W1 selection/proof method dependencies: Exit 0; Ran 1 test in 7.898s; OK.

## Final verification

The first complete 20-day focused policy run finished with exit 1:
`Ran 23 tests in 2428.164s` / `FAILED (errors=2)` (21 passed).

1. `test_genuine_all_member_evidence_reaches_complete_results`: fixture market
   rows retained the calendar-only `is_open` field by copying the entire base row
   from `document_wire`. W1 correctly raised `ValueError: market row shape is invalid`
   at formal_policy_market.py:699. The fixture has now been corrected to copy only
   the five visibility fields before adding explicit market fields.
2. `test_proofs_reject_construction_copy_shadowing_and_cross_batch_composition`:
   W3 finalization holds `_metric_batch_guard`'s `BEGIN IMMEDIATE`; the required
   F2 `.recheck()` calls financial.select → policy feature select → another
   `_metric_batch_guard` whose finalize issues `BEGIN IMMEDIATE` on a second
   connection. SQLite correctly raises `OperationalError: database is locked`,
   wrapped as `ValueError: metric batch database guard unavailable`. This is a
   predecessor nesting-interface gap, raised with the controller for a minimal
   approved seam. The required F2 final recheck will not be skipped or weakened.

The range-store compatibility run remains active; final acceptance is pending.

Two superseded focused attempts used the required policy-only command above.
Both were interrupted during `test_genuine_all_member_evidence_reaches_complete_results`
while still CPU-active in genuine producer/currentness work. The first began at
00:33:30 local, and the second at 00:41:38; both were stopped shortly before the
clean 00:45:01 restart (approximately 11 minutes and 3 minutes respectively;
no unittest elapsed/count summary was produced). The first had four preceding
tests pass and an ambiguous-configuration test helper error (`entry_id` was
incorrectly treated as a field of the raw config). That test helper was corrected
to create a distinct signed config with the same binding key. The second had all
five preceding tests pass. Neither interruption is reported as GREEN.

The fixture inherited a 400-calendar-day request cap. The controller approved
bounding only PolicyRuntimeFixture's signed synthetic cap to 20 days. This keeps
real signed configurations, raw receipts and all rechecks. Production range
configuration/semantics are unchanged. Before the clean replacement run,
`Get-Process python` returned no Python process; no superseded runner remained.

## Self-review and concerns

The ownership seam uses the original private range record validator, compares the exact owner Store and verifier, returns only None, and mints/exposes no authority. The W3 publication closure retains source/dependency methods, genuine F2/F3/W1 selections, all nine signed role bytes, and an independent shared publication state. Child eligibility includes a closure-owned parent link and owning batch hash. Callback parameters cannot be supplied through the public API. Cleanup failures are caught outside the guard context and revoke prepared proofs.

The policy-only run starting 00:45:01 and range-store compatibility run starting
00:45:54 overlapped. Both use isolated per-test TemporaryDirectory roots and only
temporary databases/raw stores. No third run will be started before both finish.
The final mandated compatibility command will run alone on unchanged files.

`git diff --check` exited 0. Git emitted only the repository's LF-to-CRLF notices.

## Checkpoint file hashes

SHA-256 hashes (will be reconfirmed at handoff):

| File | SHA-256 |
| --- | --- |
| ashare_pipeline/formal_policy_repository.py | 251CB8EE9AE7352831DC4D84ED168E91AFF279E3076E497DC9742003950A1CC4 |
| tests/test_formal_policy_repository.py | 53735819436CA66AEBADEE052B5AD85735D6269D4C3802E1B2E5C79B333CC7DD |
| tests/test_formal_policy_batch_guards.py | 3C38148CDD46FFBE95238D1886955F147DE4C25E4EEF594D7E9DA54CB8293AAD |
| tests/formal_policy_runtime_fixtures.py | 388F8A0E9205DF0FA7F1DA2278CDCDBF2430D6F153D731E0F6FC66F988E7FA40 |
| ashare_pipeline/formal_range_store.py | FF7563E615FD3A13E261C82F929B9E2A100ADCEFDBD20A068C1FDCD3BAB130B3 |
| ashare_pipeline/formal_range_source.py | 7AB8BE5A0B5649D6B8A9E71A87A1122971583834BEFD5ECA5AF118167753ED6D |
| tests/test_formal_range_store.py | 87F756566693E699687BDF8730F428C0224D99C984F7C0CB09BBDB2E3B0BC177 |

## Attack and lifecycle coverage at this checkpoint

Policy repository tests cover exact ordered three-member enumeration with
pending securities retained; genuine all-member producer evidence; unknown
membership producing no decisions; absent frozen universe; forged scoring and
policy registry objects; same-root foreign range/Context stores; foreign signed
root; assigned member with unpublished provider versus unknown membership;
proof construction, copying, object.__new__, instance shadowing, class-method
replacement, pure dictionary qualification and cross-batch composition;
entry/reader replacement; missing and ambiguous source configurations; whole
feature/Context graph replacement; copied/forged repository; and wrong provider
security, template and freeze identities.

Batch guard tests cover changing security two after financial evidence for
security one was read; initially absent industry becoming present; database
commit during preparation; equal-leading Context ambiguity; raw bytes changing
without database writes; signed source bytes replacing the current configuration;
unpublished captured proofs and no writer reservation during mint preparation;
captured decision/result revocation; swallowed reentrant provider publication;
and failures in inner or outer observer cleanup followed by successful recovery.

Range seam test covers genuine same-Store acceptance, cross-Store rejection,
verifier mismatch, object.__new__, ordinary copy, and unrelated object rejection.

## Additional self-review findings queued after active runs

1. Bind each private proof record to its exact minted class, and add a RED/GREEN
   regression against relabeling `__class__` between equal-layout proof types.
2. Capture W1/range module calculation bindings, not only repository class
   methods; explicitly attack a replaced W1 `evaluate_window`. Also capture W2's
   imported module aliases and the consumed `copy.deepcopy` operation.
3. The existing cleanup attacks force real rollback errors by closing an actual
   SQLite observer. Add a literal `close()`-throws test using a test-only wrapper
   around only the guard observer, delegating all real reads and rollback.

These are not waived. They will be implemented and verified before final handoff;
the active checkpoint runs are intentionally left unchanged in the meantime.

## Recovery from 18c45b31caf4f968de99d9513ed22c67cfffa08d

The recovery began with a clean worktree/index and the exact checkpoint HEAD.
The plan W3, amended brief and this report were read before task edits. The
already-recorded initial W3 RED above was retained and was not repeated. No
Git write, dependency installation, production data, network, scoring or pool
operation was performed.

The exact-owner nested metric guard test was added first in
`tests/test_formal_metric_batch_guard.py`. It exercises a genuine provider and
StateStore under an outer finalization, requires successful same-owner nested
finalization, and rejects mismatched Store/provider plus double use. Command:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_metric_batch_guard.OwnedProviderGuardTests.test_exact_owner_nested_guard_reuses_finalization_and_rejects_other_owners -v
```

RED: exit 1, 1 test, 1.889s, ERROR: SQLite `database is locked` from the
conflicting second `BEGIN IMMEDIATE`. After adding closure-private, exact-thread
reuse of the outer observer, epoch and writer exclusion, the same command was
GREEN: exit 0, 1 test, 0.563s, OK. No second observer/writer is opened for the
exact nesting; foreign owner paths fail closed. The existing swallowed provider
publication test remains in the metric guard module.

The queued self-review tests were then added to the W3 test files. Command:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_repository.PolicyRepositoryTests.test_relabeling_a_minted_proof_class_cannot_change_its_authority tests.test_formal_policy_repository.PolicyRepositoryTests.test_calculation_and_deepcopy_dependencies_cannot_be_replaced tests.test_formal_policy_batch_guards.PolicyBatchGuardTests.test_literal_observer_close_failure_revokes_published_children -v
```

RED: exit 1, 3 tests, 31.047s, 5 expected assertion failures: the minted proof
accepted equal-layout `__class__` relabeling, and replacement of W1
`evaluate_window`, range `_digest`, W2's `copy` alias, and its consumed
`copy.deepcopy` went undetected. The literal `close()`-throws regression already
passed, proving the existing outer BaseException handler revokes children on
that cleanup failure. After binding every proof record to its exact minted class
and capturing the calculation/alias/deepcopy dependencies, the same command was
GREEN: exit 0, 3 tests, 18.103s, OK.

Narrow predecessor compatibility command:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_metric_batch_guard -v
```

Exit 0, 16 tests, 221.264s, OK. This covers the pre-existing reentrant
publication, database write, rollback failure and recovery regressions as well
as exact-owner nesting.

The genuine populated W3 regression was run on the recovered code with the
new nested guard (before the independent self-review dependency captures were
loaded in that process):

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_repository.PolicyRepositoryTests.test_genuine_all_member_evidence_reaches_complete_results -v
```

Exit 0, 1 test, 1659.048s, OK. All three frozen members acquired genuine
industry/state/F2/W1 evidence and reached complete policy results while every
selection was rechecked, including under the final writer exclusion. The
subsequent required focused and four-module gates use fresh processes with all
final code changes.

Required focused W3 GREEN command (fresh process with all recovery edits):

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_repository tests.test_formal_policy_batch_guards -v
```

Exit 0, 26 tests, 2254.051s, OK. This includes the genuine populated
three-security path, exact-child and dependency attacks, first-to-second
security mutation, missing-to-present evidence, source/database changes,
swallowed publication, and both observer cleanup failure forms. No test failed
or errored. The mandated four-module compatibility command follows next and
is run alone on unchanged implementation files.

Required four-module compatibility command (run after the focused W3 GREEN,
alone on unchanged implementation files):

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_repository tests.test_formal_policy_batch_guards tests.test_formal_metric_batch_guard tests.test_formal_metric_engine -v
```

Exit 0, 60 tests, 2902.336s, OK. This contains the same 26 W3 cases, all 16
metric guard cases, and 18 metric engine cases. There were zero failures and
zero errors. No project-wide suite was started, per the brief.

## Final recovery self-review and file integrity

Final `git rev-parse HEAD` remained
`18c45b31caf4f968de99d9513ed22c67cfffa08d`. `git status --short` and
`git diff --name-only` showed only these five modified tracked paths, all in
the nine-path brief whitelist: `ashare_pipeline/formal_metric_batch_guard.py`,
`ashare_pipeline/formal_policy_repository.py`,
`tests/test_formal_metric_batch_guard.py`,
`tests/test_formal_policy_batch_guards.py`, and
`tests/test_formal_policy_repository.py`. The four other whitelisted paths
remain at the recovery checkpoint. No data, SQLite/WAL/SHM, history/progress,
scoring or pool path was changed or staged. `git diff --check` exited 0; Git
printed only LF-to-CRLF working-copy notices. No commit or push was made.

The nested guard only reuses an active finalization on the exact owning thread,
provider and StateStore; it reuses the outer observer and writer reservation,
checks provider epoch/finalizing and database epoch, and never opens a second
observer for exact nesting. The outer finalization still performs all W3
F2/F3/W1/context and signed-source rechecks. Reentrant provider publication
still invalidates the epoch even if its inner rejection is swallowed. The
literal close-throws test delegates real SQL reads and rollback, then raises
from the observer's `close()`; all captured W3 proofs remain revoked and a
subsequent batch succeeds. Proof records now bind to their exact minted class.
W1/range calculation bindings and W2's `copy` alias and consumed `deepcopy`
operation are included in the entry dependency check.

Final SHA-256 (recomputed after both mandated gates):

| Brief whitelist path | SHA-256 |
| --- | --- |
| `ashare_pipeline/formal_policy_repository.py` | `8BC8563F06BCF706EE4E289D3C7AE2B68817C4D6241CB3AE8B98D1765DB6FAD2` |
| `tests/test_formal_policy_repository.py` | `476DFEBF881E2DCBD04BF6CDE9EFA9E7CC85FEEF4D5A96FA16576B9BA2E92150` |
| `tests/test_formal_policy_batch_guards.py` | `53E42C751E2DC8F2A826E4C182200A5F91EF3B2889800C65710BDE22F66EDF86` |
| `tests/formal_policy_runtime_fixtures.py` | `FB5A4D6C342D81BEF011FCDC97EFB525755CD8ED91BEECD5A64E709079119F5D` |
| `ashare_pipeline/formal_range_store.py` | `FF7563E615FD3A13E261C82F929B9E2A100ADCEFDBD20A068C1FDCD3BAB130B3` |
| `ashare_pipeline/formal_range_source.py` | `7AB8BE5A0B5649D6B8A9E71A87A1122971583834BEFD5ECA5AF118167753ED6D` |
| `tests/test_formal_range_store.py` | `87F756566693E699687BDF8730F428C0224D99C984F7C0CB09BBDB2E3B0BC177` |
| `ashare_pipeline/formal_metric_batch_guard.py` | `7795386B93294B60215C49A80A75DAFF6F2B05ED120795A7B67A257784988ECD` |
| `tests/test_formal_metric_batch_guard.py` | `49CF372711B51DA5A6859FA91ABBE0135640E5CEB62F70D1EBE0FD760CA0F129` |

Concerns: no known failing regression within the required W3 and four-module
scope. The populated evidence is genuine temporary fixture production, not
production network data. Controller acceptance and Git writes remain pending.
