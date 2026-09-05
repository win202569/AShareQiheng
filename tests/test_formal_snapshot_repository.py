"""Contract tests for the verified formal snapshot repository."""

from __future__ import annotations

from contextlib import closing
from dataclasses import replace
from pathlib import Path
import sqlite3
import tempfile
import unittest
import uuid

from ashare_pipeline.formal_evidence import (
    EvidenceVerification,
    OfficialFetch,
    OfficialRequest,
    OfficialSnapshotRef,
    SourcePolicy,
    VerifiedCalendarBinding,
    verify_official_fetch,
)
from ashare_pipeline.formal_snapshot_repository import FormalSnapshotRepository
from ashare_pipeline.formal_snapshot_store import FormalSnapshotStore
from ashare_pipeline.snapshot_repository import SnapshotRef
from ashare_pipeline.state_store import StateStore


def cninfo_fetch(
    *,
    raw_bytes: bytes = b"%PDF-1.7 verified formal evidence",
    refresh_generation: str = "bootstrap-v1",
    published_at_utc: str = "2026-08-20T08:00:00+00:00",
    source_updated_at_utc: str | None = None,
    captured_at_utc: str = "2026-09-04T08:00:00+00:00",
    effective_at_utc: str | None = None,
    request: OfficialRequest | None = None,
) -> OfficialFetch:
    request = request or OfficialRequest(
        "cninfo", "annual_report", "SZ000001", "2025-12-31", "SZ"
    )
    return OfficialFetch(
        request=request,
        raw_bytes=raw_bytes,
        original_url="https://static.cninfo.com.cn/finalpage/2026-08-20/verified.pdf",
        published_at_utc=published_at_utc,
        published_precision="timestamp",
        source_updated_at_utc=source_updated_at_utc,
        captured_at_utc=captured_at_utc,
        effective_at_utc=effective_at_utc or published_at_utc,
        effective_time_evidence_hash=None,
        refresh_generation=refresh_generation,
        parser_id="cninfo-pdf",
        parser_version="cninfo-pdf-v1",
        mapping_version="cninfo-annual-v1",
        declared_security_id=request.security_id,
        declared_period=request.period_or_date,
    )


def verified(fetch: OfficialFetch) -> EvidenceVerification:
    verification = verify_official_fetch(fetch, SourcePolicy.cninfo())
    if verification.status != "verified":
        raise AssertionError(verification)
    return verification


class FormalSnapshotRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name) / "formal-raw"
        self.db_path = Path(self.tempdir.name) / "state.sqlite3"
        self.raw_store = FormalSnapshotStore(self.root)
        self.store = StateStore(self.db_path, formal_snapshot_store=self.raw_store)
        self.store.initialize()
        self.repository = FormalSnapshotRepository(self.root, self.store)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def persist_leased_snapshot(
        self, *, key: str, generation: str, raw_bytes: bytes = b"leased evidence"
    ) -> tuple[str, OfficialFetch, OfficialSnapshotRef]:
        task_id = self.store.enqueue_formal_task(
            "formal_statement", key, generation, {"key": key}
        )
        leased = self.store.lease_next_formal_task(
            ("formal_statement",), f"worker-{key}", 300
        )
        self.assertEqual(leased["id"], task_id)
        fetch = cninfo_fetch(raw_bytes=raw_bytes, refresh_generation=generation)
        ref = self.repository.persist_verified(
            fetch,
            verified(fetch),
            producing_task_id=task_id,
            worker_id=f"worker-{key}",
        )
        return task_id, fetch, ref

    def insert_direct_valid_task_snapshot(
        self,
        *,
        task_id: str,
        fetch: OfficialFetch,
    ) -> str:
        """Materialize a raw-valid extra producer row to adversarially fracture the graph."""
        verification = verified(fetch)
        stored = self.raw_store.write_verified(
            fetch, verification, producing_task_id=task_id
        )
        validated = self.raw_store.validate_stored_snapshot(
            fetch,
            stored,
            verification,
            expected_producing_task_id=task_id,
        )
        snapshot_id = str(uuid.uuid4())
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute(
                """INSERT INTO formal_source_snapshot
                (id,source,dataset,request_json,request_fingerprint,content_sha256,
                 manifest_sha256,content_path,manifest_path,original_url,published_at_utc,
                 published_precision,source_updated_at_utc,captured_at_utc,effective_at_utc,
                 effective_time_evidence_hash,parser_id,parser_version,mapping_version,
                 refresh_generation,producing_task_id,verification_json,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    snapshot_id,
                    validated.source,
                    validated.dataset,
                    validated.request_json,
                    validated.request_fingerprint,
                    validated.content_sha256,
                    validated.manifest_sha256,
                    validated.content_path,
                    validated.manifest_path,
                    validated.original_url,
                    validated.published_at_utc,
                    validated.published_precision,
                    validated.source_updated_at_utc,
                    validated.captured_at_utc,
                    validated.effective_at_utc,
                    validated.effective_time_evidence_hash,
                    validated.parser_id,
                    validated.parser_version,
                    validated.mapping_version,
                    validated.refresh_generation,
                    validated.producing_task_id,
                    validated.verification_json,
                    "2026-09-04T00:00:00+00:00",
                ),
            )
            connection.commit()
        return snapshot_id

    def test_constructor_requires_the_configured_authoritative_raw_store(self) -> None:
        """A repository must reuse, rather than replace, StateStore's raw boundary."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "raw"
            db_path = Path(directory) / "state.sqlite3"
            unconfigured = StateStore(db_path)
            unconfigured.initialize()
            with self.assertRaisesRegex(ValueError, "formal snapshot store"):
                FormalSnapshotRepository(root, unconfigured)

            raw_store = FormalSnapshotStore(root)
            configured = StateStore(db_path, formal_snapshot_store=raw_store)
            repository = FormalSnapshotRepository(root, configured)

            self.assertIsNotNone(repository)
            with self.assertRaisesRegex(ValueError, "root"):
                FormalSnapshotRepository(root / "other", configured)

    def test_bootstrap_persistence_returns_a_row_ref_and_validates_before_raw_write(self) -> None:
        """Bad evidence or a half ownership pair must not create raw evidence files."""
        fetch = cninfo_fetch()
        verification = verified(fetch)
        rejected = EvidenceVerification(
            "rejected", fetch.content_sha256, ("source_not_authoritative",), None
        )
        invalid_calls = (
            (fetch, rejected, None, None, "verified"),
            (fetch, verification, "task-1", None, "together"),
            (fetch, verification, None, "worker-1", "together"),
            (fetch, verification, " task-1", "worker-1", "trimmed"),
            (fetch, verification, "task-1", "worker-1 ", "trimmed"),
            (object(), verification, None, None, "OfficialFetch"),
            (fetch, object(), None, None, "EvidenceVerification"),
        )
        for bad_fetch, bad_verification, task_id, worker_id, error in invalid_calls:
            with self.subTest(error=error), self.assertRaisesRegex(ValueError, error):
                self.repository.persist_verified(
                    bad_fetch,  # type: ignore[arg-type]
                    bad_verification,  # type: ignore[arg-type]
                    producing_task_id=task_id,
                    worker_id=worker_id,
                )
        self.assertFalse(list(self.root.rglob("*.bin")))
        self.assertFalse(list(self.root.rglob("*.manifest.json")))

        ref = self.repository.persist_verified(
            fetch, verification, producing_task_id=None, worker_id=None
        )
        self.assertEqual(ref.source, fetch.request.source)
        self.assertEqual(ref.dataset, fetch.request.dataset)
        self.assertEqual(ref.request_fingerprint, fetch.request.request_fingerprint)
        self.assertEqual(ref.content_sha256, fetch.content_sha256)
        self.assertIsNone(ref.producing_task_id)
        self.assertEqual(ref.verification_status, "verified")
        self.assertEqual(
            self.repository.persist_verified(
                fetch, verification, producing_task_id=None, worker_id=None
            ),
            ref,
        )
        changed_generation = replace(fetch, refresh_generation="bootstrap-v2")
        later = self.repository.persist_verified(
            changed_generation,
            verified(changed_generation),
            producing_task_id=None,
            worker_id=None,
        )
        self.assertEqual(later.content_path, ref.content_path)
        self.assertNotEqual(later.manifest_sha256, ref.manifest_sha256)
        self.assertEqual(self.repository.read_verified_raw(later), fetch.raw_bytes)

    def test_leased_persistence_writes_raw_before_the_fenced_formal_receipt(self) -> None:
        """A failed lease claim may retain immutable raw bytes but never a partial DB graph."""
        task_id = self.store.enqueue_formal_task(
            "formal_statement", "repository-leased", "leased-v1", {"slot": "one"}
        )
        leased = self.store.lease_next_formal_task(
            ("formal_statement",), "worker-a", 300
        )
        self.assertEqual(leased["id"], task_id)
        fetch = cninfo_fetch(refresh_generation="leased-v1")
        ref = self.repository.persist_verified(
            fetch,
            verified(fetch),
            producing_task_id=task_id,
            worker_id="worker-a",
        )
        receipt = self.store.get_formal_task_snapshot_receipt(task_id)
        self.assertEqual(receipt["task_id"], task_id)
        self.assertEqual(receipt["snapshot_id"], ref.snapshot_id)
        self.assertEqual(receipt["manifest_sha256"], ref.manifest_sha256)
        self.assertEqual(self.repository.get_verified_by_manifest(ref.manifest_sha256), ref)

        unleased_task = self.store.enqueue_formal_task(
            "formal_statement", "repository-unleased", "unleased-v1", {"slot": "two"}
        )
        unleased = cninfo_fetch(
            raw_bytes=b"unleased raw evidence remains immutable",
            refresh_generation="unleased-v1",
        )
        with self.assertRaisesRegex(ValueError, "lease owner"):
            self.repository.persist_verified(
                unleased,
                verified(unleased),
                producing_task_id=unleased_task,
                worker_id="worker-b",
            )
        self.assertTrue(list(self.root.rglob(f"{unleased.content_sha256}.bin")))
        with closing(sqlite3.connect(self.db_path)) as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM formal_source_snapshot WHERE producing_task_id = ?",
                    (unleased_task,),
                ).fetchone()[0],
                0,
            )

        wrong_task = self.store.enqueue_formal_task(
            "formal_statement", "repository-wrong-worker", "wrong-worker-v1", {}
        )
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                """UPDATE formal_collection_task
                SET status='leased', lease_worker='lease-owner',
                    lease_expires_at='2099-01-01T00:00:00+00:00'
                WHERE id = ?""",
                (wrong_task,),
            )
            connection.commit()
        wrong = cninfo_fetch(raw_bytes=b"wrong worker raw", refresh_generation="wrong-worker-v1")
        with self.assertRaisesRegex(ValueError, "lease owner"):
            self.repository.persist_verified(
                wrong,
                verified(wrong),
                producing_task_id=wrong_task,
                worker_id="lost-worker",
            )

        expired_task = self.store.enqueue_formal_task(
            "formal_statement", "repository-expired", "expired-v1", {}
        )
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                """UPDATE formal_collection_task
                SET status='leased', lease_worker='expired-worker',
                    lease_expires_at='2000-01-01T00:00:00+00:00'
                WHERE id = ?""",
                (expired_task,),
            )
            connection.commit()
        expired = cninfo_fetch(raw_bytes=b"expired lease raw", refresh_generation="expired-v1")
        with self.assertRaisesRegex(ValueError, "lease owner"):
            self.repository.persist_verified(
                expired,
                verified(expired),
                producing_task_id=expired_task,
                worker_id="expired-worker",
            )
        with closing(sqlite3.connect(self.db_path)) as connection:
            for task_id in (wrong_task, expired_task):
                with self.subTest(task_id=task_id):
                    self.assertEqual(
                        connection.execute(
                            "SELECT COUNT(*) FROM formal_source_snapshot WHERE producing_task_id = ?",
                            (task_id,),
                        ).fetchone()[0],
                        0,
                    )
                    self.assertEqual(
                        connection.execute(
                            "SELECT COUNT(*) FROM formal_task_snapshot_receipt WHERE task_id = ?",
                            (task_id,),
                        ).fetchone()[0],
                        0,
                    )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM formal_task_snapshot_receipt WHERE task_id = ?",
                    (unleased_task,),
                ).fetchone()[0],
                0,
            )

    def test_exact_lookup_requires_every_immutable_request_and_version_field(self) -> None:
        """A lookup must not silently substitute another request, parser, or hash."""
        fetch = cninfo_fetch()
        ref = self.repository.persist_verified(
            fetch, verified(fetch), producing_task_id=None, worker_id=None
        )
        arguments = {
            "parser_id": fetch.parser_id,
            "parser_version": fetch.parser_version,
            "mapping_version": fetch.mapping_version,
            "content_sha256": fetch.content_sha256,
            "manifest_sha256": ref.manifest_sha256,
        }
        self.assertEqual(
            self.repository.find_exact_verified(fetch.request, **arguments), ref
        )
        self.assertIsNone(
            self.repository.find_exact_verified(
                fetch.request,
                **{**arguments, "manifest_sha256": "0" * 64},
            )
        )
        for field, replacement in (
            ("parser_id", "other-parser"),
            ("parser_version", "other-version"),
            ("mapping_version", "other-mapping"),
            ("content_sha256", "1" * 64),
        ):
            with self.subTest(field=field):
                self.assertIsNone(
                    self.repository.find_exact_verified(
                        fetch.request, **{**arguments, field: replacement}
                    )
                )
        changed_request = replace(fetch.request, security_id="SZ000002")
        self.assertIsNone(
            self.repository.find_exact_verified(changed_request, **arguments)
        )
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            self.repository.find_exact_verified(
                fetch.request,
                **{**arguments, "content_sha256": fetch.content_sha256.upper()},
            )
        with self.assertRaisesRegex(ValueError, "trimmed"):
            self.repository.find_exact_verified(
                fetch.request, **{**arguments, "parser_id": " cninfo-pdf"}
            )

    def test_visible_lookup_uses_effective_cutoff_and_every_formal_version_key(self) -> None:
        """Version selection is point-in-time and deterministic, never insertion-ordered."""
        as_of = "2026-08-31T07:00:00+00:00"

        def persist(
            security_id: str,
            generation: str,
            *,
            raw_bytes: bytes,
            published: str = "2026-08-20T08:00:00+00:00",
            updated: str | None = None,
            captured: str = "2026-08-21T08:00:00+00:00",
            effective: str | None = None,
        ):
            request = OfficialRequest(
                "cninfo", "annual_report", security_id, "2025-12-31", "SZ"
            )
            fetch = cninfo_fetch(
                request=request,
                raw_bytes=raw_bytes,
                refresh_generation=generation,
                published_at_utc=published,
                source_updated_at_utc=updated,
                captured_at_utc=captured,
                effective_at_utc=effective,
            )
            return fetch, self.repository.persist_verified(
                fetch, verified(fetch), producing_task_id=None, worker_id=None
            )

        older, older_ref = persist("SZ000001", "published-old", raw_bytes=b"published-old")
        newest, newest_ref = persist(
            "SZ000001",
            "published-new",
            raw_bytes=b"published-new",
            published="2026-08-21T08:00:00+00:00",
        )
        self.assertEqual(
            self.repository.find_visible_verified(
                older.request,
                parser_id=older.parser_id,
                parser_version=older.parser_version,
                mapping_version=older.mapping_version,
                as_of_utc=as_of,
            ),
            newest_ref,
        )

        update_none, _ = persist("SZ000002", "update-none", raw_bytes=b"update-none")
        _, update_old_ref = persist(
            "SZ000002",
            "update-old",
            raw_bytes=b"update-old",
            updated="2026-08-20T09:00:00+00:00",
        )
        _, update_new_ref = persist(
            "SZ000002",
            "update-new",
            raw_bytes=b"update-new",
            updated="2026-08-20T10:00:00+00:00",
        )
        self.assertNotEqual(update_old_ref, update_new_ref)
        self.assertEqual(
            self.repository.find_visible_verified(
                update_none.request,
                parser_id=update_none.parser_id,
                parser_version=update_none.parser_version,
                mapping_version=update_none.mapping_version,
                as_of_utc=as_of,
            ),
            update_new_ref,
        )

        capture_first, _ = persist("SZ000003", "capture-first", raw_bytes=b"capture-first")
        _, capture_latest_ref = persist(
            "SZ000003",
            "capture-latest",
            raw_bytes=b"capture-latest",
            captured="2026-08-22T08:00:00+00:00",
        )
        self.assertEqual(
            self.repository.find_visible_verified(
                capture_first.request,
                parser_id=capture_first.parser_id,
                parser_version=capture_first.parser_version,
                mapping_version=capture_first.mapping_version,
                as_of_utc=as_of,
            ),
            capture_latest_ref,
        )

        content_first, content_first_ref = persist(
            "SZ000004", "content-first", raw_bytes=b"content-first"
        )
        _, content_second_ref = persist(
            "SZ000004", "content-second", raw_bytes=b"content-second"
        )
        expected_content_ref = min(
            (content_first_ref, content_second_ref), key=lambda ref: ref.content_sha256
        )
        self.assertEqual(
            self.repository.find_visible_verified(
                content_first.request,
                parser_id=content_first.parser_id,
                parser_version=content_first.parser_version,
                mapping_version=content_first.mapping_version,
                as_of_utc=as_of,
            ),
            expected_content_ref,
        )

        tied_first, tied_first_ref = persist(
            "SZ000005", "manifest-tie-first", raw_bytes=b"same-content-and-times"
        )
        _, tied_second_ref = persist(
            "SZ000005", "manifest-tie-second", raw_bytes=b"same-content-and-times"
        )
        self.assertEqual(tied_first_ref.content_sha256, tied_second_ref.content_sha256)
        self.assertEqual(
            self.repository.find_visible_verified(
                tied_first.request,
                parser_id=tied_first.parser_id,
                parser_version=tied_first.parser_version,
                mapping_version=tied_first.mapping_version,
                as_of_utc=as_of,
            ),
            min((tied_first_ref, tied_second_ref), key=lambda ref: ref.manifest_sha256),
        )

        historical, historical_ref = persist(
            "SZ000006",
            "captured-after-freeze",
            raw_bytes=b"historically effective despite late capture",
            captured="2026-09-05T08:00:00+00:00",
        )
        _, future_ref = persist(
            "SZ000006",
            "future-effective",
            raw_bytes=b"not-yet-effective",
            published="2026-08-31T08:00:00+00:00",
            effective="2026-08-31T08:00:00+00:00",
        )
        self.assertNotEqual(historical_ref, future_ref)
        self.assertEqual(
            self.repository.find_visible_verified(
                historical.request,
                parser_id=historical.parser_id,
                parser_version=historical.parser_version,
                mapping_version=historical.mapping_version,
                as_of_utc=as_of,
            ),
            historical_ref,
        )
        self.assertIsNone(
            self.repository.find_visible_verified(
                historical.request,
                parser_id=historical.parser_id,
                parser_version=historical.parser_version,
                mapping_version=historical.mapping_version,
                as_of_utc="2026-08-19T07:00:00+00:00",
            )
        )

    def test_constructor_reuses_the_configured_date_only_calendar_resolver(self) -> None:
        """A second raw store would lose the trusted resolver and reject the same evidence."""
        binding = VerifiedCalendarBinding(
            snapshot_id="calendar-snapshot",
            manifest_sha256="a" * 64,
            exchange="SZ",
            freeze_at_utc="2026-08-31T07:00:00+00:00",
            registry_manifest_hash="b" * 64,
            selector_hash="c" * 64,
            prerequisite_task_id="calendar-task",
        )
        request = OfficialRequest(
            "cninfo", "annual_report", "SZ000001", "2025-12-31", "SZ"
        )

        def resolve(candidate: OfficialRequest) -> VerifiedCalendarBinding:
            if candidate.canonical_json_bytes() != request.canonical_json_bytes():
                raise ValueError("unexpected request")
            return binding

        root = Path(self.tempdir.name) / "date-only-raw"
        raw_store = FormalSnapshotStore(root, calendar_binding_resolver=resolve)
        store = StateStore(self.db_path, formal_snapshot_store=raw_store)
        repository = FormalSnapshotRepository(root, store)
        fetch = replace(
            cninfo_fetch(request=request, refresh_generation="date-only-v1"),
            published_precision="date_only",
            effective_time_evidence_hash=binding.manifest_sha256,
        )
        verification = verify_official_fetch(
            fetch, SourcePolicy.cninfo(), calendar_binding=binding
        )
        self.assertEqual(verification.status, "verified")

        ref = repository.persist_verified(
            fetch, verification, producing_task_id=None, worker_id=None
        )
        self.assertEqual(repository.get_verified_by_manifest(ref.manifest_sha256), ref)
        self.assertEqual(repository.read_verified_raw(ref), fetch.raw_bytes)

    def test_visible_manifest_tie_break_is_independent_of_database_insertion_order(self) -> None:
        """When all version keys tie, the lower manifest wins even if inserted second."""
        request = OfficialRequest(
            "cninfo", "annual_report", "SZ000007", "2025-12-31", "SZ"
        )
        candidates = []
        for generation in ("tie-a", "tie-b"):
            fetch = cninfo_fetch(
                request=request,
                raw_bytes=b"identical tie bytes",
                refresh_generation=generation,
            )
            verification = verified(fetch)
            stored = self.raw_store.write_verified(
                fetch, verification, producing_task_id=None
            )
            candidates.append((fetch, stored, verification))
        inserted = []
        for fetch, stored, verification in sorted(
            candidates, key=lambda item: item[1].manifest_sha256, reverse=True
        ):
            inserted.append(self.store.put_formal_snapshot(fetch, stored, verification))
        expected = min(inserted, key=lambda ref: ref.manifest_sha256)
        self.assertNotEqual(inserted[0], expected)

        self.assertEqual(
            self.repository.find_visible_verified(
                request,
                parser_id="cninfo-pdf",
                parser_version="cninfo-pdf-v1",
                mapping_version="cninfo-annual-v1",
                as_of_utc="2026-08-31T07:00:00+00:00",
            ),
            expected,
        )

    def test_manifest_lookup_rejects_malformed_unknown_and_bootstrap_receipt_graphs(self) -> None:
        """A bootstrap snapshot is valid only when no task receipt claims it."""
        fetch = cninfo_fetch()
        ref = self.repository.persist_verified(
            fetch, verified(fetch), producing_task_id=None, worker_id=None
        )
        self.assertEqual(self.repository.get_verified_by_manifest(ref.manifest_sha256), ref)
        for invalid in ("not-a-hash", ref.manifest_sha256.upper()):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(ValueError, "SHA-256"):
                self.repository.get_verified_by_manifest(invalid)
        with self.assertRaisesRegex(ValueError, "unknown"):
            self.repository.get_verified_by_manifest("0" * 64)

        task_id = self.store.enqueue_formal_task(
            "formal_statement", "forged-bootstrap-receipt", fetch.refresh_generation, {}
        )
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute(
                """INSERT INTO formal_task_snapshot_receipt
                (task_id,snapshot_id,manifest_sha256,refresh_generation,recorded_at)
                VALUES (?,?,?,?,?)""",
                (
                    task_id,
                    ref.snapshot_id,
                    ref.manifest_sha256,
                    fetch.refresh_generation,
                    "2026-09-04T00:00:00+00:00",
                ),
            )
            connection.commit()
        with self.assertRaisesRegex(ValueError, "bootstrap.*receipt"):
            self.repository.get_verified_by_manifest(ref.manifest_sha256)

    def test_corrupt_future_matching_candidate_is_not_silently_cutoff_filtered(self) -> None:
        """Validation happens before effective-time filtering, so a future corrupt row stops replay."""
        historical = cninfo_fetch(
            raw_bytes=b"historical candidate", refresh_generation="history-v1"
        )
        historical_ref = self.repository.persist_verified(
            historical, verified(historical), producing_task_id=None, worker_id=None
        )
        future = cninfo_fetch(
            raw_bytes=b"future candidate",
            refresh_generation="future-v1",
            published_at_utc="2026-08-31T08:00:00+00:00",
        )
        future_ref = self.repository.persist_verified(
            future, verified(future), producing_task_id=None, worker_id=None
        )
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                "UPDATE formal_source_snapshot SET content_path = ? WHERE id = ?",
                (str(self.root / "missing-corrupt-content.bin"), future_ref.snapshot_id),
            )
            connection.commit()

        with self.assertRaises(ValueError):
            self.repository.find_visible_verified(
                historical.request,
                parser_id=historical.parser_id,
                parser_version=historical.parser_version,
                mapping_version=historical.mapping_version,
                as_of_utc="2026-08-31T07:00:00+00:00",
            )
        with self.assertRaises(ValueError):
            self.repository.find_exact_verified(
                historical.request,
                parser_id=historical.parser_id,
                parser_version=historical.parser_version,
                mapping_version=historical.mapping_version,
                content_sha256=historical.content_sha256,
                manifest_sha256=historical_ref.manifest_sha256,
            )

    def test_exact_lookup_does_not_fallback_when_newer_row_fingerprint_is_tampered(self) -> None:
        """A mutable row fingerprint must not exclude corrupt newer evidence from validation."""
        older = cninfo_fetch(
            raw_bytes=b"older exact candidate", refresh_generation="exact-history-v1"
        )
        older_ref = self.repository.persist_verified(
            older, verified(older), producing_task_id=None, worker_id=None
        )
        newer = cninfo_fetch(
            raw_bytes=b"newer exact candidate",
            refresh_generation="exact-history-v2",
            published_at_utc="2026-08-21T08:00:00+00:00",
        )
        newer_ref = self.repository.persist_verified(
            newer, verified(newer), producing_task_id=None, worker_id=None
        )
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                "UPDATE formal_source_snapshot SET request_fingerprint = ? WHERE id = ?",
                ("0" * 64, newer_ref.snapshot_id),
            )
            connection.commit()

        with self.assertRaisesRegex(ValueError, "request fingerprint"):
            self.repository.find_exact_verified(
                older.request,
                parser_id=older.parser_id,
                parser_version=older.parser_version,
                mapping_version=older.mapping_version,
                content_sha256=older.content_sha256,
                manifest_sha256=older_ref.manifest_sha256,
            )

    def test_visible_lookup_does_not_fallback_when_newer_row_fingerprint_is_tampered(self) -> None:
        """Point-in-time selection must validate a corrupt newest row before choosing history."""
        older = cninfo_fetch(
            raw_bytes=b"older visible candidate", refresh_generation="visible-history-v1"
        )
        self.repository.persist_verified(
            older, verified(older), producing_task_id=None, worker_id=None
        )
        newer = cninfo_fetch(
            raw_bytes=b"newer visible candidate",
            refresh_generation="visible-history-v2",
            published_at_utc="2026-08-21T08:00:00+00:00",
        )
        newer_ref = self.repository.persist_verified(
            newer, verified(newer), producing_task_id=None, worker_id=None
        )
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                "UPDATE formal_source_snapshot SET request_fingerprint = ? WHERE id = ?",
                ("0" * 64, newer_ref.snapshot_id),
            )
            connection.commit()

        with self.assertRaisesRegex(ValueError, "request fingerprint"):
            self.repository.find_visible_verified(
                older.request,
                parser_id=older.parser_id,
                parser_version=older.parser_version,
                mapping_version=older.mapping_version,
                as_of_utc="2026-08-31T07:00:00+00:00",
            )

    def test_task_producer_requires_one_receipt_and_one_source_row(self) -> None:
        """A task-produced ref cannot survive a missing receipt, generation drift, or extra row."""
        task_id, fetch, ref = self.persist_leased_snapshot(
            key="lineage-missing", generation="lineage-missing-v1"
        )
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                "DELETE FROM formal_task_snapshot_receipt WHERE task_id = ?", (task_id,)
            )
            connection.commit()
        with self.assertRaisesRegex(ValueError, "exactly one receipt"):
            self.repository.get_verified_by_manifest(ref.manifest_sha256)

        task_id, fetch, ref = self.persist_leased_snapshot(
            key="lineage-generation", generation="lineage-generation-v1"
        )
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                "UPDATE formal_task_snapshot_receipt SET refresh_generation = ? WHERE task_id = ?",
                ("forged-generation", task_id),
            )
            connection.commit()
        with self.assertRaisesRegex(ValueError, "generation"):
            self.repository.get_verified_by_manifest(ref.manifest_sha256)

    def test_task_producer_rejects_an_extra_raw_valid_source_row(self) -> None:
        """Receipt ownership is one task to one formal source row, not merely one receipt."""
        task_id, fetch, ref = self.persist_leased_snapshot(
            key="lineage-extra", generation="lineage-extra-v1"
        )
        extra_request = replace(fetch.request, security_id="SZ000002")
        extra_fetch = replace(
            fetch,
            request=extra_request,
            raw_bytes=b"different request but forged same task producer",
            declared_security_id=extra_request.security_id,
        )
        extra_id = self.insert_direct_valid_task_snapshot(
            task_id=task_id, fetch=extra_fetch
        )
        self.assertNotEqual(extra_id, ref.snapshot_id)

        with self.assertRaisesRegex(ValueError, "producer set"):
            self.repository.get_verified_by_manifest(ref.manifest_sha256)

    def test_canonical_row_tampering_is_rejected_before_exact_selection(self) -> None:
        """A stored fingerprint is never trusted without its canonical request JSON."""
        fetch = cninfo_fetch()
        ref = self.repository.persist_verified(
            fetch, verified(fetch), producing_task_id=None, worker_id=None
        )
        noncanonical = (
            '{"source":"cninfo","dataset":"annual_report","security_id":"SZ000001",'
            '"period_or_date":"2025-12-31","exchange":"SZ"}'
        )
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                "UPDATE formal_source_snapshot SET request_json = ? WHERE id = ?",
                (noncanonical, ref.snapshot_id),
            )
            connection.commit()
        with self.assertRaisesRegex(ValueError, "canonical"):
            self.repository.find_exact_verified(
                fetch.request,
                parser_id=fetch.parser_id,
                parser_version=fetch.parser_version,
                mapping_version=fetch.mapping_version,
                content_sha256=fetch.content_sha256,
                manifest_sha256=ref.manifest_sha256,
            )

    def test_read_verified_raw_requires_the_complete_immutable_reference_projection(self) -> None:
        """Checking only the two hashes would let callers redirect parsers to another lineage."""
        fetch = cninfo_fetch()
        ref = self.repository.persist_verified(
            fetch, verified(fetch), producing_task_id=None, worker_id=None
        )
        self.assertEqual(self.repository.read_verified_raw(ref), fetch.raw_bytes)
        replacements = {
            "snapshot_id": str(uuid.uuid4()),
            "source": "other-source",
            "dataset": "other-dataset",
            "request_fingerprint": "0" * 64,
            "security_id": "SZ000002",
            "period_or_date": "2024-12-31",
            "exchange": "SH",
            "content_sha256": "0" * 64,
            "manifest_sha256": "0" * 64,
            "content_path": str(self.root / "other.bin"),
            "manifest_path": str(self.root / "other.manifest.json"),
            "original_url": "https://static.cninfo.com.cn/other.pdf",
            "published_at_utc": "2026-08-21T08:00:00+00:00",
            "published_precision": "date_only",
            "source_updated_at_utc": "2026-08-20T09:00:00+00:00",
            "captured_at_utc": "2026-09-05T08:00:00+00:00",
            "effective_at_utc": "2026-08-21T08:00:00+00:00",
            "effective_time_evidence_hash": "a" * 64,
            "refresh_generation": "other-generation",
            "producing_task_id": "other-task",
            "parser_id": "other-parser",
            "parser_version": "other-parser-v1",
            "mapping_version": "other-mapping-v1",
            "verification_status": "rejected",
        }
        for field, value in replacements.items():
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.repository.read_verified_raw(replace(ref, **{field: value}))

        legacy = SnapshotRef(
            id="legacy-id",
            source="cninfo",
            dataset="annual_report",
            request_fingerprint=fetch.request.request_fingerprint,
            payload_hash=fetch.content_sha256,
            payload_path="data/raw/legacy.json",
            row_count=1,
            fetched_at=fetch.captured_at_utc,
            created_at=fetch.captured_at_utc,
        )
        for invalid in (legacy, ref.snapshot_id, {"manifest_sha256": ref.manifest_sha256}):
            with self.subTest(invalid_type=type(invalid).__name__), self.assertRaises(ValueError):
                self.repository.read_verified_raw(invalid)  # type: ignore[arg-type]

    def test_read_verified_raw_fails_closed_for_raw_manifest_path_and_missing_row_tamper(self) -> None:
        """The repository re-reads the DB graph and manifest before handing bytes to a parser."""
        fetch = cninfo_fetch()
        ref = self.repository.persist_verified(
            fetch, verified(fetch), producing_task_id=None, worker_id=None
        )
        Path(ref.content_path).write_bytes(b"tampered raw bytes")
        with self.assertRaises(ValueError):
            self.repository.read_verified_raw(ref)

        fetch = cninfo_fetch(raw_bytes=b"manifest tamper", refresh_generation="manifest-v1")
        ref = self.repository.persist_verified(
            fetch, verified(fetch), producing_task_id=None, worker_id=None
        )
        Path(ref.manifest_path).write_text("{}", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.repository.read_verified_raw(ref)

        fetch = cninfo_fetch(raw_bytes=b"path and row tamper", refresh_generation="path-v1")
        ref = self.repository.persist_verified(
            fetch, verified(fetch), producing_task_id=None, worker_id=None
        )
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                "UPDATE formal_source_snapshot SET manifest_path = ? WHERE id = ?",
                (str(self.root / "missing.manifest.json"), ref.snapshot_id),
            )
            connection.commit()
        with self.assertRaises(ValueError):
            self.repository.read_verified_raw(ref)

        missing_fetch = cninfo_fetch(
            raw_bytes=b"missing source row", refresh_generation="missing-row-v1"
        )
        missing_ref = self.repository.persist_verified(
            missing_fetch,
            verified(missing_fetch),
            producing_task_id=None,
            worker_id=None,
        )
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                "DELETE FROM formal_source_snapshot WHERE id = ?", (missing_ref.snapshot_id,)
            )
            connection.commit()
        with self.assertRaisesRegex(ValueError, "unknown"):
            self.repository.read_verified_raw(missing_ref)

    def test_universe_source_receipt_remains_retrievable_without_mutating_task_state(self) -> None:
        """A real formal-universe source goes through the same verified manifest boundary."""
        generation = "universe-source-v1"
        task_id = self.store.enqueue_formal_task(
            "formal_universe_source",
            "repository-universe-source",
            generation,
            {"exchange": "SZ", "source": "cninfo"},
        )
        leased = self.store.lease_next_formal_task(
            ("formal_universe_source",), "universe-worker", 300
        )
        self.assertEqual(leased["id"], task_id)
        fetch = cninfo_fetch(
            raw_bytes=b"formal universe source evidence", refresh_generation=generation
        )
        ref = self.repository.persist_verified(
            fetch,
            verified(fetch),
            producing_task_id=task_id,
            worker_id="universe-worker",
        )
        self.store.complete_formal_task(task_id, "universe-worker", {"snapshot": ref.snapshot_id})
        before = self.store.get_formal_task(task_id)
        self.assertEqual(before["status"], "verified")

        self.assertEqual(self.repository.get_verified_by_manifest(ref.manifest_sha256), ref)
        self.assertEqual(self.repository.read_verified_raw(ref), fetch.raw_bytes)
        after = self.store.get_formal_task(task_id)
        self.assertEqual(after, before)

    def test_legacy_source_rows_and_apis_are_not_formal_candidates(self) -> None:
        """Formal lookups never read legacy source_snapshot rows or accept their references."""
        request = OfficialRequest(
            "cninfo", "annual_report", "SZ000001", "2025-12-31", "SZ"
        )
        legacy_id, created = self.store.record_snapshot(
            "cninfo",
            "annual_report",
            request.request_fingerprint,
            "f" * 64,
            "data/raw/legacy-source.json",
            1,
            "2026-08-20T08:00:00+00:00",
        )
        self.assertTrue(created)
        self.assertIsNone(
            self.repository.find_exact_verified(
                request,
                parser_id="cninfo-pdf",
                parser_version="cninfo-pdf-v1",
                mapping_version="cninfo-annual-v1",
                content_sha256="f" * 64,
                manifest_sha256="e" * 64,
            )
        )
        self.assertIsNone(self.store.get_formal_snapshot(legacy_id))
