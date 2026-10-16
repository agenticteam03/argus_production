"""`argus demo`: a paced, narratable replay of a recorded run that stops at the human-approval gate."""
from __future__ import annotations

import json
from pathlib import Path

from argus.adapters.inbound.cli import demo

SAMPLE = Path(__file__).resolve().parents[1] / "contracts" / "samples" / "events.json"


def _run(duration=180.0, color=False):
    events = json.loads(SAMPLE.read_text(encoding="utf-8"))
    slept, out = [], []
    demo.play(events, duration_s=duration, color=color, width=100, sleep=slept.append, write=out.append)
    return slept, "\n".join(out)


def test_total_pause_matches_requested_duration():
    slept, _ = _run(duration=180.0)
    assert abs(sum(slept) - 180.0) < 1.0


def test_shorter_duration_is_honoured():
    slept, _ = _run(duration=30.0)
    assert abs(sum(slept) - 30.0) < 1.0


def test_shows_failure_then_investigation_then_stops_at_approval_gate():
    _, text = _run()
    order = [text.index(s) for s in ("FAILURE DETECTED", "DETECT", "RECALL", "INVESTIGATE", "ACT", "RECORD",
                                     "PROPOSED ACTION", "AWAITING HUMAN APPROVAL")]
    assert order == sorted(order)
    assert "OOM-killed by its 64 MiB memory limit" in text
    assert "not implemented yet" in text
    assert "execute_write" in text                       # the pending nodes are listed, not run


def test_proposal_is_labelled_as_preview_not_agent_output():
    _, text = _run()
    assert "preview" in text.lower()


def test_no_ansi_when_color_is_off_and_ansi_when_on():
    assert "\033[" not in _run(color=False)[1]
    assert "\033[" in _run(color=True)[1]
