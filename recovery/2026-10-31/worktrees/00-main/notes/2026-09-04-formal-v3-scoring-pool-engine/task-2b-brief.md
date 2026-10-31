# Task 2B — Verified frozen universe and industry assignments

This slice implements only context prerequisites for approved Task 2; no scores, pools, metric arithmetic, collection, or migrations. Activated after Task 2A review/commit. Base: 9d5c6d1a449a82209a9169b3c326252d2c1c81ab.

## Binding rules
The metric peer population is the complete frozen ordinary-A universe, including SH/SZ/BJ, at the existing 2026-08-31 15:00 Asia/Shanghai freeze. A valid assignment requires the same approved nine-role root and a separately verified Context fact, not caller strings. Missing assignments stay explicitly pending; they do not receive a guessed template/industry.

## Frozen universe getter
Add StateStore.get_verified_formal_frozen_universe(frozen_input_hash) -> FormalFrozenUniverseInput | None. In one existing read transaction, fetch the exact header and reuse _formal_universe_from_connection. This already validates all three source receipts/raw files/producer lineage and complete member/status/hash graph; do not duplicate its SQL or weaken it. The returned structural value is not itself an independently mintable authentication token. Preserve legacy header getter and CN-vs-UTC bytes/hashes exactly. The new context factory must call this genuine repository path from an exact StateStore, not accept a caller-supplied universe.

## Signed industry contract
A new formal_metric_context.py parses bundle.blob("industry") only after an exact verified bundle's official gate and the exact sealed FormalScoringRegistry.require_official(bundle).
Exact keys:
- registry_role="industry"
- schema_version="formal-industry-registry-v1"
- purpose="official" (agrees with official root; synthetic tests author their own official-wire graph)
- classification_system="SW2021"
- source_version: trimmed nonempty string
- effective_date: canonical ISO date not after the freeze's CN date
- context_scope_key: trimmed nonempty string
- memberships: nonempty array of exact {security_id,template_id,primary_industry,secondary_industry}
- mapping_sha256

Memberships are canonical security-ID sorted and unique; exact SH/SZ/BJ IDs, one of the five same-root scoring templates, nonempty primary/secondary strings. mapping_sha256 is SHA256 of the compact sorted canonical UTF-8 JSON object with exactly classification_system/source_version/effective_date/memberships. Recompute it. Do not self-reference the root/hash in that document. The signed child may contain securities outside the selected universe (a classification snapshot can be broader), but those never become A-share peers. An absent in-universe membership is pending, not an invented classification. Extra/ambiguous/duplicate fields or template substitutions fail closed.

## Batch Context prerequisite
Existing _candidates calls a StateStore list that parses the entire Context table and replays the matching root/kind/scope before filtering security. Calling get_verified once per stock is O(N²). Add a narrow FormalContextRepository.get_verified_many(kind, scope_key, security_ids, as_of_utc, registry_manifest_hash) with an exact sorted unique finite tuple of canonical security IDs. Take one before and one after verified candidate snapshot for the scope, group by requested security, retain the same timestamp/leading-version/tie/source validation as single get_verified, and return an immutable detached mapping of every requested ID to FormalContextFact or None (None means actual absence only). Invalid signatures, receipts, raw data, ties or races must still raise. Preserve single get_verified behavior; no DDL changes. This eliminates repeated full-table scans, not every per-source verification cost. No arbitrary source/SQL hooks or mock bypasses.

## Authenticated API (names approved)
FormalMetricContextRepository(state_store, context_repository, *, registry_signature_verifier):
- exact StateStore and exact FormalContextRepository, same backing StateStore and verifier; no caller getter, fabricated raw member, or verified flag.
- load_universe(frozen_input_hash, *, scoring_registry) -> VerifiedMetricUniverse or None. Reverify persisted graph; load exact same root, validate scoring and industry registry; compare the instant to fixed freeze while keeping original universe bytes; mint closure-private immutable proof with whole sorted universe membership, source snapshot/receipt/root/frozen/industry identity and complete population hash.
- resolve_industries(universe_proof) -> VerifiedMetricIndustryBatch. Require genuine same-repository universe proof. Resolve the entire universe's sorted IDs through exact get_verified_many for industry_snapshot, signed scope, canonical UTC freeze and the same root. Compare every Context value field to signed membership/meta: classification, primary, secondary, source_version, effective_date, mapping_sha256. Bind each successful assignment to context fact ID/canonical hash, security/template/industry, root and universe hash. The batch contains exactly one successful assignment or explicit pending entry per frozen member; a caller cannot supply a subset or arbitrary industry strings.
- Only absent signed membership, actual None Context result, or an authentic fact with mismatching membership/meta becomes a specific pending entry. Invalid signature/receipt/raw/leading tie/correction race must propagate as a batch failure, not become missing. Do not catch generic ValueError or classify by message text. A forged proof, invalid universe or global registry is always fatal to the batch.
- Proof classes must be non-publicly-constructible and closure-sealed, deeply immutable/detached; copies/forges/low-level mutation fail. No public mint helper. Public canonical bytes/hashes/membership access allow later complete-cohort validation.
- Mandatory recheck_batch(universe_proof, industry_batch): reverify frozen graph/signature graph once, then get_verified_many once for the complete population and compare all selected canonical facts AND absence markers, signed mapping and universe identity. Any change fails the whole batch. This is the later metric factory's mandatory final snapshot closure check after reading features. Never re-read the full N-member graph for each member. Cover a correction to A while B's features are being processed, not only mutations inside one Context call.
- This slice authenticates captured evidence; it does not grant indefinite latest-state validity or publish rights.
- Recheck the concrete trust path at entry and exit: actual StateStore, Context repository, embedded snapshot repository/store and verifiers, including class methods/descriptors and instance overrides on consumed read/validation paths. An exact but uninitialized/copied repository, replaced reader, or cached raw-source replay must not mint proof. Keep this narrowly bound to consumed dependencies rather than creating a generalized security framework. Earlier 2A fixed a demonstrated cached FormalSnapshotStore reader/validator substitution; preserve that boundary here.

