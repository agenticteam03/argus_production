"""ACR-0018, phase 16 step 4: the private path. Every privileged route lives under `/api/v1/ops/`; the public edge
passes that prefix only for a client certificate of the team's CA (not revoked; ACR-0037: from any address), and
answers 404 for anything else, as if the route did not exist. ACR-0038: with ARGUS_OPS_PASSKEY_ONLY=on (off by
default) no certificate is needed; any TLS request reaches the prefix and the API's login, two security keys and the
step-up are the proof.

- static: the edge's rule, the two ops-mode files, the allowlist in Git allowing nobody, the private path and the
  passkey-only mode off by default, and every route that needs a privileged permission under the prefix;
- the scripts with bash and openssl: the CA (encrypted key, 90-day client certificates, revocation into the CRL), a
  person's own key and CSR, the allowlist (named entries with an expiry, no address in its log or listing);
- with Docker: the edge's start script choosing the mode, and the real Nginx in public mode with the private path on
  (certificate mode and passkey-only mode), against a fake API.
"""
from __future__ import annotations

import datetime as dt
import http.client
import os
import re
import shutil
import ssl
import subprocess
import time
import uuid

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from argus.adapters.inbound.http import OPS_PREFIX, PRIVILEGED_PERMISSIONS, ROLE_PERMISSIONS, build_api
from test_acr0011_ui_edge import FAKE_API, NGINX_DIR, NGINX_IMAGE, _docker_ready
from test_core import ROOT, make_app  # noqa: F401  (fixture)

UI = ROOT / "deploy" / "ui"
CA_SCRIPT, ALLOW_SCRIPT = ROOT / "ops" / "edge-ca.sh", ROOT / "ops" / "edge-allow.sh"
BASH, OPENSSL = shutil.which("bash"), shutil.which("openssl")
needs_tools = pytest.mark.skipif(not (BASH and OPENSSL), reason="needs bash and openssl")


# --- static ----------------------------------------------------------------------------------------------------------
def test_the_edge_passes_the_prefix_only_on_the_private_path():
    loc = (NGINX_DIR / "locations.conf").read_text(encoding="utf-8")
    block = re.search(r"location \^~ /api/v1/ops/ \{(.*?)\n\}", loc, re.S).group(1)
    assert "if ($argus_ops_ok != 1) { return 404; }" in block and "proxy.conf" in block
    assert loc.index("location ^~ /api/v1/ops/") < loc.index("location /api/ { return 404; }")


def test_the_edge_tells_the_api_whether_a_request_came_through_the_private_path():
    """ACR-0032: every proxied request carries X-Argus-Ops = $argus_ops_ok (1 only on the private path), replacing
    any copy from the browser; the API refuses an `ops` token without 1."""
    proxy = (NGINX_DIR / "proxy.conf").read_text(encoding="utf-8")
    assert "proxy_set_header X-Argus-Ops $argus_ops_ok;" in proxy
    assert "proxy_set_header X-Argus-Ops-Cert $ssl_client_verify;" in proxy    # ACR-0038: for the audit
    conf = (NGINX_DIR / "http.conf").read_text(encoding="utf-8")
    assert "argus_ops_addr" not in conf                              # ACR-0037: the address is not a condition
    assert "$argus_ops_ok {" not in conf                             # ACR-0038: an ops-mode file defines it


@pytest.mark.parametrize("mode, key, value", [("certificate", "$ssl_client_verify", '"SUCCESS"'),
                                              ("passkey", "$https", '"on"')])
def test_each_ops_mode_file_defines_the_private_path_once(mode, key, value):
    """ACR-0038: the certificate mode passes a verified team certificate; the passkey-only mode any TLS request."""
    text = (NGINX_DIR / f"ops-mode-{mode}.conf").read_text(encoding="utf-8")
    m = re.search(r"map (\S+) \$argus_ops_ok \{(.*?)\}", text, re.S)
    assert m.group(1) == key
    assert [line.strip() for line in m.group(2).strip().splitlines()] == ["default 0;", f"{value} 1;"]
    assert text.count("$argus_ops_ok") == 1


