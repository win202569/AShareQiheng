# Perf4a implementation report

Status: partial foundation. No production batch/publish path calls the journal.

Implemented:

- Build-local `FormalBatchReadJournal` with exact fixed owner types, private scope/ticket construction, owner and StateStore identity, root/cutoff/full population/thread binding, active/finalizing/consumed lifecycle, mandatory coverage, per-phase check deduplication, and same-key baseline conflict rejection. Optional tickets for other members of the frozen population are accepted. Tickets expose the exact selected result while the scope is active.
- Owner selectors and checkers are anchored when the owner modules install, so replacing one before `open` cannot become the new trusted baseline. The journal's issuer functions are also anchored.
- Context tickets use the complete candidate and winner/absence token produced by the same successful batch selection. Issuance compares that token to the current snapshot. Checkpoints authenticate original sources, preserve actual absence, and require the original winner to remain uniquely current.
- Feature tickets after successful current metric projection/absence selection, covering request, complete provider generation/facts/issues, persisted facts, signed registry, receipt metadata, bundle bytes, required feature keys and selected proof. The same selection now captures the metadata bytes used by both authenticated reads. Issuance refuses a present bundle whose hash, bytes, or receipt differs from that token, including a coherent replacement under the same `input_hash`. Checkpoint does not rebuild formulas or evaluate slots.
- Range tickets use the candidate and parent snapshot token produced by the same successful `select_current` logic, then bind it to the authenticated task/snapshot/receipt/attempt/raw/manifest six-tuple. A candidate inserted between selection and issuance is rejected. Checkpoint does not parse range data or rerun current selection.

Not implemented: financial, state, and market owner tickets; production integration and publish gating. Range absence ticketing is also not implemented. This is not a complete Perf4a deployment.

Verification:

- `tests.test_formal_batch_read_journal`: 20 passed. Includes selector-return insertion races, pre-open method substitution, two-security Context and two-request range scopes, and actual once-per-phase checker counting.
- Latest Feature-specific rerun: 5 passed, including same-input bundle replacement, same-bundle metadata replacement, and absence-to-present receipt races.
- Existing Context batch selection, feature current correction, and range current correction tests: 3 passed.
- Targeted compile check passed. Full store, C4, and repository-wide suites were not run.

All C4 dirty files were left untouched and excluded from the commit.

Feature token audit:

- Request, required keys, provider batch ID, full facts/issues, and persisted fact set originate from the successful current selector and are checked against its sealed proof at issuance.
- For present selection, `input_hash` and `bundle_hash` come from the expected/stored/reread agreement. The authenticated reader captures the exact metadata receipt bytes on both reads, and selection rejects disagreement between them. Issuance and checkpoint compare the original proof, bundle bytes/hash, and full metadata bytes to that token.
- For absence, both authenticated reads must return no receipt. The proof's `input_hash` and expected `bundle_hash` are tied to the selector's expected bundle bytes; issuance and checkpoint require both bundle and metadata to remain absent.
