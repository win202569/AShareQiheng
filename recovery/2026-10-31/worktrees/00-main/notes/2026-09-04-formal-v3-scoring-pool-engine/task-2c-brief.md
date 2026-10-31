# Task 2C — Complete-cohort metric engine

Activated after 2A and 2B passed independent review and code-only commits. Base: dbf075dd5764c4dcd0ed3cba5074cc6ec330f49a. Their final APIs/reports and integration rulings below bind this slice. Original approved Task 2 follows the integration rulings.

## Binding global constraints
- Official nonzero scores require one complete, hash-pinned production VerifiedRegistryBundle whose root FormalRegistryManifest binds source, mapping, feature, scoring, industry, cyclic, redline, status, and event registry hashes. Reject an unsigned, incomplete, test-only, or child-hash-mismatched bundle before calculating an official run.
- The formal universe is SH/SZ/BJ A-share ordinary shares. A BJ member follows identical peer, redline, and pool rules and must never be dropped by an SH/SZ-only helper.
- Metric peer eligibility is metric-level. It depends only on frozen universe membership, valid template/industry classification, and every verified required fact for that metric; it does not depend on formal_scored, pool eligibility, or a completed seven-dimension score.
- Use exactly the V3 templates: general_nonfinancial, bank, broker, insurance, and real_estate. Do not revive V2 resource, utility, or research-growth templates.
- No missing slot receives zero, a peer median, an estimate, or redistributed weight. A missing required formal slot produces pending_evidence rather than a partial score.
- No code path accepts a user-supplied final score, pool rank, pool label, or override. Registry changes and source corrections produce a new input hash/release, not edits to a prior output.
- The engine is offline and deterministic after verified inputs are stored. Unit tests use fixtures and do not contact official or third-party websites.
- Preserve all data and legacy tables. Do not stage data, SQLite, WAL/SHM, or data/status/pipeline_status.json in code commits.

## Integration rulings
- Formal eligibility cannot come from public dataclass fields or a verified=True flag. Genuine MetricInput, complete MetricInputBatch, MetricPeerContext and MetricScore proof paths must retain closure-private provenance, immutable values and root/freeze/universe/definition/component hashes.
- Formal batch factory consumes exact feature/context repositories plus same-root approved scoring registry and frozen_input_hash; it enumerates the WHOLE stored ordinary-A universe itself. It does not accept caller-selected security subsets, raw values, industry/template strings, score/pool/veto overrides. Every member has an eligible or explicit pending input for each requested metric; an incomplete company or veto status does not exclude a complete metric.
- Resolve all industries in one authenticated 2B batch. Project the union of required signed V6 keys once per security for requested metric IDs (or all metrics), then use each metric's own value/status/dependencies. Other missing metric slots must not poison a valid slot. Preserve the full selected projection hash and appropriate per-metric refs.
- Task 2A concrete projection API: FormalFeatureRepository.select_current_verified_metric_features(..., required_feature_keys=sorted_unique_tuple) returns VerifiedMetricFeatureProjection or None. Always require_verified() before consuming it. Match slots/values by signed slot ID; projection.blockers is only an aggregate, not a blanket eligibility flag. Projection identity includes input_hash/bundle_hash/fact_snapshot_hash/issue_snapshot_hash/algorithm_version and provider batch_id; final rechecks require stable logical provider snapshot identities, not per-call random batch labels. See task-2a-report.md for full wire and explicit V6 float limitations.
- Convert finite verified V6 values via Decimal(str(value)); no recovered precision claims and no changed V6 formulas. Signed direction and units come from the exact metric definition. Do not reject valid negative or zero numerators/raw values. Reject invalid denominator/unit/absence using projection reasons.
- Mandatory final closure: recheck frozen root/whole universe/industry batch including absence markers, and current selected feature proof hashes (also unpersisted/absent markers) before minting the complete input batch. A correction affecting an earlier-read member while reading a later member fails/retries the batch; no partial success with mixed generations. Missing evidence is explicit pending, while authenticity/corruption/signature/receipt/race failures propagate.
- build_metric_peer_context requires metric_id and a focal security_id plus the genuine complete batch (the illustrative plan omits its focal ID). Exclude only metric-invalid rows; use same template and secondary if eligible N>=20, otherwise same template and primary if N>=20, else reason peer_count_below_20. Focal invalid input gets its own pending reason, never a score using other peers. Exactly20 qualifies;19 does not; BJ is ordinary eligible member.
- Do not allow a caller to shrink or substitute a genuine batch's peer rows/direction. Bind every formal score to the exact selected cohort IDs/count/scope and definitions. Sorted unique security IDs make output deterministic; IDs never break numerical rank ties.
- Separate the small-N arithmetic helper from formal scoring: a pure percentile_rank function may accept raw finite Decimal test values and return average rank/percentile for N=2/4 examples; it does NOT mint an official MetricScore or bypass the formal N>=20 cohort gate. Official score_metric_percentile consumes genuine batch/context proof. Reject N=0, nonfinite values, duplicate/security identity drift or focal-value substitution. Do not expose final-score overrides.
- Use a fixed local Decimal context (document precision/rounding) so process-level decimal context changes cannot alter outputs; persisted comparisons are unquantized, display formatting separate. Follow midpoint average-rank formula and lower-direction reversal exactly.
- Decimal ruling: use an explicitly constructed local context with precision 50 and ROUND_HALF_EVEN, independent of mutable getcontext()/DefaultContext, including exponent limits and traps. Do not claim recurring division is mathematically exact; preserve the full deterministic precision without display rounding. Decimal(str(verified V6 value)) preserves only V6's already available precision. Later score modules reuse this arithmetic contract; do not mutate global Decimal state.
- Support efficient batch scoring/group reuse (do not re-read repositories or full-sort an identical cohort per output stock); immutable shared cohort tuples/caches are scoped to one input batch, not mutable global state.

