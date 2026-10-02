"""Phase 3 check (stdlib). Runs on vm-095 INSIDE the argus-v18-core network, with the agent's tokens:
  docker run --rm --network argus-v18-core -v /opt/argus-v18/secrets/agent:/s:ro \
             -v /opt/argus-v18/app/ops/phase3_check.py:/c.py:ro python:3.12-alpine python /c.py
Proves for BOTH hosts: services reachable through the inventory endpoints, correct host attribution,
exact routes, allowlists, token checks, read-only, Prometheus labelled with argus_host.
"""
import json
import urllib.error
import urllib.request

HOSTS = {
    "vm-095": {"docker_read": "http://argus-v18-read-gateway:8700", "host_probe": "http://argus-v18-host-probe:8700",
               "network_probe": "http://argus-v18-network-probe:8700", "prometheus": "http://argus-v18-prometheus:9090"},
    "vm-166": {"docker_read": "http://argus-v18-tunnel:18701", "host_probe": "http://argus-v18-tunnel:18702",
               "network_probe": "http://argus-v18-tunnel:18703", "prometheus": "http://argus-v18-tunnel:18090"},
}
results = []


def call(url, token=None, method="GET"):
    req = urllib.request.Request(url, method=method)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except ValueError:
            return e.code, {}
    except Exception as e:
        return 0, {"error": f"{type(e).__name__}: {e}"}


def check(host, name, ok, detail=""):
    results.append((host, name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {host:7} {name:52} {detail}")


for host, ep in HOSTS.items():
    tok = {ex: open(f"/s/{host}/{ex}_token").read().strip() for ex in ("docker_read", "host_probe", "network_probe")}
    g, h, n = ep["docker_read"], ep["host_probe"], ep["network_probe"]

    c, d = call(f"{g}/containers", tok["docker_read"])
    check(host, "read gateway: list in-scope containers", c == 200 and d.get("host") == host,
          f"{c} host={d.get('host')} {[x['name'] + '=' + x['state'] for x in d.get('containers', [])]}")
    c, d = call(f"{g}/containers/argus-lab-api/status", tok["docker_read"])
    check(host, "read gateway: status of argus-lab-api (baseline)", c == 200 and d.get("host") == host,
          f"{c} state={d.get('state')} health={d.get('health')} id={d.get('id')}")
    check(host, "read gateway: no Env in the answer", "Env" not in json.dumps(d) and "env" not in d)
    c, _ = call(f"{g}/containers/argus-lab-api/exec", tok["docker_read"])
    check(host, "read gateway: /exec route does not exist (404)", c == 404, str(c))
    c, _ = call(f"{g}/containers/argus-v18-read-gateway/status", tok["docker_read"])
    check(host, "read gateway: container outside allowlist (404)", c == 404, str(c))
    c, _ = call(f"{g}/containers", "wrong-token")
    check(host, "read gateway: wrong token (401)", c == 401, str(c))
    c, _ = call(f"{g}/containers", tok["docker_read"], method="POST")
    check(host, "read gateway: POST refused (405, read-only)", c == 405, str(c))
    c, _ = call(f"{g}/containers", tok["host_probe"])
    check(host, "read gateway: another service's token refused (401)", c == 401, str(c))

    c, d = call(f"{h}/memory", tok["host_probe"])
    check(host, "host probe: memory", c == 200 and d.get("host") == host,
          f"{c} total={d.get('total_mib')} MiB available={d.get('available_mib')} MiB")
    c, d = call(f"{h}/cpu", tok["host_probe"])
    check(host, "host probe: cpu", c == 200 and d.get("host") == host, f"{c} busy={d.get('cpu_busy_percent')}% cpus={d.get('cpus')}")
    c, _ = call(f"{h}/disk?mount=/etc", tok["host_probe"])
    check(host, "host probe: mount outside allowlist (400)", c == 400, str(c))

    c, d = call(f"{n}/dns?name=argus-lab-api", tok["network_probe"])
    check(host, "network probe: dns argus-lab-api on argus-lab-app", c == 200 and d.get("ok") is True, f"{c} {d.get('addresses')}")
    c, _ = call(f"{n}/tcp?host=example.com&port=443", tok["network_probe"])
    check(host, "network probe: non-allowlisted target (400)", c == 400, str(c))

    c, d = call(f"{ep['prometheus']}/api/v1/query?query=argus_container_running")
    series = d.get("data", {}).get("result", []) if isinstance(d, dict) else []
    labels = sorted({s["metric"].get("argus_host") for s in series})
    check(host, "prometheus: series exist and carry argus_host", c == 200 and labels == [host],
          f"{c} argus_host={labels} containers={sorted(s['metric'].get('container') for s in series)}")

passed = sum(ok for *_, ok in results)
print(f"\n{passed}/{len(results)} checks passed")
