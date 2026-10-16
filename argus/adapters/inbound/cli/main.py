"""CLI client: `argus diagnose` / `argus incident` / `argus demo`, formatted (default) or --raw.

Talks to the Argus API with a JWT, so it works the same on the agent host or through an SSH tunnel.
  ARGUS_API       default http://127.0.0.1:18000
  ARGUS_USER      default the current OS user
  ARGUS_PASSWORD  optional; otherwise prompted
"""
from __future__ import annotations

import getpass
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from argus.adapters.inbound.cli.render import Formatter, raw_event, raw_incident


class Client:
    def __init__(self, api: str, user: str, password: str):
        self.api = api.rstrip("/")
        self.token = None
        body = urllib.parse.urlencode({"username": user, "password": password}).encode()
        self.token = self._req("POST", "/api/v1/auth/token", body, form=True)["access_token"]

    def _req(self, method: str, path: str, body: bytes | None = None, form: bool = False):
        r = urllib.request.Request(self.api + path, data=body, method=method)
        r.add_header("Content-Type", "application/x-www-form-urlencoded" if form else "application/json")
        if self.token:
            r.add_header("Authorization", f"Bearer {self.token}")
        with urllib.request.urlopen(r, timeout=30) as resp:
            return json.loads(resp.read())

    def investigate(self, target: str, reason: str, kind: str) -> dict:
        body = json.dumps({"target": target, "reason": reason, "request_kind": kind}).encode()
        return self._req("POST", "/api/v1/investigations", body)

    def incident(self, iid: str) -> dict:
        return self._req("GET", f"/api/v1/incidents/{iid}")

    def events(self, iid: str, after: int) -> list[dict]:
        return self._req("GET", f"/api/v1/incidents/{iid}/events?after={after}")


def follow(client: Client, iid: str, raw: bool, color: bool, timeout_s: int = 600) -> int:
    fmt = Formatter(color=color)
    seq, start = 0, time.time()
    while True:
        for ev in client.events(iid, seq):
            seq = ev["seq"]
            if raw:
                print(raw_event(ev), flush=True)
            else:
                for line in fmt.event(ev):
                    print(line, flush=True)
        inc = client.incident(iid)
        if inc["status"] in ("closed", "escalated"):
            for ev in client.events(iid, seq):            # drain events written after the status change
                print(raw_event(ev) if raw else "\n".join(fmt.event(ev)), flush=True)
            if raw:
                print(raw_incident(inc), flush=True)
            return 0 if inc["outcome"] in ("diagnosed", "no_incident") else 2
        if time.time() - start > timeout_s:
            print("timeout waiting for the investigation", file=sys.stderr)
            return 3
        time.sleep(1.0)


def run(args) -> int:
    if args.cmd == "demo":                                   # offline replay: no API, no login
        from argus.adapters.inbound.cli.demo import run as run_demo
        return run_demo(args)
    api = os.getenv("ARGUS_API", "http://127.0.0.1:18000")
    user = args.user or os.getenv("ARGUS_USER") or getpass.getuser()
    password = os.getenv("ARGUS_PASSWORD") or getpass.getpass(f"Argus password for {user}: ")
    color = sys.stdout.isatty() and not args.no_color and not args.raw
    try:
        client = Client(api, user, password)
        if args.cmd == "diagnose":
            res = client.investigate(args.target, args.reason, "check" if args.check else "report")
            if not args.raw:
                print(f"incident {res['incident_id']}" + ("  (duplicate)" if res.get("duplicate") else ""))
            return follow(client, res["incident_id"], args.raw, color)
        return follow(client, args.incident_id, args.raw, color)
    except urllib.error.HTTPError as e:
        print(f"Argus API error {e.code}: {e.read()[:300]!r}", file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(f"cannot reach Argus at {api}: {e.reason}", file=sys.stderr)
        return 1


def add_parsers(sub) -> None:
    d = sub.add_parser("diagnose", help="start an investigation and follow it live")
    d.add_argument("target", help="host/kind:name, e.g. vm-166/container:argus-lab-worker")
    d.add_argument("--reason", default="", help="what was observed")
    d.add_argument("--check", action="store_true", help="'is it healthy?' instead of 'there is a problem'")
    i = sub.add_parser("incident", help="show an existing incident")
    i.add_argument("incident_id")
    m = sub.add_parser("demo", help="paced replay of a recorded investigation for a live presentation")
    m.add_argument("--duration", type=float, default=180.0, help="total seconds (default 180)")
    m.add_argument("--events", default="contracts/samples/events.json", help="recorded run events (JSON list)")
    m.add_argument("--no-color", action="store_true")
    for p in (d, i):
        p.add_argument("--raw", action="store_true", help="raw JSON lines (events) + full incident JSON")
        p.add_argument("--no-color", action="store_true")
        p.add_argument("--user", default=None)
