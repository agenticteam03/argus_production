"""Validation and step-up binding for private target holds."""
from __future__ import annotations

import hashlib

from argus.domain.model import TargetRef


def validate_hold_target(target: str, inventory) -> None:
    if target == "*":
        return
    try:
        ref = TargetRef.parse(target)
    except ValueError as exc:
        raise ValueError("hold target must be a known host-qualified target or *") from exc
    if inventory.target(ref) is None:
        raise ValueError("hold target is not in inventory")


def hold_step_up_object(target: str) -> str:
    """Bind one WebAuthn assertion to the exact hold scope without putting a slash in its object ID."""
    return "hold:" + hashlib.sha256(target.encode("utf-8")).hexdigest()
