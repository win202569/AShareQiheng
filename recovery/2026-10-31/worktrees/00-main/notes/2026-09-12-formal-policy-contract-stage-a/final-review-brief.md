# Stage A integrated review brief — ACTIVE

Final reviewed task HEAD: 101d42a24a29fce9f5d101760350ba598cea1630. A1 6809363, A2 6ea72c1, A3 101d42a are committed after separate task reviews. A1 had two findings closed in one round; A2 no findings; A3 one missing exchange-owner binding closed in one round. All task verdicts Approved. Final full policy run on exact corrected files: worker 86 / 275.907s OK, guard suite 18 / 125.243s OK; parent original 85 / 251.627s plus new targeted fix 1 / 1.931s OK; parent legacy 72 / 29.737s and focused old arithmetic/dispatch 10 / 0.005s OK. Evidence versions are distinct; no claim that parent original 85 included the later added regression. Parent final combined verification is running separately on final HEAD.

Scope: the approved Stage A plan only, code range b9b367d64d1204985ddbea77e7ca6f7832694ae8 through the final A3 commit supplied by controller. Earlier V3 work in this branch is the reviewed baseline, not an instruction to re-review all prior development. This final review must inspect the complete Stage A implementation and A1/A2/A3 interactions, not merely the last task diff.

Read the authoritative spec at docs/superpowers/specs/2026-09-12-formal-policy-contract-design.md and the implementation plan at docs/superpowers/plans/2026-09-12-formal-policy-contract-stage-a.md. Shared changes are exactly two production modules and four test/helper modules. No old production module, signed fixture JSON, data, SQLite, report output, pipeline process or CLI is changed.

## Accepted controller rulings

1. Mandatory delisting_arrangement uses exactly that singleton listing enum, not a broader value set. Other explicitly named signed rules may not redefine required semantics.
2. Opaque inactive legacy JSON preserves existing root/child canonical numeric bytes; active economic parameters remain Decimal strings.
3. Source binding follows actual source.select semantics: null-or-exact exchange then exactly one result; no fallback priority. Input-security bootstrap is rejected because the existing adapter does not accept a security identity for bootstrap requests. Existing earlier loader ValueErrors are preserved, not hidden.
4. Feature same-root means authentic content/source/mapping membership in the current verified root. Feature objects do not retain a minting-root ID; identical authentic content may legitimately be reused between roots, changed content may not.
5. contract_hash is a public field and appears in detached to_dict; canonical_bytes excludes contract_hash and equals A2's canonical bound bytes, avoiding self-reference.
6. Retain plan progress/review artifacts and existing tmpj4zv9_fq; no cleanup, merge or push. This review is read-only.

## Cross-component review priorities

- A1 detached parser objects/bytes cannot act as A3 trusted proof or scoring inputs.
- A2 re-reads actual signed graph, preserves full binding definitions, checks full five-template coverage, annual formula identity, same-template references and exhaustive V dependencies.
- A3 publishes only after complete binding and repeated source authentication; private weakref ownership and lookup protection reject ordinary copies/forgery/field/method/module/owner-binding replacement. Read-time source verification must remain, but full policy parsing/binding must not repeat on each field read.
- Preserve the explicit ordinary Python replacement threat boundary; no arbitrary interpreter/metaclass manipulation claim and no generic security-framework expansion.
- Current A1 cyclic status/semantic equality and uniqueness ensure exactly one cyclic rule per template. If that constraint changes, template-keyed dependencies need corresponding changes; no current overwrite is reachable.
- Stage B/C capabilities remain declarations only: no actual market window, annual observations, adapter execution, policy readiness, final score or pools. major_event uses the approved regulatory flag. Generic event_record syntax has no current active consuming family; no runtime event unit equality is claimed.
- Frozen cutoff, seven weights, hard vetoes, caps, peer eligibility and no-fill/no-reweight behavior must remain unchanged.

Use task reports/review results and final-verification.md as evidence, not substitutes for reading the final implementation. Report concrete file:line findings with actual severity, strengths and a clear readiness assessment. Do not rerun reported suites without a concrete unresolved risk, spawn subagents, write files, change Git state, fetch live data or touch databases. A focused check for a specific uncovered doubt is permitted. Parent performs independent fresh verification of the final tree.