def test_the_allowlist_in_git_allows_nobody():
    lines = [x for x in (NGINX_DIR / "ops-allow.conf").read_text(encoding="utf-8").splitlines()
             if x.strip() and not x.lstrip().startswith("#")]
    assert lines == []
    compose = (UI / "compose.public.yml").read_text(encoding="utf-8")
    assert "/opt/argus-v18/edge-ops/allow.conf:/etc/nginx/argus/ops-allow.conf:ro" in compose


def test_the_private_path_is_off_by_default_and_on_needs_the_ca_and_its_crl():
    compose = (UI / "compose.public.yml").read_text(encoding="utf-8")
    assert "ARGUS_OPS_PATH: ${ARGUS_OPS_PATH:-off}" in compose
    envsh = (UI / "05-argus-mode.envsh").read_text(encoding="utf-8")
    assert 'case "${ARGUS_OPS_PATH:-off}" in' in envsh and "ca.crt and crl.pem" in envsh
    # ACR-0038: the passkey-only mode is off by default too, and needs the private path on
    assert "ARGUS_OPS_PASSKEY_ONLY: ${ARGUS_OPS_PASSKEY_ONLY:-off}" in compose
    assert 'case "${ARGUS_OPS_PASSKEY_ONLY:-off}" in' in envsh and "OPS_MODE=certificate" in envsh
    tls = (NGINX_DIR / "ops-tls.conf").read_text(encoding="utf-8")
    assert "ssl_verify_client      optional;" in tls and "ssl_crl" in tls and "error_page 495" in tls
    assert "include /etc/nginx/ops/*.conf;" in (NGINX_DIR / "public.conf.template").read_text(encoding="utf-8")
    assert "include /etc/nginx/ops" not in (NGINX_DIR / "loopback.conf.template").read_text(encoding="utf-8")
    # the edge runs read-only: the directory the switch copies into must be writable (found in the X-5 window)
    ui = (NGINX_DIR.parent / "compose.ui.yml").read_text(encoding="utf-8")
    assert "- /etc/nginx/ops:uid=101,gid=101,mode=0700" in ui and "read_only: true" in ui


def _permissions(dependant) -> set[str]:
    """The permissions a route's dependencies name through `require(permission)`."""
    found = set()
    for d in dependant.dependencies:
        call = d.call
        if getattr(call, "__closure__", None) and "permission" in call.__code__.co_freevars:
            found.add(call.__closure__[call.__code__.co_freevars.index("permission")].cell_contents)
        found |= _permissions(d)
    return found


def test_every_privileged_route_lives_under_the_prefix_and_nothing_else_does(make_app):
    app = make_app()
    app.action_rows = None      # the routes without the private approval routes (an open gate mounts them; X-9)
    routes = [r for r in build_api(app).routes if hasattr(r, "dependant")]
    perms = {r.path: _permissions(r.dependant) for r in routes}
    assert "investigate" in perms["/api/v1/investigations"]                       # the reading works
    for path, needed in perms.items():
        assert bool(needed & PRIVILEGED_PERMISSIONS) == path.startswith(OPS_PREFIX), path
    assert not set().union(*ROLE_PERMISSIONS.values()) & PRIVILEGED_PERMISSIONS   # none granted yet


def test_with_the_action_routes_mounted_only_the_private_login_needs_no_privilege(make_app):  # noqa: F811
    """Phase 19 mounts the approval and hold routes; ACR-0032's private login is the one documented exception."""
    from argus.adapters.inbound.http import OPS_LOGIN
    app = make_app()
    app.action_rows = app.store
    routes = [r for r in build_api(app).routes if hasattr(r, "dependant")]
    perms = {r.path: _permissions(r.dependant) for r in routes}
    ops = [p for p in perms if p.startswith(OPS_PREFIX)]
    assert OPS_LOGIN in ops and len(ops) > 3
    for path, needed in perms.items():
        assert bool(needed & PRIVILEGED_PERMISSIONS) == (path.startswith(OPS_PREFIX) and path != OPS_LOGIN), path


