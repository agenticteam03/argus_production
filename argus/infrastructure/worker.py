"""The worker loop (T-0014, ARCHITECTURE §6.2): claims queued incidents one at a time and runs them.

A claim is a lease. The worker renews it while a run lasts; when the worker dies the lease expires and another worker
(or this one after a restart) requeues the incident, and the graph runner resumes it from its checkpoint. At start the
worker recovers only expired claims, so it never takes a run another live worker holds.
"""
from __future__ import annotations

import logging
import os
import socket
import threading

log = logging.getLogger("argus.worker")


class Worker:
    def __init__(self, app, worker_id: str | None = None, lease_s: int = 300, renew_every_s: float | None = None,
                 idle_s: float = 1.0):
        self.app = app
        self.worker_id = worker_id or f"{socket.gethostname()}:{os.getpid()}"
        self.lease_s = lease_s
        self.renew_every_s = renew_every_s if renew_every_s is not None else lease_s / 3
        self.idle_s = idle_s

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
        done = threading.Event()
        renewer = threading.Thread(target=self._renew, args=(inc.id, done), daemon=True)
        renewer.start()
        log.info("running %s on %s", inc.id, inc.target)
        try:
            self.app.runner.run(inc.id)
        except Exception:                      # the runner records outcomes; anything else must not stop the worker
            log.exception("run %s failed", inc.id)
        finally:
            done.set()
            renewer.join()
        return inc.id

    def run_forever(self, stop: threading.Event) -> None:
        self.recover()
        while not stop.is_set():
            if self.run_once() is None:
                stop.wait(self.idle_s)

    def _renew(self, incident_id: str, done: threading.Event) -> None:
        while not done.wait(self.renew_every_s):
            if not self.app.store.renew_claim(incident_id, self.worker_id, lease_s=self.lease_s):
                log.error("lost the claim on %s (lease expired); another worker may resume it", incident_id)
                return
