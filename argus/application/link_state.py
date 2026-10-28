"""TASK-60: the `link_ok` verify signal of `network.restore` (ACR-0035), read from the link recorder.

The recorder (`link_transitions.py`) keeps the latest state of each recorded edge (owner -> dependency). `link_ok` is
true only when that state is `ok`: `slow`, `broken` and `unknown` are not, and an edge with no record is not ok.
"""
from __future__ import annotations

from typing import Any


def link_ok(store: Any, dependent: str, target: str) -> bool:
    """True when the recorder's latest state of the edge `dependent` -> `target` is `ok`."""
    cursor = (store.link_probe_cursors(dependent) or {}).get(target)
    return bool(cursor) and cursor.get("state") == "ok"


def link_ok_actual(store: Any, dependent: str, target: str) -> str:
    """The value a verification sample carries for `link_ok`: "1" or "0", compared with the card's expected 1."""
    return "1" if link_ok(store, dependent, target) else "0"