def test_the_allowlist_prune_runs_daily_without_a_lease():
    service = (UI / "systemd" / "argus-v18-edge-allow-prune.service").read_text(encoding="utf-8")
    timer = (UI / "systemd" / "argus-v18-edge-allow-prune.timer").read_text(encoding="utf-8")
    assert "edge-allow.sh prune --scheduled" in service and "OnCalendar=daily" in timer


# --- the scripts -------------------------------------------------------------------------------------------------------
def sh(script, *args, cwd, env):
    return subprocess.run([BASH, str(script), *args], cwd=cwd, env=env, capture_output=True, text=True, timeout=120)


@pytest.fixture()
def ca(tmp_path):
    """The team's CA (made by edge-ca.sh, its key encrypted) and alice's 90-day certificate from her own CSR."""
    pw = tmp_path / "pass"
    pw.write_text("a-test-passphrase\n")
    env = {**os.environ, "ARGUS_EDGE_CA_DIR": str(tmp_path / "ca"), "ARGUS_EDGE_CA_PASSFILE": str(pw)}
    me = tmp_path / "alice"
    me.mkdir()
    for args, cwd in ((("init",), tmp_path), (("person-key", "alice"), me), (("sign", "alice", str(me / "alice.csr")), me)):
        r = sh(CA_SCRIPT, *args, cwd=cwd, env=env)
        assert r.returncode == 0, r.stdout + r.stderr
    return tmp_path / "ca", me, env


@needs_tools
def test_the_ca_key_is_encrypted_and_a_certificate_is_a_90_day_client_one(ca):
    cadir, me, _ = ca
    assert "ENCRYPTED" in (cadir / "ca.key").read_text()
    cert = x509.load_pem_x509_certificate((me / "alice.crt").read_bytes())
    assert cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value == "alice"
    eku = cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
    assert list(eku) == [ExtendedKeyUsageOID.CLIENT_AUTH]
    assert cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca is False
    days = (cert.not_valid_after_utc - cert.not_valid_before_utc).days
    assert 89 <= days <= 90
    assert "PRIVATE KEY" in (me / "alice.key").read_text() and not (cadir / "alice.key").exists()


@needs_tools
def test_a_revoked_certificate_is_in_the_new_crl(ca):
    cadir, me, env = ca
    serial = x509.load_pem_x509_certificate((me / "alice.crt").read_bytes()).serial_number
    r = sh(CA_SCRIPT, "revoke", "alice", cwd=me, env=env)
    assert r.returncode == 0 and "EDGE CERTS REVOKED: 1 of alice" in r.stdout, r.stdout + r.stderr
    crl = x509.load_pem_x509_crl((cadir / "crl.pem").read_bytes())
    assert crl.get_revoked_certificate_by_serial_number(serial) is not None
    assert "revoked" in sh(CA_SCRIPT, "list", cwd=me, env=env).stdout


@needs_tools
def test_the_ca_refuses_a_second_init_and_a_bad_handle(ca):
    cadir, me, env = ca
    assert "one CA per team" in sh(CA_SCRIPT, "init", cwd=me, env=env).stdout
    assert "lower-case handle" in sh(CA_SCRIPT, "person-key", "Alice Smith", cwd=me, env=env).stdout


@pytest.fixture()
def allow(tmp_path):
    (tmp_path / "SESSION").write_text("holder=alice session=x\n")
    env = {**os.environ, "ARGUS_DEPLOY_HOME": str(tmp_path), "ARGUS_DOCKER": "true"}
    return tmp_path / "edge-ops", env, tmp_path


