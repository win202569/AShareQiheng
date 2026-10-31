# W4 integration report — GREEN

Base: `fd648b97125c7d381347605b820b6099ba39c4e4` (clean at start).

## Scope and implementation

Only `tests/test_formal_policy_integration.py` (new) and `tests/formal_policy_runtime_fixtures.py` (modified) are changed among tracked paths. No production code or DDL was changed; no Git add, commit or push was run.

The fixture now permits a complete seven-member synthetic frozen universe, an unresolved member, member-specific noncyclic applicability, financial evidence intentionally absent for selected members, and a signed ST state override. It reuses a current verified calendar observation only when the *full* genuine request serialization, request fingerprint, refresh generation, complete date coverage, and exact day rows agree. It does not suppress errors or use an exchange-only or in-memory `seen` marker. For each template binding it still calls the real `FormalPolicyMarketRepository.select_calendar`, producing a binding-specific current coverage proof; market requests and observations are then produced for each security through real R4 source/store/worker and an in-memory transport.

## Integration scenarios

1. Seven frozen securities across BJ/SH/SZ cover all five templates, a second noncyclic bank, a signed ST veto with missing financial evidence, and an unknown industry/template member. The test checks exact order and count, template-only decisions, noncyclic `not_applicable`, retained pending requirements and veto, and that no Stage C score, pool, or eligibility output appears. Bank and broker on SH share one genuine calendar task/snapshot/receipt/transport fetch, but have distinct binding and coverage hashes with shared underlying lineage. Crossing the bank proof into broker market planning raises an error.
2. A minimal genuine pending-evidence graph is built twice and must have identical canonical bytes and hash. A new signed Context `g2` changes the batch identity while the old signed raw snapshot bytes and old/new snapshot rows remain; an old selection fails current recheck, while the earlier published batch remains verifiable. No seven-security data population is needed for this invariant.
3. A real paginated R4 range worker persists page one and its receipt before the successor task is enqueued. After recreating the worker/store, `resume` consumes that durable verified page with no duplicate first transport call and completes page two. An uninterrupted control produces the same canonical request/document and raw bytes. The full proof hash is intentionally not compared across distinct temporary roots because it includes raw paths and task identities. A frozen test clock prevents host-speed-dependent lease expiration without weakening persistence or receipt revalidation.

Every scenario uses `TemporaryDirectory` with explicit path assertions and exact `_CapturingRangeTransport` type assertions. `socket.create_connection` is patched to fail on any attempted real HTTP. No production data, real network, crawler, scoring pass or pool selection is touched.

## RED and correction record

The first integration attempt failed 3/3 immediately because an isolation assertion referred to nonexistent `FormalRangeStore.root`; it was changed to inspect the fixture DB/raw paths. The next uninterrupted integration attempt ended with **3 errors, 0 failures, 0 skips, 5681.511 seconds, exit 1**: a duplicate same-natural-key/different-payload SH calendar enqueue, a test SQL typo (`formal_snapshot` instead of `formal_source_snapshot`), and a 60-second producer lease expiring during this host's long signature validation. These were accurate initial RED observations, not deliberately manufactured failures.

The controller's read-only root-cause audit concluded that the store's fail-closed collision is correct; no production or V7 DDL expansion was authorized. The fixture was corrected to reuse the existing current observation by full request/receipt identity and to obtain per-binding proofs. The SQL table name was corrected. The restart test clock was frozen. A later all-template narrow run exposed a test assertion using an unbound source for cross-proof rejection; it was corrected to use the genuine broker-bound source. The restart comparison was corrected to compare semantic canonical observation and raw bytes rather than environment-specific proof hashes. All changes stayed in the two-file whitelist.

Narrow verification after corrections:

- Deterministic rebuild: 1 test, 89.630 seconds, exit 0.
- Restart: 1 test, 223.831 seconds, exit 0.
- Complete seven-member five-template case: 1 test, 4073.003 seconds, exit 0.

Full integration command: `& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_integration -v`. Result: **3 tests, 5353.997 seconds, 0 failures, 0 errors, 0 skips, exit 0**. The implementation was frozen after this GREEN result.

## Complete affected regression

Started exactly once after integration GREEN, as the only Python test run, with the brief's exact affected regression command, no duplicate TestCase and no restart of CPU-active work. The printed command contains 25 distinct `tests.*` module arguments despite the controller shorthand “26 modules.” Unified exec session `98725` ended normally. Terminal summary: **Ran 791 tests in 26771.845s; OK (skipped=1); 0 failures; 0 errors; exit code 0.** The sole skip is `tests.test_formal_feature_store.FormalFeatureStoreTests.test_symlinked_bundle_is_rejected_when_platform_allows_symlinks`, because Windows denied symlink creation with `WinError 1314`; this is the test's explicit platform-availability skip, not a failed assertion.

