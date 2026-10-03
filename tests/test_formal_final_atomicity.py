"""Transaction failures must leave neither durable rows nor live child proofs."""

import copy
import inspect
import pickle
import sqlite3
import unittest
import weakref
from contextlib import closing, nullcontext
from unittest.mock import patch
from types import SimpleNamespace

from tests.test_formal_final_repository import minimal_batches
from tests.test_formal_final_migration import TABLES


class FormalFinalAuthorityBoundaryTests(unittest.TestCase):
    def test_official_writer_gates_live_environment_inside_reservation_before_first_insert(self):
        import ashare_pipeline.formal_final_repository as module
        from ashare_pipeline.state_store import StateStore, SCHEMA_VERSION
        from tests.test_formal_registry_manifest import AcceptingVerifier
        from pathlib import Path
        import tempfile

        events = []
        inserted = [False]
        sid = "SH600000"
        identity = dict(registry_manifest_hash="r" * 64, frozen_input_hash="f" * 64,
            universe_hash="u" * 64, as_of_utc="2026-08-31T07:00:00+00:00",
            security_ids=[sid])

        class Batch:
            def __init__(self, wire):
                self.wire = wire

            def require_verified(self):
                return None

            def to_dict(self):
                return self.wire

            def canonical_bytes(self):
                return module._serialize_payload(self.wire)[0].encode()

        class Coverage:
            blockers = ()
            manifest_hash = "c" * 64

            def require_verified(self):
                events.append("coverage_proof")

            def to_dict(self):
                return dict(authenticated_context=True, blockers=[],
                    rows=[dict(security_id=sid, exchange="SH",
                               frozen_input_hash=identity["frozen_input_hash"])],
                    freeze_at_utc=identity["as_of_utc"],
                    registry_manifest_hash=identity["registry_manifest_hash"],
                    frozen_input_hash=identity["frozen_input_hash"],
                    universe_records_hash=identity["universe_hash"], member_count=1)

            def require_official_ready(self):
                events.append(("live_gate", writer.in_transaction, inserted[0]))
                if inserted[0]:
                    raise AssertionError("official gate ran after Stage D insert")

            def canonical_bytes(self):
                return module._serialize_payload(self.to_dict())[0].encode()

        class Writer(FaultConnection):
            def execute(self, sql, *args):
                if sql == "BEGIN IMMEDIATE":
                    events.append("begin")
                if sql.startswith("SELECT * FROM formal_universe_snapshot"):
                    events.append("frozen")
                    return SimpleNamespace(fetchone=lambda: object())
                return super().execute(sql, *args)

        class Loader:
            def __init__(self, *_args):
                pass

            def load(self, root):
                case.assertEqual(root, identity["registry_manifest_hash"])
                events.append("registry")
                return SimpleNamespace(manifest=SimpleNamespace(
                    schema_version="formal-registry-manifest-v2"),
                    require_official=lambda: events.append("official_root"))

        case = self
        frozen = SimpleNamespace(members=(SimpleNamespace(security_id=sid),),
            universe_hash=identity["universe_hash"],
            registry_manifest_hash=identity["registry_manifest_hash"])
        batches = tuple(Batch(identity if index == 0 else
                              dict(eligibilities=[]) if index == 2 else dict(kind=index))
                        for index in range(4))

        def source_checkpoint(_connection):
            events.append("source_checkpoint")

        def insert(_connection, table, _rows, _columns):
            if not inserted[0]:
                inserted[0] = True
                events.append("first_insert")
                _connection.execute("UPDATE schema_migration SET version=version WHERE version=?",
                                    (SCHEMA_VERSION,))

        def postwrite_gate(_coverage, _mode):
            events.append(("provenance_gate", writer.in_transaction, inserted[0]))

        with tempfile.TemporaryDirectory() as directory:
            store = StateStore(Path(directory) / "ordering.sqlite",
                registry_signature_verifier=AcceptingVerifier())
            store.initialize()
            repository = module.FormalFinalRunRepository(store, code_version="ordering-test")
            with closing(Writer(store._connect())) as writer, patch.object(
                    module, "_BATCH_TYPES", (Batch,) * 4), patch.object(
                    module, "VerifiedCoverageManifest", Coverage), patch.object(
                    module, "FormalRegistryBundleLoader", Loader), patch.object(
                    store, "_formal_universe_from_connection", return_value=(frozen, None)), patch.object(
                    module, "_prepare_publication", return_value=SimpleNamespace(batches=batches)), patch.object(
                    module, "_publication_controls", return_value=(source_checkpoint,
                        lambda: None, lambda: None, lambda: None, lambda: None,
                        lambda: nullcontext())), patch.object(
                    module, "_project_rows", return_value={table: [dict(run_id="witness")]
                        for table in module._TABLES[2:]}), patch.object(
                    module, "_writer_connection", return_value=writer), patch.object(
                    module, "_insert_rows", insert), patch.object(
                    module, "_verify_persisted", return_value=None), patch.object(
                    module, "_coverage_postwrite_gate", postwrite_gate):
                repository.commit_complete_run(mode="official_candidate",
                    coverage_manifest=Coverage(), input_batch=batches[0],
                    score_batch=batches[1], eligibility_batch=batches[2],
                    pool_batch=batches[3])
        self.assertEqual([event for event in events if isinstance(event, tuple)],
                         [("live_gate", False, False), ("live_gate", True, False),
                          ("provenance_gate", True, True)])
        self.assertLess(events.index("begin"), events.index(("live_gate", True, False)))
        self.assertLess(events.index(("live_gate", True, False)), events.index("first_insert"))
        self.assertEqual(events.count("source_checkpoint"), 3)
        self.assertEqual(events.count("frozen"), 2)
        self.assertEqual(events.count("registry"), 2)
        self.assertEqual(events.count("official_root"), 2)

    def test_post_write_source_recheck_keeps_identity_liveness_root_and_checkpoint_without_live_hash(self):
        import ashare_pipeline.formal_final_repository as module

        events = []
        sid = "SH600000"
        identity = dict(registry_manifest_hash="r" * 64, frozen_input_hash="f" * 64,
            universe_hash="u" * 64, as_of_utc="2026-08-31T07:00:00+00:00",
            security_ids=[sid])
        connection = SimpleNamespace(wrote=False,
            execute=lambda *args: SimpleNamespace(fetchone=lambda: object()))

        class Coverage:
            revoked = False
            wrong_root = False

            def require_verified(self):
                events.append("coverage_live")
                if self.revoked:
                    raise ValueError("coverage proof revoked")

            def to_dict(self):
                return dict(authenticated_context=True, blockers=[],
                    rows=[dict(security_id=sid, exchange="SH",
                               frozen_input_hash=identity["frozen_input_hash"])],
                    freeze_at_utc=identity["as_of_utc"],
                    registry_manifest_hash=("x" * 64 if self.wrong_root else
                                            identity["registry_manifest_hash"]),
                    frozen_input_hash=identity["frozen_input_hash"],
                    universe_records_hash=identity["universe_hash"], member_count=1)

            def require_official_ready(self):
                events.append("live_environment")
                if connection.wrote:
                    raise AssertionError("post-write official gate hashed its own WAL")

        class Loader:
            revoked = False

            def __init__(self, *_args):
                pass

            def load(self, root):
                events.append("registry")
                self_test.assertEqual(root, identity["registry_manifest_hash"])
                return SimpleNamespace(manifest=SimpleNamespace(
                    schema_version="formal-registry-manifest-v2"),
                    require_official=self.require_official)

            def require_official(self):
                events.append("official_root")
                if Loader.revoked:
                    raise ValueError("official registry root revoked")

        self_test = self
        frozen = SimpleNamespace(members=(SimpleNamespace(security_id=sid),),
            universe_hash=identity["universe_hash"],
            registry_manifest_hash=identity["registry_manifest_hash"])
        store = SimpleNamespace(
            _formal_universe_from_connection=lambda *_args: (frozen, None),
            _require_registry_verifier=lambda: object())
        batch = SimpleNamespace(to_dict=lambda: identity)
        coverage = Coverage()

        source_changed = [False]

        def checkpoint(_connection):
            events.append("source_checkpoint")
            if source_changed[0]:
                raise ValueError("source checkpoint changed")

        with patch.object(module, "VerifiedCoverageManifest", Coverage), patch.object(
                module, "FormalRegistryBundleLoader", Loader):
            module._recheck_sources(store, coverage, (batch,), "official_candidate",
                checkpoint, connection)
            connection.wrote = True
            module._recheck_sources(store, coverage, (batch,), "official_candidate",
                checkpoint, connection)
            self.assertEqual(events.count("source_checkpoint"), 2)
            self.assertEqual(events.count("coverage_live"), 2)
            self.assertEqual(events.count("registry"), 2)
            self.assertEqual(events.count("official_root"), 2)
            self.assertEqual(events.count("live_environment"), 0)
            coverage.wrong_root = True
            with self.assertRaisesRegex(ValueError, "coverage root"):
                module._recheck_sources(store, coverage, (batch,), "official_candidate",
                    checkpoint, connection)
            coverage.wrong_root = False
            source_changed[0] = True
            with self.assertRaisesRegex(ValueError, "source checkpoint"):
                module._recheck_sources(store, coverage, (batch,), "official_candidate",
                    checkpoint, connection)
            source_changed[0] = False
            frozen.universe_hash = "x" * 64
            with self.assertRaisesRegex(ValueError, "frozen membership"):
                module._recheck_sources(store, coverage, (batch,), "official_candidate",
                    checkpoint, connection)
            frozen.universe_hash = identity["universe_hash"]
            Loader.revoked = True
            with self.assertRaisesRegex(ValueError, "registry root revoked"):
                module._recheck_sources(store, coverage, (batch,), "official_candidate",
                    checkpoint, connection)
            Loader.revoked = False
            coverage.revoked = True
            with self.assertRaisesRegex(ValueError, "revoked"):
                module._recheck_sources(store, coverage, (batch,), "official_candidate",
                    checkpoint, connection)

    def test_replaced_frame_provider_cannot_authenticate_prepare_or_controls(self):
        import ashare_pipeline.formal_final_publication as publication
        import ashare_pipeline.formal_final_repository as module
        from ashare_pipeline.state_store import StateStore
        from pathlib import Path
        from types import SimpleNamespace
        import tempfile

        class ProducerTripwire:
            def require_verified(self):
                raise AssertionError("forged frame reached producer authority")

        with tempfile.TemporaryDirectory() as directory:
            store = StateStore(Path(directory) / "frame.sqlite")
            store.initialize()
            repository = module.FormalFinalRunRepository(store, code_version="frame-attack-test")
            forged_frame = SimpleNamespace(f_code=type(repository).commit_complete_run.__code__,
                f_locals={"self": repository}, f_back=None)
            batches = {name: ProducerTripwire() for name in (
                "input_batch", "score_batch", "eligibility_batch", "pool_batch")}
            with patch.object(publication, "_getframe", lambda depth=0: forged_frame):
                for path, call in (
                    ("prepare", lambda: module._prepare_publication(**batches)),
                    ("take_controls", lambda: module._publication_controls(object())),
                ):
                    with self.subTest(path=path), self.assertRaisesRegex(ValueError,
                            "frame authority|authenticated repository writer"):
                        call()

    def test_exported_coordinator_has_no_publication_authority(self):
        from ashare_pipeline.formal_final_publication import FormalFinalPublicationCoordinator
        class Tripwire:
            def require_verified(self):
                raise AssertionError("caller reached producer authority")
        with self.assertRaisesRegex((ValueError, TypeError), "repository"):
            FormalFinalPublicationCoordinator.prepare(input_batch=Tripwire(), score_batch=Tripwire(),
                eligibility_batch=Tripwire(), pool_batch=Tripwire())

    def test_source_checkpoint_detects_real_database_and_provider_changes(self):
        from ashare_pipeline.formal_final_score_inputs import _current_source_checkpoint
        from ashare_pipeline.formal_metric_batch_guard import FormalMetricCurrentInputProvider
        from ashare_pipeline.formal_feature_repository import FormalFeatureCurrentInput
        from ashare_pipeline.state_store import StateStore
        from pathlib import Path
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            store = StateStore(Path(directory) / "source.sqlite")
            store.initialize()
            provider = FormalMetricCurrentInputProvider(store)
            with closing(store._connect()) as connection:
                connection.execute("CREATE TABLE source_evidence(id TEXT PRIMARY KEY,value TEXT)")
                connection.execute("INSERT INTO source_evidence VALUES('fact','original')")
                connection.commit()
            checkpoint = _current_source_checkpoint(store, provider)
            with closing(store._connect()) as connection:
                connection.execute("UPDATE source_evidence SET value='corrected'")
                connection.commit()
                connection.execute("BEGIN IMMEDIATE")
                with self.assertRaisesRegex(ValueError, "source"):
                    checkpoint.recheck(connection)
                connection.rollback()
            checkpoint = _current_source_checkpoint(store, provider)
            snapshot = FormalFeatureCurrentInput("SH600000", "2026-08-31T07:00:00+00:00",
                "general_nonfinancial", "a" * 64, "corrected-provider", (), (), True)
            provider.publish(snapshot)
            with self.assertRaisesRegex(ValueError, "provider"):
                checkpoint.recheck()
            checkpoint = _current_source_checkpoint(store, provider)
            with checkpoint.hold():
                with self.assertRaisesRegex(ValueError, "finalization"):
                    provider.publish(snapshot)
                with self.assertRaisesRegex(ValueError, "provider"):
                    checkpoint.recheck()


