# Task 6C source-bootstrap review package

Base: `e149556a2aea080cd72172eed8922a43a0d3aa11`

## Requirements

Read `task-6c-source-bootstrap-brief.md` and
`task-6c-source-bootstrap-report.md` in this directory. The change may touch
only `ashare_pipeline/formal_sources.py` and `tests/test_formal_sources.py`.
It must preserve an unbound bootstrap config and reject security-bearing
requests, while permitting a validated explicit request exchange. No default
or mutable exchange state, no worker workaround, and no weakened snapshot
identity may be introduced.

## Candidate production diff

```diff
@@ FormalOfficialSourceAdapter._preflight
-        if config.bootstrap_calendar and (
-            request.exchange is not None or request.security_id is not None
-        ):
+        if config.bootstrap_calendar and request.security_id is not None:
             raise FormalTerminalSourceError(
-                "bootstrap calendar request must be a global request without an exchange"
+                "bootstrap calendar request must not carry a security_id"
             )
```

## Candidate test delta

- same adapter sequentially fetches SZ, SH, SZ, and None under one unbound
  bootstrap config; checks request/fetch/parser exchange and unique request
  fingerprints;
- exchange placeholder is rendered only for non-null explicit exchanges;
- security-bearing requests reject before transport/parser;
- scoped bootstrap config remains rejected;
- snapshot replay rejects exchange substitution before parser invocation.

The reviewer must read the live uncommitted diff in the worktree for exact
test assertions and report a spec-compliance verdict plus a task-quality
verdict, with Critical/Important/Minor findings and line references.
