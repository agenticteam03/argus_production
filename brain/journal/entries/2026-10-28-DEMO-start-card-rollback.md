## 2026-10-28 - container.start names no rollback its own service card forbids

Type: fix
Who: conantkd (+ agent)
Context: the S1 online rehearsal (8 incidents, main `dc884fc`) ended in 8 judge `doubt`s. Its reasons agreed that the
cache is the cause; one that repeated was "rollback by stopping the cache could recreate the outage and conflicts with the
service card's never-stop constraint". It is true: `config/actions/container.start.yaml` declared
`rollback: container.stop`, while the cache's service card in `config/inventory.yaml` says `never: [container.stop]`.
The approver was shown a way back that the service forbids.
Decision / result:
- `config/actions/container.start.yaml`: `rollback` is now "none: the previous state is the unavailable service
  itself", with the reason in a comment. The state before a start is the outage, and stopping the service again is the
  action its service card forbids. `none` is the convention of `container.restart` and `network.restore`.
- Effect: `rollback` only feeds the approval screen's "Reversible: yes/no" (a rollback that is a catalogue action is
  reversible, `_reversible`) and the text the judge reads. It does not enter the risk colour, which comes from
  `config/risk.yaml`. A start now shows "Reversible: no".
- `tests/test_action_card_rollback.py` fails for any action card whose rollback is a catalogue action that a service
  card lists as `never` on a target where that action is `safe`, so the clash cannot return.
Consequences: the judge no longer reads the contradiction. It may still doubt for its other reasons (why the cache
exited, the verification being one layer, an exit-code conflict between a metric and a container read); those are not
changed here. The cards are read at worker start, so the worker, agent and scheduler are rebuilt on deploy.
References: [demo plan](../../tasks/current/DEMO-argus-acts.md), ACR-0019 sections 3.4 and 3.10.

### Test state

Two new tests, both red without the change. The card, suggestion, remediation, approval view, execution, S2 card, UI
contract and class registry files pass locally; CI is the full check.

### Next step

Merge, rebuild vm-095's worker, agent and scheduler, and repeat S1 online.
