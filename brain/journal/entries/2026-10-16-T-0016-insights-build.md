## 2026-10-16 — T-0016: the UI image is built with the Map and Metrics calls on

Type: implementation
Who: conantkd (+ agent)
Context: PR #163 wired the frontend to ACR-0017's routes behind `VITE_ARGUS_INSIGHTS=1`, and its review left one
follow-up: the deploy build did not pass the flag, so the real UI image would still hide both tabs. The Nginx edge
already serves `GET /api/v1/topology` and `GET /api/v1/incidents/{id}/metrics`.
Decision / result: `deploy/ui/Dockerfile` sets `ENV VITE_ARGUS_INSIGHTS=1` next to `VITE_ARGUS_MOCK=0`. Reversal:
remove the line and rebuild; the UI hides the tabs again (ACR-0017, "How to reverse it").
Consequences: nothing changes on vm-095 until the image is rebuilt and the UI edge redeployed; the real-mode
click-through (Map, Metrics, Dashboard map, operator overlay) is still to be done by a person after that.
References: [ACR-0017](../../architecture/changes/ACR-0017-ui-topology-and-incident-metrics.md), PR #163,
`brain/tasks/current/T-0016-frontend.md`.

### Test state

`tests/test_acr0011_ui_edge.py::test_the_dockerfile_builds_the_map_and_metrics_calls_in`: red seen (no flag in the
Dockerfile), green after the line.

### Next step

Review and merge this PR, then redeploy the UI edge on vm-095 (lease, `code.bash`, `nonint-check.sh` before and
after) and do the real-mode click-through with `VITE_ARGUS_INSIGHTS=1`.
