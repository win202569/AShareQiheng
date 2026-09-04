# Formal V3 Release, Audit, and Reporting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Turn a validated V7 formal score run into a reproducible, immutable V3 release package only after every A-share member is classified and every evidence, pool, hash, and output-file gate passes; expose that package to reporting without allowing legacy preview data to impersonate an official result.

**Architecture:** Add a V8 release domain separate from legacy orchestrator finalization. FormalReleaseValidator reads one frozen V7 run plus its full V5 universe and V6/V7 evidence graph and produces a canonical validation manifest. FormalReleasePublisher renders deterministic release files into a same-volume staging directory, SHA-verifies every file, writes release_manifest last, then atomically renames into data/releases/release_id. Formal CLI commands invoke only this domain. A formal reporting reader accepts only a published V8 manifest and canonical strong/wait counts; the legacy dashboard adapter remains read-only compatibility code.

**Tech Stack:** Python 3.12, Python standard library, SQLite, unittest, CSV, canonical JSON, hashlib, tempfile, pathlib, and the V5-V7 formal contracts.

**Spec:** docs/superpowers/specs/2026-09-04-formal-scoring-release-contract-design.md

## Global Constraints

- This plan depends on V5 evidence/universe, V6 formal financial-feature, and V7 scoring/pool migrations. Its persistence starts at schema version 8 and must not rewrite V2-V7 DDL.
- A release is official only when generated through FormalReleaseValidator and FormalReleasePublisher. Legacy StateStore.finalize_score_run, orchestrator._finalize, old score_run/score_item, feature-contract-v1, and existing outputs directories must never publish or be displayed as V3 formal results.
- The frozen release time is exactly 2026-08-31T15:00:00+08:00. Release input hashes must contain universe, calendar, verified evidence, feature, market, industry, policy, registry, capacity, and selection-algorithm inputs as defined by V3.
- The full formal universe contains SH/SZ/BJ ordinary A shares. Formal publication requires every member exactly once in formal_scored, pending_evidence, pool_vetoed, or out_of_scope; BJ must not be filtered by output or reporting code.
- Formal nonzero output requires a hash-pinned approved production registry and source configuration. A test-preview registry, an unsigned/invalid registry approval, or an incomplete configuration blocks official publication.
- A zero-scored release is legal only when the full universe is completely classified and every other release gate passes. It must disclose zero score coverage; an empty run without universe status is always blocked.
- The canonical formal pool count mapping and all machine-readable pool identifiers are exactly strong and wait. The V3-specified artifact filenames strong_attention.csv and waiting_price.csv are fixed human-facing paths only; their rows and manifest metadata use canonical pool identifiers strong/wait. The strings strong_attention and waiting_price are otherwise legacy compatibility read aliases and are never count keys, database pool names, or formal selection values.
- Write only to an owned staging subdirectory below data/releases on the same volume. Never overwrite an existing release. A matching existing release is an idempotent success only when all file bytes and manifest hashes are identical.
- Release packages, raw evidence, SQLite data, and audit cards are retained project data. Do not add them to .gitignore. Do not stage generated release/data/SQLite/WAL/SHM/status files in code commits.
- All tests are hermetic and use temporary release roots and fixtures. No command in this plan downloads data or contacts a network source.

---

## File Structure

| File | Responsibility |
|---|---|
| ashare_pipeline/formal_release_types.py | Dependency-free validation, release-record, and release-file value types plus canonical validation serialization |
| ashare_pipeline/formal_release.py | Release ID, gate evaluation, deterministic rendering, staging, SHA verification, and atomic publication |
| ashare_pipeline/formal_release_reporting.py | Read-only V8 release loader, audit-card lookup, canonical pool summary, and legacy compatibility reader |
| ashare_pipeline/formal_cli.py | Formal validate, publish, inspect, and quality-report command handlers |
| ashare_pipeline/__main__.py | Narrow argparse registration for formal subcommands without changing legacy command behavior |
| ashare_pipeline/state_store.py | Additive V8 release, validation, and file-manifest tables plus append-only APIs |
| ashare_pipeline/reporting.py | Explicit delegation to formal release reporting when a formal release path/ID is requested; preserve legacy paths |
| tests/test_formal_release.py | Validator gate, release ID, output determinism, staging, conflict, and idempotence tests |
| tests/test_formal_release_reporting.py | Published-only reader, canonical count, BJ, and legacy compatibility tests |
| tests/test_formal_cli.py | Command parsing, validation-before-publish, and no-legacy-finalizer tests |
| tests/test_state_store.py | V7-to-V8 migration, release immutability, and file manifest tests |
| tests/fixtures/schema_v7.sql | Complete pre-V8 migration fixture |

### Task 1: Additive SQLite V8 Release and Manifest Persistence

**Files:**
- Create: ashare_pipeline/formal_release_types.py
- Modify: ashare_pipeline/state_store.py: schema constants, migration dispatcher, V8 DDL, and append-only release APIs
- Modify: tests/test_state_store.py: V7 migration fixture and V8 invariant tests
- Create: tests/test_formal_release_types.py
- Create: tests/fixtures/schema_v7.sql

**Interfaces:**
- Produces REQUIRED_RELEASE_GATE_NAMES, ReleaseValidationSigner, ReleaseValidationSignatureVerifier, ReleasePackageSigner, ReleasePackageSignatureVerifier, ValidationGate, FormalReleaseValidation, FormalReleaseRecord, FormalReleaseFile, FormalReleasePreparation, canonical_validation_json, canonical_release_preparation_json, StateStore.put_formal_release_validation, get_formal_release_validation, mark_formal_score_run_validated, mark_formal_score_run_published, begin_formal_release_publish, prepare_formal_release_publish, get_formal_release_preparation, complete_formal_release_publish, recover_formal_release_publish, record_formal_release_publish_event, block_formal_release_publish, get_formal_release, and list_formal_release_files.
- Release states are publishing, published, and blocked. A passed validation is stored separately; begin_formal_release_publish creates the only publishing intent. A published release is immutable; a full-hash release ID and input hash are both unique identities.
- A stored validation is authoritative only when its validation_hash was produced and signature-authenticated by FormalReleaseValidator, its required gate set is complete, and every gate passed.

- [ ] **Step 1: Write the failing V7-to-V8 migration tests**

~~~python
def test_v7_to_v8_migration_keeps_score_rows_and_adds_release_tables(self):
    migrate_fixture("schema_v7.sql", self.db_path)
    store = StateStore(self.db_path)
    store.initialize()
    self.assertEqual(store.schema_version(), 8)
    self.assertEqual(store.get_formal_score_item_count(), 1)
    self.assertTrue(store.has_table("formal_release"))
    self.assertTrue(store.has_table("formal_release_file"))

def test_final_initialize_advances_historical_v4_v6_v7_fixtures_through_v8(self):
    for fixture in ("schema_v4.sql", "schema_v6.sql", "schema_v7.sql"):
        with self.subTest(fixture=fixture):
            with migrated_fixture_db(fixture) as db_path:
                store = StateStore(db_path, **trusted_release_verifier_fixture())
                store.initialize()
                self.assertEqual(store.schema_version(), 8)
                self.assertEqual(migration_versions(db_path), [2, 3, 4, 5, 6, 7, 8])
                self.assertTrue(store.has_table("formal_financial_fact"))
                self.assertTrue(store.has_table("formal_score_run"))
                self.assertTrue(store.has_table("formal_release"))

