"""Offline authorization contract before a terminal ticket or route exists."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from argus.application.terminal_launch import LeaseProof, LaunchRequest, TerminalLaunchPolicy, TerminalLaunchRefused


NOW = datetime(2026, 10, 25, 18, 0, tzinfo=UTC)


def request(**changes):
    values = dict(principal="conantkd", principal_kind="human", auth_session="jti_1",
                  ticket_id="tt_" + "a" * 32,
                  second_factor_ready=True, effective_permissions=frozenset({"open_terminal:vm-166"}),
                  host="vm-166", incident_id="inc_001", incident_host="vm-166",
                  reason="Repair the stopped cache", step_up_token="fresh-step-up",
                  lease=LeaseProof("lease_1", "vm-166", "conantkd", NOW + timedelta(minutes=10)))
    values.update(changes)
    return LaunchRequest(**values)


def policy(consumed):
    return TerminalLaunchPolicy({("conantkd", "vm-166"): "op-conantkd"},
                                lambda token, principal, session, obj: consumed.append((token, principal, session, obj)))


def test_valid_launch_binds_identity_host_incident_lease_and_step_up():
    consumed = []
    grant = policy(consumed).authorize(request(), at=NOW)
    assert grant.account == "op-conantkd" and grant.principal == "conantkd"
    assert grant.host == "vm-166" and grant.incident_id == "inc_001" and grant.lease_id == "lease_1"
    assert consumed == [("fresh-step-up", "conantkd", "jti_1", grant.step_up_object)]
    assert grant.step_up_object == "terminal:tt_" + "a" * 32


@pytest.mark.parametrize("change", [
    {"principal_kind": "agent"},
    {"second_factor_ready": False},
    {"effective_permissions": frozenset({"open_terminal:vm-095"})},
    {"host": "vm-095"},
    {"incident_host": "vm-095"},
    {"lease": LeaseProof("lease_1", "vm-166", "other", NOW + timedelta(minutes=10))},
    {"lease": LeaseProof("lease_1", "vm-166", "conantkd", NOW)},
    {"reason": "   "},
    {"reason": "repair\nrun hidden command"},
    {"auth_session": ""},
    {"ticket_id": "tt_unbound"},
    {"step_up_token": ""},
])
def test_refusal_precedes_step_up_consumption(change):
    consumed = []
    with pytest.raises(TerminalLaunchRefused):
        policy(consumed).authorize(request(**change), at=NOW)
    assert consumed == []


def test_step_up_failure_refuses_launch():
    def reject(*_args):
        raise ValueError("used token")

    launch = TerminalLaunchPolicy({("conantkd", "vm-166"): "op-conantkd"}, reject)
    with pytest.raises(TerminalLaunchRefused, match="step-up"):
        launch.authorize(request(), at=NOW)
