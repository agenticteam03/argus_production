"""EVAL-2: what the model's first trial on the 55 cases showed, fixed before the five trials.

1. A stopped writer of the full filesystem is still a suspect (its data stays): `confirm_then_reason` reads its logs
   too (ACR-0008). The model alone never asked for them (`disk-filler-stopped-with-history`).
2. The model named the host as root cause while its own diagnosis said nothing proved a cause (`disk-filler-no-logs`,
   `disk-root-full-writer-elsewhere`): the system prompt says a host-level symptom is not a root cause by itself:
   the host is not named as one only because no container or process was found.
3. Two disk cases had fixtures that contradicted their own label: a read-only mount whose logs claimed the writes, and
   a "stopped with no history" filler whose log said `done`. The labels stay; the fixtures now say what the case means.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from argus.domain.model import UseReadTools
from argus.orchestration.strategies import BaselineStrategy, ConfirmThenReasonStrategy, disk_suspects
from test_e2e5_confirm_writer import FILL, FILLER, Harness, _disk, _status, _view

CASES = Path(__file__).resolve().parent / "eval" / "cases"


def test_a_stopped_rw_writer_of_the_full_filesystem_gets_its_logs_read():
    harness = Harness()
    s = ConfirmThenReasonStrategy(harness)
    d = s.next_step(_view([_disk(92.6), _status(2, FILLER, state="exited")]))
    assert isinstance(d, UseReadTools) and s.last_source == "rule" and harness.asked == 0
    assert [(c.name, c.arguments["target"]) for c in d.calls] == [("container.logs", FILLER)]   # no stats: it is down


def test_a_stopped_writer_is_read_once_then_the_model_decides():
    harness = Harness()
    s = ConfirmThenReasonStrategy(harness)
    done = UseReadTools(calls=[__import__("argus.domain.model", fromlist=["ReadCall"]).ReadCall(
        name="container.logs", arguments={"target": FILLER})])
    s.next_step(_view([_disk(92.6), _status(2, FILLER, state="exited")], decisions=[done]))
    assert harness.asked == 1 and s.last_source == "model"


def test_the_baseline_still_names_only_running_writers():
    view = _view([_disk(92.6), _status(2, FILLER, state="exited")])
    assert disk_suspects(view) == []                                    # the baseline's rule input is unchanged
    assert disk_suspects(view, include_stopped=True) == [FILLER]
    assert BaselineStrategy._confirm(view) == []


def test_the_system_prompt_says_a_host_symptom_is_not_a_root_cause():
    from argus.tooling.model_harness import SYSTEM_PROMPT
    text = " ".join(SYSTEM_PROMPT.split())
    assert "host-level symptom" in text and "is not a root cause by itself" in text
    assert "Do not name the host as the root cause only because no container or process was found" in text
    assert "can be the root cause of its own failure" in text      # a restart loop's container is its own cause
    # E.3: "escalate when the cause is only plausible" made the model escalate correct diagnoses; E.3b: a rule about
    # "the service that reported the symptom" made it escalate restart loops and failing health checks
    assert "plausible" not in text and "reported the symptom" not in text


def _case(name: str) -> dict:
    return yaml.safe_load((CASES / f"{name}.yaml").read_text(encoding="utf-8"))


def _filler_logs(case: dict) -> str:
    gateway = next(v for k, v in case["fixtures"].items() if isinstance(v, dict)
                   and "/containers/argus-lab-filler/logs" in v)
    return " ".join(gateway["/containers/argus-lab-filler/logs"]["lines"]).lower()


def test_the_read_only_case_logs_no_write_to_the_full_mount():
    case = _case("disk-filler-read-only")
    assert case["label"]["outcome"] == "no_action_escalated"
    assert "wrote" not in _filler_logs(case) and "read-only" in _filler_logs(case)


def test_the_stopped_case_logs_no_write_history():
    case = _case("disk-filler-stopped")
    assert case["label"]["outcome"] == "no_action_escalated"
    logs = _filler_logs(case)
    assert "wrote" not in logs and "done" not in logs and "nothing" in logs
    assert FILL                                                        # same mount as the other disk cases
