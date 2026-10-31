"""Local grouped verification only, never official publication authority."""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest
import uuid
from datetime import datetime, timezone

BASE = Path(r"D:\Projects\AShareQiheng\.tmp\grouped-checkpoint-756fdfc")
REVISION = "756fdfc38c27df4a9ea5ee01f15117ce7e9f3b00"
PRIORITY = "test_formal_final_performance.RunnerPerformanceTests.test_each_stage_is_built_once_and_diagnostics_do_not_change_result_hash"
HEAVY = {"test_formal_final_performance", "test_formal_final_integration", "test_formal_release_live_equivalence"}

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()

def group_ids(ids):
    classes = {}
    heavy = []
    for test_id in ids:
        if test_id.split(".")[0] in HEAVY:
            heavy.append([test_id])
        else:
            classes.setdefault(test_id.rsplit(".", 1)[0], []).append(test_id)
    priority = [group for group in heavy if group == [PRIORITY]]
    return priority + [group for group in heavy if group != [PRIORITY]] + list(classes.values())

def select_groups(groups, selector):
    selected = [group for group in groups if (group == [selector]
                or all(test_id.rsplit(".", 1)[0] == selector for test_id in group))]
    if not selected:
        raise ValueError("selector must name an existing complete group")
    return selected

def read_journal(path):
    if not path.exists():
        return []
    records = []
    lines = path.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            if index != len(lines) - 1:
                recovery = json.loads(lines[index + 1])
                if recovery != dict(event="partial_tail_preserved", tail_hash=digest(line.encode())):
                    raise ValueError("journal corruption before final partial line")
    return records

def append_record(path, record):
    # Preserve truncated bytes and explicitly bind their recovery marker.
    prefix = b""
    if path.exists():
        read_journal(path)
        raw = path.read_bytes()
        if raw and not raw.endswith(b"\n"):
            prefix = b"\n"
            tail = raw.split(b"\n")[-1]
            try:
                json.loads(tail)
            except json.JSONDecodeError:
                prefix += canonical(dict(event="partial_tail_preserved", tail_hash=digest(tail))) + b"\n"
    with path.open("ab") as stream:
        stream.write(prefix + canonical(dict(time_utc=datetime.now(timezone.utc).isoformat(), **record)) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())

def summary_from_log(path):
    summaries = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("GROUP_SUMMARY "):
            summaries.append(json.loads(line[len("GROUP_SUMMARY "):]))
    return summaries[0] if len(summaries) == 1 else None

def reusable(record, identity, ids):
    try:
        summary = record["summary"]
        log = Path(record["log"])
        return (record["event"] == "finish" and record["identity"] == identity
                and record["ids"] == ids and type(record["exit_code"]) is int
                and record["exit_code"] == 0 and digest(log.read_bytes()) == record["log_hash"]
                and summary == summary_from_log(log) and summary["ids"] == ids
                and summary["passed"] == ids and summary["tests_run"] == len(ids)
                and all(type(summary[key]) is int and summary[key] == 0
                        for key in ("failures", "errors", "skipped")))
    except (KeyError, TypeError, ValueError, OSError):
        return False

@contextmanager
def exclusive_lock(path):
    import msvcrt
    stream = path.open("a+b")
    acquired = False
    try:
        if path.stat().st_size == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        acquired = True
        yield
    finally:
        if acquired:
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        stream.close()

def flatten(suite):
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from flatten(test)
        else:
            yield test

def discover():
    sys.path.insert(0, os.getcwd())
    tests = list(flatten(unittest.defaultTestLoader.discover("tests")))
    ids = [test.id() for test in tests]
    if len(set(ids)) != len(ids) or any("_FailedTest" in test_id for test_id in ids):
        raise ValueError("test discovery incomplete or duplicate")
    return tests