def test_release_requires_passing_validator_hash_and_is_append_only(self):
    validation = passed_validation(run_id=self.run_id)
    release_id = canonical_release_id(FORMAL_FREEZE_AT_CN, "formal-v3", "a" * 64)
    self.store.put_formal_release_validation(validation)
    self.store.mark_formal_score_run_validated(self.run_id, validation.validation_hash)
    release = self.store.begin_formal_release_publish(
        release_id=release_id,
        run_id=self.run_id,
        input_hash="a" * 64,
        validation_hash=validation.validation_hash,
        freeze_at_utc=FORMAL_FREEZE_AT_CN,
        contract_version="formal-v3",
        release_path=str(self.release_root / release_id),
    )
    with self.assertRaisesRegex(ValueError, "preparation"):
        self.store.complete_formal_release_publish(release.release_id)
    preparation, target_contents = signed_materialized_release_preparation(
        release_id=release.release_id,
        validation_hash=validation.validation_hash,
        payload_files=payload_file_rows_with_audit_card(),
    )
    self.store.prepare_formal_release_publish(preparation)
    with self.assertRaisesRegex(ValueError, "release target"):
        self.store.complete_formal_release_publish(release.release_id)
    materialize_prepared_release_target(
        self.release_root / release_id, preparation, target_contents
    )
    self.assertTrue((self.release_root / release_id / "audit_cards").is_dir())
    self.store.complete_formal_release_publish(release.release_id)
    published_retry = self.store.begin_formal_release_publish(
        release_id=release_id,
        run_id=self.run_id,
        input_hash="a" * 64,
        validation_hash=validation.validation_hash,
        freeze_at_utc=FORMAL_FREEZE_AT_CN,
        contract_version="formal-v3",
        release_path=str(self.release_root / release_id),
    )
    self.assertEqual(published_retry.status, "published")
    with self.assertRaisesRegex(ValueError, "input_hash"):
        self.store.begin_formal_release_publish(
            release_id=canonical_release_id(FORMAL_FREEZE_AT_CN, "formal-v3", "b" * 64),
            run_id=self.run_id,
            input_hash="a" * 64,
            validation_hash=validation.validation_hash,
            freeze_at_utc=FORMAL_FREEZE_AT_CN,
            contract_version="formal-v3",
            release_path=str(self.release_root / canonical_release_id(FORMAL_FREEZE_AT_CN, "formal-v3", "b" * 64)),
        )
    with self.assertRaisesRegex(ValueError, "published"):
        self.store.complete_formal_release_publish(release.release_id)

def test_unsigned_or_incomplete_validation_cannot_validate_or_begin_publish(self):
    forged = replace(passed_validation(run_id=self.run_id), validator_signature="not-signed-by-validator")
    with self.assertRaisesRegex(ValueError, "validator signature"):
        self.store.put_formal_release_validation(forged)
    incomplete = signed_validation_with_gates({"run_identity"})
    with self.assertRaisesRegex(ValueError, "required gate"):
        self.store.put_formal_release_validation(incomplete)

def test_unsigned_or_mismatched_release_preparation_cannot_anchor_recovery(self):
    release = publishing_release_with_validated_run(self.store)
    unsigned = replace(signed_release_preparation_for(release), package_signature="not-signed")
    with self.assertRaisesRegex(ValueError, "package signature"):
        self.store.prepare_formal_release_publish(unsigned)
    mismatched = signed_release_preparation_for(release, validation_hash="f" * 64)
    with self.assertRaisesRegex(ValueError, "validation"):
        self.store.prepare_formal_release_publish(mismatched)

def test_v8_only_marks_a_run_validated_after_persisted_passing_validation(self):
    with self.assertRaisesRegex(ValueError, "passed validation"):
        self.store.mark_formal_score_run_validated(self.run_id, "v" * 64)
    validation = passed_validation(run_id=self.run_id)
    self.store.put_formal_release_validation(validation)
    self.store.mark_formal_score_run_validated(self.run_id, validation.validation_hash)
    self.assertEqual(self.store.get_formal_score_run(self.run_id)["status"], "validated")

def test_public_published_mark_cannot_bypass_v8_completion(self):
    release = publishing_release_with_validated_run(self.store)
    with self.assertRaisesRegex(ValueError, "V8 completion"):
        self.store.mark_formal_score_run_published(release.run_id, release.validation_hash)
    self.assertEqual(self.store.get_formal_release(release.release_id)["status"], "publishing")
    self.assertEqual(self.store.get_formal_score_run(release.run_id)["status"], "validated")

def test_same_publishing_intent_restarts_after_pre_rename_crash_and_blocks_only_terminally(self):
    validation = passed_validation(run_id=self.run_id)
    release_id = canonical_release_id(FORMAL_FREEZE_AT_CN, "formal-v3", "a" * 64)
    self.store.put_formal_release_validation(validation)
    self.store.mark_formal_score_run_validated(self.run_id, validation.validation_hash)
    first = self.store.begin_formal_release_publish(
        release_id, self.run_id, "a" * 64,
        validation.validation_hash, FORMAL_FREEZE_AT_CN, "formal-v3", str(self.release_root / release_id),
    )
    retry = self.store.begin_formal_release_publish(
        release_id, self.run_id, "a" * 64,
        validation.validation_hash, FORMAL_FREEZE_AT_CN, "formal-v3", str(self.release_root / release_id),
    )
    self.assertEqual(retry.release_id, first.release_id)
    self.assertEqual(retry.status, "publishing")
    self.store.record_formal_release_publish_event(
        first.release_id, "renderer_failed_retryable", {"code": "renderer_failed"}
    )
    self.assertEqual(self.store.get_formal_release(first.release_id)["status"], "publishing")
    terminal_validation = terminal_failed_validation(run_id=self.run_id)
    self.store.put_formal_release_validation(terminal_validation)
    terminal = {"code": "terminal_validation_failed", "validation_hash": terminal_validation.validation_hash}
    self.store.block_formal_release_publish(first.release_id, terminal)
    self.store.block_formal_release_publish(first.release_id, terminal)
    with self.assertRaisesRegex(ValueError, "blocked"):
        self.store.begin_formal_release_publish(
            release_id, self.run_id, "a" * 64,
            validation.validation_hash, FORMAL_FREEZE_AT_CN, "formal-v3", str(self.release_root / release_id),
        )

def test_terminal_release_block_and_v7_reason_commit_atomically(self):
    release = publishing_release_with_validated_run(self.store)
    failed = terminal_failed_validation(run_id=release.run_id)
    self.store.put_formal_release_validation(failed)
    reason = {"code": "terminal_validation_failed", "validation_hash": failed.validation_hash}
    self.store.inject_failure_after_release_block_update_once()
    with self.assertRaisesRegex(sqlite3.OperationalError, "injected"):
        self.store.block_formal_release_publish(release.release_id, reason)
    self.assertEqual(self.store.get_formal_release(release.release_id)["status"], "publishing")
    self.assertEqual(self.store.get_formal_score_run(release.run_id)["status"], "validated")
    self.store.block_formal_release_publish(release.release_id, reason)
    self.assertEqual(self.store.get_formal_release(release.release_id)["status"], "blocked")
    self.assertEqual(self.store.get_formal_score_run(release.run_id)["blocked_reason_json"], canonical_json({
        "code": "validation_terminal_failed", "validation_hash": failed.validation_hash,
    }))

def test_direct_v7_block_refuses_while_a_v8_publishing_intent_exists(self):
    release = publishing_release_with_validated_run(self.store)
    with self.assertRaisesRegex(ValueError, "release_publish_in_progress"):
        self.store.mark_formal_score_run_blocked(
            release.run_id, {"code": "validation_terminal_failed", "validation_hash": "f" * 64}
        )
    self.assertEqual(self.store.get_formal_release(release.release_id)["status"], "publishing")
    self.assertEqual(self.store.get_formal_score_run(release.run_id)["status"], "validated")
~~~

The test-only signed_materialized_release_preparation fixture starts from deterministic manifest and payload bytes, derives the preparation's real SHA-256 and byte-size rows from those bytes, signs that exact preparation, and returns both it and the bytes. Its payload_file_rows_with_audit_card fixture contains scores.csv and audit_cards/SZ000001.json, so its materialized target proves the permitted implied audit_cards parent directory succeeds. materialize_prepared_release_target writes precisely that closed tree (including release_manifest.json) under the supplied target. It must not fabricate an arbitrary claimed SHA; the missing-target assertion and this materialized-target success path prove that completion cannot be driven solely by a prepared database row.

When adding V8, update—not duplicate—the earlier test_initialize_migrates_complete_v5_ledger_to_v6_without_touching_legacy_rows and test_v6_to_v7_migration_preserves_prior_formal_evidence_and_adds_score_tables tests in tests/test_state_store.py. Their fixture setup remains the historical ledger they are designed to preserve, but their post-initialize assertions must now require the current complete sequence [2, 3, 4, 5, 6, 7, 8], schema_version() == 8, and the continued presence of their V6/V7 tables and rows. Do not add a target-version argument to StateStore.initialize merely to preserve old expectations; the final regression suite always exercises the current contiguous migrator.

