### Task 1: Seven-Dimension Contract and Deterministic Hashing

**Files:**
- Create: `ashare_pipeline/feature_contract.py`
- Create: `tests/test_feature_contract.py`

**Interfaces:**
- Consumes: Python standard-library dataclasses, mappings, JSON, SHA-256, and timezone-aware ISO timestamps.
- Produces: `CONTRACT_VERSION`, `DIMENSIONS`, `EvidenceRef`, `FeatureValue`, `DimensionInput`, `IndustryContext`, `ConfidenceInputs`, `FeatureBundle`, `canonical_json_bytes(value)`, and `canonical_sha256(value)`.

- [ ] **Step 1: Write failing contract tests**

Create `tests/test_feature_contract.py` with a helper that constructs all seven dimensions and these core assertions:

```python
import math
import unittest

from ashare_pipeline.feature_contract import (
    DIMENSIONS,
    ConfidenceInputs,
    DimensionInput,
    EvidenceRef,
    FeatureBundle,
    FeatureValue,
    IndustryContext,
)


def evidence(snapshot_id: str = "snapshot-a") -> EvidenceRef:
    return EvidenceRef(
        financial_fact_id="fact-a",
        source_snapshot_id=snapshot_id,
        source_field="TOTAL_ASSETS",
        raw_row_hash="a" * 64,
        announced_at_utc="2026-08-20T15:59:59+00:00",
        effective_at_utc="2026-08-21T07:00:00+00:00",
    )


def dimensions() -> dict[str, DimensionInput]:
    result = {
        key: DimensionInput(
            status="partial",
            values=(
                FeatureValue(
                    key=f"{key.lower()}.sample",
                    value=0.0,
                    unit="ratio",
                    period_key="2026H1",
                    status="observed",
                    formula_version="observed-v1",
                    evidence=(evidence(),),
                    missing_reason=None,
                ),
            ),
        )
        for key in DIMENSIONS
    }
    result["V"] = DimensionInput(
        status="missing",
        values=(
            FeatureValue(
                key="v.market_cap",
                value=None,
                unit="CNY",
                period_key="as_of",
                status="missing",
                formula_version="observed-v1",
                evidence=(),
                missing_reason="market_data_missing",
            ),
        ),
    )
    return result


def bundle(
    dimension_inputs: dict[str, DimensionInput] | None = None,
    *,
    is_formal_score_ready: bool = False,
) -> FeatureBundle:
    return FeatureBundle(
        schema_version=1,
        contract_version="feature-contract-v1",
        security_id="SH600001",
        report_period="2026-06-30",
        as_of_utc="2026-08-29T16:00:00+00:00",
        candidate_set_hash="c" * 64,
        industry=IndustryContext(
            source="eastmoney-provisional",
            code=None,
            name="包装印刷",
            template_id="general_nonfinancial",
            template_version="template-registry-v1",
            formal_industry_ready=False,
        ),
        input_hash="1" * 64,
        financial_status="partial",
        financial_coverage=0.5,
        confidence_inputs=ConfidenceInputs(
            data_completeness_ratio=0.5,
            date_precision_counts={"timestamp": 0, "date_only": 1},
            history_years_present=3,
            mapping_consistent=True,
            formal_confidence=None,
        ),
        dimension_inputs=dimension_inputs or dimensions(),
        blockers=("formal_industry_mapping_missing",),
        is_formal_score_ready=is_formal_score_ready,
    )


class FeatureContractTests(unittest.TestCase):
    def test_bundle_requires_exactly_seven_dimensions_and_is_never_formal(self):
        self.assertEqual(DIMENSIONS, ("G", "V", "M", "EQ", "FS", "CA", "T"))
        with self.assertRaisesRegex(ValueError, "dimension keys"):
            bundle({key: value for key, value in dimensions().items() if key != "G"})
        with self.assertRaisesRegex(ValueError, "formal score"):
            bundle(dimensions(), is_formal_score_ready=True)

    def test_zero_missing_and_nonfinite_values_have_distinct_contracts(self):
        self.assertEqual(dimensions()["G"].values[0].value, 0.0)
        self.assertIsNone(dimensions()["V"].values[0].value)
        for invalid in (True, math.nan, math.inf, -math.inf):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    FeatureValue(
                        key="g.invalid",
                        value=invalid,
                        unit="ratio",
                        period_key="2026H1",
                        status="observed",
                        formula_version="observed-v1",
                        evidence=(evidence(),),
                        missing_reason=None,
                    )

    def test_canonical_hash_is_order_independent_and_evidence_sensitive(self):
        first = bundle(dimensions())
        reversed_dimensions = dict(reversed(tuple(dimensions().items())))
        second = bundle(reversed_dimensions)
        changed = bundle(
            {**dimensions(), "G": DimensionInput(status="partial", values=(
                FeatureValue(
                    key="g.sample",
                    value=0.0,
                    unit="ratio",
                    period_key="2026H1",
                    status="observed",
                    formula_version="observed-v1",
                    evidence=(evidence("snapshot-b"),),
                    missing_reason=None,
                ),
            ))}
        )
        self.assertEqual(first.canonical_bytes(), second.canonical_bytes())
        self.assertEqual(first.bundle_hash(), second.bundle_hash())
        self.assertNotEqual(first.bundle_hash(), changed.bundle_hash())
```

Additional test methods must cover incomplete evidence, naive timestamps, coverage below 0/above 1, inconsistent observed/missing states, non-null formal confidence, and JSON round-trip.

- [ ] **Step 2: Run the contract tests to verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_feature_contract -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'ashare_pipeline.feature_contract'`.

- [ ] **Step 3: Implement the immutable contract**

Add these exact constants and state rules:

```python
CONTRACT_VERSION = "feature-contract-v1"
DIMENSIONS = ("G", "V", "M", "EQ", "FS", "CA", "T")
FEATURE_VALUE_STATES = frozenset({"observed", "derived", "missing", "not_applicable", "blocked"})
DIMENSION_INPUT_STATES = frozenset({"input_ready", "partial", "missing", "not_applicable", "blocked"})
FINANCIAL_STATUSES = frozenset({"partial", "financial_ready", "blocked"})
UNITS = frozenset({"CNY", "shares", "ratio", "CNY_per_share"})


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def require_aware_utc(value: str, field: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone offset")
    return parsed.astimezone(timezone.utc).isoformat()


def require_feature_number(value: object, *, allow_none: bool) -> float | None:
    if value is None and allow_none:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("feature value must be a finite number or allowed null")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("feature value must be finite")
    return result
```

Implement frozen dataclasses with `to_dict()`/`from_dict()`. `FeatureValue.__post_init__` must require a unit from `UNITS` in every state, a finite value plus evidence for observed/derived, and null plus a non-empty reason for missing/not_applicable/blocked. `FeatureBundle.validate()` must require exact dimension keys, `0 <= financial_coverage <= 1`, `formal_confidence is None`, and `is_formal_score_ready is False`. Sort dimensions by `DIMENSIONS`, feature values by `(key, period_key)`, evidence by all fields, and blockers lexically in `to_dict()`.

- [ ] **Step 4: Run the contract tests to verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_feature_contract -v
```

Expected: PASS.

- [ ] **Step 5: Commit the contract**

```powershell
git add -- ashare_pipeline/feature_contract.py tests/test_feature_contract.py
git commit -m "feat: define auditable seven-dimension feature contract"
```

---

