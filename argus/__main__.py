"""argus serve | api | worker | scheduler | user add|disable | db import-sqlite PATH|check | deploy record | diagnose TARGET [--raw] | incident ID [--raw]"""
from __future__ import annotations

import argparse
import asyncio
import getpass
import logging
import os
import re
import signal
import threading
import time
import uuid

from argus.infrastructure.wiring import Settings, build, make_metrics, make_store
from argus.infrastructure.worker import Worker


def _worker(app, stop: threading.Event) -> None:
    log = logging.getLogger("argus.worker")
    requeued = app.store.requeue_running()
    if requeued:
        log.warning("requeued %d interrupted runs", requeued)
    while not stop.is_set():
        inc = app.store.claim_next_queued()
        if inc is None:
            time.sleep(1.0)
            continue
        log.info("running %s on %s", inc.id, inc.target)
        app.runner.run(inc.id)


def _servers(app):
    import uvicorn
    from argus.adapters.inbound.http import build_api, build_webhook
    return [uvicorn.Server(uvicorn.Config(build_api(app), host="0.0.0.0", port=8000, log_level="info")),
            uvicorn.Server(uvicorn.Config(build_webhook(app), host="0.0.0.0", port=8001, log_level="info"))]


def api() -> None:
    """T-0014: the API and the webhook only; investigations run in `argus worker`."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    servers = _servers(build(require_credentials=False, load_credentials=False))   # T-0021: no executor token

    async def main():
        await asyncio.gather(*(s.serve() for s in servers))
    asyncio.run(main())


def worker() -> None:
    """T-0014: claims queued incidents (with a lease) and runs them; SIGTERM stops it after the current run."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    app = build()
    try:
        Worker(app, lease_s=int(os.getenv("ARGUS_WORKER_LEASE_S", "300")),
               max_queued_age_s=int(os.getenv("ARGUS_SCHEDULE_MAX_QUEUED_AGE_S", "900"))).run_forever(stop)
    finally:
        _close_tracing(app)


def _close_tracing(app) -> None:
    """ACR-0013: flush the worker's spans on a stop (bounded); a no-op when tracing is off."""
    close = getattr(app.runner.events, "close_tracing", None)
    if close is not None:
        close(timeout=2.0)


def scheduler() -> None:
    """T-0014: submits the scheduled checks of ARGUS_SCHEDULES; never runs detectors, the model or the graph."""
    from pathlib import Path

    from argus.adapters.outbound.alerts_alertmanager import AlertmanagerSource
    from argus.adapters.outbound.config_adapters import YamlInventory
    from argus.application.alerts import HandleAlertNotification, ReconcileFiringAlerts
    from argus.infrastructure.scheduler import Scheduler, load_reconcile, load_schedules
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    s = Settings()
    inventory = YamlInventory((s.config_dir / "inventory.yaml").read_text(encoding="utf-8"))
    path = Path(os.getenv("ARGUS_SCHEDULES", "deploy/scheduler/schedules.yaml"))
    text = path.read_text(encoding="utf-8")
    schedules = load_schedules(text, inventory, min_interval_s=int(os.getenv("ARGUS_SCHEDULE_MIN_INTERVAL_S", "300")))
    cfg = load_reconcile(text)
    log = logging.getLogger("argus.scheduler")
    log.info("%d schedules, %d enabled; reconcile firing alerts: %s", len(schedules),
             sum(x.enabled for x in schedules), f"every {cfg.every_s} s" if cfg.enabled else "off")
    store = make_store(s)
    reconcile = None
    if cfg.enabled:                     # ACR-0003: the pull transport profile
        hosts = {h.name: h.alertmanager for h in inventory.hosts() if h.alertmanager}
        source = AlertmanagerSource(hosts)
        watch = None
        if cfg.heartbeat:               # ACR-0009 / T-0035: the monitoring heartbeat per host
            from datetime import timedelta
            from argus.application.monitoring import MonitoringConfig, MonitoringWatch
            from argus.infrastructure.wiring import load_routing
            watch = MonitoringWatch(store, MonitoringConfig(stale_after=timedelta(seconds=cfg.stale_after_s),
                                                            grace=timedelta(seconds=cfg.grace_s)),
                                    prometheus_ready=_prometheus_ready(inventory),
                                    routing=load_routing(s.config_dir))       # #127 review: the `platform` route
            log.info("monitoring heartbeat: stale after %d s, grace %d s", cfg.stale_after_s, cfg.grace_s)
        reconcile = ReconcileFiringAlerts(source,
                                          HandleAlertNotification(store, inventory, make_metrics(s, inventory)),
                                          sorted(hosts), watch=watch)
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    Scheduler(store, schedules, reconcile, cfg.every_s).run_forever(stop)