- [ ] **Step 2: Run migration tests and verify RED**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m unittest tests.test_formal_release_types tests.test_state_store.StateStoreTestCase.test_v7_to_v8_migration_keeps_score_rows_and_adds_release_tables tests.test_state_store.StateStoreTestCase.test_final_initialize_advances_historical_v4_v6_v7_fixtures_through_v8 -v
~~~

Expected: FAIL because formal release value types, schema V8, and formal release APIs do not exist.

- [ ] **Step 3: Implement V8 tables and state transitions**

Set SCHEMA_VERSION to 8 after V5-V7 are present. Add a contiguous _apply_v8_migration and extend initialize validation to accept exactly these complete ledgers:

~~~text
{2}
{2,3}
{2,3,4}
{2,3,4,5}
{2,3,4,5,6}
{2,3,4,5,6,7}
{2,3,4,5,6,7,8}
~~~

Create ashare_pipeline/formal_release_types.py before StateStore uses its values:

~~~python
@dataclass(frozen=True)
class ValidationGate:
    name: str
    status: Literal["passed", "failed"]
    failure_kind: Literal["retryable", "terminal"] | None
    details: Mapping[str, object]

REQUIRED_RELEASE_GATE_NAMES: frozenset[str] = frozenset({
    "run_identity", "universe_complete", "evidence_lineage",
    "point_in_time_evidence", "score_completeness", "pending_and_veto_reasons",
    "jobs_quiescent", "pool_integrity", "registry_approval", "output_preconditions",
})

class ReleaseValidationSigner(Protocol):
    key_id: str
    def sign(self, canonical_validation_bytes: bytes) -> str: ...

class ReleaseValidationSignatureVerifier(Protocol):
    def verify(
        self, *, key_id: str, canonical_validation_bytes: bytes, signature: str,
    ) -> bool: ...

class ReleasePackageSigner(Protocol):
    key_id: str
    def sign(self, canonical_preparation_bytes: bytes) -> str: ...

class ReleasePackageSignatureVerifier(Protocol):
    def verify(
        self, *, key_id: str, canonical_preparation_bytes: bytes, signature: str,
    ) -> bool: ...

@dataclass(frozen=True)
class FormalReleaseValidation:
    validator_version: str
    validator_key_id: str
    run_id: str
    input_hash: str
    release_id: str
    freeze_at_utc: str
    contract_version: str
    validation_hash: str
    validator_signature: str
    gates: tuple[ValidationGate, ...]
    summary: Mapping[str, object]

    @property
    def passed(self) -> bool: ...

    def gate(self, name: str) -> ValidationGate: ...

@dataclass(frozen=True)
class FormalReleaseFile:
    relative_path: str
    byte_size: int
    sha256: str
    media_type: str

@dataclass(frozen=True)
class FormalReleasePreparation:
    release_id: str
    validation_hash: str
    manifest_sha256: str
    payload_files: tuple[FormalReleaseFile, ...]
    package_key_id: str
    package_signature: str

@dataclass(frozen=True)
class FormalReleaseRecord:
    release_id: str
    run_id: str
    input_hash: str
    validation_hash: str
    freeze_at_utc: str
    contract_version: str
    status: Literal["publishing", "published", "blocked"]
    release_path: str
    manifest_sha256: str | None
    blocked_reason: Mapping[str, object] | None

def canonical_validation_json(validation: FormalReleaseValidation) -> bytes: ...
def canonical_release_preparation_json(preparation: FormalReleasePreparation) -> bytes: ...
~~~

canonical_validation_json serializes all fields other than validation_hash and validator_signature with sorted gate names and canonical JSON. Its SHA-256 must equal validation.validation_hash; it rejects duplicate, missing, or unknown gate names relative to REQUIRED_RELEASE_GATE_NAMES, a passed gate with a failure_kind, a failed gate without one, an empty/partial gate list, or a summary that is not canonical JSON. FormalReleaseValidation.passed is true only for exactly REQUIRED_RELEASE_GATE_NAMES with every status passed. FormalReleaseValidation.gate(name) returns the sole exact-name gate and raises ValueError for an unknown name; duplicate names are impossible because construction/canonicalization rejects them. canonical_release_preparation_json serializes the release ID, validation hash, manifest SHA, package_key_id, and canonical sorted nonempty payload-file table, excluding only package_signature; its SHA-256 is the preparation hash. FormalReleaseValidator injects a ReleaseValidationSigner and signs validation bytes. FormalReleasePublisher injects a distinct ReleasePackageSigner and signs preparation bytes after deterministic rendering. V8 StateStore is constructed with the corresponding trusted validation and package signature verifiers and refuses V8 validation writes, score-run validation transitions, publishing intents, preparations, or recovery if either required verifier is absent or its signature/key ID fails. tests/test_formal_release_types.py proves equal value objects produce equal bytes/hash, every field or gate-order mutation (including package_key_id) changes/rejects the result, and missing/unknown/empty gate sets fail closed.

All V8 StateStore test fixtures that call a V8 API construct StateStore with deterministic fake trusted validation/package verifiers and use paired fake signers in the validator/publisher fixtures. Migration-only initialization tests may omit those verifiers because no V8 transition is attempted.

Add these core tables:

~~~text
formal_release_validation:
  validation_hash PRIMARY KEY, run_id, input_hash, release_id, freeze_at_utc,
  contract_version, validator_version, validator_key_id, validator_signature,
  validation_json, status, created_at

formal_release:
  release_id PRIMARY KEY, run_id UNIQUE, input_hash UNIQUE,
  validation_hash UNIQUE, freeze_at_utc, contract_version,
  status, release_path, manifest_sha256, blocked_reason_json, created_at, published_at

formal_release_file:
  release_id, relative_path, byte_size, sha256, media_type, created_at
  PRIMARY KEY (release_id, relative_path)

formal_release_preparation:
  release_id PRIMARY KEY, validation_hash, manifest_sha256,
  preparation_hash UNIQUE, package_key_id, package_signature, prepared_at

formal_release_prepared_file:
  release_id, relative_path, byte_size, sha256, media_type, created_at
  PRIMARY KEY (release_id, relative_path)

formal_release_event:
  release_id, ordinal, event_kind, reason_json, created_at
  PRIMARY KEY (release_id, ordinal)
~~~

Define the calls exactly as put_formal_release_validation(validation: FormalReleaseValidation) -> None, get_formal_release_validation(validation_hash: str) -> Mapping[str, object] | None, mark_formal_score_run_validated(run_id: str, validation_hash: str) -> None, mark_formal_score_run_published(run_id: str, validation_hash: str) -> None (a public idempotence assertion, never a publication transition), begin_formal_release_publish(release_id: str, run_id: str, input_hash: str, validation_hash: str, freeze_at_utc: str, contract_version: str, release_path: str) -> FormalReleaseRecord, prepare_formal_release_publish(preparation: FormalReleasePreparation) -> None, get_formal_release_preparation(release_id: str) -> FormalReleasePreparation | None, complete_formal_release_publish(release_id: str) -> FormalReleaseRecord, recover_formal_release_publish(release_id: str) -> FormalReleaseRecord, record_formal_release_publish_event(release_id: str, event_kind: str, reason: Mapping[str, object]) -> None, and block_formal_release_publish(release_id: str, reason: Mapping[str, object]) -> FormalReleaseRecord. Only the private `_mark_formal_score_run_published_in_completion_tx` is allowed to change a V7 run from validated to published, and it is callable only from the V8 completion transaction.

put_formal_release_validation re-runs canonical_validation_json, requires the exact validation hash and status implied by the complete required gate set, verifies validator_signature against the StateStore-injected trusted verifier and validator_key_id, and stores only those canonical signed bytes. Every later V8 transition re-verifies the stored signature rather than trusting a row merely because it exists. formal_release_validation is append-only by validation_hash: an equal canonical validation is idempotent, while a later re-audit of the same run persists a distinct validation hash and never deletes the earlier record. V8's mark_formal_score_run_validated requires a persisted, signature-verified passed validation whose run_id, input_hash, freeze_at_utc, contract_version, and canonical full release_id exactly equal the V7 run's corresponding values; it then performs preview_ready-to-validated compare-and-set and stores that hash. V7 intentionally cannot perform that future-schema check. The public mark_formal_score_run_published reads the matching release and run and returns only as an idempotent confirmation when both are already published with the same verified validation hash; it rejects every other state, including a V8 publishing intent.

