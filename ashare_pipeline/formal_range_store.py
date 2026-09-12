"""Append-only range evidence, fenced producer attempts, and authenticated rereads."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import uuid
import weakref


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _digest(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _text(value):
    if type(value) is not str or not value or value != value.strip():
        raise ValueError("range identity requires nonempty exact text")
    return value


def _time(value):
    _text(value)
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("range timestamp requires timezone")
    return parsed.astimezone(timezone.utc)


def _row_payload(row):
    if row is None:
        raise ValueError("range record absent")
    try:
        value = json.loads(row["payload_json"])
        raw = _canonical(value)
        if raw.decode() != row["payload_json"] or hashlib.sha256(raw).hexdigest() != row["payload_hash"]:
            raise ValueError("range record canonical payload differs")
        return value
    except (TypeError, KeyError, json.JSONDecodeError) as error:
        raise ValueError("invalid range record payload") from error


def _payload(value):
    return dict(payload_json=_canonical(value).decode(), payload_hash=_digest(value))


def _write_content(root, data, suffix):
    digest = hashlib.sha256(data).hexdigest()
    path = root / "formal-range" / digest[:2] / (digest + suffix)
    if not path.resolve().is_relative_to(root):
        raise ValueError("range content path escapes configured root")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(data)
    except FileExistsError:
        if path.read_bytes() != data:
            raise ValueError("content-addressed range file conflicts")
    return digest, str(path)


def _read_content(root, path_text, digest, suffix):
    expected = root / "formal-range" / digest[:2] / (digest + suffix)
    path = Path(path_text)
    if path != expected or not path.resolve().is_relative_to(root):
        raise ValueError("range content path is outside configured root")
    try:
        data = path.read_bytes()
    except OSError as error:
        raise ValueError("range content is missing") from error
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError("range content hash mismatch")
    return data


def _build_range_store_type(*, describe_request, restore_request, source_type,
                           source_binding, source_parse, fetch_type, fetch_snapshot,
                           mint_observation, observation_wire, require_execution):
    """Paired only by the source factory; no authority escapes this closure."""
    from .state_store import _range_state_store_authority, _V7_TABLE_DDL, _V7_INDEX_DDL
    from .formal_repository_identity import _require_repository_initialization
    from .formal_registry_manifest import FormalRegistryBundleLoader
    from .formal_feature_contract import load_signed_feature_registry
    from .formal_scoring_registry import load_formal_registry, RegistryApproval
    from .formal_policy_registry import load_formal_policy_registry
    from .formal_range_contract import load_policy_range_bindings

    StateStore, transaction, insert, schema_check, connect = _range_state_store_authority()
    records = {}

    def record(store):
        value = records.get(id(store))
        if type(store) is not FormalRangeStore or value is None or value[0]() is not store:
            raise ValueError("range store is forged or copied")
        _, state, path, root, verifier, verify_anchor, factory, cache = value
        _require_repository_initialization(state)
        if (type(state) is not StateStore or state.db_path.resolve() != path
                or getattr(state._connect, "__func__", None) is not connect):
            raise ValueError("range StateStore identity changed")
        if getattr(verifier, "verify") != verify_anchor:
            raise ValueError("range signature verifier changed")
        return state, root, verifier, factory, cache

    def load_binding(store, payload):
        state, _, verifier, factory, cache = record(store)
        root_hash = payload["request"]["registry_manifest_hash"]
        bundle = FormalRegistryBundleLoader(state, verifier).load(root_hash)
        key = root_hash, payload.get("binding_hash")
        if key not in cache:
            blob = bundle.blob("feature")
            vocabulary = load_signed_feature_registry(blob.canonical_json, blob.signature, blob.key_id,
                verifier, registry_manifest=bundle.manifest)
            scoring = load_formal_registry(bundle, RegistryApproval("official", bundle.manifest.scoring_registry_hash,
                bundle.manifest.approval_id), feature_registry=vocabulary)
            policy = load_formal_policy_registry(bundle, scoring_registry=scoring, feature_registry=vocabulary)
            bindings = load_policy_range_bindings(bundle, scoring_registry=scoring, policy_registry=policy)
            matches = []
            for rule in policy.to_dict()["rules"]:
                if rule["kind"] == "market_liquidity":
                    binding = bindings.for_rule(rule["rule_id"], payload["request"]["exchange"])
                    if binding.binding_hash == payload["binding_hash"]:
                        matches.append(binding)
            if len(matches) != 1:
                raise ValueError("range task binding absent or ambiguous")
            source = factory(matches[0])
            if type(source) is not source_type or source_binding(source) is not matches[0]:
                raise ValueError("range source factory returned a different binding")
            cache[key] = (matches[0], source)
        binding, source = cache[key]
        binding.require_current()
        source_binding(source)
        return binding, source

    def task_payload(row):
        value = _row_payload(row)
        if set(value) != {"schema_version", "request", "config", "source_registry_hash", "binding_hash", "parent", "refresh_generation"}:
            raise ValueError("range task fields invalid")
        if value["schema_version"] != "formal-range-task-v1":
            raise ValueError("range task schema invalid")
        request = value["request"]
        for key in ("registry_manifest_hash", "range_config_id"):
            if row[key] != request[key]:
                raise ValueError("range task identity mismatch")
        if row["request_fingerprint"] != _digest(request) or row["refresh_generation"] != value["refresh_generation"]:
            raise ValueError("range task request or generation changed")
        if row["id"] != _digest(value):
            raise ValueError("range task ID mismatch")
        return value

    def request_for(store, row, seen, *, execution=False):
        payload = task_payload(row)
        binding, source = load_binding(store, payload)
        parent = payload["parent"]
        previous = None
        if parent is not None:
            if type(parent) is not dict or set(parent) != {"task_id", "observation_hash", "mode"}:
                raise ValueError("range parent identity invalid")
            previous = read(store, parent["task_id"], historical=not execution, seen=seen)
            if observation_wire(previous)[1] != parent["observation_hash"]:
                raise ValueError("range parent changed")
        request = restore_request(source, payload["request"], previous, None if parent is None else parent["mode"])
        actual = describe_request(request)
        if any(_canonical(actual[key]) != _canonical(payload[key]) for key in ("request", "config", "source_registry_hash", "binding_hash")):
            raise ValueError("range task no longer matches genuine request")
        if execution:
            require_execution(request, store)
        return request, source

    def public(row, attempt=None):
        result = dict(row)
        result["payload"] = task_payload(row)
        result.pop("payload_json")
        result["attempt_id"] = None if attempt is None else attempt["id"]
        return result

    def owner(connection, task_id, worker_id, attempt_id, now):
        row = connection.execute("SELECT * FROM formal_range_task WHERE id=?", (task_id,)).fetchone()
        task_payload(row)
        attempt = connection.execute("SELECT * FROM formal_range_attempt WHERE id=?", (attempt_id,)).fetchone()
        expected = dict(task_id=task_id, attempt_no=row["attempt_no"], worker_id=worker_id, task_payload_hash=row["payload_hash"])
        if (row["status"] != "leased" or row["worker_id"] != worker_id
                or _time(row["lease_expires_at"]) <= _time(now) or attempt is None
                or attempt["task_id"] != task_id or attempt["attempt_no"] != row["attempt_no"]
                or attempt["worker_id"] != worker_id or attempt["finished_at"] is not None
                or attempt["outcome"] is not None or attempt["lease_expires_at"] != row["lease_expires_at"]
                or _canonical(_row_payload(attempt)) != _canonical(expected)):
            raise ValueError("range producer lease lost or expired")
        return row, attempt

    def read(store, task_id, *, historical=False, seen=()):
        state, root, _, _, _ = record(store)
        _text(task_id)
        if task_id in seen:
            raise ValueError("range parent cycle")
        with transaction(state) as connection:
            task = connection.execute("SELECT * FROM formal_range_task WHERE id=?", (task_id,)).fetchone()
            payload = task_payload(task)
            if task["status"] != "verified":
                raise ValueError("range task is not verified")
            snapshot = connection.execute("SELECT * FROM formal_range_snapshot WHERE task_id=?", (task_id,)).fetchone()
            receipt = connection.execute("SELECT * FROM formal_range_normalization_receipt WHERE task_id=?", (task_id,)).fetchone()
            manifest = _row_payload(snapshot)
            receipt_wire = _row_payload(receipt)
            producers = connection.execute("SELECT * FROM formal_range_attempt WHERE task_id=? AND outcome='verified'", (task_id,)).fetchall()
            if len(producers) != 1:
                raise ValueError("range verified producer absent or ambiguous")
            attempt = producers[0]
            expected_attempt = dict(task_id=task_id, attempt_no=task["attempt_no"], worker_id=attempt["worker_id"], task_payload_hash=task["payload_hash"])
            if (_canonical(_row_payload(attempt)) != _canonical(expected_attempt) or attempt["attempt_no"] != task["attempt_no"]
                    or attempt["finished_at"] is None or _time(attempt["finished_at"]) >= _time(attempt["lease_expires_at"])
                    or task["worker_id"] is not None or task["lease_expires_at"] is not None
                    or task["next_retry_at"] is not None or task["error_json"] is not None):
                raise ValueError("range verified producer inconsistent")
            for item in (snapshot, receipt):
                for key in ("task_id", "request_fingerprint", "registry_manifest_hash", "range_config_id", "refresh_generation"):
                    expected = task_id if key == "task_id" else task[key]
                    if item[key] != expected:
                        raise ValueError("range snapshot/receipt task identity mismatch")
            if (receipt["attempt_id"] != attempt["id"] or receipt["snapshot_id"] != snapshot["id"]
                    or snapshot["id"] != snapshot["manifest_sha256"]
                    or receipt["manifest_sha256"] != snapshot["manifest_sha256"]
                    or receipt["content_sha256"] != snapshot["content_sha256"]):
                raise ValueError("range receipt producer or content mismatch")
            raw = _read_content(root, snapshot["content_path"], snapshot["content_sha256"], ".raw")
            manifest_bytes = _read_content(root, snapshot["manifest_path"], snapshot["manifest_sha256"], ".json")
            if manifest_bytes != _canonical(manifest):
                raise ValueError("range manifest payload mismatch")
            if set(manifest) != {"schema_version", "task_payload", "task_id", "attempt_id", "worker_id", "fetch"}:
                raise ValueError("range manifest fields invalid")
            if (manifest["schema_version"] != "formal-range-snapshot-v1" or _canonical(manifest["task_payload"]) != _canonical(payload)
                    or manifest["task_id"] != task_id or manifest["attempt_id"] != attempt["id"]
                    or manifest["worker_id"] != attempt["worker_id"]):
                raise ValueError("range manifest producer mismatch")
            task_copy, snapshot_copy, receipt_copy = dict(task), dict(snapshot), dict(receipt)
            attempt_copy = dict(attempt)
        request, source = request_for(store, task_copy, (*seen, task_id))
        document = source_parse(source, request, raw_bytes=raw, manifest=manifest["fetch"]).to_dict()
        expected_receipt = dict(schema_version="formal-range-normalization-receipt-v1", task_id=task_id,
            snapshot_id=snapshot_copy["id"], attempt_id=attempt["id"], worker_id=attempt["worker_id"],
            task_payload_hash=task_copy["payload_hash"], manifest_sha256=snapshot_copy["manifest_sha256"],
            content_sha256=snapshot_copy["content_sha256"], normalization_hash=_digest(document),
            fetch=manifest["fetch"], refresh_generation=task_copy["refresh_generation"])
        if _canonical(receipt_wire) != _canonical(expected_receipt) or receipt_copy["normalization_hash"] != _digest(document):
            raise ValueError("range normalization receipt differs from actual output")
        if task_copy["result_json"] != _canonical(dict(snapshot_id=snapshot_copy["id"], receipt_hash=receipt_copy["payload_hash"])).decode():
            raise ValueError("range verified result differs")
        with transaction(state) as connection:
            for table, key, value in (("formal_range_task", "id", task_copy), ("formal_range_snapshot", "task_id", snapshot_copy),
                                      ("formal_range_normalization_receipt", "task_id", receipt_copy)):
                row = connection.execute(f"SELECT * FROM {table} WHERE {key}=?", (task_id,)).fetchone()
                if row is None or dict(row) != value:
                    raise ValueError("range records changed during verification")
            current_attempts = connection.execute("SELECT * FROM formal_range_attempt WHERE task_id=? AND outcome='verified'", (task_id,)).fetchall()
            if len(current_attempts) != 1 or dict(current_attempts[0]) != attempt_copy:
                raise ValueError("range producer changed during verification")
            if (_read_content(root, snapshot_copy["content_path"], snapshot_copy["content_sha256"], ".raw") != raw
                    or _read_content(root, snapshot_copy["manifest_path"], snapshot_copy["manifest_sha256"], ".json") != manifest_bytes):
                raise ValueError("range raw files changed during verification")
        wire = dict(request=payload["request"], document=document, receipt=dict(receipt_wire, recorded_at=receipt_copy["recorded_at"]),
            snapshot=dict(manifest, **{key: snapshot_copy[key] for key in ("id", "content_path", "manifest_path", "content_sha256", "manifest_sha256")}),
            task=public(task_copy, attempt), generation=dict(refresh_generation=task_copy["refresh_generation"], upstream_generation=document["upstream_generation"]))
        return mint_observation(store, wire, historical)

    def candidate_snapshot(connection, fingerprint):
        rows = connection.execute("SELECT * FROM formal_range_task WHERE request_fingerprint=? AND status='verified' ORDER BY id", (fingerprint,)).fetchall()
        return tuple(_canonical(dict(row)) for row in rows)

    def check_candidate_snapshots(connection, snapshots):
        for fingerprint, expected in snapshots:
            if candidate_snapshot(connection, fingerprint) != expected:
                raise ValueError("range current candidates changed during verification")

    def finish_current_check(store, snapshots):
        state, _, _, _, _ = record(store)
        with transaction(state) as connection:
            check_candidate_snapshots(connection, snapshots)

    def current_candidates(store, fingerprint):
        state, _, _, _, _ = record(store)
        with transaction(state) as connection:
            snapshot = candidate_snapshot(connection, fingerprint)
        token = (fingerprint, snapshot)
        ids = [json.loads(row)["id"] for row in snapshot]
        candidates = [read(store, identity) for identity in ids]
        if not candidates:
            return [], token
        def compare(left, right):
            a, b = observation_wire(left)[0], observation_wire(right)[0]
            da, db = a["document"], b["document"]
            same = (da["upstream_generation"], a["snapshot"]["content_sha256"]) == (db["upstream_generation"], b["snapshot"]["content_sha256"])
            ua, ub = da["source_updated_at_utc"], db["source_updated_at_utc"]
            if da["published_precision"] != db["published_precision"] or (ua is None) != (ub is None):
                if same:
                    return 0
                raise ValueError("range source versions incomparable")
            pa, pb = _time(da["published_at_utc"]), _time(db["published_at_utc"])
            va, vb = (pa, pb) if ua is None else (_time(ua), _time(ub))
            if (va > vb and pa < pb) or (va < vb and pa > pb):
                raise ValueError("range source publication and update conflict")
            if va == vb and not same:
                raise ValueError("same leading range version has different content")
            return (va > vb) - (va < vb)
        leading = []
        for candidate in candidates:
            if all(compare(candidate, other) >= 0 for other in candidates):
                leading.append(candidate)
        if not leading:
            raise ValueError("range leading version cannot be established")
        return leading, token

    def require_parent_chain(store, wire, snapshots):
        parent = wire["task"]["payload"]["parent"]
        if parent is not None:
            previous = read(store, parent["task_id"])
            parent_wire, parent_hash = observation_wire(previous)
            if parent_hash != parent["observation_hash"]:
                raise ValueError("range current parent changed")
            qualify_current(store, parent_wire, parent_hash, snapshots)

    def qualify_current(store, wire, digest, snapshots):
        leading, token = current_candidates(store, _digest(wire["request"]))
        snapshots.append(token)
        if digest not in [observation_wire(item)[1] for item in leading]:
            raise ValueError("range observation superseded")
        require_parent_chain(store, wire, snapshots)

    def require_current(store, wire, digest):
        snapshots = []
        qualify_current(store, wire, digest, snapshots)
        finish_current_check(store, snapshots)

    def parent_candidate_snapshots(connection, task):
        snapshots, seen = [], {task["id"]}
        parent = task_payload(task)["parent"]
        while parent is not None:
            if type(parent) is not dict or set(parent) != {"task_id", "observation_hash", "mode"}:
                raise ValueError("range parent identity invalid")
            if parent["task_id"] in seen:
                raise ValueError("range parent chain is cyclic")
            seen.add(parent["task_id"])
            row = connection.execute("SELECT * FROM formal_range_task WHERE id=?", (parent["task_id"],)).fetchone()
            parent = task_payload(row)["parent"]
            fingerprint = row["request_fingerprint"]
            snapshots.append((fingerprint, candidate_snapshot(connection, fingerprint)))
        return snapshots

    class FormalRangeStore:
        def __init__(self, state_store, *, root, signature_verifier, source_factory):
            if type(self) is not FormalRangeStore or type(state_store) is not StateStore:
                raise ValueError("range store requires exact StateStore")
            _require_repository_initialization(state_store)
            if not callable(source_factory) or not callable(getattr(signature_verifier, "verify", None)):
                raise ValueError("range store dependencies invalid")
            with transaction(state_store) as connection:
                schema_check(connection, _V7_TABLE_DDL, _V7_INDEX_DDL, "v7 schema")
                if connection.execute("SELECT count(*) FROM schema_migration WHERE version=7").fetchone()[0] != 1:
                    raise ValueError("range store needs initialized V7 schema")
            identity = id(self)
            records[identity] = (weakref.ref(self, lambda _: records.pop(identity, None)), state_store,
                state_store.db_path.resolve(), Path(root).resolve(), signature_verifier,
                signature_verifier.verify, source_factory, {})

        def enqueue(self, request, *, refresh_generation):
            state, _, _, _, _ = record(self)
            _text(refresh_generation)
            require_execution(request, self)
            payload = dict(schema_version="formal-range-task-v1", **describe_request(request), refresh_generation=refresh_generation)
            task_id = _digest(payload)
            now = _utc_now()
            wire = payload["request"]
            row = dict(id=task_id, request_fingerprint=_digest(wire), registry_manifest_hash=wire["registry_manifest_hash"],
                range_config_id=wire["range_config_id"], refresh_generation=refresh_generation, **_payload(payload),
                status="pending", worker_id=None, lease_expires_at=None, attempt_no=0, next_retry_at=None,
                result_json=None, error_json=None, created_at=now, updated_at=now)
            load_binding(self, payload)
            with transaction(state, immediate=True) as connection:
                existing = connection.execute("SELECT * FROM formal_range_task WHERE request_fingerprint=? AND registry_manifest_hash=? AND range_config_id=? AND refresh_generation=?",
                    tuple(row[key] for key in ("request_fingerprint", "registry_manifest_hash", "range_config_id", "refresh_generation"))).fetchone()
                if existing is not None:
                    if _canonical(task_payload(existing)) != _canonical(payload):
                        raise ValueError("range task natural key conflicts")
                    result = public(existing)
                else:
                    insert(connection, "formal_range_task", row)
                    result = public(row)
            if result["status"] == "verified":
                read(self, result["id"])
            return result

        def lease_next(self, worker_id, *, lease_seconds):
            state, _, _, _, _ = record(self)
            _text(worker_id)
            if type(lease_seconds) is not int or lease_seconds <= 0:
                raise ValueError("lease duration must be positive exact integer")
            while True:
                now = _utc_now()
                with transaction(state) as connection:
                    rows = connection.execute("SELECT * FROM formal_range_task WHERE status IN ('pending','retryable_failed','leased') ORDER BY created_at,id").fetchall()
                    row = next((r for r in rows if r["status"] == "pending" or
                        (r["status"] == "retryable_failed" and _time(r["next_retry_at"]) <= _time(now)) or
                        (r["status"] == "leased" and _time(r["lease_expires_at"]) <= _time(now))), None)
                    if row is None:
                        return None
                    candidate = dict(row)
                request, source = request_for(self, candidate, (), execution=True)
                with transaction(state, immediate=True) as connection:
                    row = connection.execute("SELECT * FROM formal_range_task WHERE id=?", (candidate["id"],)).fetchone()
                    if row is None or dict(row) != candidate:
                        continue
                    now = _utc_now()
                    expires = (_time(now) + timedelta(seconds=lease_seconds)).isoformat()
                    if row["status"] == "leased":
                        count = connection.execute("UPDATE formal_range_attempt SET finished_at=?, outcome='expired' WHERE task_id=? AND attempt_no=? AND outcome IS NULL",
                            (now, row["id"], row["attempt_no"])).rowcount
                        if count != 1:
                            raise ValueError("range expired attempt missing")
                    number = row["attempt_no"] + 1
                    attempt = dict(id=str(uuid.uuid4()), task_id=row["id"], attempt_no=number, worker_id=worker_id,
                        leased_at=now, lease_expires_at=expires, finished_at=None, outcome=None,
                        **_payload(dict(task_id=row["id"], attempt_no=number, worker_id=worker_id, task_payload_hash=row["payload_hash"])))
                    insert(connection, "formal_range_attempt", attempt)
                    connection.execute("UPDATE formal_range_task SET status='leased', worker_id=?,lease_expires_at=?,attempt_no=?,next_retry_at=NULL,error_json=NULL,updated_at=? WHERE id=?",
                        (worker_id, expires, number, now, row["id"]))
                    result = public(connection.execute("SELECT * FROM formal_range_task WHERE id=?", (row["id"],)).fetchone(), attempt)
                return dict(result, request=request, binding=source_binding(source))

        def renew(self, task_id, worker_id, attempt_id, *, lease_seconds):
            state, _, _, _, _ = record(self)
            if type(lease_seconds) is not int or lease_seconds <= 0:
                raise ValueError("lease duration must be positive exact integer")
            now = _utc_now()
            expires = (_time(now) + timedelta(seconds=lease_seconds)).isoformat()
            with transaction(state, immediate=True) as connection:
                _, attempt = owner(connection, task_id, worker_id, attempt_id, now)
                connection.execute("UPDATE formal_range_task SET lease_expires_at=?,updated_at=? WHERE id=?", (expires, now, task_id))
                connection.execute("UPDATE formal_range_attempt SET lease_expires_at=? WHERE id=?", (expires, attempt_id))
                return public(connection.execute("SELECT * FROM formal_range_task WHERE id=?", (task_id,)).fetchone(), attempt)

        def fail(self, task_id, worker_id, attempt_id, *, code, retryable, next_retry_at):
            state, _, _, _, _ = record(self)
            _text(code)
            if type(retryable) is not bool or (retryable and next_retry_at is None) or (not retryable and next_retry_at is not None):
                raise ValueError("range failure retry shape invalid")
            now = _utc_now()
            if retryable and _time(next_retry_at) <= _time(now):
                raise ValueError("retry must be in future")
            status = "retryable_failed" if retryable else "terminal_failed"
            with transaction(state, immediate=True) as connection:
                _, attempt = owner(connection, task_id, worker_id, attempt_id, now)
                connection.execute("UPDATE formal_range_attempt SET outcome=?,finished_at=? WHERE id=?", (status, now, attempt_id))
                connection.execute("UPDATE formal_range_task SET status=?,worker_id=NULL,lease_expires_at=NULL,next_retry_at=?,error_json=?,updated_at=? WHERE id=?",
                    (status, next_retry_at, _canonical(dict(code=code, retryable=retryable)).decode(), now, task_id))
                return public(connection.execute("SELECT * FROM formal_range_task WHERE id=?", (task_id,)).fetchone(), attempt)

        def persist(self, task_id, worker_id, attempt_id, *, fetch):
            state, root, _, _, _ = record(self)
            if type(fetch) is not fetch_type:
                raise ValueError("range persistence requires genuine fetch")
            fetch_manifest_bytes, raw_bytes = fetch_snapshot(fetch)
            fetch_wire = json.loads(fetch_manifest_bytes)
            with transaction(state) as connection:
                row = connection.execute("SELECT * FROM formal_range_task WHERE id=?", (task_id,)).fetchone()
                task_payload(row)
                task = dict(row)
                parent_snapshots = parent_candidate_snapshots(connection, task)
            if task["status"] == "verified":
                replay = read(self, task_id)
                wire, _ = observation_wire(replay)
                if (wire["receipt"]["attempt_id"] != attempt_id or wire["receipt"]["worker_id"] != worker_id
                        or _canonical(wire["snapshot"]["fetch"]) != _canonical(fetch_wire)):
                    raise ValueError("range verified task cannot be claimed by another producer")
                return replay
            request, source = request_for(self, task, (), execution=True)
            document = source_parse(source, request, raw_bytes=raw_bytes, manifest=fetch_wire).to_dict()
            manifest = dict(schema_version="formal-range-snapshot-v1", task_payload=task_payload(task),
                task_id=task_id, attempt_id=attempt_id, worker_id=worker_id, fetch=fetch_wire)
            content_hash, content_path = _write_content(root, raw_bytes, ".raw")
            manifest_hash, manifest_path = _write_content(root, _canonical(manifest), ".json")
            receipt_wire = dict(schema_version="formal-range-normalization-receipt-v1", task_id=task_id,
                snapshot_id=manifest_hash, attempt_id=attempt_id, worker_id=worker_id, task_payload_hash=task["payload_hash"],
                manifest_sha256=manifest_hash, content_sha256=content_hash, normalization_hash=_digest(document),
                fetch=fetch_wire, refresh_generation=task["refresh_generation"])
            now = _utc_now()
            identity = {key: task[key] for key in ("request_fingerprint", "registry_manifest_hash", "range_config_id", "refresh_generation")}
            snapshot = dict(id=manifest_hash, task_id=task_id, **identity, content_sha256=content_hash, content_path=content_path,
                manifest_sha256=manifest_hash, manifest_path=manifest_path, **_payload(manifest), created_at=now)
            receipt = dict(task_id=task_id, snapshot_id=manifest_hash, attempt_id=attempt_id, **identity,
                manifest_sha256=manifest_hash, content_sha256=content_hash, normalization_hash=_digest(document), **_payload(receipt_wire), recorded_at=now)
            with transaction(state, immediate=True) as connection:
                owner(connection, task_id, worker_id, attempt_id, now)
                check_candidate_snapshots(connection, parent_snapshots)
                _read_content(root, content_path, content_hash, ".raw")
                _read_content(root, manifest_path, manifest_hash, ".json")
                insert(connection, "formal_range_snapshot", snapshot)
                insert(connection, "formal_range_normalization_receipt", receipt)
                finished = _utc_now()
                owner(connection, task_id, worker_id, attempt_id, finished)
                connection.execute("UPDATE formal_range_attempt SET outcome='verified',finished_at=? WHERE id=?", (finished, attempt_id))
                connection.execute("UPDATE formal_range_task SET status='verified',worker_id=NULL,lease_expires_at=NULL,result_json=?,error_json=NULL,updated_at=? WHERE id=?",
                    (_canonical(dict(snapshot_id=manifest_hash, receipt_hash=receipt["payload_hash"])).decode(), finished, task_id))
            return read(self, task_id)

        def read_verified(self, task_id):
            return read(self, task_id)

        def read_history(self, task_id):
            return read(self, task_id, historical=True)

        def select_current(self, request_fingerprint):
            candidates, token = current_candidates(self, _text(request_fingerprint))
            snapshots = [token]
            if not candidates:
                finish_current_check(self, snapshots)
                return None
            require_parent_chain(self, observation_wire(candidates[0])[0], snapshots)
            finish_current_check(self, snapshots)
            return candidates[0]

    return FormalRangeStore, read, require_current, record


# Source completes both paired types; this import is safe in either entry order.
from . import formal_range_source
