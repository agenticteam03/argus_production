"""argus serve | api | worker | scheduler | user add|disable | session revoke | webauthn allow-enrol|reset | db import-sqlite PATH|check | deploy record | diagnose TARGET [--raw] | incident ID [--raw]"""
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
from datetime import date

from argus.domain.model import AuditRecord, utcnow
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
    from argus.infrastructure.scheduler import (AuditChainCheck, Scheduler, load_audit_chain, load_audit_digest,
                                                load_reconcile, load_schedules, load_security_alerts)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    s = Settings()
    inventory = YamlInventory((s.config_dir / "inventory.yaml").read_text(encoding="utf-8"))
    path = Path(os.getenv("ARGUS_SCHEDULES", "deploy/scheduler/schedules.yaml"))
    text = path.read_text(encoding="utf-8")
    schedules = load_schedules(text, inventory, min_interval_s=int(os.getenv("ARGUS_SCHEDULE_MIN_INTERVAL_S", "300")))
    cfg = load_reconcile(text)
    chain_every = load_audit_chain(text)               # ACR-0018: the audit hash chain, verified on a schedule
    digest_every = load_audit_digest(text)             # ACR-0018 step 5: its signed daily digest, shipped off host
    alerting = load_security_alerts(text, inventory)   # ACR-0018 §18: security events to the team's route
    log = logging.getLogger("argus.scheduler")
    log.info("%d schedules, %d enabled; reconcile firing alerts: %s", len(schedules),
             sum(x.enabled for x in schedules), f"every {cfg.every_s} s" if cfg.enabled else "off")
    store = make_store(s)
    reconcile = links = None
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
        metrics = make_metrics(s, inventory)
        reconcile = ReconcileFiringAlerts(source, HandleAlertNotification(store, inventory, metrics),
                                          sorted(hosts), watch=watch)
        if cfg.link_states:             # ACR-0025 / T-0046 L3: the declared links' state changes (link_event)
            from argus.application.link_transitions import LinkTransitions
            links = LinkTransitions(store, inventory, metrics)
            log.info("link states: %d owner(s) recorded", len(links.owners()))
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    log.info("audit chain check: %s", f"every {chain_every} s" if chain_every else "off")
    chain = AuditChainCheck(store) if chain_every else None
    digest = None
    if digest_every:
        from argus.infrastructure.audit_digest import AuditDigestJob
        from argus.infrastructure.wiring import ed25519_signing_key, make_digest_sink
        digest = AuditDigestJob(store, ed25519_signing_key(s.secret("audit_digest_ed25519_key"),
                                                           name="audit_digest_ed25519_key"), make_digest_sink(s))
    log.info("audit digest: %s", f"every {digest_every} s" if digest_every else "off")
    alerts = None
    if alerting:
        from argus.infrastructure.security_alerts import SecurityAlerts
        alerts = SecurityAlerts(store, alerting[1])
    log.info("security alerts: %s", f"every {alerting[0]} s" if alerting else "off")
    Scheduler(store, schedules, reconcile, cfg.every_s, chain_check=chain, chain_every_s=chain_every or 86400,
              links=links, digest_job=digest, digest_every_s=digest_every or 86400,
              alerts_job=alerts, alerts_every_s=alerting[0] if alerting else 60).run_forever(stop)


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
        ended = store.revoke_principal_sessions(args.name, "argus user disable", "disabled", utcnow())
        print(f"disabled {args.name}; {ended} open session(s) ended")
        return
    pw = getpass.getpass(f"password for {args.name}: ")
    if len(pw) < 10 or pw != getpass.getpass("repeat: "):
        raise SystemExit("passwords differ or shorter than 10 characters")
    store.upsert_principal(args.name, "human", args.role, args.scopes, PasswordHash.recommended().hash(pw))
    ended = store.revoke_principal_sessions(args.name, "argus user add", "password or role changed", utcnow())
    print(f"user {args.name} saved with role {args.role}; {ended} open session(s) ended")


