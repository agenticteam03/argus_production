"""What this process would really load about writes (T-0031, ARCHITECTURE §22.2 deployment check).

`python -m argus.infrastructure.gate_report` prints one line and exits 0 only when the gate holds exactly what was
reviewed:
    gate_open=<n> write_capabilities=<n> action_gateway_resolves=<0|1> policy=<version> released_ok=<0|1>
`released_ok=1` means the pairs of `write_gate.open` equal the pairs of the release file
(`deploy/action_gateway/first-lab-release.candidate.json`, or the JSON in ARGUS_RELEASE_JSON, or the file named by
ARGUS_RELEASE_FILE), every pair matches the lab rule, no write capability exists beyond the released capabilities,
and the action gateway name resolves only when something is released. Without a release file the released set is
empty, so any gate entry fails. An empty gate with an empty release passes, as before. It reads the policy file and
the catalogue the way `wiring.build` does, but without the startup refusal, so a wrong gate is reported instead of
hidden behind a crash. Read-only; ops/write-gate-check.sh runs it in each container.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import socket
from pathlib import Path

import yaml

from argus.capabilities.catalog import build_catalog

READ_ONLY = {"READ_ONLY_SAFE", "READ_ONLY_SENSITIVE"}
ACTION_GATEWAY = "argus-v18-action-gateway"          # the §13.3 action gateway's name on the core network
LAB_TARGET = re.compile(r"vm-166/container:argus-lab-[A-Za-z0-9_.-]+")     # the policy engine's lab rule
# The repository copy, when run from a checkout. ops/write-gate-check.sh pipes this file into a container's python
# (`python - <file`, so __file__ is "<stdin>") and passes the release as ARGUS_RELEASE_JSON instead.
_HERE = Path(__file__).resolve()
RELEASE_FILE = (_HERE.parents[2] if len(_HERE.parents) > 2 else _HERE.parent) / "deploy/action_gateway/first-lab-release.candidate.json"


def _resolves(name: str) -> bool:
    try:
        socket.getaddrinfo(name, None)
        return True
    except OSError:
        return False


def released_pairs() -> list[tuple[str, str]] | None:
    """The reviewed pairs of the release file; [] when there is none; None when it is unreadable or malformed."""
    text = os.getenv("ARGUS_RELEASE_JSON")
    if text is None:
        path = Path(os.getenv("ARGUS_RELEASE_FILE") or RELEASE_FILE)
        if not path.is_file():
            return []
        text = path.read_text(encoding="utf-8")
    try:
        rows = json.loads(text)["released"]
        return [(row["capability"], row["target"]) for row in rows]
    except (ValueError, KeyError, TypeError):
        return None


def _gate_pairs(raw: object) -> list[tuple[str, str]] | None:
    if not isinstance(raw, list) or not all(isinstance(r, dict) and set(r) == {"capability", "target"} for r in raw):
        return None
    return [(r["capability"], r["target"]) for r in raw]


def report(config_dir: Path) -> tuple[bool, str]:
    text = (config_dir / "policy.yaml").read_text(encoding="utf-8")
    raw = (yaml.safe_load(text).get("write_gate") or {}).get("open") or []
    pairs, released = _gate_pairs(raw), released_pairs()
    writes = [s.name for s in build_catalog() if s.safety_class not in READ_ONLY]
    resolves = _resolves(ACTION_GATEWAY)
    in_order = (pairs is not None and released is not None and len(set(pairs)) == len(pairs)
                and set(pairs) == set(released) and all(LAB_TARGET.fullmatch(t) for _, t in pairs))
    ok = (in_order and set(writes) <= {c for c, _ in pairs} and (not resolves or bool(pairs)))
    line = (f"gate_open={len(raw) if isinstance(raw, list) else 1} write_capabilities={len(writes)} "
            f"action_gateway_resolves={int(resolves)} policy={hashlib.sha256(text.encode()).hexdigest()[:12]} "
            f"released_ok={int(ok)}")
    return ok, line


def main() -> int:
    ok, line = report(Path(os.getenv("ARGUS_CONFIG_DIR", "config")))
    print(line)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
