# Argus v1.8: targets, incidents and how to run them

How to ask Argus to investigate something on the two VMs, from **Swagger** or the **CLI**. It covers:
- the targets Argus knows;
- the incident classes it can diagnose;
- the synthetic incidents (scenarios) you can trigger, with expected results;
- how to reset each one.

Argus is **read-only**. It never restarts, deletes or changes anything. Remediation is a recommendation
for a human. The write gate is closed.

---

## 1. Where to run it

| Interface | How to open it |
|---|---|
| **Swagger** | On the laptop, open a tunnel and leave it open: `ssh -N -L 18000:127.0.0.1:18000 argus-vm095` (SSH alias for VM 0.95 in your `~/.ssh/config`). Then browse to **http://127.0.0.1:18000/docs** |
| **CLI** (formatted) | On VM 0.95: `sudo docker exec -it -e ARGUS_USER=<your-github-handle> argus-v18-agent argus diagnose <target> --reason "<what you see>"` |
| **CLI** (raw JSON) | The same command with `--raw`. To view a finished incident: `... argus incident <incident_id> [--raw]` |

### 1.1 Swagger, step by step

1. Click **Authorize**. Enter your GitHub handle as the username and the team's shared password, leave the other fields empty, then
   click **Authorize** and **Close**. The token lasts 30 minutes; after that, authorize again.
2. Open **POST `/api/v1/investigations`**, click **Try it out**, paste one of the bodies from §4, and
   click **Execute**. The response is `202` with `{"incident_id": "inc_…", "status": "queued"}`.
3. Copy the `incident_id`. Then use these endpoints:
   - **GET `/api/v1/incidents/{incident_id}`**: the result. It has `status`, `outcome`,
     `incident_class`, `diagnosis`, `root_cause_target`, `findings`, plus `evidence` and `audit`.
   - **GET `/api/v1/incidents/{incident_id}/events`**: the stage-by-stage run (detect, recall,
     investigate, act, record). This is the same data the CLI shows.
   - **GET `/api/v1/incidents`**: the latest incidents.

A model-driven run takes about 1 to 3 minutes. Re-run GET until `status` is `closed` or `escalated`.

### 1.2 Request body fields

```json
{
  "target": "vm-166/container:argus-lab-worker",
  "reason": "keeps restarting",
  "request_kind": "report"
}
```

| Field | Meaning |
|---|---|
| `target` | **`<host>/<kind>:<name>`**. The host is always part of the name: `argus-lab-api` exists on **both** VMs, and `vm-095/…` and `vm-166/…` are different targets. It must be one of the targets in §2, or Argus refuses it |
| `reason` | What a human observed. It is stored as evidence (`reported_symptom`) and used for runbook recall |
| `request_kind` | **`check`** asks "is it healthy?": if nothing matches, it ends quietly as `no_incident`. **`report`** says "there is a problem": if no class matches, it escalates with an evidence pack and no model call |
| `idempotency_key` | Optional. **Delete this line**, or use a new string every time. Reusing a key returns the existing incident with `"duplicate": true` and starts nothing new |

---

## 2. Targets Argus knows (`config/inventory.yaml`)

