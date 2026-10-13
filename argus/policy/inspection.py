"""Per-target inspection policy (ARCHITECTURE §4.7): what file, log and process reads a target allows.

Imports domain only. The data is the `inspection` section of config/policy.yaml; the probes get each host's part in
their rendered config (ops/render_target_config.py) and re-check it. Fail closed: a target or a kind without an entry
allows nothing, deny patterns win over allow entries, a built-in deny floor applies whatever the data says, and a path
that is not already normal (absolute, no `.`/`..`/empty segment) is refused, never normalized.
"""
from __future__ import annotations

import fnmatch
import posixpath
import re
from dataclasses import dataclass, field

from argus.domain.model import TargetRef

# Always denied, even if the data's deny list leaves them out (credentials, including Argus's own tokens, and kernel
# or Docker state that holds them). A pattern without `/` matches any component of the path, directories included
# (#98 review: `/srv/tokens/x`, `~/.ssh/config`). The probe carries the same tuple (services/target/service.py).
BUILTIN_DENY = ("environment_variables", "/run/secrets/", "/opt/argus-v18/secrets/", "/root/", "/proc/",
                "/var/lib/docker/", "/etc/shadow", "/etc/shadow-", "/etc/gshadow", "/etc/gshadow-", "/etc/sudoers",
                "/etc/sudoers.d/", ".ssh", "id_*", "*.key", "*.pem", ".env", "*.env", "*password*", "*token*")
KEYWORDS = {"environment_variables"}                 # deny entries that name a kind of data, not a path

# capability -> (kind of entry, argument that names what is read)
INSPECTED = {"host.read_file": ("files", "path"), "host.service_config": ("service_config", "path"),
             "host.journal": ("journal", "unit"), "host.process_details": ("processes", "pid")}
TARGET_KEYS = {"files", "service_config", "journal", "processes"}
TOP_KEYS = {"targets", "deny", "limits", "arbitrary_exec"}
UNIT = re.compile(r"^[A-Za-z0-9@_.-]{1,128}$")
MAX_LINES_CAP = 2000


@dataclass(frozen=True)
class Decision:                                      # the engine turns it into a PolicyDecision
    allowed: bool
    reason: str
    rule: str = "inspection"


def _normal(path: object, *, directory_ok: bool) -> str | None:
    """The path itself if it is absolute and already normal, else None (refused)."""
    if not isinstance(path, str) or not path.startswith("/") or "\x00" in path:
        return None
    body = path[:-1] if directory_ok and path.endswith("/") and len(path) > 1 else path
    if posixpath.normpath(body) != body or body.startswith("//"):
        return None
    return path


def _denied(path: str, deny: tuple[str, ...]) -> str | None:
    parts = [p.lower() for p in path.split("/") if p]
    for d in deny:
        if d in KEYWORDS:
            continue
        if d.endswith("/"):
            if (path + "/").startswith(d):
                return d
        elif d.startswith("/"):
            if path == d or fnmatch.fnmatchcase(path, d):
                return d
        elif any(fnmatch.fnmatchcase(p, d.lower()) for p in parts):   # a name pattern: any component, any case
            return d
    return None


