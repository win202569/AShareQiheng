# Task 4 Fix Round 1

Reviewer verdict: **Changes requested**. Apply TDD fixes to Task 4 only. Task 3 is also being repaired, so consume its documented fields defensively and add an integration test that builds a report from an actual `run_command(..., status)` payload when possible.

## Important fixes

1. Support the real Task 3 status contract. Infer/retain source safely when individual source batch rows omit it; consume and visibly summarize `curated.prefilter`, `source_errors`, `circuit_breakers`, `blocked_reasons`, and `next_actions`. Do not let failures sort out of the visible sample. Replace artificial test fixtures with at least one actual producer-shaped payload.
2. Correct canonical source definitions: `core_field_completeness` is the share of five required core cells present among disclosed companies; disclosed-universe coverage is unique disclosed eligible securities divided by eligible universe. Keep their 95% gates and denominators separate everywhere.
3. Enforce the one-source markdown rule. Split V2 method claims, pipeline status/pool claims, and mixed execution-timing/sensitivity claims into separate blocks with correct sourceId, or make source-free prose contain no quantitative claim. Every quantitative markdown statement must resolve to exactly one canonical source.
4. When source status is bounded to 25 rows, expose the full reviewed row count, shown count, truncation boolean and selection rule in the artifact/source metadata and reader-facing subtitle/note. Prioritize failed/blocked/retryable rows before success so truncation cannot hide failures.
5. Harden recursive sanitization for Windows drive/UNC paths, POSIX absolute paths (`/tmp`, `/mnt`, `/home`, `/Users`, `/Volumes`, etc.), credentials embedded in URLs, Bearer/Basic/API-key/password/token/secret forms including quoted JSON keys. Do not overclaim perfect secrecy: report that known sensitive patterns are redacted and raw inputs are excluded. Add adversarial tests.
6. Make lifecycle semantics input-driven. Before freeze, formal pool count is a factual 0 and snapshot is partial. For a proven final input, show final/ready and actual supplied strong/wait pool counts; if final evidence lacks counts, use null/unknown, not 0. For blocked after cutoff, remain partial/blocked with reasons and do not say “尚未到截止日”. Add pre-cutoff, post-cutoff blocked, and final tests.
7. Preserve canonical validator compatibility, bounded datasets and deterministic output. Update `task-4-report.md`; do not package HTML or access network.

## Acceptance

- Task 4 tests plus all existing regressions pass.
- Append red/green evidence and exact changed files.

## Submitted fix hashes

- `ashare_pipeline/reporting.py` — `70CF15F8F0B306D43C1516677224668D5529C4F9473D2867FA26BA584949F9AE`
- `tests/test_reporting.py` — `2C1005256BC6DAC78FF63D9EDD97000A954C0DD0445AAF54AEBA29F1CF2E0F49`
- `task-4-report.md` — `F8F77D334C1AD74E2E5E3986A1FC19F715841DAA97E30EFEC2291E29A89569F1`

Implementer reports 21/21 Task 4 tests and 106/106 full regressions passing; canonical validator accepts partial, blocked and ready examples. Re-review every original Important and new regressions; `Approved` only if no Critical/Important remains. Do not edit, rerun, package or access network.