begin_formal_release_publish first recomputes canonical_release_id(freeze_at_utc, contract_version, input_hash), requires it to equal release_id, and requires release_path to be the owned same-volume target whose basename is exactly that full release ID. It then looks up an existing exact identity (release ID, run, input, validation, contract/freeze, and release path) before it checks the V7 state: a published exact row is returned so the publisher can still verify its target tree and report already_published, and a still-publishing exact row is returned so a retry with no target can safely create a fresh owned staging directory. Any mismatched existing identity conflicts and a blocked row is rejected. Only when no row exists does begin require a persisted signature-verified passed validation whose run_id/input_hash/release_id/freeze_at_utc/contract_version exactly equal all arguments and the V7 run, require the V7 run to be validated with validation_manifest_hash exactly equal validation_hash, then create the committed publishing intent before filesystem staging and copy no score rows. formal_release_file lists payload artifacts only and explicitly excludes release_manifest.json, which is the non-self-referential trust envelope.

complete_formal_release_publish and recover_formal_release_publish take only release_id: caller-supplied manifest hashes and file tables are forbidden. Each first loads the persisted signed FormalReleasePreparation and release_path, re-verifies the preparation signature, then invokes the narrow StateStore `_verify_prepared_release_target` helper. That helper uses the stored path and preparation only; it requires an ordinary target directory, a release_manifest.json whose raw SHA-256 equals preparation.manifest_sha256, every prepared payload file at its canonical relative path with exact size and SHA-256, and no missing payload, extra regular file, extra or unknown directory, symlink, junction, special entry, traversal, or path escape. It permits only the ordinary parent directories implied by canonical payload paths (for example audit_cards for audit_cards/SZ000001.json); it rejects every other directory. It does not trust a publisher-provided file list or hash. Only after that exact filesystem verification, while the V8 row is still publishing, does one SQLite transaction copy the durable prepared-file table into formal_release_file, set the stored manifest SHA, change formal_release to published, and execute the private V7 validated-to-published compare-and-set. A target that exists without a matching durable preparation is always a conflict; recovery never trusts a release_manifest or file table read solely from the target directory.

record_formal_release_publish_event is append-only, records every deferred I/O/render/rename recovery event with a canonical reason, and leaves a publishing intent reusable. block_formal_release_publish is reserved for a canonical terminal_validation_failed or existing_target_conflict reason, compares-and-sets publishing to blocked, and is idempotent only for the exact same reason; for a terminal validation it atomically calls the private score-run block CAS with {"code": "validation_terminal_failed", "validation_hash": validation_hash}, while a target conflict records {"code": "release_target_conflict", "release_id": release_id, "validation_hash": validation_hash} as the V7 terminal reason. It never removes a target directory. Renderer, hash-verification, staging-cleanup, and pre-rename I/O failures are recorded as retryable events and never call this blocker. No update or delete API exists for published records.

prepare_formal_release_publish(preparation: FormalReleasePreparation) -> None may act only on a matching publishing intent. It rechecks the canonical preparation hash, signed package manifest, nonempty sorted file table, exact release/validation identity, and then atomically stores formal_release_preparation plus formal_release_prepared_file; an equal preparation is idempotent and a different one conflicts. get_formal_release_preparation(release_id: str) -> FormalReleasePreparation | None reads that preparation and its sorted prepared-file rows only through StateStore, recomputes its canonical bytes/hash, and re-verifies the trusted package signature before returning it. The publisher calls prepare after all staged files and release_manifest.json are hashed and before target rename, and calls this getter rather than reading StateStore SQL during recovery.

The only completion APIs are complete_formal_release_publish(release_id) and recover_formal_release_publish(release_id). They require the durable preparation, re-verify its package signature, and independently inspect the stored target path with `_verify_prepared_release_target`; no publisher-provided manifest SHA or payload table is accepted or compared. A target that exists without a matching durable preparation is always a conflict; recovery never trusts a release_manifest or file table read solely from the target directory.

For avoidance of doubt, a terminal_validation_failed reason must name a persisted signature-verified failed validation for the same run/input/release identity with at least one terminal gate; a passed validation hash is never acceptable to the release blocker. The standalone validator owns a direct V7 block only when no publishing intent is being audited. Once a V8 intent exists, the publisher invokes the validator in audit_only mode and block_formal_release_publish atomically owns both state changes. A target-conflict V7 reason includes both {"code": "release_target_conflict", "release_id": release_id, "validation_hash": validation_hash} so it meets the V7 source/validation-lineage requirement.

After V8 is installed, the public StateStore.mark_formal_score_run_blocked first rejects release_publish_in_progress when the run has a formal_release row in publishing state; this is a persistence guard, not merely a CLI convention. block_formal_release_publish alone uses a private transaction-internal score-run block CAS that bypasses that guard, changes the V8 intent and V7 row in one SQLite transaction, and accepts only the signed terminal-validation or signed target-conflict reasons described above. Published and blocked V8 rows remain non-bypassable.

Require V7 formal_score_run persistence to contain registry_manifest_hash, registry_approval_id, registry_purpose, and scoring registry_hash as specified by the scoring plan. V8 validator must be able to load the one persisted root FormalRegistryManifest and prove that its approved production purpose and every child registry hash, rather than a test fixture or mixed configuration, produced the score run.

- [ ] **Step 4: Run V8 and legacy persistence tests**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m unittest tests.test_state_store tests.test_scoring -v
~~~

Expected: PASS; existing legacy score tables and operations remain unchanged.

- [ ] **Step 5: Commit V8 persistence**

~~~powershell
git add -- ashare_pipeline/formal_release_types.py ashare_pipeline/state_store.py tests/test_formal_release_types.py tests/test_state_store.py tests/fixtures/schema_v7.sql
git commit -m "feat: add immutable formal release schema"
~~~

### Task 2: FormalReleaseValidator and Release Identity

**Files:**
- Create: ashare_pipeline/formal_release.py
- Create: tests/test_formal_release.py

**Interfaces:**
- Produces FormalReleaseValidator.validate, FormalReleaseValidator.audit_target_tree, canonical_release_id, release_display_alias, FormalReleaseBlocked, and FormalReleaseDeferred; it imports and re-exports ValidationGate and FormalReleaseValidation from formal_release_types for compatibility.
- Consumes formal_release_types, a V7 run, V7 formal_score_input_manifest and run-bound formal_score_universe_status rows, V5 frozen universe members, V6 bundle/evidence/context rows, V7 metrics/policy/pool rows, verified registry bundle, and StateStore.
- A validator returns every gate result in canonical name order; it returns passed only when every required gate passed.

- [ ] **Step 1: Write the failing release-validation tests**

~~~python
class FormalReleaseValidatorTests(unittest.TestCase):
    def test_release_id_is_deterministic_from_freeze_contract_and_full_input_hash(self):
        self.assertEqual(
            canonical_release_id("2026-08-31T15:00:00+08:00", "formal-v3", "a" * 64),
            "formal-v3-20260831-" + "a" * 64,
        )

    def test_unclassified_or_future_evidence_blocks_release(self):
        validation = self.validator.validate(run_with_unclassified_bj_member())
        self.assertFalse(validation.passed)
        self.assertEqual(validation.gate("universe_complete").status, "failed")
        future = self.validator.validate(run_with_future_feature_evidence())
        self.assertEqual(future.gate("point_in_time_evidence").status, "failed")

    def test_zero_scores_with_full_classification_is_valid(self):
        validation = self.validator.validate(fullly_classified_zero_score_run())
        self.assertTrue(validation.passed)
        self.assertEqual(validation.summary["formal_scored_count"], 0)

    def test_pool_gates_check_exact_keys_capacity_industry_order_and_exclusivity(self):
        validation = self.validator.validate(run_with_legacy_pool_key_or_bad_scan())
        self.assertEqual(validation.gate("pool_integrity").status, "failed")

    def test_test_registry_and_missing_validation_manifest_cannot_be_official(self):
        validation = self.validator.validate(run_using_test_registry())
        self.assertEqual(validation.gate("registry_approval").status, "failed")

    def test_recoverable_jobs_gate_leaves_preview_run_revalidatable(self):
        run_id = preview_run_with_open_source_circuit()
        first = self.validator.validate(run_id)
        self.assertFalse(first.passed)
        self.assertEqual(first.gate("jobs_quiescent").failure_kind, "retryable")
        self.assertEqual(self.store.get_formal_score_run(run_id)["status"], "preview_ready")
        clear_fixture_source_circuit_and_finish_task()
        second = self.validator.validate(run_id)
        self.assertTrue(second.passed)

    def test_published_reaudit_persists_audit_without_transitioning_published_run(self):
        run_id = published_formal_run_with_release()
        audit = self.validator.validate(run_id)
        self.assertTrue(audit.passed)
        self.assertEqual(self.store.get_formal_score_run(run_id)["status"], "published")
        self.assertTrue(self.store.get_formal_release_validation(audit.validation_hash))
