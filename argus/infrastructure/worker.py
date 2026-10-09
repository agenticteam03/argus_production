"""The worker loop (T-0014, ARCHITECTURE §6.2): claims queued incidents one at a time and runs them.

A claim is a lease. The worker renews it while a run lasts; when the worker dies the lease expires and another worker
(or this one after a restart) requeues the incident, and the graph runner resumes it from its checkpoint. The worker
recovers only expired claims, so it never takes a run another live worker holds; it checks at start and every
`recover_every_s` while it runs (a restarted worker comes back before the dead one's lease has expired).

OP-009: a renewal that fails (a database error) is retried until the lease has really expired. A lost claim
(another worker owns it, or the lease expired while retrying) cancels the run: the runner stops at its next node and
writes nothing more, so two workers never run the same incident.
"""
from __future__ import annotations

import logging
import os
import socket
import threading
import time
import uuid
from datetime import datetime, timedelta
from typing import Callable

from argus.domain.model import AuditRecord, Incident, IncidentStatus, TriggerKind, utcnow

log = logging.getLogger("argus.worker")


class Worker:
    def __init__(self, app, worker_id: str | None = None, lease_s: int = 300, renew_every_s: float | None = None,
                 idle_s: float = 1.0, max_queued_age_s: int = 900, now: Callable[[], datetime] = utcnow,
                 recover_every_s: float = 30.0):
        self.app = app
        self.max_queued_age_s = max_queued_age_s
        self.now = now
        self.worker_id = worker_id or f"{socket.gethostname()}:{os.getpid()}"
        self.lease_s = lease_s
        self.renew_every_s = renew_every_s if renew_every_s is not None else lease_s / 3
        self.idle_s = idle_s
        # A crashed worker is restarted within seconds while its lease is still live: re-check while running.
        self.recover_every_s = recover_every_s

    def recover(self) -> int:
        n = self.app.store.requeue_expired()
        if n:
            log.warning("requeued %d runs whose claim expired", n)
        return n

    def run_once(self) -> str | None:
        """Claim and run one incident. Returns its id, or None when the queue is empty."""
        inc = self.app.store.claim_next_queued(self.worker_id, lease_s=self.lease_s)
        if inc is None:
            return None
        if stale(inc, self.now(), self.max_queued_age_s):
            self._skip_stale(inc)
            return inc.id
        done, lost = threading.Event(), threading.Event()
        renewer = threading.Thread(target=self._renew, args=(inc.id, done, lost), daemon=True)
        renewer.start()
        log.info("running %s on %s", inc.id, inc.target)
        try:
            self.app.runner.run(inc.id, cancel=lost)
        except Exception:                      # the runner records outcomes; anything else must not stop the worker
            log.exception("run %s failed", inc.id)
        finally:
            done.set()
            renewer.join()
        return inc.id

    def run_forever(self, stop: threading.Event) -> None:
        self.recover()
        next_recover = time.monotonic() + self.recover_every_s
        while not stop.is_set():
            if time.monotonic() >= next_recover:
                self.recover()
                next_recover = time.monotonic() + self.recover_every_s
            if self.run_once() is None:
                stop.wait(self.idle_s)

    def _skip_stale(self, inc: Incident) -> None:
        waited = int((self.now() - inc.opened_at).total_seconds())
        inc.status = IncidentStatus.closed
        inc.closed_at = utcnow()
        inc.diagnosis = (f"stale_skipped: the scheduled check waited {waited} s in the queue "
                         f"(maximum {self.max_queued_age_s} s); not run")
        self.app.store.update_incident(inc)
        self.app.store.append(AuditRecord(audit_id=f"aud_{uuid.uuid4().hex[:16]}", incident_id=inc.id, at=utcnow(),
                                          category="incident", event="schedule.stale_skipped", actor=self.worker_id,
                                          detail={"waited_s": waited, "max_queued_age_s": self.max_queued_age_s}))
        log.warning("skipped %s: scheduled check waited %d s", inc.id, waited)

    def _renew(self, incident_id: str, done: threading.Event, lost: threading.Event) -> None:
        expires = time.monotonic() + self.lease_s           # the claim was just taken for lease_s
        while not done.wait(self.renew_every_s):
            try:
                renewed = self.app.store.renew_claim(incident_id, self.worker_id, lease_s=self.lease_s)
            except Exception:                  # noqa: BLE001 - a failed renewal is retried while the lease lasts
                if time.monotonic() < expires:
                    log.warning("renewing the claim on %s failed; retrying", incident_id, exc_info=True)
                    continue
                log.error("could not renew the claim on %s before it expired; stopping the run", incident_id)
                lost.set()
                return
            if not renewed:
                log.error("lost the claim on %s (another worker may own it); stopping the run", incident_id)
                lost.set()
                return
            expires = time.monotonic() + self.lease_s


def stale(inc: Incident, now: datetime, max_queued_age_s: int) -> bool:
    """§6.5 maximum queued age: only scheduled requests go stale; manual, alert and peer requests never do."""
    return inc.trigger_kind == TriggerKind.scheduled and now - inc.opened_at > timedelta(seconds=max_queued_age_s)
