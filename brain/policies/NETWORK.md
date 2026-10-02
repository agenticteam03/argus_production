# Policy — network traffic and data leaving the VMs

| Flow | Direction for the VMs | Size | Notes |
|---|---|---|---|
| Developer SSH sessions, `code.bash` commands | in | small | terminal output going out is small text |
| `git fetch` by `ops/deploy.sh` (read-only deploy key) | in | ~100 KB per update | GitHub → VM |
| Docker image pulls, `pip install` during builds | in | 10–200 MB per new image | only when images or dependencies change |
| vm-095 ↔ vm-166 (SSH tunnel: gateways, probes, Prometheus) | private network | KB per read | stays inside the cloud network; not internet egress |
| Prometheus, exporter, Postgres, evidence storage | local | — | no `remote_write`; metrics and evidence never leave the VMs |
| **Agent → OpenAI API (vm-095)** | **out** | ≈ 5–30 KB per model step; ≤ 8 steps per incident | context = runbook passages + the last evidence bodies (bounded) + findings; healthy checks, refused targets and evidence packs make **no** model call |
| Swagger / CLI through `ssh -L` | out | KB | — |

## Rules

- Evidence and logs stay on the VMs; only summaries leave.
- No `remote_write`, log shipping or new external service without an ACR.
- The model context stays bounded (enforced in code: log reads are capped, evidence bodies are truncated for context).
- Raw outputs pasted into `output.bash` are small by design.
- New outbound destinations (another API, a registry) need an ACR.

Cost: the cloud provider bills internet egress above a free monthly allowance; our outbound volume is in the KB–MB
range per day. Traffic over private addresses inside the cloud network is normally not internet egress.