## Actual 2B integration surface
- FormalMetricContextRepository consumes the actual StateStore/Context repository/verifier. Its load_universe(frozen_input_hash, *, scoring_registry) returns VerifiedMetricUniverse or None; resolve_industries(universe_proof) returns VerifiedMetricIndustryBatch for the complete population; recheck_batch(universe_proof, industry_batch) performs the mandatory final full-population closure.
- Universe and industry proofs expose require_verified(), canonical_bytes(), detached to_dict(), and immutable fields. Verify same frozen root/population/industry/scoring/feature identities. Final 2B report defines canonical payload names; do not reconstruct proof objects from their structural payloads.
- Approved constructor: FormalMetricInputRepository(feature_repository, context_repository, *, registry_signature_verifier), consuming the exact FormalFeatureRepository and underlying exact FormalContextRepository. Require feature_repository._store is context_repository._state_store and the same verifier, and internally construct FormalMetricContextRepository from those actual dependencies. The existing metric-context repository keeps dependencies closure-private, so do not accept an opaque prebuilt wrapper and guess its store. Retain and recheck dependency identities. Calls must remain through genuine, unchanged repository paths; a copied wrapper or replaced reader cannot replay old proof material to bypass the final closure.
- Approved batch entry: .build_batch(frozen_input_hash, *, scoring_registry, metric_ids=None). Optional metric selection must be a nonempty canonical sorted unique tuple of known registered IDs; omitted selects all applicable metrics. This is NOT a security subset selector. Missing frozen universe may return None; invalid/corrupt evidence raises. Document exact result/proof APIs for Task 3.
- Metric identity ruling: every public engine selector and result uses the canonical qualified ID `<dimension>.<registered metric_id>` for ALL metrics (for example M.return_persistence and CA.return_persistence). Bare IDs are rejected even when currently unambiguous. The signed registry reuses some leaf IDs across dimensions; preserve its original dimension/leaf fields and canonical bytes, binding both in the definition hash. None selects all qualified applicable slots. This changes no formula, metric weight or signed feature key.
- Parent permits one narrow extension to tests/formal_metric_fixtures.py (or a separate tests/formal_metric_feature_fixtures.py if clearer) for real same-store member-specific financial sources described below. Keep the existing three-member fixture defaults unchanged and avoid production feature/provider changes unless a concrete integration gap is escalated first.

## Additive absence-state prerequisite
Read formal_feature_repository.py's current select path around the early stored-is-None return. Two successive bare None results do not prove the same current inputs: facts, issues or logical provider batch could change while both expected bundles remain unpersisted. Do not mint a whole-population batch from that ambiguous marker.

Parent approves a narrow additive endpoint in the same repository, select_current_verified_metric_feature_state, with the same arguments as select_current_verified_metric_features. It returns either the existing unchanged VerifiedMetricFeatureProjection or a new closure-sealed VerifiedMetricFeatureAbsence. Preserve the old projection-or-None method, present projection canonical bytes/hashes, strict old complete-feature APIs, V6 formulas and schema. Share the genuine existing read/validation path instead of duplicating a second provider/source validator in the metric engine.

