# Policy — network traffic and data leaving the VMs

| Flow | Direction for the VMs | Size | Notes |
|---|---|---|---|
| Developer SSH sessions, `code.bash` commands | in | small | terminal output going out is small text |
| `git fetch` by `ops/deploy.sh` (read-only deploy key) | in | ~100 KB per update | GitHub → VM |
| Docker image pulls, `pip install` during builds | in | 10–200 MB per new image | only when images or dependencies change |
| vm-095 ↔ vm-166 (SSH tunnel: gateways, probes, Prometheus) | private network | KB per read | stays inside the cloud network; not internet egress |
| Prometheus, exporter, Postgres, evidence storage | local | — | no `remote_write`; metrics and evidence never leave the VMs |
| **Agent → OpenAI API (vm-095)** | **out** | ≈ 5–30 KB per model step; ≤ 8 steps per incident | context = runbook passages + the last evidence bodies (bounded) + findings; healthy checks, refused targets and evidence packs make **no** model call |
| **Scheduler → OCI Object Storage (vm-095)** | **out** | a few hundred bytes a day: one signed audit digest | `https` to the Object Storage endpoint of the account's region, with a create-and-inspect credential (ACR-0018 §5); OCI is the configured application destination, but the shared bridge does not yet enforce an outbound allowlist; off until the schedule is turned on |
| Swagger / CLI through `ssh -L` | out | KB | — |
| Privileged UI routes (`/api/v1/ops/`) through the public edge | in | KB | only with a client certificate of the team's CA and an allowlisted address (ACR-0018 step 4); else 404 |

## Rules

- Evidence and logs stay on the VMs; only summaries leave.
- No `remote_write`, log shipping or new external service without an ACR.
- The model context stays bounded (enforced in code: log reads are capped, evidence bodies are truncated for context).
- Raw outputs pasted into `output.bash` are small by design.
- New outbound destinations (another API, a registry) need an ACR.
- The scheduler's OCI-only egress is an intended restriction, not an enforced network boundary. Before claiming it,
  add and test an outbound allowlist or a narrow proxy for the scheduler; the current `argus-v18-core` bridge permits
  other outbound destinations. Track this in the phase-16 task.
- The private path's allowlist (`/opt/argus-v18/edge-ops/allowlist.tsv` on vm-095, `ops/edge-allow.sh`) holds people's addresses: personal data. They never enter Git, a journal entry, an evidence file or `output.bash`; the script's listing and log name the person, never the address. The widest entry is a /24.
- The private path's CA key never goes to a VM: an administrator's laptop, encrypted, with one copy kept by the other administrator (`ops/edge-ca.sh`). vm-095 holds only the CA certificate and its CRL.

Cost: the cloud provider bills internet egress above a free monthly allowance; our outbound volume is in the KB–MB
range per day. Traffic over private addresses inside the cloud network is normally not internet egress.
