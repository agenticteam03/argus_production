"""ACR-0011 (T-0016 step 4c): the UI edge's Nginx configuration (deploy/ui/nginx/).

Static: the API routes Nginx lets through are exactly the routes and methods of contracts/ui-api.json.
With Docker (skipped without it): the real Nginx image runs the loopback configuration next to a fake
`argus-v18-agent`, and a curl matrix checks what passes, what is refused, the runbooks' token check, the headers, and
that a browser cannot forge the edge's own headers.
"""
from __future__ import annotations

import http.client
import json
import re
import shutil
import subprocess
import time
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NGINX_DIR = ROOT / "deploy" / "ui" / "nginx"
CONTRACT = json.loads((ROOT / "contracts" / "ui-api.json").read_text(encoding="utf-8"))
NGINX_IMAGE = "nginxinc/nginx-unprivileged:1.27.5-alpine3.21"     # the Dockerfile's base, kept equal by a test


# --- static: the allowlist is the contract -------------------------------------------------------------------------
def nginx_api_routes() -> set[tuple[str, str]]:
    """(method, OpenAPI path) for every API location that proxies, from locations.conf."""
    text = (NGINX_DIR / "locations.conf").read_text(encoding="utf-8")
    routes = set()
    for m in re.finditer(r"location\s+(=|~)\s+(\S+)\s*\{", text):
        kind, loc = m.groups()
        depth, i = 1, m.end()
        while depth:                                    # the block's body, nested braces included
            depth += {"{": 1, "}": -1}.get(text[i], 0)
            i += 1
        body = text[m.end():i - 1]
        if "proxy.conf" not in body:
            continue
        method = re.search(r"limit_except\s+(\w+)", body).group(1)
        path = loc if kind == "=" else (loc.strip("^$")
                                        .replace("incidents/[A-Za-z0-9_-]+/events", "incidents/{incident_id}/events")
                                        .replace("incidents/[A-Za-z0-9_-]+", "incidents/{incident_id}")
                                        .replace("evidence/[A-Za-z0-9_-]+", "evidence/{evidence_id}"))
        routes.add((method, path))
    return routes


def test_the_edge_proxies_exactly_the_routes_and_methods_of_the_ui_contract():
    contract = {(method.upper(), path) for path, ops in CONTRACT["paths"].items() for method in ops}
    assert nginx_api_routes() == contract


def test_everything_else_under_api_and_swagger_is_404_at_the_edge():
    text = (NGINX_DIR / "locations.conf").read_text(encoding="utf-8")
    for loc in ("location /api/ { return 404; }", "location = /docs", "location = /openapi.json"):
        assert loc in text
    code = lambda f: "\n".join(ln.split("#")[0] for ln in (NGINX_DIR / f).read_text(encoding="utf-8").splitlines())
    assert ":8001" not in code("locations.conf") + code("http.conf") + code("proxy.conf")   # never the webhook


def test_the_edge_overwrites_its_own_headers_on_every_proxied_request():
    proxy = (NGINX_DIR / "proxy.conf").read_text(encoding="utf-8")
    for h in ("X-Argus-Edge $argus_edge", "X-Real-IP $remote_addr", "X-Forwarded-For $remote_addr"):
        assert f"proxy_set_header {h}" in proxy


def test_the_dockerfile_uses_the_tested_nginx_image_and_a_real_mode_build():
    df = (ROOT / "deploy" / "ui" / "Dockerfile").read_text(encoding="utf-8")
    assert f"FROM {NGINX_IMAGE}" in df and "ENV VITE_ARGUS_MOCK=0" in df


# --- with Docker: the real Nginx, a fake API ------------------------------------------------------------------------
FAKE_API = r'''
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
class H(BaseHTTPRequestHandler):
    def _send(self, code, body):
        b = json.dumps(body).encode(); self.send_response(code)
        self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b)))
        self.end_headers(); self.wfile.write(b)
    def _echo(self):
        auth = self.headers.get("Authorization", "")
        if self.path.startswith("/api/v1/me") and auth != "Bearer good":
            return self._send(401, {"detail": "no"})
        self._send(200, {"path": self.path, "method": self.command, "edge": self.headers.get("X-Argus-Edge"),
                         "real_ip": self.headers.get("X-Real-IP"), "xff": self.headers.get("X-Forwarded-For")})
    do_GET = do_POST = do_DELETE = do_PUT = _echo
    def log_message(self, *a): pass
HTTPServer(("0.0.0.0", 8000), H).serve_forever()
'''


