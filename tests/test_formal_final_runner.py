"""Runner contracts. All accepted inputs come from genuine producer boundaries."""

import atexit
import copy
import importlib
import importlib.util
import inspect
import io
import json
import sys
import pickle
import unittest
from types import SimpleNamespace
from dataclasses import FrozenInstanceError
from contextlib import redirect_stdout
from datetime import datetime, timezone
from unittest.mock import patch

from ashare_pipeline.formal_coverage_manifest import CoverageRequirement, FormalCoverageAuditor
from ashare_pipeline.formal_final_repository import FormalFinalRunRepository
from ashare_pipeline.formal_final_score_inputs import FormalFinalScoreInputRepository
from tests.formal_final_scoring_fixtures import FinalScoringFixture
from tests.test_formal_coverage_manifest import good


def runner_module(case):
    # Missing implementation is an assertion RED, not an import/setup error.
    case.assertIsNotNone(importlib.util.find_spec("ashare_pipeline.formal_final_runner"),
        "the thin offline Stage D runner has not been implemented")
    return importlib.import_module("ashare_pipeline.formal_final_runner")


def coverage_for(fixture, *, missing=False, frozen_hash=None, ids=None):
    requirements = [CoverageRequirement(frozen_hash or fixture.frozen.frozen_input_hash,
        sid, "financial", "selector", "2025", sid[:2], ("CNY",))
        for sid in (ids or sorted(fixture.templates))]
    freeze_at_utc = datetime.fromisoformat(fixture.frozen.as_of_utc).astimezone(timezone.utc).isoformat()
    return FormalCoverageAuditor(freeze_at_utc=freeze_at_utc,
        repository_validators={"financial": lambda *_: True}).audit(
        requirements, [] if missing else [good(row) for row in requirements])


def configured_runner(module, fixture, *, code_version="task11-test"):
    inputs = FormalFinalScoreInputRepository(fixture.feature_repository, fixture.context,
        fixture.range_store, registry_signature_verifier=fixture.verifier)
    repository = FormalFinalRunRepository(fixture.store, code_version=code_version)
    runner = module.FormalFinalScoreRunner(fixture.store, input_repository=inputs,
        run_repository=repository, registry_signature_verifier=fixture.verifier)
    return runner, repository


def run_arguments(fixture, coverage):
    return dict(frozen_input_hash=fixture.frozen.frozen_input_hash,
        scoring_registry=fixture.scoring, policy_registry=fixture.policy_registry,
        valuation_adapter_registry=fixture.valuation_registry, coverage_manifest=coverage)


_SMALL = None


def small_test_fixture():
    global _SMALL
    if _SMALL is None:
        fixture = FinalScoringFixture(peer_count=3, purpose="test")
        atexit.register(fixture.close)
        fixture.populate_final_inputs()
        _SMALL = fixture
    return _SMALL


class RunnerBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        case = unittest.TestCase()
        cls.module = runner_module(case)
        print("Task 11 complete small fixture: start", flush=True)
        cls.fixture = small_test_fixture()
        print("Task 11 complete small fixture: ready", flush=True)
        cls.addClassCleanup(cls.fixture.close)
        cls.runner, cls.repository = configured_runner(cls.module, cls.fixture)
        cls.coverage = coverage_for(cls.fixture)
        # Every successful branch consumes this real baseline. Failed gates
        # execute independently and cannot cache a validity decision.
        # Functional timing is unprofiled. Structural observers are confined to
        # the performance suite and never establish wall-clock pass thresholds.
        print("Task 11 baseline run: start", flush=True)
        with patch("socket.create_connection", side_effect=AssertionError("network forbidden")), patch(
                "socket.socket.connect", side_effect=AssertionError("network forbidden")):
            cls.preview = cls.runner.run_preview(**run_arguments(cls.fixture, cls.coverage))
        cls.preview_diagnostics = cls.runner.last_diagnostics
        case.assertEqual(cls.preview_diagnostics.counts["d1_builds"], 1)
        cls.observed_d1_builds = [cls.preview_diagnostics.counts["d1_builds"]]
        print("Task 11 baseline run: end", flush=True)
        print("Task 11 baseline:", json.dumps(dict(status=cls.preview.status,
            result_hash=cls.preview.result_hash, counts=dict(cls.preview_diagnostics.counts),
            stage_seconds=dict(cls.preview_diagnostics.stage_seconds),
            status_counts=dict(cls.preview_diagnostics.status_counts),
            reason_counts=dict(cls.preview_diagnostics.reason_counts),
            blockers=cls.preview_diagnostics.blockers), sort_keys=True), flush=True)

    @classmethod
    def tearDownClass(cls):
        if len(cls.observed_d1_builds) == 3:
            unittest.TestCase().assertEqual(sum(cls.observed_d1_builds), 3)
        print("Task 11 completed run counts:", json.dumps(dict(
            d1_builds_per_returned_run=cls.observed_d1_builds,
            d1_builds_total=sum(cls.observed_d1_builds)), sort_keys=True), flush=True)

    def setUp(self):
        self.assertIsNotNone(self.preview)

    def test_runner_has_no_network_or_legacy_score_input_path(self):
        fixture, runner, repository, receipt = self.fixture, self.runner, self.repository, self.preview
        self.assertIsNotNone(repository.get_run(receipt.run_id))
        for forbidden in ("legacy_scores", "score_items", "pre_policy_batch", "input_batch",
                          "allow_test", "bypass_official", "expected_purpose"):
            self.assertNotIn(forbidden, inspect.signature(runner.run_preview).parameters)
            with self.assertRaises(TypeError):
                runner.run_preview(**dict(run_arguments(fixture, coverage_for(fixture)),
                    **{forbidden: object()}))

    def test_runner_closes_root_and_all_batch_identities_before_d1(self):
        fixture = self.fixture
        runner, repository = configured_runner(self.module, fixture)
        # A mismatched coverage must be rejected even when D1 would itself fail.
        builds = []
        original_profile = sys.getprofile()
        def observe(frame, event, arg):
            if event == "call" and frame.f_code is FormalFinalScoreInputRepository.build_batch.__code__:
                builds.append(frame.f_code)
        bad = (coverage_for(fixture, frozen_hash="0" * 64),
               coverage_for(fixture, ids=[next(iter(fixture.templates))]))
        sys.setprofile(observe)
        try:
            for coverage in bad:
                with self.subTest(coverage=coverage.manifest_hash), self.assertRaises(ValueError):
                    runner.run_preview(**run_arguments(fixture, coverage))
        finally:
            sys.setprofile(original_profile)
        self.assertEqual(builds, [])
        self.assertIsNone(runner.last_diagnostics)

    def test_preview_accepts_genuine_test_root_and_records_explicit_blockers(self):
        fixture, repository, coverage, receipt = self.fixture, self.repository, self.coverage, self.preview
        diagnostics = self.preview_diagnostics
        snapshot = repository.get_run(receipt.run_id)
        self.assertEqual(snapshot.mode, "test_preview")
        self.assertEqual(receipt.status, "blocked")  # genuine incomplete three-member evidence
        self.assertIn("test_registry_not_official", diagnostics.blockers)
        self.assertIn("v9_release_not_implemented", diagnostics.blockers)
        self.assertFalse(diagnostics.official_ready)
        with self.assertRaises(ValueError):
            coverage.require_official_ready()
        with self.assertRaises((FrozenInstanceError, AttributeError)):
            diagnostics.mode = "official_candidate"
        with self.assertRaises(TypeError):
            diagnostics.counts["members"] = 999

    def test_official_candidate_rejects_failed_gates_without_writing_an_official_mode_row(self):
        fixture, runner, repository, preview = self.fixture, self.runner, self.repository, self.preview
        old = repository.get_run(preview.run_id)
        before = repository.list_runs_by_input_manifest(preview.input_manifest_hash)
        with self.assertRaises(ValueError):
            runner.run_official_candidate(**run_arguments(fixture, coverage_for(fixture)))
        self.assertEqual(repository.list_runs_by_input_manifest(preview.input_manifest_hash), before)
        self.assertEqual(repository.get_run(preview.run_id), old)

    def test_v1_v2_prepolicy_and_recovery_dtos_cannot_impersonate_stage_d_inputs(self):
        fixture, runner, repository = self.fixture, self.runner, self.repository
        arguments = run_arguments(fixture, self.coverage)
        receipt = self.preview
        recovered = repository.get_run(receipt.run_id)
        for key in ("coverage_manifest", "scoring_registry", "policy_registry",
                    "valuation_adapter_registry", "frozen_input_hash"):
            for fake in ({"schema_version": "formal-v1"}, {"schema_version": "formal-v2"},
                         recovered, recovered.to_dict(), receipt.input_batch.to_dict()):
                with self.subTest(key=key, fake=type(fake).__name__), self.assertRaises((ValueError, TypeError)):
                    runner.run_preview(**dict(arguments, **{key: fake}))
        with self.assertRaises(TypeError):
            runner.rebuild_affected(**arguments, prior_run_id=receipt.run_id,
                prior_input_manifest_hash=receipt.input_manifest_hash, changed_ids=["BJ430001"])

    def test_two_independent_runs_have_identical_canonical_result_hash(self):
        fixture, coverage, repository = self.fixture, self.coverage, self.repository
        second, _ = configured_runner(self.module, fixture)
        a = self.preview
        print("Task 11 independent run: start", flush=True)
        b = second.run_preview(**run_arguments(fixture, coverage))
        diagnostics = second.last_diagnostics
        self.assertEqual(diagnostics.counts["d1_builds"], 1)
        type(self).observed_d1_builds.append(diagnostics.counts["d1_builds"])
        print("Task 11 independent run: end", json.dumps(dict(run_id=b.run_id,
            input_manifest_hash=b.input_manifest_hash, result_hash=b.result_hash,
            counts=dict(diagnostics.counts), stage_seconds=dict(diagnostics.stage_seconds)),
            sort_keys=True), flush=True)
        self.assertNotEqual(a.run_id, b.run_id)
        self.assertEqual(a.input_manifest_hash, b.input_manifest_hash)
        self.assertEqual(a.result_hash, b.result_hash)
        self.assertEqual(repository.get_run(a.run_id).artifacts, repository.get_run(b.run_id).artifacts)

    def test_rebuild_affected_derives_changes_from_current_verified_manifest(self):
        fixture = self.fixture
        runner, repository = configured_runner(self.module, fixture)
        before = self.preview
        old = repository.get_run(before.run_id)
        print("Task 11 trusted rebuild: start", flush=True)
        after = runner.rebuild_affected(**run_arguments(fixture, coverage_for(fixture, missing=True)),
            prior_run_id=before.run_id, prior_input_manifest_hash=before.input_manifest_hash)
        diagnostics = runner.last_diagnostics
        self.assertEqual(diagnostics.counts["d1_builds"], 1)
        type(self).observed_d1_builds.append(diagnostics.counts["d1_builds"])
        print("Task 11 trusted rebuild: end", json.dumps(dict(run_id=after.run_id,
            prior_run_id=before.run_id, input_manifest_hash=after.input_manifest_hash,
            result_hash=after.result_hash, counts=dict(diagnostics.counts),
            stage_seconds=dict(diagnostics.stage_seconds)), sort_keys=True), flush=True)
        self.assertNotEqual(after.run_id, before.run_id)
        self.assertNotEqual(after.input_manifest_hash, before.input_manifest_hash)
        self.assertEqual(repository.get_run(before.run_id), old)
        self.assertTrue(runner.last_diagnostics.rebuild_plan.rescan_pools)
        self.assertEqual(runner.last_diagnostics.rebuild_plan.prior_manifest_hash,
                         before.input_manifest_hash)
        revoked = coverage_for(fixture)
        FormalCoverageAuditor.revoke(revoked)
        with self.assertRaises(ValueError):
            runner.rebuild_affected(**run_arguments(fixture, revoked), prior_run_id=before.run_id,
                prior_input_manifest_hash=before.input_manifest_hash)

    def test_initialized_runner_configuration_and_diagnostics_are_not_writable(self):
        for key in ("_inputs", "_runs", "_loader", "_store", "_last_diagnostics", "last_diagnostics"):
            with self.subTest(key=key), self.assertRaises((TypeError, AttributeError)):
                setattr(self.runner, key, object())

    def test_runner_cannot_be_copied_or_pickled(self):
        for operation in (copy.copy, copy.deepcopy, pickle.dumps):
            with self.subTest(operation=operation.__name__), self.assertRaises(TypeError):
                operation(self.runner)

    def test_repository_and_loader_ownership_changes_fail_closed(self):
        arguments = run_arguments(self.fixture, self.coverage)
        loader = self.runner._loader
        original = loader._repository
        loader._repository = object()
        try:
            with self.assertRaisesRegex(ValueError, "ownership|configuration"):
                self.runner.run_preview(**arguments)
        finally:
            loader._repository = original
        original = self.repository._store
        self.repository._store = object()
        try:
            with self.assertRaisesRegex(ValueError, "ownership|configuration"):
                self.runner.run_preview(**arguments)
        finally:
            self.repository._store = original

    def test_repository_instance_method_replacement_fails_closed(self):
        with patch.object(self.repository, "commit_complete_run", lambda **_: None):
            with self.assertRaisesRegex(ValueError, "configuration"):
                self.runner.run_preview(**run_arguments(self.fixture, self.coverage))

    def test_nonexact_modes_are_rejected_on_a_registered_runner(self):
        for mode in (None, True, "official", "preview", type("Mode", (str,), {})("test_preview")):
            with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, "mode"):
                self.runner.rebuild_affected(**run_arguments(self.fixture, self.coverage),
                    prior_run_id=self.preview.run_id, prior_input_manifest_hash=self.preview.input_manifest_hash,
                    mode=mode)