~~~

- [ ] **Step 2: Run validator tests and verify RED**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m unittest tests.test_formal_release.FormalReleaseValidatorTests -v
~~~

Expected: FAIL because ashare_pipeline.formal_release does not exist.

- [ ] **Step 3: Implement all release gates**

Import the immutable value types from formal_release_types and define:

~~~python
from ashare_pipeline.formal_release_types import (
    FormalReleaseValidation, ReleaseValidationSigner, ValidationGate,
)

class FormalReleaseValidator:
    def __init__(self, *, signer: ReleaseValidationSigner, ...) -> None: ...
    def validate(
        self, run_id: str, *, transition_mode: Literal["standalone", "audit_only"] = "standalone"
    ) -> FormalReleaseValidation: ...
    def audit_target_tree(
        self, run_id: str, *, release_id: str, mismatch: Mapping[str, object],
    ) -> FormalReleaseValidation: ...
~~~

canonical_release_id uses the fixed contract version, freeze date, and the complete 64-character canonical input hash in the database key and release-directory name. release_display_alias may show only the first sixteen lower-case hash characters to people, but it is not accepted by persistence, CLI inspect, or filesystem APIs and is never a unique key.

Validate these named gates, with deterministic failure details. A passed gate has failure_kind null. A failed jobs_quiescent gate is retryable: it preserves the current pre-publication V7 state (preview_ready before initial validation, validated during publisher revalidation) and may be checked again after the lease, retryable source state, or circuit is resolved without changing the canonical score input. Every other failed gate below is terminal for that exact immutable V7 input and may move an unpublished run to blocked; a corrected lineage/configuration/data set must create a new input hash and V7 run.

1. run_identity: one V7 run has the V3 contract, exact 2026-08-31 close, and one persisted formal_score_input_manifest. The validator canonicalizes that manifest again, requires its SHA-256 to equal run input_hash, verifies the selection version, capacities, industry caps, calendar/context refresh generations, every selected evidence/feature/config hash, evidence-manifest hash, frozen_universe_input_hash, universe_registry_manifest_hash, and approved production registry bundle identity. It requires universe_registry_manifest_hash == run.registry_manifest_hash.
2. universe_complete: the frozen V5 universe has a nonempty SHA-256 and sorted unique SH/SZ/BJ members, exactly one V5 source link per BJ/SH/SZ exchange, and each source link resolves through a verified formal_universe_source task receipt/result to the same root registry manifest and frozen-input hash. It requires the V5 frozen_input_hash and registry_manifest_hash to equal the V7 input manifest's corresponding values and that root to equal the V7 run/bundle root. The same V7 run has exactly one permitted formal_score_universe_status row per member. An empty or missing run-bound status set fails even when there are zero score rows; V5 collection-stage status rows are not release classifications.
3. evidence_lineage: every formal fact, feature, metric, policy outcome, and score reference resolves to a verified formal snapshot, original content hash, parser/mapping version, and matching security/period identity.
4. point_in_time_evidence: every referenced published/effective instant is at or before freeze. Captured-after-freeze evidence passes only if independently verified publication and effective instants pass.
5. score_completeness: every formal_scored run-bound member has all seven dimensions, Sc, B, R safety, risk exposure, C components, required slot evidence, feature hash, and valid peer contexts; pool_vetoed members may retain a score but do not count as formal_scored.
6. pending_and_veto_reasons: every run-bound pending, vetoed, or out-of-scope member has deterministic nonempty source-backed reasons and all listed veto flags are traceable.
7. jobs_quiescent: no leased formal task, unresolved terminal/retryable error without a classified reason, or source-circuit condition is left unexplained.
8. pool_integrity: strong and wait are disjoint, counts use exactly strong/wait, each capacity is at most 20/50, each frozen secondary-industry count is at most 4/10, members satisfy the exact corresponding V3 thresholds, comparison keys/order are correct, and all cap skips continue scanning correctly.
9. registry_approval: source, mapping, feature, scoring, redline, status, cyclic, event, and industry configuration hashes are complete and approved for production; no test-only registry participates.
10. output_preconditions: input/evidence manifest hashes are canonical and all required release artifacts are renderable. Its canonical passed details are deliberately target-state-independent: an absent target and a byte-identical target produce the same passed gate record and validation hash. Target-tree existence, unexpected files, and byte equality are checked by the publisher after it locates a publishing intent; a mismatch is a release conflict, not a new validation identity.

The validation hash is the SHA-256 of the Task 1 canonical validation JSON containing validator version/key ID, run ID, release ID, input hash, freeze instant, contract version, ordered complete required gate records including failure_kind, and summary; FormalReleaseValidator signs those exact bytes with its injected ReleaseValidationSigner. Persist the passed or failed signed validation to V8. In standalone mode (formal-validate or initial pre-publish validation), a passed validation calls mark_formal_score_run_validated through its compare-and-set API only when the current run state is preview_ready. A validated run accepts only an equal persisted pass hash as a no-op confirmation; it never transitions again. In audit_only mode (publisher re-audit or a published read-only audit), the validator only persists the signed audit record and never changes V7 state. A published run, whether its re-audit passes or fails, always uses audit_only. A failed validation whose all failed gates are retryable preserves its current preview_ready or validated state. In standalone mode only, a failed validation with any terminal gate first persists the signed failed validation, then calls mark_formal_score_run_blocked(run_id, {"code": "validation_terminal_failed", "validation_hash": validation.validation_hash}) only when the run is not published. During a publishing-intent re-audit, the publisher calls audit_only and block_formal_release_publish exclusively owns the atomic V8 publishing-to-blocked plus V7 validated-to-blocked transition. No failed validation creates a release directory.

audit_target_tree is the only target-conflict audit factory. It re-evaluates the normal complete required gate set in audit_only mode, replaces output_preconditions with a terminal failed gate containing the canonical target/preparation mismatch, re-signs the complete resulting validation, and returns it for append-only persistence. It never calls a V7 or V8 transition, including when the release is already published. FormalReleasePublisher uses this method whenever an existing publishing or published target fails byte-for-byte comparison, rather than attempting to construct a validation or signature itself.

- [ ] **Step 4: Run validator and scoring regression suites**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m unittest tests.test_formal_release tests.test_formal_score_runner tests.test_formal_pool -v
~~~

Expected: PASS; a legacy run cannot satisfy V3 validation.

- [ ] **Step 5: Commit release validation**

~~~powershell
git add -- ashare_pipeline/formal_release.py tests/test_formal_release.py
git commit -m "feat: validate formal V3 releases"
~~~

### Task 3: Deterministic Package Rendering and Atomic Publication

**Files:**
- Modify: ashare_pipeline/formal_release.py: renderer, SHA verifier, staged publisher, and idempotence comparator
- Modify: tests/test_formal_release.py: package, failure, conflict, and replay cases

**Interfaces:**
- Produces FormalReleaseRenderer, FormalReleasePublisher.publish, FormalReleasePublisher.recover_existing_publish, PublishedFormalRelease, ReleaseConflict, and FormalReleaseDeferred.
- Consumes a passed, signature-verified FormalReleaseValidation for new staging, or a previously persisted exact publishing intent plus its stored signed validation for post-rename recovery.
- Creates data/releases/.staging/release_id.nonce before atomic replacement of data/releases/release_id.

- [ ] **Step 1: Write failing publication tests**

