# Task 2 Fix Round 3

Reviewer verdict after round 2: no remaining Critical; two Important acceptance items remain. Apply this narrow TDD fix to Task 2 only.

1. On same-day rerun, when the current existing job is the terminal `SourceBlocked` trigger, add its source to the circuit **and return the real `_job_result` for that trigger** (terminal status, structured classification and reason). Only later same-source jobs are `blocked_by_circuit`. Test exact status and cause retention as well as zero remote calls.
2. Add a real pilot-kind lease lifecycle test using `pilot_fetch:<task+as-of>`: before lease expiry rerun reports running and does not call the source; after expiry `_run_online` recovers, re-leases the same job, performs the fetch and completes it. Do not use an unrelated kind.
3. Add a weekend/holiday calendar test (for example Sunday 2026-08-30 with 8/29–30 non-trading and 8/28 trading) proving latest completed trading date is 8/28 and daily query uses 8/28.
4. Address the two Minor points if safe: verify a reused calendar snapshot against its recorded content hash before using its rows, and include safe `task_key`/job id in batch summaries so daily/financial outputs remain attributable without raw requests.
5. Re-run Task 1+2 and append evidence to `task-2-report.md`. Do not modify Task 3/4 or access network.

## Submitted fix hashes

- `ashare_pipeline/pilot.py` — `5B65BDA685CC1C9852A87EC4713733BABFEC5DA9C96BCD225A8E4504EE1261F3`
- `tests/test_pilot.py` — `1C85176178BE08A4B1A7E19A0BB4FA49D61A2352BC0FC110D8BC28EA4DC43C87`
- `task-2-report.md` — `3BFEB87C54DB04669A9551E2CC9A560E87F8D408FDF54998D526B3771FAFB34F`

Implementer reports 54/54 Task 1+2 tests passing. Re-review only the remaining two Important and two Minor points plus new regressions; `Approved` requires no Critical/Important. Do not edit or rerun tests.
