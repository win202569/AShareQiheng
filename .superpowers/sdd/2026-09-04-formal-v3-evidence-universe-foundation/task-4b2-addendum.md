# Task 4B2 addendum — adversarial lease rulings

This addendum is binding for Task 4B2 and supersedes only the narrow ambiguity below.

## Expired dependent with terminal prerequisite

An unexpired `leased` child remains protected from dependency resolution.  A child whose lease has expired is no longer an active lease holder.  Therefore, when a prerequisite is `terminal_failed` or `superseded`, `resolve_formal_task_dependencies()` must be able to terminal-fail that expired child atomically (clear lease/retry/result fields and use the existing deterministic prerequisite error), rather than leave it permanently unleaseable behind the formal lease predicate.  Sample the resolver's current time inside its writer transaction.  Do not rewrite a lease whose expiry is strictly after that sampled time.

Add regression coverage for: a terminal parent + live leased child (unchanged); the same child at exact/expired expiry (terminal-failed); and a subsequent lease attempt never returning it.

## Formal worker identity invariant

The fixed V5 schema/API fences mutations by `worker_id` and has no lease-incarnation token.  Exact stale-owner fencing therefore requires callers to supply a unique worker ID per lease-owning process/incarnation; a caller must not reuse the same `worker_id` across a prior expired claim and a new claim.  Do not make unsupported claims that same-ID ABA reuse is fenced.  Test takeovers with distinct worker IDs, validate nonempty string IDs, and document this input invariant in the Task 4B2 report/ledger for V6 worker design.

## Mandatory implementation checks

- Acquire `BEGIN IMMEDIATE` before sampling implicit time.
- Validate a candidate's canonical payload/hash before committing it as leased; a tampered row must remain byte-for-byte unchanged if leasing raises.
- Repeat full state/time/dependency eligibility in the lease CAS update.
- Use normalized UTC timestamps and `timedelta`, not float timestamp round trips.
- Renew/fail CAS must compare `lease_expires_at > now` at the final update; equality is lost ownership.