~~~python
class FormalReleasePublisherTests(unittest.TestCase):
    def test_publisher_writes_required_deterministic_files_and_sha_manifest(self):
        validation = self.passed_validation()
        published = self.publisher.publish(validation)
        paths = set(relative_paths(published.path))
        self.assertTrue({
            "release_manifest.json", "universe_status.csv", "scores.csv",
            "strong_attention.csv", "waiting_price.csv", "evidence_manifest.json",
            "quality_report.md", "audit_cards/SZ000001.json",
        } <= paths)
        verify_release_manifest(published.path)

    def test_identical_retry_is_idempotent_but_published_byte_conflict_is_read_only(self):
        first = self.publisher.publish(self.passed_validation())
        second = self.publisher.publish(self.passed_validation())
        self.assertEqual(second.status, "already_published")
        Path(first.path, "scores.csv").write_bytes(b"changed")
        with self.assertRaisesRegex(ReleaseConflict, "existing release differs"):
            self.publisher.publish(self.passed_validation())
        self.assertEqual(self.store.get_formal_release(self.release_id)["status"], "published")
        self.assertEqual(self.store.get_formal_score_run(self.run_id)["status"], "published")

    def test_failed_staging_verification_is_retryable_and_never_leaves_partial_target(self):
        self.publisher.renderer = renderer_that_tampers_after_hash()
        with self.assertRaisesRegex(FormalReleaseDeferred, "file hash"):
            self.publisher.publish(self.passed_validation())
        self.assertFalse((self.release_root / self.release_id).exists())
        self.assertEqual(list((self.release_root / ".staging").iterdir()), [])
        self.assertEqual(self.store.get_formal_release(self.release_id)["status"], "publishing")
        self.publisher.renderer = stable_renderer()
        self.assertEqual(self.publisher.publish(self.passed_validation()).status, "published")

    def test_retryable_revalidation_defers_and_reuses_publishing_intent(self):
        self.publisher.validator = pass_once_then_retryable_jobs_quiescent()
        with self.assertRaisesRegex(FormalReleaseDeferred, "jobs_quiescent"):
            self.publisher.publish(self.passed_validation())
        self.assertEqual(self.store.get_formal_release(self.release_id)["status"], "publishing")
        self.assertEqual(self.store.get_formal_score_run(self.run_id)["status"], "validated")
        self.assertFalse((self.release_root / self.release_id).exists())
        self.publisher.validator = stable_passing_validator()
        published = self.publisher.publish(self.passed_validation())
        self.assertEqual(published.status, "published")

    def test_targetless_existing_intent_terminal_reaudit_blocks_v8_and_v7_together(self):
        self.publisher.renderer = renderer_that_fails_before_target()
        with self.assertRaises(FormalReleaseDeferred):
            self.publisher.publish(self.passed_validation())
        self.assertFalse((self.release_root / self.release_id).exists())
        self.publisher.validator = terminal_validator()
        result = invoke_cli("formal-publish", "--run-id", self.run_id, "--release-root", self.release_root)
        self.assertNotEqual(result.exit_code, 0)
        self.assertEqual(self.store.get_formal_release(self.release_id)["status"], "blocked")
        self.assertEqual(self.store.get_formal_score_run(self.run_id)["status"], "blocked")

    def test_crash_after_rename_recovers_with_stored_validation_before_fresh_cli_validation(self):
        self.publisher.fail_after_target_rename_before_database_completion = True
        with self.assertRaisesRegex(RuntimeError, "after rename"):
            self.publisher.publish(self.passed_validation())
        self.assertTrue((self.release_root / self.release_id).is_dir())
        self.assertEqual(self.store.get_formal_release(self.release_id)["status"], "publishing")
        recovered = invoke_cli("formal-publish", "--run-id", self.run_id, "--release-root", self.release_root)
        self.assertEqual(recovered.exit_code, 0)
        self.assertIn("published", recovered.stdout)
        self.assertEqual(self.store.get_formal_release(self.release_id)["status"], "published")

    def test_tampered_target_after_rename_before_database_completion_never_recovers(self):
        self.publisher.fail_after_target_rename_before_database_completion = True
        with self.assertRaisesRegex(RuntimeError, "after rename"):
            self.publisher.publish(self.passed_validation())
        Path(self.release_root, self.release_id, "scores.csv").write_bytes(b"tampered")
        with self.assertRaisesRegex(ReleaseConflict, "prepared file differs"):
            self.publisher.recover_existing_publish(self.run_id)
        self.assertEqual(self.store.get_formal_release(self.release_id)["status"], "blocked")
        self.assertEqual(self.store.get_formal_score_run(self.run_id)["status"], "blocked")
        self.assertGreater(
            count_read_only_target_audits(self.store, self.run_id), 0,
        )
~~~

- [ ] **Step 2: Run publication tests and verify RED**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m unittest tests.test_formal_release.FormalReleasePublisherTests -v
~~~

Expected: FAIL because the renderer and publisher do not exist.

- [ ] **Step 3: Implement the package and atomic protocol**

Render these minimum artifacts with UTF-8, LF newlines, stable column order, sorted rows, and canonical JSON:

~~~text
release_manifest.json
universe_status.csv
scores.csv
strong_attention.csv
waiting_price.csv
evidence_manifest.json
audit_cards/<security_id>.json
quality_report.md
~~~

universe_status.csv is rendered only from the V7 run-bound formal_score_universe_status ledger and contains every frozen universe member, including BJ entries and source-backed reasons. scores.csv includes dimensions, Sc, B, R safety, risk exposure, C/D/P/H/K, peer metadata, grades, and hashes. Both pool CSVs include ordinal, comparison key, secondary industry, running industry count, selection reason, score hash, and policy hash. evidence_manifest.json contains only canonical source/fact/feature/config references and their hashes, not copied raw documents. audit card output is generated for every scored or vetoed scored member with evidence, cycle, redline, peer, and recomputation inputs. quality_report.md declares full-universe coverage, status counts, formal score count, pool counts, blockers, and gate outcomes.

Use the exact protocol:

1. Derive the full canonical release ID from the immutable V7 run. Before requesting a fresh validation, look up an existing V8 intent by that exact release ID/run/input. If it is publishing and its target directory exists, load its persisted signature-verified validation and durable signature-verified FormalReleasePreparation, use those two records to verify every target byte, and call recover_formal_release_publish; do not run a new validator or require a newly produced validation hash for this post-rename recovery path. If it is publishing and its target directory does not exist, any fresh re-audit must use validate(..., transition_mode="audit_only"): a passed equal hash continues the same intent, retryable failures defer it, and a terminal failed audit is persisted then sent to block_formal_release_publish for the atomic V8/V7 block. It must never use standalone validation while a publishing intent exists. If it is already published, do not stage, revalidate, or transition anything: re-read and verify the target tree against its stored manifest/file table. Return already_published only when it is byte-identical. If either existing target is tampered, append a failed read-only audit validation, raise ReleaseConflict, and leave both V8 release and V7 run published. Only when no publishing/published intent exists does the CLI obtain a standalone passed signature-verified validation and call begin_formal_release_publish. The returned row is the committed V8 publishing intent while the V7 run is validated; create an owned unique same-volume staging directory.
2. Render all non-manifest artifacts. Open each file as bytes, calculate SHA-256 and byte length, reject traversal/symlink escape, and re-read it to verify the calculated hash.
3. Build a canonical payload-file table sorted by relative path. It includes every artifact other than release_manifest.json; release_manifest is intentionally excluded from its own table to avoid an impossible self-hash. Write evidence_manifest and then release_manifest last. release_manifest includes release ID, complete input/validation hashes, contract/freeze, canonical formal_pool_counts, every payload-file hash/length/media type, and gate summary. Hash and re-read both manifests. Persist the raw release_manifest SHA only in formal_release.manifest_sha256 after publication.
3a. Before target rename, construct FormalReleasePreparation from the raw release_manifest SHA and canonical payload-file table, sign its canonical bytes with ReleasePackageSigner, and call prepare_formal_release_publish. The durable signed preparation—not a self-describing target file—becomes the recovery trust anchor.
4. Only for a newly rendered publishing intent, re-run the validator in audit_only mode against the run and compare the staged file table against its in-memory manifest. The output_preconditions pass record is target-state-independent, so an unchanged run produces the exact pre-begin validation hash whether the target is absent or later byte-identical. If this re-audit passes, require its validation hash to equal the pre-begin passed validation hash. If it has only retryable failed gates, persist that re-audit, remove the owned staging directory, retain the matching V8 publishing intent and V7 validated state, record a retryable event, and raise FormalReleaseDeferred; the next exact publish retry reuses the intent. If it has any terminal failed gate, persist it then block that publishing intent through block_formal_release_publish with {"code": "terminal_validation_failed", "validation_hash": validation_hash}; that one transaction records the V7 blocked reason required by V7. This branch is never applied to a recovered or already-published row.
5. If target exists for a publishing intent, require a matching durable signed preparation, then require that its release_manifest raw bytes and every payload-table file are byte-identical to that preparation and have no extra/missing expected files or symlink/unknown entries. If its matching V8 row is publishing, call recover_formal_release_publish to re-verify the exact target and complete the V8/V7 database transaction. If it is a published row, use step 1's read-only success/conflict behavior. Otherwise call block_formal_release_publish with a canonical existing_target_conflict reason including the stored validation hash and raise ReleaseConflict without changing target. If target does not exist but begin returned a matching publishing intent left by a pre-rename crash, reuse that intent and continue with a fresh owned staging directory.
6. If target does not exist, require the signed preparation already committed in step 3a, atomically rename the completed staging directory to the target directory on the same volume, then call complete_formal_release_publish for that precommitted publishing intent. A process/DB failure after rename leaves the target, intent, and recovery trust anchor intact; the next exact retry must recover it rather than return already_published without durable rows.
7. On renderer, hash-verification, staging-cleanup, or pre-rename I/O/rename failure, remove only the explicit owned staging directory, append a canonical retryable publish event, retain the publishing intent and V7 validated state, and raise FormalReleaseDeferred; a later exact retry may re-render and publish the same immutable run. Only the terminal-validator branch in step 4 or an existing-target conflict in step 5 calls block_formal_release_publish. After a successful rename, retain the publishing intent and target for recovery; never delete an existing release target.

