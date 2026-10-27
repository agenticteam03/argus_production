"""Exact-route action gateway core, with no released route by default.

No listener, Docker socket or credential is wired here. Phase 20 must review each
route and target pair before building or deploying a transport.
"""
from __future__ import annotations

import hmac
import json
import re
import sqlite3
from collections.abc import Mapping
from datetime import datetime, timezone
from threading import RLock
from types import MappingProxyType


ACTION_ID = re.compile(r"^act_[0-9a-f]{32}$")


class GatewayRefused(ValueError):
    """The gateway refused an unauthenticated, unlisted or duplicate action."""


class NotSent(ValueError):
    """The proxy refused before any write reached Docker (the identity changed): a definite failure, not ambiguous."""


def validated_pairs(host, released):
    pairs = dict(released or {})
    if pairs and host == "vm-095":
        raise GatewayRefused("Argus's own host cannot have an action route")
    for (capability, target), route in pairs.items():
        if not re.fullmatch(re.escape(host) + r"/container:argus-lab-[A-Za-z0-9_.-]+", target):
            raise GatewayRefused("only an exact lab container on this host may be configured")
        name = target.split(":", 1)[1]
        if capability == "network.restore":
            if not isinstance(route, Mapping) or set(route) != {"route", "connect_network", "disconnect_network"}:
                raise GatewayRefused("network.restore needs its exact route and network pair")
            if route["route"] != f"POST /containers/{name}/network-restore":
                raise GatewayRefused("network.restore route differs")
            for key in ("connect_network", "disconnect_network"):
                network = route[key]
                if not isinstance(network, str) or not re.fullmatch(r"argus-lab-[A-Za-z0-9_.-]+", network):
                    raise GatewayRefused("network.restore names must be lab networks")
            if route["connect_network"] == route["disconnect_network"]:
                raise GatewayRefused("network.restore networks must differ")
            pairs[(capability, target)] = MappingProxyType(dict(route))
            continue
        verb = capability.removeprefix("container.")
        if verb not in {"start", "stop", "restart", "pause", "unpause"} or route != f"POST /containers/{name}/{verb}":
            raise GatewayRefused("capability and exact Docker route differ")
    return MappingProxyType(pairs)


class ActionJournal:
    def __init__(self, path):
        self.path = path
        self._lock = RLock()
        self._db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._db.execute("PRAGMA synchronous=FULL")
        self._db.execute("PRAGMA foreign_keys=ON")
        self._db.execute("CREATE TABLE IF NOT EXISTS action_receipt ("
                         "action_id TEXT PRIMARY KEY, capability TEXT NOT NULL, target TEXT NOT NULL, "
                         "target_identity TEXT NOT NULL, route TEXT NOT NULL, received_at TEXT NOT NULL)")
        self._db.execute("CREATE TABLE IF NOT EXISTS action_event ("
                         "seq INTEGER PRIMARY KEY AUTOINCREMENT, action_id TEXT NOT NULL "
                         "REFERENCES action_receipt(action_id), at TEXT NOT NULL, "
                         "docker_status TEXT NOT NULL CHECK(docker_status IN ('received','confirmed','failed')))")
        self._db.execute("CREATE TABLE IF NOT EXISTS action_step ("
                         "seq INTEGER PRIMARY KEY AUTOINCREMENT, action_id TEXT NOT NULL "
                         "REFERENCES action_receipt(action_id), at TEXT NOT NULL, "
                         "step TEXT NOT NULL CHECK(step IN ('connect','disconnect')), UNIQUE(action_id, step))")
        for table in ("action_receipt", "action_event", "action_step"):
            self._db.execute(f"CREATE TRIGGER IF NOT EXISTS {table}_no_update BEFORE UPDATE ON {table} "
                             "BEGIN SELECT RAISE(ABORT, 'gateway journal is append-only'); END")
            self._db.execute(f"CREATE TRIGGER IF NOT EXISTS {table}_no_delete BEFORE DELETE ON {table} "
                             "BEGIN SELECT RAISE(ABORT, 'gateway journal is append-only'); END")

    def accept(self, action_id, capability, target, route, identity):
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                self._db.execute("INSERT INTO action_receipt "
                                 "(action_id, capability, target, target_identity, route, received_at) "
                                 "VALUES (?,?,?,?,?,?)",
                                 (action_id, capability, target, json.dumps(identity, sort_keys=True), route,
                                  datetime.now(timezone.utc).isoformat()))
                self._db.execute("INSERT INTO action_event (action_id, at, docker_status) VALUES (?,?,'received')",
                                 (action_id, datetime.now(timezone.utc).isoformat()))
                self._db.execute("COMMIT")
            except sqlite3.IntegrityError as exc:
                self._db.execute("ROLLBACK")
                raise GatewayRefused("action id already accepted") from exc
            except Exception:
                self._db.execute("ROLLBACK")
                raise

    def finish(self, action_id, status):
        with self._lock:
            if status not in ("confirmed", "failed"):
                raise GatewayRefused("invalid Docker result")
            self._db.execute("BEGIN IMMEDIATE")
            try:
                latest = self._db.execute("SELECT docker_status FROM action_event WHERE action_id=? "
                                           "ORDER BY seq DESC LIMIT 1", (action_id,)).fetchone()
                if not latest or latest[0] != "received":
                    raise GatewayRefused("action is not awaiting a result")
                self._db.execute("INSERT INTO action_event (action_id, at, docker_status) VALUES (?,?,?)",
                                 (action_id, datetime.now(timezone.utc).isoformat(), status))
                self._db.execute("COMMIT")
            except Exception:
                self._db.execute("ROLLBACK")
                raise

    def status(self, action_id):
        with self._lock:
            row = self._db.execute("SELECT docker_status FROM action_event WHERE action_id=? "
                                   "ORDER BY seq DESC LIMIT 1", (action_id,)).fetchone()
            steps = {item[0] for item in self._db.execute("SELECT step FROM action_step WHERE action_id=?",
                                                           (action_id,))}
        if not row:
            return None
        if row[0] != "received":
            return row[0]
        if "disconnect" in steps:
            return "confirmed"
        if "connect" in steps:
            return "indeterminate"
        return "received"

    def record_step(self, action_id, step):
        if step not in ("connect", "disconnect"):
            raise GatewayRefused("invalid network step")
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                latest = self._db.execute("SELECT docker_status FROM action_event WHERE action_id=? "
                                          "ORDER BY seq DESC LIMIT 1", (action_id,)).fetchone()
                steps = {item[0] for item in self._db.execute("SELECT step FROM action_step WHERE action_id=?",
                                                                (action_id,))}
                if not latest or latest[0] != "received":
                    raise GatewayRefused("action is not awaiting a network step")
                if step in steps:
                    raise GatewayRefused("network step already recorded")
                if step == "disconnect" and "connect" not in steps:
                    raise GatewayRefused("disconnect cannot precede connect")
                self._db.execute("INSERT INTO action_step (action_id, at, step) VALUES (?,?,?)",
                                 (action_id, datetime.now(timezone.utc).isoformat(), step))
                self._db.execute("COMMIT")
            except sqlite3.IntegrityError as exc:
                self._db.execute("ROLLBACK")
                raise GatewayRefused("network step already recorded") from exc
            except Exception:
                self._db.execute("ROLLBACK")
                raise

    def events(self, action_id):
        with self._lock:
            action_rows = self._db.execute("SELECT docker_status FROM action_event WHERE action_id=? ORDER BY seq",
                                           (action_id,)).fetchall()
            step_rows = self._db.execute("SELECT step FROM action_step WHERE action_id=? ORDER BY seq",
                                         (action_id,)).fetchall()
        if not action_rows:
            return []
        return [action_rows[0][0], *(step[0] for step in step_rows), *(row[0] for row in action_rows[1:])]

    def close(self):
        self._db.close()


