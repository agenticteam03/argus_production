## 2026-10-16 — DEMO: `argus demo`, a paced replay of a recorded investigation for live presentations

Type: tooling (no architecture change)
Who: conantkd (+ agent)
Context: a 3-minute live demo with a narrator: the failure, then the investigation, stopping where the human approval
(HITL) is not implemented yet. The real run takes 0.26 s, so it cannot be shown live as it is.
Decision / result: `argus demo` replays the real run events of a recorded OOM restart-loop run
(`contracts/samples/events.json`) through the existing CLI `Formatter`, slowed so it fills `--duration` seconds
(default 180). It opens with the failure and closes with a panel labelled "preview" (the proposal, from RB-001 step 7)
and the pending nodes `propose_action … verify`. It is stdlib only and offline (no API, model or host), so on a VM it
runs as `python3 -m argus.adapters.inbound.cli.demo` from a plain checkout, without touching the deployed app.
Consequences: the proposal shown is NOT agent output until `propose_action` exists; the panel says so.
References: `argus/adapters/inbound/cli/demo.py`, `tests/test_demo_cli.py`.

### Test state

`tests/test_demo_cli.py` 5 passed (red seen first: module missing); full suite green.

### Next step

When `propose_action` / `request_approval` exist, replace the preview panel with the real events.
