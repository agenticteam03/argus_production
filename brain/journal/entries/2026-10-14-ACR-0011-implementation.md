## 2026-10-14 — ACR-0011 built in #144: the public UI edge, offline (4a–4c)

Type: feature (API, frontend, deployment files)
Who: conantkd (+ agent)
Context: `conantkd` asked to build ACR-0011 as if accepted. It has one approval (`juanes6554`, #140); the second
approval is still required (least privilege and secrets). #144 therefore cannot merge before both approvals, and
nothing is deployed.
Decision / result:
- **API:** edge logins are read-only; failed logins are audited and limited per username and address, with a
  lockout; `limit` is capped.
- **Frontend:** the runbooks load from the edge after login, and the real bundle has none.
- **The edge** `argus-v18-ui`:
  - Nginx without root, in `loopback` and `public` modes;
  - the contract allowlist, limits and security headers;
  - `/runbooks/` checked against `/api/v1/me`;
  - certbot with a renewal timer, `DOCKER-USER` connection limits, and `nonint-check` aware of its ports.
- **Documents:** ARCHITECTURE 1.8.10, `environment.md`, `SECURITY.md` and `API-FOR-UI.md` updated.
- **Verified:** with the real Nginx image (tests and a local run of the built image in both modes).

Two differences from the ACR text, recorded in its §9:
- the `DOCKER-USER` rule is a per-address connection limit, because Docker already restricts a published port to its
  container;
- `nonint-check` needed a port exclusion, not a firewall one.
Consequences: the root `.dockerignore` is new (the build context no longer sends `node_modules`, `.venv`, `.git`).
4d (vm-095 loopback) needs the lease; 4e needs ACR-0011 §8's data.
References: [ACR-0011](../../architecture/changes/ACR-0011-public-https-ui.md),
[T-0016](../../tasks/current/T-0016-frontend.md).

### Test state

- New: `tests/test_acr0011_edge_login.py` (10, red seen) and `tests/test_acr0011_ui_edge.py` (24; Docker).
- Frontend: `npm test` 80, `npm run e2e` 10, `npm run lint` 0 errors.

### Next step

The approvals of #144 (a teammate's, and the second approval of ACR-0011). Then 4d on vm-095's loopback with the
lease, and 4e once §8's data is known.
