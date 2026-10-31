# P1 implementation report — bounded feature-registry parse reuse

## Current checkpoint

**ACCEPTED — independent review was clean at checkpoint
`21746b2990b24c79b93521dc75f5d8e7e4a7f176`; a later target-lifetime-only
diagnostic full-project run passed 1403 tests with 4 unchanged Windows symlink
privilege skips.** The earlier non-green run remains historical evidence; no P1
implementation expansion or lease/test repair was made.

Evidence note: one session poll payload between native capture sequences
16 and 18 was consumed, but its append failed with a Windows sandbox-helper IPC
timeout before the payload was exposed or persisted. It has not been reconstructed.
The completed PowerShell transcript also omitted the bulk native unittest stream,
including that payload, while retaining the wrapper metadata, traceback tail, and
complete terminal summary. Intermediate native evidence is therefore incomplete
at that one disclosed capture point. This capture issue is separate from the
unittest ERROR and did not affect the running process.

- Status: ACCEPTED_AFTER_DIAGNOSTIC_FULL_SUITE
- Base inspected: `ba0def62a4ffe45cb5e3bee41537ea1b79ff6de0`
- Current reviewed checkpoint/HEAD:
  `21746b2990b24c79b93521dc75f5d8e7e4a7f176`
- Owned module before review: 22/22 passing, exit 0, pristine unittest output.
- Same-operation profile: exit 0; full feature-registry parses fell from 422 to 1.
- Authority-flow counts were preserved exactly at feature `require_verified` 286,
  `_derive_graph` 7, and `source_record` 3.
- No commit/stage/merge/push was performed. No network, production data, scoring,
  signatures, SQLite state, installs, or other source/test files were touched.

## Changed paths

Production/test ownership:

- `ashare_pipeline/formal_feature_contract.py`
- `tests/test_formal_feature_contract.py`

Named task artifact:

- `.superpowers/sdd/2026-09-12-formal-policy-stage-b/task-P1-report.md`
- `.superpowers/sdd/2026-09-12-formal-policy-stage-b/task-P1-focused-red.log`
- `.superpowers/sdd/2026-09-12-formal-policy-stage-b/task-P1-focused-green.log`
- `.superpowers/sdd/2026-09-12-formal-policy-stage-b/task-P1-owned-module.log`
- `.superpowers/sdd/2026-09-12-formal-policy-stage-b/task-P1-profile.log`
- `.superpowers/sdd/2026-09-12-formal-policy-stage-b/task-P1-full-suite.log`
- `.superpowers/sdd/2026-09-12-formal-policy-stage-b/task-P1-full-suite-native.log`
- `.superpowers/sdd/2026-09-12-formal-policy-stage-b/task-P1-full-suite-native-chronological.log`

The pre-existing modification to
`docs/superpowers/plans/2026-09-12-formal-policy-stage-b.md` was preserved and not
touched.

## Implementation

Each weakref-bound verified registry record now owns an immutable tuple mapping
every declared template to that registry's canonical per-slot wire bytes. The
bytes are prepared from the original successfully parsed slots and the sealed
slot-byte snapshot during construction.

`require_verified` still runs for every sensitive read and template selection. It
still fingerprints all exact live public fields, serializes every live slot and
nested formula for comparison with the initial sealed bytes, enforces record/object
identity, compares every sealed field, and recomputes SHA-256 over the sealed
canonical registry bytes. It no longer reparses those already authenticated,
byte-identical whole-registry bytes.

After `require_verified` succeeds, `slots_for_template` reads only the calling
registry record's immutable slot wires and reconstructs each selected slot via the
existing canonical JSON loader and strict `FormalFeatureSlot.from_dict` /
`FormulaNode.from_dict` validation. Every result, including every nested formula,
is newly allocated. The signed loader's full parser, signature result check, root
validation, eligibility policy, canonical bytes, hashes, public API, and formulas
are unchanged.

## TDD evidence

### RED

Command (project Python; no competing workload):

```text
D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_feature_contract.FormalFeatureContractTests.test_registry_reuses_authenticated_parse_and_returns_fresh_template_slots -v
```

Captured process/output:

```text
SHELL_PID=36972
test_registry_reuses_authenticated_parse_and_returns_fresh_template_slots (tests.test_formal_feature_contract.FormalFeatureContractTests.test_registry_reuses_authenticated_parse_and_returns_fresh_template_slots) ... FAIL

======================================================================
FAIL: test_registry_reuses_authenticated_parse_and_returns_fresh_template_slots (tests.test_formal_feature_contract.FormalFeatureContractTests.test_registry_reuses_authenticated_parse_and_returns_fresh_template_slots)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation\tests\test_formal_feature_contract.py", line 304, in test_registry_reuses_authenticated_parse_and_returns_fresh_template_slots
    self.assertEqual(parse_registry.call_count, 1)
AssertionError: 24 != 1

----------------------------------------------------------------------
Ran 1 test in 0.008s

FAILED (failures=1)
```

This was the expected behavioral failure: the real loader parsed once, then
authenticated property/template reads called the real full-registry parser 23
additional times. The spy forwarded to the actual parser; signature and root
acceptance were not stubbed.

Complete original terminal output is preserved in `task-P1-focused-red.log`.

### Focused GREEN

Command:

```text
D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_feature_contract.FormalFeatureContractTests.test_registry_reuses_authenticated_parse_and_returns_fresh_template_slots tests.test_formal_feature_contract.FormalFeatureContractTests.test_registry_cached_slot_wires_are_detached_per_registry_and_read tests.test_formal_feature_contract.FormalFeatureContractTests.test_registry_parse_reuse_does_not_cache_load_acceptance_or_live_validity -v
```

Captured process/output:

```text
SHELL_PID=41828
test_registry_reuses_authenticated_parse_and_returns_fresh_template_slots (...) ... ok
test_registry_cached_slot_wires_are_detached_per_registry_and_read (...) ... ok
test_registry_parse_reuse_does_not_cache_load_acceptance_or_live_validity (...) ... ok

----------------------------------------------------------------------
Ran 3 tests in 0.007s

OK
```

The new coverage uses real registry bytes, real manifest fixtures, real signature
verifier behavior, literal hand-checked all-template slot/formula wires, and a
forwarding parser spy. It covers one full parse after construction; exact returned
order/types/wires/hash; unknown templates; fresh slots and nested formulas across
reads and genuine registry instances; repeated malformed/rejected/non-True loads;
post-read scalar/canonical-byte/hash/slot/nested-formula mutation including equality
spoofs; copied-object forgery; and wrong-root non-eligibility. A final self-review
assertion added explicit top-level live-slot equality-spoof coverage; it exercised
the already-preserved fingerprint behavior and required no production amendment.
Complete original terminal output is preserved in `task-P1-focused-green.log`.

### Complete owned module (current tree)

Command:

```text
D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_feature_contract -v
```

Captured terminal summary:

```text
SHELL_PID=40572
[all 22 named tests reported "ok"]

----------------------------------------------------------------------
Ran 22 tests in 0.025s

OK
```

Exit code: 0. No warnings or unexpected output from unittest.
Complete original terminal output, including all 22 test names, is preserved in
`task-P1-owned-module.log`.

## Same-operation before/after profile

Scope in both measurements: only in-memory `RangeSourceFixture()` construction
plus one
`fixture.source.first_calendar_request("2026-08-31T07:00:00+00:00")`; no fetch,
worker, database, network, or competing test workload. cProfile overhead is
included. The before data is the accepted R4 `task-R4-tiny-profile.log`; the after
probe was run exactly once after GREEN (shell PID 37116, exit 0).

| Metric | R4 before | P1 after |
|---|---:|---:|
| Wall seconds | 41.591 | 9.559 |
| CPU seconds | 36.141 | 8.891 |
| Profiler seconds | 40.825 | 9.516 |
| Total calls | 76,092,272 | 25,150,521 |
| Primitive calls | 74,623,706 | 24,548,755 |
| Feature `_parse_registry_bytes` | 422 / 29.820s cumulative | 1 / 0.023s cumulative |
| Feature `require_verified` | 286 / 30.568s cumulative | 286 / 7.025s cumulative |
| `_derive_graph` | 7 / 33.912s cumulative | 7 / 8.433s cumulative |
| `source_record` | 3 / 14.642s cumulative | 3 / 3.831s cumulative |

Raw after header and required call details:

```text
SHELL_PID=37116
SCOPE: in-memory fixture construction plus one first-calendar request; no fetch, worker, DB or network
WALL_SECONDS: 9.559
CPU_SECONDS: 8.891
         25150521 function calls (24548755 primitive calls) in 9.516 seconds

   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
        7    0.004    0.001    8.433    1.205 formal_range_contract.py:138(_derive_graph)
       25    0.002    0.000    8.426    0.337 formal_scoring_registry.py:516(require_official)
       26    0.002    0.000    8.045    0.309 formal_scoring_registry.py:186(_feature_slots)
      286    0.006    0.000    7.025    0.025 formal_feature_contract.py:566(require_verified)
      287    0.025    0.000    7.014    0.024 formal_feature_contract.py:531(fingerprint)
        1    0.000    0.000    7.013    7.013 formal_range_source.py:940(first_calendar_request)
      135    0.004    0.000    4.925    0.036 formal_feature_contract.py:622(slots_for_template)
        3    0.000    0.000    3.831    1.277 formal_range_source.py:853(source_record)
        1    0.000    0.000    2.543    2.543 formal_range_fixtures.py:215(__init__)

REQUIRED_CALL_DETAILS:
        7    0.004    0.001    8.433    1.205 formal_range_contract.py:138(_derive_graph)
      286    0.006    0.000    7.025    0.025 formal_feature_contract.py:566(require_verified)
        3    0.000    0.000    3.831    1.277 formal_range_source.py:853(source_record)
        1    0.000    0.000    0.023    0.023 formal_feature_contract.py:390(_parse_registry_bytes)
```

The required 286/7/3 authority-check counts are unchanged, so the reduction did
not come from removing current-authority checks. The one remaining full parse is
the signed feature-registry loader. The 135 template selections remain and now
strictly reconstruct only selected cached slot wires; live fingerprint
serialization and per-read SHA-256 also remain. These bounded profiler timings
demonstrate the intended hotspot reduction in this fixture only and are not a
universal production throughput claim.

Complete original profiler output, including all top-25 rows and the selected
counter section, is preserved in `task-P1-profile.log`.

## Full-project suite

The sole controller-authorized full-project command was run once after the clean
independent review:

```text
D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest discover -s tests -p "test_*.py" -v
```

- Unified exec session: `17770`
- PowerShell PID: `42476`
- Computing project-Python PID: `42300`
- Launcher project-Python PID: `42304`
- Start UTC: `2026-09-19T12:19:15.9575900Z`
- End UTC: `2026-09-19T13:34:26.3134613Z`
- Wrapper elapsed: `4510.287s`
- Unittest result: `Ran 1403 tests in 4508.303s`
- Terminal status: `FAILED (errors=1, skipped=4)`
- Exit code: `1`

The sole error was:

```text
test_formal_context_repository.ContextIntegrationTests.test_date_only_uses_calendar_provenance_without_recursive_self_lookup
ValueError: formal snapshot task lease expired or ownership changed
```

The complete terminal traceback ran from
`tests/test_formal_context_repository.py:629` through its helper at line 236,
`ashare_pipeline/state_store.py:1980`,
`ashare_pipeline/formal_context_repository.py:243` and line 65, to
`ashare_pipeline/state_store.py:3156`. It does not enter either P1-owned file.
No causal claim is made from that fact alone. Per the brief, the implementation
was frozen immediately after the non-green suite and the failure was not rerun,
debugged, or fixed.

The four skips were Windows symlink-privilege skips (`WinError 1314`):

- `test_formal_feature_store.FormalFeatureStoreTests.test_symlinked_bundle_is_rejected_when_platform_allows_symlinks`
- `test_formal_snapshot_store.FormalSnapshotStoreTests.test_existing_content_symlink_outside_store_is_rejected`
- `test_formal_snapshot_store.FormalSnapshotStoreTests.test_existing_manifest_symlink_outside_store_is_rejected`
- `test_formal_snapshot_store.FormalSnapshotStoreTests.test_validate_stored_snapshot_rejects_symlink_escape_when_available`

Expected argparse diagnostics were printed twice by
`test_orchestrator.OrchestratorTestCase.test_deep_parser_accepts_limit_bounds_and_rejects_outside`
for invalid `--limit` values; the test itself reported `ok`. No other unexpected
noise or warning was observed.

