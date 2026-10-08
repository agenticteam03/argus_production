# T-0015 step 06 — evidence (2026-10-07, juanbetancurm, lease DEMO-SC07 renewed)

Goal: prove on the deployed agent (vm-095) that a `scope=read` token reads and is refused on a write. No deploy and
no rebuild: the running agent image (rebuilt for T-0019/T-0020) already carries T-0015 from `main` (PR #22).

Key output lines from output.bash, SANITIZED (no addresses, no secrets, no token).

| Check | Expected | Observed | Result |
|---|---|---|---|
| Lease | renewed | `Lease renewed until 2026-10-07T23:29:04+00:00` | OK |
| Session marker | `SESSION OK` | `SESSION OK` | OK |
| Login `scope=read` | a token with `access: read` | `login scope=read: token with access=read` (token never printed) | OK |
| `GET /api/v1/me` | user, role, `access=read`, actions | `juanbetancurm operator access=read actions=view_incidents,view_timeline,view_evidence` | OK |
| `GET /api/v1/incidents` with the read token | 200 | `200` | OK |
| `POST /api/v1/investigations` with the read token | 403 | `403` (nothing created) | OK |
| `GET /api/v1/incidents` without a token | 401 | `401` | OK |

nonint-check: NO INTERFERENCE on vm-095 (yes). vm-166 not touched.

**Result:** T-0015 is done: the deployed API gives read-only tokens to user interfaces and refuses them on every write.
