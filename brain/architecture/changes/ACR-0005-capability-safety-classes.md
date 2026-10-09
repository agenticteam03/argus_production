# ACR-0005 — One safety class for runbooks and capabilities (OP-003)

| Field | Value |
|---|---|
| Status | `proposed` — no architecture or runtime change in this proposal |
| Proposed by | conantkd (+ agent) · 2026-10-09 |
| Accepted by | pending team decision |
| Second approval (safety principle only) | required in the implementation PR |
| Architecture version | proposed from `1.8.2`; next version determined after ACR-0003/0004 |
| Task / PR | OP-003 · proposal PR pending |

## 1. Detect and explain

`RUNBOOK-CONVENTIONS.md` gives operations five safety classes. Architecture §12.3 instead gives a capability an
independent `risk: low | medium | high | very_high`, `side_effect: none | write`, and `permission: read | write_hitl`.
There is no rule translating one scheme to the other. The running read catalogue already has a two-value
`safety_class`, but it has no mandatory per-source field allowlist and cannot represent writes. This leaves the
architecture, runbooks, and runtime contract divergent.

The difference is concrete: RB-001/RB-002 classify container status as `READ_ONLY_SENSITIVE`, while the registered
`container.status` spec says `READ_ONLY_SAFE`. RB-002 classifies health-check output as sensitive, while
`container.health` says safe. RB-009 treats DNS and HTTP observations as sensitive, while `network.resolve_dns` and
`network.http_probe` say safe. These are classification disagreements, not evidence of a released write capability.

## 2. Why the current architecture is insufficient

- §12.2 lists capabilities and rollout levels without a safety class. A level limits availability; it does not
  describe data sensitivity or action risk.
- §12.3's `risk` has no defined mapping to the runbook classes; `READ_ONLY_SENSITIVE` cannot be inferred from
  `permission="read"`. §4.7 controls file/log inspection but is not a complete output-field rule for every executor.
- §13.1 already has a closed write gate. A low-risk label must not bypass HITL, precheck, or that gate.

## 3. Smallest reasonable change

**Proposed §12.3 contract, before → after:** replace the free-standing `risk` and `side_effect` fields with
`safety_class: READ_ONLY_SAFE | READ_ONLY_SENSITIVE | MUTATING_LOW_RISK | MUTATING_HIGH_RISK` and derive
`permission` (`read` for the first two; `write_hitl` for the last two). `FORBIDDEN` is a policy classification only:
it is never a registered capability. Keep `level` as a separate rollout control. All writes remain unavailable until
their existing per-capability/target gate is explicitly released.

**Proposed §12.3 rule:** a sensitive read has an explicit, executor-specific output schema and field allowlist.
Unknown fields are dropped before evidence/model storage; literals are redacted, and missing or partial data is
reported as such. Registration fails closed when its schema/allowlist is missing. Apply this only after the existing
sensitive reads have reviewed allowlists, so the migration cannot silently disable incident diagnosis. This also
addresses the field-allowlist portion of OP-002/G-006; it does not claim to settle the other seven P0 gaps.

**Proposed §12.2 inventory** (classify each named capability; a future capability requires its own review):

| Class | Capabilities |
|---|---|
| `READ_ONLY_SAFE` | `container.resources`, `container.restart_count`, `container.events`, `host.cpu`, `host.memory`, `host.disk_usage`, `host.uptime`, `host.load`, `host.io`, `docker.disk_usage`, `network.tcp_connect`, `network.tcp_connection`, `metrics.memory_history`, `metrics.cpu_history`, `metrics.disk_history`, `metrics.network_history`, `metrics.restart_history`, `metrics.compare_baseline`, `knowledge.runbook` |
| `READ_ONLY_SENSITIVE` | `container.list`, `container.status`, `container.logs`, `container.health`, `container.processes`, `container.detailed_logs`, `container.search_logs`, `container.network`, `host.top_cpu`, `host.top_memory`, `host.directory_sizes`, `host.kernel_oom_records`, `host.socket_summary`, `host.read_file`, `host.service_config`, `host.journal`, `host.process_details`, `network.http_probe`, `network.resolve_dns`, `network.connectivity`, `database.health`, `knowledge.prior_incidents`, `analysis.diagnostic_snapshot`, `analysis.timeline`, `analysis.trace_request_path` |
| `MUTATING_LOW_RISK` | none in this release; a bounded reversible write still needs HITL and an explicit gate |
| `MUTATING_HIGH_RISK` | `container.restart`; future `service.scale`, `container.update_resources`, `docker.prune`, `logs.rotate`, `service.restart`, `deployment.rollback`, `container.isolate`, `runbook.execute` remain unregistered until separately designed and released |
| `FORBIDDEN` | no registered capability; arbitrary shell/SQL/file access and bypass operations remain refused |

The sensitive row deliberately uses the stricter runbook classification where current code and runbooks disagree.
Before applying this inventory, review each capability's actual output schema and decide whether to narrow the
output or keep the sensitive class. In particular, `container.status`, `container.health`, DNS, and HTTP probe are
explicit review cases. A narrower response may justify a later class change through review, not an implicit downgrade.

**Alternatives considered:**

- Keep the `risk` field and maintain a translation table. This leaves two independent labels that can drift and
  makes a sensitive read indistinguishable from ordinary telemetry without consulting a second registry.
- Treat every read as sensitive. This is safe but adds allowlist maintenance to simple structured metrics and
  obscures the difference the runbook library already records.

## 4. Consequences

- The implementation PR must update §12.2–§12.3, version/changelog, `CapabilitySpec`, every registered spec, policy
  validation/redaction, and tests. It must identify reviewed allowed fields for all sensitive sources before enabling
  fail-closed validation. It must keep the write gate closed and add no write tool to the model or MCP catalogue.
- `container.status`, `container.health`, DNS, and HTTP probe may require tighter responses or allowlists. This can
  affect diagnosis, so compare existing scenario/evaluation behavior before deployment.
- Reversal: revert the accepted architecture and implementation PR together. A proposal rejection changes no runtime.
- **Safety principle:** yes — data minimization, evidence integrity, and the write gate. A second team member's
  approval is required; this ACR is not eligible for fast-track.

## 5. Decision

Pending team review. Approval must settle the four currently conflicting read classifications and the migration
order for required allowlists. No architecture or code change is authorized by this proposed record alone.

## 6. Applied

- [ ] ACR accepted by the team with a second safety approval
- [ ] `ARCHITECTURE.md` updated, version bumped, changelog line added
- [ ] catalog/policy migration implemented with tests and evaluation comparison
- [ ] OP-003 marked fixed after the implemented inventory and policy are verified