| Target | Host | What it is | Normal state |
|---|---|---|---|
| `vm-166/container:argus-lab-api` | VM 0.166 | small HTTP api; **depends on** `argus-lab-cache` (TCP 6379) | always on, healthy |
| `vm-166/container:argus-lab-cache` | VM 0.166 | redis (memory only, tmpfs) | always on |
| `vm-166/container:argus-lab-db` | VM 0.166 | PostgreSQL, **for testing only** (a production deployment points the db-probe at its real database instead); 20 connection slots, memory only. Read by `inspect_database_health`; used by **SC-04** | always on, healthy |
| `vm-166/container:argus-lab-client` | VM 0.166 | calls its backend every 5 s; **depends on** `argus-lab-backend` (TCP 8080). Used by **SC-07** | absent until the scenario starts |
| `vm-166/container:argus-lab-leaker` | VM 0.166 | holds database sessions idle in transaction; **depends on** `argus-lab-db` (TCP 5432). Used by **SC-04** | absent until the scenario starts |
| `vm-166/container:argus-lab-backend` | VM 0.166 | small HTTP api on the network `argus-lab-iso`. Used by **SC-07** | absent until the scenario starts |
| `vm-166/container:argus-lab-worker` | VM 0.166 | worker used by **SC-01** | absent until the scenario starts |
| `vm-166/host:vm-166` | VM 0.166 | the host itself (mounts `/`, `/srv/argus-lab-fill`) | up |
| `vm-095/container:argus-lab-api` | VM 0.95 | the **twin**: same name as vm-166's api, but no dependency | always on, healthy |
| `vm-095/container:argus-lab-worker` | VM 0.95 | worker used by **SC-02** (same name as vm-166's!) | absent until the scenario starts |
| `vm-095/host:vm-095` | VM 0.95 | the host itself (mount `/`) | up |

Anything else, such as `vm-166/container:nginx` or the pre-existing WireGuard deployment's `argus-api-1`, is **refused before anything
is read** (outcome `refused`, audited). Argus only reads what the inventory lists.

---

## 3. Incident classes (what Argus can diagnose today)

Detection reads the **target host's own Prometheus**. Every series carries the label `argus_host`.

| Class | Detected when (signals over the last 10 min) | Runbooks recalled | Strategy |
|---|---|---|---|
| `container_restart_loop` | the container restarted **≥ 3 times**. Findings include `OOMKilled` and the last exit code | **RB-001** (OOM restart loop), **RB-008** (non-OOM crash loop) | `model_loop` (the AI model reads evidence through guarded tools) |
| `dependency_unavailable` | a declared dependency probe fails (`dependency_probe_min < 1`) | **RB-003**, branches RB-004, RB-009 | `model_loop` |
| `health_check_failed` | Docker health check is `unhealthy` | **RB-002**, branch RB-003 | `model_loop` |

If several classes match, the first one in this order becomes the incident class. The others become
findings. Host targets (`…/host:…`) have no class yet.

**Outcomes:**

| Outcome | Meaning |
|---|---|
| `no_incident` | `check` request and everything is healthy. No model call |
| `diagnosed` | a class matched and the model produced a cited diagnosis (`root_cause_target`, evidence IDs) |
| `unsupported_escalated` | `report` request, but no class matches. Argus collects an evidence pack and escalates to a human, with no model call and no guessing |
| `undiagnosable` | the host's metrics are stale or unavailable (see RB-014). Argus escalates with an evidence pack |
| `no_action_escalated` | the investigation ended without a diagnosis (step budget or model error). Argus escalates with the evidence collected |
| `refused` | the target is not in the inventory. Nothing was read |

---

## 4. Incidents you can run now

One failure at a time. Always run the **reset** step afterwards. Then, on the VM where the scenario
ran, `sudo bash /opt/argus-v18/app/ops/nonint-check.sh after` must print **NO INTERFERENCE**.

### H-1 / H-2: healthy checks (no failure needed)

```json
{"target": "vm-166/container:argus-lab-api", "reason": "is it healthy?", "request_kind": "check"}
```
```json
{"target": "vm-095/container:argus-lab-api", "reason": "is it healthy?", "request_kind": "check"}
```
**Expected:** `no_incident` for both, each attributed to its own host, with no model call.
Verified 2026-10-01.

---

### SC-01: OOM restart loop on vm-166

The worker grows its memory until its own 64 MiB limit kills it (exit 137), then restarts.

**Start** [VM 0.166 · bash], then wait until there are 3 or more restarts (about 1 to 2 minutes):
```bash
cd /opt/argus-v18/app/deploy/lab && sudo docker compose -f compose.lab.yml --profile sc01 up -d argus-lab-worker-oom && cd ~
sudo docker inspect -f 'restarts={{.RestartCount}} oom={{.State.OOMKilled}}' argus-lab-worker
```
**Investigate:**
```json
{"target": "vm-166/container:argus-lab-worker", "reason": "keeps restarting", "request_kind": "report"}
```
**Expected:**
- detect: `container_restart_loop` (restarts ≥ 3, OOMKilled=True, exit 137);
- recall: RB-001 first;
- act: tools read **vm-166** only;
- record: `diagnosed`, with "killed by its own memory limit; growth each cycle; restart only helps
  temporarily", plus a human recommendation (raise the limit or fix the leak). Nothing is executed.

Verified 2026-10-01 (Tasks 7 and 9; the exporter now reads the last exit from Docker events).

**Reset** [VM 0.166 · bash]:
```bash
cd /opt/argus-v18/app/deploy/lab && sudo docker compose -f compose.lab.yml --profile sc01 rm -sf argus-lab-worker-oom && cd ~
```

---

### SC-02: non-OOM crash loop on vm-095 (same container name as SC-01)

The worker exits with code 1 at start because its configuration file is missing.

**Start** [VM 0.95 · bash], then wait until there are 3 or more restarts:
```bash
cd /opt/argus-v18/app/deploy/lab && sudo docker compose -f compose.lab.yml --profile sc02 up -d argus-lab-worker-crash && cd ~
sudo docker inspect -f 'restarts={{.RestartCount}} oom={{.State.OOMKilled}} exit={{.State.ExitCode}}' argus-lab-worker
```
**Investigate:**
```json
{"target": "vm-095/container:argus-lab-worker", "reason": "keeps restarting", "request_kind": "report"}
```
**Expected:**
- detect: `container_restart_loop` (OOMKilled=False, exit 1);
- recall: RB-008 first;
- logs show `FATAL: config file not found: /etc/worker/config.yml`;
- record: `diagnosed` as a non-OOM crash from missing configuration on **vm-095**. It must **not** be
  confused with SC-01.

**Reset** [VM 0.95 · bash]:
```bash
cd /opt/argus-v18/app/deploy/lab && sudo docker compose -f compose.lab.yml --profile sc02 rm -sf argus-lab-worker-crash && cd ~
```

**Identity proof (SC-01 + SC-02 at the same time):** start both, then investigate both targets. Expected
result: two incidents and two different diagnoses, each read only from its own host. SC-02 and the identity
proof were verified on 2026-10-01 (Task 8).

---

### SC-03: dependency unavailable on vm-166

`argus-lab-api` needs `argus-lab-cache`. Stopping the cache makes the api the **victim**, not the cause.

**Start** [VM 0.166 · bash], then wait about 1 minute for the probe to fail:
```bash
sudo docker stop argus-lab-cache
```
**Investigate:**
```json
{"target": "vm-166/container:argus-lab-api", "reason": "api returns errors", "request_kind": "report"}
```
**Expected:**
- detect: `dependency_unavailable` (and maybe `health_check_failed` as a finding);
- recall: RB-003;
- record: `diagnosed` with **`root_cause_target` = `vm-166/container:argus-lab-cache`**. The api is a
  victim, and Argus should not suggest restarting it. Verified 2026-10-01 (Task 9).

**Reset** [VM 0.166 · bash]:
```bash
sudo docker start argus-lab-cache
```

---

### SC-04: a worker leaks database sessions (vm-166)

`argus-lab-leaker` connects to `argus-lab-db` (testing only) as the ordinary role `argus_lab_app` and opens 16
sessions, each with a transaction it never ends (`idle in transaction`). That is 16 of the 17 usable connection
slots (94 %): new ordinary clients would soon be rejected. Restarting the database would only hide the defect: the
cause is the client that holds the sessions.

**Start** [VM 0.166 · bash], then wait about 5 minutes (the signal is the slot usage sustained for 5 minutes, and the
alert `DbConnectionsExhausted` fires after 5 minutes at 90 % or more):
```bash
cd /opt/argus-v18/app/deploy/lab && sudo docker compose -f compose.lab.yml --profile sc04 up -d argus-lab-leaker
```
**Investigate:**
```json
{"target": "vm-166/container:argus-lab-db", "reason": "clients cannot get a database connection", "request_kind": "report"}
```
**Expected:**
- detect: `postgresql_connection_exhaustion` (94 % of the usable slots for 5 minutes);
- recall: RB-004 (branch RB-013);
- investigate: `inspect_database_health` shows 16 sessions `idle in transaction` from `argus-lab-leaker` /
  `argus_lab_app` and the age of the oldest open transaction;
- record: `diagnosed`, root cause `vm-166/container:argus-lab-leaker` (sessions held idle in transaction), and
  **no restart of the database advised**.

**Reset** [VM 0.166 · bash] (its sessions close with it; never `compose down`, which would remove the whole lab):
```bash
sudo docker rm -f argus-lab-leaker
```

---

### SC-07: a healthy backend on the wrong network (vm-166)

`argus-lab-client` (network `argus-lab-app`) calls `argus-lab-backend`, which is healthy but attached **only** to
`argus-lab-iso` (172.30.3.0/24). Docker's DNS on the client's network does not know the backend's name. Restarting
anything would not help: the fix is the network attachment.

**Start** [VM 0.166 · bash], then wait about 1 minute for the probe to fail:
```bash
cd /opt/argus-v18/app/deploy/lab && sudo docker compose -f compose.lab.yml --profile sc07 up -d
```
**Investigate:**
```json
{"target": "vm-166/container:argus-lab-client", "reason": "the client cannot reach its backend", "request_kind": "report"}
```
**Expected:**
- detect: `dependency_unavailable`;
- recall: RB-003; during the investigation the model can read the branch runbook RB-009 with `query_runbook`;
- investigate: the container status shows each side's `networks`; DNS and TCP to the backend fail from vm-166's
  app network;
- record: `diagnosed`, root cause `vm-166/container:argus-lab-backend` not attached to the client's network, and
  **no restart advised**. Verified 2026-10-07 (T-0018): `inc_fb92d115abb2`, and `inc_21f900ee6139` with RB-009
  read through `query_runbook`.

**Reset** [VM 0.166 · bash]:
```bash
sudo docker rm -f argus-lab-client argus-lab-backend && sudo docker network rm argus-lab-iso
```

---

### SC-09: report with no matching class (healthy target)

**Investigate:**
```json
{"target": "vm-095/container:argus-lab-api", "reason": "users see stale data", "request_kind": "report"}
```
**Expected:** `unsupported_escalated`, with an evidence pack collected, **no model call and no
diagnosis**. Argus does not guess outside its registered classes. No reset is needed.

---

### SC-11: identity guard (refusals)

```json
{"target": "vm-166/container:argus-api-1", "reason": "check", "request_kind": "report"}
```
**Expected:** `refused`: "not in the inventory; nothing was read" (audited). A body without a host,
such as `"target": "container:argus-lab-api"`, is rejected with **422** before any incident is created.

---

## 5. Planned (not implemented yet)

| ID | Incident | Host | Missing piece |
|---|---|---|---|
| SC-05 | disk almost full (256 MiB loop mount) | vm-166 | loop mount + `disk_pressure` class |
| SC-06 | CPU saturation (capped burner) | vm-166 | `cpu_saturation` class |
| SC-08 | nginx upstream failure | vm-166 | nginx + slow api + class |
| SC-10 | monitoring blind spot (exporter stopped) | vm-095 | scripted in code.bash Task 10, not yet verified |
| SC-12 | executor partition (gateway stopped) | vm-166 | scripted in code.bash Task 10, not yet verified |

Full catalogue: `AAbrainProject/plans/argus-v1.8-two-vm-plan.md` §7.1.
