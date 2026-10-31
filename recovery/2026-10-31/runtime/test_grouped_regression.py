"""Recovery tests: removing completion/identity/lock checks must break these."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

class RecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).with_name("grouped_regression.py")
        if path.exists():
            spec = importlib.util.spec_from_file_location("grouped_regression", path)
            cls.tool = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.tool)
        else:
            cls.tool = None

    def require_tool(self):
        self.assertIsNotNone(self.tool, "recoverable grouped runner is not implemented")
        return self.tool

    def test_groups_preserve_class_lifecycle_and_isolate_expensive_methods(self):
        tool = self.require_tool()
        ids = ["m.C.test_a", "m.C.test_b", "test_formal_final_performance.C.test_c"]
        self.assertEqual(tool.group_ids(ids), [["test_formal_final_performance.C.test_c"], ["m.C.test_a", "m.C.test_b"]])

    def record(self, directory):
        tool = self.require_tool()
        ids = ["m.C.test_a", "m.C.test_b"]
        log = Path(directory) / "attempt.log"
        summary = dict(ids=ids, passed=ids, tests_run=2, failures=0, errors=0, skipped=0)
        log.write_text("GROUP_SUMMARY " + json.dumps(summary) + "\n", encoding="utf-8")
        return dict(event="finish", identity="same", ids=ids, exit_code=0,
                    summary=summary, log=str(log), log_hash=tool.digest(log.read_bytes()))

    def test_complete_matching_attempt_can_resume(self):
        tool = self.require_tool()
        with tempfile.TemporaryDirectory() as directory:
            record = self.record(directory)
            self.assertTrue(tool.reusable(record, "same", record["ids"]))

    def test_changed_identity_cannot_resume(self):
        tool = self.require_tool()
        with tempfile.TemporaryDirectory() as directory:
            record = self.record(directory)
            self.assertFalse(tool.reusable(record, "other", record["ids"]))

    def test_missing_completion_or_exit_cannot_resume(self):
        tool = self.require_tool()
        with tempfile.TemporaryDirectory() as directory:
            record = self.record(directory)
            for field in ("summary", "exit_code", "log_hash"):
                broken = dict(record)
                del broken[field]
                self.assertFalse(tool.reusable(broken, "same", record["ids"]))

    def test_count_skip_failure_and_wrong_ids_cannot_resume(self):
        tool = self.require_tool()
        with tempfile.TemporaryDirectory() as directory:
            record = self.record(directory)
            for field, value in (("tests_run", 1), ("skipped", 1), ("failures", 1), ("errors", 1), ("passed", record["ids"][:1]), ("ids", list(reversed(record["ids"])))):
                broken = dict(record, summary=dict(record["summary"], **{field: value}))
                self.assertFalse(tool.reusable(broken, "same", record["ids"]))

    def test_changed_log_cannot_resume(self):
        tool = self.require_tool()
        with tempfile.TemporaryDirectory() as directory:
            record = self.record(directory)
            Path(record["log"]).write_text("tampered", encoding="utf-8")
            self.assertFalse(tool.reusable(record, "same", record["ids"]))

    def test_partial_journal_tail_never_becomes_completion(self):
        tool = self.require_tool()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "journal.jsonl"
            path.write_text('{"event":"start"}\n{"event":', encoding="utf-8")
            self.assertEqual(tool.read_journal(path), [{"event":"start"}])

    def test_append_after_partial_tail_preserves_completed_records(self):
        tool = self.require_tool()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "journal.jsonl"
            path.write_text('{"event":"start"}\n{"event":', encoding="utf-8")
            tool.append_record(path, {"event": "new_start"})
            records = tool.read_journal(path)
            self.assertEqual(records[0], {"event": "start"})
            self.assertEqual(records[-1]["event"], "new_start")

    def test_complete_append_journal_is_readable(self):
        tool = self.require_tool()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "journal.jsonl"
            tool.append_record(path, {"event": "start"})
            tool.append_record(path, {"event": "finish"})
            self.assertEqual([row["event"] for row in tool.read_journal(path)], ["start", "finish"])

    def test_duplicate_lock_rejected_and_released_lock_reusable(self):
        tool = self.require_tool()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "lock"
            with tool.exclusive_lock(path):
                with self.assertRaises(OSError):
                    with tool.exclusive_lock(path):
                        self.fail("duplicate run acquired lock")
            with tool.exclusive_lock(path):
                pass

    def test_group_selection_rejects_nonexistent_or_split_class(self):
        tool = self.require_tool()
        groups = [["m.C.test_a", "m.C.test_b"], ["n.D.test_a"]]
        self.assertEqual(tool.select_groups(groups, "m.C"), [groups[0]])
        for selector in ("m.C.test_a", "missing"):
            with self.assertRaises(ValueError):
                tool.select_groups(groups, selector)

if __name__ == "__main__":
    unittest.main()
