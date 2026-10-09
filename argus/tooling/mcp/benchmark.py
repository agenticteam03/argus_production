"""T-0021 step 5 (ARCHITECTURE §25 OD-3): what the MCP tools process adds to one read.

    docker exec -u argus-tools argus-v18-worker python -m argus.tooling.mcp.benchmark [N] [TARGET] [CAPABILITY]

Read-only. It runs as argus-tools, the only user that can read the executor tokens, so the same read can go both
ways: in-process through the dispatcher (`direct`) and through a tools process over stdio (`mcp`). The two
alternate, so both see the same target load. One warm-up pair is not measured (the child's start is a one-off cost
per worker, not per call). Prints p50/p95 of each way and of the per-pair overhead; the last line is OD-3 OK (p95
overhead below 100 ms, every read ok) or OD-3 STOP.
"""
from __future__ import annotations

import math
import os
import sys
import time

from argus.infrastructure.wiring import Settings, tools_dispatcher
from argus.tooling.mcp.client import child_client
from argus.tooling.mcp.tools_server import handle

LIMIT_MS = 100.0


def _pct(values: list[float], p: float) -> float:
    s = sorted(values)
    return s[max(0, math.ceil(p * len(s)) - 1)]


def report(direct_ms: list[float], mcp_ms: list[float], not_ok: int,
           limit_ms: float = LIMIT_MS) -> tuple[list[str], bool]:
    overhead = [m - d for d, m in zip(direct_ms, mcp_ms)]
    lines = [f"{name:<9}p50 {_pct(v, 0.5):7.1f} ms   p95 {_pct(v, 0.95):7.1f} ms"
             for name, v in (("direct", direct_ms), ("mcp", mcp_ms), ("overhead", overhead))]
    lines.append(f"pairs: {len(overhead)}   not ok: {not_ok}   budget: p95 overhead < {limit_ms:.0f} ms")
    return lines, not_ok == 0 and _pct(overhead, 0.95) < limit_ms


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    n = int(argv[0]) if argv else 30
    target = argv[1] if len(argv) > 1 else "vm-095/container:argus-lab-api"
    capability = argv[2] if len(argv) > 2 else "container.status"
    s = Settings()
    specs, dispatcher, inventory = tools_dispatcher(s)
    published = {sp.name: sp for sp in specs if sp.runs_in == "tools_child" and sp.permission == "read"}
    arguments = {"target": target, "args": {}}
    env = {"ARGUS_CONFIG_DIR": str(s.config_dir.resolve()), "ARGUS_SECRETS_DIR": str(s.secrets_dir)}
    if os.getenv("PYTHONPATH"):
        env["PYTHONPATH"] = os.environ["PYTHONPATH"]
    client = child_client(env)
    direct_ms: list[float] = []
    mcp_ms: list[float] = []
    not_ok = 0
    try:
        for i in range(n + 1):
            t = time.perf_counter()
            d = handle(published, dispatcher, inventory, capability, arguments)
            t_direct = (time.perf_counter() - t) * 1000
            t = time.perf_counter()
            m = client.call(capability, target, {})
            t_mcp = (time.perf_counter() - t) * 1000
            if i == 0:                                     # warm-up: starts the tools process
                continue
            direct_ms.append(t_direct)
            mcp_ms.append(t_mcp)
            not_ok += (d.status != "ok") + (getattr(m, "status", "refused") != "ok")
    finally:
        client.close()
    print(f"OD-3 benchmark: {capability} on {target}")
    lines, ok = report(direct_ms, mcp_ms, not_ok)
    print("\n".join(lines))
    print("OD-3 OK" if ok else "OD-3 STOP")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
