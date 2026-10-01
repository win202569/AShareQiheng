"""Append-only, atomic V8 Stage D runs and non-authoritative recovery DTOs."""

from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from types import MappingProxyType
from uuid import uuid4

from .formal_coverage_manifest import VerifiedCoverageManifest
from .formal_final_publication import FormalFinalPublicationCoordinator
from .formal_final_score_inputs import PolicyAdjustedScoreInputBatch
from .formal_final_scoring import FinalScoreCardBatch
from .formal_final_eligibility import FormalEligibilityBatch, _validate_scorecard_coverage
from .formal_pool import PoolSelectionBatch
from .formal_registry_manifest import FormalRegistryBundleLoader
from .formal_repository_identity import _require_repository_initialization
from .state_store import StateStore


ARTIFACT_KINDS = ("coverage_manifest", "score_input_batch", "scorecard_batch",
    "eligibility_batch", "pool_selection_batch")
_TABLES = ("formal_final_run", "formal_final_artifact", "formal_final_input",
    "formal_final_scorecard", "formal_final_status", "formal_final_eligibility",
    "formal_final_pool_decision", "formal_final_dependency")
_BATCH_TYPES = (PolicyAdjustedScoreInputBatch, FinalScoreCardBatch,
    FormalEligibilityBatch, PoolSelectionBatch)
_prepare_publication = FormalFinalPublicationCoordinator.prepare


def _json_value(value):
    if type(value) is Decimal:
        if not value.is_finite():
            raise ValueError("Stage D decimal must be finite")
        return str(value)
    if type(value) is float:
        raise ValueError("Stage D payload cannot contain float")
    if type(value) in (dict, MappingProxyType):
        if any(type(key) is not str for key in value):
            raise ValueError("Stage D object keys must be strings")
        return {key: _json_value(item) for key, item in value.items()}
    if type(value) in (tuple, list):
        return [_json_value(item) for item in value]
    if value is None or type(value) in (str, bool, int):
        return value
    raise ValueError("Stage D payload has an unsupported value")


def _serialize_payload(value):
    raw = json.dumps(_json_value(value), ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False)
    return raw, hashlib.sha256(raw.encode()).hexdigest()


def _immutable(value):
    if type(value) is dict:
        return MappingProxyType({key: _immutable(item) for key, item in value.items()})
    if type(value) in (list, tuple):
        return tuple(_immutable(item) for item in value)
    return value


def _new_run_id():
    return uuid4().hex


