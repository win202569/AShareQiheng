# A3 original task review

Reviewer /root/policy_a3_review (astra/high). Original staged two-file snapshot vs 6ea72c16ba206cdf69f5f1ac6aaaa9a1258fd670.

Spec Compliance: Needs fixes. Task Quality: Needs fixes. One Important/P2, no Critical or Minor.

Finding: registry.py:338 captures formal_sources._require_exchange but not its owner module _EXCHANGES. That enum is read at formal_sources.py:259 through CalendarSelector.__post_init__:369 and formal_context_schema.py:409; it is an actual binder descriptor-path dependency. Focused reproduction loaded and verified a genuine graph, replaced _EXCHANGES with frozenset({'SH','SZ','BJ','FAKE'}), and both existing proof.require_verified() and a new loaded proof succeeded. This demonstrates missing replacement rejection, not forged signatures. Add the exact owner binding and a restored-mutation regression checking old reads and new loading fail. No upstream redesign needed.

Strengths: exact private ownership/weakref cleanup at :410/:493; original source methods and root/nine-child/feature verification at :386/:477; immutable payload/hash serialization; tests for no rereparse, construction invalidation, collection and B/C boundaries at guards:209/:228/:253. Reviewer ran only the focused reproduction, no suite reruns or file/Git mutations.

## Fix round 1 scoped re-review

Finding ADDRESSED: registry.py:338 now retains defining-module _EXCHANGES identity; new test at guards:181 proves old reads and new loads fail during replacement and both recover after restoration. Exact fix delta reviewed; no new breakage or out-of-scope observations.

Resulting Spec Compliance: Approved. Task Quality: Approved. Worker focused RED/GREEN and parent independent focused pass support closure; corrected-tree full acceptance remains a separate pending parent gate. No suites rerun or file/Git mutations by reviewer.
