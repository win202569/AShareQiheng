from dataclasses import dataclass
import unittest

from ashare_pipeline.formal_time import (
    formal_version_sort_key,
    is_visible_at,
    market_close_as_of,
    resolve_effective_at,
)


@dataclass(frozen=True)
class VersionRow:
    published_at_utc: str
    source_updated_at_utc: str | None
    captured_at_utc: str
    content_hash: str


class FormalTimeTests(unittest.TestCase):
    def test_formal_market_close_is_exactly_the_shanghai_close(self):
        self.assertEqual(
            market_close_as_of("2026-08-31"),
            "2026-08-31T15:00:00+08:00",
        )

    def test_date_only_requires_verified_next_close_and_respects_freeze_visibility(self):
        close = market_close_as_of("2026-08-31")

        with self.assertRaisesRegex(ValueError, "verified next exchange close"):
            resolve_effective_at("2026-08-31", "date_only")
        with self.assertRaisesRegex(ValueError, "15:00:00 Asia/Shanghai"):
            resolve_effective_at(
                "2026-08-31",
                "date_only",
                verified_next_exchange_close="2026-09-01T15:00:01+08:00",
            )

        same_day_effective = resolve_effective_at(
            "2026-08-31",
            "date_only",
            verified_next_exchange_close="2026-09-01T15:00:00+08:00",
        )
        prior_day_effective = resolve_effective_at(
            "2026-08-28",
            "date_only",
            verified_next_exchange_close="2026-08-31T15:00:00+08:00",
        )

        self.assertFalse(is_visible_at(same_day_effective, close))
        self.assertTrue(is_visible_at(prior_day_effective, close))

    def test_timestamp_precision_uses_validated_timestamp_directly(self):
        timestamp = "2026-08-31T14:59:59+08:00"

        self.assertEqual(resolve_effective_at(timestamp, "timestamp"), timestamp)
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            resolve_effective_at("2026-08-31T14:59:59", "timestamp")

    def test_version_order_is_published_desc_updated_desc_captured_desc_hash_asc(self):
        rows = [
            VersionRow("2026-08-30T08:00:00+00:00", None, "2026-09-01T00:00:00+00:00", "f" * 64),
            VersionRow("2026-08-31T08:00:00+00:00", None, "2026-09-01T00:00:00+00:00", "e" * 64),
            VersionRow("2026-08-31T08:00:00+00:00", "2026-08-31T09:00:00+00:00", "2026-08-31T10:00:00+00:00", "d" * 64),
            VersionRow("2026-08-31T08:00:00+00:00", "2026-08-31T09:00:00+00:00", "2026-08-31T11:00:00+00:00", "c" * 64),
            VersionRow("2026-08-31T08:00:00+00:00", "2026-08-31T09:00:00+00:00", "2026-08-31T11:00:00+00:00", "b" * 64),
            VersionRow("2026-08-31T08:00:00+00:00", "2026-08-31T09:00:00+00:00", "2026-08-31T11:00:00+00:00", "a" * 64),
        ]

        ordered = sorted(rows, key=formal_version_sort_key)

        self.assertEqual(
            [row.content_hash for row in ordered],
            ["a" * 64, "b" * 64, "c" * 64, "d" * 64, "e" * 64, "f" * 64],
        )

    def test_visibility_rejects_malformed_or_naive_times(self):
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            is_visible_at("2026-08-31T15:00:00", "2026-08-31T15:00:00+08:00")
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            market_close_as_of("not-a-date")


if __name__ == "__main__":
    unittest.main()
