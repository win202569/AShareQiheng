# W4 fix round 1 independent review — `bba7e0f`

Base: `9452b31`. Reviewed the original W4 review, the updated implementation report, the complete fix diff, and the changed test lines. This was a read-only code review; no tests were rerun and no Git state was changed. The report records the two affected tests as 1/158.178s and 1/697.729s, both OK.

## Original finding status

- **Important — closed.** `tests/test_formal_policy_integration.py:134-151` captures complete pre-correction SQLite rows for the old `formal_source_snapshot`, its linked `formal_collection_task`, `formal_task_snapshot_receipt`, and `formal_context_fact`. Lines 160-179 reread the same identities after `g2` and compare every column through `dict(sqlite3.Row)`, with explicit existence checks. Line 158 independently checks the old raw bytes. An in-place rewrite or deletion of these old rows now fails the test.
- **Minor — closed.** `tests/test_formal_policy_integration.py:184-188` resolves both `content_path` and `manifest_path` with `strict=True` and requires containment in the owning fixture root. The helper is applied to the persisted first page at line 204, recovered final page at line 230, and uninterrupted control final page at line 231. Each fixture root was already asserted to be its own `TemporaryDirectory`; missing, redirected, or escaping files fail.

## New issues

- Critical: none.
- Important: none.
- Minor: none.

The diff changes only `tests/test_formal_policy_integration.py`; `git diff --check 9452b31 bba7e0f` returned clean. The new assertions do not alter producer behavior or weaken the existing canonical-result and raw-byte checks.

## Task quality

**Approved.** Both review findings are fully closed within W4's test-only scope. The two focused passing test results are sufficient for this fix round; the prior long regression was not repeated.