Absence is a proof only that the exact expected CURRENT feature receipt is unpersisted for authenticated captured inputs. It is not numeric evidence or indefinite absence. Bind request security/cutoff/template/root, signed feature hash, required keys, expected input/bundle identity, complete canonical fact/issue snapshot hashes and stable logical provider batch identity, explicit absence status, and a deterministic absence hash. No public constructor/mint/from_dict/verified flag. Reject copied/mutated proofs and replaced read/validation dependencies exactly as for present projection. Recheck actual source facts, provider snapshot, registry graph and current receipt absence before minting; do not reinterpret corruption or provider failure as absence.

The engine compares these genuine present/absence markers on the final per-member pass and calls the mandatory final 2B batch closure. Any present-to-absent, absent-to-present, or changed-absent-to-different-absent transition fails the batch. The marker must include issue and provider identity changes even when no numeric metric becomes eligible. Stable unchanged absent inputs must remain reproducible. Preserve metric-specific missing/blocked slots when a present bundle exists.

Additional approved identity adapter: expose module-private _require_authentic_metric_feature_repository directly bound to the existing Feature repository dependencies closure. It is read-only validation, not mint authority. The engine calls it during construction and final dependency checks, including batches with no valid template/industry where no feature selection endpoint is invoked. This prevents copied/fabricated Feature repositories from qualifying through an all-pending shortcut. Preserve old public APIs and proof bytes; cover that exact scenario RED/GREEN.

TDD must demonstrate changed still-unpersisted inputs are missed by the old bare-None comparison, then covered by the additive state API and a cross-member batch correction regression. Also cover absent receipt becoming present, invalid raw/source/signature on absence, immutable proof rejection, old method returning None unchanged, and byte-identical existing present projection.

## Review-round-1 consistency ruling

The original two-pass closure is insufficient: mutation of an earlier member while reading a later member during the final pass can escape. Add a genuine owned provider publication epoch and a same-connection SQLite epoch barrier, not a third unguarded sweep. A closure-owned exact provider stores detached immutable complete records (or issues/logical identities with real StateStore facts), increments its private whole-provider epoch on every publication, and exposes no mutable records. No implicit empty completeness. Generic existing providers remain supported by old APIs but cannot mint new complete metric batches, including all-pending batches.

Capture provider epoch and PRAGMA data_version on one persistent same-store observer connection before any universe/context/feature reads. Reads continue through existing authenticated repository paths. At finalization acquire provider publication exclusion plus a short BEGIN IMMEDIATE transaction on that same observer, compare both original epochs, and mint only inside the guards; rollback/close on every path. The observer must never perform data writes. Any database commit conservatively invalidates the attempt, including unrelated progress writes; retry policy belongs to a later bounded runner, not an infinite loop here. Do not hold the database writer lock throughout the potentially long whole-A-share read pass. SQLite busy/lock errors fail closed with bounded timeout.

Sources checked by parent: https://www.sqlite.org/pragma.html#pragma_data_version (compare only the same connection; detects other-connection commits), https://www.sqlite.org/lang_transaction.html (BEGIN IMMEDIATE reserves writer access). Test actual SQLite behavior and writer-fence cleanup, not a mock stable flag. Logical source corrections change authenticated database receipts; immutable content-addressed raw/feature files remain reauthenticated by existing readers. This is a logical input-generation fence, not a promise of a globally atomic filesystem snapshot against arbitrary OS file tampering; no native file-lock subsystem in this slice.

Allow one focused new owned-provider/guard production module and one focused test module in addition to the original six files if needed. No StateStore/schema edits without a separate concrete prerequisite. Original implementer must also reject non-exact-str metric/security selectors before lookup and serialize canonical focal-row identity, and remove the strong proof-table context/batch ownership cycle while preserving same-batch checks/cache tuple reuse. Cover all three exact review reproductions RED/GREEN; preserve the staged original review baseline until scoped re-review.

