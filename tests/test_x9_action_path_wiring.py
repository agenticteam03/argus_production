"""Phase 20 (X-9): the worker builds the supervised-action path from pieces already reviewed, and only when asked.

The proposer is deterministic (no model call), narrower than ACR-0019 allows; the judge is still a second model. Every
unit here uses the repository's real action cards, inventory and runbooks.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from argus.actions.cards import load_action_cards
from argus.actions.remediation import ProposalInput, RemediationRefused
from argus.adapters.outbound.config_adapters import YamlInventory
from argus.domain.model import TargetRef
from argus.infrastructure import action_wiring as aw

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)
CACHE = "vm-166/container:argus-lab-cache"
API = "vm-166/container:argus-lab-api"
FULL_ID = "c" * 64
CARDS = load_action_cards(ROOT / "config" / "actions")
INVENTORY = YamlInventory((ROOT / "config" / "inventory.yaml").read_text(encoding="utf-8"))
PAIR = {"capability": "container.start", "target": CACHE}


def incident(cls="dependency_unavailable"):
    return SimpleNamespace(id="inc_x9", incident_class=cls, target=TargetRef.parse(API), root_cause_target=CACHE)


def candidate(action="container.start", target=CACHE):
    return {"action": action, "target": target, "text": "t", "basis": "runbook", "grounds": ["RB-003"],
            "evidence_refs": ["ev_cache"], "risk_color": "amber", "is_executable": False}


def proposer(gate=frozenset({("container.start", CACHE)}), read=None):
    read = read or (lambda inc, target: ({"state": "exited", "container_id": FULL_ID}, NOW))
    rows = SimpleNamespace(evidence_state=lambda incident_id: (7, None))
    return aw.CandidateProposer(rows=rows, inventory=SimpleNamespace(version=lambda: "inventory-1"), cards=CARDS,
                                gate_open=gate, read_status=read, policy_version="policy-1")


# --- the gate ---------------------------------------------------------------------------------------------------------
def test_the_gate_is_read_as_exact_pairs_and_anything_else_stops_the_start():
    assert aw.gate_pairs([]) == frozenset() and aw.gate_pairs(None) == frozenset()
    assert aw.gate_pairs([PAIR]) == frozenset({("container.start", CACHE)})
    for bad in ({"capability": "container.start"}, {**PAIR, "route": "x"}, {"capability": "", "target": CACHE},
                "container.start", {"capability": 1, "target": CACHE}):
        with pytest.raises(SystemExit):
            aw.gate_pairs([bad])


# --- the proposer -----------------------------------------------------------------------------------------------------
def test_the_proposer_builds_a_complete_proposal_from_the_candidate_the_card_and_a_fresh_read():
    result = proposer()(incident(), [candidate()], {})
    assert isinstance(result, ProposalInput)
    assert (result.capability, result.target, result.arguments) == ("container.start", CACHE, {})
    assert result.target_identity == {"container_id": FULL_ID}
    assert result.root_cause == CACHE and result.evidence_refs == ["ev_cache"] and result.grounds == ["runbook:RB-003"]
    assert (result.prediction.signal, result.prediction.target, result.prediction.expected) == (
        "dependency_probe_min", API, "healthy")                      # the victim recovers, not the cause alone
    assert result.prediction.within_seconds == aw.PREDICTION_WINDOW_S and result.rollback == CARDS["container.start"].rollback
    assert (result.inventory_version, result.policy_version, result.evidence_version) == ("inventory-1", "policy-1", "7")


@pytest.mark.parametrize("why, gate, inc, cand", [
    ("pair not released", frozenset(), incident(), candidate()),
    ("another pair released", frozenset({("container.start", API)}), incident(), candidate()),
    ("class has no reviewed verification signal", frozenset({("container.start", CACHE)}), incident("cpu_saturation"), candidate()),
    ("class unknown", frozenset({("container.start", CACHE)}), incident(None), candidate()),
    ("action needs arguments this proposer cannot set", frozenset({("network.restore", API)}), incident(),
     candidate("network.restore", API)),
    ("action has no card", frozenset({("container.nope", CACHE)}), incident(), candidate("container.nope")),
])
def test_the_proposer_makes_no_proposal_unless_everything_is_reviewed_and_released(why, gate, inc, cand):
    assert proposer(gate)(inc, [cand], {}) is None, why


def test_the_proposer_skips_a_candidate_whose_identity_cannot_be_read_and_takes_the_next():
    calls = []

    def read(inc, target):
        calls.append(target)
        if len(calls) == 1:
            raise RemediationRefused("a current container status is unavailable")
        return {"state": "exited", "container_id": FULL_ID}, NOW

    gate = frozenset({("container.start", CACHE), ("container.start", API)})
    result = proposer(gate, read)(incident(), [candidate(), candidate("container.start", API)], {})
    assert result.target == API and calls == [CACHE, API]
    assert proposer(gate, lambda i, t: (_ for _ in ()).throw(RemediationRefused("no")))(incident(), [candidate()], {}) is None
    assert proposer(gate, lambda i, t: ({"state": "exited"}, NOW))(incident(), [candidate()], {}) is None   # no identity


def test_the_proposer_restarts_a_stalled_worker_and_predicts_its_own_processing_rate():
    """S4: the cause and the symptom are the same container; the reviewed signal is its job throughput."""
    worker = "vm-166/container:argus-lab-jobworker"
    inc = SimpleNamespace(id="inc_s4", incident_class="worker_stalled", target=TargetRef.parse(worker),
                          root_cause_target=worker)
    cand = {**candidate("container.restart", worker), "grounds": ["RB-022"]}
    read = lambda i, t: ({"state": "running", "container_id": FULL_ID}, NOW)
    result = proposer(frozenset({("container.restart", worker)}), read)(inc, [cand], {})
    assert (result.capability, result.target, result.arguments) == ("container.restart", worker, {})
    assert result.grounds == ["runbook:RB-022"] and result.target_identity == {"container_id": FULL_ID}
    assert (result.prediction.signal, result.prediction.target) == ("jobs_processed_rate", worker)
    assert result.prediction.within_seconds == aw.PREDICTION_WINDOW_S
    assert "running" in result.rationale and "worker_stalled" in result.rationale
    assert aw.VERIFY_SIGNALS["worker_stalled"][0] == "jobs_processed_rate" and 0 < aw.VERIFY_SIGNALS["worker_stalled"][1] <= 0.1


def test_the_proposer_restores_a_wrong_network_from_inventory_and_live_status_only():
    client = "vm-166/container:argus-lab-client"
    api_info = SimpleNamespace(networks=["argus-lab-app"])
    client_info = SimpleNamespace(depends_on=[TargetRef.parse(API)])
    inventory = SimpleNamespace(version=lambda: "inventory-1", target=lambda ref: (
        api_info if str(ref) == API else client_info if str(ref) == client else None))
    rows = SimpleNamespace(evidence_state=lambda incident_id: (7, None))
    read = lambda _inc, _target: ({"state": "running", "container_id": FULL_ID,
                                   "networks": ["argus-lab-iso"]}, NOW)
    proposer = aw.CandidateProposer(rows=rows, inventory=inventory, cards=CARDS,
                                    gate_open=frozenset({("network.restore", API)}), read_status=read,
                                    policy_version="policy-1")
    inc = SimpleNamespace(id="inc_s2", incident_class="dependency_unavailable", target=TargetRef.parse(client),
                          root_cause_target=API)
    result = proposer(inc, [candidate("network.restore", API)], {})
    assert isinstance(result, ProposalInput)
    assert (result.capability, result.target, result.arguments) == (
        "network.restore", API, {"connect_network": "argus-lab-app", "disconnect_network": "argus-lab-iso"})
    assert (result.prediction.signal, result.prediction.target, result.prediction.expected) == (
        "link_ok", f"{client} -> {API}", "1")


def test_network_restore_is_held_back_when_the_incident_has_no_declared_link_to_the_target():
    api_info = SimpleNamespace(networks=["argus-lab-app"])
    inventory = SimpleNamespace(version=lambda: "inventory-1", target=lambda ref: api_info if str(ref) == API else None)
    rows = SimpleNamespace(evidence_state=lambda incident_id: (7, None))
    read = lambda _inc, _target: ({"state": "running", "container_id": FULL_ID, "networks": ["argus-lab-iso"]}, NOW)
    proposer = aw.CandidateProposer(rows=rows, inventory=inventory, cards=CARDS,
                                    gate_open=frozenset({("network.restore", API)}), read_status=read,
                                    policy_version="policy-1")
    assert proposer(incident(), [candidate("network.restore", API)], {}) is None


@pytest.mark.parametrize("declared, attached", [
    (["argus-lab-app"], ["argus-lab-app"]),
    ([], ["argus-lab-iso"]),
    (["argus-lab-app", "argus-lab-extra"], ["argus-lab-iso"]),
    (["argus-lab-app"], ["argus-lab-iso", "argus-lab-extra"]),
])
def test_network_restore_is_held_back_when_its_arguments_are_not_unambiguously_derivable(declared, attached):
    api_info = SimpleNamespace(networks=declared)
    inventory = SimpleNamespace(version=lambda: "inventory-1", target=lambda ref: api_info if str(ref) == API else None)
    rows = SimpleNamespace(evidence_state=lambda incident_id: (7, None))
    read = lambda _inc, _target: ({"state": "running", "container_id": FULL_ID, "networks": attached}, NOW)
    proposer = aw.CandidateProposer(rows=rows, inventory=inventory, cards=CARDS,
                                    gate_open=frozenset({("network.restore", API)}), read_status=read,
                                    policy_version="policy-1")
    assert proposer(incident(), [candidate("network.restore", API)], {}) is None


def test_a_job_rate_is_healthy_only_when_it_is_above_zero():
    worker = "vm-166/container:argus-lab-jobworker"

    def rate(value):
        return SimpleNamespace(snapshot=lambda t, signals: SimpleNamespace(values={"jobs_processed_rate": value},
                                                                           observed_at=NOW))
    sample = lambda value: aw.SignalSampler(rate(value))("jobs_processed_rate", worker)
    assert sample(0.5) == ("healthy", NOW) and sample(0.0)[0] == "unhealthy"


def test_link_ok_is_sampled_from_the_single_recorded_inventory_edge():
    dependent = "vm-166/container:argus-lab-client"
    rows = SimpleNamespace(link_probe_cursors=lambda owner: {API: {"state": "ok", "at": NOW}})
    info = SimpleNamespace(depends_on=[TargetRef.parse(API)])
    inventory = SimpleNamespace(target=lambda ref: info if str(ref) == dependent else None)
    edge = f"{dependent} -> {API}"
    assert aw.SignalSampler(object(), rows=rows, inventory=inventory)("link_ok", edge) == ("1", NOW)

    missing_rows = SimpleNamespace(link_probe_cursors=lambda owner: {})
    assert aw.SignalSampler(object(), rows=missing_rows, inventory=inventory)("link_ok", edge) is None
    bad_rows = SimpleNamespace(link_probe_cursors=lambda owner: {API: {"state": "broken", "at": NOW}})
    assert aw.SignalSampler(object(), rows=bad_rows, inventory=inventory)("link_ok", edge) == ("0", NOW)
    assert aw.SignalSampler(object(), rows=rows, inventory=inventory)("link_ok", f"{dependent} -> {CACHE}") is None


# --- verification samples ---------------------------------------------------------------------------------------------
def metrics_with(value, observed_at=NOW, raises=None):
    def snapshot(target, signals):
        if raises:
            raise raises
        return SimpleNamespace(values={"dependency_probe_min": value}, observed_at=observed_at)
    return SimpleNamespace(snapshot=snapshot)


def test_a_sample_is_healthy_only_at_the_reviewed_minimum_and_unknown_is_never_healthy():
    sample = lambda m: aw.SignalSampler(m)("dependency_probe_min", API)
    assert sample(metrics_with(1.0)) == ("healthy", NOW)
    assert sample(metrics_with(0.0)) == ("unhealthy", NOW)
    assert sample(metrics_with(0.99)) == ("unhealthy", NOW)
    for unknown in (metrics_with(None), metrics_with(math.nan), metrics_with(math.inf * 0), metrics_with(1.0, observed_at=None),
                    metrics_with(1.0, raises=RuntimeError("prometheus down"))):
        assert sample(unknown) is None
    assert aw.SignalSampler(metrics_with(1.0))("restarts_10m", API) is None          # no reviewed minimum for it


def test_the_detector_checks_fail_in_opposite_directions_so_that_not_knowing_never_acts_or_claims_recovery(monkeypatch):
    inc = incident()
    monkeypatch.setattr(aw, "detected_class", lambda metrics, target: "dependency_unavailable")
    assert aw.class_detected(None, inc) is True and aw.class_still_firing(None, inc) is True
    monkeypatch.setattr(aw, "detected_class", lambda metrics, target: None)
    assert aw.class_detected(None, inc) is False and aw.class_still_firing(None, inc) is False

    def broken(metrics, target):
        raise RuntimeError("metrics unavailable")

    monkeypatch.setattr(aw, "detected_class", broken)
    assert aw.class_detected(None, inc) is False          # precheck: unknown means nothing is sent
    assert aw.class_still_firing(None, inc) is True       # verification: unknown means no recovery is claimed


# --- the judge's context ----------------------------------------------------------------------------------------------
def frozen(evidence_refs=("ev_cache",), grounds=("runbook:RB-003",), capability="container.start", target=CACHE):
    data = SimpleNamespace(evidence_refs=list(evidence_refs), grounds=list(grounds), capability=capability, target=target)
    return SimpleNamespace(input=data)


def review(records=None):
    records = {"ev_cache": SimpleNamespace(evidence_id="ev_cache", model_text="state=exited  exit=1")} if records is None else records
    rows = SimpleNamespace(get_evidence=lambda ids: [records[i] for i in ids if i in records])
    return aw.ReviewContext(rows=rows, inventory=INVENTORY, cards=CARDS, runbooks_dir=ROOT / "argus" / "runbooks")


def test_the_judge_context_has_bounded_extracts_of_exactly_the_cited_records_and_both_reviewed_cards():
    context = review()(frozen())
    assert set(context) == {"evidence_extracts", "ground_extracts", "service_card", "action_card"}
    assert context["evidence_extracts"] == {"ev_cache": "state=exited exit=1"}
    extract = context["ground_extracts"]["runbook:RB-003"]
    assert 0 < len(extract) <= 480 and "---" not in extract[:3]
    # X-5: the runbook's declared action and its recovery check, not its header (the judge saw "status: draft" only)
    assert extract.startswith("RB-003 — Dependency unavailable. Declared action: container.start on the root_cause")
    assert "Recovery:" in extract and "status: draft" not in extract
    assert context["action_card"]["name"] == "container.start" and context["service_card"]["role"] == "cache"
    assert len(str(context)) < 6000


@pytest.mark.parametrize("why, kwargs, records", [
    ("a cited record is missing", {}, {}),
    ("the runbook is not in the library", {"grounds": ("runbook:RB-999",)}, None),
    ("no action card", {"capability": "container.nope"}, None),
    ("an empty extract", {}, {"ev_cache": SimpleNamespace(evidence_id="ev_cache", model_text="   ")}),
])
def test_the_judge_context_refuses_what_it_cannot_cite_exactly(why, kwargs, records):
    with pytest.raises(RemediationRefused):
        review(records)(frozen(**kwargs))


# --- the decision to build ----------------------------------------------------------------------------------------------
def settings(tmp_path, **changes):
    token = tmp_path / "action_token"
    token.write_text("a" * 40, encoding="utf-8")                      # a fake secret, low entropy on purpose
    base = dict(action_path=True, runner="langgraph", action_gateway_url="http://argus-v18-action-gateway:8705",
                action_token_file=str(token), judge_model="gpt-5.6-terra", llm_model="gpt-5.6-luna",
                action_daily_host_cap=2, runbooks_dir=ROOT / "argus" / "runbooks",
                secret=lambda name: "k" * 24 if name == "openai_api_key" else "")
    return SimpleNamespace(**{**base, **changes})


def build(s, gate=(PAIR,), store=None):
    policy = SimpleNamespace(write_gate_open=list(gate), version="policy-1")
    store = store or SimpleNamespace(add_action_proposal=lambda proposal: None)
    return aw.build_action_path(s, store=store, policy=policy, inventory=INVENTORY,
                                action_policy=SimpleNamespace(cards=CARDS), metrics=object(), invoke=object())


def test_the_path_is_not_built_while_it_is_off_or_while_the_gate_is_empty(tmp_path):
    assert build(settings(tmp_path, action_path=False)) is None
    assert build(settings(tmp_path, action_path=False), gate=()) is None
    assert build(settings(tmp_path), gate=()) is None                  # on, but nothing is released


@pytest.mark.parametrize("why, changes, store", [
    ("the runner", {"runner": "plain"}, None),
    ("the gateway address", {"action_gateway_url": ""}, None),
    ("the token file", {"action_token_file": "/nonexistent/action_token"}, None),
    ("the judge key", {"secret": lambda name: ""}, None),
    ("the action tables", {}, SimpleNamespace()),
])
def test_with_the_flag_on_and_the_gate_open_a_missing_piece_stops_the_start(tmp_path, why, changes, store):
    with pytest.raises(SystemExit, match="action path is enabled"):
        build(settings(tmp_path, **changes), store=store)


def test_every_missing_piece_is_named_at_once(tmp_path):
    with pytest.raises(SystemExit) as stop:
        build(settings(tmp_path, runner="plain", action_gateway_url="", secret=lambda name: ""))
    for piece in ("langgraph", "ARGUS_ACTION_GATEWAY_URL", "judge's model key"):
        assert piece in str(stop.value)


def test_a_complete_configuration_builds_the_path_with_the_reviewed_gateway_and_the_released_pairs(tmp_path):
    from argus.actions.gateway_client import HttpActionGateway
    from argus.orchestration.action_path import OfflineActionPath
    path = build(settings(tmp_path))
    assert isinstance(path, OfflineActionPath)
    assert path.executor.gate_open == frozenset({("container.start", CACHE)})
    assert isinstance(path.executor.gateway, HttpActionGateway)
    assert path.judge_model_id == "gpt-5.6-terra" and path.judge_model.model == "gpt-5.6-terra"


def test_the_approval_notice_goes_to_the_home_hosts_alertmanager_and_its_absence_is_logged(tmp_path, caplog):
    """TASK-61's sender was never handed to the path: an approval waited with no notice on the team's route. A held-back
    proposal's escalation uses the same route."""
    path = build(settings(tmp_path, home_host="vm-095"))
    sender, escalation = path.approval_notifier, path.escalation_notifier
    assert (sender.__name__, escalation.__name__) == ("notify_approval_waiting", "notify_escalation")
    assert sender.__self__.url == escalation.__self__.url == INVENTORY.host("vm-095").alertmanager
    unset = build(settings(tmp_path))
    assert unset.approval_notifier is None and unset.escalation_notifier is None
    assert "approval and escalation notices will not be sent" in caplog.text