def _prometheus_ready(inventory):
    """ACR-0009: one bounded readiness read of a host's own Prometheus (`GET /-/ready`, 3 s, read-only) to refine the
    cause of a lost heartbeat. True / False, or None when the host has no Prometheus in the inventory."""
    import httpx

    def ready(host: str) -> bool | None:
        info = next((h for h in inventory.hosts() if h.name == host), None)
        url = info.executors.get("prometheus") if info else None
        if not url:
            return None
        try:
            return httpx.get(f"{url.rstrip('/')}/-/ready", timeout=3.0).status_code == 200
        except httpx.HTTPError:
            return False
    return ready


def monitoring(args) -> None:
    """ACR-0009: declare a planned stop of a host's monitoring (no incident for a loss during it; audited)."""
    from argus.adapters.outbound.config_adapters import YamlInventory
    from argus.application.monitoring import MonitoringWatch
    s = Settings()
    inventory = YamlInventory((s.config_dir / "inventory.yaml").read_text(encoding="utf-8"))
    if args.host not in {h.name for h in inventory.hosts()}:
        raise SystemExit(f"{args.host} is not a host of the inventory")
    try:
        until = MonitoringWatch(make_store(s)).maintenance(args.host, args.minutes, args.who)
    except ValueError as e:
        raise SystemExit(str(e)) from None
    print(f"monitoring maintenance of {args.host} until {until.isoformat()} (declared by {args.who})")


DEPLOY_COMMIT = re.compile(r"^[0-9a-f]{7,40}$")
DEPLOY_REF = re.compile(r"^[A-Za-z0-9._/-]{1,100}$")
DEPLOY_ACTOR = re.compile(r"^[A-Za-z0-9-]{1,39}$")                 # a GitHub handle


def deploy(args) -> None:
    """ACR-0021 (T-0045 B7): record a deploy of a commit to a host, for the incident charts' `deploy` events. The host
    is an inventory host (default `ARGUS_HOME_HOST`, where this agent runs); commit, ref and actor are checked; audited."""
    from argus.adapters.outbound.config_adapters import YamlInventory
    from argus.domain.model import AuditRecord, utcnow
    s = Settings()
    host = args.host or s.home_host
    inventory = YamlInventory((s.config_dir / "inventory.yaml").read_text(encoding="utf-8"))
    if host not in {h.name for h in inventory.hosts()}:
        raise SystemExit(f"{host or '(no host)'} is not a host of the inventory (--host or ARGUS_HOME_HOST)")
    for value, pattern, what in ((args.commit, DEPLOY_COMMIT, "commit (7 to 40 lowercase hex)"),
                                 (args.ref, DEPLOY_REF, "ref (letters, digits, . _ / -)"),
                                 (args.who, DEPLOY_ACTOR, "--as (a GitHub handle)")):
        if not pattern.match(value or ""):
            raise SystemExit(f"not a valid {what}: {value!r}")
    store, at = make_store(s), utcnow()
    store.add_deploy_event(host, args.commit, args.ref, args.who, at)
    store.append(AuditRecord(audit_id=f"aud_{uuid.uuid4().hex[:16]}", incident_id=None, at=at, category="incident",
                             event="deploy.recorded", actor=args.who,
                             detail={"host": host, "commit": args.commit, "ref": args.ref}))
    print(f"deploy recorded: {args.commit[:12]} ({args.ref}) on {host} by {args.who}")


def serve() -> None:
    """Single process (api + webhook + worker thread): the rollback for the T-0014 split."""
    import uvicorn
    from argus.adapters.inbound.http import build_api, build_webhook

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    app = build()
    stop = threading.Event()
    threading.Thread(target=_worker, args=(app, stop), daemon=True).start()
    servers = [uvicorn.Server(uvicorn.Config(build_api(app), host="0.0.0.0", port=8000, log_level="info")),
               uvicorn.Server(uvicorn.Config(build_webhook(app), host="0.0.0.0", port=8001, log_level="info"))]

    async def main():
        await asyncio.gather(*(s.serve() for s in servers))
    try:
        asyncio.run(main())
    finally:
        stop.set()
        _close_tracing(app)


