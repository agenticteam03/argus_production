"""ACR-0018 §3, phase 16 step 5: the job that signs and ships the daily audit digest.

On the scheduler's schedule (`audit_digest` in `schedules.yaml`, off by default) it verifies the whole chain; if the chain
is broken it signs nothing (a digest of a rewritten chain would vouch for it) and records why. Otherwise it builds the
digest of every closed UTC day, signs it with the audit digest key and puts it once in the sink. Everything it does is a
`security` audit event; none of them carries a key, a body or an error message from the store.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import date
from pathlib import Path
from typing import Callable

from argus.domain.audit_chain import verify
from argus.domain.audit_digest import build_digest, check_series, digest_days, object_name, sign, to_bytes
from argus.domain.model import AuditRecord, utcnow

log = logging.getLogger("argus.audit_digest")


class AuditDigestJob:
    def __init__(self, store, key, sink, clock: Callable = utcnow):
        self.store, self.key, self.sink, self.clock = store, key, sink, clock

    def _record(self, event: str, detail: dict) -> None:
        self.store.append(AuditRecord(audit_id=f"aud_{uuid.uuid4().hex[:16]}", incident_id=None, at=self.clock(),
                                      category="security", event=f"security.audit_digest_{event}", actor="scheduler",
                                      detail=detail))

    def run_once(self) -> str:
        missing = [name for name, thing in (("key", self.key), ("sink", self.sink)) if thing is None]
        if missing:
            for name in missing:
                self._record("unconfigured", {"missing": name})
            log.error("audit digest is enabled but has no %s: nothing is signed or shipped", " or ".join(missing))
            return f"unconfigured: no {' or '.join(missing)}"
        rows = self.store.audit_chain()
        _, _, problems = verify(rows)
        if problems:
            self._record("skipped", {"reason": "chain_broken", "problems": len(problems)})
            log.error("audit digest skipped: the audit chain is broken (%d problem(s))", len(problems))
            return f"skipped: the chain is broken ({len(problems)} problem(s))"
        shipped = conflicts = 0
        off_host = bool(self.sink.off_host)
        for day in digest_days(rows, self.clock().date()):
            try:
                result = self._ship(rows, day)
            except Exception as e:                      # the next run starts again from this day; nothing is skipped
                detail = {"day": day.isoformat(), "error": type(e).__name__, "off_host": off_host}
                if isinstance(getattr(e, "reason", None), str):       # a sink's own short, safe reason (a status and a code)
                    detail["reason"] = e.reason[:120]
                self._record("failed", detail)
                log.error("audit digest of %s failed: %s", day, type(e).__name__)
                return f"failed at {day.isoformat()}: {type(e).__name__} ({shipped} shipped before it)"
            if result == "stored":
                shipped += 1
                digest = build_digest(rows, day)
                self._record("shipped", {"day": day.isoformat(), "name": object_name(day), "off_host": off_host,
                                         "last_audit_id": digest["last_audit_id"],
                                         "chained_rows": digest["chained_rows"]})
            elif result == "exists_different":
                conflicts += 1
                self._record("conflict", {"day": day.isoformat(), "name": object_name(day), "off_host": off_host})
                log.error("audit digest of %s: the store holds different bytes under %s", day, object_name(day))
        if not off_host and shipped:
            log.warning("audit digest: the sink is not off host, so these digests do not protect the chain")
        return f"shipped {shipped} digest(s), {conflicts} conflict(s)"

    def _ship(self, rows, day: date) -> str:
        body = build_digest(rows, day)
        return self.sink.put_once(object_name(day), to_bytes(sign(body, self.key)))


def check_digest_files(paths, rows, public_pem: bytes) -> list[str]:
    """`argus audit check-digests`: read the shipped digests (files, or folders searched for `*.json`) and check them as a
    series against the chain and the audit digest key's public half. A file that is not a signed digest is reported by name,
    and finding nothing to check is a problem, not a pass."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    from cryptography.hazmat.primitives.serialization import load_pem_public_key
    key = load_pem_public_key(public_pem)
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError("the public key must be an Ed25519 key")
    files: list[Path] = []
    for p in map(Path, paths):
        files += sorted(p.rglob("*.json")) if p.is_dir() else [p]
    if not files:
        return ["no digest files found"]
    items, problems = [], []
    for f in files:
        try:
            item = json.loads(f.read_bytes())
            date.fromisoformat(item["digest"]["day"])
            item["signature"], item["digest"]["last_audit_id"], item["digest"]["last_hash"]
            item["digest"]["chained_rows"]
        except (ValueError, KeyError, TypeError, OSError):
            problems.append(f"{f.name}: not a signed digest")
            continue
        items.append(item)
    return problems + check_series(items, rows, key)