@pytest.mark.skipif(not BASH, reason="needs bash")
def test_the_allowlist_holds_named_entries_with_an_expiry_and_logs_no_address(allow):
    d, env, cwd = allow
    run = lambda *a: sh(ALLOW_SCRIPT, *a, cwd=cwd, env=env)  # noqa: E731
    assert "NOT YOUR SESSION" in run("add", "bob", "198.51.100.7", "--as", "eve").stdout
    assert "EDGE ALLOW OK: bob" in run("add", "bob", "198.51.100.7", "--as", "alice").stdout
    assert "EDGE ALLOW OK: carol" in run("add", "carol", "203.0.113.0/24", "--days", "7", "--as", "alice").stdout
    conf = (d / "allow.conf").read_text()
    assert "198.51.100.7 1;  # bob" in conf and "203.0.113.0/24 1;  # carol" in conf
    run("add", "bob", "198.51.100.9", "--as", "alice")                     # a new address replaces the old one
    assert "198.51.100.7" not in (d / "allow.conf").read_text()
    listing = run("list").stdout
    assert "bob until" in listing and "2 active" in listing and "198.51" not in listing
    assert "198.51" not in (d / "changes.log").read_text() and "add bob by alice" in (d / "changes.log").read_text()
    if os.name != "nt":                                                  # NTFS has no such mode
        assert oct((d / "allowlist.tsv").stat().st_mode)[-3:] == "600"
    assert "EDGE ALLOW REMOVED: carol" in run("remove", "carol", "--as", "alice").stdout
    assert "carol" not in (d / "allow.conf").read_text()


@pytest.mark.skipif(not BASH, reason="needs bash")
@pytest.mark.parametrize("addr, why", [("300.1.1.1", "not an IPv4"), ("10.0.0.0/16", "wider than /24"),
                                       ("example.org", "not an IPv4"), ("0.0.0.0/0", "wider than /24")])
def test_the_allowlist_refuses_what_is_not_one_persons_address(allow, addr, why):
    d, env, cwd = allow
    assert why in sh(ALLOW_SCRIPT, "add", "bob", addr, "--as", "alice", cwd=cwd, env=env).stdout


@pytest.mark.skipif(not BASH, reason="needs bash")
def test_prune_drops_an_expired_entry_and_needs_no_lease_when_scheduled(allow):
    d, env, cwd = allow
    sh(ALLOW_SCRIPT, "add", "bob", "198.51.100.7", "--as", "alice", cwd=cwd, env=env)
    sh(ALLOW_SCRIPT, "add", "dan", "198.51.100.8", "--as", "alice", cwd=cwd, env=env)
    rows = (d / "allowlist.tsv").read_text().splitlines()
    (d / "allowlist.tsv").write_text("\n".join(r.replace(r.split("\t")[2], "1000") if r.startswith("dan") else r
                                               for r in rows) + "\n")       # dan's entry expired long ago
    assert "needs --as <lease holder>" in sh(ALLOW_SCRIPT, "prune", cwd=cwd, env=env).stdout   # by hand: a lease
    out = sh(ALLOW_SCRIPT, "prune", "--scheduled", cwd=cwd, env=env).stdout
    assert "EDGE ALLOW PRUNED: dan" in out
    assert "dan" not in (d / "allow.conf").read_text() and "bob" in (d / "allow.conf").read_text()


# --- with Docker: the real Nginx, public mode, the private path on --------------------------------------------------
# The client's address as Nginx sees it depends on the platform (the network's gateway on Linux CI, another one on
# Docker Desktop), so "allowed" is written straight into the file as every address (edge-allow.sh itself refuses
# anything wider than /24) and "not allowed" as a documentation address.
EVERYONE = "0.0.0.0/0 1;  # the test client, whatever address Docker gives it\n"


def _key_cert(cn, issuer_key=None, issuer=None, ca=False, days=1):
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    now = dt.datetime.now(dt.timezone.utc)
    b = (x509.CertificateBuilder().subject_name(name).issuer_name(issuer or name).public_key(key.public_key())
         .serial_number(x509.random_serial_number()).not_valid_before(now - dt.timedelta(minutes=5))
         .not_valid_after(now + dt.timedelta(days=days))
         .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True))
    if cn == "argus.test":
        b = b.add_extension(x509.SubjectAlternativeName([x509.DNSName("argus.test")]), critical=False)
    cert = b.sign(issuer_key or key, hashes.SHA256())
    return key, cert


