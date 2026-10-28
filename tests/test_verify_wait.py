"""`OfflineActionPath.verify_wait`: how much of the reviewed verification window is left."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from argus.actions.remediation import freeze_proposal
from argus.orchestration.action_path import OfflineActionPath
from test_phase18_remediation import candidate

NOW = datetime(2026, 10, 28, 20, 26, 0, tzinfo=timezone.utc)


def _path(result_at, window=120, proposal=True):
    freeze = freeze_proposal(candidate(prediction=candidate().prediction.model_copy(update={"within_seconds": window})),
                             at=NOW)
    rows = SimpleNamespace(
        get_action=lambda action_id: None if result_at == "missing" else {
            "id": action_id, "proposal_id": "prop_1", "result_at": result_at},
        get_action_proposal=lambda proposal_id: freeze if proposal else None)
    path = object.__new__(OfflineActionPath)
    path.rows, path.clock = rows, lambda: NOW + timedelta(seconds=30)
    return path


def test_the_time_left_counts_from_the_completion_of_the_action():
    assert _path(NOW).verify_wait("act_1") == 90.0                       # 120 s window, 30 s used
    assert _path(NOW.isoformat()).verify_wait("act_1") == 90.0           # a stored text timestamp reads the same


def test_it_is_never_negative_and_zero_when_anything_is_unknown():
    assert _path(NOW - timedelta(minutes=10)).verify_wait("act_1") == 0.0   # the window is over
    assert _path(None).verify_wait("act_1") == 0.0                          # not completed
    assert _path("missing").verify_wait("act_1") == 0.0                     # no such action
    assert _path(NOW, proposal=False).verify_wait("act_1") == 0.0           # no proposal
