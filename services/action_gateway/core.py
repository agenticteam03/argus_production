"""Exact-route action gateway core, with no released route by default.

No listener, Docker socket or credential is wired here. Phase 20 must review each
route and target pair before building or deploying a transport.
"""
from __future__ import annotations

import hmac
import json
import re
import sqlite3
from datetime import datetime, timezone
from threading import RLock
from types import MappingProxyType


ACTION_ID = re.compile(r"^act_[0-9a-f]{32}$")


class GatewayRefused(ValueError):
    """The gateway refused an unauthenticated, unlisted or duplicate action."""


class ActionJournal:
    def __init__(self, path):
        self.path = path
        self._lock = RLock()
        self._db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._db.execute("PRAGMA synchronous=FULL")
        self._db.execute("CREATE TABLE IF NOT EXISTS action_journal ("
                         "action_id TEXT PRIMARY KEY, capability TEXT NOT NULL, target TEXT NOT NULL, "
                         "target_identity TEXT NOT NULL, route TEXT NOT NULL, received_at TEXT NOT NULL, "
                         "docker_status TEXT NOT NULL CHECK(docker_status IN ('received','confirmed','failed')))")

    def accept(self, action_id, capability, target, route, identity):
        with self._lock:
            try:
                self._db.execute("INSERT INTO action_journal "
                                 "(action_id, capability, target, target_identity, route, received_at, docker_status) "
                                 "VALUES (?,?,?,?,?,?,'received')",
                                 (action_id, capability, target, json.dumps(identity, sort_keys=True), route,
                                  datetime.now(timezone.utc).isoformat()))
            except sqlite3.IntegrityError as exc:
                raise GatewayRefused("action id already accepted") from exc

    def finish(self, action_id, status):
        with self._lock:
            self._db.execute("UPDATE action_journal SET docker_status=? "
                             "WHERE action_id=? AND docker_status='received'", (status, action_id))

    def status(self, action_id):
        with self._lock:
            row = self._db.execute("SELECT docker_status FROM action_journal WHERE action_id=?", (action_id,)).fetchone()
        return row[0] if row else None

    def close(self):
        self._db.close()


class ActionGateway:
    def __init__(self, host, token, journal, proxy, *, released=None):
        self.host, self.token, self.journal, self.proxy = host, token, journal, proxy
        pairs = dict(released or {})
        if pairs and host == "vm-095":
            raise GatewayRefused("Argus's own host cannot have an action route")
        for (capability, target), route in pairs.items():
            if not re.fullmatch(re.escape(host) + r"/container:argus-lab-[A-Za-z0-9_.-]+", target):
                raise GatewayRefused("only an exact lab container on this host may be configured")
            name = target.split(":", 1)[1]
            verb = capability.removeprefix("container.")
            if verb not in {"start", "stop", "restart", "pause", "unpause"} or route != f"POST /containers/{name}/{verb}":
                raise GatewayRefused("capability and exact Docker route differ")
        self.released = MappingProxyType(pairs)

    def _authenticate(self, token, action_id):
        if not self.token or not token or not hmac.compare_digest(token, self.token):
            raise GatewayRefused("invalid gateway credential")
        if not ACTION_ID.fullmatch(action_id):
            raise GatewayRefused("invalid action id")

    def dispatch(self, token, action_id, capability, target, route, identity):
        self._authenticate(token, action_id)
        if self.released.get((capability, target)) != route or not self.released:
            raise GatewayRefused("route and target pair is not released")
        if not target.startswith(self.host + "/container:") or not isinstance(identity, dict) or not identity:
            raise GatewayRefused("invalid host-qualified target or identity")
        if self.proxy.identity(target) != identity:
            raise GatewayRefused("target identity changed")
        self.journal.accept(action_id, capability, target, route, identity)
        result = self.proxy.execute(route, action_id, identity)
        if result not in ("confirmed", "failed"):
            raise GatewayRefused("proxy did not report a definitive result")
        self.journal.finish(action_id, result)
        return result

    def status(self, token, action_id):
        self._authenticate(token, action_id)
        return self.journal.status(action_id)