def test_the_judge_must_be_a_different_model_from_the_decider(tmp_path):
    with pytest.raises(ValueError, match="different model"):
        build(settings(tmp_path, llm_model="gpt-5.6-terra"))


# --- Settings and build() -----------------------------------------------------------------------------------------------
def test_settings_default_to_off_and_read_their_environment(monkeypatch):
    from argus.infrastructure.wiring import Settings
    for name in ("ARGUS_ACTION_PATH", "ARGUS_ACTION_GATEWAY_URL", "ARGUS_ACTION_TOKEN_FILE", "ARGUS_JUDGE_MODEL",
                 "ARGUS_ACTION_DAILY_HOST_CAP"):
        monkeypatch.delenv(name, raising=False)
    s = Settings()
    assert (s.action_path, s.action_gateway_url, s.judge_model, s.action_daily_host_cap) == (
        False, "", "gpt-5.6-terra", 2)
    assert s.action_token_file == "/run/argus-secrets/action_token"
    monkeypatch.setenv("ARGUS_ACTION_PATH", "1")
    monkeypatch.setenv("ARGUS_ACTION_DAILY_HOST_CAP", "5")
    assert Settings().action_path is True and Settings().action_daily_host_cap == 5
    monkeypatch.setenv("ARGUS_ACTION_PATH", "true")                    # only "1" turns it on
    assert Settings().action_path is False