For every existing-target mismatch, FormalReleasePublisher calls validator.audit_target_tree with the stored full release identity and canonical mismatch details and persists that signed audit append-only. For a published row it then raises ReleaseConflict without changing V8/V7 state. For a publishing row it next calls block_formal_release_publish with the signed audit's validation hash in the canonical existing_target_conflict reason, thereby atomically blocks the irreparable target conflict and its V7 run, then raises ReleaseConflict. It has no signer-backed shortcut of its own.

Do not use a mutable current pointer as evidence. If a convenience latest pointer is later added, derive it outside the release identity and do not let it overwrite a release directory.

- [ ] **Step 4: Run publication and full release suites**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m unittest tests.test_formal_release tests.test_state_store -v
~~~

Expected: PASS; repeated equal publication is byte-for-byte idempotent.

- [ ] **Step 5: Commit immutable publishing**

~~~powershell
git add -- ashare_pipeline/formal_release.py tests/test_formal_release.py
git commit -m "feat: publish immutable formal release packages"
~~~

### Task 4: Formal CLI and Isolated Release Orchestration

**Files:**
- Create: ashare_pipeline/formal_cli.py
- Modify: ashare_pipeline/__main__.py: register formal subcommands only
- Create: tests/test_formal_cli.py

**Interfaces:**
- Produces commands formal-validate, formal-publish, formal-inspect, and formal-quality-report.
- formal-publish first resolves the immutable full release identity. For a post-rename publishing intent with an existing target, it invokes the publisher's stored-validation recovery path. For a targetless existing publishing intent it calls the validator in audit_only mode and lets the publisher continue, defer, or atomically block that intent; only when no intent exists does it call standalone validation and pass the result to the publisher. It never accepts a manually typed validation hash.
- Commands display whether the result is preview, blocked, validated, published, or already_published, and return nonzero on blocked/error outcomes.

- [ ] **Step 1: Write failing CLI tests**

~~~python
class FormalCliTests(unittest.TestCase):
    def test_publish_validates_before_publishing_and_never_calls_legacy_finalizer(self):
        result = invoke_cli("formal-publish", "--run-id", self.run_id, "--release-root", self.root)
        self.assertEqual(result.exit_code, 0)
        self.assertIn("published", result.stdout)
        self.assertEqual(self.legacy_finalize_call_count, 0)

    def test_blocked_run_has_nonzero_exit_and_no_release_target(self):
        result = invoke_cli("formal-publish", "--run-id", self.blocked_run_id, "--release-root", self.root)
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("blocked", result.stderr)
        self.assertFalse((self.root / blocked_release_id()).exists())

    def test_validate_refuses_an_active_publishing_intent_without_changing_either_state(self):
        create_targetless_publishing_intent(self.store, self.run_id)
        result = invoke_cli("formal-validate", "--run-id", self.run_id)
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("use formal-publish", result.stderr)
        self.assertEqual(self.store.get_formal_release(self.release_id)["status"], "publishing")
        self.assertEqual(self.store.get_formal_score_run(self.run_id)["status"], "validated")

    def test_inspect_reads_only_published_formal_release(self):
        result = invoke_cli("formal-inspect", "--release-id", self.release_id, "--release-root", self.root)
        self.assertIn("formal_scored_count", result.stdout)
~~~

- [ ] **Step 2: Run CLI tests and verify RED**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m unittest tests.test_formal_cli -v
~~~

Expected: FAIL because formal CLI handlers are not registered.

- [ ] **Step 3: Implement narrow commands**

Implement:

~~~text
python -m ashare_pipeline formal-validate --run-id <id>
python -m ashare_pipeline formal-publish --run-id <id> [--release-root <path>]
python -m ashare_pipeline formal-inspect --release-id <id> [--release-root <path>]
python -m ashare_pipeline formal-quality-report --release-id <id> [--release-root <path>]
~~~

Use data/releases as the default root and only allow a caller-provided root for tests or an explicitly configured workspace path. formal-validate first resolves the full release identity: with no V8 intent it persists a standalone validation but never renders; with an active publishing intent it refuses without validating or changing either state and directs the caller to formal-publish, which owns recovery/defer/block atomically; with a published row it may append an audit_only validation only. Except for the exact post-rename recovery path, formal-publish revalidates; it uses audit_only rather than standalone validation whenever a targetless publishing intent already exists, refuses an already-blocked or test-preview run, publishes only after a passed signature-verified validation, and prints the full release ID/path/hash/counts; it may display the non-authoritative short alias for readability. formal-inspect requires the full release ID and formal-quality-report invokes the V8 read-only loader. Do not add a command that directly edits pool membership, score items, validation gate values, registry approvals, or release manifests.

- [ ] **Step 4: Run CLI and legacy command regression suites**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m unittest tests.test_formal_cli tests.test_orchestrator tests.test_reporting -v
~~~

Expected: PASS; legacy command output remains nonformal.

- [ ] **Step 5: Commit formal CLI**

~~~powershell
git add -- ashare_pipeline/formal_cli.py ashare_pipeline/__main__.py tests/test_formal_cli.py
git commit -m "feat: add validated formal release CLI"
~~~

### Task 5: Published-Only Reporting and Compatibility Reader

**Files:**
- Create: ashare_pipeline/formal_release_reporting.py
- Modify: ashare_pipeline/reporting.py: formal-release routing and legacy count compatibility reader
- Create: tests/test_formal_release_reporting.py

**Interfaces:**
- Produces load_published_formal_release, formal_pool_summary, load_formal_audit_card, and render_formal_release_summary.
- Consumes StateStore, a published V8 release row, its release directory, and V8 release manifest.
- Returns canonical strong/wait counts to formal callers. The legacy adapter can map old strong_attention/waiting_price input keys into a display-only legacy view but cannot create a formal release or alter a formal count.

- [ ] **Step 1: Write failing reporting tests**

