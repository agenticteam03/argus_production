"""Separate gateway/proxy processes. Neither starts with an empty release map."""
from __future__ import annotations

import json
import os
import socketserver
from http.server import ThreadingHTTPServer
from pathlib import Path

from services.action_gateway.core import ActionGateway, ActionJournal, validated_pairs
from services.action_gateway.server import make_handler
from services.action_gateway.socket_proxy import SocketProxyPolicy, make_proxy_handler
from services.action_gateway.unix_transport import DockerSocketClient, GatewayProxyTransport, UnixRequester


CONFIG = Path("/etc/argus-v18/action-gateway.json")
TOKEN = Path("/run/argus-v18/action_token")
PROXY_SOCKET = "/run/argus-v18/action-proxy.sock"
DOCKER_SOCKET = "/var/run/docker.sock"
JOURNAL = Path("/var/lib/argus-v18/action-journal.db")


def load_config(path):
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {"host", "released"}:
        raise ValueError("gateway config fields differ")
    host, releases = raw["host"], raw["released"]
    if host not in ("vm-095", "vm-166") or not isinstance(releases, list):
        raise ValueError("invalid host or releases")
    pairs = {}
    for item in releases:
        base_fields = {"capability", "target", "route"}
        network_fields = base_fields | {"connect_network", "disconnect_network"}
        if (not isinstance(item, dict) or set(item) not in (base_fields, network_fields)
                or (item.get("capability") == "network.restore") != (set(item) == network_fields)):
            raise ValueError("release fields differ")
        if not all(isinstance(value, str) for value in item.values()):
            raise ValueError("release fields must be strings")
        key = (item["capability"], item["target"])
        if key in pairs:
            raise ValueError("duplicate released pair")
        pairs[key] = ({"route": item["route"], "connect_network": item["connect_network"],
                       "disconnect_network": item["disconnect_network"]}
                      if item["capability"] == "network.restore" else item["route"])
    return host, dict(validated_pairs(host, pairs))


def main():
    host, released = load_config(CONFIG)
    if not released:
        raise RuntimeError("action gateway and proxy must not start with an empty release map")
    role = os.environ.get("ARGUS_ACTION_ROLE", "")
    if role == "gateway":
        token = TOKEN.read_text(encoding="utf-8").strip()
        if len(token) < 32:
            raise RuntimeError("action token is unavailable")
        gateway = ActionGateway(host, token, ActionJournal(JOURNAL),
                                GatewayProxyTransport(UnixRequester(PROXY_SOCKET)), released=released)
        server = ThreadingHTTPServer(("0.0.0.0", 8705), make_handler(gateway))
    elif role == "proxy":
        if os.path.exists(PROXY_SOCKET):
            raise RuntimeError("proxy socket already exists")
        os.umask(0o077)
        policy = SocketProxyPolicy(host, released, DockerSocketClient(DOCKER_SOCKET))

        class UnixServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
            daemon_threads = True

        server = UnixServer(PROXY_SOCKET, make_proxy_handler(policy))
    else:
        raise RuntimeError("ARGUS_ACTION_ROLE must be gateway or proxy")
    server.serve_forever()


if __name__ == "__main__":
    main()
