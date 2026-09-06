# SDD ledger — plan: docs/superpowers/plans/2026-09-04-formal-v3-financial-feature-pipeline.md

V6 Task 1: contract preflight complete — two independent read-only audits confirm V5 evidence/universe foundation at `cc4227e` is the required base. Binding brief `task-1-brief.md` freezes fail-closed source/manifest wire formats, V5 reuse, canonical date-only day-anchor conversion, adapter-level calendar self-consistency, and no production defaults.

V6 Task 1: deferred-boundary ruling — exact task prerequisite-edge comparison belongs to the Task 6 typed worker payload, because the Task 1 public adapter has no task-edge input. Bootstrap-calendar status is returned as signed config/document provenance only; no incompatible V5 raw-manifest metadata field is invented. Production signed endpoints/parsers/registries remain absent and must be blocked rather than inferred.

V6 Task 1: author submitted `aaf750d feat: add injected formal official source adapter` after RED evidence, focused 24/24 tests, prior four-module 49/49 regression, compilation, clean scope, and diff checks. Mid-flight audit found the otherwise impossible root/child full-hash fixed point; the binding brief now requires a separately signed canonical child-binding envelope (`child_sha256`, `registry_manifest_hash`, `registry_role`) so the root retains exact child hashes while each child has an independently signed reverse declaration. The brief also requires the adapter's source registry hash to equal the root source member and makes bootstrap calendar unscoped/global only. Independent post-submit review pending; no data/state artifacts staged.

V6 Task 1: independent post-submit review of `aaf750d` failed with three Important findings despite independent four-module regression 50/50 green: direct dataclass construction bypassed the formal signed-release gate; raw URL controls/CRLF were accepted in endpoint/response/replay paths; and non-global universe listings were rejected only after transport/parser work. It also found two Minor fail-closed gaps (dynamic query/header keys and non-bootstrap unbound calendar config accepted at registry load). Author remediation is in progress; a fresh re-review is mandatory after a code-only fix commit.

V6 Task 1: author remediation submitted `81aaa87 fix: harden formal registry provenance boundary`, still only the four Task 1 files. It fixes all original review findings plus subsequent independently reproduced token-leak and post-verification mutation bypasses: formal manifest/bundle provenance is now private weak-reference identity plus sealed immutable field fingerprints, while untrusted repository blob envelopes remain raw inputs reverified by the loader. The fix adds zero-network preflight, URL/template control rejection, and calendar/config validation regressions. Author reports focused 31/31 and four-module 57/57 green, compilation and diff checks clean. Fresh re-review pending; no data/state artifacts staged.

V6 Task 1: fresh re-review of `81aaa87` failed with two Important provenance findings despite independent 57/57 regression: `SignedSourceRegistry` itself was still forgeable/mutable after verification, allowing unsigned endpoint/template changes to reach transport; and module-level manifest/bundle construction/registration helpers could mint verified-official capability directly. All other reviewed source, outer-binding, URL, template, calendar, and replay guards passed. Remediation must encapsulate factories/registries in unexported closure state and seal the signed source registry/configs before the adapter accepts it; another fresh re-review is required.

V6 Task 1: third author remediation submitted `32cbf16 fix: seal formal registry construction`, again only the four Task 1 files. It moves source-registry trust records and trusted manifest/bundle factories into executed-and-deleted type-factory closures, seals raw registry fields plus ordered complete config fingerprints, and has the adapter revalidate registry sealing at construction, fetch preflight, and replay selection. New RED proofs cover forged/mutated source config and previously visible module helper exposure. Author reports focused 33/33 and independent four-module 59/59 green, compilation and diff checks clean. A final fresh re-review must attack the old helper imports, object construction/mutation, and source registry mutation paths before acceptance.

V6 Task 1: final fresh re-review of `32cbf16` failed with one Important TOCTOU defect. A sealed source registry was checked, then the same mutable config object crossed injected parser lookup/parse callbacks; a parser could mutate endpoint before transport or mapping version before verified fetch construction. All earlier direct construction, module-helper exposure, raw blob revalidation, URL/template, calendar, replay, and scope checks passed. A locally reproduced adapter root/freeze field mutation was also sent to the author for defense-in-depth. Remediation must use operation-local signed config snapshots and isolated parser copies across every callback boundary, plus sealed adapter trust anchors; final fresh re-review remains mandatory.

V6 Task 1: fourth author remediation submitted `837d3aa fix: isolate formal source trust snapshots`, changing only `formal_sources.py` and its tests. Each operation now reconstructs a local config from closure-sealed canonical registry data, passes parsers deep-isolated working copies, and uses the local operation plan after callbacks; adapter registry/root/source/freeze/policy anchors are closure-sealed too. It also closes a discovered seal-record leakage/re-anchoring path. Author reports focused 41/41 and four-module 67/67 green, compilation/diff checks clean. Final fresh attack-oriented review is required before Task 1 acceptance.

V6 Task 1: fresh attack-oriented review of `837d3aa` failed with one Blocker and one Important. The manifest/bundle public methods dynamically dispatched through instance `_require_verified`, so ordinary `object.__setattr__` could replace the guard and mint an official gate; and a parser holding the injected transport response could mutate it after parsing while the adapter later re-read it to build a still-verified fetch. Review also found a Minor untrusted child approval-id type check gap. Remediation must use closure-local direct guards (and slotted trusted types), snapshot the complete transport response before every callback, and strictly validate official child approval text. All other source snapshot, config mutation, URL, replay, and scope paths passed.

V6 Task 1: fifth author remediation submitted `6c47721 fix: seal formal registry and transport response`, again only the four Task 1 files. Trusted manifest/bundle types are slotted with weakref support and public gates invoke closure-local seal checks directly; transport responses are strict MappingProxy-backed operation-local snapshots before parser callbacks; official child approval text is exact type/trim validated. Author reports focused 44/44 and four-module 70/70 green, compilation/diff checks clean. Fresh re-review is still required before acceptance.

