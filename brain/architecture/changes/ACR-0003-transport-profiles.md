# ACR-0003 — Portable transport profiles; alert delivery by profile (closes D-001)

An Architecture Change Record is the **only** way to change `brain/architecture/ARCHITECTURE.md`. ACRs are never
fast-tracked. This one touches a safety principle (host isolation, the cross-host path), so it needs a second team
member's approval in its pull request.

| Field | Value |
|---|---|
| Status | `proposed` |
| Proposed by | conantkd (+ agent) · 2026-10-08 |
| Accepted by | conantkd · 2026-10-08 (decision text in §5); waits for the second approval |
| Second approval (safety principle only) | **required** (host isolation): `juanbetancurm` in the T-0022 PR |
| Architecture version | from `1.8.2` (ACR-0002, PR #39) → `1.8.3` |
| Task / PR | T-0022 (phase 7, alerting) · PR to be opened |

## 1. Detect and explain

- **D-001** (`brain/OPEN_PROBLEMS.md`, open since 2026-10-02): the architecture text and the running system
  disagree on the cross-host path and on the direction of alerts.
  - The architecture says the hosts talk over the private network with no tunnel, and that alerts are pushed
    (Alertmanager on Host T → webhook on Host A).
  - The running system uses a **restricted SSH tunnel** over port 22, the only port open between the VMs, because the
    cloud network rules cannot be changed by the team (`IMPLEMENTATION_PLAN.md`, "Cross-host transport — decided and
    verified 2026-10-01"). It is forward-only (`argus-v18-tunnel` on vm-095, `-L` forwards), with a shell-less account
    (`nologin`, `restrict,port-forwarding,permitopen=…`), a pinned host key, and target services bound to `127.0.0.1`.
- **Phase 7** (T-0022) has to deliver firing alerts to Argus. Over a forward-only tunnel, Host T cannot reach Host A,
  so the push webhook of §4.2 cannot work in this deployment without opening a new reverse path.
- The `ReconcileFiringAlerts` use case (§7.3) exists in the architecture but only as an optional backup, and reads
  Prometheus `ALERTS`.

## 2. Why the current architecture is insufficient

- **§3.2, rule 1:** *"Hosts communicate over a private network … When the path crosses any network that is not private
  to the deployment, an encrypted tunnel (WireGuard) is required."* It names one transport and assumes the private
  addresses are reachable on the service ports. Here only port 22 is.
- **§3.2, rule 2:** *"Every service on Host T that Host A must reach … is published only on the private address."*
  With an SSH tunnel the services are bound to loopback and reached through exact `permitopen` destinations, which is
  stricter, but the text does not allow it.
- **§3.3 and §4.2:** Alertmanager **posts** to Argus's webhook over the private path. There is no delivery rule for a
  deployment where the path is one-directional.
- **§3.6:** *"Cross-host path: private subnet, no tunnel (accepted risk of §3.2)"* and *"`<host-a private IP>:8000` for
  the webhook from `<host-t private IP>` only"*. Neither is true for this deployment.
- **§3.5:** `node-exporter`, `cadvisor` are *"reused if already present"*. On vm-166 the existing ones belong to a
  protected deployment that Argus must never scrape (`infrastructure/environment.md` §4).
- **§7.3:** `ReconcileFiringAlerts` reads Prometheus `ALERTS`. The alert identity there (§6.6, `fingerprint +
  startsAt`) is Alertmanager's, so a pulled alert would not match a pushed one.

## 3. Smallest reasonable change

**§3.2** — replace rule 1 and rule 2 with a **transport profile**, and keep rules 3 and 4 as profile requirements:

> after: A deployment selects **one explicit transport profile** for the cross-host path. The profile is configuration
> (`deploy/`, `hosts.env`), never automatic detection or fallback.
>
> | Profile | Path | Services on Host T are reached at | Alert delivery |
> |---|---|---|---|
> | `direct-private` | private addresses (shared subnet or VCN) + `DOCKER-USER` source restrictions | the private address only | push webhook (§4.2), plus reconciliation |
> | `wireguard-overlay` | an **Argus-owned** WireGuard interface, keys and firewall rules | the overlay address only | push webhook (§4.2), plus reconciliation |
> | `restricted-ssh` | an encrypted, **forward-only** SSH tunnel over port 22: a shell-less account, a pinned host key, exact `permitopen` destinations | `127.0.0.1` only, through the tunnel | **pull**: scheduler-driven reconciliation (§7.3) |
>
> Every profile preserves: per-service credentials (§17.2); the host-qualified inventory; no public exposure (no
> `0.0.0.0`, no public interface); no cross-host executor fallback (a call for host X goes only to host X's executor).
> Push needs bidirectional connectivity; a profile without it pulls. `restricted-ssh` is the portable fallback when
> only SSH is available. Rules 3 and 4 below apply to every profile.

**§3.3** — the Alertmanager row gets the profile:

> after: `Alertmanager → Argus POST /api/v1/alerts` (push profiles) **or** `argus-scheduler → Alertmanager
> /api/v2/alerts` (pull profiles) · authentication: bearer service token (push) / the profile's path + Alertmanager
> bound to loopback (pull).

**§3.5** — `node-exporter`, `cadvisor`:

> before: *"reused if already present"*
>
> after: **Argus-owned instances** (`argus-v18-*`). Exporters of another deployment are reused only when that
> deployment's owners agree, recorded in `infrastructure/environment.md`. `cadvisor` mounts `/sys`, `/var/lib/docker`
> and the Docker socket **read-only**: an accepted risk recorded in §4.3 (it is not an Argus process and is not reachable
> from Host A except through Prometheus).

**§3.6** — the instance values:

> after: Transport profile: **`restricted-ssh`** (only port 22 is open between the VMs). Alert delivery: pull. API
> exposure: `127.0.0.1:8000` for humans (SSH tunnel); no private-address listener (no webhook from Host T).

**§4.2** — Alertmanager:

> after: … It **posts** to Argus's webhook (push profiles) with a bearer token read from a file … In a pull profile it
> is bound to loopback, sends no notification to Argus, and is read by `ReconcileFiringAlerts`.

**§7.3** — `ReconcileFiringAlerts`:

> before: queries each Argus-owned Prometheus's current `ALERTS` through `MetricsPort.firing_alerts()` … covers alerts
> missed during an Argus outage.
>
> after: queries each Host T's **Argus-owned Alertmanager** (`GET /api/v2/alerts?active=true&silenced=false&inhibited=false`)
> through `AlertSourcePort.firing_alerts(host)` and submits every firing alert through `HandleAlertNotification`, with
> the same identity as the webhook (`fingerprint + startsAt`, §6.6), so a push and a pull of the same alert are one
> incident. In a **pull** profile it is the primary trigger and is **enabled**; in a push profile it is the backup for
> alerts missed during an Argus outage.

**§8.1** (outbound ports) — `MetricsPort.firing_alerts(host)` moves to a new `AlertSourcePort.firing_alerts(host) ->
list[AlertNotification]` (adapter `alerts_alertmanager.py`, fake `alerts_fake.py`): Alertmanager is a different
backend from Prometheus. "The seven deterministic ports" become eight.

**§17.1 (layers, row 7)** — *"Cross-host path: the selected transport profile (§3.2); per-service
credentials; no public exposure; no cross-host executor fallback."*

**§25 OD-16** — *"decided by ACR-0003: covered by the transport profiles; a profile that leaves the private network
is encrypted (`wireguard-overlay`, `restricted-ssh`)."*

**Alternatives considered:**

- **A. Keep the architecture text; open the ports later (D-001 option A).** Not possible for the team (the cloud rules
  cannot be changed), and it leaves phase 7 with no alert delivery at all in the meantime.
- **B'. Push through a reverse SSH forward** (`ssh -R`) in the existing tunnel. It opens a new Host T → Host A path,
  and needs `permitlisten` on Host A's side: a second door into the agent host for the convenience of push. Pull keeps
  the tunnel forward-only.
- **C. Use the existing WireGuard tunnel (D-001 option C).** It belongs to a protected deployment. The
  `wireguard-overlay` profile allows a WireGuard path only when Argus owns the interface, keys and rules.
- **Pull from Prometheus `ALERTS` instead of Alertmanager.** Simpler (no new component, no new `permitopen`), but there
  is no grouping, silencing or inhibition, and the identity differs from the webhook's, so a later switch to push would
  duplicate incidents.

## 4. Consequences

- **Code:**
  - `HandleAlertNotification` becomes an application use case shared by the webhook and the reconciliation (today the
    translation lives inside `adapters/inbound/http.py`).
  - New `AlertSourcePort` with an Alertmanager adapter.
  - `ReconcileFiringAlerts` runs in the scheduler, controlled by `reconcile_firing_alerts` in `schedules.yaml`.
- **Deployment (T-0022):**
  - per host: `argus-v18-alertmanager`, `argus-v18-node-exporter`, `argus-v18-cadvisor` (memory limits, images for
    ARM64);
  - Prometheus `alerting:` to the local Alertmanager;
  - vm-166: Alertmanager on a loopback port, plus one more `-L` forward in `argus-v18-tunnel` and one more
    `permitopen` destination in the tunnel account's `authorized_keys`;
  - `infrastructure/environment.md`: the new objects and ports.
- **Other sections:** §3.2, §3.3, §3.5, §3.6, §4.2, §4.3 (cAdvisor's read-only mounts), §7.3, §8.1, §17.1, §25 OD-16;
  `OPEN_PROBLEMS.md` D-001 → decided.
- **Risk:**
  - Pull adds latency: an alert reaches Argus within one reconciliation interval (configured, default 60 s), on top
    of Prometheus' `for:` window.
  - If the scheduler is down, alerts wait until it is back; Alertmanager keeps them firing, so none is lost.
  - `cadvisor`'s read-only mounts give it root-equivalent read visibility on the host; it is upstream code, it has no
    network path from Host A except Prometheus' scrape, and its memory is limited.
- **How to reverse it:** select `direct-private` (or `wireguard-overlay`) when the network allows it, enable the
  webhook route in Alertmanager, and keep reconciliation as the backup. The identity rule makes the switch free of
  duplicates. Reverting the text restores the single-transport wording of 1.8.1.
- **Safety principle touched?** **yes — host isolation (the cross-host path).** The profiles keep every existing
  control (per-service credentials, no public exposure, no cross-host executor fallback). `restricted-ssh` stays
  forward-only, and pull adds no new direction. A second team member's approval is required.

## 5. Decision

Decided by `conantkd` on 2026-10-08, D-001 option B, in these words:

> Adopt a portable transport profile architecture. For the current deployment, Argus uses the restricted-ssh profile:
> an encrypted, forward-only SSH tunnel over port 22, with a shell-less account, pinned host key, exact permitopen
> destinations and target services bound to loopback only. Firing alerts are reconciled by pull through that tunnel.
>
> The architecture does not require SSH specifically. A deployment selects one explicit transport profile:
> direct-private (private addresses plus firewall restrictions); wireguard-overlay (an Argus-owned WireGuard interface,
> keys and firewall rules); restricted-ssh (the portable fallback when only SSH is available).
>
> The selected profile is configuration, never automatic detection or fallback. All profiles preserve per-service
> credentials, host-qualified inventory, no public exposure and no cross-host executor fallback.
>
> Alert delivery is profile-dependent: push webhook is allowed when the selected transport offers bidirectional
> connectivity; restricted-ssh uses scheduler-driven pull/reconciliation.

Also decided by `conantkd` (2026-10-08) for phase 7:
- the pull reads **Alertmanager**, not Prometheus `ALERTS`;
- the host and container exporters are **Argus-owned** (`argus-v18-node-exporter`, `argus-v18-cadvisor`), not the
  protected deployment's.

D-001 required the whole team: the second approval (`juanbetancurm`) in the PR completes it.

## 6. Applied

- [x] `ARCHITECTURE.md` updated, version 1.8.3, changelog line added (with this ACR's link) — on `task/T-0022-alerting`
- [ ] journal entry
- [ ] the ACR, the architecture change and the first code that needs it are in the same pull request
