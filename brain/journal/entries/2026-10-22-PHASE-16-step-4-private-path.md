## 2026-10-22 - PHASE-16 step 4: the private path (privileged routes behind mTLS and an allowlist; ARCHITECTURE 1.8.30)

Type: work (security)
Who: conantkd (+ agent)
Context: ACR-0018 requires every privileged route to answer 404 on the public edge unless the client's certificate
verifies and its address is allowlisted. No privileged route exists yet (they come with phases 17-19), so the gate is
built first. Decided with conantkd: one prefix for all of them, the CA on his laptop with a copy kept by Juan.
Decision / result:
- `/api/v1/ops/` (`OPS_PREFIX`) is the only home of a route that needs a privileged permission (a test reads each
  route's `require(...)` and fails a privileged one outside it or an ordinary one inside).
- The edge: `location ^~ /api/v1/ops/` proxies only when `$argus_ops_ok` (a map) is 1: `$ssl_client_verify` is
  SUCCESS and the address is in a `geo` allowlist; else 404. With `ssl_verify_client optional`, a browser without a
  certificate keeps the public UI; a bad or revoked certificate's 495 becomes 404. `ops-tls.conf` (CA, CRL) is included
  only with `ARGUS_OPS_PATH=on`; off (the default), the prefix is 404 for everyone. The allowlist in Git
  (`ops-allow.conf`) allows nobody; vm-095's file is mounted over it.
- `ops/edge-ca.sh` (a laptop): the CA (P-256 key, AES-256 encrypted), 90-day client certificates from a person's own
  CSR (their key never travels), revocation into a 30-day CRL, a `.p12` for the browser. Works in Git Bash on Windows
  (no path conversion of subjects; `cygpath -m` for the config).
- `ops/edge-allow.sh` (vm-095, with the lease): named entries with an expiry (up to 90 days, at most a /24), written in
  place and the edge reloaded; the listing and `changes.log` never show an address; `prune --scheduled` from a daily
  timer (`deploy/ui/systemd/argus-v18-edge-allow-prune.*`).
- ARCHITECTURE 1.8.30 (§17.3, changelog), ACR-0018 §6, `policies/NETWORK.md` (the flow; addresses are personal data;
  the CA key never on a VM), the PHASE-16 task.
Consequences: nothing changes for anyone until a privileged route exists and the private path is switched on. The
deploy must create `/opt/argus-v18/edge-ops/allow.conf` before the edge's `up` (a missing bind source becomes a
directory).
References: [PHASE-16](../../tasks/current/PHASE-16-operator-access.md),
[ACR-0018](../../architecture/changes/ACR-0018-operator-access-and-audit.md).

### Test state

`tests/test_phase16_private_path.py` 20 passed on Windows with Docker: the real Nginx in public mode with the private
path on; no certificate, an unlisted address, a revoked or a foreign certificate → 404; a valid certificate from an
allowed address reaches the API; the public UI unchanged. On Linux, the scripts and static checks pass (the Docker
cases skip there). `tests/test_acr0011_ui_edge.py` 34 passed with Docker. `nginx -t` passes in loopback, public-off
and public-on modes. Shellcheck is clean.