V6 Task 1: subsequent gate review found a deterministic Blocker in loader blob handling: `_read_blob` re-read one mutable untrusted envelope across signature/hash/parse/delivery, so a strict-verifier callback could swap canonical bytes after signature verification and get unsigned bytes into a bundle. It also found an Important shallow-freeze issue for verified parsed-document row mappings, plus minor exact-type gaps for request exchange and publication precision. The reviewer’s final aggregation was platform-interrupted, but its individual reproduced reports are preserved and sufficient for remediation. Next patch must snapshot raw root/child envelopes at loader entry, deep-freeze verified parsed rows, and exact-type these security enums; a fresh post-fix review is mandatory.

V6 Task 1: sixth author remediation submitted `1a087a1 fix: snapshot formal source integrity inputs`, only the four Task 1 files. Root/child repository envelopes are now exact immutable snapshots at read entry; verified parser metadata/rows are copied and recursively frozen; request exchange, publication precision, calendar selector enums, and HTTP method use exact string guards. Author reports focused 50/50 and four-module 76/76 green, compilation/diff checks clean. A new independent review must replay verifier/blob mutation and post-verification row mutation before acceptance.

V6 Task 1: integrity review of `1a087a1` needs two further fixes. Replay copied `OfficialSnapshotRef` fields without exact primitive/enum/hash validation, allowing custom equality objects to impersonate precision, status, request fingerprint, mapping version, and date-only provenance fields; and parser rows still accepted arbitrary leaf objects via `deepcopy`, whose custom implementation could return the original mutable object. The review independently confirmed root/child envelope snapshots, ordinary nested JSON-shaped rows, scope, and the 76/76 baseline passed. Remediation must validate/snapshot every trusted ref field before replay and whitelist-recursively freeze JSON-shaped parsed row values, rejecting unknown leaf types; a fresh re-review is mandatory.

V6 Task 1: seventh author remediation submitted `352223b fix: validate formal replay snapshots`, changing only `formal_sources.py` and its tests. Replay now snapshots and canonical-validates all 24 ref fields (including evidence relationship), while verified rows use a recursive JSON-value whitelist freezer that rejects unknown/self-copying keys and leaves. Author reports source-focused 36/36 and four-module 78/78 green, compilation/diff checks clean. Fresh independent review must verify replay field coverage and immutable parsed rows before acceptance.

V6 Task 1: ACCEPTED after fresh independent replay review PASS with no Blocker/Important/Minor. The reviewer independently exercised all 24 replay-ref fields with spoofed equality objects, ref mutation during replay, deep nested row mutation and JSON-value freezing, historical blob/config/adapter/response/guard TOCTOU cases, scope, and 78/78 four-module regression. Root independently reran the same 78 tests successfully and confirmed `git diff --check cc4227e..HEAD` plus clean worktree. Task 1 code commits are `aaf750d`, `81aaa87`, `32cbf16`, `837d3aa`, `6c47721`, `1a087a1`, and `352223b`; no data/state artifacts were staged.

V6 Task 2: contract preflight complete. The plan did not specify a safe parser-row value-field convention or a source/parser/version/exchange mapping selection key, so binding brief `task-2-brief.md` freezes a signed `item_value_v1` row contract and exact scoped bindings. It also assigns formal-snapshot/database membership and official-root approval to later Task 5/6, while Task 2 owns signed mapping structure, fact lineage/value validation, deterministic issues, and legacy isolation. Author implementation may begin only in the two new Task 2 files.

V6 Task 2: author submitted `97f6666 feat: add formal financial fact schema` with exactly the two permitted new files. RED evidence is recorded; author reports focused 15/15 and required formal-plus-legacy 88/88 green, compilation/diff checks clean, and no data/state artifacts staged. Independent review pending.

V6 Task 2: fresh independent review of `97f6666` failed SPEC/QUALITY despite focused 15/15, combined 88/88, clean diff, and clean worktree. Important: the strict-decimal regex used Unicode `\d`, accepting Arabic-Indic digits; and a malformed duplicate row with a recognizable mapped `ITEM` was recorded only as invalid shape while a valid duplicate still emitted a fact. Minor: custom equality could evade the signed-registry seal's tuple comparison (without changing canonical-byte reconstruction output), and `FormalFactIssue.details` used a mappingproxy with no canonical serialization boundary. Remediation is restricted to the same two Task 2 files and requires fresh independent re-review.

V6 Task 2: review remediation submitted as `914ca63 fix: harden formal financial fact validation`, still only `formal_financial_schema.py` and its test file. It replaces Unicode decimal matching with explicit ASCII digits; retains a safe recognizable `ITEM` on malformed rows so mapped duplicates block facts; strengthens the closure seal with exact primitive/identity fingerprints; adds detached JSON-native `FormalFactIssue.to_dict()`/canonical bytes; and sorts duplicate row indices in source order. Root recorded RED for reversed malformed/valid row order, then GREEN with focused 18/18, required combined 91/91, compilation, and clean diff checks. Fresh independent re-review is pending; no data/state artifacts were staged.

V6 Task 2: fresh re-review of `914ca63` failed only on one Important mutation-integrity defect. Replacing a sealed fact's normalized float value with numerically equal int via `object.__setattr__` bypassed Python's loose equality in both the seal and normalized-dict comparison; `to_dict()` then emitted an ID inconsistent with its serialized scientific fields. The review confirmed the four prior repairs, all other mapping/binding/lineage/numeric/legacy boundaries, 18/18 focused, 91/91 combined, and clean scope. Same-process reflection into closure cells is recorded as the accepted Task1-equivalent ordinary-threat-model limitation, not a Task2 blocker. Remediation remains restricted to the two Task2 files and needs a fresh final review.

