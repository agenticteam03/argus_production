"""OP-014 step 9: tests written from the mutation run of `argus/domain/audit_chain.py` (mutmut 3.3.1, 2026-10-23).

- A row without a hash after the chain started is reported and the rows after it are still verified: one row inserted
  outside the store must not hide an edit further down (`continue` replaced by `break` survived).
- The canonical form and the link hash are pinned to fixed values. A change to either (key order, separators, how
  non-ASCII text or a time is written) would still verify rows written after it, so no other test sees it, but every
  row already chained on a VM would then fail `verify` (the `canonical` mutants survived).
"""
from __future__ import annotations

from datetime import datetime, timezone

from argus.domain.audit_chain import GENESIS, canonical, link_hash, verify

BODY = {"event": "security.webauthn_login", "detail": {"session": "s1", "credential": "ñandú"},
        "at": datetime(2026, 10, 23, 4, 0, tzinfo=timezone.utc), "n": [1, None, True]}


def _chain(bodies: list[dict]) -> list[tuple[str, dict, str, str]]:
    rows, prev = [], GENESIS
    for i, body in enumerate(bodies):
        h = link_hash(prev, f"aud_{i}", body)
        rows.append((f"aud_{i}", body, prev, h))
        prev = h
    return rows


def test_rows_after_an_unhashed_row_are_still_verified():
    rows = _chain([{"n": 0}, {"n": 1}, {"n": 2}])
    audit_id, _, prev_hash, hash_ = rows[2]
    rows[2] = (audit_id, {"n": "edited"}, prev_hash, hash_)
    rows.insert(1, ("aud_x", {"n": "outside"}, None, None))
    chained, before, problems = verify(rows)
    assert (chained, before) == (3, 0)
    assert problems == ["aud_x: no hash after the chain started (inserted outside the store)",
                        "aud_2: hash does not match its body (the row was edited)"]


def test_the_canonical_form_and_the_link_hash_are_fixed():
    assert canonical(BODY) == ('{"at":"2026-10-23 04:00:00+00:00","detail":{"credential":"ñandú","session":"s1"},'
                               '"event":"security.webauthn_login","n":[1,null,true]}')
    assert link_hash(GENESIS, "aud_1", BODY) == "38079ce6e16f908cdf04514d2c792198723950826f1e2cf2ad3291da1017f145"
