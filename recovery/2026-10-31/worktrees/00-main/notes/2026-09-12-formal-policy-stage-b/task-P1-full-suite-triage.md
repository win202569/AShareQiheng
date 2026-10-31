# P1 full-suite failure — read-only triage

HEAD: 21746b2990b24c79b93521dc75f5d8e7e4a7f176.
Reviewer: /root/p1_full_suite_failure_triage. No tests, edits or Git writes.

- Error occurs at the first persistence ownership gate, before fact insertion:
  tests/test_formal_context_repository.py:629 -> :233-236;
  state_store.py:1976-1980; formal_context_repository.py:231-244.
- The same receipt already passed ownership checks during normalization at
  formal_context_schema.py:623-645. Between the final successful check and the
  failing one, the fixture returns the sealed receipt and opens persistence.
- state_store.py:3147-3156 combines kind, leased status, worker, expiry and
  generation into a single query. formal_context_repository.py:38-65 already
  checks task existence/kind/generation. Static evidence narrows the failure to
  status/worker/expiry, but cannot establish which predicate changed. The generic
  error alone does not prove timeout.
- This case uses default lease_seconds=300 at test lines188-195/625-629. Related
  multi-step date-only tests use3600 at lines660-675/689-692. Duration is a lead,
  not causal proof.
- The modified P1 path is not consumed by this test. FormalContextRegistry.load
  (formal_context_schema.py:551-590) uses the generic FormalRegistryBundleLoader
  (formal_registry_manifest.py:633-727). Fixture feature role is a tiny generic
  blob (test lines156-159); this flow does not call/import SignedFormalFeatureRegistry,
  load_signed_feature_registry, _parse_registry_bytes or slots_for_template.
- Repeated work here is context bundle loading/source selection/calendar binding
  through two _select passes (formal_context_repository.py:416-437), stored-fact
  validation and snapshot revalidation. P1 does not optimize these paths.

## Proposed next scope — not executed

Run only this test once with forwarding diagnostics that record the task row
(status, lease_worker, lease_expires_at, refresh_generation) and sampled now at the
final normalization gate and persistence gate. Do not change verdicts, clocks,
production leases, source rules or owner checks. If expiry with unchanged ownership
is proven, consider a separately authorized test-only lease_seconds=3600 at line629
consistent with adjacent cases; otherwise investigate the actual failed predicate.

Current user approval limits edits to feature contract and its corresponding test.
Controller will request expanded test-only scope before any third-file fix.
Full-suite result remains FAILED(errors=1,skipped=4), not relabeled GREEN.