V6 Task 3: read-only contract preflight complete. Before implementation, its brief must freeze root/feature-child external binding (no hash fixed point), exact signed registry and AST wires, sealed evidence/bundle serialization, canonical manifest headers, path derivation, and no-clobber/atomic storage semantics. Task3 stays limited to its four new files and must not implement formulas, SQLite/task integration, legacy changes, or scoring.

V6 Task 2: final mutation-seal remediation submitted as `89cf17b fix: seal formal fact serialization`, still only the two Task2 files. The fact record now uses exact field-kind fingerprints plus IEEE-754 bytes for float fields, so int/float equivalence and signed-zero changes cannot evade immutable serialization validation. Root recorded the reviewer reproduction as RED, then GREEN: the focused counterexample, formal 19/19, required combined 92/92, compilation, and diff checks all pass. A brand-new final independent reviewer is now auditing the complete `352223b..89cf17b` review package; no data/state artifacts were staged.

V6 Task 2: final independent review of `89cf17b` failed with two Important and one Minor. `FormalFinancialFact.from_dict` normalized noncanonical int/float/signed-zero wire values before validating the same ID; two recognizable but malformed duplicate mapped rows fell through to missing rather than duplicate conflict; and `FormalFactIssue` had no provenance seal so low-level replacement of valid-looking details/code still serialized. The review independently confirmed the registry ordinary-threat-model seal, prior decimal/row repairs, binding, lineage, raw hash, and legacy isolation. A plain JSON-native fact `to_dict` boundary will be added alongside the required fixes. Remediation remains only the two Task2 files; a fresh final review is mandatory.

V6 Task 2: canonical-record remediation submitted as `cb76672 fix: enforce canonical formal fact records`, again only the two Task2 files. It rejects type-/signed-zero-noncanonical fact wires before construction, returns detached JSON-native fact records, classifies every repeated recognizable mapped field (including all-malformed pairs) as a conflict while retaining legacy single-malformed missing behavior, and closure-seals deep-frozen issue objects before serialization. Root recorded three RED cases, then GREEN: formal 21/21, required combined 94/94, compilation, and diff checks pass. A new final reviewer is auditing the complete four-commit package; no data/state artifacts were staged.

V6 Task 2: fresh final review of `cb76672` failed on one Important parser-row boundary. A custom exact `Mapping` whose `items()` exposed a recognizable mapped `ITEM` then repeated a key made `_snapshot_row` return with `item=None`; paired with a valid row, it failed to enter invalid-match conflict handling and still emitted a fact. All other reviewed signed mapping, numeric, lineage, canonical fact/issue, and legacy boundaries passed. Remediation will preserve safely observed candidate items across malformed-row exits and add repeated ITEM/VALUE regressions, restricted to the two Task2 files; one further fresh review is mandatory.

V6 Task 2: streaming malformed-row remediation submitted as `b1c41bb fix: preserve malformed formal row identities`, again only `formal_financial_schema.py` and its test file. The row snapshot now streams finite mapping items and records only safe canonical `ITEM` candidates (including repeated occurrences) despite duplicate keys, later target fields, or iterator interruption; invalid extraction consumes those candidates occurrence-by-occurrence to block valid/malformed repeats while issue row indices remain sorted physical rows. Root recorded RED for duplicate ITEM/VALUE, late ITEM, interrupted stream, and in-row repeat cases, then GREEN: formal 24/24, required combined 97/97, compilation, and diff checks all pass. A separate post-fix adversarial audit found no fact-release or parser-object-retention path. One new fresh final review is mandatory; no data/state artifacts were staged.

V6 Task 2: independent review of `b1c41bb` found three further Important boundaries: tuple/list pair subclasses were not safely recognized as row pairs, public `select()` used loose equality on its six signed-binding query keys, and registry/created/identity/lineage hard failures could consume a parser row first. Remediation submitted as `9bc6fb7 fix: harden formal fact selection boundaries`, still only the two Task2 files. It reads tuple/list subtype storage only through intrinsic base accessors, exact-validates every public selection key, and separates document metadata from row snapshotting so snapshot/registry/binding/created/identity/parser/publication/bootstrap checks all occur before `items()` consumption. Root recorded all three RED paths and added hostile override plus row-consumption probes; formal 28/28 and required combined 101/101 are GREEN, with compilation/diff checks clean. A brand-new fresh final review is mandatory; no data/state artifacts were staged.

V6 Task 2: ACCEPTED after two fresh independent final reviews PASS at `9bc6fb7`, with no P0/P1/P2 findings. The reviewers separately exercised 67+ temporary adversarial probes for forged/mutated registry, exact query selection/equality spoofing, snapshot/document/binding/time/bootstrap hard failures before row consumption, custom Mapping streams, repeated/truncated/interrupted rows, pair subclasses with overridden methods, and parser-object retention. Root independently reran formal-plus-legacy 101/101, compiled both Task2 files, confirmed `git diff --check 352223b..HEAD`, and a clean worktree. Task2 code commits are `97f6666`, `914ca63`, `89cf17b`, `cb76672`, `b1c41bb`, and `9bc6fb7`; no data/state artifacts were staged.

V6 Task 3: initial submission `a8bca10 feat: add formal feature contract and storage` failed two independent reviews. Important/P1: public `__post_init__` calls re-sealed low-level-mutated evidence/value/bundle or `object.__new__` forgeries; store published via `os.replace` and could clobber a race winner; verified feature directory could be substituted with a link/junction before part/publish operations; and FormulaNode accepted an equality-spoofed mutable unused-items leaf. Review also identified missing focused concurrent/header-mismatch/failure-stage proof. Fix round 1/5 has been dispatched to the original author; remediation remains limited to the same four Task 3 files.

