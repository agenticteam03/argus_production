## 2026-10-28 - ACR-0037: the private path needs the client certificate alone

Type: architecture change
Who: conantkd
Context: a team member with a valid client certificate in the browser and a registered passkey got "The private login is reachable only on the private path" on the Actions tab: the edge's 404, because the private path also required the client's address in vm-095's allowlist. The address changes, entries expire and IPv6 cannot be registered; each fix needs a lease.
Decision / result:
- `deploy/ui/nginx/http.conf`: `$argus_ops_ok` is 1 only when `$ssl_client_verify` is `SUCCESS`; the `geo` block over the allowlist is gone.
- Unchanged: the CA and CRL, the 404 for no, revoked or foreign certificates, `ARGUS_OPS_PATH=off` by default, `X-Argus-Ops` set only by the edge, the login, second factor and step-up.
- `ARCHITECTURE.md` 1.8.44 with the changelog row linking [ACR-0037](../../architecture/changes/ACR-0037-private-path-certificate-only.md).
Consequences: `ops/edge-allow.sh`, its prune timer and the `allow.conf` mount stay in the repository but no longer gate anything; removing them is a separate clean-up. Nothing changes on vm-095 until the next UI deploy.
References: [ACR-0018](../../architecture/changes/ACR-0018-operator-access-and-audit.md), [ACR-0032](../../architecture/changes/ACR-0032-private-browser-login.md).

### Test state

`tests/test_phase16_private_path.py` (including the Docker nginx edge tests) and `tests/test_acr0011_ui_edge.py` pass locally: a valid certificate from an address not in the allowlist now reaches the API and the private login with `X-Argus-Ops: 1`; no, revoked and foreign certificates stay 404. The full suite is left to CI.

### Next step

Deploy the UI edge on vm-095 in a leased window, then log in privately from the browser with the certificate and open the Actions tab.