@dataclass(frozen=True)
class FormalFinalRunSnapshot:
    """Detached immutable history. It is intentionally not a live proof."""
    header: MappingProxyType
    artifacts: MappingProxyType
    artifact_hashes: MappingProxyType
    inputs: tuple
    scorecards: tuple
    statuses: tuple
    eligibilities: tuple
    pool_decisions: tuple
    dependencies: tuple

    def __getattr__(self, name):
        try:
            return self.header[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    @property
    def security_ids(self):
        return tuple(row["security_id"] for row in self.inputs)

    def to_dict(self):
        return _json_value(dict(header=self.header,
            artifacts={key: json.loads(raw) for key, raw in self.artifacts.items()},
            artifact_hashes=self.artifact_hashes, inputs=self.inputs,
            scorecards=self.scorecards, statuses=self.statuses, eligibilities=self.eligibilities,
            pool_decisions=self.pool_decisions, dependencies=self.dependencies))


@dataclass(frozen=True)
class FormalFinalRunReceipt:
    run_id: str
    status: str
    input_manifest_hash: str
    result_hash: str
    input_batch: PolicyAdjustedScoreInputBatch
    score_batch: FinalScoreCardBatch
    eligibility_batch: FormalEligibilityBatch
    pool_batch: PoolSelectionBatch

    @property
    def batches(self):
        return self.input_batch, self.score_batch, self.eligibility_batch, self.pool_batch


def _coverage_identity(coverage, wire, ids, mode):
    if type(coverage) is not VerifiedCoverageManifest:
        raise ValueError("run requires a genuine coverage manifest")
    coverage.require_verified()
    data = coverage.to_dict()
    rows = data["rows"]
    if ({row["security_id"] for row in rows} != set(ids)
            or any(row["frozen_input_hash"] != wire["frozen_input_hash"]
                   or row["exchange"] != row["security_id"][:2] for row in rows)
            or data["freeze_at_utc"] != wire["as_of_utc"]):
        raise ValueError("coverage does not cover the exact frozen universe")
    if data.get("authenticated_context"):
        if (data["registry_manifest_hash"] != wire["registry_manifest_hash"]
                or data["frozen_input_hash"] != wire["frozen_input_hash"]
                or data["universe_records_hash"] != wire["universe_hash"]
                or data["member_count"] != len(ids)):
            raise ValueError("coverage root or universe identity mismatch")
    if mode == "official_candidate":
        coverage.require_official_ready()
    elif not data["blockers"]:
        coverage.require_preview_ready()


def _recheck_sources(store, coverage, batches, mode, publication, connection):
    publication.recheck()
    inputs = batches[0].to_dict()
    ids = tuple(inputs["security_ids"])
    _coverage_identity(coverage, inputs, ids, mode)
    row = connection.execute("SELECT * FROM formal_universe_snapshot WHERE frozen_input_hash = ?",
        (inputs["frozen_input_hash"],)).fetchone()
    if row is None:
        raise ValueError("run frozen universe is no longer present")
    frozen, _ = store._formal_universe_from_connection(connection, row)
    if (tuple(member.security_id for member in frozen.members) != ids
            or frozen.universe_hash != inputs["universe_hash"]
            or frozen.registry_manifest_hash != inputs["registry_manifest_hash"]):
        raise ValueError("run root or frozen membership changed")
    bundle = FormalRegistryBundleLoader(store, store._require_registry_verifier()).load(
        inputs["registry_manifest_hash"])
    if bundle.manifest.schema_version != "formal-registry-manifest-v2":
        raise ValueError("Stage D run requires a v2 registry root")
    if mode == "official_candidate":
        bundle.require_official()


def _arm_publication(publication):
    publication.arm()


def _payload_columns(payload):
    raw, digest = _serialize_payload(payload)
    return dict(payload_json=raw, payload_hash=digest)


def _decimal_text(value):
    if type(value) is not str:
        raise ValueError("score projection requires decimal text")
    number = Decimal(value)
    if not number.is_finite() or str(number) != value:
        raise ValueError("score projection is not a canonical finite decimal")
    return value


def _project_rows(run_id, wires):
    inputs, scores, eligibility, pools = wires
    ids = tuple(inputs["security_ids"])
    _validate_scorecard_coverage(ids, scores)
    if (tuple(row["security_id"] for row in inputs["inputs"]) != ids
            or tuple(eligibility["security_ids"]) != ids
            or tuple(row["security_id"] for row in eligibility["eligibilities"]) != ids
            or tuple(pools["security_ids"]) != ids
            or len(set(ids)) != len(ids) or ids != tuple(sorted(ids))):
        raise ValueError("Stage D member coverage is incomplete or duplicated")
    if (scores["source_batch_hash"] != inputs["batch_hash"]
            or eligibility["source_batch_hash"] != inputs["batch_hash"]
            or eligibility["score_batch_hash"] != scores["batch_hash"]
            or pools["source_batch_hash"] != eligibility["batch_hash"]):
        raise ValueError("Stage D batch dependency closure differs")
    for key in ("registry_manifest_hash", "frozen_input_hash", "universe_hash"):
        if scores[key] != inputs[key]:
            raise ValueError("Stage D roots differ")
    rows = {name: [] for name in _TABLES[2:]}
    for item in inputs["inputs"]:
        rows["formal_final_input"].append(dict(run_id=run_id, security_id=item["security_id"],
            entry_hash=item["entry_hash"], **_payload_columns(item)))
    for item in scores["cards"]:
        projection = {key: _decimal_text(item[key]) for key in ("S0", "Sc", "Sbase", "B", "R_safety")}
        rows["formal_final_scorecard"].append(dict(run_id=run_id, security_id=item["security_id"],
            card_hash=item["card_hash"], C=_decimal_text(item["confidence"]["C"]),
            grade=item["Sc_grade"], **projection, **_payload_columns(item)))
    for item in eligibility["eligibilities"]:
        status = {key: item[key] for key in ("security_id", "state", "reason_codes")}
        rows["formal_final_status"].append(dict(run_id=run_id, security_id=item["security_id"],
            state=item["state"], reason_codes_json=_serialize_payload(item["reason_codes"])[0],
            **_payload_columns(status)))
        flags = {key: int(item[key]) for key in ("strong_qualified", "wait_qualified", "hard_veto",
            "strong_prohibited", "wait_prohibited")}
        rows["formal_final_eligibility"].append(dict(run_id=run_id, security_id=item["security_id"],
            eligibility_hash=item["eligibility_hash"], **flags, **_payload_columns(item)))
    expected_pairs = {(sid, pool) for sid in ids for pool in ("strong", "wait")}
    actual_pairs = [(item["security_id"], item["pool"]) for item in pools["decisions"]]
    if len(actual_pairs) != len(expected_pairs) or set(actual_pairs) != expected_pairs:
        raise ValueError("pool decisions must cover both pools and every frozen member")
    ordinals = {}
    for pool in ("strong", "wait"):
        selected = pools[pool + "_security_ids"]
        if len(selected) != len(set(selected)) or pools["counts"][pool] != len(selected):
            raise ValueError("pool selected membership or count is invalid")
        ordinals.update({(sid, pool): index for index, sid in enumerate(selected, 1)})
    for item in pools["decisions"]:
        ordinal = ordinals.get((item["security_id"], item["pool"]))
        if (item["decision"] == "selected") != (ordinal is not None):
            raise ValueError("pool selected membership differs from its decisions")
        rows["formal_final_pool_decision"].append(dict(run_id=run_id, security_id=item["security_id"],
            pool_name=item["pool"], decision=item["decision"], selected_ordinal=ordinal,
            decision_hash=item["decision_hash"], **_payload_columns(item)))
    # Preserve root-wide and per-member dependencies. Fine-grained upstream
    # hashes are retained with their field paths for the later rebuild planner.
    dependencies = {}
    def add_dependencies(value, *, sid, path):
        if type(value) is dict:
            for key, child in value.items():
                child_path = path + "." + key
                if ((key.endswith("_hash") or key.endswith("_sha256"))
                        and type(child) is str and child):
                    dependency = dict(security_id=sid, source_kind=key,
                        source_id=child_path, source_hash=child,
                        effect_scope="global" if sid is None else "security",
                        dependent_key="run" if sid is None else sid)
                    dependencies[(key, child_path, dependency["dependent_key"])] = dependency
                elif type(child) in (dict, list):
                    add_dependencies(child, sid=sid, path=child_path)
        elif type(value) is list:
            for index, child in enumerate(value):
                add_dependencies(child, sid=sid, path=path + "." + str(index))
    add_dependencies({key: value for key, value in inputs.items() if key != "inputs"},
        sid=None, path="batch")
    for item in inputs["inputs"]:
        add_dependencies(item, sid=item["security_id"], path="input." + item["security_id"])
    for _, dependency in sorted(dependencies.items()):
        rows["formal_final_dependency"].append(dict(run_id=run_id, **dependency,
            **_payload_columns(dependency)))
    return rows


def _insert_rows(connection, table, rows, columns):
    sql = "INSERT INTO " + table + " (" + ",".join(columns) + ") VALUES ("
    sql += ",".join("?" for _ in columns) + ")"
    connection.executemany(sql, [tuple(row[key] for key in columns) for row in rows])


def _verify_persisted(connection, run_id, expected):
    # Full value comparison checks exact member/key sets, every hash and every
    # Decimal projection. Counts alone cannot prove an untorn result.
    for table, rows in expected.items():
        actual = [dict(row) for row in connection.execute(
            "SELECT * FROM " + table + " WHERE run_id = ?", (run_id,))]
        canonical = lambda entries: sorted(_serialize_payload(row)[0] for row in entries)
        if canonical(actual) != canonical(rows):
            raise ValueError("persisted Stage D table differs: " + table)
    artifacts = {row["artifact_kind"]: row for row in expected["formal_final_artifact"]}
    if set(artifacts) != set(ARTIFACT_KINDS):
        raise ValueError("Stage D requires exactly the five owned artifact kinds")
    for row in artifacts.values():
        if hashlib.sha256(row["payload_json"].encode()).hexdigest() != row["artifact_hash"]:
            raise ValueError("Stage D artifact canonical hash differs")
    header = expected["formal_final_run"][0]
    inputs = json.loads(artifacts["score_input_batch"]["payload_json"])
    if (any(header[key] != inputs[key] for key in
            ("registry_manifest_hash", "frozen_input_hash", "universe_hash", "as_of_utc"))
            or header["coverage_manifest_hash"] != artifacts["coverage_manifest"]["artifact_hash"]):
        raise ValueError("run header differs from its canonical artifacts")
    identity = _input_identity(header, artifacts)
    if header["input_manifest_hash"] != _serialize_payload(identity)[1]:
        raise ValueError("run input manifest differs from its canonical artifacts")
    if header["result_hash"] != _result_hash(header, artifacts):
        raise ValueError("run result identity differs from canonical artifacts")


def _input_identity(header, artifacts):
    return {**{key: header[key] for key in ("mode", "registry_manifest_hash",
        "frozen_input_hash", "universe_hash", "as_of_utc", "code_version", "contract_version")},
        "coverage_manifest_hash": artifacts["coverage_manifest"]["artifact_hash"],
        "score_input_batch_hash": artifacts["score_input_batch"]["artifact_hash"]}


def _result_hash(header, artifacts):
    return _serialize_payload(dict(input_manifest_hash=header["input_manifest_hash"],
        status=header["status"], artifacts={name: row["artifact_hash"]
            for name, row in artifacts.items()}))[1]


class FormalFinalRunRepository:
    """The sole Stage D mutation is commit_complete_run; history has no writer."""

    def __init__(self, state_store, *, code_version, contract_version="formal-final-v1"):
        if type(state_store) is not StateStore:
            raise ValueError("Stage D repository requires the owning StateStore")
        _require_repository_initialization(state_store)
        if any(type(value) is not str or not value.strip() for value in (code_version, contract_version)):
            raise ValueError("Stage D requires code and contract identities")
        self._store = state_store
        self._path = Path(state_store.db_path).resolve()
        self._code_version, self._contract_version = code_version, contract_version

    def commit_complete_run(self, *, mode, coverage_manifest, input_batch,
                            score_batch, eligibility_batch, pool_batch):
        if mode not in ("test_preview", "official_candidate"):
            raise ValueError("Stage D run mode is invalid")
        if Path(self._store.db_path).resolve() != self._path:
            raise ValueError("Stage D repository database changed")
        batches = (input_batch, score_batch, eligibility_batch, pool_batch)
        if any(type(batch) is not cls for batch, cls in zip(batches, _BATCH_TYPES, strict=True)):
            raise ValueError("Stage D requires genuine exact batch types")
        for batch in batches:
            batch.require_verified()
        wires = tuple(batch.to_dict() for batch in batches)
        _coverage_identity(coverage_manifest, wires[0], tuple(wires[0]["security_ids"]), mode)
        publication = _prepare_publication(input_batch=input_batch, score_batch=score_batch,
            eligibility_batch=eligibility_batch, pool_batch=pool_batch)
        try:
            run_id = _new_run_id()
            rows = _project_rows(run_id, wires)
            raw_artifacts = (coverage_manifest.canonical_bytes(),) + tuple(
                batch.canonical_bytes() for batch in batches)
            artifacts = {}
            for kind, raw in zip(ARTIFACT_KINDS, raw_artifacts, strict=True):
                canonical, digest = _serialize_payload(json.loads(raw))
                if canonical.encode() != raw:
                    raise ValueError("Stage D artifact is not canonical")
                artifacts[kind] = dict(run_id=run_id, artifact_kind=kind,
                    payload_json=canonical, artifact_hash=digest)
            if len(artifacts) != 5 or set(artifacts) != {
                    "coverage_manifest", "score_input_batch", "scorecard_batch",
                    "eligibility_batch", "pool_selection_batch"}:
                raise ValueError("Stage D requires exactly its five canonical artifacts")
            blocked = bool(coverage_manifest.blockers) or any(
                row["state"] == "pending_evidence" for row in wires[2]["eligibilities"])
            header = dict(run_id=run_id, mode=mode, status="blocked" if blocked else "preview_ready",
                **{key: wires[0][key] for key in ("registry_manifest_hash", "frozen_input_hash",
                    "universe_hash", "as_of_utc")},
                coverage_manifest_hash=coverage_manifest.manifest_hash,
                code_version=self._code_version, contract_version=self._contract_version,
                created_at=datetime.now(timezone.utc).isoformat())
            header["input_manifest_hash"] = _serialize_payload(_input_identity(header, artifacts))[1]
            header["result_hash"] = _result_hash(header, artifacts)
            expected = {"formal_final_run": [header], "formal_final_artifact": list(artifacts.values()), **rows}
            publication.prevalidate_commit()
            # Resolve and validate everything which can fail before entering the
            # commit boundary. The captured flip itself performs only STORE_SUBSCR.
            mark_committed = publication.mark_committed
            receipt = FormalFinalRunReceipt(run_id, header["status"], header["input_manifest_hash"],
                header["result_hash"], *publication.batches)
            empty_columns = {
                "formal_final_scorecard": ("run_id", "security_id", "card_hash", "S0", "Sc", "Sbase",
                    "B", "R_safety", "C", "grade", "payload_json", "payload_hash"),
            }
            connection = self._store._connect()
            committed = False
            try:
                connection.execute("BEGIN IMMEDIATE")
                _recheck_sources(self._store, coverage_manifest, batches, mode, publication, connection)
                for table in _TABLES:
                    items = expected[table]
                    columns = tuple(items[0]) if items else empty_columns.get(table)
                    if columns is None:
                        raise ValueError("Stage D required table has no complete records: " + table)
                    _insert_rows(connection, table, items, columns)
                _verify_persisted(connection, run_id, expected)
                _recheck_sources(self._store, coverage_manifest, batches, mode, publication, connection)
                _arm_publication(publication)
                connection.commit()
                mark_committed()
                committed = True
            except BaseException:
                publication.revoke()
                connection.rollback()
                raise
            finally:
                # Closing is cleanup after publication. It cannot turn a
                # successful durable commit into a reported failed run.
                try:
                    connection.close()
                except Exception:
                    if not committed:
                        raise
            return receipt
        except BaseException:
            publication.revoke()
            raise

    def get_run(self, run_id):
        with self._store._transaction() as connection:
            return self._read_run(connection, run_id)

    def _read_run(self, connection, run_id):
        row = connection.execute("SELECT * FROM formal_final_run WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            return None
        artifacts = list(connection.execute(
            "SELECT * FROM formal_final_artifact WHERE run_id = ? ORDER BY artifact_kind", (run_id,)))
        if {item["artifact_kind"] for item in artifacts} != set(ARTIFACT_KINDS):
            raise ValueError("historical run artifact set is incomplete")
        payloads, hashes = {}, {}
        for item in artifacts:
            raw = item["payload_json"].encode()
            if hashlib.sha256(raw).hexdigest() != item["artifact_hash"]:
                raise ValueError("historical run artifact hash mismatch")
            payloads[item["artifact_kind"]], hashes[item["artifact_kind"]] = raw, item["artifact_hash"]
        groups = []
        for table in _TABLES[2:]:
            order = "source_kind,source_id,effect_scope,dependent_key" if table == "formal_final_dependency" else "security_id"
            if table == "formal_final_pool_decision":
                order += ",pool_name"
            group = []
            for item in connection.execute("SELECT * FROM " + table + " WHERE run_id = ? ORDER BY " + order, (run_id,)):
                raw = item["payload_json"]
                if hashlib.sha256(raw.encode()).hexdigest() != item["payload_hash"]:
                    raise ValueError("historical run payload hash mismatch")
                group.append(_immutable(json.loads(raw)))
            groups.append(tuple(group))
        return FormalFinalRunSnapshot(_immutable(dict(row)), MappingProxyType(payloads),
            MappingProxyType(hashes), *groups)

    def list_runs_by_input_manifest(self, input_manifest_hash):
        with self._store._transaction() as connection:
            ids = tuple(row[0] for row in connection.execute(
                "SELECT run_id FROM formal_final_run WHERE input_manifest_hash = ? ORDER BY created_at,run_id",
                (input_manifest_hash,)))
            return tuple(self._read_run(connection, run_id) for run_id in ids)


__all__ = ["FormalFinalRunRepository", "FormalFinalRunReceipt", "FormalFinalRunSnapshot"]
