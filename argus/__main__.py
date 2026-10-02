"""argus serve | user add|disable | db import-sqlite PATH|check | diagnose TARGET [--raw] | incident ID [--raw]"""
from __future__ import annotations

import argparse
import asyncio
import getpass
import logging
import threading
import time

from argus.infrastructure.wiring import Settings, build, make_store


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


def serve() -> None:
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


def main() -> None:
    p = argparse.ArgumentParser(prog="argus")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("serve")
    u = sub.add_parser("user")
    u.add_argument("action", choices=["add", "disable"])
    u.add_argument("name")
    u.add_argument("--role", default="operator", choices=["viewer", "operator", "approver"])
    u.add_argument("--scopes", nargs="*", default=["lab"])
    d = sub.add_parser("db", help="Postgres system of record: import the lab SQLite history, prove the guarantees")
    d.add_argument("action", choices=["import-sqlite", "check"])
    d.add_argument("path", nargs="?", default="/data/argus.db")
    from argus.adapters.inbound.cli.main import add_parsers, run
    add_parsers(sub)
    a = p.parse_args()
    if a.cmd == "serve":
        serve()
    elif a.cmd == "user":
        user(a)
    elif a.cmd == "db":
        db(a)
    else:
        raise SystemExit(run(a))


if __name__ == "__main__":
    main()