V6 Task 3: fix round 1/5 submitted as `4a97f74 fix: harden formal feature provenance and storage`, only the four allowed Task 3 files. The author added RED/GREEN proofs for public re-sealing/object-forgery, AST equality spoofing, no-clobber target appearance, cleanup, and directory replacement; publication uses `os.link`, not `os.replace`, and verified directory chains are pinned (POSIX dir-fd/no-follow, Windows CreateFileW no-delete sharing). Author reports required four-module 66/67 pass with the sole direct file-symlink privilege skip, directory-replacement probe passing, compilation and diff checks clean. Fresh scoped re-review is mandatory.

V6 Task 3: scoped fix-round-1 review found original provenance, no-clobber, and AST findings addressed, but directory creation remained outside the secure directory session: `_paths(create=True)` could make missing `formal/features` components through an externally substituted parent before pinning began. This is an Important continuation of the directory-substitution finding. Fix round 2/5 has been returned to the original author with a required parent/missing-ancestor creation regression; same four-file scope.

V6 Task 3: fix round 2/5 submitted as `d6d78bd fix: secure formal feature directory creation`, changing only store code/tests. The new missing-ancestor external-target reproduction was RED (created `external-target/data`) then GREEN (external target remains empty); secure traversal now creates every missing component beneath an already pinned parent. Author reports required four-module 67/68 pass with one direct file-symlink privilege skip, both directory replacement probes passing, compilation/diff checks clean. One fresh scoped re-review is required.

V6 Task 3: root independent regression after the scoped approval exposed an environment-specific functional failure: the restricted Windows token can traverse into its default C: TEMP descendants but cannot safely open `C:\Users\Lenovo`; the all-ancestor directory-pin design therefore failed before every TEMP-backed store write. Direct diagnostics showed D: workspace and actual C: TEMP descendant handles work while the inaccessible ancestor does not; the store suite passes when rooted under the D: worktree. Ruling: retain fail-closed behavior for a configured root whose required security chain cannot be pinned rather than silently fall back to unsafe pathname checks; make the test fixture use the project's explicitly supported D: workspace root. Cost if wrong: a user choosing an unpinnable C: root receives a clear safe refusal rather than persistence; supporting that root securely requires a larger handle-relative Windows backend, not a test-only bypass. Fix round 3/5 is required to make the test environment explicit and re-verify the complete suite.

V6 Task 3: fix round 3 submitted as `df1cbc1 test: use secure project temp roots`, only the allowed store test. Root independently reran the required regression without TEMP/TMP overrides: 67/68 pass with one expected direct-symlink privilege skip; compilation and full Task3 diff check passed. Scoped review approved with no Critical/Important issue and confirmed cleanup/no production security weakening. The reviewer identified one Minor POSIX-only test-hook defect: patching `os.mkdir` removes its identity from `os.supports_dir_fd`, so the missing-ancestor race probe can abort before its hook. It is being fixed in round 4/5 rather than deferred, still test-only.

V6 Task 3: fix round 4 submitted as `f121506 test: preserve POSIX mkdir capability in race`, only the allowed store test. It uses a test-local capability-set copy containing the patched mkdir callable so the POSIX secure-path branch can execute the existing race injection; production capability checks are unchanged. Root independently reran the required four-module regression: 67/68 pass with one expected Windows direct-symlink-privilege skip; compiled all four Task3 files and passed `git diff --check 9bc6fb7..HEAD`. Fresh scoped review approved, including restoration of patched globals after exceptional exit.

V6 Task 3: COMPLETE (commits `a8bca10..f121506`, review clean). It provides the signed formal feature contract, closure-sealed evidence/value/bundle boundary, no-clobber content-addressed store, and platform-secure directory traversal within its four-file scope. No data, SQLite/WAL/SHM, score, pool, network, or progress artifact was staged. The Task3 rulings remain: closed fact units; ordered aggregate AST nodes; canonical float wire forms; stale locks fail closed; and an unpinnable Windows root fails closed rather than reverting to unsafe pathname operations.

V6 Task 4: preflight complete. Binding brief `task-4-brief.md` freezes the missing point-in-time, lineage, quarter, history, formula, and builder rules before implementation. Source updates after freeze are excluded while late capture is allowed; selected-quarter lineage is parser ID/version plus mapping version and economic identity, never equal report snapshot/content/generation. Cost if wrong: either revision look-ahead leaks into the frozen 2026-08-31 result or legitimate cross-period reports are incorrectly rejected.

V6 Task 4: policy boundary ruling — history maturity is a separate gate with an exact externally supplied cyclic bool and current Shanghai-calendar eight-quarter window; the Task4 builder publishes only selected FY/quarter inventories, never a score-eligibility claim. Cost if wrong: generic feature construction could silently classify an industry/metric as cyclic or let stale history pass a current-window gate.

V6 Task 4: registry/evaluator boundary ruling — the builder requires a sealed formal root and exact root-child source/mapping/feature hash binding; a structurally valid but non-release child produces blocked values, while forged/mismatched trust material raises. Formula facts use only `FYyyyy` raw-FY and `YYYYQn` trusted-quarter namespaces with a closed unit table and no partial evidence on error. Cost if wrong: unsigned input could be treated as ordinary missing data, or cumulative raw periods could collide with comparable-quarter arithmetic.

V6 Task 4: derivative boundary ruling — FormalQuarterFact has a sealed canonical `formal-quarter-fact-v1` ID over its scientific identity and sorted component facts; direct construction/object-forgery cannot mint a trusted derivative. Builder input hashing covers all visible raw candidates, selected facts, derived quarters, root/child hashes, and issues rather than only winners. Cost if wrong: a conflict or changed revision could reuse a historical result/input hash without preserving the evidence that made the old conclusion unsafe.