class RunnerMalformedInputsTests(unittest.TestCase):
    def test_configured_runner_binds_explicit_official_workspace_revision_without_io(self):
        self.assertIn("code_version", inspect.signature(configured_runner).parameters,
            "configured_runner must accept the official coverage workspace revision")
        revision = "a" * 40
        coverage = SimpleNamespace(to_dict=lambda: {"workspace_revision": revision})
        fixture = SimpleNamespace(feature_repository=object(), context=object(),
            range_store=object(), verifier=object(), store=object())

        class InputRepository:
            def __init__(self, *_args, **_kwargs):
                pass

        class RunRepository:
            def __init__(self, store, *, code_version):
                self._store = store
                self._code_version = code_version

        class Runner:
            def __init__(self, _store, *, input_repository, run_repository,
                         registry_signature_verifier):
                self.repository = run_repository

        module = SimpleNamespace(FormalFinalScoreRunner=Runner)
        with patch(__name__ + ".FormalFinalScoreInputRepository", InputRepository), \
                patch(__name__ + ".FormalFinalRunRepository", RunRepository):
            _, preview_repository = configured_runner(module, fixture)
            runner, repository = configured_runner(module, fixture,
                code_version=coverage.to_dict()["workspace_revision"])

        self.assertEqual(preview_repository._code_version, "task11-test")
        self.assertIs(runner.repository, repository)
        self.assertEqual(repository._code_version,
                         coverage.to_dict()["workspace_revision"])

    def test_shared_setup_never_schedules_a_background_traceback_timer(self):
        cls = RunnerBoundaryTests
        original_members = dict(vars(cls))
        original_lists = {name: list(value) for name, value in original_members.items()
            if type(value) is list}
        stop_before_fixture = RuntimeError("stop before genuine fixture construction")
        try:
            with patch("faulthandler.dump_traceback_later",
                    side_effect=AssertionError("background dump timer forbidden")), patch(
                    "faulthandler.cancel_dump_traceback_later",
                    side_effect=AssertionError("background dump timer forbidden")), patch.object(
                    sys.modules[__name__], "small_test_fixture", side_effect=stop_before_fixture), \
                    redirect_stdout(io.StringIO()):
                with self.assertRaises(Exception) as caught:
                    cls.setUpClass()
            # Reaching this deliberate stop proves setup passed the timer gate,
            # without constructing a fixture or accepting any substitute proof.
            self.assertIs(caught.exception, stop_before_fixture)
        finally:
            for name in tuple(vars(cls)):
                if name not in original_members:
                    delattr(cls, name)
            for name, value in original_members.items():
                if name in original_lists:
                    value[:] = original_lists[name]
                if vars(cls).get(name) is not value:
                    setattr(cls, name, value)

    def test_preview_coverage_helper_binds_exact_fixture_freeze(self):
        fixture = SimpleNamespace(templates={"SH600000": "general_nonfinancial"},
            frozen=SimpleNamespace(frozen_input_hash="frozen",
                as_of_utc="2026-08-31T15:00:00+08:00"))
        self.assertEqual(coverage_for(fixture).to_dict()["freeze_at_utc"],
            "2026-08-31T07:00:00+00:00")

    """Early gates do not need filesystem fixture setup or source calculation."""

    def setUp(self):
        self.module = runner_module(self)

    def test_non_repository_configuration_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "repositories"):
            self.module.FormalFinalScoreRunner(object(), input_repository=object(),
                run_repository=object(), registry_signature_verifier=object())

    def test_non_exact_mode_and_plain_inputs_fail_before_any_repository_access(self):
        runner = object.__new__(self.module.FormalFinalScoreRunner)
        arguments = dict(frozen_input_hash="frozen", scoring_registry={}, policy_registry={},
            valuation_adapter_registry={}, coverage_manifest={})
        for mode in (None, True, "official", "preview", type("Mode", (str,), {})("test_preview")):
            with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, "configuration"):
                runner.rebuild_affected(**arguments, prior_run_id="prior",
                    prior_input_manifest_hash="hash", mode=mode)
        for name in ("run_preview", "run_official_candidate"):
            with self.assertRaisesRegex(ValueError, "configuration"):
                getattr(runner, name)(**arguments)