def _docker_ready() -> bool:
    if not shutil.which("docker"):
        return False
    return subprocess.run(["docker", "info"], capture_output=True).returncode == 0


@pytest.fixture(scope="module")
def edge(tmp_path_factory):
    if not _docker_ready():
        pytest.skip("needs Docker (the real Nginx image)")
    tag = uuid.uuid4().hex[:8]
    net, api, web = f"argus-edge-test-{tag}", "argus-v18-agent", f"argus-edge-web-{tag}"
    site = tmp_path_factory.mktemp("site")
    (site / "html").mkdir()
    (site / "html" / "index.html").write_text("<!doctype html><title>Argus</title>", encoding="utf-8")
    (site / "runbooks").mkdir()
    (site / "runbooks" / "index.json").write_text('["RB-001-x.md"]', encoding="utf-8")
    (site / "runbooks" / "RB-001-x.md").write_text("# RB-001", encoding="utf-8")
    conf = tmp_path_factory.mktemp("conf")
    (conf / "default.conf").write_text((NGINX_DIR / "loopback.conf.template").read_text(encoding="utf-8"),
                                       encoding="utf-8")
    # pytest's temporary directories are 0700 for the runner's user; Nginx runs as uid 101 in the container and must
    # read the mounted files (on Linux CI an unreadable conf.d means no server block and nothing on 8080)
    for d in (site, site / "html", site / "runbooks", conf):
        d.chmod(0o755)
        for f in d.iterdir():
            if f.is_file():
                f.chmod(0o644)
    run = lambda *a: subprocess.run(["docker", *a], capture_output=True, text=True, timeout=300)
    run("network", "create", net)
    apis = []

    def start_api():
        name = f"{api}-{tag}-{len(apis)}"
        run("run", "-d", "--name", name, "--network", net, "--network-alias", api, "python:3.12-alpine",
            "python", "-c", FAKE_API)
        apis.append(name)

    def recreate_api():
        """The agent recreated by a deployment: a new container (a new address) under the same name, then the old one
        removed, so Docker cannot hand the old address back."""
        old = apis[-1]
        start_api()
        run("rm", "-f", old)
        time.sleep(2)                                   # the new fake API listening

    start_api()
    r = run("run", "-d", "--name", web, "--network", net, "-p", "127.0.0.1::8080",
            "-v", f"{NGINX_DIR}:/etc/nginx/argus:ro", "-v", f"{conf}:/etc/nginx/conf.d:ro",
            "-v", f"{site / 'html'}:/usr/share/nginx/html:ro", "-v", f"{site / 'runbooks'}:/usr/share/nginx/runbooks:ro",
            NGINX_IMAGE)
    try:
        assert r.returncode == 0, r.stderr
        port = run("port", web, "8080").stdout.split(":")[-1].strip()
        base = f"http://127.0.0.1:{port}"
        for _ in range(60):
            try:
                if curl(base, "/healthz")[0] == 200:
                    break
            except OSError:
                pass
            time.sleep(1)
        else:
            pytest.fail("nginx did not start: " + run("logs", web).stderr[-2000:])
        yield base, run, web, recreate_api
    finally:
        run("rm", "-f", web, *apis)
        run("network", "rm", net)


def curl(base, path, method="GET", headers=None, data=None):
    """(status, the response headers as lower-case `name: value` lines, the body)."""
    host, port = base.removeprefix("http://").split(":")
    c = http.client.HTTPConnection(host, int(port), timeout=30)
    hdrs = dict(headers or {})
    if data is not None:
        hdrs.setdefault("Content-Type", "application/x-www-form-urlencoded")
    c.request(method, path, body=data, headers=hdrs)
    r = c.getresponse()
    head = "\n".join(f"{k}: {v}" for k, v in r.getheaders()).lower()
    body = r.read().decode("utf-8", "replace")
    c.close()
    return r.status, head, body


def test_nginx_accepts_the_configuration(edge):
    _, run, web, _ = edge
    r = run("exec", web, "nginx", "-t")
    assert r.returncode == 0, r.stderr


