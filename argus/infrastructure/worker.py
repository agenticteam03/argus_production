"""The worker loop (T-0014, ARCHITECTURE §6.2): claims queued incidents one at a time and runs them.

A claim is a lease. The worker renews it while a run lasts; when the worker dies the lease expires and another worker
(or this one after a restart) requeues the incident, and the graph runner resumes it from its checkpoint. The worker
recovers only expired claims, so it never takes a run another live worker holds; it checks at start and every
`recover_every_s` while it runs (a restarted worker comes back before the dead one's lease has expired).

OP-009: a renewal that fails (a database error) is retried until the lease has really expired. A lost claim
(another worker owns it, or the lease expired while retrying) cancels the run: the runner stops at its next node and
writes nothing more, so two workers never run the same incident.

inc_6a4980a4d8ed: a run that stops at an interrupt (an approval, a fresh verification sample) is parked, not left
claimed: `claimed_by` is cleared and the claim ends at the approval's expiry. The approval's answer requeues it at once.
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
                 recover_every_s: float = 5.0, db_retry_s: float = 5.0):
        self.app = app
        self.max_queued_age_s = max_queued_age_s
        self.now = now
        self.worker_id = worker_id or f"{socket.gethostname()}:{os.getpid()}"
        self.lease_s = lease_s
        self.renew_every_s = renew_every_s if renew_every_s is not None else lease_s / 3
        self.idle_s = idle_s
        # A crashed worker is restarted within seconds while its lease is still live: re-check while running. Every
        # 5 s (ARGUS_WORKER_RECOVER_S): a parked run whose approval expired resumes within one check; one cheap UPDATE.
        self.recover_every_s = recover_every_s
        self.db_retry_s = db_retry_s                  # T-0030: pause after a database error, then retry

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
        if not lost.is_set():
            self._park_if_paused(inc.id)
        return inc.id

    def _park_if_paused(self, incident_id: str) -> None:
        """inc_6a4980a4d8ed: a run paused at an interrupt looked live (claimed, lease in the future), so an approval
        waited for the claim to expire. It is parked instead: no worker holds it, and its claim ends at the pending
        approval's expiry (one lease when no approval waits). The answer requeues a parked run in the transaction that
        records it; an answer given before the park committed is found by the check that follows the park."""
        paused = getattr(self.app.runner, "paused", None)          # the plain runner never pauses
        waiting = paused(incident_id) if paused is not None else None
        if waiting is None:
            return
        approval_id = waiting.get("approval_id")
        if not self.app.store.park_claim(incident_id, self.worker_id, approval_id, lease_s=self.lease_s):
            return                                                 # no longer this worker's claim
        log.info("parked %s: waiting for %s", incident_id, approval_id or "a fresh verification sample")
        if approval_id and self.app.store.wake_answered(incident_id, approval_id):
            log.info("requeued %s: approval %s was answered while the run was live", incident_id, approval_id)

    def run_forever(self, stop: threading.Event) -> None:
        """T-0030: a database error (Postgres restarting) is a pause, never the end of the loop: it is logged, the
        worker waits `db_retry_s` and tries again, like the scheduler. A run in progress is not affected here: its
        own errors end in `run_once`, and its claim expires and is requeued if it could not be recorded."""
        next_recover = time.monotonic()                     # recover at start, then every recover_every_s
        while not stop.is_set():
            try:
                if time.monotonic() >= next_recover:
                    self.recover()
                    next_recover = time.monotonic() + self.recover_every_s
                if self.run_once() is None:
                    stop.wait(self.idle_s)
            except Exception:                  # noqa: BLE001 - the database is down or restarting
                log.warning("database call failed; retry in %.0f s", self.db_retry_s, exc_info=True)
                stop.wait(self.db_retry_s)

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
        failing = False
        while True:
            # While renewals fail, wake at the lease's expiry at the latest: the run stops when the lease is gone,
            # not up to one renewal interval later (review of PR #53).
            wait = min(self.renew_every_s, max(0.0, expires - time.monotonic())) if failing else self.renew_every_s
            if done.wait(wait):
                return
            if failing and time.monotonic() >= expires:
                log.error("could not renew the claim on %s before it expired; stopping the run", incident_id)
                lost.set()
                return
            try:
                renewed = self.app.store.renew_claim(incident_id, self.worker_id, lease_s=self.lease_s)
            except Exception:                  # noqa: BLE001 - a failed renewal is retried while the lease lasts
                failing = True
                if time.monotonic() < expires:
                    log.warning("renewing the claim on %s failed; retrying", incident_id, exc_info=True)
                    continue
                log.error("could not renew the claim on %s before it expired; stopping the run", incident_id)
                lost.set()
                return
            failing = False
            if not renewed:
                log.error("lost the claim on %s (another worker may own it); stopping the run", incident_id)
                lost.set()
                return
            expires = time.monotonic() + self.lease_s


def stale(inc: Incident, now: datetime, max_queued_age_s: int) -> bool:
    """§6.5 maximum queued age: only scheduled requests go stale; manual, alert and peer requests never do."""
    return inc.trigger_kind == TriggerKind.scheduled and now - inc.opened_at > timedelta(seconds=max_queued_age_s)