class RunnerIdentityTests(unittest.TestCase):
    """Pure scalar identity checks do not construct or confer proof authority."""

    def setUp(self):
        self.module = runner_module(self)
        self.identity = ("root", "frozen", "universe", "2026-08-31T07:00:00+00:00",
            ("BJ430001", "SH600000", "SZ000001"))

    def test_frozen_time_representations_close_to_the_same_fixed_utc_instant(self):
        normalize = getattr(self.module, "_canonical_freeze", None)
        self.assertIsNotNone(normalize, "runner must close the fixed freeze instant")
        for value in ("2026-08-31T15:00:00+08:00", "2026-08-31T07:00:00+00:00"):
            with self.subTest(value=value):
                self.assertEqual(normalize(value), "2026-08-31T07:00:00+00:00")

    def test_changed_naive_or_malformed_freeze_is_rejected(self):
        normalize = getattr(self.module, "_canonical_freeze", None)
        self.assertIsNotNone(normalize, "runner must close the fixed freeze instant")
        for value in ("2026-08-31T07:00:01+00:00", "2026-08-30T07:00:00+00:00",
                      "2026-08-31T07:00:00", "not-a-time", None, True):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "as_of_utc"):
                normalize(value)

    def test_d1_identity_matches_only_exact_fields(self):
        require = getattr(self.module, "_require_d1_identity", None)
        self.assertIsNotNone(require, "runner must identify mismatched D1 fields")
        require(self.identity, self.identity)
        for index, field in enumerate(("registry_manifest_hash", "frozen_input_hash",
                "universe_hash", "as_of_utc", "security_ids")):
            actual = list(self.identity)
            actual[index] = "private-mismatch-value" if index < 4 else ("SH600000",)
            with self.subTest(field=field), self.assertRaises(ValueError) as caught:
                require(self.identity, tuple(actual))
            self.assertEqual(str(caught.exception), "runner D1 identity mismatch: " + field)

    def test_d1_security_order_and_membership_cannot_be_normalized_away(self):
        require = getattr(self.module, "_require_d1_identity", None)
        self.assertIsNotNone(require, "runner must identify mismatched D1 fields")
        for ids in (tuple(reversed(self.identity[4])), self.identity[4][:-1],
                    self.identity[4] + ("SZ000002",), self.identity[4] + ("SZ000001",)):
            with self.subTest(ids=ids), self.assertRaisesRegex(ValueError, "security_ids"):
                require(self.identity, self.identity[:4] + (ids,))

    def test_d1_retains_canonical_utc_and_lists_multiple_mismatches_in_field_order(self):
        require = getattr(self.module, "_require_d1_identity", None)
        self.assertIsNotNone(require, "runner must identify mismatched D1 fields")
        actual = ("another-root", *self.identity[1:3], "2026-08-31T15:00:00+08:00", self.identity[4])
        with self.assertRaises(ValueError) as caught:
            require(self.identity, actual)
        self.assertEqual(str(caught.exception),
            "runner D1 identity mismatch: registry_manifest_hash, as_of_utc")