@pytest.mark.parametrize("method, path, code", [
    ("GET", "/api/v1/me", 200), ("GET", "/api/v1/incidents?limit=30", 200), ("GET", "/api/v1/incidents/inc_1", 200),
    ("GET", "/api/v1/incidents/inc_1/events?after=0", 200), ("GET", "/api/v1/evidence/ev_1", 200),
    ("GET", "/api/v1/escalations", 200), ("POST", "/api/v1/auth/token", 200),
    ("POST", "/api/v1/investigations", 200), ("GET", "/api/v1/targets", 200),   # ACR-0012
    ("GET", "/api/v1/investigations", 403), ("DELETE", "/api/v1/incidents/inc_1", 403),
    ("POST", "/api/v1/me", 403), ("GET", "/api/v1/auth/token", 403), ("GET", "/docs", 404),
    ("GET", "/openapi.json", 404), ("GET", "/api/v1/approvals", 404), ("GET", "/metrics", 200),
])
def test_what_passes_and_what_is_refused(edge, method, path, code):
    base, _, _, _ = edge
    status, _, body = curl(base, path, method=method, headers={"Authorization": "Bearer good"},
                           data="username=a&password=b&scope=read" if method == "POST" else None)
    assert status == code
    if path == "/metrics":                      # not proxied: the SPA's index.html, never Argus's metrics
        assert "<title>Argus</title>" in body


def test_a_browser_cannot_forge_the_edge_headers(edge):
    base, _, _, _ = edge
    _, _, body = curl(base, "/api/v1/me", headers={"Authorization": "Bearer good", "X-Argus-Edge": "",
                                                   "X-Real-IP": "198.51.100.99", "X-Forwarded-For": "198.51.100.99"})
    seen = json.loads(body)
    assert seen["edge"] == "public" and seen["real_ip"] != "198.51.100.99" and seen["xff"] != "198.51.100.99"


def test_the_runbooks_need_a_token_that_passes_api_me(edge):
    base, _, _, _ = edge
    assert curl(base, "/runbooks/index.json")[0] == 401
    assert curl(base, "/runbooks/RB-001-x.md", headers={"Authorization": "Bearer bad"})[0] == 401
    code, head, body = curl(base, "/runbooks/RB-001-x.md", headers={"Authorization": "Bearer good"})
    assert code == 200 and body == "# RB-001" and "text/markdown" in head
    code, head, body = curl(base, "/runbooks/index.json", headers={"Authorization": "Bearer good"})
    assert code == 200 and json.loads(body) == ["RB-001-x.md"] and "application/json" in head


def test_the_security_headers_are_on_every_answer(edge):
    base, _, _, _ = edge
    for path in ("/", "/incidents/inc_1", "/api/v1/me"):
        _, head, _ = curl(base, path, headers={"Authorization": "Bearer good"})
        for h in ("content-security-policy: default-src 'self'", "x-frame-options: deny",
                  "x-content-type-options: nosniff", "referrer-policy: no-referrer"):
            assert h in head, (path, h)
        assert "server: nginx/" not in head          # server_tokens off


def test_a_burst_of_logins_is_limited(edge):
    base, _, _, _ = edge
    codes = [curl(base, "/api/v1/auth/token", method="POST", data="username=a&password=b&scope=read")[0]
             for _ in range(12)]
    assert 429 in codes and codes[0] == 200


def test_the_edge_follows_a_recreated_agent_without_a_reload(edge):
    """AFTER-MERGE 2026-10-14: recreating argus-v18-agent gave it a new address and the public edge answered 502 until
    `nginx -s reload` (Nginx had resolved the name once, at start). The upstream re-resolves through Docker's DNS."""
    base, _, _, recreate_api = edge
    assert curl(base, "/api/v1/me", headers={"Authorization": "Bearer good"})[0] == 200
    recreate_api()
    codes = []
    for _ in range(20):                              # within the resolver's validity (a few seconds)
        codes.append(curl(base, "/api/v1/me", headers={"Authorization": "Bearer good"})[0])
        if codes[-1] == 200:
            break
        time.sleep(1)
    assert codes[-1] == 200, codes


def test_a_burst_of_investigations_is_limited_per_address(edge):
    """ACR-0012: about 6 a minute per address (burst 2) at the edge; the API's per-principal quotas come on top."""
    base, _, _, _ = edge
    codes = [curl(base, "/api/v1/investigations", method="POST", headers={"Authorization": "Bearer good"},
                  data='{"target": "vm-166/container:argus-lab-api", "reason": "x"}')[0] for _ in range(6)]
    assert codes[0] == 200 and 429 in codes


def test_an_oversized_investigation_request_is_refused_at_the_edge(edge):
    base, _, _, _ = edge
    assert curl(base, "/api/v1/investigations", method="POST", headers={"Authorization": "Bearer good"},
                data="x" * 5000)[0] == 413
