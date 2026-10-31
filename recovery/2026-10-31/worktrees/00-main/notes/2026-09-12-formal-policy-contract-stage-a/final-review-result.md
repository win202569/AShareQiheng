# Stage A integrated review — original committed HEAD

Reviewer /root/policy_stage_a_final_review (astra/high). Full six-file range b9b367d..101d42a reviewed with relevant upstream interfaces. Readiness: Changes required. One Important finding, no Critical or separate Minor.

Finding at formal_policy_contract.py:294: _selector does not require kind=context for expected_kind bool/enum/market_record/calendar_record. Context type comparison only runs in Context branch; final discriminator check only covers feature/annual_series. A valid feature selector bypasses Context requirements.

Two genuinely signed focused probes: (1) replace both bank_no_effective_trade_20d inputs with bank.policy.equity feature selectors and add feature-valued boolean/enum rules; A3 load and require_verified both succeed, authenticating all three malformed active rules and omitting required market/calendar Context bindings. (2) replace mandatory bank_st value with that feature selector; later KeyError('context_kind') rather than PolicyContractError. Same missing discriminator root cause.

Required correction: enforce Context kind for Context-typed inputs before dispatch; cover feature/annual substitutions in A1, separately signed market/state substitutions through A3 and mandatory-ST typed-error behavior. Preserve unknown kind/version error classification and existing allowed inputs.

Strengths: detached A1 / bound A2 / privately owned A3 separation; actual source/root/slot/annual/template/V closure; immutable storage/reauthentication/dependency-owner guards; no policy reparse on reads and no runtime authority. _freeze compatibility is sound for all current accepted definition leaf types.

Reviewer ran only the two focused probes, no suite rerun/file/Git/DB/network side effects. Combined parent suite is separate evidence and this review never authorizes merge or push.

## Single consolidated fix scoped re-review

Finding ADDRESSED. Selector family is checked before subtype parsing; Context expectations require context, financial/annual expectations retain their families. Unknown kinds remain unsupported_contract; known-family substitutions are malformed_contract at .kind; Context subtype checks and generic accepted syntax preserved.

New tests separately reject signed market/calendar/additional boolean/additional enum/mandatory-ST substitutions with both feature and annual inputs. Exact PolicyContractError code/path assertions occur after real signing, so setup failures and KeyErrors cannot count as successful rejection. Three hashes match report; no unstaged delta; production change confined to _selector.

No new breakage or out-of-scope observations. Final Stage A readiness Approved CONDITIONAL on pending corrected full-policy suite success. Worker focused15 /11.385s and independent parent15 /12.611s OK are supporting evidence, not a substitute for the final full run. Reviewer ran no tests/writes in this scoped pass.

## Final gate closure

Condition satisfied: exact frozen corrected policy suite94 /292.440s OK, parent independent corrected-tree118 /39.758s OK, final hashes match. Fix committed as29cf92362574945f9ca41d2c9374a56bcc9ffe90. Stage A readiness Approved; no unresolved finding. Branch remains isolated with no merge/push.
