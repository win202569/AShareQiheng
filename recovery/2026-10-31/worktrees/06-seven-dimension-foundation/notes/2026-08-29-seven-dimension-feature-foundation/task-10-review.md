# Task 10 Independent Review

Verdict: **APPROVED**

Reviewed range: `7fb2211365d43af62445e083817174965dbd6af7..322f1a7ead1d3389c588edf3bb2bb94aa76c78b0`.

## Resolution of prior findings

### Curated `records_hash` validation

Resolved in `ashare_pipeline/deep_worker.py:150-156`.

Both schema-v2 curated inputs now require `records_hash`. The value must be a valid SHA-256 digest and must match the canonical hash of the complete normalized `records` list. The prefilter and performance paths use the same fail-closed validation.

The added tests independently cover missing, malformed, and well-formed-but-mismatched hashes for both documents.

### Existing statement-job identity binding

Resolved in `ashare_pipeline/deep_worker.py:339-375`.

An existing job is reused only when its kind matches the requested `JobSpec` and its `security_id`, `dataset`, `report_period`, and `refresh_date` exactly match the requested payload and therefore the requested idempotency-key identity. The exact payload-key check and current request-version validation remain in force. Only `candidate_set_hash` and `performance_input_hash` may retain their first-enqueued values across a same-day candidate-context change.

The added tests inject well-formed mismatches for kind and all four immutable payload fields. Each case raises before atomic completion, verifies that the parent is not succeeded, and does not create requested follow-up rows. The existing same-day candidate-change test continues to verify preservation of the first-enqueued audit hashes.

## Verification considered

- Focused review tests: 11 passed, exit 0.
- Task 10 suite: 23 passed, exit 0.
- Task 5 state-store regression: 59 passed, exit 0.
- Full regression: 269 passed, exit 0.
- `py_compile` and `git diff --check`: exit 0.

No remaining blocking or non-blocking findings were identified in the requested re-review scope.