def user(args) -> None:
    from pwdlib import PasswordHash
    store = make_store(Settings())
    if args.action == "disable":
        store.set_disabled(args.name, True)
        print(f"disabled {args.name}")
        return
    pw = getpass.getpass(f"password for {args.name}: ")
    if len(pw) < 10 or pw != getpass.getpass("repeat: "):
        raise SystemExit("passwords differ or shorter than 10 characters")
    store.upsert_principal(args.name, "human", args.role, args.scopes, PasswordHash.recommended().hash(pw))
    print(f"user {args.name} saved with role {args.role}")


def db(args) -> None:
    s = Settings()
    if s.db_backend != "postgres":
        raise SystemExit("db commands need ARGUS_DB_BACKEND=postgres")
    if args.action == "import-sqlite":
        from argus.adapters.outbound.postgres_store import PostgresStore, import_sqlite
        store = PostgresStore(s.pg_conninfo())
        counts = import_sqlite(args.path, store)
        store.close()
        print("imported (new rows): " + ", ".join(f"{k}={v}" for k, v in counts.items()))
    elif args.action == "check":
        from argus.adapters.outbound.postgres_store import check
        results = check(s.pg_conninfo())
        for name, ok, detail in results:
            print(f"  {'PASS' if ok else 'FAIL'}  {name}  ({detail})")
        passed = sum(ok for _, ok, _ in results)
        print(f"{passed}/{len(results)} database checks passed (as {s.pg_user}; rolled back, nothing kept)")
        if passed != len(results):
            raise SystemExit(1)
    elif args.action == "prune-checkpoints":
        from argus.infrastructure.checkpoint_retention import prune_checkpoints

        result = prune_checkpoints(s.pg_conninfo(), days=args.days, dry_run=not args.apply)
        mode = "PRUNED" if args.apply else "DRY RUN"
        print(f"{mode}: threads={result['threads']} checkpoints={result['checkpoints']} "
              f"blobs={result['blobs']} writes={result['writes']}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="argus")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("serve")
    sub.add_parser("api")
    sub.add_parser("worker")
    sub.add_parser("scheduler")
    u = sub.add_parser("user")
    u.add_argument("action", choices=["add", "disable"])
    u.add_argument("name")
    u.add_argument("--role", default="operator", choices=["viewer", "operator", "approver"])
    u.add_argument("--scopes", nargs="*", default=["lab"])
    d = sub.add_parser("db", help="Postgres system of record: import the lab SQLite history, prove the guarantees")
    d.add_argument("action", choices=["import-sqlite", "check", "prune-checkpoints"])
    d.add_argument("path", nargs="?", default="/data/argus.db")
    d.add_argument("--days", type=int, default=int(os.getenv("ARGUS_CHECKPOINT_RETENTION_DAYS", "30")))
    d.add_argument("--apply", action="store_true", help="delete eligible checkpoints; default is a read-only preview")
    m = sub.add_parser("monitoring", help="ACR-0009: declare a planned stop of a host's monitoring")
    m.add_argument("action", choices=["maintenance"])
    m.add_argument("host")
    m.add_argument("--minutes", type=int, required=True, help="1..240")
    m.add_argument("--as", dest="who", required=True, help="who declares it (audited)")
    dp = sub.add_parser("deploy", help="ACR-0021: record a deploy (ops/deploy.sh calls it after DEPLOY OK)")
    dp.add_argument("action", choices=["record"])
    dp.add_argument("--host", default=None, help="an inventory host (default: ARGUS_HOME_HOST)")
    dp.add_argument("--commit", required=True)
    dp.add_argument("--ref", required=True)
    dp.add_argument("--as", dest="who", required=True, help="who deployed (audited)")
    from argus.adapters.inbound.cli.main import add_parsers
    add_parsers(sub)
    return p


def main() -> None:
    p = build_parser()
    a = p.parse_args()
    if a.cmd == "serve":
        serve()
    elif a.cmd == "api":
        api()
    elif a.cmd == "worker":
        worker()
    elif a.cmd == "scheduler":
        scheduler()
    elif a.cmd == "user":
        user(a)
    elif a.cmd == "db":
        db(a)
    elif a.cmd == "monitoring":
        monitoring(a)
    elif a.cmd == "deploy":
        deploy(a)
    else:
        from argus.adapters.inbound.cli.main import run
        raise SystemExit(run(a))


if __name__ == "__main__":
    main()
