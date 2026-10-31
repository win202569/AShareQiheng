# Final evidence-integrity fix — independent scoped re-review

## Review identity and boundary

- Fix base: `c799531f8a8a2173c5557db4d1d9afaf6ebd464e`.
- Reviewed head: `dd1e3322dfa73c7c53ca7c0944544c895b781789`.
- Frozen change boundary: `review-c799531..dd1e332.diff`, opened exactly once. It contains five changed files: `ashare_pipeline/state_store.py`, `ashare_pipeline/orchestrator.py`, `tests/test_state_store.py`, `tests/test_orchestrator.py`, and `tests/test_deep_worker.py` (548 insertions, 17 deletions).
- Required context read: the complete final-fix brief and report, the private progress ledger's fresh whole-branch Ruling, current transaction/schema/contract/raw-slot/progress/cleanup implementations, and the focused current test contexts referenced by the package.
- Review was read-only with respect to source and tests. No Git command, network access, tracked runtime database, broad/full suite, or subagent was used. No isolated probe was run because static inspection did not leave a concrete behavioral doubt; fresh verification evidence in the implementation report was checked against the tests present in the frozen boundary.

## Severity summary

- Critical: 0
- Important: 0
- Minor: 0 new findings in this fix boundary

The three previously deferred whole-branch Minors remain deliberately out of this fix and were not modified. They are not regressions introduced by `c799531..dd1e332`.

## Requirement-by-requirement verdicts

### 1. Transactional fail-closed persistence and idempotency — PASS

`StateStore.put_feature_bundle()` computes context-free content before the database transaction, then enters the existing `BEGIN IMMEDIATE` transaction and invokes `_validate_feature_bundle_evidence()` at `ashare_pipeline/state_store.py:914-915`. Only after successful validation does it query the existing feature row at lines 916-925; the idempotent return is therefore downstream of validation at lines 926-931. Header insertion starts at line 934 and value insertion at line 950, so missing, empty-store, malformed, or mismatched referenced facts/snapshots cannot write either table.

The regressions at `tests/test_state_store.py:660-678` prove an evidence-bearing production-built ready bundle against an empty database yields zero `feature_set` and zero `feature_value` rows. Lines 680-709 prove the already-existing/idempotent path revalidates first and leaves the previously valid 1/363 rows unchanged after referenced-fact loss.

### 2. Exact bounded set reads and canonical fact reconstruction — PASS

The validator deduplicates by evidence fact ID, rejecting conflicting metadata for the same ID (`state_store.py:807-814`). Unique sorted IDs are read in fixed 256-ID chunks (`state_store.py:818-826`), every returned row is reconstructed through `FinancialFact.from_record()` (`state_store.py:827-833`), and exact set equality rejects omissions (`state_store.py:834-835`). `FinancialFact.from_record()` recomputes the canonical ID from normalized content and rejects an ID/content mismatch (`ashare_pipeline/financial_schema.py:252-269`), while its normalization validates security, statement, metric, period shape, finite value, unit, timestamps, snapshot ID, source field, SHA-256 raw hash, and active mapping version.

Unique fact-owned snapshot IDs use the same fixed-size chunk pattern (`state_store.py:837-844`); non-string/duplicate returned identity rows and set inequality fail closed (`state_store.py:845-851`). The primary-key schema makes duplicates impossible in a healthy database, while the explicit checks preserve fail-closed behavior under malformed result sets. Parameter cardinality is safely below SQLite's common bounds and set equality spans all chunks rather than accepting partial batches.

### 3. EvidenceRef/fact and descriptor-decidable raw binding — PASS

Exact fact-ID resolution is enforced by the evidence-key/fact-key set equality and dictionary lookup. Every distinct referenced fact must match bundle security and all public shared metadata: snapshot ID, source field, raw-row hash, announced time, and effective time (`state_store.py:853-863`). This applies equally to every operand of derived values. Derived formula evaluation is intentionally absent; only existence, canonical reconstruction, security, snapshot existence, and shared metadata are checked, matching the requested boundary.

For every descriptor-decidable observed raw value, the validator binds canonical dimension/key, observed status, recognized seven-period mapping, unit, active formula/mapping version, and exactly one evidence reference (`state_store.py:865-889`). It then binds the referenced canonical fact's metric, period end, numeric value, unit, mapping version, and allowed source field (`state_store.py:890-899`). The schema-owned `raw_financial_slot_descriptor()` remains the single authority; the StateStore does not copy a formula engine.

The table-driven tests cover missing fact/snapshot and every public evidence metadata mismatch (`tests/test_state_store.py:711-820`), plus wrong security and raw metric/period/value/unit/mapping rejection (`tests/test_state_store.py:822-876`). The mapping corruption case also exercises canonical ID/content reconstruction. Existing public-contract tests remain responsible for raw dimension/key/status/cardinality shape; the new database validator independently enforces those attributes before persistence.

### 4. Progress revalidation, consistent reads, no fallback, bounded unknowns, no value leak — PASS

