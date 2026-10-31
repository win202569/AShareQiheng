# R2 review — 38644671691e244164c267b07732d9756a06142e
## Spec Compliance
Issues found: request minting, parser execution, cross-root source isolation, and fetch sealing each permit an authority bypass. These violate R2 genuine-request, sealed-execution, same-root, and exact-type requirements.
Cannot verify from this diff: R3 receipt/file authentication, final visibility and coverage decisions, and joint cross-task acceptance. These remain downstream gates; RangeFetch is not that proof.
## Strengths
formal_sources.py:918 checks complete source-registry hash; tests :166/:183 distinguish changed blobs from identical blobs in different roots.
formal_range_source.py:221 provides closed document/row timing, counts, pagination, unresolved date-only observations; test :308 preserves late observations.
test_formal_range_source.py:370 covers registry-value and normalizer-method replacement with genuine bindings.
## Important findings (verbatim)
1. **An arbitrary guard callback can mint an accepted request.**
   ashare_pipeline/formal_range_request.py:84, :109, :120: the module-accessible _mint_range_request accepts caller-provided wire/config/hash and grants registration when root_guard() returns True. It neither authenticates the guard’s provenance nor validates the date/freeze bounds; page_index=True also satisfies its equality check against 1.
   **Reproduced:** calling it directly with a copied genuine config, root_guard=lambda: True, start_date="0001-01-01", end_date="9999-12-31", a future freeze, and boolean page index produced a request accepted by SignedSourceRegistry.select_range. No monkeypatching was needed. Authenticate the mint capability against genuine binding authority and enforce exact request invariants at the mint boundary.
2. **Instance method shadowing bypasses the registered parser and normalizer.**
   ashare_pipeline/formal_range_source.py:626, :676: fetch and replay dispatch through mutable self._parse, which is absent from the sealed dependency checks.
   **Reproduced:** assigning source._parse = lambda *args: ParsedRangeDocumentV1.from_dict(document_wire(request)) allowed fetch_verified to return a genuine fetch while the registered parser and normalizer each had zero calls. This also skips _parse’s identity and pagination checks. Capture the genuine parsing implementation in the source closure and invoke that captured implementation for both paths.
3. **Fetch and replay accept requests belonging to another source’s root and source blob.**
   ashare_pipeline/formal_range_source.py:606, :610, :636, :640: both paths discard the request’s private source-registry hash and compare only the selected config. They never compare the request’s manifest root with the receiving source binding.
   **Reproduced:** changed an unrelated SZ source entry, creating different complete source-blob and manifest hashes while retaining the selected SH entry. The second source successfully fetched the first source’s request and returned a fetch carrying the first root’s identity. Compare both manifest-root and complete source-registry identities against the receiving binding before transport/replay, preserving the live checks.
4. **Fetch sealing uses equality that conflates boolean and integer fields.**
   ashare_pipeline/formal_range_source.py:349, :352: the seal compares tuples with ordinary equality, and fetch slots remain assignable.
   **Reproduced:** setting a genuine fetch’s page_count from 1 to True left to_manifest() successful and emitted a boolean page count. This violates exact typing and the promise that mutated fetches fail authentication. Verify exact field types together with values, or compare a canonical sealed representation; add mutation tests for all numeric manifest fields.
## Assessment
No Critical/Minor findings. Spec issues; task quality Needs fixes.
One focused in-memory probe covering all four named risks, exit 0, reproduced all four. Runtime code metadata supplied exact lines. No unchanged production source, Git commands, suites, or file writes. Prior 79-test run does not cover these demonstrated paths.
## Root disposition
Read complete feedback and confirmed the four affected code paths directly. No conflict with approved spec; resume original implementer for fix round 1. No production data or broader source authority authorized.