def _pem(key=None, cert=None) -> bytes:
    if cert is not None:
        return cert.public_bytes(serialization.Encoding.PEM)
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())


@pytest.fixture(scope="module")
def private_edge(tmp_path_factory):
    """The edge in the default mode: a client certificate of the team's CA."""
    yield from _edge(tmp_path_factory, "certificate")


@pytest.fixture(scope="module")
def passkey_edge(tmp_path_factory):
    """ACR-0038: the edge with ARGUS_OPS_PASSKEY_ONLY=on: no certificate is asked for (no ops-tls include)."""
    yield from _edge(tmp_path_factory, "passkey")


def _edge(tmp_path_factory, mode):
    if not _docker_ready():
        pytest.skip("needs Docker (the real Nginx image)")
    tag = uuid.uuid4().hex[:8]
    net, api, web = f"argus-ops-test-{tag}", "argus-v18-agent", f"argus-ops-web-{mode[:4]}-{tag}"
    root = tmp_path_factory.mktemp("ops")
    tls, ops, inc, conf, certs, books = (root / n for n in ("tls", "ops", "inc", "conf", "certs", "runbooks"))
    for d in (tls, ops, inc, conf, certs, books):
        d.mkdir()
    (books / "RB-001-x.md").write_text("# RB-001", encoding="utf-8")
    ca_key, ca_cert = _key_cert("Argus test CA", ca=True, days=30)
    srv_key, srv_cert = _key_cert("argus.test")
    (tls / "privkey.pem").write_bytes(_pem(srv_key))
    (tls / "fullchain.pem").write_bytes(_pem(cert=srv_cert))
    (ops / "ca.crt").write_bytes(_pem(cert=ca_cert))
    clients = {}
    for who in ("alice", "mallory"):
        k, c = _key_cert(who, ca_key, ca_cert.subject)
        clients[who] = (k, c)
    other_key, other_cert = _key_cert("Other CA", ca=True)
    clients["stranger"] = _key_cert("stranger", other_key, other_cert.subject)
    for who, (k, c) in clients.items():
        (certs / f"{who}.key").write_bytes(_pem(k))
        (certs / f"{who}.crt").write_bytes(_pem(cert=c))

    def write_crl(revoked):
        now = dt.datetime.now(dt.timezone.utc)
        b = x509.CertificateRevocationListBuilder().issuer_name(ca_cert.subject).last_update(now).next_update(
            now + dt.timedelta(days=1))
        for c in revoked:
            b = b.add_revoked_certificate(x509.RevokedCertificateBuilder().serial_number(c.serial_number)
                                          .revocation_date(now).build())
        (ops / "crl.pem").write_bytes(b.sign(ca_key, hashes.SHA256()).public_bytes(serialization.Encoding.PEM))

    write_crl([clients["mallory"][1]])
    if mode == "certificate":                           # what 05-argus-mode.envsh copies for each mode
        (inc / "tls.conf").write_text((NGINX_DIR / "ops-tls.conf").read_text(encoding="utf-8"), encoding="utf-8")
    (conf / "00-argus-ops-mode.conf").write_text((NGINX_DIR / f"ops-mode-{mode}.conf").read_text(encoding="utf-8"),
                                                 encoding="utf-8")
    (conf / "default.conf").write_text((NGINX_DIR / "public.conf.template").read_text(encoding="utf-8")
                                       .replace("${ARGUS_UI_DOMAIN}", "argus.test"), encoding="utf-8")
    allow = root / "allow.conf"
    allow.write_text("# nobody yet\n")
    for d in (root, tls, ops, inc, conf, books):
        d.chmod(0o755)
        for f in d.iterdir():
            if f.is_file():
                f.chmod(0o644)
    run = lambda *a: subprocess.run(["docker", *a], capture_output=True, text=True, timeout=300)  # noqa: E731
    run("network", "create", net)
    gw = run("network", "inspect", net, "-f", "{{(index .IPAM.Config 0).Gateway}}").stdout.strip()
    run("run", "-d", "--name", f"{api}-{tag}", "--network", net, "--network-alias", api, "python:3.12-alpine",
        "python", "-c", FAKE_API)
    r = run("run", "-d", "--name", web, "--network", net, "-p", "127.0.0.1::8443",
            "-v", f"{NGINX_DIR}:/etc/nginx/argus:ro", "-v", f"{allow}:/etc/nginx/argus/ops-allow.conf:ro",
            "-v", f"{conf}:/etc/nginx/conf.d:ro", "-v", f"{tls}:/etc/argus-tls:ro", "-v", f"{ops}:/etc/argus-ops:ro",
            "-v", f"{inc}:/etc/nginx/ops:ro", "-v", f"{books}:/usr/share/nginx/runbooks:ro", NGINX_IMAGE)
    try:
        assert r.returncode == 0, r.stderr
        port = int(run("port", web, "8443").stdout.split(":")[-1].strip())

        def get(path, who=None, headers=None):
            ctx = ssl.create_default_context()
            ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
            if who:
                ctx.load_cert_chain(certs / f"{who}.crt", certs / f"{who}.key")
            c = http.client.HTTPSConnection("127.0.0.1", port, context=ctx, timeout=20)
            c.request("GET", path, headers={"Host": "argus.test", **(headers or {})})
            resp = c.getresponse()
            out = resp.status, resp.read().decode("utf-8", "replace")
            c.close()
            return out

        def set_allow(text):
            allow.write_text(text)                      # in place: the bind mount keeps the inode
            assert run("exec", web, "nginx", "-s", "reload").returncode == 0
            time.sleep(1)

        for _ in range(60):
            try:
                get("/healthz")
                break
            except OSError:
                time.sleep(1)
        else:
            pytest.fail("nginx did not start: " + run("logs", web).stderr[-2000:])
        yield get, set_allow, gw, run, web
    finally:
        run("rm", "-f", web, f"{api}-{tag}")
        run("network", "rm", net)


