"""T-0021: prove the credential isolation of ARCHITECTURE §12.6 from inside the worker container, as its user.

    docker exec argus-v18-worker python -m argus.tooling.isolation_check

Read-only. The last line is TOOLS ISOLATION OK or TOOLS ISOLATION STOP. Checks: this user can read none of the
executor tokens the inventory names; sudo lets it start the tools-server launcher as argus-tools and nothing else (no `cat` of a token,
no arguments to the launcher, no root); the launcher does not run an `argus` package planted in the caller's working
folder; the tools process starts and lists its read capabilities.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from argus.adapters.outbound.config_adapters import YamlInventory
from argus.infrastructure.wiring import Settings


def _readable(path) -> bool:
    try:
        with open(path, "rb") as f:
            f.read(1)
        return True
    except OSError:
        return False


def _sudo_refused(cmd: list[str]) -> bool:
    try:
        r = subprocess.run(["sudo", "-n", *cmd], stdin=subprocess.DEVNULL, capture_output=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return True
    return r.returncode != 0


PLANTED = "ARGUS-PLANTED-CODE-RAN"


def _planted_code_runs(cmd: list[str]) -> bool:
    """Start the launcher from a folder holding a fake `argus` package. sudo keeps the working folder; a launcher that
    lets Python look there runs the fake package as argus-tools (it prints PLANTED). Readable by argus-tools, so the
    probe would see the hole if it were there. The real tools server just exits: stdin is closed."""
    folder = Path(tempfile.mkdtemp(prefix="argus-plant-"))
    try:
        (folder / "argus").mkdir()
        (folder / "argus" / "__init__.py").write_text(f"print({PLANTED!r}, flush=True)\nraise SystemExit(0)\n",
                                                     encoding="utf-8")
        for path, mode in ((folder, 0o755), (folder / "argus", 0o755), (folder / "argus" / "__init__.py", 0o644)):
            os.chmod(path, mode)
        try:
            r = subprocess.run(cmd, cwd=folder, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30)
            out = r.stdout + r.stderr
        except subprocess.TimeoutExpired as e:
            out = str(e.stdout or "") + str(e.stderr or "")
        return PLANTED in out
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def main() -> int:
    s = Settings()
    results: list[tuple[bool, str, str]] = []
    # From the inventory, not a listing: the token folders belong to argus-tools, so this user cannot list them.
    # Their presence is proved by the tools process starting below (it refuses to start without every token).
    inventory = YamlInventory((s.config_dir / "inventory.yaml").read_text(encoding="utf-8"))
    tokens = [s.secrets_dir / h.name / f"{ex}_token" for h in inventory.hosts() for ex in h.executors
              if ex != "prometheus"]
    readable = [str(t) for t in tokens if _readable(t)]
    results.append((bool(tokens) and not readable, "this user cannot read any executor token",
                    ", ".join(readable) or f"none readable ({len(tokens)} expected by the inventory)"))
    cmd = s.tools_command
    launcher = len(cmd) >= 4 and cmd[0] == "sudo"
    results.append((launcher, "the tools process starts through the sudo launcher", " ".join(cmd) or "(not set)"))
    if launcher and tokens:
        for probe in (["-u", "argus-tools", "/bin/cat", str(tokens[0])], [*cmd[2:], "extra-argument"], ["true"]):
            results.append((_sudo_refused(probe), "sudo refuses", " ".join(probe)))
    if launcher:
        try:
            planted, detail = _planted_code_runs(cmd), ""
        except OSError as e:        # cannot write the probe folder: unproven, so not ok
            planted, detail = True, f"probe not run: {e!r}"[:200]
        results.append((not planted, "the launcher ignores code planted in the caller's folder", detail or (
            "the fake argus package RAN as argus-tools" if planted else "the fake argus package did not run")))
        from argus.tooling.mcp.client import child_client
        client = child_client({}, cmd, timeout_s=60)
        try:
            names = client.list_names()
            results.append((bool(names), "the tools process starts (it needs every token) and lists its reads",
                            f"{len(names)} capabilities"))
        except Exception as e:      # noqa: BLE001 - reported, never raised
            results.append((False, "the tools process starts (it needs every token) and lists its reads",
                            repr(e)[:200]))
        finally:
            client.close()
    for ok, what, detail in results:
        print(f"{'ok  ' if ok else 'FAIL'} {what}: {detail}")
    ok = all(r[0] for r in results)
    print("TOOLS ISOLATION OK" if ok else "TOOLS ISOLATION STOP")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