def audit(args) -> None:
    """ACR-0018: recompute the audit hash chain; exit 1 at the first row edited, removed or inserted outside the store.
    `check-digests` compares the shipped, signed daily digests with the chain (files downloaded from the store)."""
    from pathlib import Path

    from argus.domain.audit_chain import verify
    store = make_store(Settings())
    if args.action == "check-digests":
        from argus.infrastructure.audit_digest import check_digest_files
        if not args.paths or not args.public_key:
            raise SystemExit("check-digests needs the digest files or folders and --public-key <pem>")
        try:
            through_day = date.fromisoformat(args.through_day) if args.through_day else None
            problems = check_digest_files(args.paths, store.audit_chain(), Path(args.public_key).read_bytes(),
                                          through_day=through_day)
        except (OSError, ValueError) as e:
            raise SystemExit(f"check-digests: {e}")
        for p in problems[:50]:
            print(f"  PROBLEM  {p}")
        if problems:
            raise SystemExit(f"DIGESTS DO NOT MATCH THE CHAIN: {len(problems)} problem(s)")
        print("DIGESTS OK: signed by the audit digest key, a series without gaps, all matching the chain")
        return
    chained, before, problems = verify(store.audit_chain())
    for p in problems[:20]:
        print(f"  BROKEN  {p}")
    if problems:
        raise SystemExit(f"AUDIT CHAIN BROKEN: {len(problems)} problem(s); {chained} rows chained, {before} before the chain")
    print(f"AUDIT CHAIN OK: {chained} rows chained, {before} written before the chain (migration 011)")


def session(args) -> None:
    """ACR-0018: an administrator ends every open session of a principal at once (audited)."""
    store = make_store(Settings())
    ended = store.revoke_principal_sessions(args.name, args.who, args.reason, utcnow())
    store.append(AuditRecord(audit_id=f"aud_{uuid.uuid4().hex[:16]}", incident_id=None, at=utcnow(), category="access",
                             event="access.sessions_revoked", actor=args.who[:64],
                             detail={"principal": args.name, "ended": ended, "reason": args.reason[:200]}))
    print(f"{ended} open session(s) of {args.name} ended")


def hold_inventory(s: Settings):
    from argus.adapters.outbound.config_adapters import YamlInventory
    return YamlInventory((s.config_dir / "inventory.yaml").read_text(encoding="utf-8"))


def hold(args) -> None:
    """ACR-0019 §3.10: place, list or release a hold from vm-095 (audited). The only way to release the emergency stop
    (`*`); the browser cannot."""
    from argus.application.holds import hold_audit, validate_hold_target
    s = Settings()
    store, now = make_store(s), utcnow()
    if args.action == "place":
        validate_hold_target(args.target, hold_inventory(s))
        hold_id = f"hold_{uuid.uuid4().hex}"
        store.place_target_hold(hold_id, args.target, args.reason[:500], args.who[:64], now,
                                hold_audit("action.hold_placed", args.who, now, hold_id=hold_id, target=args.target))
        print(f"{hold_id} placed on {args.target}")
    elif args.action == "list":
        for h in store.list_active_target_holds(args.target, now):
            print(f"{h['id']}  {h['target']}  by {h['placed_by']} at {h['placed_at']}: {h['reason']}")
    else:
        h = store.get_target_hold(args.target)
        if h is None or h["released_at"] is not None:
            raise SystemExit(f"{args.target}: no active hold")
        audit = hold_audit("action.hold_released", args.who, now, hold_id=args.target, target=h["target"],
                           reason=args.reason[:500])
        if not store.release_target_hold(args.target, args.who[:64], now, audit=audit):
            raise SystemExit(f"{args.target}: no active hold")
        print(f"{args.target} released ({h['target']})")


