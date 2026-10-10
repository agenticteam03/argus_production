"""What this process would really load about writes (T-0031, ARCHITECTURE §22.2 deployment check).

`python -m argus.infrastructure.gate_report` prints one line and exits 0 only when nothing can write:
    gate_open=<n> write_capabilities=<n> action_gateway_resolves=<0|1> policy=<version>
It reads the policy file and the catalogue the way `wiring.build` does, but without the startup refusal, so an open
gate is reported instead of hidden behind a crash. Read-only; ops/write-gate-check.sh runs it in each container.
"""
from __future__ import annotations

import hashlib
import os
import socket
from pathlib import Path

import yaml

from argus.capabilities.catalog import build_catalog

READ_ONLY = {"READ_ONLY_SAFE", "READ_ONLY_SENSITIVE"}
ACTION_GATEWAY = "argus-v18-action-gateway"          # the §13.3 action gateway's name on the core network


def _resolves(name: str) -> bool:
    try:
        socket.getaddrinfo(name, None)
        return True
    except OSError:
        return False


def report(config_dir: Path) -> tuple[bool, str]:
    text = (config_dir / "policy.yaml").read_text(encoding="utf-8")
    gate_open = len((yaml.safe_load(text).get("write_gate") or {}).get("open") or [])
    writes = [s.name for s in build_catalog() if s.safety_class not in READ_ONLY]
    resolves = _resolves(ACTION_GATEWAY)
    line = (f"gate_open={gate_open} write_capabilities={len(writes)} action_gateway_resolves={int(resolves)} "
            f"policy={hashlib.sha256(text.encode()).hexdigest()[:12]}")
    return gate_open == 0 and not writes and not resolves, line


def main() -> int:
    closed, line = report(Path(os.getenv("ARGUS_CONFIG_DIR", "config")))
    print(line)
    return 0 if closed else 1


if __name__ == "__main__":
    raise SystemExit(main())
