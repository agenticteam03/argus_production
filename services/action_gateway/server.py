"""Narrow HTTP listener for the action gateway; no route is released by default."""
from __future__ import annotations

import json
import re
from http.server import BaseHTTPRequestHandler

from services.action_gateway.core import GatewayRefused


CONTAINER_PATH = re.compile(r"^/containers/[A-Za-z0-9_.-]+/(start|stop|restart|pause|unpause|network\.restore)$")
ACTION_PATH = re.compile(r"^/actions/(act_[0-9a-f]{32})$")


def _parse_post_body(path, raw):
    match = CONTAINER_PATH.fullmatch(path)
    if match is None:
        raise ValueError("invalid action path")
    try:
        body = json.loads(raw)
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid action body") from exc
    network_restore = match[1] == "network.restore"
    required = {"capability", "target", "target_identity"}
    if network_restore:
        required |= {"connect_network", "disconnect_network"}
    if (not isinstance(body, dict) or set(body) != required
            or not isinstance(body["capability"], str) or not isinstance(body["target"], str)
            or not isinstance(body["target_identity"], dict)):
        raise ValueError("invalid action body")
    if network_restore and (not isinstance(body["connect_network"], str)
                            or not isinstance(body["disconnect_network"], str)):
        raise ValueError("invalid network names")
    return body


def make_handler(gateway):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            # The durable journal records accepted actions; do not log bearer credentials or request bodies.
            pass

        def _json(self, code, body):
            data = json.dumps(body, separators=(",", ":")).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _token(self):
            value = self.headers.get("Authorization", "")
            return value[7:] if value.startswith("Bearer ") else ""

        def do_GET(self):
            match = ACTION_PATH.fullmatch(self.path)
            if match is None:
                self._json(404, {"detail": "not found"})
                return
            try:
                result = gateway.status(self._token(), match[1])
            except GatewayRefused:
                self._json(403, {"detail": "forbidden"})
                return
            self._json(200, {"status": result}) if result is not None else self._json(404, {"detail": "not found"})

        def do_POST(self):
            if CONTAINER_PATH.fullmatch(self.path) is None:
                self._json(404, {"detail": "not found"})
                return
            token = self._token()
            action_id = self.headers.get("X-Argus-Action-Id", "")
            try:
                gateway._authenticate(token, action_id)
            except GatewayRefused:
                self._json(403, {"detail": "forbidden"})
                return
            try:
                size = int(self.headers.get("Content-Length", ""))
                if not 1 <= size <= 4096:
                    raise ValueError
                body = _parse_post_body(self.path, self.rfile.read(size))
            except (ValueError, TypeError, json.JSONDecodeError):
                self._json(400, {"detail": "invalid action body"})
                return
            try:
                result = gateway.dispatch(token, action_id, body["capability"], body["target"],
                                          "POST " + self.path, body["target_identity"],
                                          connect_network=body.get("connect_network"),
                                          disconnect_network=body.get("disconnect_network"))
            except GatewayRefused as exc:
                code = 409 if str(exc) == "action id already accepted" else 403
                self._json(code, {"detail": "refused"})
                return
            except Exception:
                # An ambiguous proxy result remains `received` in the journal for reconciliation.
                self._json(503, {"detail": "action outcome pending reconciliation"})
                return
            self._json(200, {"status": result})

    return Handler