def test_nginx_accepts_the_private_path_configuration(private_edge):
    *_, run, web = private_edge
    r = run("exec", web, "nginx", "-t")
    assert r.returncode == 0, r.stderr


def test_without_a_certificate_the_prefix_is_404_and_the_public_ui_still_works(private_edge):
    get, set_allow, *_ = private_edge
    set_allow(EVERYONE)
    assert get("/api/v1/ops/anything")[0] == 404
    assert get("/api/v1/escalations")[0] == 200                       # the public UI needs no certificate
    assert get("/docs")[0] == 404


def test_a_valid_certificate_from_an_allowed_address_reaches_the_api(private_edge):
    get, set_allow, *_ = private_edge
    set_allow(EVERYONE)
    code, body = get("/api/v1/ops/approvals", "alice")
    assert code == 200 and '"path": "/api/v1/ops/approvals"' in body
    assert '"ops": "1"' in body                                         # ACR-0032: the API learns it is private


def test_the_ops_header_is_0_off_the_private_path_and_a_browser_cannot_forge_it(private_edge):
    get, set_allow, *_ = private_edge
    set_allow(EVERYONE)
    for who in (None, "alice"):                                        # public routes, with or without a certificate
        code, body = get("/api/v1/escalations", who, headers={"X-Argus-Ops": "1"})
        assert code == 200 and ('"ops": "1"' in body) == (who == "alice"), body


def test_a_valid_certificate_reaches_the_api_from_any_address(private_edge):
    """ACR-0037: the allowlist no longer gates the private path; the certificate alone does."""
    get, set_allow, *_ = private_edge
    set_allow("198.51.100.7 1;  # someone else, ignored by the edge\n")
    code, body = get("/api/v1/ops/approvals", "alice")
    assert code == 200 and '"ops": "1"' in body