Evidence artifacts:

- `task-P1-full-suite.log` is the original completed PowerShell transcript. It
  contains start/command metadata plus the traceback tail, count, timing, status,
  exit marker, and end time, but PowerShell omitted most native unittest lines
  and the beginning of the traceback while the process was running.
- `task-P1-full-suite-native.log` is the unchanged original raw PTY capture,
  newest-first, SHA-256
  `ff7f5ff7accfe1e6bf642fe417869c0d4f472618a08c7c00be7d840a6360d568`.
- `task-P1-full-suite-native-chronological.log` is the mechanical chronological
  normalization of the same 64 received nonempty chunks, strictly ordered from
  capture sequence 1 through 88 with empty polls omitted, SHA-256
  `a42d1792a63fce472f06243ecd47824a3869c1384226e2f8c4f4356621a08e66`.
  It explicitly records the unreconstructed sequence-17 capture gap. Initial
  chunk IDs `5a5a0e` and `3d0606` were recorded before sequence numbers were
  embedded in the JSON and are preserved as sequences 1 and 2 respectively.
- The completed transcript SHA-256 is
  `496b854ae28bc73f9a95dcb86579985664480d87442e943fb56987906c64176a`.

## Hashes and hygiene

Initial SHA-256 at base:

```text
d994852ca7217d9e49634ecc50908160d7421689267486cc5edd765526a98bcf  ashare_pipeline/formal_feature_contract.py
fc74f2063906b547aad7e9de2d51feec3512590283e4b06ffdc86f77a7129383  tests/test_formal_feature_contract.py
```

Fresh current SHA-256:

```text
f55b0b58ba9619ac2050e4952d938b79e882c5e7f1b0f637cfa6483a5a890f7c  ashare_pipeline/formal_feature_contract.py
646070781fd64c4834b5c88e9f235e7b662b2cc42a570a77ed3f0c138c947e89  tests/test_formal_feature_contract.py
```

The same two hashes were recomputed after the terminal full-suite result and were
identical. `git diff --check --` over both owned paths exited 0, and neither owned
path had a staged or unstaged diff at reviewed checkpoint HEAD
`21746b2990b24c79b93521dc75f5d8e7e4a7f176`. `git status --short` showed only the
pre-existing modified plan file named above. The controller created the reviewed
checkpoint; this implementer performed no Git write.

`git diff --check -- ashare_pipeline/formal_feature_contract.py
tests/test_formal_feature_contract.py` exited 0. Git emitted only the checkout's
LF-to-CRLF conversion notices; it found no whitespace errors.

## Self-review

- Completeness: checked every acceptance item against the new and existing tests;
  the only missing explicit case found was top-level live-slot equality spoof after
  cache use, which was added and passed in the final owned-module run.
- Security/authority: no verdict, signature result, root eligibility, registry
  object, or live slot/formula object is cached. A separately loaded equal-byte
  registry is independently parsed, signature-checked, root-checked, and recorded.
- Freshness: returned slots/formulas are reconstructed from immutable private bytes
  on each selection; mutations cannot reach later results, public `registry.slots`,
  or another registry record.
- Scope: only the two owned code/test files were changed as implementation; all
  other task writes are the named report/log artifacts above. Public interfaces
  and wire/hash/formula semantics are unchanged.
- Mutation check: removing loader parsing, removing per-read fingerprint/SHA,
  returning shared values, admitting copied objects, accepting invalid signatures,
  or selecting a wrong/unknown template is covered by a failing test.

## Concerns

The sole full-project suite was non-green because the context-integration test
named above encountered an expired or changed formal-snapshot lease. The owned
module remained green within that same suite, its reviewed hashes were unchanged,
and the traceback did not enter an owned file, but the full-project gate is still
failed and no root cause is asserted without an authorized diagnostic run.

Full intermediate native output is unavailable for exactly one consumed poll
payload (capture sequence 17), and PowerShell did not duplicate the bulk native
stream into its transcript. The missing payload was not reconstructed. The final
traceback is complete in native capture sequence 88; the aggregate result, exit
code, and timings are complete in both that terminal capture and the PowerShell
transcript.