def webauthn(args) -> None:
    """ACR-0018 step 3 (D3, D4): another administrator lets a person enrol their first credential (a one-time code,
    shown once: give it to them, never paste it into a record) or resets every credential and session of theirs."""
    from argus.application.second_factor import SecondFactor, SecondFactorRefused
    s = Settings()
    second = SecondFactor(make_store(s), s.webauthn_rp_id, s.webauthn_origin, ticket_hours=s.webauthn_enrol_ticket_hours)
    try:
        if args.action == "allow-enrol":
            code = second.allow_enrol(args.name, args.who)
            print(f"enrolment code for {args.name} (single use, {s.webauthn_enrol_ticket_hours} h): {code}")
        else:
            creds, sessions = second.reset(args.name, args.who)
            print(f"{creds} credential(s) of {args.name} revoked, {sessions} open session(s) ended")
    except SecondFactorRefused as e:
        raise SystemExit(str(e))


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

        result = prune_checkpoints(s.pg_conninfo(), days=retention_days(args), dry_run=not args.apply)
        mode = "PRUNED" if args.apply else "DRY RUN"
        print(f"{mode}: threads={result['threads']} checkpoints={result['checkpoints']} "
              f"blobs={result['blobs']} writes={result['writes']}")
    elif args.action == "prune-sessions":
        from argus.infrastructure.session_retention import prune_sessions

        result = prune_sessions(s.pg_conninfo(), days=retention_days(args), dry_run=not args.apply)
        mode = "PRUNED" if args.apply else "DRY RUN"
        print(f"{mode}: sessions={result['sessions']} revoked={result['revoked']}")


def retention_days(args) -> int:
    """`--days`, else the action's own default: checkpoints 30 (OP-004), sessions 90 (ACR-0018)."""
    if args.days is not None:
        return args.days
    if args.action == "prune-sessions":
        return int(os.getenv("ARGUS_SESSION_RETENTION_DAYS", "90"))
    return int(os.getenv("ARGUS_CHECKPOINT_RETENTION_DAYS", "30"))


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
    d.add_argument("action", choices=["import-sqlite", "check", "prune-checkpoints", "prune-sessions"])
    d.add_argument("path", nargs="?", default="/data/argus.db")
    d.add_argument("--days", type=int, default=None, help="retention window (default: checkpoints 30, sessions 90)")
    d.add_argument("--apply", action="store_true", help="delete eligible rows; default is a read-only preview")
    m = sub.add_parser("monitoring", help="ACR-0009: declare a planned stop of a host's monitoring")
    m.add_argument("action", choices=["maintenance"])
    m.add_argument("host")
    m.add_argument("--minutes", type=int, required=True, help="1..240")
    m.add_argument("--as", dest="who", required=True, help="who declares it (audited)")
    au = sub.add_parser("audit", help="ACR-0018: verify the audit hash chain, or check shipped digests against it")
    au.add_argument("action", choices=["verify", "check-digests"])
    au.add_argument("paths", nargs="*", help="check-digests: the digest files or folders")
    au.add_argument("--public-key", help="check-digests: the audit digest key's public half (PEM)")
    au.add_argument("--through-day", help="check-digests: last expected UTC day (YYYY-MM-DD); folders default to yesterday")
    se = sub.add_parser("session", help="ACR-0018: end every open session of a principal now")
    se.add_argument("action", choices=["revoke"])
    se.add_argument("name")
    se.add_argument("--as", dest="who", required=True, help="who revokes (audited)")
    se.add_argument("--reason", default="revoked by an administrator")
    ho = sub.add_parser("hold", help="ACR-0019: place, list or release a hold; `*` is the emergency stop")
    ho.add_argument("action", choices=["place", "list", "release"])
    ho.add_argument("target", help="place/list: a host, a host-qualified target or *; release: the hold id")
    ho.add_argument("--as", dest="who", default="", help="who places or releases it (audited)")
    ho.add_argument("--reason", default="")
    wa = sub.add_parser("webauthn", help="ACR-0018: a first-credential ticket for a person, or a reset of their keys")
    wa.add_argument("action", choices=["allow-enrol", "reset"])
    wa.add_argument("name")
    wa.add_argument("--as", dest="who", required=True, help="the other administrator (audited; never the person)")
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
    elif a.cmd == "session":
        session(a)
    elif a.cmd == "webauthn":
        webauthn(a)
    elif a.cmd == "hold":
        if a.action != "list" and not (a.who and a.reason):
            p.error("hold place/release needs --as and --reason")
        hold(a)
    elif a.cmd == "audit":
        audit(a)
    else:
        from argus.adapters.inbound.cli.main import run
        raise SystemExit(run(a))


if __name__ == "__main__":
    main()