V6 Task 4: key-namespace correction — FormalQuarterFact.quarter_key and its canonical-ID payload use the global exact `YYYYQ[1-4]` namespace, not bare Q1–Q4. Cost if wrong: identical quarter evidence can fork between history/formula lookup and the derivative identity, undermining deterministic replay.

V6 Task 4: root-release ruling — builder release approval is the conjunction of the passed sealed root's official gate, exact root-child binding, and child release eligibility; approval previously observed under another root is not transferable merely because child role hashes coincide. Formula-map construction preserves duplicate `(metric_key, period_key)` identities as ambiguity. Cost if wrong: a test/nonofficial root can inherit official approval, or input order can turn an ambiguous economic fact into a fabricated deterministic value.

V6 Task 4: quarter-loading boundary — `FormalQuarterFact.from_dict` is a structural canonical-wire loader and cannot mathematically authenticate a recomputed derivative from operand IDs/evidence alone; only internal derivation from sealed raw facts establishes arithmetic provenance. The builder accepts no caller-supplied quarters and rederives internally. Cost if wrong: a future persistence consumer might mistake an independently canonicalized quarter wire for audited source evidence instead of rederiving or verifying a higher-level bundle.

V6 Task 4: second independent review of `44b974a` reproduced an Important/P1 input-hash collision: an unbound child registry and the same child loaded against its matching official root yielded blocked versus derived bundle contents under the same root/child hashes and identical `input_hash`. Task6 persistence makes input hashes unique, so the blocked historical result could prevent later correct recovery. Remediation must include the sealed effective release-eligibility boolean in the canonical input wire and add the direct regression; same two-file scope, then a fresh review is mandatory.

V6 Task 4: ACCEPTED at `1eef9a6` (initial `44b974a`, remediation `1eef9a6`). It provides deterministic sealed-fact snapshot selection, point-in-time revision exclusion, comparable-quarter derivation, current-window history gating, closed-unit formula evaluation, and root-bound feature bundle construction without scoring. First independent review passed; second review caught and reproduced the release-eligibility input-hash collision; the fresh fix review independently verified distinct hashes for distinct derived/blocked outputs, hostile mutation snapshotting, order stability, and clean scope. Root reran the plan regression: 145/145 passed, compilation and `git diff --check f121506..HEAD` passed, and the worktree is clean. Only the two authorized Task4 code/test files were committed; no data, SQLite/WAL/SHM, score, pool, network, report, brief, or ledger artifact was staged.

V6 Task 5: contract preflight complete. Binding brief `task-5-brief.md` corrects the plan's raw child-envelope DDL: a persisted Task1 registry blob requires declared root hash plus independent binding signature/key ID, not merely child signature fields. StateStore gains optional verifier and feature-store dependencies, with formal APIs failing closed when absent. Cost if wrong: a restart cannot reconstruct/reverify the exact root-child trust graph or bundle receipt and may silently treat raw envelopes as trusted.

V6 Task 5: persistence boundary rulings — fact IDs exclude audit creation time, so exact scientific replay preserves first stored creation time; quarter insertion must rederive from its declared persisted components rather than accept a canonical ID/wire; bundle input hashes are append-only audit identities but Task5 does not claim it can recompute them without Task4 issue/input-manifest persistence. Cost if wrong: ordinary restart/replay conflicts, forged quarter arithmetic becomes durable, or a future reader fabricates a historical input by assuming no extraction issues.

V6 Task 5: ownership reuse ruling — V5 already owns the formal task state machine. Task5 adds only list/circuit APIs and fixes receipt expiry fencing, source-kind receipt validation, and corrupted missing-dependency fail-open behavior; it preserves generic V5 task payloads and generation semantics. Cost if wrong: a stale lease may write after expiry, a corrupted graph becomes leaseable, or a broad queue rewrite breaks accepted V5 recovery behavior.

V6 Task 5: task-list filter ruling — list kinds are exact trimmed safe strings rather than a new finite runtime-kind set, while statuses remain closed. Cost if wrong: a Task5 reader could hide legitimate V5 generic formal tasks or Task5 could accidentally impose Task6 worker-kind policy early.

V6 Task 5: explicit deferred boundary — FormalStoredFeatureBundle has no public durable receipt-recovery constructor; Task5 verifies only a live injected receipt through FeatureBundleStore.read_verified. Task5A must add a public verified recovery API before it can return a typed bundle from SQL. Cost if wrong: persistence code would need to bypass Task3's closure seal with object construction/reflection or incorrectly call an unverified SQL row a trusted bundle.

V6 Task 5: ACCEPTED at `3938b16` after three fresh independent review lanes
found no reproducible issue in V6 migration/task ownership, fact/quarter
provenance, or registry/feature receipt persistence. Root independently ran
the required four-module regression: 268 tests passed in 145.781s with one
expected Windows direct-symlink privilege skip; compilation and
`git diff --check 1eef9a6..HEAD` passed and the worktree was clean. Scope was
exactly `ashare_pipeline/state_store.py` and `tests/test_state_store.py`;
no data, SQLite/WAL/SHM, or progress artifact was staged. Task5A remains
explicitly deferred for public durable feature-receipt recovery.