class RunnerMethodIntegrityTests(unittest.TestCase):
    def test_callable_bound_method_impostors_fail_configuration_access(self):
        module = runner_module(self)
        # Configuration-only objects: no database initialization, signature,
        # published input repository or proof. Never invoke run/build/commit.
        path = module.Path(__file__).resolve().with_name("task11-never-created.db")
        self.assertFalse(path.exists())
        verifier = SimpleNamespace(verify=lambda *_args: False)
        store = module.StateStore(path, registry_signature_verifier=verifier)
        inputs = object.__new__(module.FormalFinalScoreInputRepository)
        runs = module.FormalFinalRunRepository(store, code_version="method-boundary-test")
        runner = module.FormalFinalScoreRunner(store, input_repository=inputs,
            run_repository=runs, registry_signature_verifier=verifier)
        loader = runner._loader
        # The real configuration guard accepts normal bound methods without
        # requiring any I/O or claiming the uninitialized input owner is a proof.
        self.assertIsNone(runner.last_diagnostics)

        class CallableImpostor:
            def __init__(self, method):
                self.__self__, self.__func__ = method.__self__, method.__func__
            def __call__(self, *_args, **_kwargs):
                raise AssertionError("impostor must not be executed")

        for owner, name in ((store, "get_verified_formal_frozen_universe"),
                (runs, "commit_complete_run"), (runs, "plan_rebuild"), (loader, "load")):
            impostor = CallableImpostor(getattr(owner, name))
            with self.subTest(entry=name), patch.object(owner, name, impostor):
                with self.assertRaisesRegex(ValueError, "configuration entry point"):
                    _ = runner.last_diagnostics
            self.assertIsNone(runner.last_diagnostics)
        with self.subTest(entry="MethodType binding"), patch.object(
                module, "MethodType", CallableImpostor, create=True):
            with self.assertRaisesRegex(ValueError, "authority"):
                _ = runner.last_diagnostics
        self.assertIsNone(runner.last_diagnostics)
        self.assertFalse(path.exists())

    def test_replaced_configuration_and_diagnostic_helpers_fail_before_repository_access(self):
        module = runner_module(self)
        forged = object.__new__(module.FormalFinalScoreRunner)
        for name in ("Path", "Counter", "MappingProxyType"):
            with self.subTest(name=name), patch.object(module, name, object):
                with self.assertRaisesRegex(ValueError, "authority"):
                    forged.run_preview(frozen_input_hash="frozen", scoring_registry={},
                        policy_registry={}, valuation_adapter_registry={}, coverage_manifest={})

    def test_diagnostic_constructor_replacement_fails_before_repository_access(self):
        module = runner_module(self)
        forged = object.__new__(module.FormalFinalScoreRunner)
        with patch.object(module.FormalFinalRunDiagnostics, "__init__", lambda *_args, **_kwargs: None):
            with self.assertRaisesRegex(ValueError, "authority"):
                forged.run_preview(frozen_input_hash="frozen", scoring_registry={},
                    policy_registry={}, valuation_adapter_registry={}, coverage_manifest={})

    def test_diagnostic_field_metadata_mutation_fails_before_repository_access(self):
        module = runner_module(self)
        forged = object.__new__(module.FormalFinalScoreRunner)
        field = module.FormalFinalRunDiagnostics.__dataclass_fields__["status"]
        with patch.object(field, "init", False):
            with self.assertRaisesRegex(ValueError, "authority"):
                forged.run_preview(frozen_input_hash="frozen", scoring_registry={},
                    policy_registry={}, valuation_adapter_registry={}, coverage_manifest={})

    def test_method_impostor_cannot_spoof_captured_identity_using_equality(self):
        module = runner_module(self)
        forged = object.__new__(module.FormalFinalScoreRunner)
        class EqualImpostor:
            def __eq__(self, _):
                return True
            def __call__(self, *_args, **_kwargs):
                return None
        with patch.object(module._RunnerOperations, "_run", EqualImpostor()):
            with self.assertRaisesRegex(ValueError, "authority"):
                forged.run_preview(frozen_input_hash="frozen", scoring_registry={},
                    policy_registry={}, valuation_adapter_registry={}, coverage_manifest={})

    def test_replaced_critical_type_fails_before_repository_access(self):
        module = runner_module(self)
        forged = object.__new__(module.FormalFinalScoreRunner)
        for name in ("StateStore", "FormalFinalScoreInputRepository", "FormalFinalRunRepository",
                     "FormalRegistryBundleLoader"):
            with self.subTest(name=name), patch.object(module, name, object):
                with self.assertRaisesRegex(ValueError, "authority"):
                    forged.run_preview(frozen_input_hash="frozen", scoring_registry={},
                        policy_registry={}, valuation_adapter_registry={}, coverage_manifest={})

    def test_replaced_builder_code_fails_before_repository_access(self):
        module = runner_module(self)
        forged = object.__new__(module.FormalFinalScoreRunner)
        function = module.select_formal_pools
        original_code = function.__code__
        # Keep the closure shape while changing the executable entry point.
        changed_code = original_code.replace(co_name="replaced_pool_entry")
        function.__code__ = changed_code
        try:
            with self.assertRaisesRegex(ValueError, "authority"):
                forged.run_preview(frozen_input_hash="frozen", scoring_registry={},
                    policy_registry={}, valuation_adapter_registry={}, coverage_manifest={})
        finally:
            function.__code__ = original_code

    def test_replaced_producer_module_entry_fails_before_repository_access(self):
        from ashare_pipeline import formal_pool
        module = runner_module(self)
        forged = object.__new__(module.FormalFinalScoreRunner)
        with patch.object(formal_pool, "select_formal_pools", lambda *_: None):
            with self.assertRaisesRegex(ValueError, "authority"):
                forged.run_preview(frozen_input_hash="frozen", scoring_registry={},
                    policy_registry={}, valuation_adapter_registry={}, coverage_manifest={})

    def test_runner_class_method_cannot_be_replaced(self):
        module = runner_module(self)
        owner = module.FormalFinalScoreRunner
        original = owner.run_preview
        try:
            with self.assertRaises(TypeError):
                setattr(owner, "run_preview", lambda *_: None)
        finally:
            if owner.run_preview is not original:
                setattr(owner, "run_preview", original)

    def test_unregistered_runner_fails_before_repository_access(self):
        module = runner_module(self)
        forged = object.__new__(module.FormalFinalScoreRunner)
        with self.assertRaisesRegex(ValueError, "configuration"):
            forged.run_preview(frozen_input_hash="frozen", scoring_registry={},
                policy_registry={}, valuation_adapter_registry={}, coverage_manifest={})

    def test_replaced_module_builder_fails_before_repository_access(self):
        module = runner_module(self)
        forged = object.__new__(module.FormalFinalScoreRunner)
        for name in ("build_final_score_card_batch", "build_formal_eligibility_batch", "select_formal_pools"):
            with self.subTest(name=name), patch.object(module, name, lambda *_: None):
                with self.assertRaisesRegex(ValueError, "authority"):
                    forged.run_preview(frozen_input_hash="frozen", scoring_registry={},
                        policy_registry={}, valuation_adapter_registry={}, coverage_manifest={})


if __name__ == "__main__":
    unittest.main()