Progress retains verified canonical file/hash parsing and full DB-header comparison (`ashare_pipeline/orchestrator.py:1066-1077`), then invokes the same public `StateStore.validate_feature_bundle_evidence()` used by persistence (`orchestrator.py:1078`; `state_store.py:796-800`). That public method runs all fact and snapshot reads inside one explicit deferred read transaction (`state_store.py:277-287`, `796-800`), giving a consistent SQLite snapshot across its bounded reads.

`seen_feature_securities` is updated before any candidate validation (`orchestrator.py:1060-1065`), so a bad newest row is counted once and cannot fall through to an older row. The exception path increments `unknown_failures` exactly once for that candidate and does not retain the invalid row (`orchestrator.py:1079-1082`). Status aggregation consumes only header-level public metadata and missing reasons; neither evidence details nor raw feature values are emitted.

The real progress regression creates an older and newer valid row, deletes a snapshot referenced only by the newest evidence, and proves zero ready/partial/blocked counts, exactly one unknown, no fallback, and all formal/pool gates closed (`tests/test_orchestrator.py:1248-1299`).

### 5. Positive production order and gate closure — PASS

The shared positive fixture records three statement snapshots, inserts canonical production `FinancialFact` objects, and builds the ready bundle through the production financial-feature builder (`tests/test_state_store.py:163-211`). The orchestrator regression then performs bundle parse, canonical feature-file write, transactional DB persistence, verified file read, and real status/progress calculation (`tests/test_orchestrator.py:1204-1235`). It observes exactly one `financial_ready` result and explicitly proves `formal_score_ready`, `seven_dimension_ready`, waiting-price pool, and strong-attention pool remain closed (`tests/test_orchestrator.py:1236-1246`).

Existing deep-worker order remains snapshot persistence/verification, fact normalization/insertion, bundle publication, then DB persistence; the fix changes none of those producer steps. The reported focused modules (258 tests), fresh full discovery (363 tests), and staged fresh full discovery (363 tests) all passed.

### 6. Deep-worker orphan cleanup — PASS

No production cleanup change was needed. `_write_and_store_feature_bundle()` deletes only when `write_feature_bundle()` reports `file_created=True`, no matching committed DB header owns that path/hash, and a fresh byte read still hashes to the expected bundle hash (`ashare_pipeline/deep_worker.py:1165-1197`). A concurrently replaced file or a pre-existing canonical file is preserved.

The focused regression uses the real writer/store rejection path: the newly created invalid orphan is removed, while a manually pre-created byte-identical canonical file survives a second DB rejection, with zero DB feature headers (`tests/test_deep_worker.py:1491-1525`).

### 7. Test-diff integrity — PASS

The 548-line test-heavy change is high signal rather than a test-only production mirror. It uses real `StateStore`, real `FinancialFact` canonicalization, the production financial-feature builder, real canonical file write/read, real progress, and the existing real deep-worker helper. The shared test fixture centralizes prerequisite snapshots/facts but does not reimplement validation logic.

Legacy StateStore tests that previously used invented evidence now seed an actual snapshot row and canonical fact before exercising atomicity/conflict/latest-row behavior (`tests/test_state_store.py:151-159`, 584-632, 878-947). Their original row-count, conflict, rollback, ordering, and parsed-content assertions remain intact; no broad assertion weakening or mock substitution was introduced. The ready-path fixture uses the complete canonical fact set rather than vacuous evidence. The mapping mutation reaches rejection partly through canonical ID/content verification, but production also contains the explicit mapping comparison; this is not a correctness gap.

### 8. New production risks and scope control — PASS

No schema or migration changed. The only new production behavior is a fixed-size set read validator plus one progress call. With the bounded candidate set and 256-ID chunks, query count and parameter size are reasonable; writes remain under the pre-existing immediate transaction, and read-side progress uses short consistent transactions. Public bundle compatibility is unchanged because context-free `FeatureBundle` parsing remains untouched.

The frozen production diff does not touch network code, runtime data, scoring/pool implementations, whole-job heartbeat coverage, legacy absolute snapshot containment, or the deferred plan-table-name typos. No new Critical/Important transaction, compatibility, migration, or performance issue was found.

## Strengths

- One transaction-aware validator is reused at both persistence and progress boundaries, avoiding divergent evidence rules.
- Canonical `FinancialFact.from_record()` reconstruction closes both missing-row and same-ID/corrupt-content attacks.
- Evidence checks are deliberately strict where raw-slot descriptors make content decidable and deliberately limited for derived formulas.
- Progress ordering makes the no-fallback and at-most-one-unknown properties explicit rather than incidental.
- Cleanup safety relies on both creation ownership and current-byte hash verification.

## Issues

### Critical

None.

### Important

None.

### Minor

None introduced by this fix boundary.

## Assessment

**All findings addressed.**

**APPROVED.** The original DB-backed evidence-integrity finding is closed: invented, missing, orphaned, mismatched, or canonically corrupted referenced facts cannot be persisted or counted ready, and the legitimate snapshot/fact/bundle/file/DB/progress path remains open while all formal and pool gates remain closed.

