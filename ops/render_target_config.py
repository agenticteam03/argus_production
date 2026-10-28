"""Render each host's target-side allowlist FROM THE INVENTORY (single source: policy and gateway ACLs
cannot drift apart). T-0019 batch 3a: plus that host's part of the inspection policy (config/policy.yaml, §4.7). Writes deploy/target/config/<host>.json. Run after editing config/inventory.yaml."""
from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT                                   # where `argus` is imported from (tests move ROOT)
PROTOCOLS = {"redis"}                         # the protocol probes services/target/service.py has (PROTOCOL_PROBES)


def _inspection(host: str) -> dict:
    """T-0019 batch 3a: this host's part of the inspection policy (§4.7, config/policy.yaml); the probe re-checks it."""
    import sys
    sys.path.insert(0, str(REPO))
    from argus.policy.inspection import InspectionPolicy
    pol = yaml.safe_load((ROOT / "config" / "policy.yaml").read_text(encoding="utf-8"))
    return InspectionPolicy.from_data(pol.get("inspection")).for_host(host)


def render_host(inv: dict, host: str) -> dict:
    targets = inv.get("targets", [])
    mine = [t for t in targets if t["ref"].startswith(f"{host}/")]
    containers = [t["ref"].split(":", 1)[1] for t in mine if "/container:" in t["ref"]]
    mounts = sorted({m for t in mine if "/host:" in t["ref"] for m in t.get("mounts", [])})
    tcp = [[t["ref"].split(":", 1)[1], p] for t in mine for p in t.get("tcp_ports", [])]
    http = [u for t in mine for u in t.get("http_endpoints", [])]
    # T-0029: the exporter probes every declared endpoint of a container target (its owner) through the app network
    http_probes = [{"owner": t["ref"].split(":", 1)[1], "url": u} for t in mine if "/container:" in t["ref"]
                   for u in t.get("http_endpoints", [])]
    probes = []
    for t in mine:
        owner = t["ref"].split(":", 1)[1]
        for dep in t.get("depends_on", []):
            ref = dep["ref"] if isinstance(dep, dict) else dep        # ACR-0025: a ref or {ref, port, required}
            dname = ref.split(":", 1)[1]
            dinfo = next((x for x in targets if x["ref"] == ref), {})
            declared = dep.get("port") if isinstance(dep, dict) else None
            protocol = dinfo.get("protocol")          # the probe asks the protocol, not only TCP (RB-003 Recovery)
            if protocol is not None and protocol not in PROTOCOLS:
                raise ValueError(f"{ref}: protocol {protocol!r} has no probe (known: {sorted(PROTOCOLS)})")
            for port in [declared] if declared is not None else dinfo.get("tcp_ports", []):
                probes.append({"owner": owner, "dependency": dname, "host": dname, "port": port,
                               **({"protocol": protocol} if protocol else {})})
    # db-probe allowlist: a container target with a `database`, reached by its container name on the app network
    databases = [{"name": t["ref"].split(":", 1)[1], "host": t["ref"].split(":", 1)[1], "port": t["database"]["port"],
                  "dbname": t["database"]["dbname"]} for t in mine if "/container:" in t["ref"] and t.get("database")]
    return {"host": host, "containers": containers, "dns_names": containers, "tcp": tcp,
            "http_endpoints": http, "http_probes": http_probes, "probes": probes, "mounts": mounts, "databases": databases,
            "inspection": _inspection(host)}


def main() -> None:
    inv = yaml.safe_load((ROOT / "config" / "inventory.yaml").read_text(encoding="utf-8"))
    out_dir = ROOT / "deploy" / "target" / "config"
    out_dir.mkdir(parents=True, exist_ok=True)
    for host in inv["hosts"]:
        cfg = render_host(inv, host)
        (out_dir / f"{host}.json").write_bytes((json.dumps(cfg, indent=2) + "\n").encode("utf-8"))  # LF always
        print(f"{host}: {len(cfg['containers'])} containers, {len(cfg['probes'])} probes, mounts {cfg['mounts']}, "
              f"databases {[d['name'] for d in cfg['databases']]}")


if __name__ == "__main__":
    main()
