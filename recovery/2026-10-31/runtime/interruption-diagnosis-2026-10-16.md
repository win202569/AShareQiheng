# Long-running verification interruption investigation

Date: 2026-10-16. User-facing timezone: Asia/Tbilisi (+04:00).
Scope: local verification infrastructure only; no scoring/authentication changes.

## Observed evidence

- Source checkpoint remains caff956aaac170ff6c46f017bfccfcf5d065e885.
- Journal: D:/Projects/AShareQiheng/.tmp/grouped-checkpoint-caff956/journal.jsonl.
- Three groups have finish records, exit_code=0, one original test each,
  no failures/errors/skips. The fourth attempt, 16a6c83af6b340ddbbe8565a5cca2851,
  has no finish record. Last heartbeat: 2026-10-16T15:09:59.312115+00:00.
- At investigation, authoritative Win32_Process enumeration found no Python
  verification supervisor or worker. Both levels disappeared; this is not an
  observed unittest failure or an observed normal runner exit.
- Application events 1000/1001/1002 in 19:05-19:30 local yielded no matching
  crash/hang records. System power/reboot/resource checks in that interval
  yielded no matching events. Absence is not proof that no external kill occurred.
- Desktop log:
  C:/Users/Lenovo/AppData/Local/Codex/Logs/2026/10/16/codex-desktop-e0ea7786-4ddf-4802-9138-f99961e7f095-20000-t0-i1-000017-0.log
  line 15049: 2026-10-16T15:09:01.879Z thread/unsubscribe for this chat.
  line 15050: 2026-10-16T15:09:01.882Z inactive_thread_unsubscribed for
  01a07fc8-e7a7-7b90-9ef4-0a7a58f30880, window not visible.
  This precedes the final heartbeat by approximately 57 seconds. Correlation,
  not proof of an exact termination callback or a confirmed product defect.
- A read-only Win32 probe in an elevated command execution context reported
  IsProcessInJob=true; QueryInformationJobObject ExtendedLimitInformation flags
  0x3000: KILL_ON_JOB_CLOSE=true, BREAKAWAY_OK=false,
  SILENT_BREAKAWAY_OK=true. A normal subprocess probe also reported in-job=true.
  The probe was run after the incident, not inside the lost worker. It cannot
  establish the lost worker's full nested job chain or the termination initiator.

## Working diagnosis

The verification process tree is vulnerable to its managed command-host
lifecycle. Chat inactivity/host cleanup is the strongest current hypothesis for
this incident. A precise native/app root cause is NOT proven. Historical Python
0xC0000005 incidents are separate and must not be conflated with this loss.

The current append-only journal and locks preserve validated completed groups
but cannot keep a supervisor alive if its entire host-owned tree is removed.
Ordinary same-host restarts do not solve that lifecycle vulnerability.

## Proposed bounded remediation (requires operating-mode approval)

Use one explicitly named, current-user, non-elevated Windows one-shot task to
host the existing unchanged grouped runner outside the chat terminal lifecycle.
No recurring schedule, machine-start trigger, registry/security-policy changes,
or unlimited auto-retry. Keep source identity, locks, all signature/evidence
checks, original assertions and result reuse checks unchanged. Preserve old
journals. Fail closed on source drift or failing tests.

First verify with a short harmless job: distinct external parentage, completion
after the initiating command ends, explicit exit record, duplicate-launch refusal,
and task cleanup. Then inventory the existing runner and resume only pending
groups. Independent-host survival across chat inactivity remains an operational
acceptance check, not something to claim from a launch acknowledgment.

Status: no new OS task registered; no new full queue launched; no code, HEAD,
Python installation, system policy, stock data, or database changed.

## Approved remediation and observed validation

User explicitly approved the operating-mode change. Added runtime-only wrapper
independent_verification.ps1 and real process tests test_independent_task.py.
Tests first failed because the wrapper did not exist; after implementation,
both success=0 and deliberate child failure=7 are preserved in process exit
and status.json. Two tests pass (2.848 seconds). An initial sandbox test run
had temporary-directory permission errors; authoritative current-user rerun
with the project temp root supplied the clean red/green evidence. Output log
encoding is explicitly UTF-8. Existing status evidence is not overwritten.

Registered AShareQiheng-Independent-Smoke-20261016 under current user Lenovo,
Interactive logon / Limited run level / zero triggers / zero restart count /
MultipleInstances=IgnoreNew. Startup command returned; a separate command
observed the smoke PowerShell PID22084 parent3484 (svchost.exe), and its Python
probe continued. Probe ran 17:07:19-17:07:39 UTC, emitted PROBE_FINISHED,
status exit_code=0 and scheduler LastTaskResult=0 / Ready. Removed ONLY the
completed smoke task; preserved .tmp/independent-smoke-20261016 logs.
This proves completion after initiating command return, not yet indefinite
survival across desktop inactivity, logoff, sleep, reboot, or resource failure.

Registered and started AShareQiheng-Verification-caff956 using the same limited
current-user/no-trigger/no-retry settings. No persistent service or security
policy change. Execution time limit disabled for this explicitly started task;
no automatic restart. The task runs only when manually dispatched and should
be unregistered after its terminal result is inspected. Interactive logon means
it is not a guarantee against user logoff/reboot.

At 17:08:21 UTC, unchanged runner identity 744a2816... confirmed 2028 tests /
171 groups / 168 pending. Resumed fourth group as attempt
01592ce281604b439a16462fa5dada35. Task PID28308 parent3484(svchost), runner
PIDs15892/16004 and worker9708/29980 observed alive. Wrapper status/output:
.tmp/independent-verification-caff956/status.json and output.log.
Runner's existing immutable identity, journal, locks, checks, tests and source
were not changed. No full acceptance or root-cause certainty claimed.
