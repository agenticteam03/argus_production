"""Generate Argus v1.8 tokens into deploy/secrets/<host>/ (gitignored). Existing files are kept.

deploy/secrets/vm-166/            docker_read_token, host_probe_token, network_probe_token  (vm-166 services)
deploy/secrets/vm-095/            the same for vm-095's own services
deploy/secrets/vm-095/agent/      <host>/<executor>_token for BOTH hosts + jwt_signing_key   (the agent's copy)
"""
from __future__ import annotations

import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "deploy" / "secrets"
EXECUTORS = ("docker_read", "host_probe", "network_probe")


def put(p: Path, value: str) -> str:
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        p.write_text(value, encoding="utf-8")
    return p.read_text(encoding="utf-8")


def main() -> None:
    for host in ("vm-095", "vm-166"):
        for ex in EXECUTORS:
            tok = put(ROOT / host / f"{ex}_token", secrets.token_urlsafe(32))
            put(ROOT / "vm-095" / "agent" / host / f"{ex}_token", tok)
    put(ROOT / "vm-095" / "agent" / "jwt_signing_key", secrets.token_urlsafe(48))
    for f in sorted(ROOT.rglob("*")):
        if f.is_file():
            print(f.relative_to(ROOT))


if __name__ == "__main__":
    main()
