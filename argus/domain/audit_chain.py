"""ACR-0018 §17.1 layer 13: the audit hash chain.

Every audit row written after migration 011 carries `prev_hash` (the previous chained row's `hash`) and its own
`hash` = SHA-256 of the previous hash, the row's id and its body as canonical JSON. A row edited, deleted or inserted
outside the store breaks the chain at that row. Rows written before 011 have no hash; they are counted, not chained.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable

GENESIS = "0" * 64


def canonical(body: Any) -> str:
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def link_hash(prev_hash: str, audit_id: str, body: Any) -> str:
    return hashlib.sha256(f"{prev_hash}\n{audit_id}\n{canonical(body)}".encode("utf-8")).hexdigest()


def verify(rows: Iterable[tuple[str, Any, str | None, str | None]]) -> tuple[int, int, list[str]]:
    """rows: (audit_id, body, prev_hash, hash) in write order. Returns (chained rows, rows before the chain,
    problems); the first problem names the first row where the chain breaks."""
    chained, before, problems, prev = 0, 0, [], None
    for audit_id, body, prev_hash, hash_ in rows:
        if hash_ is None:
            if prev is None:
                before += 1                       # written before migration 011
                continue
            problems.append(f"{audit_id}: no hash after the chain started (inserted outside the store)")
            continue
        expected_prev = GENESIS if prev is None else prev
        if prev_hash != expected_prev:
            problems.append(f"{audit_id}: prev_hash does not match the previous row (a row removed or reordered)")
        if link_hash(prev_hash or GENESIS, audit_id, body) != hash_:
            problems.append(f"{audit_id}: hash does not match its body (the row was edited)")
        prev = hash_
        chained += 1
    return chained, before, problems
