# A1 review result — original staged snapshot

Spec compliance: issues found. Task quality: Needs fixes.

Important 1: formal_policy_contract.py:111 parses JSON floats as Decimal, then :114 canonicalizes them differently from the existing json.loads/json.dumps(sort_keys=True) contract at formal_registry_manifest.py:69/81. Valid existing canonical bytes containing exponent-form numbers are rejected. Focused reviewer probe added inactive opaque value 1e-6 using the existing test canonicalizer; parse_policy_contract rejected it at :115. Use established canonical semantics or exactly compatible implementation; extend inactive-content test at test_formal_policy_contract.py:491 with exponent form.

Important 2: formal_policy_contract.py:383 reports unsupported median_method/profit_basis_method as malformed_contract; :408 treats unknown effective_trade_method likewise. Unknown algorithm identifiers must report unsupported_contract. Add classification and assertions to existing mutations at tests:226/319.

No Critical/Minor findings. Reviewer praised exact fields, recursive freezing, fixed dispatcher, effect validation and inactive identity preservation.

Cannot verify by task boundary: five-template coverage/source/AST/descriptor/V coverage/mandatory veto = A2; authenticated loading/read guards = A3. Root resolves these by scheduled A2/A3 gates, not as claimed A1 capabilities.

