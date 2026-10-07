# T-0019 batch 1 step 01 — evidence (2026-10-07, conantkd, session 3307114120d3)

Goal: confirm vm-166 can host the db-probe and the lab database. Read-only; run by the agent over SSH.

| Check | Expected | Observed | Result |
|---|---|---|---|
| Session | `SESSION OK` | `SESSION OK` | OK |
| PyPI (pg8000 for the image build) | http 200 | `pypi pg8000 http=200` | OK |
| `postgres:16-alpine` | present, or Docker Hub reachable | absent; `docker hub http=401` (reachable, pull at deploy) | OK |
| Port | `127.0.0.1:18704` free | `port 18704 free` | OK |
| Network | `argus-lab-app` exists | `network argus-lab-app <addr>/24` | OK |
| Memory | >= 1024 MB available | `mem total=5909MB available=4472MB` | OK |
| Disk | below 80 % | `docker disk used=27% avail=36G` | OK |
| Isolation | NO INTERFERENCE | `NO INTERFERENCE: non-Argus objects unchanged` | OK |

Also checked in the repository: the vm-095 tunnel already forwards 18704 (`deploy/vm-095/tunnel/Dockerfile`).

**Result:** nothing blocks batch 1 on vm-166.