@dataclass(frozen=True)
class InspectionPolicy:
    targets: dict[TargetRef, dict] = field(default_factory=dict)
    deny: tuple[str, ...] = BUILTIN_DENY
    limits: dict = field(default_factory=lambda: {"max_lines": 500, "max_bytes": 65536})
    arbitrary_exec: bool = False

    @classmethod
    def from_data(cls, data: dict | None) -> "InspectionPolicy":
        data = data or {}
        if not isinstance(data, dict) or set(data) - TOP_KEYS:
            raise ValueError(f"inspection: unknown keys {sorted(set(data) - TOP_KEYS) if isinstance(data, dict) else data}")
        if data.get("arbitrary_exec", False) is not False:
            raise ValueError("inspection: arbitrary_exec must be false (ARCHITECTURE §4.7)")
        limits = {"max_lines": 500, "max_bytes": 65536, **(data.get("limits") or {})}
        for k, v in limits.items():
            if k not in ("max_lines", "max_bytes") or not isinstance(v, int) or isinstance(v, bool) or v <= 0:
                raise ValueError(f"inspection.limits: bad {k}={v!r}")
        if limits["max_lines"] > MAX_LINES_CAP:
            raise ValueError(f"inspection.limits.max_lines above {MAX_LINES_CAP}")
        deny = list(data.get("deny") or [])
        if not all(isinstance(d, str) and d for d in deny):
            raise ValueError("inspection.deny: non-empty strings only")
        targets: dict[TargetRef, dict] = {}
        for ref, entry in (data.get("targets") or {}).items():
            try:
                target = TargetRef.parse(str(ref))
            except ValueError as e:
                raise ValueError(f"inspection.targets: {ref!r}: {e}") from None
            targets[target] = cls._entry(str(ref), entry or {}, limits["max_lines"])
        return cls(targets=targets, deny=tuple(dict.fromkeys([*BUILTIN_DENY, *deny])), limits=limits,
                   arbitrary_exec=False)

    @staticmethod
    def _entry(ref: str, entry: dict, max_lines: int) -> dict:
        if not isinstance(entry, dict) or set(entry) - TARGET_KEYS:
            raise ValueError(f"inspection.targets.{ref}: unknown keys {sorted(set(entry) - TARGET_KEYS)}")
        out: dict = {}
        for kind in ("files", "service_config"):
            paths = entry.get(kind) or []
            for p in paths:
                if _normal(p, directory_ok=True) is None:
                    raise ValueError(f"inspection.targets.{ref}.{kind}: {p!r} is not an absolute normal path")
            out[kind] = tuple(paths)
        processes = entry.get("processes", False)
        if not isinstance(processes, bool):
            raise ValueError(f"inspection.targets.{ref}.processes must be true or false")
        out["processes"] = processes
        j = entry.get("journal")
        if j is not None:
            units, lines = j.get("units") or [], j.get("max_lines", max_lines)
            if set(j) - {"units", "max_lines"} or not all(isinstance(u, str) and UNIT.match(u) for u in units):
                raise ValueError(f"inspection.targets.{ref}.journal: bad units {units!r}")
            if not isinstance(lines, int) or isinstance(lines, bool) or not 0 < lines <= max_lines:
                raise ValueError(f"inspection.targets.{ref}.journal.max_lines must be 1..{max_lines}")
            out["journal"] = {"units": tuple(units), "max_lines": lines}
        return out

    # --- decisions ------------------------------------------------------------------------------------------------
    def allows(self, target: TargetRef, capability: str, arguments: dict | None) -> Decision:
        if capability not in INSPECTED:
            return Decision(True, "not an inspected capability")
        kind, arg = INSPECTED[capability]
        entry = self.targets.get(target)
        if entry is None:
            return Decision(False, f"{target} has no inspection entry")
        if not isinstance(arguments, dict):
            return Decision(False, f"{capability} needs `{arg}`")
        if kind == "service_config" and arguments.get("path") is None:
            # T-0019 batch 3b: no path = every file listed for this target, and only those (the probe re-checks each)
            return Decision(True, "service_config: the listed files") if entry.get("service_config") else \
                Decision(False, f"no service configuration is allowed on {target}")
        if arg not in arguments:
            return Decision(False, f"{capability} needs `{arg}`")
        value = arguments[arg]
        if kind == "processes":
            return Decision(True, "processes allowed") if entry["processes"] else \
                Decision(False, f"process details are not allowed on {target}")
        if kind == "journal":
            j = entry.get("journal")
            lines = arguments.get("lines")
            if j is None or value not in j["units"]:
                return Decision(False, f"journal unit {value!r} is not allowed on {target}")
            if not isinstance(lines, int) or isinstance(lines, bool) or not 0 < lines <= j["max_lines"]:
                return Decision(False, f"journal lines must be 1..{j['max_lines']}")
            return Decision(True, f"journal {value}")
        path = _normal(value, directory_ok=False)
        if path is None:
            return Decision(False, f"{value!r} is not an absolute normal path")
        hit = _denied(path, self.deny)
        if hit:
            return Decision(False, f"deny pattern {hit!r} matches {path}")
        for allowed in entry.get(kind, ()):
            if path == allowed or (allowed.endswith("/") and path.startswith(allowed)):
                return Decision(True, f"{kind} {allowed}")
        return Decision(False, f"{path} is not in the {kind} allowlist of {target}")

    # --- startup validation and the probes' copy ------------------------------------------------------------------
    def errors_against_inventory(self, inventory: dict) -> list[str]:
        """Every entry is an inventory target; every path lies under a declared mount of its host (the probe reads
        the host's filesystem only through those)."""
        refs = {t["ref"] for t in inventory.get("targets", [])}
        mounts = {t["ref"].split("/", 1)[0]: t.get("mounts", []) for t in inventory.get("targets", [])
                  if "/host:" in t["ref"]}
        errors = []
        for target, entry in self.targets.items():
            if str(target) not in refs:
                errors.append(f"inspection: {target} is not an inventory target")
                continue
            for kind in ("files", "service_config"):
                for p in entry.get(kind, ()):
                    if not any(p == m or p.startswith(m.rstrip("/") + "/") for m in mounts.get(target.host, [])):
                        errors.append(f"inspection: {target} {kind} {p} is not under a declared mount of {target.host}")
        return errors

    def for_host(self, host: str) -> dict:
        targets = {}
        for t, e in self.targets.items():
            if t.host == host:
                row = {k: list(v) if isinstance(v, tuple) else v for k, v in e.items()}
                if "journal" in row:
                    row["journal"] = {"units": list(e["journal"]["units"]), "max_lines": e["journal"]["max_lines"]}
                targets[str(t)] = row
        return {"targets": targets, "deny": list(self.deny), "limits": dict(self.limits), "arbitrary_exec": False}
