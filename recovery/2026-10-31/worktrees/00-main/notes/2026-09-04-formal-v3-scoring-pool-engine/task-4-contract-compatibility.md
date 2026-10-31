# Task 4 contract compatibility — 2026-09-12

Read-only design-support check by policy_contract_compatibility (gpt-5.6-sol/high), at HEAD 853b932. No implementation, tests, signing, data changes or Git mutations.

- Existing manifest binds the four policy roles; its generic child validation authenticates canonical bytes/signature/hash/root/approval but imposes no policy-body schema (formal_registry_manifest.py:24-35, 640-700).
- A separate FormalPolicyRegistry can accept an exact sealed VerifiedRegistryBundle, require_official(), and consume its cyclic/redline/status/event blobs (formal_registry_manifest.py:560-593).
- Preserve policy child top-level six-key shape and formal-scoring-policy-v1. Existing scoring validation fixes both (formal_scoring_registry.py:212-228).
- Additional executable contracts may use distinct new IDs under rules and explicit per-rule schema versions; existing loader permits arbitrary nonempty rule objects (formal_scoring_registry.py:233-239).
- Preserve existing selected classification rule's exact secondary_industries-only shape and original semantics (formal_scoring_registry.py:444-447).
- A new exact validator can resolve explicit executable rule IDs without changing the old scoring wrapper's shape (formal_scoring_registry.py:243-252, 449-456).
- Changed policy child content necessarily changes hashes; contract versions/categories must match. Scoring wrapper content must therefore be reissued and re-signed with corresponding policy hashes (formal_scoring_registry.py:220-232). Preserving old SCHEMA is possible; pretending modified bytes retain old hash/signature is not.
- Scoring wrapper schema can stay formal-scoring-registry-v1 or v2 (formal_scoring_registry.py:365-384). No new wrapper field is needed solely for a separate rule loader.

Proposed staged direction for user design approval: (1) exact versioned signed policy-contract loader, (2) authenticated policy evidence/outcomes including confirmed missing-close representation, (3) adjusted valuation whole-cohort recalculation and final confidence/cards before pool selection. Existing constants remain binding. Production selectors, source equivalences, quantile convention and additional thresholds require explicit signed configuration; no default or production approval is supplied here.

This is research/design support, not an approved executable specification or implementation dispatch. Task 4 remains at the architectural design approval gate.
