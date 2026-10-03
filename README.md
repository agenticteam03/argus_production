# Argus

Argus is an SRE incident-diagnosis agent for servers and containers. When an alert fires, a schedule ticks or an
operator asks, it detects the symptom deterministically, recalls runbooks, investigates with narrow, read-only,
audited tools, and concludes or escalates to a human. It is **read-only** in this phase.

**New on the team?** Follow [`START_HERE.md`](START_HERE.md): put it in an empty folder, open your AI agent there and say
"Read START_HERE.md and follow it". The agent installs, clones and sets up everything with you.

- **Start here (developers and AI agents):** [`brain/README.md`](brain/README.md).
- Architecture: [`brain/architecture/ARCHITECTURE.md`](brain/architecture/ARCHITECTURE.md) (v1.8.x).
- Where we stand: [`brain/CURRENT_STATE.md`](brain/CURRENT_STATE.md).

## Run the tests (laptop)

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[test,dev]"
.\.venv\Scripts\pre-commit install          # Brain audit on every commit; refuses a push to main
.\.venv\Scripts\python -m pytest -q          # Postgres tests: see brain/policies/TDD.md
git config argus.developer <your-github-handle>
python brain/tools/brain.py status
```

## Layout

| Path | What |
|---|---|
| `argus/` | the agent (domain, ports, adapters, orchestration, tooling, policy) |
| `services/target/` | the per-host read gateway, probes and exporter |
| `config/` | inventory, policy, signals — canonical data |
| `deploy/` | compose files, migrations, lab workloads |
| `ops/` | operational scripts (non-interference check, migrations, checks) |
| `tests/` | offline, Postgres and `brain.py` tests |
| `brain/` | the shared project Brain: state, plan, rules, guides, journal |

The runbook library (RB-001 … RB-021) lives in `argus/runbooks/` — see its README for provenance and how to change it.