~~~python
class FormalReleaseReportingTests(unittest.TestCase):
    def test_reader_rejects_unpublished_or_hash_tampered_release(self):
        with self.assertRaisesRegex(ValueError, "published"):
            load_published_formal_release(self.store, self.staging_release_id, self.staging_path)
        Path(self.published_path, "scores.csv").write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "sha256"):
            load_published_formal_release(self.store, self.release_id, self.published_path)

    def test_reader_rejects_any_unknown_file_or_symlink_in_published_tree(self):
        Path(self.published_path, "unexpected.txt").write_bytes(b"extra")
        with self.assertRaisesRegex(ValueError, "unknown release entry"):
            load_published_formal_release(self.store, self.release_id, self.published_path)

    def test_summary_uses_canonical_counts_and_keeps_bj_universe_rows(self):
        release = load_published_formal_release(self.store, self.release_id, self.published_path)
        self.assertEqual(formal_pool_summary(release), {"strong": 2, "wait": 3})
        self.assertIn("BJ430001", {row["security_id"] for row in release.universe_status})

    def test_legacy_count_alias_is_read_only_compatibility(self):
        self.assertEqual(legacy_pool_count_view({"strong_attention": 1, "waiting_price": 2}), {
            "strong": 1, "wait": 2,
        })
        with self.assertRaisesRegex(ValueError, "canonical"):
            validate_formal_pool_counts({"strong_attention": 1, "waiting_price": 2})
~~~

- [ ] **Step 2: Run reporting tests and verify RED**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m unittest tests.test_formal_release_reporting -v
~~~

Expected: FAIL because the published-only reader does not exist.

- [ ] **Step 3: Implement verified release reads**

load_published_formal_release first obtains the V8 formal_release row by full release ID and requires status published, exact normalized release path, and an on-disk raw release_manifest SHA equal to formal_release.manifest_sha256. It then parses release_manifest JSON canonically and requires its canonical payload table to equal formal_release_file exactly. It walks the entire target tree: release_manifest.json plus the payload-table regular files must be the complete file set, every listed parent directory must be implied by a payload path, and any unknown regular file, unknown directory, symlink, junction, special file, traversal path, or missing expected file rejects the release. It recomputes each payload SHA/byte size before returning typed rows. It verifies that manifest formal_pool_counts has exactly strong and wait, maps the two fixed artifact filenames to canonical pool IDs, recomputes counts, and validates every selected row appears in scores and in run-bound universe status. It must not read a V7 database run as a substitute when a release directory is absent.

Modify reporting.py only at the formal request boundary: a caller that supplies a V8 release ID/path receives the formal reader summary; callers of existing legacy report functions retain their current behavior and labels. Never derive a formal pool from old official_pool_counts, old score items, or a preview status file.

- [ ] **Step 4: Run reporting and release regression suites**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m unittest tests.test_formal_release_reporting tests.test_formal_release tests.test_reporting -v
~~~

Expected: PASS; tampering is visible instead of silently falling back to a database value.

- [ ] **Step 5: Commit reporting integration**

~~~powershell
git add -- ashare_pipeline/formal_release_reporting.py ashare_pipeline/reporting.py tests/test_formal_release_reporting.py
git commit -m "feat: report verified formal releases"
~~~

### Task 6: End-to-End, Reproducibility, and Sensitivity Acceptance Tests

**Files:**
- Modify: tests/test_formal_release.py: full universe release fixtures and reproducibility coverage
- Create: tests/test_formal_v3_e2e.py
- Create: tests/test_formal_sensitivity.py

**Interfaces:**
- Produces a hermetic V5-to-V8 fixture builder that creates SH, SZ, and BJ formal members, verified inputs, valid peer cohorts, explicit pending/veto reasons, and either a test-preview bundle or an injected production-purpose contract fixture.
- Test-purpose registries exercise preview rejection only. Official publication tests use a fully populated purpose-official registry bundle signed by an injected fake verifier, with every role hash and approval ID persisted in the temporary V6 store; it exercises the official contract path without inventing a real production configuration.
- Sensitivity reporting consumes an already validated configuration variant matrix and writes preview-only comparison rows; it cannot alter a published release or pool.

- [ ] **Step 1: Write failing full-contract tests**

~~~python
class FormalV3EndToEndTests(unittest.TestCase):
    def test_same_verified_fixture_inputs_produce_same_release_bytes(self):
        first = build_and_publish_official_contract_fixture_release(self.root / "one")
        second = build_and_publish_official_contract_fixture_release(self.root / "two")
        self.assertEqual(tree_sha256(first.path), tree_sha256(second.path))
        self.assertEqual(load_manifest(first.path)["input_hash"], load_manifest(second.path)["input_hash"])

    def test_each_universe_failure_mode_blocks_or_classifies_without_silent_drop(self):
        self.assert_release_blocked(run_without_universe_status())
        self.assert_release_blocked(run_with_future_evidence())
        self.assert_release_blocked(run_with_active_task())
        release = build_fully_classified_zero_score_official_contract_fixture_release()
        self.assertEqual(release.status, "published")

    def test_test_purpose_registry_can_never_publish(self):
        self.assert_release_blocked(run_using_test_purpose_registry())

class FormalSensitivityTests(unittest.TestCase):
    def test_sensitivity_is_preview_only_and_never_changes_published_release(self):
        result = run_sensitivity(self.published_release, weight_delta=Decimal("0.05"), threshold_delta=Decimal("10"))
        self.assertEqual(result.status, "preview")
        self.assertEqual(tree_sha256(self.published_release.path), self.before_hash)
~~~

- [ ] **Step 2: Run end-to-end tests and verify RED**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m unittest tests.test_formal_v3_e2e tests.test_formal_sensitivity -v
~~~

Expected: FAIL because the V5-V8 fixture integration and sensitivity report do not exist.

- [ ] **Step 3: Implement complete acceptance coverage**

Build both a test-preview fixture path and an injected official-contract fixture path. The preview path uses purpose test and can never pass FormalReleaseValidator. The official-contract fixture uses purpose official, a complete root bundle, all persisted child blobs, and a fake verifier scoped to the temporary test store only. It must create a mixed universe with scored, pending, vetoed, and out-of-scope members and include at least one BJ member. Confirm:

- Same source bytes, canonical input order, registry hashes, and frozen time produce byte-identical files, manifests, sorted pool members, and release ID.
- One missing status, duplicate member, future input, non-verified source, pending task, active source circuit, invalid pool key, over-cap industry, out-of-order comparison key, duplicate member, or manifest mismatch blocks publication.
- A fully classified all-pending/all-vetoed universe with zero formal scores can publish and reports zero coverage.
- Industry-cap scanning continues after a capped industry; strong/wait do not overlap; an unselected strong candidate does not enter wait.
- A correction changes input_hash and therefore release ID, leaving the first package untouched.
- Sensitivity uses V3 weights plus/minus five percentage points and thresholds plus/minus ten score points only as an explicitly labeled preview comparison. It records membership deltas by security/industry/template and never writes to the published package, release rows, score run, or pool membership.

- [ ] **Step 4: Run full formal and repository regression suites**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m unittest tests.test_formal_v3_e2e tests.test_formal_sensitivity tests.test_formal_release tests.test_formal_release_reporting tests.test_formal_cli -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
~~~

Expected: PASS; existing V1/V2 tests stay green and no test reaches a live source.

- [ ] **Step 5: Commit acceptance coverage**

~~~powershell
git add -- tests/test_formal_release.py tests/test_formal_v3_e2e.py tests/test_formal_sensitivity.py
git commit -m "test: cover formal V3 release acceptance"
~~~

## Plan Self-Review

- Spec coverage: Tasks 1-2 establish immutable V8 release identity and all V3 validation gates: full universe status, verified point-in-time evidence, complete scores, explicit pending/veto reasons, quiescent jobs, exact pool rules, approved registries, and renderability. Task 3 provides same-volume staging, byte hashes, manifest-last ordering, atomic commit, idempotent retry, and conflict blocking. Tasks 4-5 isolate CLI/reporting from legacy finalization and enforce canonical strong/wait keys. Task 6 verifies full-universe release behavior, BJ coverage, zero-score legality, reproducibility, corrections, capacity, and preview-only sensitivity analysis.
- Placeholder scan: every source file, table, public interface, gate, state, required artifact, staging behavior, fixture, and test command is named. The absence of a user-approved production registry remains an explicit publication blocker rather than an implicit default.
- Type consistency: V7 FormalScoreRun and score/policy/pool rows feed FormalReleaseValidator; its FormalReleaseValidation is the only input to FormalReleasePublisher; the published V8 manifest feeds formal_release_reporting and CLI inspection. Legacy score/run/report paths have no type conversion into this chain.
