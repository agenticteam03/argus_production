"""Render each host's target-side allowlist FROM THE INVENTORY (single source: policy and gateway ACLs
cannot drift apart). Writes deploy/target/config/<host>.json. Run after editing config/inventory.yaml."""
from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    inv = yaml.safe_load((ROOT / "config" / "inventory.yaml").read_text(encoding="utf-8"))
    out_dir = ROOT / "deploy" / "target" / "config"
    out_dir.mkdir(parents=True, exist_ok=True)
    targets = inv.get("targets", [])
    for host in inv["hosts"]:
        mine = [t for t in targets if t["ref"].startswith(f"{host}/")]
        containers = [t["ref"].split(":", 1)[1] for t in mine if "/container:" in t["ref"]]
        mounts = sorted({m for t in mine if "/host:" in t["ref"] for m in t.get("mounts", [])})
        tcp = [[t["ref"].split(":", 1)[1], p] for t in mine for p in t.get("tcp_ports", [])]
        http = [u for t in mine for u in t.get("http_endpoints", [])]
        probes = []
        for t in mine:
            owner = t["ref"].split(":", 1)[1]
            for dep in t.get("depends_on", []):
                dname = dep.split(":", 1)[1]
                dinfo = next((x for x in targets if x["ref"] == dep), {})
                for port in dinfo.get("tcp_ports", []):
                    probes.append({"owner": owner, "dependency": dname, "host": dname, "port": port})
        cfg = {"host": host, "containers": containers, "dns_names": containers, "tcp": tcp,
               "http_endpoints": http, "probes": probes, "mounts": mounts}
        (out_dir / f"{host}.json").write_bytes((json.dumps(cfg, indent=2) + "\n").encode("utf-8"))  # LF always
        print(f"{host}: {len(containers)} containers, {len(probes)} probes, mounts {mounts}")


if __name__ == "__main__":
    main()