V6 Task 5A: ACCEPTED at `e2b85fe` (`feat: read verified formal feature
bundles`). It adds the Task3-owned public verified receipt-recovery path and
a fail-closed `FormalFeatureRepository` for exact historical and current
typed bundle reads. Historical reads revalidate file/SQL/header projection,
official/release registry gates, signed slot semantics, and persisted evidence;
current reads rebuild through Task4 using a trusted complete input provider and
fence persisted-fact revisions before, during, and after lookup. The boundary
remains explicit: V6 historic reads prove receipt/config/evidence provenance,
while full semantic recomputation is available only for current provider-backed
selection because V6 does not persist Task4's complete candidate/issue input
manifest. Two independent final reviews found no blocking issue. A time-cutoff
test fixture was corrected without changing production logic: published,
effective, and source-update timestamps are inclusive at the cutoff; late
capture is allowed. Root independently reran the required regression: 274
tests passed in 38.312s with one expected Windows symlink-permission skip;
four-file compilation and `git diff --check HEAD^ HEAD` passed, and the
worktree was clean. Commit scope is exactly the repository/store pair and
their tests; no data, SQLite/WAL/SHM, or progress artifact was staged.

V6 Task 5B: preflight complete after three independent read-only audits
(`task-5b-plan-audit.md`, `task-5b-storage-audit.md`, and
`task-5b-context-audit.md`). The nonnumeric `Task 5B` heading cannot be
extracted by the SDD helper's numeric task parser, so its manually maintained
binding brief is the task authority. Ruling: a canonical
`formal-context-registry-v1` section lives in the existing signed
`scoring` child rather than changing the accepted nine-role root protocol;
it explicitly binds each context kind/scope/request shape/source/parser/mapping
normalizer/generation and every referenced root role. Cost if wrong: an
unregistered dataset or fixture could become official context evidence.
Ruling: bootstrap calendar is only a signed timestamp-source exception to
date-only calendar binding, never a task-provenance exception; every stored
Context fact must originate from a verified `formal_context` producer task.
Cost if wrong: a statement/universe snapshot could be relabeled as market
context. Ruling: a trading-calendar fact carries its exact exchange inside
its canonical value and calendar lookup filters it, avoiding an unapproved
V6 DDL migration; source updates, when present, must be no later than the
explicit cutoff while late capture remains allowed. Cost if wrong: cross-market
calendar reuse or post-freeze correction look-ahead becomes possible. Ruling:
the existing V6 table remains append-only without a new schema/index migration;
logical-generation collisions are checked transactionally and repository
selection uses the specified deterministic V5 version order. Cost if wrong:
conflicts fail closed rather than silently overwriting audit history.

V6 Task 5B: normalizer-boundary ruling — the scoring child Context registry
wire is exactly `{registry_role:"scoring",
schema_version:"formal-context-registry-v1",descriptors:[...]}`. Because no
approved production raw parser/normalizer exists, a narrow injected
`FormalContextNormalizer` is the explicit trusted semantic boundary:
`normalize_verified` checks verified raw bytes/request/descriptor and mints
a sealed normalization receipt; StateStore accepts that receipt rather than
a caller-created fact tuple. Cost if wrong: a direct fabricated
`no_valid_coverage` claim could persist as neutral consensus evidence.

V6 Task 5B: refresh-history ruling — descriptor generation is a fixed
`generation_namespace`, while `upstream_generation` is a required
keyword-only trusted collection input recorded in request/receipt/evidence and
hashed into refresh generation. Cost if wrong: a static descriptor generation
makes legitimate same-root source corrections unpersistable, or an unbound
generation lets audit history be forged. Task6 owns proving the external
authority of that input; Task5B validates exact provenance consistency.

V6 Task 5B: historical-read recursion ruling — repository reads prove source
bytes via `FormalSnapshotRepository.get_verified_by_manifest/read_verified_raw`
and compare sealed persisted normalization provenance; they never re-run a
source adapter or injected normalizer. Bootstrap calendar is a signed timestamp
source selected through that same nonrecursive chain. Cost if wrong: date-only
validation can recursively depend on its own calendar or a mutable runtime
normalizer can be mistaken for historical proof.

V6 Task 5B: durable-normalization ruling — persist a deterministic
`normalization_input_hash` (excluding fact ID and its self field) so read
paths can recheck raw/configuration/structural coherence. The sealed
normalization receipt remains an in-process write capability; no approved
normalizer signing authority exists, so restart reads cannot claim semantic
reparsing protection against a coordinated direct-DB rewrite. Cost if wrong:
either a fabricated direct no-coverage tuple bypasses normalizer gating, or the
system falsely promises a cryptographic semantic guarantee it cannot provide.

V6 Task 5B: private-verification reuse ruling — a public Context entry may
reuse only its own closure-sealed, freshly checked request descriptor during
that single call; it cannot cache it or skip any snapshot/receipt/task/calendar
validation. Cost if wrong: repeated root reloads make strict tests unusably
slow, while broader caching risks a forged request or stale binding crossing
the authorization boundary.

V6 Task 6: contract preflight complete. The numeric Task 6 is extracted into
`task-6-brief.md`; the bundled SDD shell extractor was attempted through Git
Bash but its environment lacks `basename`, so the equivalent plan-scoped
brief/workspace is maintained manually. The existing isolated worktree is on
`cf60a5c`; no Task 6 code has started. Three independent read-only inventories
confirm that V5/V6 already supply leases, immutable receipt binding, circuit
state, facts/context/bundle persistence, and atomic three-exchange universe
storage; Task 6 needs no DDL, migration, index, cache, or global mutable
state.

V6 Task 6: preflight interface scan — typed payload/generation/runtime work
feeds source-task execution; source-task receipts feed statement/context
writes, feature rebuilds, and universe source results; universe source results
feed only the zero-transport finalizer. The feature rebuild must replay the
selected verified raw snapshots to reconstruct extraction issues and compare
the extracted facts with V6 before building, because V6 does not persist
`FormalFactIssue`. No task consumes an unverified SQL projection as raw proof.
Each internal delivery is reviewed before the next one because all production
work is confined to one new module and one new test module.

