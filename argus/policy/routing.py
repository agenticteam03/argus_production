"""Escalation routing as data (ARCHITECTURE §15.2, `config/routing.yaml`; T-0042).

Imports nothing from Argus. An escalation goes, in this order, to the route of its unsupported alert's name, to the
route of its class family, or to the default (the operators' channel). A target is `channel:<name>` (a human
channel) or `peer:<name>` (a peer agent, §23). Fail closed: an unknown key, an unknown family, a malformed target or
no default refuses the file at startup.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

TARGET = re.compile(r"^(channel|peer):[a-z0-9][a-z0-9_-]{0,63}$")
KEYS = {"default", "by_family", "by_alertname"}


@dataclass(frozen=True)
class Routing:
    default: str = "channel:operators"
    by_family: dict[str, str] = field(default_factory=dict)
    by_alertname: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_data(cls, data: dict | None, families: set[str]) -> "Routing":
        data = data or {}
        if not isinstance(data, dict) or set(data) - KEYS:
            raise ValueError(f"routing: unknown keys {sorted(set(data) - KEYS) if isinstance(data, dict) else data}")
        default = data.get("default")
        if not isinstance(default, str) or not TARGET.match(default):
            raise ValueError(f"routing.default must be channel:<name> or peer:<name>, not {default!r}")
        by_family = dict(data.get("by_family") or {})
        by_alert = dict(data.get("by_alertname") or {})
        for f in by_family:
            if f not in families:
                raise ValueError(f"routing.by_family: unknown class family {f!r} (known: {sorted(families)})")
        for where, mapping in (("by_family", by_family), ("by_alertname", by_alert)):
            for k, v in mapping.items():
                if not isinstance(v, str) or not TARGET.match(v):
                    raise ValueError(f"routing.{where}.{k} must be channel:<name> or peer:<name>, not {v!r}")
        return cls(default=default, by_family=by_family, by_alertname=by_alert)

    def target(self, family: str | None, alertname: str | None) -> str:
        if alertname and alertname in self.by_alertname:
            return self.by_alertname[alertname]
        if family and family in self.by_family:
            return self.by_family[family]
        return self.default
