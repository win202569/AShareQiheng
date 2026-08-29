# Task 3 Review Package

## Spec

Authoritative requirements: `task-3-brief.md`, `PLAN.md`, `SCORING_SPEC_V2.md`; expected Task 2 adapter contract is in `task-2-brief.md`. Task 2 is currently in a separate fix round, so identify integration assumptions explicitly without editing either task.

## Review scope

- `ashare_pipeline/curation.py` — `B8ACDD090B7668BD95BEAC491E71362BDD85C3E624E66B9919FDA2DB2264C58C`
- `ashare_pipeline/scoring.py` — `4B7CEE98B8241B03D763AACA4FBEB4B5EE5E37DE14E6341E62EC2B21423B1AAC`
- `ashare_pipeline/orchestrator.py` — `760DC83AC88F92537B8131464A44455A5A4DF4B2B480BF0B1ED0AA129CA28C76`
- `tests/test_curation.py` — `F47FF5CEC83125C9F72A52407AB94378F19B575260B5CD024264F70CC7EC5553`
- `tests/test_scoring.py` — `99853CB9DECF96AD1ECAC9EF4DED3F6F42B9B8D02F4449F587CF0E61CF7E26BC`
- `tests/test_orchestrator.py` — `1780B62A3385D05EA5E0BACBE5AD9CC9C04A165D159ADF333DF87D9CF379E23F`
- `task-3-report.md` — `A2AE0BB429CB20B0A4E4D7BA8EBE24BC4FF3F2DFBE07623AD8712ADBF43C2B0E`

## Implementer evidence

Reported: 17 Task 3 tests passed; then-current Task 1/2 regressions passed; compileall passed; no network use. Controller will rerun after reviews and Task 2 integration.

## Review focus

Read-only review. Check every brief requirement and, in particular:

1. exact Shanghai/Shenzhen A-share universe rules, status/type handling, ST preservation, exchange/board classification and code normalization;
2. performance field mapping against Task 2's stable output, deterministic latest-date dedupe and no future announcement leakage;
3. quality denominators, core-field completeness, 95% boundary, after-cutoff semantics, market evidence and no misleading zeros;
4. percentile/tie/missing/industry-fallback math, selection determinism, industry representation and prefilter cap;
5. CLI argument order, offline no-network, bootstrap/incremental behavior, content-hash idempotency, job state transitions, circuit breaker and status atomicity;
6. finalize cannot freeze a prefilter, cannot change provisional on failure, and uses timezone-aware strict cutoff;
7. tests prove behavior and do not hide integration gaps.

Classify findings Critical/Important/Minor with file/line citations. Return `Approved` only if no Critical/Important finding remains. Do not edit files or rerun tests.
