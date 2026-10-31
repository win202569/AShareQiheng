# Pre-V7 legacy DDL fingerprints

Captured at wave2 BASE f4ed417, before R3 dispatch. StateStore schema version is 6.
Read-only Python AST/literal extraction, no local module import and no database opened.
Canonical JSON per constant: sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False.
SHA-256 must remain identical after R3; only the new V7 namespace may be added.

```json
{
  "_V2_INDEX_DDL": {
    "objects": 1,
    "sha256": "b6cc73d2f81e507f96afb9acc9813c4347c21438f16ee76520eeb8ff7cd0f5c9"
  },
  "_V2_TABLE_DDL": {
    "objects": 7,
    "sha256": "d6f24dfa4b6049da28dccc6f7fae6064bcd69b211c9e174ce26d403835fa078e"
  },
  "_V3_INDEX_DDL": {
    "objects": 3,
    "sha256": "cad6e0659a696bb6196574b5791df78ad46261c86f309216e14f58bb36c5640c"
  },
  "_V3_TABLE_DDL": {
    "objects": 3,
    "sha256": "bb2a9b5ddbeeea7d882997f448c4b71c28ede7201e4933d5e68ae9639403900c"
  },
  "_V4_INDEX_DDL": {
    "objects": 0,
    "sha256": "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a"
  },
  "_V4_TABLE_DDL": {
    "objects": 1,
    "sha256": "389fac8d111b1829b4edf203a6b9a8421aa9e202c8fb51afc628abaaf948534c"
  },
  "_V5_INDEX_DDL": {
    "objects": 2,
    "sha256": "927875bb0dafaa3ba358407ad4ea9daa50afa0279c60e4d5123c8b4d62193983"
  },
  "_V5_TABLE_DDL": {
    "objects": 8,
    "sha256": "706343d045efa145f9aacc4075a7b19a7b3eaf126b6504ed627be608ed4d18e3"
  },
  "_V6_INDEX_DDL": {
    "objects": 3,
    "sha256": "9552130df6575dca64c5cb51b99bb05c64fba347c38372e298269674a46a24fa"
  },
  "_V6_TABLE_DDL": {
    "objects": 8,
    "sha256": "7f37c76c4d0c45574e4ea351a5432b63b91f24e741f2aedc05e7d346f1874cd7"
  }
}
```