from test_core import make_app  # noqa: E402,F401  (the fixture other build() tests use)


def test_a_default_build_has_no_action_path_and_the_hook_passes_one_to_the_runner(make_app, monkeypatch):  # noqa: F811
    monkeypatch.delenv("ARGUS_ACTION_PATH", raising=False)
    monkeypatch.setenv("ARGUS_RUNNER", "langgraph")                    # only the graph runner has the action branch
    assert make_app().runner.action_path is None
    sentinel = object()
    monkeypatch.setattr(aw, "build_action_path", lambda *args, **kw: sentinel)
    assert make_app().runner.action_path is sentinel
    monkeypatch.setenv("ARGUS_RUNNER", "plain")                        # the rollback runner never gets one
    monkeypatch.setattr(aw, "build_action_path", lambda *args, **kw: None)
    assert not hasattr(make_app().runner, "action_path")


# --- the whole path, with real pieces ------------------------------------------------------------------------------------
class Rows:
    """The real store, plus the incident row and the evidence version this test controls."""

    def __init__(self, store, incident):
        self.store, self._incident = store, incident

    def get_incident(self, incident_id):
        return self._incident

    def evidence_state(self, incident_id):
        return 7, None

    def __getattr__(self, name):
        return getattr(self.store, name)


class StoredIncident(SimpleNamespace):
    def model_copy(self, update):
        return StoredIncident(**{**vars(self), **update})


