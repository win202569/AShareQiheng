# V9 local verification checkpoint — 2026-10-10

This is a local code/test checkpoint, not a publishable release or whole-project
acceptance. No data, SQLite files, sidecars, runtime progress or logs are included.

## Producer-backed replay (previous revision)

At revision `3fa64ce45abe9a5e199cd158d217e48d37404d78`, the real
20-member signed fixture passed `tests.test_formal_release_live_equivalence`:
1 test OK in 14706.756 seconds. Four calculation artifacts matched exactly,
V8 remained unchanged and no V9 publication authority was created. This is a
test fixture, not production full-domain coverage, and does not validate a
later revision or cross-process restart.

## Workspace batching

Per-file Git hashing became bounded batches, preserving path-specific clean
filters, text/CRLF/ident handling, two independent hash passes and existing
status/index/revision/type/race checks. No currently-valid verdict is cached.
An oversized individual path is rejected before filesystem/hash access.

The batch test first failed (8 hash commands instead of 2); the oversized-path
test first failed with the old tracked-type error. Both passed after their
respective changes. Real required clean-filter equivalence was verified before
the batching patch was accepted by safety review.

Latest workspace trust run: 18 tests OK in 21.917 seconds. Diagnostic only:
same 41-file fixture, scalar 5.360 seconds versus batch 0.944 seconds; hash
processes 82 to 4. This does not estimate full-pipeline acceleration.

## Calendar purpose propagation

The date-only resolver omitted required purpose arguments. It now explicitly
uses `official` at registry load, fact enumeration, binding resolution and final
selection. Public interfaces, source/binding verification, temporal checks and
the seven-dimensional score rules are unchanged. Signed test roots remain
rejected by the official approval/purpose boundary.

The original calendar and SZ date-only tests failed before the fix, then both
passed (2 tests in 101.642 seconds). Corrected complete Context repository run:
48 tests OK in 640.273 seconds. An earlier imported fixture mistakenly used
`test_only` instead of `test` and produced one error; that stale run is not the
final result. Independent scoped reviews found no critical/important findings;
the workspace review's single-path budget issue is addressed here.

## Remaining verification

Whole-project discovery stopped without a final summary after 529 OK lines
and 37 FAIL/ERROR lines (including subtests). Exit cause is unknown. A reproduced
official coverage error rejected dirty production source before hashing; a
separate calendar failure led to the purpose fix above. Do not classify all 37
as one cause or claim whole-project success. After this checkpoint, rerun the
failed groups at a fixed clean-source revision with separate logs and exit
statuses. Public validator/12 release gates and publication remain unfinished.

Runtime evidence stays outside Git under `D:/Projects/AShareQiheng/.tmp/`:
`v9-live-equivalence.log`, `workspace-batch-full-regression.log`,
`workspace-batch-boundary-regression.log`, `calendar-purpose-regression-v2.log`.
