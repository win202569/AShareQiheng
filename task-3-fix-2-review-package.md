# Task 3 Fix Round 2

Reviewer verdict after round 1: three Important items remain. Apply this narrow TDD fix to Task 3 only.

1. Restore source circuit from cached job evidence. If a same-day leased-miss job has structured `error.classification == 'blocked'`, return that trigger's truthful cached state/reason and open the source circuit; no later task from that source may call the network and it must be reported circuit-open. Add the exact disclosure-blocked then performance-not-called rerun test.
2. Add an explicit `PREFILTER_RULESET_HASH` derived from the prefilter metric/weight/percentile/candidate rules. Put it in `prefilter.json` validity/input fingerprint independently of `CURATION_RULESET_HASH` and formal `RULESET_HASH`. A prefilter-only rule version change with identical source snapshots must rebuild the candidate artifact; test it.
3. Make suspended 2026-08-31 evidence reproducible from approved Task 2 raw fields. Controller policy: an active-trading row requires nonempty raw `close`; a suspended row (`tradestatus='0'`) may use nonempty raw `preclose` as `effective_close`, labelled `suspended_preclose`, and must retain the exact raw record hash plus deterministic transformation version. If both close/preclose are absent, block. Do not require derived fields inside the raw FetchBatch. Tests must construct real Task 2 daily shapes only and verify tampering/hash/universe/date/duplicate protections remain.
4. Re-run Task3 + full regressions, update `task-3-report.md`, and do not modify other tasks or access network.
