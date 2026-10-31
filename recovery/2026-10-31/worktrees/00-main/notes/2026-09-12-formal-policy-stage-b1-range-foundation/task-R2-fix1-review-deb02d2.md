# R2 scoped fix round 1 review — deb02d2
Reviewer: /root/stage_b_r2_reviewer
Fix base 38644671691e244164c267b07732d9756a06142e; head deb02d287e03442002d6e6182e4a68e033c74e01.

- Arbitrary guard callback can mint an accepted request — ADDRESSED. formal_range_request.py:3 only reexports the type. Closure-owned mint at formal_range_source.py:239 requires a genuine current binding and computes frozen bounds/page identity itself. Tests :144,:169,:572 check removed mint surface and invalid bound/type mutations.
- Instance method shadowing bypasses registered parsing — ADDRESSED. Fetch/replay call captured trusted_parse at formal_range_source.py:830,:887. Tests :547,:557 install shadows and verify both registered implementations still execute.
- Fetch/replay accept another root or source blob — ADDRESSED. Source binding manifest and complete source hash compared at formal_range_source.py:810,:847. Tests :237,:257 cover both cross-root cases through fetch/replay, including rejection before transport.
- Fetch sealing conflates bool/int — ADDRESSED. formal_range_source.py:564 checks each field exact type and value. Test :583 covers all three integer manifest fields.

## New Breakage
None identified.
## Out-of-Scope Observations
None.
## Checks
Read complete fix diff and retained final output: 31 tests, 643.039s, OK, exit 0.
Read-only runtime metadata used for line references. No rerun tests, Git or file edits.
Root joint compatibility still ongoing.
## Verdict
All findings addressed, no new Critical/Important breakage.

