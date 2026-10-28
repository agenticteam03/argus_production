"""Validation, step-up binding and audit rows for private target holds (ACR-0019 §3.10, §3.11).

A hold names a host-qualified target, a whole host (`vm-166`) or `*` (the emergency stop). Placing one lowers power and
is one step; releasing one raises it, so it needs its own step-up, and the emergency stop is released only from the
CLI on vm-095 by the lease holder, never from the browser.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime

from argus.domain.model import AuditRecord, TargetRef


def validate_hold_target(target: str, inventory) -> None:
    if target == "*" or ("/" not in target and inventory.host(target) is not None):
        return
    try:
        ref = TargetRef.parse(target)
    except ValueError as exc:
        raise ValueError("hold target must be a known host, a known host-qualified target or *") from exc
    if inventory.target(ref) is None:
        raise ValueError("hold target is not in inventory")


def hold_step_up_object(target: str) -> str:
    """Bind one WebAuthn assertion to the exact hold scope without putting a slash in its object ID."""
    return "hold:" + hashlib.sha256(target.encode("utf-8")).hexdigest()


def hold_release_step_up_object(hold_id: str) -> str:
    return f"hold-release:{hold_id}"


def hold_audit(event: str, actor: str, at: datetime, *, incident_id: str | None = None, **detail) -> AuditRecord:
    return AuditRecord(audit_id=f"aud_{uuid.uuid4().hex[:16]}", incident_id=incident_id, at=at, category="decision",
                       event=event, actor=actor[:64], detail=detail)