def identity_for(ids):
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    if revision != REVISION:
        raise ValueError("checkpoint revision changed")
    if subprocess.check_output(["git", "status", "--porcelain", "--", "ashare_pipeline", "tests"], text=True).strip():
        raise ValueError("source/test tree dirty")
    files = []
    for folder in ("ashare_pipeline", "tests"):
        for path in sorted(Path(folder).rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                files.append([path.as_posix(), digest(path.read_bytes())])
    details = dict(revision=revision, files=files, ids=ids, python=sys.version,
                   executable=sys.executable, helper=digest(Path(__file__).read_bytes()),
                   temp=os.environ.get("TEMP"), tmp=os.environ.get("TMP"))
    return digest(canonical(details))

class RecordingResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.passed_ids = []

    def startTest(self, test):
        self.stream.writeln("TEST_STARTED " + test.id())
        self.stream.flush()
        super().startTest(test)

    def addSuccess(self, test):
        self.passed_ids.append(test.id())
        super().addSuccess(test)
        self.stream.flush()

def child(attempt):
    with exclusive_lock(BASE / "worker.lock"):
        return child_locked(attempt)

def child_locked(attempt):
    request = json.loads(attempt.read_text(encoding="utf-8"))
    tests = discover()
    all_ids = [test.id() for test in tests]
    if identity_for(all_ids) != request["identity"]:
        raise ValueError("child identity mismatch")
    by_id = {test.id(): test for test in tests}
    ids = request["ids"]
    suite = unittest.TestSuite(by_id[test_id] for test_id in ids)
    result = unittest.TextTestRunner(verbosity=2, resultclass=RecordingResult).run(suite)
    if identity_for(all_ids) != request["identity"]:
        raise ValueError("identity changed while testing")
    summary = dict(ids=ids, passed=result.passed_ids, tests_run=result.testsRun,
                   failures=len(result.failures), errors=len(result.errors), skipped=len(result.skipped))
    print("GROUP_SUMMARY " + json.dumps(summary), flush=True)
    return 0 if result.wasSuccessful() else 1

def run_group(identity, ids, all_ids):
    attempt_id = uuid.uuid4().hex
    request = BASE / (attempt_id + ".json")
    log = BASE / (attempt_id + ".log")
    journal = BASE / "journal.jsonl"
    with request.open("x", encoding="utf-8") as stream:
        json.dump(dict(identity=identity, ids=ids), stream)
        stream.flush()
        os.fsync(stream.fileno())
    start = dict(event="start", attempt=attempt_id, identity=identity, ids=ids, log=str(log))
    append_record(journal, start)
    print(json.dumps(start), flush=True)
    with log.open("x", encoding="utf-8") as stream:
        worker = subprocess.Popen([sys.executable, "-u", "-X", "faulthandler", __file__, "--child", str(request)], stdout=stream, stderr=stream)
        append_record(journal, dict(event="child_started", attempt=attempt_id, pid=worker.pid))
        while worker.poll() is None:
            time.sleep(30)
            if worker.poll() is None:
                append_record(journal, dict(event="alive", attempt=attempt_id, pid=worker.pid))
    summary = summary_from_log(log)
    finish = dict(event="finish", attempt=attempt_id, identity=identity, ids=ids,
                  log=str(log), log_hash=digest(log.read_bytes()), exit_code=worker.returncode,
                  summary=summary)
    # Successful child and unchanged parent identity are both required.
    if identity_for(all_ids) != identity:
        finish["identity"] = "changed"
    append_record(journal, finish)
    print(json.dumps(finish), flush=True)
    return reusable(finish, identity, ids)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--child", type=Path)
    parser.add_argument("--inventory", action="store_true")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--group")
    args = parser.parse_args()
    if args.child:
        return child(args.child)
    BASE.mkdir(parents=True, exist_ok=True)
    with exclusive_lock(BASE / "run.lock"):
        # A surviving child also fences restart after its supervisor dies.
        with exclusive_lock(BASE / "worker.lock"):
            pass
        tests = discover()
        ids = [test.id() for test in tests]
        identity = identity_for(ids)
        groups = group_ids(ids)
        if args.group:
            groups = select_groups(groups, args.group)
        records = read_journal(BASE / "journal.jsonl")
        pending = [group for group in groups if not any(reusable(record, identity, group) for record in records)]
        print(json.dumps(dict(identity=identity, tests=len(ids), groups=len(groups), pending_groups=len(pending), kind="grouped-only")), flush=True)
        if args.inventory:
            return 0
        for group in pending if args.all else pending[:1]:
            if not run_group(identity, group, ids):
                return 1
        return 0

if __name__ == "__main__":
    sys.exit(main())
