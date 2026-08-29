# Task 4 Review Package

## Spec

Authoritative requirements: `task-4-brief.md`, `PLAN.md`, `SCORING_SPEC_V2.md`, the complete `data-analytics:build-report` skill, its `specifications/technical-report.md`, and shared `src/analytics-app-core.md`.

## Review scope

- `ashare_pipeline/reporting.py` — `4A8848C6603A08CF37756C6A25FBDA679D7ACC94DF79B459BE673B4E6F0D1759`
- `tests/test_reporting.py` — `47413C67D61F6C46CBEC6D37B4C345566C7A4247268154278E7F983ED84DB991`
- `task-4-report.md` — `FA9684F2B5D1A585278DD202A3AE41467FA905725C1E22EF3A9C3A493457E2A5`

## Implementer evidence

Reported: 14/14 Task 4 tests pass; canonical validator returned `ok=true`; 14 blocks and 5 bounded datasets; no network and no HTML packaging. Controller will independently generate and validate a real artifact after pilot data.

## Review focus

Read-only review. Fully read the skill and required references yourself, then check:

1. exact canonical top-level/manifest/snapshot/source structure and portable HTML compatibility;
2. report title match, technical audience section order, one peer section per markdown block, partial/access notices prominent;
3. every quantitative claim/card/table has correct source provenance, definitions, units and safe bounded rows;
4. no fabricated zeros or metrics; explicit distinction among universe size, disclosure coverage, core-field completeness, prefilter, formal score and formal pools;
5. V2 weights total 100, four user display grades and risk direction are correct, governance/event gates and industry templates are not flattened;
6. no credentials, local absolute paths, raw full-market rows or unverified investment claims;
7. deterministic output and tests genuinely cover the brief, including status-shape variants and missing data.

Classify Critical/Important/Minor with file/line citations. `Approved` only with no Critical/Important. Do not edit, rerun tests, package HTML, or access the network.