class FaultConnection:
    def __init__(self, connection, fail_table=None, before_commit=None):
        self.connection = connection
        self.fail_table = fail_table
        self.before_commit = before_commit
        self.writing = False

    def execute(self, sql, *args):
        if sql == "BEGIN IMMEDIATE":
            self.writing = True
        if self.fail_table and sql.startswith("INSERT INTO " + self.fail_table + " "):
            raise RuntimeError("injected table failure")
        return self.connection.execute(sql, *args)

    def executemany(self, sql, values):
        if self.fail_table and sql.startswith("INSERT INTO " + self.fail_table + " "):
            raise RuntimeError("injected table failure")
        return self.connection.executemany(sql, values)

    def commit(self):
        if self.before_commit and self.writing:
            self.before_commit()
        return self.connection.commit()

    def __getattr__(self, name):
        return getattr(self.connection, name)


class FormalFinalAtomicityContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture, cls.batches = minimal_batches()

    def setUp(self):
        from ashare_pipeline.formal_final_repository import FormalFinalRunRepository
        self.repository = FormalFinalRunRepository(self.fixture.store, code_version="task9-test")

    def counts(self):
        with closing(self.fixture.store._connect()) as connection:
            return tuple(connection.execute("SELECT COUNT(*) FROM " + name).fetchone()[0] for name in TABLES)

    def test_every_commit_failure_leaves_zero_stage_d_rows_and_revokes_children(self):
        import ashare_pipeline.formal_final_repository as module
        original = self.fixture.store._connect
        for table in TABLES:
            before = self.counts()
            captured = []
            prepare = module._prepare_publication
            def capture(*args, **kwargs):
                result = prepare(*args, **kwargs)
                captured.append(result)
                return result
            with self.subTest(table=table), patch.object(module, "_prepare_publication", capture), patch.object(
                    module, "_writer_connection", lambda store: FaultConnection(original(), fail_table=table)):
                with self.assertRaisesRegex(RuntimeError, "injected table failure"):
                    self.repository.commit_complete_run(**self.batches)
            self.assertEqual(self.counts(), before)
            self.assertTrue(captured)
            for proof in captured[0].batches + captured[0].children:
                with self.assertRaises(ValueError):
                    proof.require_verified()
            for proof in tuple(self.batches[key] for key in (
                    "input_batch", "score_batch", "eligibility_batch", "pool_batch")):
                proof.require_verified()

    def test_serialization_final_source_set_arm_and_commit_failures_rollback(self):
        import ashare_pipeline.formal_final_repository as module
        for name in ("_serialize_payload", "_recheck_sources", "_verify_persisted", "_arm_publication"):
            before = self.counts()
            original = getattr(module, name)
            calls = [0]
            def fail(*args, **kwargs):
                calls[0] += 1
                if name == "_recheck_sources" and calls[0] == 1:
                    return original(*args, **kwargs)
                raise RuntimeError("injected boundary")
            with self.subTest(boundary=name), patch.object(module, name, side_effect=fail):
                with self.assertRaisesRegex(RuntimeError, "injected boundary"):
                    self.repository.commit_complete_run(**self.batches)
            self.assertEqual(self.counts(), before)
        before = self.counts()
        original = self.fixture.store._connect
        def fail():
            raise sqlite3.OperationalError("injected commit")
        with patch.object(module, "_writer_connection", lambda store: FaultConnection(original(), before_commit=fail)):
            with self.assertRaisesRegex(sqlite3.OperationalError, "injected commit"):
                self.repository.commit_complete_run(**self.batches)
        self.assertEqual(self.counts(), before)

    def test_armed_proofs_remain_invisible_until_commit_returns(self):
        import ashare_pipeline.formal_final_repository as module
        captured = []
        prepare = module._prepare_publication
        def capture(*args, **kwargs):
            result = prepare(*args, **kwargs)
            captured.append(result)
            return result
        def observe():
            for name in ("prevalidate_commit", "arm", "mark_committed", "revoke"):
                self.assertFalse(hasattr(captured[0], name))
            # Even a callback inside the writer stack cannot take its capability.
            with self.assertRaisesRegex(ValueError, "repository"):
                module._publication_controls(captured[0])
            for proof in captured[0].batches + captured[0].children:
                with self.assertRaises(ValueError):
                    proof.require_verified()
        original = self.fixture.store._connect
        with patch.object(module, "_prepare_publication", capture), patch.object(module,
                "_writer_connection", lambda store: FaultConnection(original(), before_commit=observe)):
            receipt = self.repository.commit_complete_run(**self.batches)
        for proof in receipt.batches:
            proof.require_verified()

    def test_replaced_frame_provider_cannot_take_a_real_pending_publication(self):
        import ashare_pipeline.formal_final_publication as publication
        import ashare_pipeline.formal_final_repository as module
        from types import SimpleNamespace
        prepare = module._prepare_publication
        forged_frame = SimpleNamespace(f_code=type(self.repository).commit_complete_run.__code__,
            f_locals={"self": self.repository}, f_back=None)
        def capture(**kwargs):
            prepared = prepare(**kwargs)
            with patch.object(publication, "_getframe", lambda depth=0: forged_frame):
                with self.assertRaisesRegex(ValueError, "frame authority|authenticated repository writer"):
                    module._publication_controls(prepared)
            for proof in prepared.batches + prepared.children:
                with self.assertRaises(ValueError):
                    proof.require_verified()
            return prepared
        with patch.object(module, "_prepare_publication", capture):
            receipt = self.repository.commit_complete_run(**self.batches)
        for proof in receipt.batches:
            proof.require_verified()

    def test_post_commit_mark_committed_is_prevalidated_and_cannot_fail(self):
        import ashare_pipeline.formal_final_repository as module
        prepared = self.capture_aborted_preparation()
        for name in ("prevalidate_commit", "arm", "mark_committed", "revoke", "recheck"):
            self.assertFalse(hasattr(prepared, name))
        with self.assertRaisesRegex(ValueError, "repository"):
            module._publication_controls(prepared)
        with self.assertRaisesRegex(ValueError, "repository"):
            module._prepare_publication(**{key: self.batches[key] for key in (
                "input_batch", "score_batch", "eligibility_batch", "pool_batch")})
        # No source recheck, JSON, hashing, SQL or minting belongs to the flip.
        # Inspect code, never obtain a usable flip capability.
        import dis
        from types import CodeType
        flip = next(code for code in module._prepare_publication.__code__.co_consts
            if isinstance(code, CodeType) and code.co_name == "mark_committed")
        instructions = list(dis.get_instructions(flip))
        self.assertFalse(any("CALL" in item.opname or "BUILD" in item.opname or "RAISE" in item.opname
            for item in instructions))
        for proof in prepared.batches:
            with self.assertRaises(ValueError):
                proof.require_verified()

    def capture_aborted_preparation(self):
        import ashare_pipeline.formal_final_repository as module
        captured, prepare = [], module._prepare_publication
        def capture(**kwargs):
            result = prepare(**kwargs)
            captured.append(result)
            return result
        with patch.object(module, "_prepare_publication", capture), patch.object(
                module, "_writer_connection", side_effect=RuntimeError("abort prepared")):
            with self.assertRaisesRegex(RuntimeError, "abort prepared"):
                self.repository.commit_complete_run(**self.batches)
        return captured[0]

    def test_prepared_adapters_reject_constructor_copy_pickle_and_method_replacement(self):
        from ashare_pipeline.formal_final_publication import FormalFinalPublicationCoordinator
        prepared = self.capture_aborted_preparation()
        for proof in prepared.batches:
            cls = type(proof)
            with self.assertRaises(TypeError):
                cls()
            for action in (copy.copy, copy.deepcopy, pickle.dumps):
                with self.assertRaises((TypeError, ValueError)):
                    action(proof)
            with self.assertRaises((TypeError, ValueError)):
                object.__new__(cls).require_verified()
            with self.assertRaises(TypeError):
                setattr(cls, "require_verified", lambda self: None)
        with self.assertRaises(TypeError):
            FormalFinalPublicationCoordinator()
        with self.assertRaises(TypeError):
            setattr(type(prepared), "mark_committed", lambda self: None)

    def test_weak_reference_redirect_does_not_authenticate_forgery(self):
        source = self.batches["input_batch"]
        with patch.object(weakref, "ref", lambda item, *args: lambda: source):
            # Stage C captures weakref's original authority and deliberately
            # rejects this environment change during final source revalidation.
            with self.assertRaises(ValueError):
                self.repository.commit_complete_run(**self.batches)
        for proof in tuple(self.batches[key] for key in (
                "input_batch", "score_batch", "eligibility_batch", "pool_batch")):
            proof.require_verified()
            with self.assertRaises(ValueError):
                forged = object.__new__(type(proof))
                weakref.proxy(forged).require_verified()

    def test_source_revocation_invalidates_committed_descendants(self):
        from ashare_pipeline.formal_final_score_inputs import PolicyAdjustedScoreInputBatch
        receipt = self.repository.commit_complete_run(**self.batches)
        source = self.batches["input_batch"]
        record = inspect.getclosurevars(PolicyAdjustedScoreInputBatch.input_for).nonlocals["record"]
        proofs = inspect.getclosurevars(record).nonlocals["proofs"]
        state = proofs[id(source)][4]
        state[0] = False
        try:
            for proof in receipt.batches:
                with self.assertRaises(ValueError):
                    proof.require_verified()
        finally:
            state[0] = True

    def test_adapter_never_accepts_an_external_mint_capability(self):
        from ashare_pipeline.formal_final_score_inputs import _prepare_final_inputs
        from ashare_pipeline.formal_final_scoring import _prepare_final_scores
        from ashare_pipeline.formal_final_eligibility import _prepare_final_eligibility
        from ashare_pipeline.formal_pool import _prepare_final_pools
        inputs, scores, eligibility, pools = tuple(self.batches[key] for key in (
            "input_batch", "score_batch", "eligibility_batch", "pool_batch"))
        actions = (
            lambda: _prepare_final_inputs(inputs, object()),
            lambda: _prepare_final_scores(scores, inputs, {}, object(), source_input=inputs),
            lambda: _prepare_final_eligibility(eligibility, inputs, scores, object(),
                source_inputs=inputs, source_scores=scores),
            lambda: _prepare_final_pools(pools, eligibility, object(), source_eligibility=eligibility),
        )
        for action in actions:
            with self.assertRaises(ValueError):
                action()

    def test_final_set_recheck_detects_missing_member_and_changed_hash(self):
        import ashare_pipeline.formal_final_repository as module
        insert = module._insert_rows
        for damage in ("DELETE FROM formal_final_status WHERE run_id=? AND security_id='SH600000'",
                       "UPDATE formal_final_input SET payload_hash='changed' WHERE run_id=?"):
            before = self.counts()
            def corrupt(connection, table, rows, columns):
                insert(connection, table, rows, columns)
                if table == "formal_final_dependency":
                    connection.execute(damage, (rows[0]["run_id"],))
            with self.subTest(damage=damage), patch.object(module, "_insert_rows", corrupt):
                with self.assertRaisesRegex(ValueError, "persisted Stage D table differs"):
                    self.repository.commit_complete_run(**self.batches)
            self.assertEqual(self.counts(), before)

    def test_final_serialization_failure_after_inserts_rolls_back(self):
        import ashare_pipeline.formal_final_repository as module
        insert, serialize = module._insert_rows, module._serialize_payload
        writing_complete = [False]
        def insert_and_track(connection, table, rows, columns):
            insert(connection, table, rows, columns)
            if table == "formal_final_dependency":
                writing_complete[0] = True
        def fail_serialization(value):
            if writing_complete[0]:
                raise ValueError("injected final serialization")
            return serialize(value)
        before = self.counts()
        with patch.object(module, "_insert_rows", insert_and_track), patch.object(
                module, "_serialize_payload", fail_serialization):
            with self.assertRaisesRegex(ValueError, "injected final serialization"):
                self.repository.commit_complete_run(**self.batches)
        self.assertTrue(writing_complete[0])
        self.assertEqual(self.counts(), before)

    def test_connection_cleanup_cannot_revoke_a_durable_commit(self):
        import ashare_pipeline.formal_final_repository as module
        original = self.fixture.store._connect
        class CleanupFailure(FaultConnection):
            def close(self):
                self.connection.close()
                if self.writing:
                    raise RuntimeError("injected cleanup")
        with patch.object(module, "_writer_connection", lambda store: CleanupFailure(original())):
            receipt = self.repository.commit_complete_run(**self.batches)
        self.assertIsNotNone(self.repository.get_run(receipt.run_id))
        for proof in receipt.batches:
            proof.require_verified()

    def test_replaced_verification_method_cannot_open_an_unpublished_proof(self):
        prepared = self.capture_aborted_preparation()
        for proof in prepared.batches:
            base = type(proof).__mro__[1]
            original = vars(base)["require_verified"]
            type.__setattr__(base, "require_verified", lambda self: None)
            try:
                with self.assertRaises(ValueError):
                    proof.require_verified()
            finally:
                type.__setattr__(base, "require_verified", original)

    def test_adapter_method_replacement_fails_closed_before_write(self):
        from ashare_pipeline import formal_final_score_inputs, formal_final_scoring
        from ashare_pipeline import formal_final_eligibility, formal_pool
        for module, name in ((formal_final_score_inputs, "_prepare_final_inputs"),
                (formal_final_scoring, "_prepare_final_scores"),
                (formal_final_eligibility, "_prepare_final_eligibility"),
                (formal_pool, "_prepare_final_pools")):
            before = self.counts()
            with self.subTest(name=name), patch.object(module, name, lambda *args, **kwargs: None):
                with self.assertRaises(ValueError):
                    self.repository.commit_complete_run(**self.batches)
            self.assertEqual(self.counts(), before)

    def test_zz_real_source_correction_and_provider_change_after_preparation_abort(self):
        import ashare_pipeline.formal_final_repository as module
        from dataclasses import replace
        before = self.counts()
        prepare = module._prepare_publication
        captured = []
        with closing(self.fixture.store._connect()) as connection:
            row = connection.execute("SELECT id,content_sha256 FROM formal_source_snapshot LIMIT 1").fetchone()
        self.assertIsNotNone(row)

        def corrected_source(**kwargs):
            publication = prepare(**kwargs)
            captured.append(publication)
            with closing(self.fixture.store._connect()) as connection:
                connection.execute("UPDATE formal_source_snapshot SET content_sha256=? WHERE id=?",
                    ("e" * 64, row["id"]))
                connection.commit()
            return publication
        try:
            with patch.object(module, "_prepare_publication", corrected_source):
                with self.assertRaisesRegex(ValueError, "current-source"):
                    self.repository.commit_complete_run(**self.batches)
        finally:
            with closing(self.fixture.store._connect()) as connection:
                connection.execute("UPDATE formal_source_snapshot SET content_sha256=? WHERE id=?",
                    (row["content_sha256"], row["id"]))
                connection.commit()
        self.assertEqual(self.counts(), before)
        for proof in captured.pop().batches:
            with self.assertRaises(ValueError):
                proof.require_verified()

        def changed_provider(**kwargs):
            publication = prepare(**kwargs)
            captured.append(publication)
            sid = next(iter(self.fixture.templates))
            snapshot = self.fixture.provider.resolve_current_inputs(security_id=sid,
                as_of_utc=self.batches["input_batch"].as_of_utc,
                template_id=self.fixture.templates[sid],
                registry_manifest_hash=self.batches["input_batch"].registry_manifest_hash)
            self.fixture.provider.publish(replace(snapshot, batch_id="post-preparation-correction"))
            return publication
        with patch.object(module, "_prepare_publication", changed_provider):
            with self.assertRaisesRegex(ValueError, "current-source provider"):
                self.repository.commit_complete_run(**self.batches)
        self.assertEqual(self.counts(), before)
        for proof in captured.pop().batches:
            with self.assertRaises(ValueError):
                proof.require_verified()