Finalization refinement: expensive encoding, freezing, indexes and object preparation must occur outside the writer fence. Prepared rows and their batch share a closure-private unpublished capability and are unusable by every verifier/consumer until the final constant-work guarded publication; no public verified flag or mint exists. Revoke publication on every failed finalization path, including errors after the callback. In this ruling, minting means publishing usable authenticated proofs, not allocating unverified private preparation objects. Test that another connection can acquire writer reservation while canonical preparation executes, and that failed finalization leaves prepared capabilities unusable. Cleanup must reset provider finalization state even if rollback raises. The new 1-second busy timeout bounds final lock acquisition, not total execution; inherited StateStore connection setup may wait 5 seconds.

## Scope
Create ashare_pipeline/formal_metric_engine.py and tests/test_formal_metric_engine.py. Add only the absence-state prerequisite to ashare_pipeline/formal_feature_repository.py and focused tests in tests/test_formal_metric_features.py. Reuse the real combined signed persistence fixture from 2B; the financial-source helper extension above is allowed. Do not modify legacy scoring, collection, policy, pools, V7, production config, old feature contracts, or completed 2B modules. No network, no user data, no git writes or nested agents. Parent reviews and commits. Use apply_patch only. Preserve unrelated tmpj4zv9_fq/ and all SDD artifacts.

Read and follow test-driven-development and its writing-good-tests reference. Run focused RED/GREEN tests during iteration; do not repeatedly run the entire repository or the slow calendar suites. Freeze source and write full API, canonical payload/hash, real fixture, exact RED/GREEN command/output and concerns report to task-2c-report.md beside this brief. Parent runs affected legacy regressions and independent review. Final message <=15 lines: status, tests, changed files/concerns, report path. Workdir D:/Projects/AShareQiheng/.worktrees/formal-v3-implementation; Python D:/Projects/AShareQiheng/.venv/Scripts/python.exe.

TDD cases must include hand-derived ties/reversal, 19/20 fallback thresholds, template separation, complete metric on unscored/pool-vetoed stock, true all-universe enumeration vs subset/replacement, root/security/metric/unit/definition substitution, proof copying/mutation, missing markers, and cross-member correction closure. Use pure helper tests for arithmetic and real verified fixtures for formal provenance; never accept fake repository subclasses as official proof.

## Original Task 2

## Real-fixture integration notes (read-only preflight)
- Reuse 2B's combined signed persistence helper and optional exchange_rows; exactly three exchange producer/receipt chains may contain many ordinary members. Never use tests/test_formal_universe.py extraction-only fabricated snapshot references for success proofs.
- tests/test_formal_scoring_registry.py signed_graph(mutate=...) authors metric/source/industry fields before signing. Source/mapping document changes also require updating feature metadata's source/mapping hashes. Existing context=True only configures SZ security-state; actual industry descriptors and all exchanges come from 2B's helper.
- Do not invoke test_formal_feature_repository setup per member (it installs twelve periods and a separate graph). Do not reuse tests/test_state_store.py install_fact unchanged: it replaces self.store without the shared verifier and its written_formal_snapshot remains SZ-specific even when fact fields are overridden.
- Build a narrow test-only financial-source helper against the SAME shared store, signature verifier and root. Follow existing leased-source write/producer-receipt pattern, with unique task natural keys and member-specific request/declared ID/exchange; derive all fact/lineage/raw hashes from the actual stored source, not default placeholder references.
- For eligible metric-local tests, one FY2025 raw statement per member with independently controlled selected metric leaves can suffice. Sign the appropriate actual AST before sealing the root, persist each unchanged full bundle, and leave unrelated slots/history pending. Stable logical per-security batch IDs are required on recheck.
- One complete 20+ population and several independently controlled metric eligibility masks can cover 19/20, fallback and template separation without repeatedly building all sources. Include BJ in a qualifying group and an other-template group with identical industry labels. Reuse immutable results within that batch; isolate corruption/correction tests in fresh fixtures, never copy live databases/raw trees with embedded paths.
- Fixture reuse must not import/inherit a TestCase subclass into the new module's discovery namespace; use ordinary helper objects or module-qualified borrowed methods.

### Task 2: Metric Eligibility, Peer Cohorts, and Percentile Scores

**Files:**
- Create: ashare_pipeline/formal_metric_engine.py
- Create: tests/test_formal_metric_engine.py

**Interfaces:**
- Produces MetricInput, MetricPeerContext, MetricScore, metric_peer_eligible, build_metric_peer_context, and score_metric_percentile.
- Consumes frozen FormalUniverseMember, frozen industry mapping, FormalFeatureBundle, TemplateDefinition, and MetricDefinition.
- Returns an explicit pending reason for no valid template, no valid industry, missing verified fact, invalid denominator, unsupported unit, or a peer cohort below twenty; it never silently builds a smaller cohort.