## Tests and files
Allowed:
- ashare_pipeline/formal_metric_context.py (new focused contract/repository/proofs)
- ashare_pipeline/state_store.py (one narrow getter and review-round-1 constructor identity registration; no DDL change)
- ashare_pipeline/formal_snapshot_repository.py and ashare_pipeline/formal_snapshot_store.py (review-round-1 only: narrow authentic-construction bookkeeping; preserve normal public initialization/read semantics)
- ashare_pipeline/formal_repository_identity.py if needed: one focused closure-private constructor identity helper shared by the three underlying dependencies; no general security framework or public mint override
- ashare_pipeline/formal_context_repository.py (narrow batch getter with original validation semantics)
- tests/test_formal_metric_context.py
- tests/test_formal_context_repository.py (batch equivalence, absence-vs-corruption and correction coverage)
- tests/formal_metric_fixtures.py if a shared real combined-graph helper is necessary
- tests/test_state_store.py only optional parameters on existing task_backed_frozen_universe helper, preserving all defaults. Do not copy/import a TestCase subclass with inherited test methods.
- The helper may additionally accept optional exchange_rows (or equivalent canonical member input) for same-market multi-member fixtures and later real 20+ cohorts. The identical rows must feed both actual raw JSON and FormalUniverseSourceDocument, retaining the same real producer/receipt chain per exchange. Preserve the original three-member default; do not create financial/cohort functionality in this slice.
- tests/test_formal_scoring_registry.py only a narrowly justified reusable graph-helper parameter if unavoidable; prefer new helper.

Use one actual temporary StateStore and raw store + one complete signed nine-role graph for universe, scoring and industry Context. Existing helper root "7"*64 and source placeholder "8"*64 must be parameterized to actual signed root/source hash. Never authorize a mock repository or fabricate a member/proof in success tests. Real source producer/receipt lineage, raw hashes, Context normalization and signed child bindings remain exercised.
TDD coverage: valid SH/SZ/BJ assignments; canonical ordering/digest; legacy header getter unchanged; missing any exchange/member/status/receipt/raw fails; wrong root/template/context field/digest/version/future effective date fails; absent mapping/Context explicit pending; forged/copied/mutated capability fails; late capture with verified prefreeze source accepted; local correction race rejected; extra out-of-universe mapping cannot mint a peer. Parent runs appropriate existing StateStore universe/Context regressions after stable code.

Workdir D:/Projects/AShareQiheng/.worktrees/formal-v3-implementation; Python D:/Projects/AShareQiheng/.venv/Scripts/python.exe.
apply_patch only for edits, no network, no Git writes or nested agents. Preserve all data/SQLite/progress and unrelated tmpj4zv9_fq/. Full RED/GREEN/API report to task-2b-report.md in this SDD directory; parent owns progress and commit after review. Final <=15 lines status, tests, concerns, report path.

## Execution rulings
- Batch security_ids must be a nonempty sorted unique exact tuple of canonical ordinary-A security IDs. Reject trading_calendar without its exchange selector and invalid kinds/identities explicitly, never report them as actual absence.
- No repeated broad suites during iteration: run focused RED/GREEN tests, then freeze files and report; parent runs the affected existing Context/universe/StateStore regressions. Previous unchanged Context+universe baseline: 54 tests / 386.543s / OK. Use verbose output for long test commands.
- Run TDD and read its writing-good-tests reference. Real database/raw/producer/signature integration is required; mocks cannot establish provenance. Report any unresolved architectural or fixture issue promptly with a concrete proposed smallest adapter rather than broad file crawling.