Command:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_range_contract tests.test_formal_range_source tests.test_formal_range_store tests.test_formal_range_worker tests.test_formal_policy_values tests.test_formal_policy_financial tests.test_formal_policy_state tests.test_formal_policy_market tests.test_formal_policy_evaluator tests.test_formal_policy_repository tests.test_formal_policy_batch_guards tests.test_formal_policy_integration tests.test_formal_policy_contract tests.test_formal_policy_registry tests.test_formal_policy_registry_guards tests.test_formal_sources tests.test_formal_context_schema tests.test_formal_context_repository tests.test_formal_feature_repository tests.test_formal_feature_store tests.test_formal_metric_context tests.test_formal_metric_features tests.test_formal_metric_batch_guard tests.test_formal_metric_engine tests.test_state_store -v
```

## Compatibility and self-review

The fixture extension defaults preserve earlier W3 behavior. No V2–V6 DDL, descriptors, arithmetic, request schemas, snapshot behavior, scoring, or pools were edited. `git status --short` shows only `M tests/formal_policy_runtime_fixtures.py` and `?? tests/test_formal_policy_integration.py`. `git diff --check` exited 0 (Git only warned that the fixture's LF may later be converted to CRLF); `git diff --cached --name-only` is empty, so no data, SQLite, WAL/SHM, outputs, or progress file is staged. SHA-256 of the initial W4 implementation before review fix round 1:

- `tests/test_formal_policy_integration.py`: `07DC142CF51F90DA27CEEF40078C5228C67334EF2A2B851C86EF5C699CFB753F`.
- `tests/formal_policy_runtime_fixtures.py`: `A1D2EC0223752F783736A9F9716D6B70693D5B0F56EF495CEFE974E618536C58`.

The full regression and the independently GREEN integration module exercised the pre-policy and new policy paths without any production edit. The report itself is an ignored SDD coordination artifact and is not staged.

One read-only diagnosis identified an unresolved boundary in production `FormalRangeWorker.resume`: distinct bindings can concurrently attempt the same calendar natural key with differing task payloads. This task does not change or claim to solve that cross-binding concurrency risk; the tested sequential fixture reuse is narrower.

## Independent review fix round 1 — pre-edit coverage rationale

Review `task-W4-review-9452b31.md` identifies two test-only assertion gaps. First, the old `formal_source_snapshot` existence query after `g2` would also pass if that historical row were updated in place. The new assertion must take a pre-correction raw SQLite image of the entire old snapshot row and its linked producer task/receipt (and the old Context fact), then compare each full row after correction; existing raw content-byte equality remains separate. Second, checking fixture DB/raw roots does not prove the observed page files were written there. The new restart assertion must resolve and contain each actual first/recovered/control `content_path` and `manifest_path` under the corresponding fixture's temporary root before reading raw bytes. Both checks target a concrete bad behavior, but no production change is authorized or needed; if the genuine existing code passes, that is new coverage rather than a manufactured RED. No mutation of production code or deliberate corruption of test data will be used to force failure.

## Independent review fix round 1 — implementation and verification

Only `tests/test_formal_policy_integration.py` changed in this round. Before `g2`, the correction test now reads the complete SQLite rows for the old `formal_source_snapshot`, linked `formal_collection_task`, `formal_task_snapshot_receipt`, and `formal_context_fact`. After republishing it rereads the same identities and compares every column value against the captured rows; the existing old raw-byte equality and new-generation existence checks remain. These expectations are actual pre-correction database values captured at a different time, not values recomputed by a production helper. A realistic in-place historical-row rewrite, task/receipt rewrite, fact rewrite, or deletion now fails. The restart test checks `Path(...).resolve(strict=True).is_relative_to(fixture.root.resolve())` for both content and manifest paths of the persisted first page and recovered/control final pages, before comparing real raw file bytes. A misrouted path or symlink outside the temporary root now fails.

No production behavior was changed, so both new assertions passed directly as additional coverage; no artificial RED was manufactured. The two affected single-test commands were run separately, with no seven-security rerun, full integration rerun, or 791-test regression rerun:

```powershell
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_integration.FormalPolicyIntegrationTests.test_rebuild_is_identical_then_append_only_correction_changes_identity -v
& D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m unittest tests.test_formal_policy_integration.FormalPolicyIntegrationTests.test_restart_reuses_authenticated_page_without_transport_duplicate -v
```

- Correction: **Ran 1 test in 158.178s; OK; exit 0**.
- Restart: **Ran 1 test in 697.729s; OK; exit 0**.

Final round-1 audit: `git status --short` shows only `M tests/test_formal_policy_integration.py`; `git diff --check` exits 0 with Git's LF→CRLF advisory only; `git diff --cached --name-only` is empty. No fixture, production, DDL, data, network, Git index, or other tracked path was touched. Updated SHA-256 for `tests/test_formal_policy_integration.py`: `D9BDB378D088C791EB30BAE11D0E669F5245668FE15A8BFFAD9C628C30897887`. Self-review confirms each observed path is checked against its own fixture root, `strict=True` rejects nonexistent files, the raw bytes are still read from disk, and old rows are compared across correction without using the producer to derive either expected row.
