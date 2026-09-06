# V6 Task 4 binding brief — point-in-time facts, comparable quarters, and formal feature evaluation

Plan: \`docs/superpowers/plans/2026-09-04-formal-v3-financial-feature-pipeline.md\`, Task 4.

Prerequisites: Tasks 1, 2, and 3 are accepted through \`f121506\`. This
brief resolves Task 4 omissions only. It creates no production registry,
metric, industry/cyclic policy, raw field map, template substitution, source
fetch, SQLite record, score, pool, confidence C, or release decision.

## Scope and commit boundary

Create or modify exactly:

1. \`ashare_pipeline/formal_financial_features.py\`
2. \`tests/test_formal_financial_features.py\`

Do not modify Tasks 1–3, legacy financial code, \`state_store.py\`, plans,
data, SQLite/WAL/SHM, or any other tracked file. Do not collect data or make
network calls. The initial code commit subject is:

\`\`\`text
feat: derive formal point-in-time financial features
\`\`\`

Record RED/GREEN only in ignored \`task-4-report.md\`; never stage this brief,
reports, ledger, data, SQLite/WAL/SHM, or progress files.

## Shared security posture

Use the accepted Task 1–3 ordinary Python threat model: exact public type
checks, sealed upstream records, defensive snapshots, canonical JSON, and
deterministic sorted tuples. General arbitrary same-process reflection into
Python closure cells remains the acknowledged language-level limitation; do
not weaken ordinary constructor, \`object.__new__\`, public-field mutation,
custom equality, custom Mapping, or insertion-order defenses.

Every \`FormalFinancialFact\` consumer must require
\`type(fact) is FormalFinancialFact\` and immediately call \`fact.to_dict()\`
before reading scientific/lineage fields. Every \`FormalFactIssue\` consumer
must require exact type then call \`.to_dict()\`. Never consume public fact
attributes first. \`FormalEvidenceRef.from_formal_fact\` is the only raw-fact
to evidence conversion route.

Use only \`formal_time.is_visible_at\` and \`formal_time.formal_version_sort_key\`
for their stated jobs. Task 4 must independently enforce its stricter
canonical UTC, type, conflict, and reliability rules; \`formal_time\` accepts
aware non-UTC strings and does not validate a fact seal for this task.

All externally supplied timestamps in this module are exact, canonical UTC
\`str\` values with a literal \`+00:00\` suffix, parse/round-trip equal through
\`datetime.fromisoformat(...).isoformat()\`, and have no \`Z\` alias. Dates are
exact ASCII \`YYYY-MM-DD\`; quarter keys are exact ASCII \`YYYYQ[1-4]\`. SHA-256
is lowercase 64 hex characters. Security IDs are exact canonical SH/SZ/BJ
identities from Task 2. Reject bools as numbers and every nonfinite result.

## Public surface

\`formal_financial_features.py\` exports exactly:

\`\`\`text
FormalFactVersionView
FormalFactSelection
FormalQuarterFact
FormalQuarterDerivation
FormalHistoryResult
FormalFormulaResult
select_visible_formal_facts
derive_comparable_quarters
require_formal_history
evaluate_formula
build_formal_feature_bundle
\`\`\`

\`FormalFactVersionView\` is the only object passed to
\`formal_version_sort_key\`; it has exactly:

\`\`\`text
published_at_utc, source_updated_at_utc, captured_at_utc, content_hash
\`\`\`

Its \`content_hash\` comes exactly from a sealed fact wire's
\`source_content_sha256\`, never from a similarly named ad-hoc field.

\`FormalFactSelection\` has exact frozen fields
\`facts: tuple[FormalFinancialFact, ...]\` and
\`blockers: tuple[str, ...]\`. Facts are sorted by the canonical logical group
key below; blockers are safe sorted unique text.

\`FormalQuarterFact\` has exactly the plan fields:

\`\`\`text
id, security_id, statement, metric_key, quarter_end, quarter_key, value,
unit, nature, accounting_basis, mapping_version, component_fact_ids, evidence,
derivation_version
\`\`\`

It is a trusted derivative: ordinary direct construction and
\`object.__new__\` population must not mint a valid quarter. It must expose
\`.to_dict()\` and strict canonical \`.from_dict()\`, each revalidating its
closure-private provenance. Its canonical ID is the SHA-256 of canonical JSON:

\`\`\`json
{
  "schema_version": "formal-quarter-fact-v1",
  "security_id": "...",
  "statement": "...",
  "metric_key": "...",
  "quarter_end": "YYYY-MM-DD",
  "quarter_key": "YYYYQ[1-4]",
  "value": 0.0,
  "unit": "...",
  "nature": "...",
  "accounting_basis": "...",
  "mapping_version": "...",
  "component_fact_ids": ["..."],
  "derivation_version": "formal-quarter-derivation-v1"
}
\`\`\`

Fields are JSON-native and values are canonical finite floats (reject integer
and negative-zero substitutions in \`.from_dict()\`). The operand IDs are
strictly sorted/unique and evidence is the corresponding sorted/unique
\`FormalEvidenceRef\` union. Evidence is fully determined by operands but is
validated again before serialization. The ID changes when an operand ID,
scientific identity, value, unit, mapping version, or derivation version
changes. Do not add a clock, path, score, or source default.

\`.from_dict()\` is a strict structural canonical-wire loader: with only
operand IDs and evidence wires, it cannot independently prove the arithmetic
relationship to raw operand values when an attacker has recomputed a new ID.
It must seal post-load mutation, but arithmetic provenance is established only
by \`derive_comparable_quarters\` from sealed raw facts. Therefore the formal
bundle builder must never accept caller-supplied quarters (and does not); a
future persistence reader must rederive from verified raw facts or use a
separately verified higher-level bundle boundary rather than treating a
standalone loaded quarter as source evidence.

\`FormalQuarterDerivation\` has frozen
\`facts: tuple[FormalQuarterFact, ...]\` and
\`blockers: tuple[str, ...]\`. \`FormalHistoryResult\` has frozen
\`eligible: bool, annual_endpoints: tuple[str, ...], blockers: tuple[str, ...]\`.
\`FormalFormulaResult\` has frozen
\`value: float | None, unit: str | None, evidence: tuple[FormalEvidenceRef, ...],
time_reliability: float | None, missing_reason: str | None\`.

For a derived formula result, value is finite float, unit is a closed formal
unit, evidence is nonempty/sorted/unique, time reliability is finite in
\`[0, 1]\`, and missing reason is \`None\`. For any missing result, all of
value/unit/evidence/time reliability are respectively
\`None/None/()/None\` and missing reason is nonempty safe text. It never
preserves partial evidence for a failed arithmetic operation.

## Point-in-time fact selection

\`select_visible_formal_facts(facts, as_of_utc)\` snapshots the finite input
before selection. It accepts only exact \`FormalFinancialFact\` objects;
custom mappings, generic objects, malformed iterable elements, and mutated
facts raise \`ValueError\`.

1. Validate exact canonical UTC \`as_of_utc\`.
2. Snapshot every fact wire through \`.to_dict()\`.
3. Exclude (without a \`future_fact\` blocker) a fact when any of
   \`published_at_utc\`, \`effective_at_utc\`, or non-null
   \`source_updated_at_utc\` is after the cutoff. A late
   \`captured_at_utc\` remains valid: it can represent a later reconstruction
   of pre-cutoff evidence.
4. Group remaining facts by exactly
   \`security_id, statement, metric_key, period_start, period_end, period_kind,
   unit, nature, accounting_basis\`.
5. Within one logical group, any differing \`parser_id\`, \`parser_version\`,
   or \`mapping_version\` is a mapping/version conflict. Drop that group and
   add \`fact_mapping_version_conflict\`. Do not select the newer parser or
   mapping opportunistically.
6. Project every candidate to \`FormalFactVersionView\` and sort ascending by
   \`formal_version_sort_key\` (newest publication, newest non-null source
   update, newest capture, then content hash). Collapse byte-identical fact
   wires. If the best sort key has more than one distinct sealed fact wire,
   including a distinct raw value or lineage, drop that group and add
   \`fact_selection_tie_conflict\`; never use input order or fact ID as an
   unapproved tie breaker.
7. Output the winner of each surviving group sorted by the group tuple above,
   and blockers sorted/unique. A conflict removes only its own logical group;
   other groups remain available.

Call \`is_visible_at\` only after validating canonical timestamps. A raw fact
whose \`source_updated_at_utc\` is after freeze must not backfill a
pre-freeze publication. This freeze is stricter than the original abbreviated
Task 4 prose and is required to prevent revision look-ahead.

## Comparable quarters

\`derive_comparable_quarters(facts)\` consumes only the already selected
\`FormalFinancialFact\` tuple (normally \`selection.facts\`). It does not
receive an as-of time and therefore never attempts version selection. Duplicate
logical facts or multiple inputs for one endpoint create a blocker rather than
an arrival-order choice.

Facts are grouped by calendar year and the economic family
\`security_id, statement, metric_key, unit, nature\`. Within the same family
and year:

- \`accounting_basis\`, \`parser_id\`, \`parser_version\`, or
  \`mapping_version\` disagreement invalidates the entire family/year: emit
  respectively \`quarter_accounting_basis_mismatch\`,
  \`quarter_parser_version_mismatch\`, or
  \`quarter_mapping_version_mismatch\` and emit no quarter from that group.
- Do **not** require equal snapshot ID, content SHA, refresh generation,
  publication time, source update, or capture time across Q1/H1/Q3/FY:
  legitimate reports necessarily differ. The compatible selected-version
  lineage is the equal parser identity/version and mapping version above,
  together with the exact economic family.
- \`OTHER\`, wrong calendar endpoint, a noncanonical period, or duplicate
  period kind invalidates that family/year with
  \`quarter_invalid_period\` or \`quarter_duplicate_period\`.

Recognized period endpoints are Q1/03-31, H1/06-30, Q3/09-30, and FY/12-31
of the same calendar year. Duration facts use exactly:

\`\`\`text
Q1 = Q1 cumulative
Q2 = H1 cumulative - Q1 cumulative
Q3 = Q3 cumulative - H1 cumulative
Q4 = FY cumulative - Q3 cumulative
\`\`\`

Instant facts use Q1/H1/Q3/FY directly as Q1/Q2/Q3/Q4 point values. Missing
or nonconsecutive duration prerequisites emit
\`quarter_missing_prerequisite\` and suppress only the affected quarter; do
not interpolate, substitute a later year, treat annual cumulative as Q4, or
clamp negative arithmetic. An arithmetic overflow/nonfinite result emits
\`quarter_nonfinite_derivation\` and suppresses that quarter. The mixed-basis
example consequently yields an empty output for its sole family/year.

Each emitted quarter has complete sorted operand IDs (one operand for direct
Q1/instant, two for subtraction), every operand's
\`FormalEvidenceRef.from_formal_fact\` evidence, and derivation version
\`formal-quarter-derivation-v1\`. Output is sorted by
\`security_id, statement, metric_key, quarter_end, unit, nature,
accounting_basis, mapping_version, id\`; blockers are sorted/unique.

## Formal history gate

\`require_formal_history(annual_endpoints, *, comparable_quarter_keys,
as_of_utc, cyclic)\` is deliberately a separate gate. Task 4 does not infer
cyclic status from template/industry, and the feature builder below does not
claim that a generic union of endpoints proves score eligibility. A later
verified policy caller supplies exact \`cyclic: bool\` and feeds the relevant
selected metric history.

\`cyclic\` is exact \`bool\`. Annual endpoints must be sorted/unique exact
\`YYYY-12-31\` dates. Quarter keys must be sorted/unique and **exactly eight**
\`YYYYQ[1-4]\` values. Convert the UTC cutoff to Asia/Shanghai calendar date;
the expected quarter window is the eight consecutive calendar quarters ending
at the most recently ended calendar quarter no later than that date. At the
formal 2026-08-31 close it is exactly 2024Q3 through 2026Q2. A completed but
stale old eight-quarter window is ineligible.

The latest eligible annual endpoint is the most recent 12-31 no later than
the cutoff. Non-cyclic requires its four consecutive annual endpoints;
cyclic requires five. Extra historical endpoints are allowed but the result
returns the required latest window only. Missing, nonconsecutive, future,
duplicate, unordered, malformed, or stale inputs return
\`eligible=False\` with deterministic blockers; any evidence insufficiency
must include \`pending_evidence/history_not_mature\`. The helper never
shortens a CAGR/persistence window.

## Formula evaluation

\`evaluate_formula(node, facts)\` is syntax-safe arithmetic only. It evaluates
a fresh \`FormulaNode.from_dict(node.to_dict())\` snapshot and rejects a
malformed/deep/cyclic node as \`ValueError\`, never calls or evaluates text.
The \`facts\` input must be an exact \`dict\`: keys are exact two-string tuples,
values are exact sealed \`FormalFinancialFact\` or \`FormalQuarterFact\`, and
every key must match its value's canonical identity. All mapped values must
have one canonical security ID; ambiguous duplicate economic values are
rejected rather than resolved by insertion order.

The only formula period-key namespace is:

\`\`\`text
FYYYYY       -> selected raw FY fact whose period_end is YYYY-12-31
YYYYQ[1-4]   -> trusted derived comparable quarter
\`\`\`

\`fact_key\` matches \`metric_key\` exactly. It deliberately does not guess
aliases or statement/template equivalences. Multiple facts that would match
the same \`(metric_key, period_key)\` make the formula missing with
\`formula_fact_ambiguous\`; unknown/unsupported keys make it missing with
\`formula_fact_missing\`. Raw Q1/H1/Q3 cumulative values cannot be fed
directly into formula keys, preventing cumulative-versus-single-quarter
collisions.

Reliability is exactly \`1.0\` for \`timestamp\` evidence and \`0.8\` for
\`date_only\` evidence; a derived result uses the minimum across **all**
operands. Quarter reliability is the minimum of its component fact
precisions. Every successful operation returns the sorted/unique union of all
operand evidence.

Operations use this closed economic-unit table:

- add/subtract: both operands have the same unit; result keeps it;
- divide: equal units produce \`ratio\`; \`CNY / shares\` produces
  \`CNY_per_share\`; every other pair is \`formula_unit_mismatch\`;
- cagr: \`left\` is the start, \`right\` the end; units match; both values are
  strictly positive; result is \`ratio\` and equals
  \`(right / left) ** (1 / intervals) - 1\`;
- median/minimum: every finite operand has the same unit; even median is the
  arithmetic mean.

Zero (including negative zero) division denominators, nonpositive CAGR
endpoints, unit mismatch, nonfinite arithmetic, or any missing child return a
missing result with a deterministic reason and no partial evidence. Minimum
evidence includes every candidate, not just the winning value.

## Feature bundle construction

The complete required signature is:

\`\`\`python
def build_formal_feature_bundle(
    *,
    security_id: str,
    as_of_utc: str,
    template_id: str,
    facts: Iterable[FormalFinancialFact],
    issues: Iterable[FormalFactIssue],
    registry: SignedFormalFeatureRegistry,
    registry_manifest: FormalRegistryManifest,
) -> FormalFeatureBundle: ...
\`\`\`

There are no optional/default registry, root, issues, cyclic, quarters, or
history parameters. Quarters are rederived internally from the selected raw
facts; a caller cannot inject a forged or stale quarter. History eligibility
is intentionally not guessed by this builder because cyclic policy and
per-metric score-history anchors are owned by a later verified policy task.
Its \`history_endpoints\` is only the sorted inventory of visible selected FY
period ends, and \`comparable_quarter_keys\` is the sorted inventory of
internally derived quarter keys. Neither inventory alone asserts eligibility;
callers must use \`require_formal_history\` on the relevant selected metric
sequence before scoring.

Validate canonical security/time/template first. Snapshot every raw fact and
issue as above; a fact for another security is \`ValueError\`. Issue codes are
closed to Task 2 extraction's six codes:

\`\`\`text
required_source_field_missing, duplicate_source_field, nonnumeric_value,
invalid_row_shape, unknown_source_field, mapping_not_applicable
\`\`\`

Any valid passed issue makes the bundle globally blocked with the corresponding
sorted \`formal_fact_issue_<code>\` blocker. An unknown/forged/mutated issue
raises \`ValueError\`, rather than smuggling arbitrary text into a bundle.

The root boundary is mandatory:

1. require exact \`SignedFormalFeatureRegistry\` and use
   \`.slots_for_template(template_id)\` to revalidate/rebuild its signed slots;
2. require exact \`FormalRegistryManifest\`; read all nine public role hashes,
   call \`.assert_member_hashes(**all_nine)\` to force its closure seal, and
   validate that its source/mapping/feature hashes exactly equal the child;
3. use \`registry_manifest.manifest_hash\` as the bundle's
   \`registry_manifest_hash\`.

A forged/mutated root or registry, an invalid template, or any root-child hash
mismatch raises \`ValueError\`. Release eligibility is the conjunction of the
child's \`.release_eligible\` flag and the **passed** sealed root satisfying
its official/release gate; never inherit approval merely because the child was
previously loaded alongside another root with identical member hashes. A
structurally valid signed registry that is not release eligible (including a
correctly sealed test-purpose root or a registry loaded without its matching
root) is not an exception: create one
\`blocked\` \`FormalFeatureValue\` for every applicable slot, all with
\`feature_registry_not_release_eligible\`, and include the same bundle
blocker. This is the only meaning of the original plan's “unsigned fixture”
case; arbitrary untrusted objects never become a blocked bundle.

If registry release eligibility holds but selection or passed issues produce
global blockers, produce every applicable slot as \`blocked\` with
\`feature_input_not_trustworthy\`. Otherwise evaluate each signed slot
formula against a fresh exact fact map constructed from the selected facts and
internally derived quarters:

- a successful finite result must exactly equal the slot's signed unit and
  becomes \`derived\`;
- an unsuccessful formula becomes \`missing\` with its deterministic reason;
- a required missing slot additionally appends
  \`feature_required_slot_missing\` to bundle blockers;
- optional slots may be \`missing\` but do not add that global required-slot
  blocker; \`not_applicable\` is never fabricated for a slot that is applicable
  to the chosen signed template.

Before constructing the formula mapping, detect duplicate formula identities;
two legal values that resolve to the same \`(metric_key, period_key)\` must
reach the evaluator as \`formula_fact_ambiguous\`, never overwrite according
to input order. The builder includes all selection/quarter blockers in the sorted bundle
blockers. It never assigns a formal score, peer percentile, pool, confidence
C, or formal-scored state.

Compute \`input_hash\` as SHA-256 of canonical JSON with fixed
\`schema_version="formal-feature-input-v1"\`, containing:

- \`security_id, as_of_utc, template_id, contract_version\`;
- root manifest hash and source/mapping/feature registry hashes;
- the sealed, effective boolean release eligibility used for this build (passed
  root official gate AND signed child release eligibility);
- a sorted/unique canonical list for every visible raw candidate consumed at
  this cutoff (not merely winners): fact ID, source snapshot ID, source content
  SHA-256, and refresh generation;
- selected fact IDs; sorted derived quarter IDs; fixed quarter derivation
  version; and sorted canonical issue wires.

Including all visible candidates prevents a tied/conflicting revision from
reusing a historical input hash merely because it was not selected. Future
facts are excluded from the historical input. Input order must not affect the
hash.

## Required TDD proof

Start RED because \`formal_financial_features.py\` is absent. Tests must cover:

1. cutoff equality, post-close publication/effective exclusion, post-cutoff
   source-update exclusion, late-capture acceptance, every sort-key level,
   random-order independence, mapping/parser conflicts, equal-sort-key
   scientific conflicts, duplicate collapse, sealed/mutated fact rejection;
2. all duration and instant quarter rules, mixed basis/parser/mapping/unit,
   missing prerequisites, duplicate/nonconsecutive/OTHER/cross-year endpoints,
   negative result preservation, nonfinite failure, stable canonical quarter
   identity, full operand evidence, and direct/low-level quarter forgery;
3. four/five annual gate, exact current eight-quarter window, stale windows,
   malformed/duplicate/future inputs, exact bool cyclic, and
   \`pending_evidence/history_not_mature\`;
4. all FormulaNode operations and period namespace, mapping/key impersonation,
   cross-security values, ambiguity, wrong units, zero denominator, nonpositive
   CAGR, overflow, even median, missing nested child, reliability 1.0/0.8,
   and complete evidence union;
5. mandatory root/child binding, sealed test-purpose/non-release registry
   producing blocked slots, forged root/registry failure, passed Task 2 issue
   blocking, selected/quarter blocker propagation, required vs optional
   missing slots, quarter injection impossibility, canonical input-hash
   stability/order independence and changes on root/mapping/generation/tied
   candidate changes; and
6. plan-required regression:

\`\`\`powershell
.\.venv\Scripts\python.exe -m unittest tests.test_formal_financial_features tests.test_formal_financial_schema tests.test_formal_feature_contract tests.test_formal_time tests.test_financial_features -v
\`\`\`

Run compilation and \`git diff --check\` before commit.
