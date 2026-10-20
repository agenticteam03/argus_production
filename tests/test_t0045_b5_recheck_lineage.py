"""T-0045 step B5 (ACR-0021): re-check lineage. `POST /api/v1/investigations` accepts an optional `parent_id`, the
incident this one re-checks; it must name an existing incident (every role reads every incident, so "readable by the
caller" is "exists"), else 422 and nothing is created. It is stored, returned in the incident view and in the list,
and `GET /api/v1/incidents?parent_id=` lists the re-checks. Quotas are unchanged: a re-check is a manual incident like
any other. Migration 007 adds the column in Postgres (tests/test_postgres.py); an older SQLite file gains it."""
from __future__ import annotations

import json
import sqlite3

from argus.domain.model import utcnow
from test_acr0012_investigate import EDGE, audit_bodies, start, token, ui  # noqa: F401  (ui is a fixture)
from test_core import make_app  # noqa: F401  (fixture, used by ui)


def _first(c, t):
    r = start(c, t)
    assert r.status_code == 202, r.text
    return r.json()["incident_id"]


# --- the request ---------------------------------------------------------------------------------------------------------
def test_a_recheck_names_its_parent_and_the_views_return_it(ui):
    app, client = ui
    c = client()
    t = token(c)
    parent = _first(c, t)
    r = start(c, t, parent_id=parent, request_kind="check")
    assert r.status_code == 202, r.text
    child = r.json()["incident_id"]
    assert app.store.get_incident(child).parent_id == parent
    h = {"Authorization": f"Bearer {token(c, scope='read')}"}
    assert c.get(f"/api/v1/incidents/{child}", headers=h).json()["parent_id"] == parent
    assert c.get(f"/api/v1/incidents/{parent}", headers=h).json()["parent_id"] is None
    rows = {r["id"]: r for r in c.get("/api/v1/incidents", headers=h).json()}
    assert rows[child]["parent_id"] == parent and rows[parent]["parent_id"] is None


def test_an_unknown_parent_is_refused_and_nothing_is_created(ui):
    app, client = ui
    c = client()
    t = token(c)
    before = len(app.store.list_incidents())
    r = start(c, t, parent_id="inc_000000000000")
    assert r.status_code == 422 and "parent_id" in r.text
    assert len(app.store.list_incidents()) == before


def test_a_malformed_parent_is_refused_before_any_read(ui):
    _, client = ui
    c = client()
    t = token(c)
    for bad in ("../inc_1", "inc_" + "a" * 80, "", "x' OR 1=1 --"):
        assert start(c, t, parent_id=bad).status_code == 422, bad


def test_the_list_filters_by_parent_newest_first(ui):
    _, client = ui
    c = client()
    t = token(c)
    a, b = _first(c, t), _first(c, t)
    a1 = start(c, t, parent_id=a).json()["incident_id"]
    a2 = start(c, t, parent_id=a).json()["incident_id"]
    start(c, t, parent_id=b)
    h = {"Authorization": f"Bearer {token(c, scope='read')}"}
    got = c.get("/api/v1/incidents", params={"parent_id": a}, headers=h).json()
    assert [r["id"] for r in got] == [a2, a1]
    assert c.get("/api/v1/incidents", params={"parent_id": "inc_000000000000"}, headers=h).json() == []
    assert c.get("/api/v1/incidents", params={"parent_id": "not an id"}, headers=h).status_code == 422


def test_a_viewer_can_list_rechecks_but_still_cannot_start_one(ui):
    _, client = ui
    c = client()
    parent = _first(c, token(c))
    viewer = token(c, user="vera")
    assert start(c, viewer, parent_id=parent).status_code == 403
    h = {"Authorization": f"Bearer {viewer}"}
    assert c.get("/api/v1/incidents", params={"parent_id": parent}, headers=h).status_code == 200


# --- quotas: unchanged ---------------------------------------------------------------------------------------------------
def test_a_recheck_counts_against_the_quotas_like_any_manual_incident(ui):
    app, client = ui
    app.settings.investigations_per_hour = 2
    c = client()
    t = token(c, scope="investigate", headers=EDGE)
    parent = start(c, t, headers=EDGE).json()["incident_id"]
    assert app.store.close_queued_incident(parent, "resolved_externally", "test", utcnow())
    child = start(c, t, headers=EDGE, parent_id=parent)
    assert child.status_code == 202
    assert app.store.close_queued_incident(child.json()["incident_id"], "resolved_externally", "test", utcnow())
    r = start(c, t, headers=EDGE, parent_id=parent)
    assert r.status_code == 429
    assert any('"per_hour"' in b for b in audit_bodies(app))


def test_the_request_audit_records_the_parent(ui):
    app, client = ui
    c = client()
    t = token(c)
    parent = _first(c, t)
    start(c, t, parent_id=parent)
    requested = [json.loads(b) for b in audit_bodies(app) if '"investigation.requested"' in b]
    assert [r["detail"]["parent_id"] for r in requested] == [None, parent]


# --- storage -------------------------------------------------------------------------------------------------------------
def test_db_check_proves_the_column_before_counting_its_refusals():
    """Without migration 007 the two refusals "pass" because the column is missing; a read that must succeed comes
    first, so `argus db check` fails on a database that lacks 007 (review of #181)."""
    from argus.adapters.outbound.postgres_store import CHECKS_SQL
    names = [n for n, _, _ in CHECKS_SQL]
    present = names.index("re-check lineage column present (migration 007)")
    assert CHECKS_SQL[present][2] is True and "parent_id" in CHECKS_SQL[present][1]
    for refusal in ("re-check of a missing incident refused (ACR-0021)", "an incident's parent cannot change (ACR-0021)"):
        assert present < names.index(refusal)



def test_an_older_sqlite_file_gains_the_column(tmp_path):
    from argus.adapters.outbound.sqlite_store import SqliteStore
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as conn:                  # the incident table as it was before B5
        conn.execute("CREATE TABLE incident (id TEXT PRIMARY KEY, target TEXT NOT NULL, status TEXT NOT NULL, "
                     "opened_at TEXT NOT NULL, idempotency_key TEXT UNIQUE, body TEXT NOT NULL, claimed_by TEXT, "
                     "claimed_until TEXT)")
    store = SqliteStore(str(path))
    cols = {r[1] for r in sqlite3.connect(path).execute("PRAGMA table_info(incident)")}
    assert "parent_id" in cols
    assert store.list_incidents(parent_id="inc_000000000000") == []
