# T-0031 step 02 — evidence: the deployment write-gate check on vm-095 (2026-10-10, conantkd, session 4ef1e84354ce)

Run by the agent over SSH (`code.bash` in this folder), vm-095 lease only. Sanitized: no addresses, no secrets. The
branch (`8a6915b`) was copied to `/tmp/argus-t0031` with `git archive` and removed afterwards; the deployed checkout
(`main` `ebbe9c9`) and the running containers were not changed. The report module ran from `argus/policy/`; it
moved to `argus/infrastructure/` afterwards (the policy package may import only the domain), unchanged.

| Check | Result |
|---|---|
| Before | `nonint-check before` saved the baseline |
| Per service | `argus-v18-agent`, `-worker`, `-scheduler`: `gate_open=0 write_capabilities=0 action_gateway_resolves=0 policy=987032aaddc8` |
| Host | no action container, no action mount, no `ARGUS_ACTION*` variable |
| Verdict | **`WRITE GATE CLOSED`**, exit 0 |
| Cross-check | the running agent's `policy.yaml` has `write_gate: open: []`; `/healthz` reports `policy_version` `987032aaddc8`, the same hash the check computed |
| After | **NO INTERFERENCE** |

**Result:** the agent host has no write path: the running services load a closed gate and a read-only catalogue, and
no action gateway, credential or route exists.
