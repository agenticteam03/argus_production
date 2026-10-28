## 2026-10-28 - A held-back proposal escalates, and the approval and escalation notices reach the team's route

Type: fix
Who: conantkd (+ agent)
Context: the second S1 rehearsal on vm-166 (main `e92052f`) diagnosed the cache as the cause for both victims and froze
a `container.start` for each. The judge answered `doubt` both times, and both incidents were recorded `closed` /
`diagnosed` with the cache still down: nobody was told, and the problem stayed. Separately, TASK-61's approval notice
(`SecurityAlerts.notify_approval_waiting`) was never handed to the worker's action path, so an approval would have
waited with no Telegram message.
Decision / result:
- `argus/orchestration/graph_runner.py`: when a frozen proposal stops before an approval (the judge does not agree,
  its review fails, or the approval request is refused), the incident is recorded `escalated` instead of `closed`. It
  keeps the `diagnosed` outcome and root cause, and its diagnosis ends with why nothing was sent. The escalation
  enters the outbox like any other. The owner asked for this: a problem that is still active must not close. This
  changes the phase 18 behaviour ("the recommendation remains visible"); it needs the team's review in this PR.
- `argus/orchestration/action_path.py`: `held_back(incident_id)` sends a notice with no detail ("an incident needs
  a person ... open the incident on the private path"); a missing or failing sender is only logged.
- `argus/infrastructure/security_alerts.py`: `notify_escalation` posts `ArgusIncidentEscalated` with
  `argus_security="true"`, so vm-095's Alertmanager routes it to the team's Telegram group like the approval notice.
- `argus/infrastructure/action_wiring.py`: both senders are built from `ARGUS_HOME_HOST`'s Alertmanager in the
  inventory. The worker reaches `argus-v18-alertmanager:9093` on `argus-v18-core` (checked: ready, HTTP 200).
- `deploy/vm-095/compose.core.yml`: the worker gets `ARGUS_HOME_HOST: vm-095`, as the agent already has.
Consequences: a proposal stopped by the judge now reaches a person. Incident escalations outside the action path still
go only to the recording outbox.
References: [demo plan](../../tasks/current/DEMO-argus-acts.md), ACR-0018 section 18, ACR-0019.

### Test state

Five new or changed assertions, each red without the change: the doubt and refused-request routes escalate and keep
the diagnosis (`test_phase18_graph`), the held-back notice carries no detail and a failing sender is only logged, the
escalation alert's labels and hold (`test_notify_approval_waiting`), and both senders built from the home host
(`test_x9_action_path_wiring`). The phase 18, 19 and 20 files pass locally; CI is the full check.

### Next step

Team review of the behaviour change, merge, redeploy vm-095's worker and repeat S1.