@pytest.fixture()
def gateway_url(tmp_path):
    from http.server import ThreadingHTTPServer
    from threading import Thread

    from services.action_gateway.core import ActionGateway, ActionJournal
    from services.action_gateway.server import make_handler
    from test_phase19_gateway import ROUTE, FakeProxy

    proxy = FakeProxy()
    core = ActionGateway("vm-166", "a" * 40, ActionJournal(tmp_path / "journal.db"), proxy,
                         released={("container.start", CACHE): ROUTE})
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(core))
    Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}", proxy
    server.shutdown()


def test_a_released_start_runs_from_diagnosis_to_a_verified_recovery_through_the_real_gateway(tmp_path, monkeypatch,
                                                                                            gateway_url):
    from datetime import timedelta

    from argus.actions.incident import ActionPolicy
    from argus.adapters.outbound.sqlite_store import SqliteStore
    from argus.domain.model import EvidenceRecord, IncidentOutcome, IncidentStatus, Observation
    from test_phase18_remediation import GOOD_CHECKS

    url, proxy = gateway_url
    seen = {"judge": [], "invoked": []}

    class AgreeingJudge:
        def __init__(self, key, model, *, deciding_model, **kw):
            self.model = model

        def __call__(self, packet):
            seen["judge"].append(packet)
            return {"verdict": "agree", "checks": GOOD_CHECKS, "reasons": []}

    monkeypatch.setattr("argus.adapters.outbound.judge.OpenAIJudge", AgreeingJudge)
    monkeypatch.setattr(aw, "detected_class", lambda metrics, target: "dependency_unavailable" if not seen.get("healed") else None)

    store = SqliteStore(str(tmp_path / "path.db"))
    inc = StoredIncident(id="inc_sc03", target=TargetRef.parse(API), incident_class="dependency_unavailable",
                         root_cause_target=CACHE, outcome=IncidentOutcome.diagnosed, status=IncidentStatus.running)
    now = datetime.now(timezone.utc)
    store.append_evidence(EvidenceRecord(
        evidence_id="ev_cache_status", incident_id="inc_sc03", kind="observation", capability="container.status",
        target=CACHE, host="vm-166", executor="docker_read", caller="strategy:baseline", source_time=now,
        collected_at=now, status="ok", values={"values": {"state": "exited"}}, model_text="state=exited").with_hash())

    ticks = [now]

    def clock():                                   # one second per call: a read lands between two decisions
        ticks[0] += timedelta(seconds=1)
        return ticks[0]

    def invoke(ctx, name, arguments):
        seen["invoked"].append((name, arguments["target"], ctx.caller))
        at = ticks[0] + timedelta(milliseconds=500)                   # measured after the last decision time
        return Observation(observation_id="obs_1", status="ok", capability=name, target=TargetRef.parse(arguments["target"]),
                           host="vm-166", executor="docker_read", source_time=at, collected_at=at,
                           values={"state": "exited", "container_id": "cache-1"}, model_text="state=exited"), None

    metrics = SimpleNamespace(snapshot=lambda target, signals: SimpleNamespace(
        values={"dependency_probe_min": 1.0}, observed_at=ticks[0] + timedelta(milliseconds=500)))
    path = aw.build_action_path(
        settings(tmp_path, action_gateway_url=url, action_token_file=str(tmp_path / "action_token")),
        store=Rows(store, inc), policy=SimpleNamespace(write_gate_open=[PAIR], version="policy-1"), inventory=INVENTORY,
        action_policy=ActionPolicy.from_paths(ROOT / "config", ROOT / "argus" / "runbooks"), metrics=metrics, invoke=invoke)
    path.clock = clock
    try:
        proposal_id = path.propose(inc, {"passages": [{"runbook_id": "RB-003"}]})
        assert proposal_id, "the deterministic proposal must survive propose()'s own validation"
        proposal = store.get_action_proposal(proposal_id)
        assert (proposal.input.capability, proposal.input.target) == ("container.start", CACHE)
        assert path.judge(proposal_id).verdict == "agree"
        packet = seen["judge"][0]
        assert set(packet["evidence_extracts"]) == {"ev_cache_status"} and "runbook:RB-003" in packet["ground_extracts"]
        approval_id = path.request(proposal_id)
        assert approval_id and path.approval_state(approval_id) == "pending"
        assert path.answer(approval_id, digest=proposal.digest, principal="operator", principal_kind="human",
                           decision="approved")
        action = path.execute(approval_id)
        assert action["state"] == "confirmed" and proxy.calls == [(proxy.calls[0][0], action["id"])]
        assert ("container.status", CACHE, "action_path") in seen["invoked"]          # the audited read path, by name
        seen["healed"] = True
        assert path.verify(action["id"]) == "recovered_verified"     # a sample read after the action, judged after it
    finally:
        store._db.close()