@pytest.mark.parametrize("who", ["mallory", "stranger"])          # revoked in the CRL; issued by another CA
def test_a_revoked_or_foreign_certificate_is_404(private_edge, who):
    get, set_allow, *_ = private_edge
    set_allow(EVERYONE)
    assert get("/api/v1/ops/approvals", who)[0] == 404


def test_the_private_login_is_404_at_the_edge_unless_on_the_private_path(private_edge):
    """ACR-0032 §3: the login itself, not only the prefix: no certificate, a revoked or foreign one are 404; a
    valid certificate reaches the API with X-Argus-Ops 1."""
    from argus.adapters.inbound.http import OPS_LOGIN
    get, set_allow, *_ = private_edge
    set_allow(EVERYONE)
    for who in (None, "mallory", "stranger"):
        assert get(OPS_LOGIN, who, headers={"X-Argus-Ops": "1"})[0] == 404, who
    code, body = get(OPS_LOGIN, "alice", headers={"X-Argus-Ops": "0"})
    assert code == 200 and '"ops": "1"' in body


def test_the_runbooks_auth_check_uses_the_edges_ops_value_not_the_browsers(private_edge):
    """#347 review: /_argus_auth is a separate proxied request; it must carry $argus_ops_ok too. A forged header from a
    public browser must not make an `ops` token pass, and a real private request with one must."""
    get, set_allow, *_ = private_edge
    set_allow(EVERYONE)
    ops = {"Authorization": "Bearer ops"}
    assert get("/runbooks/RB-001-x.md", None, headers={**ops, "X-Argus-Ops": "1"})[0] == 401   # forged, public
    code, body = get("/runbooks/RB-001-x.md", "alice", headers={**ops, "X-Argus-Ops": "0"})
    assert code == 200 and "RB-001" in body                                                      # private path


def test_the_edge_passes_the_certificate_state_and_a_browser_cannot_claim_one(private_edge):
    """ACR-0038: X-Argus-Ops-Cert is the edge's $ssl_client_verify (for the audit), never the browser's copy."""
    get, set_allow, *_ = private_edge
    set_allow(EVERYONE)
    code, body = get("/api/v1/ops/approvals", "alice", headers={"X-Argus-Ops-Cert": "NONE"})
    assert code == 200 and '"cert": "SUCCESS"' in body
    code, body = get("/api/v1/escalations", None, headers={"X-Argus-Ops-Cert": "SUCCESS"})
    assert code == 200 and '"cert": "SUCCESS"' not in body


# --- with Docker: ACR-0038, the passkey-only mode (ARGUS_OPS_PASSKEY_ONLY=on) -----------------------------------------
def test_nginx_accepts_the_passkey_only_configuration(passkey_edge):
    *_, run, web = passkey_edge
    r = run("exec", web, "nginx", "-t")
    assert r.returncode == 0, r.stderr


def test_in_passkey_mode_the_prefix_and_the_private_login_need_no_certificate(passkey_edge):
    """The certificate is not asked for: the prefix and the private login reach the API with X-Argus-Ops 1, and the
    audit header says no certificate whatever the browser sends. The API's login, two keys and step-up remain."""
    from argus.adapters.inbound.http import OPS_LOGIN
    get, *_ = passkey_edge
    for path in ("/api/v1/ops/approvals", OPS_LOGIN):
        code, body = get(path, None, headers={"X-Argus-Ops": "0", "X-Argus-Ops-Cert": "SUCCESS"})
        assert code == 200 and '"ops": "1"' in body and '"cert": "NONE"' in body, (path, body)
    assert get("/docs")[0] == 404                                     # the rest of the edge is unchanged


