"""ACR-0018 §18 / phase 16: security events raise an alert through the Argus-owned Alertmanager to the team's route.

The scheduler posts each new alerting audit row to the home host's Alertmanager with `argus_security="true"`; the
alert names the event, the actor, the time and the row, never the row's detail. Argus's own intake skips those alerts.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

from argus.adapters.outbound.alerts_alertmanager import AlertmanagerSource
from argus.adapters.outbound.sqlite_store import SqliteStore
from argus.domain.model import AuditRecord
from argus.infrastructure.scheduler import load_security_alerts
from argus.infrastructure.security_alerts import ALERT_EVENTS, SecurityAlerts

ROOT = Path(__file__).resolve().parents[1]
UTC = timezone.utc
NOW = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)


@pytest.fixture
def store(tmp_path):
    return SqliteStore(str(tmp_path / "alerts.db"))


@pytest.fixture
def inventory():
    from argus.adapters.outbound.config_adapters import YamlInventory
    return YamlInventory((ROOT / "config" / "inventory.yaml").read_text(encoding="utf-8"))


def add(store, n: int, event: str, minutes_ago: int, detail: dict | None = None) -> None:
    store.append(AuditRecord(audit_id=f"aud_{n:04d}", incident_id=None, at=NOW - timedelta(minutes=minutes_ago),
                             category=event.split(".")[0], event=event, actor=f"user{n}", detail=detail or {}))


class Alertmanager:
    def __init__(self, status: int = 200):
        self.posts, self.status = [], status

    def client(self) -> httpx.Client:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "POST" and request.url.path == "/api/v2/alerts"
            self.posts.append(json.loads(request.content))
            return httpx.Response(self.status)
        return httpx.Client(transport=httpx.MockTransport(handler))


def job(store, am: Alertmanager, clock=lambda: NOW) -> SecurityAlerts:
    return SecurityAlerts(store, "http://argus-v18-alertmanager:9093", client=am.client(), clock=clock)


def test_an_alerting_event_is_posted_with_the_security_label_and_no_detail(store):
    store.upsert_principal("user1", "human", "operator", ["lab"], "x")
    add(store, 1, "access.login_locked", 5, {"address": "a" * 8})
    am = Alertmanager()
    assert job(store, am).run_once() == "1 security alert(s) sent"
    [alert] = am.posts[0]
    assert alert["labels"] == {"alertname": "ArgusSecurityEvent", "argus_security": "true",
                               "event": "access.login_locked", "audit_id": "aud_0001"}
    assert alert["annotations"]["summary"] == "access.login_locked by user1 at 2026-10-26 11:55:00Z"
    assert "a" * 8 not in json.dumps(alert)                       # the detail (an address) never leaves
    assert alert["endsAt"] > alert["startsAt"]


def test_an_actor_that_is_not_a_known_principal_is_never_sent(store):
    """A locked login's actor is whatever was typed in the username box: an attacker's text or a password typed in the
    wrong field. Only a principal the store knows is named."""
    store.append(AuditRecord(audit_id="aud_0001", incident_id=None, at=NOW - timedelta(minutes=5), category="access",
                             event="access.login_locked", actor="hunter2-typed-by-mistake", detail={}))
    am = Alertmanager()
    job(store, am).run_once()
    [alert] = am.posts[0]
    assert alert["annotations"]["summary"] == "access.login_locked by unknown at 2026-10-26 11:55:00Z"
    assert "hunter2" not in json.dumps(alert)


def test_ordinary_events_do_not_alert(store):
    add(store, 1, "access.login", 5)
    add(store, 2, "security.audit_chain_verified", 4)
    am = Alertmanager()
    assert job(store, am).run_once() == "0 security alert(s)"
    assert am.posts == []


def test_a_row_is_posted_once_and_a_later_row_on_the_next_pass(store):
    add(store, 1, "security.audit_chain_broken", 10)
    am = Alertmanager()
    alerts = job(store, am)
    alerts.run_once()
    assert alerts.run_once() == "0 security alert(s)"
    add(store, 2, "security.session_refused", 1)
    alerts.run_once()
    assert [[a["labels"]["audit_id"] for a in post] for post in am.posts] == [["aud_0001"], ["aud_0002"]]


def test_a_failed_post_is_sent_again_on_the_next_pass(store):
    add(store, 1, "security.audit_digest_failed", 3)
    down = Alertmanager(status=503)
    alerts = job(store, down)
    with pytest.raises(httpx.HTTPStatusError):
        alerts.run_once()
    alerts.client = Alertmanager().client()
    assert alerts.run_once() == "1 security alert(s) sent"


def test_a_restart_looks_back_one_hour_only(store):
    add(store, 1, "access.sessions_revoked", 90)
    add(store, 2, "access.sessions_revoked", 30)
    am = Alertmanager()
    job(store, am).run_once()
    assert [a["labels"]["audit_id"] for a in am.posts[0]] == ["aud_0002"]


def test_the_alerting_events_are_the_ones_the_code_records():
    assert len(set(ALERT_EVENTS)) == len(ALERT_EVENTS)
    sources = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "argus").rglob("*.py"))
    for event in ALERT_EVENTS:
        prefix, name = event.split(".", 1)
        assert name in sources, event                             # a renamed event would never alert


def test_intake_skips_argus_security_alerts():
    items = [{"labels": {"alertname": "ArgusSecurityEvent", "argus_security": "true", "event": "x"},
              "fingerprint": "f1", "startsAt": "2026-10-26T12:00:00Z"},
             {"labels": {"alertname": "HostDown", "argus_host": "vm-095"},
              "fingerprint": "f2", "startsAt": "2026-10-26T12:00:00Z"}]
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=items)))
    got = AlertmanagerSource({"vm-095": "http://am:9093"}, client=client).firing_alerts("vm-095")
    assert [a.fingerprint for a in got] == ["f2"]


def test_the_schedule_entry_names_a_host_with_an_alertmanager(inventory):
    assert load_security_alerts("", inventory) is None
    assert load_security_alerts("security_alerts: {enabled: false, host: vm-095}", inventory) is None
    every, url = load_security_alerts("security_alerts: {enabled: true, every_s: 60, host: vm-095}", inventory)
    assert every == 60 and url == "http://argus-v18-alertmanager:9093"
    for bad, error in (("{enabled: true, host: nowhere}", "not an inventory host"),
                       ("{enabled: true, host: vm-095, every_s: 5}", "below the minimum"),
                       ("{enabled: true, host: vm-095, to: x}", "unknown field")):
        with pytest.raises(ValueError, match=error):
            load_security_alerts(f"security_alerts: {bad}", inventory)


def test_the_shipped_schedule_file_alerts_every_minute_through_vm_095(inventory):
    text = (ROOT / "deploy" / "scheduler" / "schedules.yaml").read_text(encoding="utf-8")
    assert load_security_alerts(text, inventory) == (60, "http://argus-v18-alertmanager:9093")


# --- the egress allowlist and the team's route (deploy files) ----------------------------------------------------------
def _yaml(*parts):
    import yaml
    return yaml.safe_load((ROOT.joinpath(*parts)).read_text(encoding="utf-8"))


def test_the_scheduler_has_no_route_out_but_the_egress_proxy():
    core = _yaml("deploy", "vm-095", "compose.core.yml")
    sched = core["services"]["argus-v18-scheduler"]
    assert sched["networks"] == ["argus-v18-sched"]
    assert core["networks"]["argus-v18-sched"]["internal"] is True
    assert sched["environment"]["HTTPS_PROXY"] == "http://argus-v18-egress:8888"
    egress = core["services"]["argus-v18-egress"]
    assert egress["networks"] == ["argus-v18-sched", "argus-v18-core"] and egress["read_only"] is True
    for name in ("argus-v18-postgres", "argus-v18-tunnel"):                  # what the scheduler reads stays reachable
        assert "argus-v18-sched" in core["services"][name]["networks"]
    join = _yaml("deploy", "monitoring", "compose.core-join.yml")["services"]
    assert all("argus-v18-sched" in join[n]["networks"] for n in ("argus-v18-prometheus", "argus-v18-alertmanager"))
    neighbours = set(sched["environment"]["NO_PROXY"].split(",")) - {"localhost"}
    assert neighbours == {"argus-v18-postgres", "argus-v18-tunnel", "argus-v18-prometheus", "argus-v18-alertmanager"}


def test_the_proxy_tunnels_https_to_oci_and_telegram_only():
    import re
    egress = ROOT / "deploy" / "vm-095" / "egress"
    rules = [line for line in (egress / "filter").read_text(encoding="utf-8").splitlines() if line]
    assert rules == [r"^objectstorage\.[a-z0-9-]+\.oraclecloud\.com$", r"^api\.telegram\.org$"]
    allowed = lambda host: any(re.search(r, host) for r in rules)
    assert allowed("objectstorage.eu-frankfurt-1.oraclecloud.com") and allowed("api.telegram.org")
    for host in ("api.openai.com", "objectstorage.x.oraclecloud.com.evil.example", "evil-api.telegram.org", "github.com"):
        assert not allowed(host), host
    conf = (egress / "tinyproxy.conf").read_text(encoding="utf-8")
    for line in ("FilterDefaultDeny Yes", "ConnectPort 443", "FilterType ere", "Allow 172.30.4.0/24"):
        assert line in conf.splitlines()


def test_vm_095s_alertmanager_sends_security_events_to_telegram_and_nothing_else():
    cfg = _yaml("deploy", "monitoring", "alertmanager-vm-095.yml")
    [route] = cfg["route"]["routes"]
    assert route == {**route, "matchers": ['argus_security="true"'], "receiver": "team-telegram"}
    receivers = {r["name"]: r for r in cfg["receivers"]}
    assert set(receivers) == {"argus-pull", "team-telegram"} and len(receivers["argus-pull"]) == 1   # host alerts: pulled
    [tg] = receivers["team-telegram"]["telegram_configs"]
    assert tg["bot_token_file"].startswith("/etc/alertmanager/secrets/") and "bot_token" not in tg   # never in Git
    assert tg["chat_id_file"].startswith("/etc/alertmanager/secrets/") and "chat_id" not in tg
    assert tg["http_config"] == {"proxy_url": "http://argus-v18-egress:8888"}
    join = _yaml("deploy", "monitoring", "compose.core-join.yml")["services"]["argus-v18-alertmanager"]
    assert "./alertmanager-vm-095.yml:/etc/alertmanager/alertmanager.yml:ro" in join["volumes"]


def test_a_refused_console_use_reaches_the_telegram_route(store):
    """T-0016: the operator console's refusal (security.console_refused) is posted like any security event: the
    Alertmanager route `argus_security="true"` sends it to the team's Telegram receiver, without the row's detail."""
    import yaml
    store.upsert_principal("user7", "human", "viewer", ["lab"], "x")
    add(store, 7, "security.console_refused", 2, {"reason": "role viewer lacks the permission investigate",
                                                  "path": "/api/v1/ops/console/incidents/inc_1/sessions"})
    am = Alertmanager()
    assert job(store, am).run_once() == "1 security alert(s) sent"
    [alert] = am.posts[0]
    assert alert["labels"]["argus_security"] == "true" and alert["labels"]["event"] == "security.console_refused"
    assert alert["annotations"]["summary"] == "security.console_refused by user7 at 2026-10-26 11:58:00Z"
    assert "/api/v1/ops/console" not in json.dumps(alert)
    route = yaml.safe_load((ROOT / "deploy/monitoring/alertmanager-vm-095.yml").read_text(encoding="utf-8"))["route"]
    [telegram] = [r for r in route["routes"] if r["receiver"] == "team-telegram"]
    assert telegram["matchers"] == ['argus_security="true"']