V6 Task 6: three-exchange ruling — use the Formal V3 plan's explicit
BJ/SH/SZ universe and `FormalUniverseIngestor`, rather than silently applying
the older PLAN.md's SH/SZ wording. This matches the user's all-A-share scope
and the existing ingestor's exact three-exchange contract. Cost if wrong: the
worker's frozen universe may differ from an older product-policy definition;
the later scoring/release plan must make any narrower investability filter
explicit rather than altering collection evidence.

V6 Task 6: upstream-generation ruling — the new worker never invents an
upstream generation: typed spec builders receive the caller's authoritative
generation, store it verbatim, and recompute the derived collection generation
from that value plus the loaded signed root/role/calendar binding before receipt
reuse or transport. The approved Task 6 interface provides no separate signed
external-generation authority type, so provenance of that external value stays
at the injected scheduling boundary; absent/mismatched typed/root evidence is
terminal and makes zero network requests. Cost if wrong: an upstream scheduler
can label a correction incorrectly, but the worker cannot silently reuse it
under a different root/configuration or fabricate a discovery value.

V6 Task 6: result/recovery ruling — source-task results use a canonical typed
audit wire containing the lease-bound receipt identity, snapshot manifest and
content hash, parser identity, root and derived generation (and canonical rows
hash/exchange for universe sources). A statement feature rebuild writes the
content-addressed feature receipt first, persists/re-reads the V6 row next,
then completes the task; retry recovery uses the same immutable input hash.
Cost if wrong: a crash between files and SQLite could be mistaken for a new
remote collection or a source/parser change could be hidden behind a generic
task result.

| Task 6 delivery | Produces | Consumes | Preflight finding |
| --- | --- | --- | --- |
| 6A contract/runtime | closed payload codecs, derived generation, task specs, runtime loader | verified root bundle, signed role blobs, V5 task key/edge APIs | compatible; no direct registry construction |
| 6B statement/feature | receipt replay/fetch, V6 facts, feature task/bundle recovery | adapter, snapshot receipt, mapping registry, V6 fact/bundle APIs | issues must be replayed from selected raw snapshots |
| 6C context/calendar | date-only gate and sealed Context writer execution | signed context request, binding repository, Task5B normalizer | compatible only with exact leased task/worker capability |
| 6D universe | BJ/SH/SZ source specs and zero-transport frozen finalizer | signed resolver, re-parsed receipts, FormalUniverseIngestor, V6 universe store | compatible; exactly three immutable source edges |

V6 Task 6: preflight self-review — Task 6's only shared implementation files
are intentionally sequential because every delivery extends the same closed
worker dispatcher. The plan, brief, and existing APIs agree on the five kinds,
receipt-before-completion, fail-closed date-only binding, no legacy/generic
payloads, and canonical three-exchange universe. The external-generation
authority limitation is recorded above rather than hidden; no separate
authority type or unapproved source endpoint is introduced.

V6 Task 6: test-discipline ruling — an interrupted 6A agent left an
unreported untracked production module before providing RED evidence. The
module was deleted without inspection, its test file was retained, and root
recorded the expected `ModuleNotFoundError` RED before re-dispatching a fresh
implementer. Cost if wrong: deleting an unreviewed implementation may repeat
work, but retaining it would violate the required test-first provenance and
make later review unable to distinguish design from retrofit.

V6 Task 6: statement-order ruling — the main plan says fixed lexical order;
the initial brief accidentally named a nonlexical human statement order. The
binding order is `balance_sheet`, `cash_flow_sheet`, `profit_sheet`, which is
the literal lexical order and is now explicit in the brief. Cost if wrong: a
downstream caller that assumed a business-label order must use its own named
dataset lookup rather than infer semantics from task sequence.

V6 Task 6: context-payload ruling — `FormalContextRequest` is already the
closure-sealed capability minted by `SignedContextRequestResolver`; a raw
`FormalContextTaskPayload` tuple cannot independently prove a descriptor's
dataset, scope, selected roles, generation, or calendar binding. Therefore
Task6 context payloads are constructed only from a sealed request and must
field-for-field match it; the task spec retains the resulting canonical wire
and immutable prerequisite edge. Cost if wrong: duplicating descriptor rules
in the worker either admits fabricated context work or rejects valid signed
contexts with different dataset/scope labels.

## Task 6A completion — 2026-09-06

