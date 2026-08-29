# Task 2 Review Package

## Spec

Authoritative requirements: `task-2-brief.md` plus Task 1 public API in `ashare_pipeline/state_store.py`.

## Review scope

- `ashare_pipeline/sources.py` — `98312C6222455AC983343CE73D1FE1A46A0DA12F72590618C877CF418D466BE7`
- `ashare_pipeline/snapshot_store.py` — `165EB5D844219EAECAE8586C83F1A418A9012A0F49E3E05FA1FBAB10456414D3`
- `ashare_pipeline/pilot.py` — `2ECF98E2E17E95504A1A5A5C2AC87461FB8B48FF12ECB14934EF4E5E67B198DB`
- `tests/test_sources.py` — `1FF3FFF31FBABCD9432794A9915BD67012942C33244042E49B2A5C3F38E00FC1`
- `tests/test_snapshot_store.py` — `A148EF71D65537EA1A8A9D3BDCDE89E0F091C9AA32FCFF497F789401F454A9BB`
- `tests/test_pilot.py` — `F2292BD8E62762B44197C66A50D863DE5B04610426C879049EBAD91BF392AF61`
- `task-2-report.md` — `0574CF92B42828C8EFC9B1A2386B87BD4E5AE408B4929423BACEF49555A46D0B`

## Implementer evidence

Reported Task 2-only `unittest` result: 13/13 passing. Controller will independently rerun tests and online pilot after review.

## Review focus

Perform a read-only specification and quality review. Check every requirement in `task-2-brief.md`, especially:

1. canonical JSON/hash handling of NaN/NaT/date and leading-zero codes;
2. BaoStock login/logout/error/empty semantics and exact daily fields;
3. AKShare real function names/parameters, report-period matching, error classification and optional-dependency imports;
4. SnapshotStore atomicity, hash verification, dedupe and `.part` cleanup;
5. pilot offline no-network behavior, online source sequence, idempotent job transitions, close/future-date semantics, spot degradation and second-run safety;
6. whether tests prove the behavior rather than mirror a flawed implementation.

Classify findings Critical/Important/Minor, cite file and line, and return `Approved` only if no Critical or Important issue remains. Do not edit files and do not rerun tests.
