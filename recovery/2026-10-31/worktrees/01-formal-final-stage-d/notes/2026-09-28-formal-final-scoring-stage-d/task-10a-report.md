# Task 10A report

Status: DONE

Commit: `d575027` — `feat: add signed test-root computation gate`

Implemented an exact-purpose authenticated computation gate for genuine signed
v2 ten-role test roots while preserving every official/release/coverage gate.
Public computation and authenticated loader boundaries default to
`expected_purpose="official"`; test-root execution requires an explicit exact
`"test"` value. Purpose is sealed through Context, feature, metric, policy,
range, valuation, market selection/tickets/rechecks, D1 preparation, caches and
recovery evidence.

Security fixes covered mixed purpose, approval on test roots, cross-root/copy/
forgery/mutation, canonical parser replacement, official release-ineligible
feature registries, method replacement, purpose replay, and implicit
manifest-driven downgrade.

TDD evidence included independent RED reproductions for the missing authenticated
API, implicit purpose propagation, parser substitution, official feature release
bypass, policy/range/adapter loaders, market planning/selection, and genuine
full-chain fixture propagation.

Final evidence:

- genuine signed test-root Stage A/B/C/D1: 1/1 PASS in 1585.369s;
- final focused purpose/trust/registry/market/release regressions: 54/54 PASS in
  42.653s;
- scoring registry regression: 25/25 PASS in 70.404s;
- independent trust-boundary review: no Critical or Important findings,
  Ready: Yes;
- staged/committed files: Python code and tests only; no data, SQLite, WAL/SHM,
  report, progress or plan files.

Known limitation: the genuine fixture remains CPU-heavy; this is measured work,
not an orphan-process or deadlock condition. Task 11 owns broader 20/23-member
performance diagnostics.