# --- the API's approval routes --------------------------------------------------------------------------------------------
OPS_ROUTES = {"/api/v1/ops/auth/token", "/api/v1/ops/approvals", "/api/v1/ops/approvals/{approval_id}/answer",
              "/api/v1/ops/holds"}


def test_the_approval_rows_exist_only_while_the_gate_names_a_pair_and_need_the_approval_tables():
    full = SimpleNamespace(**{method: (lambda *a, **k: None) for method in aw.APPROVAL_ROW_METHODS})
    assert aw.approval_rows(SimpleNamespace(write_gate_open=[]), full) is None
    assert aw.approval_rows(SimpleNamespace(write_gate_open=[PAIR]), full) is full
    with pytest.raises(SystemExit, match="approval tables"):
        aw.approval_rows(SimpleNamespace(write_gate_open=[PAIR]), SimpleNamespace(list_pending_approvals=None))


def test_the_api_mounts_the_private_login_approval_and_hold_routes_only_with_approval_rows(make_app, monkeypatch):  # noqa: F811
    from fastapi.testclient import TestClient

    from argus.adapters.inbound.http import build_api

    def routes(app):
        return {getattr(route, "path", "") for route in build_api(app).routes}

    monkeypatch.setattr(aw, "approval_rows", lambda policy, store: None)
    closed = make_app()                                                           # an empty write gate
    assert closed.action_rows is None and not routes(closed) & OPS_ROUTES
    monkeypatch.setattr(aw, "approval_rows", lambda policy, store: store)
    opened = make_app()
    assert opened.action_rows is opened.store and OPS_ROUTES <= routes(opened)
    client = TestClient(build_api(opened))
    assert client.get("/api/v1/ops/approvals").status_code in (401, 404)            # still behind its own guards
    assert client.post("/api/v1/ops/auth/token", data={"username": "u", "password": "p"}).status_code == 404  # private path only
