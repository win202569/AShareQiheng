# P1 — bounded feature-registry parse reuse

APPROVED DESIGN, CLEARED FOR DISPATCH. User selected performance first after R4
final100 and approved the short in-chat design below. R4 final100 is TERMINAL:
100 tests /7067.269s, OK, exit0; root verified full output and frozen hashes.
BASE: ba0def62a4ffe45cb5e3bee41537ea1b79ff6de0. This is a bounded supplemental task, not a new architecture or
another Stage B scoring feature. No separate formal plan/spec is required.

## Approved outcome and hard constraints

Remove redundant parsing of identical previously authenticated feature-registry
bytes. Continue authenticating each live registry object, exact field types and
values, original slots/formulas, canonical bytes and hash on every read. Do not
cache a current-validity verdict, skip signature/root checks, or authorize a
different object merely because its bytes/hash match. Every registry load still
validates input and signature/root eligibility before original-owner minting.

Public interfaces, canonical bytes/hashes, formula semantics, score weights,
freeze2026-08-31T07:00:00+00:00, evidence thresholds and v1 policy rules unchanged.
Returned template slots must remain fresh detached values, including nested
formulas; mutating one result cannot corrupt later results or private cached data.
Mutating registry.slots or its nested formulas must still invalidate that registry.
No global cross-object/root cache, public cache API, new dependency, cache toggle,
dynamic registration or proof construction shortcut. Preserve trusted private
Python runtime boundary; do not redesign defenses against arbitrary interpreter
or private helper replacement. Quantified-event policy gap stays explicit.

## Exact ownership

- ashare_pipeline/formal_feature_contract.py
- tests/test_formal_feature_contract.py

All other production/test files are read-only. Controller alone stages/commits.
Do not touch user data, SQLite/WAL/SHM, progress/history, tmpj4zv9_fq, source
configuration files, production signatures, main branch or remote state. No real
HTTP, crawling, scoring, stock pools, installs or subagents. Work only in
D:/Projects/AShareQiheng/.worktrees/formal-v3-implementation with project Python
D:/Projects/AShareQiheng/.venv/Scripts/python.exe. Edit via apply_patch.

## Evidence and existing owner boundary

Read B1 task-R4-runtime-diagnosis.md and task-R4-tiny-profile.log under sibling
2026-09-12-formal-policy-stage-b1-range-foundation workspace. Root measured only
RangeSourceFixture construction plus one first_calendar_request: 76,092,272calls,
422 full registry parses,41.591s wall with profiler overhead. This is a bounded
measurement, not a production throughput baseline. Repeated graph checks invoke
scoring _feature_slots, whose sensitive field reads and five template selections
reparse the entire registry repeatedly.

Current feature owner has records containing weak identity + frozen _Seal.
fingerprint validates all exact public fields and serializes every original
slot/formula before comparison with initial slot_bytes. Keep this check intact.
require_verified then redundantly reparses sealed canonical bytes already checked
against the originally validated input. slots_for_template validates again and
reparses all templates to return fresh matching slots. Restrict optimization to
these repeated parse steps, not object fingerprinting or other graph owners.

Prefer owner-private immutable per-template slot wire bytes prepared from the
original successfully loaded registry and its sealed snapshot. Read only after
require_verified succeeds; reconstruct fresh selected slot/formula values using
existing strict value parsing, rather than returning shared cached objects or
registry.slots. Preserve sorted order and every declared template. A different
equally hashed object remains independently authenticated, never cache-admitted.
If a smaller equivalent implementation satisfies all constraints, explain it.
If this requires other production files/public APIs, stop and report the specific
obstacle before expanding scope.

Read-only design audit confirmed this shape against the existing Formula/Slot
layouts. Keep the loader's actual full parser and per-read SHA-256. No new repeated
signature verification or altered root-eligibility policy: those remain at their
existing boundaries. Sensitive field fingerprinting must still serialize live
slots/formulas and reject EqualitySpoof, not compare permissive raw tuples.
Cache belongs to each weakref-bound record; its lifetime follows that registry.
The benchmark is exactly fixture construction plus first_calendar_request, not
an easier substituted helper. The audited minimal approach needs only two files.

## Test-first acceptance

Use real registry fixtures/signatures and literal hand-checked slot/formula wires.
First demonstrate RED that repeated authenticated property/template reads reparse
the full registry. Instrument the real parser with a forwarding counter/spy;
never stub acceptance or replace verification with a no-op. Assert both exact
returned values and the absence of additional full-registry parse calls after
successful construction. Do not assert fragile wall-time thresholds.

Cover behavior:
- Repeated valid reads avoid full-registry reparsing; malformed initial bytes and
  rejected/non-True signatures still fail on each load.
- Fresh template-returned slots and nested formulas cannot poison later reads,
  other template results, registry.slots or another genuine registry instance.
- Registry scalar, canonical-byte/hash, slot and nested-formula mutations after
  successful prior reads remain rejected, including equality-spoof objects.
- Forged, copied and wrong-root objects do not gain authority from matching bytes;
  original release-eligibility behavior remains unchanged.
- Each template's order, types, slot/formula wires and hashes match the original
  contract; unknown template still fails.

Run focused RED then GREEN and the complete owned test module. Use existing
tamper/forgery/root/equality-spoof tests, adding only missing behavioral coverage.
Command: python -m unittest tests.test_formal_feature_contract -v.

After focused GREEN, repeat root's same in-memory fixture+first-request cProfile
measurement once, with no competing test workload. Record raw output/call counts,
wall/CPU time and scope; compare parse count and hotspot work rather than claiming
a universal speedup. No hypothetical result or arbitrary performance target.
Also report the per-read require_verified and outer _derive_graph/source_record
call counts (baseline286/7/3 in that exact probe): the optimization must not obtain
speed by removing current-authority checks. Explain any call-flow difference;
these baseline diagnostics are not brittle wall-time unit-test assertions.

Freeze for controller checkpoint and independent spec/quality review before the
expensive final project verification. Correct review findings with scoped tests.
After clean review and controller resume, run the project's existing full command
once: python -m unittest discover -s tests -p "test_*.py" -v.
Persist complete incremental output, process/session identity and terminal counts/
exit. Report all failures by name, including unrelated ones. No partial suite or
profiling measurement establishes completion. R4's pre-optimization100 is baseline
evidence only, not proof of optimized code. Do not launch duplicate suites.

## Handoff report

Report at task-P1-report.md in this directory: current checkpoint first, exact
changed paths, real RED/GREEN commands/output, fresh file hashes, before/after
measurement, self-review and concerns. Controller owns Git writes/master ledger;
preserve artifacts. Return concise DONE/DONE_WITH_CONCERNS/NEEDS_CONTEXT/BLOCKED,
actual tests and concerns. Never perform unrelated fixes or publish new scores.