def test_in_passkey_mode_an_ops_token_reads_the_runbooks_without_a_certificate(passkey_edge):
    get, *_ = passkey_edge
    code, body = get("/runbooks/RB-001-x.md", None, headers={"Authorization": "Bearer ops", "X-Argus-Ops": "0"})
    assert code == 200 and "RB-001" in body
    assert get("/runbooks/RB-001-x.md", None, headers={"Authorization": "Bearer bad"})[0] == 401


# --- with Docker: the edge's own start script chooses the mode --------------------------------------------------------
@pytest.mark.parametrize("env, ca, code, expect", [
    ({"ARGUS_UI_MODE": "public", "ARGUS_OPS_PATH": "on"}, True, 0, ("$ssl_client_verify", "tls.conf")),
    ({"ARGUS_UI_MODE": "public", "ARGUS_OPS_PATH": "on", "ARGUS_OPS_PASSKEY_ONLY": "on"}, False, 0, ("$https", "")),
    ({"ARGUS_UI_MODE": "public"}, False, 0, ("$ssl_client_verify", "")),
    ({"ARGUS_UI_MODE": "loopback"}, False, 0, ("$ssl_client_verify", "")),
    ({"ARGUS_UI_MODE": "public", "ARGUS_OPS_PASSKEY_ONLY": "on"}, False, 1, ("needs ARGUS_OPS_PATH=on",)),
    ({"ARGUS_UI_MODE": "public", "ARGUS_OPS_PATH": "on", "ARGUS_OPS_PASSKEY_ONLY": "yes"}, True, 1, ("must be on or off",)),
    ({"ARGUS_UI_MODE": "public", "ARGUS_OPS_PATH": "on"}, False, 1, ("needs /etc/argus-ops/ca.crt",)),
])
def test_the_start_script_picks_exactly_one_ops_mode(tmp_path, env, ca, code, expect):
    """ACR-0038: off by default (the certificate map); on needs the private path on and no CA files; anything else
    stops the edge before Nginx starts."""
    if not _docker_ready():
        pytest.skip("needs Docker (the real Nginx image)")
    tls, ops = tmp_path / "tls", tmp_path / "ops"
    for d in (tls, ops):
        d.mkdir()
    (tls / "fullchain.pem").write_text("x\n")
    (tls / "privkey.pem").write_text("x\n")
    if ca:
        (ops / "ca.crt").write_text("x\n")
        (ops / "crl.pem").write_text("x\n")
    for d in (tmp_path, tls, ops):
        d.chmod(0o755)
        for f in d.iterdir():
            if f.is_file():
                f.chmod(0o644)
    tmpfs = [a for p in ("/etc/nginx/ops", "/etc/nginx/conf.d", "/etc/nginx/templates")
             for a in ("--tmpfs", f"{p}:uid=101,gid=101,mode=0700")]
    envs = [a for k, v in env.items() for a in ("-e", f"{k}={v}")]
    r = subprocess.run(["docker", "run", "--rm", *tmpfs, *envs, "-e", "ARGUS_UI_DOMAIN=argus.test",
                        "-v", f"{NGINX_DIR}:/etc/nginx/argus:ro", "-v", f"{UI / '05-argus-mode.envsh'}:/e.envsh:ro",
                        "-v", f"{tls}:/etc/argus-tls:ro", "-v", f"{ops}:/etc/argus-ops:ro", "--entrypoint", "sh",
                        NGINX_IMAGE, "-c",
                        ". /e.envsh; echo; grep '^map' /etc/nginx/conf.d/00-argus-ops-mode.conf; ls /etc/nginx/ops"],
                       capture_output=True, text=True, timeout=300)
    out = r.stdout + r.stderr
    assert r.returncode == code, out
    if code:
        assert expect[0] in out and "00-argus-ops-mode" not in r.stdout
        return
    key, include = expect
    [line] = [x for x in r.stdout.splitlines() if x.startswith("map ")]
    assert line.split()[1] == key, out
    assert (include in r.stdout.split(line)[1]) if include else "tls.conf" not in r.stdout.split(line)[1], out
