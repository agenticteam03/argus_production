## 2026-10-28 - ACR-0038: a passkey-only mode of the private path, off by default

Type: architecture change
Who: conantkd
Context: approvers had to install and renew a client certificate (`.p12`) in the browser before the private path answered, although the private login already requires two security keys, a key-completed session and a step-up per decision.
Decision / result:
- The edge's `$argus_ops_ok` now comes from one of two files the start script copies: `ops-mode-certificate.conf` (the default, unchanged) or `ops-mode-passkey.conf` (`ARGUS_OPS_PASSKEY_ONLY=on`, which needs `ARGUS_OPS_PATH=on`): any TLS request, never the loopback server. It covers the whole `/api/v1/ops/` prefix and an `ops` token's runbook reads.
- The API still requires a human approver with two keys at the private login, a key-completed session before any privileged permission, and a step-up per decision.
- The edge sends `X-Argus-Ops-Cert`; the private login and each approval answer record `client_cert: verified | none`.
- `ARCHITECTURE.md` 1.8.46 and [ACR-0038](../../architecture/changes/ACR-0038-private-path-passkey-only.md).
Consequences: nothing changes on vm-095 until `ARGUS_OPS_PASSKEY_ONLY=on` is set in `deploy/ui/vm-095.env` and the edge is recreated, in a leased window.
References: [ACR-0018](../../architecture/changes/ACR-0018-operator-access-and-audit.md), [ACR-0032](../../architecture/changes/ACR-0032-private-browser-login.md), [ACR-0037](../../architecture/changes/ACR-0037-private-path-certificate-only.md).

### Test state

Locally: `test_phase16_private_path.py` with Docker (the real Nginx in certificate mode and in passkey-only mode; the start script choosing exactly one mode and stopping on a bad value or a missing private path), `test_acr0011_ui_edge.py`, `test_phase19_private_login.py` (the audit's `client_cert`, the header believed only from the edge on the private path, a password alone reaching no privileged route), `test_incident_action_trail.py`, `test_phase16_security_alerts.py`; ruff 0.8.6 clean. The frontend test and the full suite are left to CI.

### Next step

To turn it on: `ARGUS_OPS_PASSKEY_ONLY=on` in vm-095's `deploy/ui/vm-095.env`, recreate `argus-v18-ui`, then sign in privately without the certificate and check `client_cert: none` in the audit.
