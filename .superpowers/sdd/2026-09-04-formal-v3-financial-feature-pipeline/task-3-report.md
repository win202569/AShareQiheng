# V6 Task 3 report

## Scope and prerequisite

- Worktree: `D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation`
- Branch: `codex/formal-v3-implementation`
- Task 2 prerequisite: ACCEPTED at `9bc6fb7` per the SDD progress ledger.
- Tracked scope is restricted to the two formal feature modules and their two tests. No data, network, task, score, pool, SQLite, WAL, or SHM operation is performed.

## Initial RED — absent modules

Command:

`D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_formal_feature_contract tests.test_formal_feature_store -v`

Result: expected failure before production code. Both `_FailedTest` imports raised:

`ModuleNotFoundError: No module named 'ashare_pipeline.formal_feature_contract'`

The two production modules did not exist when RED was recorded.

## Focused RED/GREEN

- Initial RED: 2 import errors, both caused by the intentionally absent `ashare_pipeline.formal_feature_contract` module.
- Additional provenance RED: after adding the low-level registry-mutation regression, the focused test failed because a direct sensitive-field read did not revalidate the registry seal.
- GREEN: the focused Task 3 suite ran 24 tests successfully, with 1 Windows-only symlink case skipped because the test process lacked `SeCreateSymbolicLinkPrivilege` (`WinError 1314`).

## Final verification

- Four-file `py_compile`: exit 0.
- Required combined command: `python -m unittest tests.test_formal_feature_contract tests.test_formal_feature_store tests.test_feature_contract tests.test_snapshot_store -v`.
- Result: 60 tests run, 59 passed, 0 failed, 1 skipped (Windows symlink privilege unavailable).
- `git diff --cached --check`: clean before commit.
- Staged scope: exactly the two formal feature modules and their two test modules.

## Implementation summary

- Added the closed formula AST, signed formal registry loader, sealed evidence/value/bundle contracts, strict canonical JSON parsing, and release-eligibility binding.
- Added immutable content-addressed bundle/manifest storage with exclusive per-hash locks, conflict-safe publication, crash completion, path/link defenses, and verified reads.
- No production registry, template substitution, financial fetch, scoring, pool, SQLite, state, or network operation was performed.

## Commit

- Commit: `a8bca10` (`feat: add formal feature contract and storage`)
- Files: `ashare_pipeline/formal_feature_contract.py`, `ashare_pipeline/formal_feature_store.py`, `tests/test_formal_feature_contract.py`, `tests/test_formal_feature_store.py`.

## Residual platform note

- The link-substitution regression is present but skipped on this Windows host because symbolic-link creation was denied. The store's link/junction rejection remains exercised by the implementation path and the test runs on hosts where link creation is permitted.

## Review fix round 1 — RED

Focused contract command covered five new reproductions. Result before production changes: 5 tests run, 5 failures. The failures proved that equality-spoofed formula `items`, evidence refresh-generation resealing, value resealing, bundle resealing, and populated forged-bundle initialization were all accepted.

Focused store command covered three publication/path reproductions. Result before production changes: 3 tests run, 3 failures. The failures proved that `os.link` was not used, injected link failure was not observed, and a directory replacement race wrote a bundle into the temporary external junction target.

## Review fix round 1 — GREEN

- Removed the independent evidence/value/bundle `__post_init__` seal hooks. Their public direct initializers now reject any repeat or pre-populated initialization before changing an existing field, then seal exactly once.
- Formula binary/fact nodes now require an exact tuple before accepting empty `items`; registry mutation with an equality-spoof object fails closed.
- Replaced `os.replace` publication with hard-link no-clobber publication. `FileExistsError` independently reads and validates exact final bytes and SHA-256; conflicts are never overwritten. Owned part and lock files are removed through the pinned directory context.
- Added directory-chain binding for every write/read operation: POSIX uses `O_NOFOLLOW` directory descriptors and `dir_fd` operations; Windows holds `CreateFileW` handles for every ancestor with `OPEN_REPARSE_POINT`, rejects reparse attributes, permits read/write sharing needed for normal hard-link publication, and withholds delete sharing so the chain cannot be renamed or replaced while active.
- The Windows directory-replacement regression uses a real temporary junction target. It ran (not skipped), the rename/replacement was blocked by the held handles, and the external target remained empty.

Verification command:

`D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_formal_feature_contract tests.test_formal_feature_store tests.test_feature_contract tests.test_snapshot_store -v`

Result: 67 tests run, 66 passed, 0 failed, 1 skipped. The skipped case is the pre-existing direct file-symlink test requiring unavailable Windows symlink privilege; the junction directory-race test passed. Four-file `py_compile` exited 0. `git diff --check` reported no whitespace errors. Production/test sources contain no `os.replace` reference.

Bounded platform note: Windows Python has no `dir_fd` file API. The implementation therefore pins and reparse-checks the complete ancestor chain with native handles, then uses normal child path operations while those handles deny directory deletion/rename. This closes the reported directory replacement/junction race and preserves normal Windows writes; it is not a claim of general immunity to arbitrary same-process API hooking or kernel-level filesystem attacks.

Fix commit: `4a97f74` (`fix: harden formal feature provenance and storage`). Only the four Task 3 scoped files were committed.

## Review fix round 2 — secure missing-directory creation

RED command:

```text
D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_formal_feature_store.FormalFeatureStoreTests.test_missing_directory_creation_is_bound_to_verified_parent -v
```

RED output:

```text
test_missing_directory_creation_is_bound_to_verified_parent (tests.test_formal_feature_store.FormalFeatureStoreTests.test_missing_directory_creation_is_bound_to_verified_parent) ... FAIL

----------------------------------------------------------------------
Ran 1 test in 0.091s

FAILED (failures=1)
```

The failing assertion showed `external-target/data` had been created after the test replaced the unpinned store root with a temporary junction.

GREEN focused command/output:

```text
D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_formal_feature_store.FormalFeatureStoreTests.test_missing_directory_creation_is_bound_to_verified_parent -v

test_missing_directory_creation_is_bound_to_verified_parent (tests.test_formal_feature_store.FormalFeatureStoreTests.test_missing_directory_creation_is_bound_to_verified_parent) ... ok

----------------------------------------------------------------------
Ran 1 test in 0.011s

OK
```

Implementation: `_paths()` is now pure path construction. `write()` enters secure traversal with `create=True` before any root/descendant creation; `read_verified()` uses `create=False`. POSIX creates each missing component relative to its already pinned parent descriptor and immediately reopens it with `O_NOFOLLOW`. Windows pins each existing ancestor with `CreateFileW`; a missing component is created only while its parent handle denies rename/delete, then reopened with `OPEN_REPARSE_POINT` and rejected if it is a reparse point.

Final verification command/output:

```text
D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_formal_feature_contract tests.test_formal_feature_store tests.test_feature_contract tests.test_snapshot_store -v

----------------------------------------------------------------------
Ran 68 tests in 1.321s

OK (skipped=1)
```

The one skipped test remains the direct Windows file-symlink case requiring unavailable privilege; both Windows junction race tests executed and passed. The exact four-file `py_compile` command exited 0 with no output.

Fix round 2 commit: `d6d78bd` (`fix: secure formal feature directory creation`). Only `ashare_pipeline/formal_feature_store.py` and `tests/test_formal_feature_store.py` changed and were committed.

## Review fix round 3 — default TEMP verification RED

No `TEMP`/`TMP` override was supplied.

```text
Set-Location -LiteralPath 'D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation'; D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_formal_feature_store -v

----------------------------------------------------------------------
Ran 13 tests in 0.057s

FAILED (failures=6, errors=8)
```

Representative root-cause output:

```text
PermissionError: [WinError 5] Access is denied.

The above exception was the direct cause of the following exception:

ValueError: formal feature directory handle acquisition failed
```

All failing store cases were created beneath the process-global default Windows temp root under `C:\Users\Lenovo`. The restricted test token cannot acquire the required native handle for that ancestor; the production store correctly fails closed before store I/O. The same suite previously passed when its temporary roots were explicitly located inside the D-drive worktree. This round changes only test-root selection and does not relax pinning or path security.

GREEN change: `tests/test_formal_feature_store.py` now derives `PROJECT_TEST_TEMP_ROOT` from `Path(__file__).resolve().parents[1]` and creates every top-level and nested `TemporaryDirectory` under `.tmp/formal-feature-store-tests`. The primary storage test asserts that selected root explicitly. No production file changed.

Focused command/output, with no `TEMP` or `TMP` assignment:

```text
Set-Location -LiteralPath 'D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation'; D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_formal_feature_store -v

----------------------------------------------------------------------
Ran 13 tests in 0.175s

OK (skipped=1)
```

Required full command/output, with no `TEMP` or `TMP` assignment:

```text
Set-Location -LiteralPath 'D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation'; D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_formal_feature_contract tests.test_formal_feature_store tests.test_feature_contract tests.test_snapshot_store -v

----------------------------------------------------------------------
Ran 68 tests in 1.420s

OK (skipped=1)
```

Compile command/output:

```text
Set-Location -LiteralPath 'D:\Projects\AShareQiheng\.worktrees\formal-v3-implementation'; D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m py_compile ashare_pipeline/formal_feature_contract.py ashare_pipeline/formal_feature_store.py tests/test_formal_feature_contract.py tests/test_formal_feature_store.py

[exit 0; no output]
```

Fix round 3 commit: `df1cbc1` (`test: use secure project temp roots`). Only `tests/test_formal_feature_store.py` changed and was committed; production pinning/path behavior is unchanged.

## Review fix round 4 — POSIX capability-preserving race hook

Root cause: patching the shared module attribute `os.mkdir` replaces the builtin with a `MagicMock`; on POSIX, `_pin_posix_chain()` correctly checks the replacement against `os.supports_dir_fd` and fails before reaching the intended race injection. The test now creates a local copy of the capability set, adds the exact patched callable, and patches only that capability set for the duration of the race test. Production capability detection and store behavior are unchanged.

Capability evidence command output:

```text
mocked_mkdir_supported_before=False
mocked_mkdir_supported_after=True
```

A POSIX runtime was not available on this host (`wsl.exe --status` failed with `Wsl/EnumerateDistros/Service/E_ACCESSDENIED`), so the portable hook was verified structurally and the complete Windows behavior was rerun.

Focused command/output:

```text
D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_formal_feature_store -v

----------------------------------------------------------------------
Ran 13 tests in 0.178s

OK (skipped=1)
```

Required full command/output:

```text
D:\Projects\AShareQiheng\.venv\Scripts\python.exe -m unittest tests.test_formal_feature_contract tests.test_formal_feature_store tests.test_feature_contract tests.test_snapshot_store -v

----------------------------------------------------------------------
Ran 68 tests in 1.226s

OK (skipped=1)
```

The four-file `py_compile` command exited 0 with no output. `git diff --check` reported no whitespace errors.

Fix round 4 commit: `f121506` (`test: preserve POSIX mkdir capability in race`). Only `tests/test_formal_feature_store.py` changed and was committed.
