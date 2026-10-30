"""ACR-0043 with T-0021 (ARCHITECTURE §12.6): the console's reads and write proposals run in the worker.

The API never investigates: it holds no executor token and no action path. A console command that needs either is
one `console_job` row (migration 022): `ConsoleJobs.run` (the API) inserts it and waits for the answer;
`ConsoleJobRunner` (a thread of `argus worker`, on while ARGUS_OPERATOR_CONSOLE=1) claims it, runs it with the
worker's guarded invoke or action path, and stores the result. A `read` names one of the console's own read
capabilities (anything else is refused before invoke, which still applies policy, inventory, redaction and audit);
a `propose` names a write command and its released pair (`proposals.propose_write`). Who may run what was decided by
the API (the console session, the permission, the quota) before the row was written.
"""
from __future__ import annotations

import logging
import os
import socket
import threading
import time
import uuid
from datetime import datetime, timedelta
from typing import Any, Callable

from argus.domain.model import TargetRef, utcnow

log = logging.getLogger("argus.console")

READ, PROPOSE = "read", "propose"
# The capabilities the console's handlers read (console/handlers.py); a job naming another one is refused.
READ_CAPABILITIES = frozenset({"container.status", "container.search_logs", "metrics.cpu_history",
                               "host.cpu", "host.memory", "host.disk_usage"})


class JobFailed(Exception):
    """The worker answered with an error, or did not answer in time; the message is safe to show."""


class ConsoleJobs:
    """The API's side: queue one job and wait for the worker's answer."""

    def __init__(self, store, config, *, poll_s: float = 0.1, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep):
        self.store, self.config, self.poll_s, self.clock, self.sleep = store, config, poll_s, clock, sleep

    def run(self, kind: str, incident_id: str, person: str, request: dict[str, Any]) -> dict[str, Any]:
        timeout = self.config.propose_timeout_s if kind == PROPOSE else self.config.job_timeout_s
        job_id = f"cjb_{uuid.uuid4().hex[:16]}"
        self.store.add_console_job(job_id, kind, incident_id, person, request, utcnow())
        deadline = self.clock() + timeout
        while True:
            job = self.store.get_console_job(job_id)
            if job is not None and job["status"] == "done":
                return job["result"]
            if job is not None and job["status"] == "error":
                raise JobFailed((job["result"] or {}).get("error") or "the worker could not run it")
            if self.clock() >= deadline:
                raise JobFailed(f"the worker did not answer within {timeout:g} s; is `argus worker` running with "
                                "the console on?")
            self.sleep(self.poll_s)


class ConsoleJobRunner:
    """The worker's side: one job at a time, beside the investigation the worker may be running."""

    def __init__(self, app, config, worker_id: str | None = None, *, idle_s: float = 0.25,
                 db_retry_s: float = 5.0, now: Callable[[], datetime] = utcnow):
        self.app, self.config, self.idle_s, self.db_retry_s, self.now = app, config, idle_s, db_retry_s, now
        self.worker_id = worker_id or f"{socket.gethostname()}:{os.getpid()}:console"
        self._lock = threading.Lock()           # one proposal at a time, as the API's per-incident lock did

    def run_once(self) -> str | None:
        """Claim and answer one job; its id, or None when none is waiting."""
        now = self.now()
        oldest = now - timedelta(seconds=max(self.config.job_timeout_s, self.config.propose_timeout_s))
        job = self.app.store.claim_console_job(self.worker_id, since=oldest, at=now)
        if job is None:
            return None
        try:
            status, result = "done", self._answer(job)
        except JobFailed as exc:
            status, result = "error", {"error": str(exc)}
        except Exception:                       # logged here; never shown (it may name internals)
            log.exception("console job %s failed", job["job_id"])
            status, result = "error", {"error": "the worker could not run it"}
        self.app.store.finish_console_job(job["job_id"], status, result, self.now())
        return job["job_id"]

    def _answer(self, job: dict[str, Any]) -> dict[str, Any]:
        incident = self.app.store.get_incident(job["incident_id"])
        if incident is None:
            raise JobFailed(f"the incident {job['incident_id']} does not exist")
        request = job["request"]
        if job["kind"] == READ:
            capability, target = request.get("capability"), str(request.get("target"))
            if capability not in READ_CAPABILITIES:
                raise JobFailed(f"{capability} is not a console read")
            from argus.application.invoke_capability import InvocationContext
            ctx = InvocationContext(incident=incident, caller=f"console:{job['person']}",
                                    scope={TargetRef.parse(target)}, counters={})
            observation, _ = self.app.runner.invoke(ctx, capability, {"target": target, **request.get("arguments", {})})
            return observation.model_dump(mode="json")
        if job["kind"] == PROPOSE:
            from argus.console.proposals import propose_write
            pair = (request["capability"], request["target"])
            return propose_write(self.app, incident, pair, request["command"],
                                 datetime.fromisoformat(request["started_at"]), self._lock)
        raise JobFailed(f"unknown console job {job['kind']}")

    def run_forever(self, stop: threading.Event) -> None:
        """Like the worker's loop: a database error is a pause, never the end."""
        log.info("console jobs on (%s)", self.worker_id)
        while not stop.is_set():
            try:
                if self.run_once() is None:
                    stop.wait(self.idle_s)
            except Exception:                   # noqa: BLE001 - the database is down or restarting
                log.warning("console job claim failed; retry in %.0f s", self.db_retry_s, exc_info=True)
                stop.wait(self.db_retry_s)
