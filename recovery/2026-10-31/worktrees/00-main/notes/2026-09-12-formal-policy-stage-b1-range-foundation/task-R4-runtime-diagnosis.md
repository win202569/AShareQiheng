# Range runtime diagnosis — static audit plus bounded measurement

Agent: /root/range_runtime_diagnosis. Static review based on bc1d137 and existing
R4 logs; no tests/profile runs or mutations. R4 fix1 began independently afterward.

## Measured
Different three-test groups took 1100.321s and 521.178s. Only aggregate timing is
available; no per-call attribution. The 1100s group includes a cold subprocess,
the 521s group does not, so they are not directly comparable.

## Static inference
No intentional retry sleeps: formal_range_worker.py:48–56 computes next_retry_at.
Fake transport at tests/formal_range_fixtures.py:172–191 is synchronous/in-memory.
Worker test scheduling clocks are mocked (test_formal_range_worker.py:27–37).
StateStore has a five-second busy timeout (state_store.py:1614–1631), but the
named tests show no concurrent lock holder. There is no evidence of deadlock.

Strongest hypothesis: repeated CPU/file/SQLite authenticity-validation work.
- Store.load_binding reloads manifest/all roles before its cache lookup:
  formal_range_store.py:112–140; formal_registry_manifest.py:713–727.
- Every current binding check reruns _derive_graph:
  formal_range_contract.py:339–359,416–417. It verifies scoring directly and
  again through policy verification: formal_policy_registry.py:387–418;
  formal_scoring_registry.py:479–528.
- Request/source authentication repeats these current checks:
  formal_range_source.py:214–243,853–884.
- Current observations reread/reparse candidate rows and recursively replay
  parent evidence: formal_range_store.py:214–279,295–347.
- One page-two run fans through lease reconstruction, fetch, persist/replay and
  successor validation, multiplying whole-graph and parent verification.

This is a hypothesis, not measured proof or a basis for removing checks.

## Proposed later measurement (NOT RUN)
One representative test under cProfile, saving to a new task-owned temporary
pstats file, no production changes:
D:/Projects/AShareQiheng/.venv/Scripts/python.exe -m cProfile -o <new-temporary-path>
-m unittest tests.test_formal_range_worker.FormalRangeWorkerTests.test_success_queues_only_next_page_and_missing_page_keeps_first -v

Inspect cumulative time/call counts for registry load, _derive_graph, scoring
sealed/require_official, store read/current_candidates/require_parent_chain,
and SQLite execute. Compare process time and wall time if possible. Profiling
will itself add overhead. No profiling, performance fix, caching shortcut or
authority weakening is authorized by this diagnostic artifact.

## Controller bounded measurement (completed after GREEN83795)

Instead of rerunning a test, root profiled only RangeSourceFixture construction
and one first_calendar_request in memory. Session31853 finished exit0 with no
competing test process, fetch, worker, database or network operations. Full
top25 output: task-R4-tiny-profile.log. Measured41.591s wall/36.141s CPU; profiler
recorded76,092,272 function calls in40.825s. This includes profiler overhead and
fixture construction, so it is not an unprofiled production request benchmark.

Dominant cumulative paths: scoring require_official25calls/37.340s;
_feature_slots26calls/37.025s; _derive_graph7calls/33.912s; feature registry parser
422calls/29.820s. These times overlap and must not be added. First-request minting
alone accounted19.161s cumulative; fixture constructor22.430s.

Root checked scoring_registry._feature_slots and feature_contract owner methods:
_feature_slots authenticates and reads several sensitive properties, then obtains
five template slot sets. Each sensitive property triggers __getattribute__ ->
require_verified, which fingerprints all slots and reparses registry bytes.
slots_for_template likewise revalidates and reparses again. Repeated range/policy
graph checks multiply those operations. This confirms the repeated parse/check
hotspot for the measured bounded path. Parent-chain costs and full worker/suite
behavior were not profiled, so broader attribution remains limited.

No performance cache or validation shortcut was implemented. Any optimization
must separately preserve current-source checks, mutation rejection, same-root
identity, callback-time integrity and existing signed-contract behavior. Default
real-time lease adequacy and production throughput remain unverified.