- Committed `fd35595 feat: add formal collection task contracts` on `codex/formal-v3-implementation`; it contains only `ashare_pipeline/formal_deep_worker.py` and `tests/test_formal_deep_worker.py`.
- Contract layer is complete: closed typed task payloads/specs, canonical generation/key binding, sealed `FormalContextRequest`-derived payloads, exact date-only calendar pairing, verified runtime provenance, and immutable finalizer dependency edges.
- Verification: 17 `tests.test_formal_deep_worker` tests passed in 8.417s in the final root run; cached diff check clean; post-commit security and specification reviews found no Critical/Important/Minor findings.
- Deferred intentionally to 6B–6D: queued execution, source transport, raw snapshot receipt persistence/recovery, feature rebuilds, context execution, and universe finalization.
- 2026-09-06 — Task 6B1 committed as `96e66a9 feat: execute formal statement tasks safely`. It contains only `ashare_pipeline/formal_deep_worker.py` and `tests/test_formal_deep_worker.py`. Statement tasks now validate runtime/generation/calendar/request provenance, recover receipt-first with verified raw replay, persist facts only under live leases, enqueue/supersede same-security feature work safely, and map retry/circuit/terminal outcomes. Final root verification: 36 tests in 2.441s, cached diff check clean; post-commit security and spec reviews clean. Feature execution, context execution, and universe execution remain deferred.
- 2026-09-06 — 6B2 discovery: the existing signed `cyclic` root child is intended to govern frozen SW2021 secondary industries in V7, while the V6 feature boundary explicitly excludes industry/policy context. No current typed cyclic parser exists. A full cyclic 5-FY gate in V6 therefore requires an explicit cross-plan amendment to carry verified frozen industry-context lineage into feature tasks; do not use a per-security fallback or silently default unknown coverage. User direction is required before implementation.
- 2026-09-06 — User chose **B** for the cyclic-policy boundary: V6 stays context-free and enforces the universal non-cyclic 4-FY/8-quarter history baseline; the signed cyclic-industry policy, 5-FY rule, and cyclic cap remain a separate V7 policy-engine delivery. No per-security fallback or V6 industry-context dependency is authorized.
- 2026-09-06 — Task 6B2 D1 committed as `0169d6d feat: enforce universal feature history gate`. V6 now applies the user-selected noncyclic 4-FY/latest-8Q gate using input-v2 semantics. Root verification ran 72 tests in 4.202s; post-commit security/spec reviews clean. V1 bundle storage remains compatible; D2 will version queued feature-task generation before execution is enabled.
- 2026-09-06 — Task 6B2 D2 committed as `d679ac6 feat: version feature task history semantics`. Feature refresh generations now bind the fixed noncyclic history semantics, superseding only unfinished same-scope legacy generations while preserving verified historical artifacts. Root verification ran 73 tests in 5.987s; post-commit security/spec reviews clean.
- 2026-09-06 — Task 6B2 D3 committed as `e919176 feat: reconstruct frozen feature inputs`. The new pure helper rebuilds only from frozen selected raw snapshots: it verifies the leased feature spec/runtime, source verified task/receipt/result/request lineage, original date-only statement binding, full re-extracted V6 fact identity, and real extraction issues before constructing a bundle. It makes no transport, task, database, file, feature-store, or circuit mutation. Non-release signed roots and insufficient history return blocked bundles; unverified sources raise `FeatureSourcePending` for D4 recovery. Root verification ran 85 tests in 14.831s, compilation and diff checks passed, and independent pre/post-commit security and specification reviews were clean. D4 is next: lease-fenced feature persistence and recovery.
- 2026-09-06 — Task 6B2 D4 ruling: retain the accepted 6B1 dispatch priority. In a mixed queue, lease a ready `formal_statement` before any ready `formal_feature_build`; fall back to a feature task only when no statement is leaseable. Cost if wrong: a pending feature build can run against facts that an already-ready correction statement will immediately supersede, and the prior statement-worker semantics regress.
- 2026-09-06 — Task 6B2 D4 committed as `9853e7c feat: execute resilient feature build tasks`. It adds lease-fenced local feature reconstruction persistence and exact content-addressed recovery: file-only and DB-before-completion crashes recover without transport, corrupt/root-mismatched receipts terminalize without overwrite, non-release/history-blocked bundles persist and complete, and the closed completion result has no machine-local paths. Source-pending work uses a finite no-transport/no-circuit hold. Statement priority remains ahead of feature work. Four lost-lease cutpoints plus pending-hold fail, direct persistence loss, root binding, and security/template isolation have regressions. Root verification: `tests.test_formal_deep_worker` 66 passed in 48.411s; `tests.test_formal_financial_features tests.test_formal_feature_store` 53 passed in 1.102s (one expected Windows symlink-permission skip); compilation and cached/post-commit diff checks passed. Three independent D4 reviews found no Critical/Important/Minor issue. Only worker code/tests were committed; no data, SQLite/WAL/SHM, network, report, or progress artifact was staged.
- 2026-09-06 — Task 6B2 follow-up ruling: three pre-existing `FormalV6PersistenceTests` fixture failures are not D4 regressions. The D4 baseline and current tree are byte-identical for `formal_financial_features.py`, `state_store.py`, and `test_state_store.py`; the fixture supplies only FY2025, while D1’s universal history gate correctly returns a blocked no-evidence bundle. Align those StateStore tests in a separate code/test-only task using history-complete fixture evidence. Cost if wrong: the aggregate suite remains red or an invalid no-evidence bundle can falsely exercise evidence-integrity assertions.
- 2026-09-06 — D1 StateStore fixture alignment committed as `ee85a76 test: align formal bundle history fixtures`. The test-only helper supplies FY2022–FY2025 plus the raw cumulative periods that derive 2024Q3–2026Q2; the three persistence tests now exercise valid evidenced bundles while retaining missing-evidence and foreign-security rejection paths. Independent review found no findings. Root verification: focused 3 tests passed, `tests.test_state_store` 208 passed in 73.828s, and combined worker/financial-feature/feature-store/state-store regression 327 passed in 120.458s with one expected Windows symlink-permission skip; compilation and diff checks passed. Only `tests/test_state_store.py` was committed; no data or state artifact was staged.
- 2026-09-06 — Task 6C preflight: existing sealed Context request/normalization and StateStore persistence APIs are sufficient; no migration is authorized. Ruling: re-resolve with the StateStore-configured verifier and preserve resolver-owned `formal-context-refresh-generation-v1`, rather than using the statement generation helper. Cost if wrong: an old/forged descriptor or different generation semantics can be treated as current official Context evidence.
- 2026-09-06 — Task 6C normalizer boundary ruling: add an explicit version-keyed normalizer injection with an immutable empty default; use only a `FormalContextRegistry` loaded from the exact configured StateStore/verifier, and require exactly one normalized fact. Cost if wrong: an arbitrary callback or multi-fact response can fabricate/merge Context evidence under a leased task.
- 2026-09-06 — Task 6C scheduling/result ruling: retain statement-first dispatch, then Context, then feature; Context success must not schedule a V6 feature build. Completion has the closed worker audit map recorded in `task-6c-context-execution-brief.md`. Cost if wrong: corrected statements lose priority, V6 context-free feature inputs are polluted, or a task result leaks mutable/local data.
