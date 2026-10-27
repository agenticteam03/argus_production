"""The gateway listener exposes only the configured exact route and action-status read."""
from __future__ import annotations

import json
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from services.action_gateway.core import ActionGateway, ActionJournal
from services.action_gateway.server import make_handler
from test_phase19_gateway import ACTION_ID, IDENTITY, ROUTE, TARGET, FakeProxy


def _request(base, method, path, *, token=None, action_id=None, body=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    if action_id:
        headers["X-Argus-Action-Id"] = action_id
    data = json.dumps(body).encode() if body is not None else None
    try:
        with urlopen(Request(base + path, data=data, headers=headers, method=method), timeout=3) as response:
            return response.status, json.load(response)
    except HTTPError as exc:
        return exc.code, json.load(exc)


def test_http_listener_denies_unlisted_routes_and_exposes_journal_status(tmp_path):
    proxy = FakeProxy()
    journal = ActionJournal(tmp_path / "journal.db")
    gateway = ActionGateway("vm-166", "test-secret", journal, proxy,
                            released={("container.start", TARGET): ROUTE})
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(gateway))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    body = {"capability": "container.start", "target": TARGET, "target_identity": IDENTITY}
    try:
        assert _request(base, "POST", "/containers/argus-lab-cache/start", body=body)[0] == 403
        assert _request(base, "POST", "/containers/argus-lab-cache/start", token="test-secret", body=body)[0] == 403
        assert _request(base, "POST", "/containers/argus-lab-cache/start?extra=1", token="test-secret",
                        action_id=ACTION_ID, body=body)[0] == 404
        assert _request(base, "POST", "/containers/argus-v18-agent/start", token="test-secret",
                        action_id=ACTION_ID, body=body)[0] == 403
        assert proxy.calls == []
        code, result = _request(base, "POST", "/containers/argus-lab-cache/start", token="test-secret",
                                action_id=ACTION_ID, body=body)
        assert code == 200 and result["status"] == "confirmed"
        assert _request(base, "GET", f"/actions/{ACTION_ID}", token="test-secret")[1]["status"] == "confirmed"
        assert _request(base, "GET", f"/actions/{ACTION_ID}", token="wrong")[0] == 403
        assert _request(base, "POST", "/containers/argus-lab-cache/start", token="test-secret",
                        action_id=ACTION_ID, body=body)[0] == 409
        assert len(proxy.calls) == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        journal.close()
