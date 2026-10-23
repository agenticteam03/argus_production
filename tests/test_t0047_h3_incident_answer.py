"""T-0047 H3 (ACR-0024 §3.6): `GET /api/v1/incidents/{id}` carries the final decision's hypotheses, by rank, and
`ranking_disagrees`. Derived from the stored rows (`incident_hypothesis`), never a model call. An operator also gets
the cited evidence ids; a viewer gets the counts only."""
from __future__ import annotations

import json
from types import SimpleNamespace

from argus.application.incident_view import hypotheses_view
from argus.domain.model import utcnow
from test_core import make_app  # noqa: F401  (fixture)
from test_t0045_b4_incident_verdict import SECRET_LINE, WORKER, _client, _diagnosed, _evidence


def row(hid, rank, score, chosen=False, support=(), against=(), status="supported", target=WORKER,
        relation="self", cause_class="container_restart_loop"):
    return {"hypothesis_id": hid, "statement": f"hypothesis {hid}", "cause_class": cause_class, "target": target,
            "relation": relation, "status": status, "support_ids": list(support), "against_ids": list(against),
            "score": score, "rank": rank, "chosen": chosen}


def _stored(app, steps):
    """An SC-01-like diagnosed incident with evidence ev_a, ev_b and the given hypotheses per step."""
    inc = _diagnosed(app, WORKER, "container_restart_loop", WORKER, "OOM-killed.", findings=["4 restarts"],
                     cited=["ev_a"])
    _evidence(app, inc, "ev_a")
    _evidence(app, inc, "ev_b")
    for step, rows in enumerate(steps, start=1):
        app.store.add_hypotheses(inc.id, step, rows, utcnow())
    return inc


def test_an_operator_gets_the_final_steps_list_with_the_ids(make_app):
    app = make_app()
    inc = _stored(app, [[row("h1", 1, -0.5, status="untested"), row("h2", 2, -0.5, status="untested")],
                        [row("h1", 1, 5.0, chosen=True, support=["ev_a", "ev_b"]),
                         row("h2", 2, -1.0, against=["ev_b"], status="ruled_out", target=None, relation="external",
                             cause_class="other")]])
    api, h = _client(app, "operator")
    body = api.get(f"/api/v1/incidents/{inc.id}", headers=h).json()
    assert body["ranking_disagrees"] is False
    assert body["hypotheses"] == [
        {"id": "h1", "statement": "hypothesis h1", "cause_class": "container_restart_loop", "target": WORKER,
         "relation": "self", "status": "supported", "rank": 1, "chosen": True,
         "support": {"score": 5.0, "for": 2, "against": 0}, "support_ids": ["ev_a", "ev_b"], "against_ids": []},
        {"id": "h2", "statement": "hypothesis h2", "cause_class": "other", "target": None, "relation": "external",
         "status": "ruled_out", "rank": 2, "chosen": False, "support": {"score": -1.0, "for": 0, "against": 1},
         "support_ids": [], "against_ids": ["ev_b"]}]


def test_a_viewer_gets_the_counts_not_the_ids(make_app):
    app = make_app()
    inc = _stored(app, [[row("h1", 1, 5.0, chosen=True, support=["ev_a", "ev_b"])]])
    api, h = _client(app, "viewer")
    body = api.get(f"/api/v1/incidents/{inc.id}", headers=h).json()
    assert body["hypotheses"][0]["support"] == {"score": 5.0, "for": 2, "against": 0}
    assert "support_ids" not in body["hypotheses"][0] and "against_ids" not in body["hypotheses"][0]
    assert "ev_a" not in json.dumps(body["hypotheses"]) and SECRET_LINE not in json.dumps(body)


def test_ranking_disagrees_when_the_chosen_one_is_not_first(make_app):
    app = make_app()
    inc = _stored(app, [[row("h1", 1, 3.0, support=["ev_a"]), row("h2", 2, 0.0, chosen=True)]])
    api, h = _client(app, "operator")
    body = api.get(f"/api/v1/incidents/{inc.id}", headers=h).json()
    assert body["ranking_disagrees"] is True
    assert [(x["id"], x["rank"], x["chosen"]) for x in body["hypotheses"]] == [("h1", 1, False), ("h2", 2, True)]


def test_no_stored_hypotheses_is_an_empty_list(make_app):
    app = make_app()
    inc = _stored(app, [])
    api, h = _client(app, "operator")
    body = api.get(f"/api/v1/incidents/{inc.id}", headers=h).json()
    assert body["hypotheses"] == [] and body["ranking_disagrees"] is False


def test_the_counts_leave_out_ids_that_are_not_stored_evidence_and_repeats():
    stored = [SimpleNamespace(evidence_id="ev_a")]
    rows = [{**row("h1", 1, 3.0, chosen=True, support=["ev_a", "ev_gone", "ev_a"]), "step": 1}]
    ranked, disagrees = hypotheses_view(rows, stored, show_evidence=True)
    assert ranked[0]["support"]["for"] == 1 and ranked[0]["support_ids"] == ["ev_a", "ev_gone", "ev_a"]
    assert disagrees is False
