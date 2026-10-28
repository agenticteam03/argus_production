## 2026-10-28 - An incident shows its supervised action and who approved it, and a slow restart is confirmed

Type: fix
Who: conantkd (+ agent)
Context: the S4 rehearsal on vm-166 (main `7e9028e`) ran end to end. The judge agreed, conantkd approved on the
private path at 12:48:56Z, and the gateway restarted the worker at 12:53:16Z. The worker processed again at the next
scrape (12:53:35Z) and the queue drained. Three gaps showed:
- `docker restart` took 10.7 s (Docker waits up to 10 s to stop, then starts), and both Unix hops in the gateway
  waited 10 s. The gateway answered "pending reconciliation", its journal stayed `received`, and Argus recorded the
  action `indeterminate` and the incident `indeterminate_escalated`. A restart that happened was reported as unknown.
- The approval's audit line (`action.approval_answered`) had no incident, so the incident's page never showed it.
- The execution left no audit line at all.
Decision / result:
- `services/action_gateway/unix_transport.py`: proxy -> Docker waits 20 s and gateway -> proxy 25 s.
  `argus/actions/gateway_client.py`: the Argus client waits 30 s. Each hop waits longer than the one below it.
- `argus/adapters/inbound/http.py` / `argus/application/holds.py`: the approval's audit line carries its proposal's
  incident. `argus/orchestration/graph_runner.py`: `action.executed` names the approval, who approved it, the
  capability, the target, the action id and its state; `action.verified` names the outcome. A failing approver lookup
  only shortens the line.
- `argus/application/incident_action.py` and the incident detail route: for an operator, `action` holds the newest
  proposal, the judge's verdict and reasons, the approval (state, who answered, when), the execution state and the
  outcome. It has no token, digest or gateway journal, and it appears only while the action routes are mounted.
- `frontend/src/components/ActionTrail.jsx`: the incident's Overview shows that trail as five read-only steps
  (proposal, judge, operator approval, execution, verification), with no control. Approving stays on Actions.
Consequences: the gateway image on vm-166 and vm-095's services are rebuilt after this merges; S1 is repeated.
References: [demo plan](../../tasks/current/DEMO-argus-acts.md), ACR-0019, ACR-0018 section 18.

### Test state

New, each red without the change: the nested timeouts (`test_phase19_gateway_client`), `action.executed` and
`action.verified` with the approver and a failing lookup that never stops the action (`test_phase18_graph`), and the
approval on the incident's audit plus the page's action trail (`test_incident_action_trail`). `ActionTrail.test.jsx`
has 3 tests. The phase 18, 19 and 20 files, the UI contract and the page tests pass locally; ruff and eslint are clean.

### Next step

Merge, rebuild the gateway on vm-166 and vm-095's services, and repeat S1.
