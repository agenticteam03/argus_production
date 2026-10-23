"""ACR-0018 §3, phase 16 step 5: the signed daily digest of the audit hash chain.

The chain (`audit_chain.py`) proves that no row was edited, removed or inserted *inside the database*. Someone with
`sudo` on the VM could still rewrite the whole chain, hashes included. A digest closes that: for each closed UTC day it
records the last chained row on or before that day, signed with the audit digest key and shipped to a store outside the
VMs (put once, never overwritten). `check_against_chain` compares a shipped digest with the chain as it stands now.

Pure functions: no I/O, no clock. The job that calls them is `argus/infrastructure/audit_digest.py`.
"""
from __future__ import annotations

import base64
import hashlib
from datetime import date, datetime, timedelta
from typing import Any, Iterable

from argus.domain.audit_chain import canonical

VERSION = 1
Row = tuple[str, Any, str | None, str | None]       # (audit_id, body, prev_hash, hash), as `Store.audit_chain()` returns


def _day(body: Any) -> date:
    return datetime.fromisoformat(str(body["at"])).date()


def _chained(rows: Iterable[Row]) -> list[Row]:
    return [r for r in rows if r[3] is not None]     # rows from before migration 011 have no hash and are not digested


def digest_days(rows: Iterable[Row], today: date) -> list[date]:
    """The closed days to ship: from the day of the first chained row to the day before `today`."""
    chained = _chained(rows)
    if not chained:
        return []
    first = _day(chained[0][1])
    return [first + timedelta(days=i) for i in range((today - first).days)]


def build_digest(rows: Iterable[Row], day: date) -> dict[str, Any] | None:
    """What the chain held at the end of `day`: the last row written before the first row dated after it (so a row dated
    out of order cannot move an earlier day), how many rows the chain holds up to it, how many were dated that day.
    None when the chain had not started. A quiet day repeats the previous last row, so a missing day stays visible."""
    last, count, that_day = None, 0, 0
    for row in _chained(rows):
        d = _day(row[1])
        if d > day:
            break
        last, count = row, count + 1
        that_day += d == day
    if last is None:
        return None
    return {"version": VERSION, "day": day.isoformat(), "last_audit_id": last[0], "last_hash": last[3],
            "chained_rows": count, "rows_that_day": that_day}


def object_name(day: date) -> str:
    """One object per day, with a name of its own: the store's credential can create but not overwrite."""
    return f"audit-digest/{day.year}/{day.isoformat()}.json"


def key_id(public_key) -> str:
    """A short, public name for the signing key, so a shipped digest says which key signed it."""
    from cryptography.hazmat.primitives import serialization
    raw = public_key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return hashlib.sha256(raw).hexdigest()[:16]


def sign(body: dict[str, Any], private_key) -> dict[str, Any]:
    """The digest with its Ed25519 signature over the canonical JSON of the body (deterministic: the same digest signed
    twice gives the same bytes, so putting it again is recognised as the same object)."""
    signature = private_key.sign(canonical(body).encode("utf-8"))
    return {"digest": body, "key_id": key_id(private_key.public_key()),
            "signature": base64.urlsafe_b64encode(signature).decode()}


def to_bytes(signed: dict[str, Any]) -> bytes:
    return (canonical(signed) + "\n").encode("utf-8")


def verify_signed(signed: Any, public_key) -> bool:
    """True when the signature is valid for the digest body and this key. Never raises on a malformed object."""
    from cryptography.exceptions import InvalidSignature
    try:
        signature = base64.urlsafe_b64decode(str(signed["signature"]).encode())
        public_key.verify(signature, canonical(signed["digest"]).encode("utf-8"))
        return True
    except (InvalidSignature, KeyError, TypeError, ValueError):
        return False


def check_against_chain(signed: dict[str, Any], rows: Iterable[Row]) -> list[str]:
    """Problems between a shipped digest and the chain as it stands now (empty = they agree). The signature is checked
    by `verify_signed`; this is the other half: the chain still holds the row the digest named, with the same hash."""
    body = signed["digest"]
    day = body["day"]
    chained = _chained(rows)
    for position, (audit_id, _, _, hash_) in enumerate(chained, start=1):
        if audit_id != body["last_audit_id"]:
            continue
        if hash_ != body["last_hash"]:
            return [f"{day}: the chain holds a different hash for {audit_id} than the one shipped"]
        if position != body["chained_rows"]:
            return [f"{day}: the chain holds {position} rows up to {audit_id}, the digest says {body['chained_rows']}"]
        return []
    return [f"{day}: {body['last_audit_id']} is not in the chain (rows removed)"]


def check_series(items: list[dict[str, Any]], rows: Iterable[Row], public_key) -> list[str]:
    """The shipped digests as a whole (empty = all well): each is signed by the audit digest key and agrees with the
    chain, none is twice for a day, and no day is missing between the first and the last (a gap hides a removed digest).
    Problems come ordered by day."""
    rows = list(rows)
    found: list[tuple[str, str]] = []
    days: list[date] = []
    for item in items:
        day = date.fromisoformat(item["digest"]["day"])
        if day in days:
            found.append((day.isoformat(), f"{day}: more than one digest for this day"))
            continue
        days.append(day)
        if not verify_signed(item, public_key):
            found.append((day.isoformat(), f"{day}: the signature does not verify"))
            continue
        found.extend((day.isoformat(), p) for p in check_against_chain(item, rows))
    if days:
        have = set(days)
        first, last = min(days), max(days)
        for i in range((last - first).days):
            missing = first + timedelta(days=i)
            if missing not in have:
                found.append((missing.isoformat(), f"{missing}: no digest for this day (a gap in the series)"))
    return [message for _, message in sorted(found, key=lambda t: t[0])]