- [ ] **Step 1: Write the failing peer and rank tests**

~~~python
class FormalMetricEngineTests(unittest.TestCase):
    def test_tied_higher_metric_uses_average_rank_midpoint_formula(self):
        rows = [
            metric_input("SZ000001", Decimal("1")),
            metric_input("BJ430001", Decimal("2")),
            metric_input("SH600001", Decimal("2")),
            metric_input("SH600002", Decimal("4")),
        ]
        score = score_metric_percentile(rows[1], rows, direction="higher")
        self.assertEqual(score.average_rank, Decimal("2.5"))
        self.assertEqual(score.percentile, Decimal("50.0"))
        self.assertEqual(score.peer_count, 4)

    def test_lower_is_better_reverses_percentile_without_reversing_tie_rank(self):
        rows = [metric_input("SZ000001", Decimal("1")), metric_input("SZ000002", Decimal("3"))]
        self.assertEqual(
            score_metric_percentile(rows[0], rows, direction="lower").percentile,
            Decimal("75.0"),
        )

    def test_secondary_industry_shortfall_falls_back_then_fails_closed_below_twenty(self):
        context = build_metric_peer_context(metric_id="m", inputs=nineteen_secondary_plus_twenty_primary())
        self.assertEqual(context.scope, "template_primary_industry")
        self.assertEqual(context.peer_count, 20)
        self.assertEqual(build_metric_peer_context(metric_id="m", inputs=only_nineteen()).reason, "peer_count_below_20")

    def test_metric_peer_eligible_does_not_require_formal_scored(self):
        candidate = unscored_but_verified_metric_input("BJ430001")
        self.assertTrue(metric_peer_eligible(candidate))
~~~

- [ ] **Step 2: Run metric tests and verify RED**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m unittest tests.test_formal_metric_engine -v
~~~

Expected: FAIL because ashare_pipeline.formal_metric_engine does not exist.

- [ ] **Step 3: Implement deterministic cohorts and ranks**

Use immutable input and output records:

~~~python
@dataclass(frozen=True)
class MetricInput:
    security_id: str
    template_id: str
    secondary_industry: str | None
    primary_industry: str | None
    metric_id: str
    raw_value: Decimal | None
    verified_feature_refs: tuple[str, ...]
    invalid_reason: str | None

@dataclass(frozen=True)
class MetricPeerContext:
    metric_id: str
    security_id: str
    scope: Literal["template_secondary_industry", "template_primary_industry"] | None
    peer_security_ids: tuple[str, ...]
    peer_count: int
    reason: str | None

@dataclass(frozen=True)
class MetricScore:
    metric_id: str
    security_id: str
    raw_value: Decimal
    percentile: Decimal
    average_rank: Decimal
    peer_context: MetricPeerContext
~~~

metric_peer_eligible returns true only when the universe member is in scope, has a valid registry template plus frozen primary and secondary industry assignments, has each required feature reference verified and visible at freeze, and has a valid metric-specific denominator. It does not inspect complete seven-dimension status, veto flags, score rows, or pool rows.

build_metric_peer_context first filters by template plus secondary industry and metric_peer_eligible. If N is at least twenty, return that group. Otherwise filter by template plus primary industry; N must then be at least twenty. Return sorted security IDs and a reason instead of fabricating a score for a short cohort.

For a positive direction, calculate:

~~~text
percentile = 100 × (average_rank - 0.5) / N
~~~

Use average ranks for ties, exact Decimal arithmetic, and security ID only as a deterministic output-order tie breaker, never as a rank tie breaker. For lower-is-better metrics, return one hundred minus the positive-direction percentile. Preserve raw negative and zero values where the metric definition permits them; reject only the definition's invalid denominator or non-comparable-unit cases.

- [ ] **Step 4: Run focused peer and formal-universe tests**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m unittest tests.test_formal_metric_engine tests.test_formal_universe -v
~~~

Expected: PASS, including BJ fixtures and all peer fallback cases.

- [ ] **Step 5: Commit metric scoring**

~~~powershell
git add -- ashare_pipeline/formal_metric_engine.py tests/test_formal_metric_engine.py
git commit -m "feat: add formal peer percentile engine"
~~~
