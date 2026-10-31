# C4 Perf 3: single policy source authentication per read

Scope: `formal_policy_registry.py`, `formal_range_contract.py`, `formal_valuation_adapter_contract.py`, and their dedicated tests. The existing C4 changes in the adapter file and all other dirty files were left intact and excluded from this commit.

## Change

- Adapter `sources` reads the policy owner's authenticated wire once, then compares root and role hashes locally. The adapter's own record still reruns source authentication on each public read.
- Policy owner exposes a private authenticated source reader. It runs `proof_record` once and returns the original bundle, scoring, feature identities and policy canonical bytes. It is guarded as an owner entry point.
- A range snapshot uses that read. When the passed bundle and scoring are the policy's original objects, the policy proof has already verified both; otherwise it independently verifies the passed bundle and scoring. Every snapshot still checks actual manifest and child bytes and hashes.

## Red/green profile evidence

For two adapter `require_official` calls, policy `proof_record` fell from 14 to 2 (7 to 1 per call). For two range `require_current` snapshots, policy `proof_record` stayed 2; top-level scoring fingerprints fell from 4 to 2, and feature fingerprints from 6 to 4. Counts were measured by `sys.setprofile` on real signed in-memory graphs. Repeated public calls still reauthenticate.

## Verification

`D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_formal_valuation_adapter_contract tests.test_formal_range_contract tests.test_formal_policy_registry`: 91 tests passed. Added checks cover replacement of private readers after warmup and an equal-root, distinct-object scoring graph; existing checks cover root/child/feature/scoring mutation and forged inputs. No long store, C4, or full suite was run.

`git diff --check` returned exit 0. The report is in `.superpowers/sdd`, which is ignored by Git.
