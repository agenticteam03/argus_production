# SP-1 evidence (2026-10-05, run by conantkd, sanitized)

State probe (read-only):
- vm-095 (`vm-appsvnic`): `DEPLOYED` commit `c87d76c`, ref `task/T-0013-langgraph-skeleton`, by juanbetancurm,
  2026-10-05T02:17:54Z. 8 `argus-v18-*` containers + `argus-lab-api` Up (postgres healthy); `argus-v18-agent` Up 2 hours
  (not rebuilt by the deploy). `nonint-check.sh after`: NO INTERFERENCE.
- vm-166 (`agent-test-vnic`): `DEPLOYED` commit `8eff994`, ref `main`, by juanbetancurm, 2026-10-05T02:17:46Z.
  Argus containers Up; `nonint-check.sh after`: NO INTERFERENCE.
- `GET /health` on the agent API (127.0.0.1:18000) -> HTTP 404 (path probably not `/health`; not investigated).
- `git -C /opt/argus-v18/app` as `ubuntu` -> "dubious ownership" (root-owned clone; use `sudo git`). Harmless.

Login test (legacy 12b.2), vm-095, cheap `--check`, no model call:
- juanbetancurm -> inc_cebf36e4acdd, outcome HEALTHY
- conantkd      -> inc_1617ce824b09, outcome HEALTHY
- juanes6554    -> inc_c193b26c95af, outcome HEALTHY

Note: the first paste of SP-1.3 was run on vm-166 by mistake (no agent container there); it failed harmlessly and
was repeated on vm-095.