class ActionGateway:
    def __init__(self, host, token, journal, proxy, *, released=None):
        self.host, self.token, self.journal, self.proxy = host, token, journal, proxy
        self.released = validated_pairs(host, released)

    def _authenticate(self, token, action_id):
        if not self.token or not token or not hmac.compare_digest(token, self.token):
            raise GatewayRefused("invalid gateway credential")
        if not ACTION_ID.fullmatch(action_id):
            raise GatewayRefused("invalid action id")

    def dispatch(self, token, action_id, capability, target, route, identity, *,
                 connect_network=None, disconnect_network=None):
        self._authenticate(token, action_id)
        release = self.released.get((capability, target))
        expected_route = release.get("route") if isinstance(release, Mapping) else release
        if expected_route != route or not self.released:
            raise GatewayRefused("route and target pair is not released")
        if capability == "network.restore":
            if (not isinstance(release, Mapping) or connect_network != release["connect_network"]
                    or disconnect_network != release["disconnect_network"]):
                raise GatewayRefused("network names differ from the released pair")
        elif connect_network is not None or disconnect_network is not None:
            raise GatewayRefused("unexpected network names")
        if not target.startswith(self.host + "/container:") or not isinstance(identity, dict) or not identity:
            raise GatewayRefused("invalid host-qualified target or identity")
        if self.proxy.identity(target) != identity:
            raise GatewayRefused("target identity changed")
        self.journal.accept(action_id, capability, target, route, identity)
        if capability == "network.restore":
            try:
                result = self.proxy.connect_network(target, connect_network, action_id, identity)
            except NotSent:
                result = "failed"
            if result == "failed":
                self.journal.finish(action_id, "failed")
                return "failed"
            if result != "confirmed":
                raise GatewayRefused("proxy did not report a definitive connect result")
            self.journal.record_step(action_id, "connect")
            result = self.proxy.disconnect_network(target, disconnect_network, action_id, identity)
            if result != "confirmed":
                # Once connect succeeded, any incomplete second step is a human reconciliation case.
                raise ConnectionError("network restore is connected but not disconnected")
            self.journal.record_step(action_id, "disconnect")
            self.journal.finish(action_id, "confirmed")
            return "confirmed"
        try:
            result = self.proxy.execute(route, action_id, identity)
        except NotSent:
            result = "failed"
        if result not in ("confirmed", "failed"):
            raise GatewayRefused("proxy did not report a definitive result")
        self.journal.finish(action_id, result)
        return result

    def status(self, token, action_id):
        self._authenticate(token, action_id)
        return self.journal.status(action_id)
