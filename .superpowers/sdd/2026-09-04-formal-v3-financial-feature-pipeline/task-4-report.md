# Task 4 implementation report

Scope: only `ashare_pipeline/formal_financial_features.py` and
`tests/test_formal_financial_features.py` are tracked/staged. This report stays ignored.

## TDD evidence

Initial tests were added before the production module. Command:
`D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_formal_financial_features -v`
returned exit 1, one import error: `ModuleNotFoundError: No module named 'ashare_pipeline.formal_financial_features'`.

Initial GREEN: 14 tests passed after implementing selection, quarter derivation,
history windows, safe formula evaluation, and mandatory root-bound builder.
An initial fixture mismatch (single-template child cannot be release eligible)
was corrected by explicitly signing all five test templates. Instant facts use
the accepted balance/instant Task 2 contract; OTHER facts have null period_start.

Expanded security/edge coverage: 30 focused tests. Includes complete version
ordering, late source-update exclusion, capture acceptance, same-ID/different-wire
conflicts, raw/quarter seals, missing quarter prerequisites, unit/year isolation,
exact current annual/quarter windows, complete arithmetic evidence/reliability,
economic unit table, protected root/child eligibility, semantic key ambiguity,
issue blocking, hash order/generation/future-candidate behavior, detached snapshots,
and generators mutating facts/root/child inputs.

Plan-required regression command:
`D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_formal_financial_features tests.test_formal_financial_schema tests.test_formal_feature_contract tests.test_formal_time tests.test_financial_features -v`
passed all 144 tests, zero skips, in 1.104s before final canonical-wire hardening.

`python -m py_compile ashare_pipeline/formal_financial_features.py tests/test_formal_financial_features.py` passed.
`git diff --check` passed. Staged diff check and final verification are recorded below.

## Decisions

- Quarter keys use global YYYYQn as explicitly clarified by controller.
- Exact formula dict cannot itself hold two equal keys; builder detects semantic
  collisions before constructing its evaluation map and propagates an ambiguous
  key set. Referencing formulas become missing; unrelated signed slots survive.
- Every selected fact is a detached sealed from_dict reconstruction. Root/child
  fields needed after caller issue iteration are copied immediately after seal and
  official checks. This prevents generator side effects from changing a validated
  feature input midway through construction.
- Root official status and child release eligibility are conjunctive. A matching
  sealed test root produces blocked slots even with a previously official child.
- Quarter error blockers remain on the bundle; selection/issue conflicts globally
  block slots as specified. History output is inventory, not score eligibility.

No network, data, SQLite, scoring, pool, or production registry changes.

## Final verification and commit

Final regression after canonical-wire hardening: same five-module unittest
command (without verbose flag) passed 144/144 tests, zero skips, in 1.065s.
Compilation passed again. `git diff --cached --check` passed; staged diff contained
exactly the two authorized files, 1,056 insertions. Initial commit:
`44b974a` — `feat: derive formal point-in-time financial features`.

Git index writes required the normal sandbox escalation; it succeeded. No other
files were staged. Implementation awaits independent controller review.

## Review fix: release-eligibility input identity

Independent review found blocked and derived bundles could share input_hash
when the same child bytes were loaded without/with the official root while
the builder received the same passed official root. Added a public-fixture
regression first: the exact focused test failed RED on equal hashes
`59cb89205a70497bc31258f98e299ff2243fbc9022c61335f6e07968e4b5bafc`.

The canonical input payload now contains `effective_release_eligible=eligible`,
using the same locally captured sealed conjunction that controls slot output.
The regression also proves input-order stability in both modes and equal hashes
for bound/unbound children when the passed test root makes both effectively false.

GREEN: focused module 31/31 tests passed in 0.156s; required five-module regression
145/145 passed in 0.999s, zero skips. py_compile, working and staged diff checks
passed. Commit `1eef9a6 fix: bind feature input hash to release eligibility`
changes exactly the two authorized files, 30 insertions.
