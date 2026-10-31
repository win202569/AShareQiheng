# Final trust-boundary scoped review

## Per-finding verdicts

1. **ADDRESSED — current candidate context is authenticated at progress.** `ashare_pipeline/orchestrator.py:1073-1083` first verifies the artifact, exact stored header/children, and canonical evidence. It then reads the current frozen industry from `context.industries[security_id]`, resolves the expected registered template, and requires both the exact source-industry name and template id to match at `ashare_pipeline/orchestrator.py:1084-1092`. The row is marked seen before validation at `ashare_pipeline/orchestrator.py:1068-1072`, so a mismatch fails closed without fallback. Existing contract validation also authenticates the bundle's registered name/template/version relationship at `ashare_pipeline/feature_contract.py:301-316`. The negative substitution and matching-context production-path controls are at `tests/test_orchestrator.py:1279-1366`.

2. **ADDRESSED — balance-equation readiness is recomputed at the DB trust boundary.** The single shared production authority, including complete-triplet applicability, common-unit handling, `max(1000.0, 0.001 * abs(assets))` tolerance, and strict `>` mismatch semantics, is defined at `ashare_pipeline/financial_schema.py:382-410`. The builder consumes it at `ashare_pipeline/financial_features.py:780-787`. StateStore reconstructs the exact authenticated observed raw facts at `ashare_pipeline/state_store.py:878-941`, recomputes and compares the advertised marker in both directions at `ashare_pipeline/state_store.py:943-953`, and requires a genuine mismatch to block the bundle and every financial dimension at `ashare_pipeline/state_store.py:954-963`. This validation runs before both the existing-row/idempotent branch and first insert at `ashare_pipeline/state_store.py:1017-1035`, and verified progress calls the same validator at `ashare_pipeline/orchestrator.py:1080-1083`. Focused tests cover first persistence, ready/partial omission, balanced blocked addition, idempotent reuse, progress/no-fallback, exact tolerance, and missing-triplet positives at `tests/test_financial_features.py:969-981`, `tests/test_state_store.py:1017-1130`, and `tests/test_orchestrator.py:1368-1427`.

3. **ADDRESSED — future-as-of bundles cannot enter or suppress earlier progress.** The SQL visibility predicate `as_of_utc<=?` is applied in the query before iteration/newest-per-security selection at `ashare_pipeline/orchestrator.py:1055-1067`; only the already-filtered rows can enter the seen set at `ashare_pipeline/orchestrator.py:1068-1072`. Bundle timestamps are canonicalized to UTC at `ashare_pipeline/feature_contract.py:76-85,465`, and the cutoff is converted to UTC at `ashare_pipeline/orchestrator.py:1016`, so equality remains visible and canonical text ordering is temporal. Future-only, future-suppressor, and exact-cutoff behavior are covered at `tests/test_orchestrator.py:1429-1503`.

Implementation-report verification: the report records the pre-edit base, a production-path RED command and expected failures for all three findings at `final-trust-boundary-fix-report.md:13-43`; final focused GREEN at `final-trust-boundary-fix-report.md:71-80`; affected GREEN at `final-trust-boundary-fix-report.md:83-94`; full GREEN at `final-trust-boundary-fix-report.md:96-107`; staged full GREEN and staged scope at `final-trust-boundary-fix-report.md:109-129`; and fresh committed-tree focused/affected/full results at `final-trust-boundary-fix-report.md:131-137`.

## New Breakage in Fix Diff

- Critical: **0**
- Important: **0**
- Minor: **0**
- Scoped fix integrable: **Yes**. The three authorized trust-boundary repairs are coherent, fail closed at the required boundaries, and introduce no new Critical/Important breakage.

## Out-of-Scope Observations

- **Non-blocking process-evidence discrepancy:** `final-trust-boundary-fix-report.md:18-29` labels `FFFFFFFFF` as the exact RED progress output for a nine-method command that includes two positive-control methods. The current positive controls at `tests/test_state_store.py:1094-1130` and `tests/test_orchestrator.py:1279-1321` are expected to pass against the pre-fix behavior, while the three cases inside `tests/test_state_store.py:1017-1053` report as separate failing subtests. Standard `unittest` progress output would therefore include two dots in addition to the nine failure markers. The report contains substantive pre-production RED failure descriptions and complete GREEN coverage, but its claimed exact RED progress line is not internally exact as written. This documentation/provenance issue does not alter the scoped code verdict or integrability.
- Worktree-local untracked controller/test temporary directories remain present and unstaged. They are outside the frozen fix diff and do not affect the committed tree.

Fix round: All findings addressed, no new Critical/Important breakage
