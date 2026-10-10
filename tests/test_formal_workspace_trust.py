"""Focused trust-boundary tests for the Stage D source workspace."""

from pathlib import Path
import inspect
import os
import subprocess
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import ashare_pipeline.formal_coverage_manifest as coverage_module
import ashare_pipeline.formal_final_repository as repository_module
import ashare_pipeline.formal_final_runner as runner_module
from ashare_pipeline.formal_coverage_manifest import CoverageRequirement, FormalCoverageAuditor


def _git(root, *args):
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


class WorkspaceGitIdentityTests(unittest.TestCase):
    def make_repository(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        source = root / "ashare_pipeline"
        source.mkdir()
        (source / "tracked.py").write_text("VALUE = 1\n", encoding="utf-8")
        _git(root, "init")
        _git(root, "config", "user.email", "stage-d-tests@example.invalid")
        _git(root, "config", "user.name", "Stage D Tests")
        _git(root, "add", "ashare_pipeline")
        _git(root, "commit", "-m", "fixture")
        return root

    def helper(self):
        helper = getattr(coverage_module, "_read_workspace_git_identity", None)
        self.assertIsNotNone(helper, "coverage must expose the workspace Git identity reader")
        return helper

    def test_clean_workspace_identity_binds_commit_and_ashare_pipeline_tree(self):
        root = self.make_repository()

        identity = self.helper()(root)

        self.assertEqual(identity, {
            "workspace_revision": _git(root, "rev-parse", "HEAD"),
            "workspace_tree": _git(root, "rev-parse", "HEAD:ashare_pipeline"),
        })

    def test_blob_reads_batch_files_but_keep_two_independent_passes(self):
        root = self.make_repository()
        for name in ('space name.py', 'second.py', 'third.py'):
            (root / 'ashare_pipeline' / name).write_text('VALUE = 1\n', encoding='utf-8')
        _git(root, 'add', 'ashare_pipeline')
        _git(root, 'commit', '-m', 'more files')
        calls = []

        def observed(command_root, args, binary=False):
            if args[0] == 'hash-object':
                calls.append(args)
            return coverage_module._run_workspace_git(command_root, args, binary)

        identity = self.helper()(root, _git=observed)
        self.assertEqual(identity['workspace_revision'], _git(root, 'rev-parse', 'HEAD'))
        self.assertEqual(len(calls), 2)

    def test_batch_hashes_preserve_text_and_ident_filters(self):
        root = self.make_repository()
        source = root / 'ashare_pipeline'
        _git(root, 'config', 'filter.trim.clean', 'git stripspace')
        _git(root, 'config', 'filter.trim.required', 'true')
        (source / '.gitattributes').write_text(
            '*.py text eol=crlf ident filter=trim\n', encoding='utf-8')
        (source / 'tracked.py').write_bytes(b'# $Id$\r\nVALUE = 1   \r\n')
        _git(root, 'add', 'ashare_pipeline')
        _git(root, 'commit', '-m', 'attributes')
        paths = ('ashare_pipeline/.gitattributes', 'ashare_pipeline/tracked.py')
        expected = [coverage_module._run_workspace_git(
            root, ('hash-object', '--path=' + path, str(root / path))).strip()
            for path in paths]
        actual = coverage_module._run_workspace_git(
            root, ('hash-object', '--', *paths)).splitlines()
        self.assertEqual(actual, expected)
        identity = self.helper()(root)
        self.assertEqual(identity['workspace_tree'], _git(root, 'rev-parse', 'HEAD:ashare_pipeline'))

    def test_large_batch_matches_scalar_reference_with_bounded_arguments(self):
        root = self.make_repository()
        for index in range(40):
            name = f'{index:03d}_' + 'x' * 160 + '.py'
            (root / 'ashare_pipeline' / name).write_text('VALUE = 1\n', encoding='utf-8')
        _git(root, 'add', 'ashare_pipeline')
        _git(root, 'commit', '-m', 'large batch')
        calls = []

        def scalar_reference(command_root, args, binary=False):
            if args[0] == 'hash-object' and args[1] == '--':
                return ''.join(coverage_module._run_workspace_git(
                    command_root, ('hash-object', '--path=' + path, str(command_root / path)))
                    for path in args[2:])
            return coverage_module._run_workspace_git(command_root, args, binary)

        def observed(command_root, args, binary=False):
            if args[0] == 'hash-object':
                calls.append(args)
                self.assertLessEqual(sum(2 * len(path) + 4 for path in args[2:]), 8000)
            return coverage_module._run_workspace_git(command_root, args, binary)

        start = time.perf_counter()
        expected = self.helper()(root, _git=scalar_reference)
        scalar_seconds = time.perf_counter() - start
        start = time.perf_counter()
        actual = self.helper()(root, _git=observed)
        batch_seconds = time.perf_counter() - start
        self.assertEqual(actual, expected)
        self.assertEqual(len(calls), 4)
        print(f'\nworkspace diagnostic: scalar={scalar_seconds:.3f}s '
              f'batch={batch_seconds:.3f}s; hash processes 82 -> {len(calls)}', flush=True)

    def test_malformed_batch_hash_output_fails_closed(self):
        root = self.make_repository()
        for output in ('', 'a' * 40 + '\n' + 'b' * 40 + '\n', 'a' * 40, 'z' * 40 + '\n'):
            with self.subTest(output=output):
                def malformed(command_root, args, binary=False):
                    if args[0] == 'hash-object':
                        return output
                    return coverage_module._run_workspace_git(command_root, args, binary)
                with self.assertRaisesRegex(ValueError, 'output is malformed'):
                    self.helper()(root, _git=malformed)

    def test_oversized_single_path_is_rejected_before_filesystem_or_hash_read(self):
        root = self.make_repository()
        oversized = 'ashare_pipeline/' + ('segment/' * 500) + 'tracked.py'

        def boundary(command_root, args, binary=False):
            output = coverage_module._run_workspace_git(command_root, args, binary)
            if args[0] in ('ls-tree', 'ls-files'):
                return output.replace(b'ashare_pipeline/tracked.py', oversized.encode())
            if args[0] == 'hash-object':
                self.fail('oversized argument must never reach Git')
            return output

        with self.assertRaisesRegex(ValueError, 'argument budget'):
            self.helper()(root, _git=boundary)

    def test_workspace_identity_rejects_every_source_worktree_change(self):
        cases = ("unstaged", "staged", "deleted", "untracked")
        for change in cases:
            with self.subTest(change=change):
                root = self.make_repository()
                tracked = root / "ashare_pipeline" / "tracked.py"
                if change in ("unstaged", "staged"):
                    tracked.write_text("VALUE = 2\n", encoding="utf-8")
                    if change == "staged":
                        _git(root, "add", "ashare_pipeline/tracked.py")
                elif change == "deleted":
                    tracked.unlink()
                else:
                    (root / "ashare_pipeline" / "untracked.py").write_text(
                        "VALUE = 3\n", encoding="utf-8")

                with self.assertRaisesRegex(ValueError, "workspace.*dirty"):
                    self.helper()(root)

    def test_workspace_recheck_rejects_a_tree_dirtied_after_identity_capture(self):
        root = self.make_repository()
        identity = self.helper()(root)
        require = getattr(coverage_module, "_require_workspace_git_identity", None)
        self.assertIsNotNone(require, "coverage must expose the workspace Git recheck")
        (root / "ashare_pipeline" / "tracked.py").write_text("VALUE = 4\n", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "workspace"):
            require(root, identity)

    def test_skip_worktree_cannot_hide_modified_tracked_source(self):
        root = self.make_repository()
        _git(root, "update-index", "--skip-worktree", "ashare_pipeline/tracked.py")
        (root / "ashare_pipeline" / "tracked.py").write_text(
            "VALUE = 99\n", encoding="utf-8")
        self.assertEqual(_git(root, "status", "--porcelain=v1", "--",
                              "ashare_pipeline"), "")

        with self.assertRaisesRegex(ValueError, "workspace"):
            self.helper()(root)

    def test_skip_worktree_change_after_first_blob_hash_is_rejected(self):
        root = self.make_repository()
        tracked = root / "ashare_pipeline" / "tracked.py"
        _git(root, "update-index", "--skip-worktree", "ashare_pipeline/tracked.py")
        command = coverage_module._run_workspace_git
        changed = []

        def race(command_root, args, binary=False):
            output = command(command_root, args, binary)
            if args[0] == "hash-object" and not changed:
                tracked.write_text("VALUE = 101\n", encoding="utf-8")
                changed.append(True)
            return output

        with self.assertRaisesRegex(ValueError, "changed during read|tracked source changed"):
            self.helper()(root, _git=race)
        self.assertEqual(changed, [True])

    def test_workspace_git_commands_ignore_inherited_git_environment(self):
        root = self.make_repository()
        poison = root / "attacker-index"
        environments = []

        def capture(command, **kwargs):
            environments.append(dict(kwargs["env"]))
            return subprocess.run(command, **kwargs)

        def controlled(command_root, args, binary=False):
            return coverage_module._run_workspace_git(
                command_root, args, binary, capture, os.environ)

        poisoned = {
            "GIT_INDEX_FILE": str(poison),
            "GIT_CONFIG_COUNT": "2",
            "GIT_CONFIG_KEY_0": "safe.directory",
            "GIT_CONFIG_VALUE_0": "attacker-root",
            "GIT_CONFIG_KEY_1": "core.hooksPath",
            "GIT_CONFIG_VALUE_1": str(root / "attacker-hooks"),
        }
        with patch.dict(os.environ, poisoned):
            try:
                identity = self.helper()(root, _git=controlled)
            except ValueError as exc:
                self.fail(f"workspace Git identity inherited GIT_INDEX_FILE: {exc}")

        self.assertEqual(identity["workspace_revision"], _git(root, "rev-parse", "HEAD"))
        self.assertTrue(environments)
        for environment in environments:
            with self.subTest():
                self.assertEqual(environment.get("GIT_CONFIG_COUNT"), "1")
                self.assertEqual(environment.get("GIT_CONFIG_KEY_0"), "safe.directory")
                self.assertEqual(environment.get("GIT_CONFIG_VALUE_0"), str(root))
                self.assertNotIn("GIT_INDEX_FILE", environment)
                self.assertNotIn("GIT_CONFIG_KEY_1", environment)
                self.assertNotIn("GIT_CONFIG_VALUE_1", environment)

    def test_git_command_stderr_and_nonzero_fail_closed(self):
        command = getattr(coverage_module, "_run_workspace_git", None)
        self.assertIsNotNone(command, "coverage must own a fail-closed Git command runner")
        root = self.make_repository()
        cases = (
            (SimpleNamespace(returncode=0, stdout="value\n", stderr="warning\n"),
             "emitted stderr"),
            (SimpleNamespace(returncode=7, stdout="", stderr=""), "command failed"),
        )
        for result, error in cases:
            with self.subTest(error=error), self.assertRaisesRegex(ValueError, error):
                command(root, ("rev-parse", "HEAD"), False,
                        lambda *_args, **_kwargs: result, {})

    def test_malformed_git_tree_output_fails_closed(self):
        helper = self.helper()
        self.assertIn("_git", inspect.signature(helper).parameters,
            "workspace identity reader must permit isolated command-boundary testing")
        root = self.make_repository()
        oid = "a" * 40

        def malformed(_root, args, binary=False, *_dependencies):
            if args == ("rev-parse", "--show-toplevel"):
                return str(root) + "\n"
            if args == ("status", "--porcelain=v1", "-z", "--untracked-files=all",
                        "--", "ashare_pipeline"):
                return b""
            if args in (("rev-parse", "HEAD"),
                        ("rev-parse", "HEAD:ashare_pipeline")):
                return oid + "\n"
            if args == ("ls-tree", "-r", "-z", "HEAD", "--", "ashare_pipeline"):
                return b"malformed-tree-record\0"
            raise AssertionError(args)

        with self.assertRaisesRegex(ValueError, "Git tree output is malformed"):
            helper(root, _git=malformed)

    def test_read_environment_rejects_an_unrelated_clean_repository(self):
        root = self.make_repository()
        database = root / "formal.db"
        status = root / "status.json"
        database.write_bytes(b"not-a-state-store")
        status.write_text("{}", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "loaded coverage project root"):
            coverage_module._read_environment(root, database, status, 8)


class CoverageMethodAuthorityTests(unittest.TestCase):
    method_names = (
        "require_official_ready",
        "require_preview_ready",
        "_recheck_official_provenance",
        "_recheck_official_workspace",
        "_data",
        "require_verified",
        "canonical_bytes",
        "to_dict",
    )

    def setUp(self):
        requirement = CoverageRequirement(
            "frozen", "SH600000", "financial", "selector", "2025", "SH")
        self.manifest = FormalCoverageAuditor().audit([requirement])
        self.manifest_type = type(self.manifest)

    def replace_method(self, name):
        original = getattr(self.manifest_type, name, None)
        self.assertIsNotNone(original, f"coverage authority must define {name}")
        owned = name in vars(self.manifest_type)
        type.__setattr__(self.manifest_type, name, lambda _self: None)

        def restore():
            if owned:
                type.__setattr__(self.manifest_type, name, original)
            else:
                type.__delattr__(self.manifest_type, name)

        return restore

    def test_repository_live_gate_rejects_every_coverage_method_replacement(self):
        for name in self.method_names:
            with self.subTest(name=name):
                restore = self.replace_method(name)
                try:
                    with self.assertRaisesRegex(ValueError, "coverage authority changed"):
                        repository_module._coverage_live_gate(
                            self.manifest, "official_candidate")
                finally:
                    restore()

    def test_repository_postwrite_gate_rejects_every_coverage_method_replacement(self):
        for name in self.method_names:
            with self.subTest(name=name):
                restore = self.replace_method(name)
                try:
                    with self.assertRaisesRegex(ValueError, "coverage authority changed"):
                        repository_module._coverage_postwrite_gate(
                            self.manifest, "test_preview")
                finally:
                    restore()

    def test_runner_rejects_every_coverage_method_replacement_without_io(self):
        for name in self.method_names:
            with self.subTest(name=name):
                restore = self.replace_method(name)
                try:
                    runner = object.__new__(runner_module.FormalFinalScoreRunner)
                    with self.assertRaisesRegex(ValueError, "runner authority entry point changed"):
                        getattr(runner, "run_preview")
                finally:
                    restore()

    def test_official_code_version_must_equal_coverage_workspace_revision(self):
        require = getattr(repository_module, "_require_official_code_version", None)
        self.assertIsNotNone(require, "repository must bind official code to coverage Git revision")
        coverage = {"workspace_revision": "a" * 40}
        require("test_preview", "release-label", coverage)
        require("official_candidate", "a" * 40, coverage)
        with self.assertRaisesRegex(ValueError, "code version"):
            require("official_candidate", "release-label", coverage)


if __name__ == "__main__":
    unittest.main()
