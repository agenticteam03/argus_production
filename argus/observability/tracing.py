"""Optional, filtered OTLP tracing of the worker's investigations, for a self-hosted Langfuse (ACR-0013, §18.5).

Telemetry, never audit (§18.1): it may be dropped. `TracingEventSink` sits behind the runner's run-event sink: it
passes every event on unchanged, then turns the same events into spans. One root span per execution attempt, a child
span per graph node, and one per capability read inside `act`. Only allowlisted attributes leave the worker: names,
statuses, error categories, steps, opaque evidence ids, the host name and the incident's class, strategy and outcome.
Never prompts, replies, tool arguments or results, evidence bodies, signal values, runbook passages, diagnoses,
target addresses or secrets.

`OtlpExporter` sends OTLP/HTTP JSON to Langfuse's native endpoint from its own thread, through a bounded queue: a full
queue, an unreachable Langfuse or an error drops spans and counts them (`dropped`); the graph never waits. Off by
default (`ARGUS_TRACING_ENABLED`); only the worker gets the Langfuse project keys.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import queue
import threading
import time
import urllib.request
import uuid
from typing import Any, Callable

log = logging.getLogger("argus.tracing")

# run-event data key -> exported attribute; anything else in an event is never exported
ALLOWED = {"capability": "argus.capability", "status": "argus.status", "error_category": "argus.error_category",
           "step": "argus.step", "decided_by": "argus.decided_by", "evidence_id": "argus.evidence_id",
           "host": "argus.host"}
ROOT_KEYS = {"incident_class": "argus.incident_class", "strategy": "argus.strategy", "outcome": "argus.outcome"}


def _attr(key: str, value: Any) -> dict:
    if isinstance(value, bool):
        return {"key": key, "value": {"boolValue": value}}
    if isinstance(value, int):
        return {"key": key, "value": {"intValue": str(value)}}
    return {"key": key, "value": {"stringValue": str(value)[:200]}}


def _id(nbytes: int) -> str:
    return os.urandom(nbytes).hex()


class OtlpExporter:
    def __init__(self, endpoint: str, public_key: str, secret_key: str, *, post: Callable | None = None,
                 max_queue: int = 2000, batch_size: int = 64, flush_interval: float = 2.0, timeout: float = 3.0):
        self.endpoint, self.timeout = endpoint, timeout
        self.batch_size, self.flush_interval = batch_size, flush_interval
        auth = base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()
        self.headers = {"Authorization": f"Basic {auth}", "Content-Type": "application/json",
                        "x-langfuse-ingestion-version": "4"}
        self.post = post or self._http_post
        self.dropped = self.exported = 0
        self._q: queue.Queue = queue.Queue(maxsize=max_queue)
        self._stop = threading.Event()
        self._warned = False
        self._thread = threading.Thread(target=self._loop, name="argus-otlp-exporter", daemon=True)
        self._thread.start()

    # --- the graph's side: never blocks ---------------------------------------------------------------------------
    def submit(self, span: dict) -> None:
        try:
            self._q.put_nowait(span)
        except queue.Full:
            self._drop(1, "queue full")

    def close(self, timeout: float = 2.0) -> None:
        """Flush what is queued, bounded by `timeout`; whatever is left is dropped."""
        self._stop.set()
        self._thread.join(timeout)
        left = self._q.qsize()
        if left:
            self._drop(left, "shutdown")

    # --- the exporter thread --------------------------------------------------------------------------------------
    def _loop(self) -> None:
        while True:
            batch = []
            try:
                batch.append(self._q.get(timeout=0.05 if self._stop.is_set() else self.flush_interval))
            except queue.Empty:
                if self._stop.is_set():
                    return
                continue
            while len(batch) < self.batch_size:
                try:
                    batch.append(self._q.get_nowait())
                except queue.Empty:
                    break
            self._send(batch)

    def _send(self, batch: list[dict]) -> None:
        body = json.dumps({"resourceSpans": [{
            "resource": {"attributes": [_attr("service.name", "argus-worker")]},
            "scopeSpans": [{"scope": {"name": "argus"}, "spans": batch}]}]})
        try:
            self.post(self.endpoint, self.headers, body, self.timeout)
            self.exported += len(batch)
        except Exception as e:                               # fail-open: telemetry only
            self._drop(len(batch), f"{type(e).__name__}")

    def _drop(self, n: int, why: str) -> None:
        self.dropped += n
        if not self._warned:
            log.warning("tracing: %d span(s) dropped (%s); investigations are not affected", n, why)
            self._warned = True

    @staticmethod
    def _http_post(url: str, headers: dict, body: str, timeout: float) -> None:
        req = urllib.request.Request(url, data=body.encode(), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as r:          # noqa: S310 (a configured internal URL)
            if r.status >= 300:
                raise OSError(f"OTLP export answered {r.status}")


class TracingEventSink:
    """The runner's event sink, plus spans. `inner` (the store) always gets the event first and unchanged."""

    def __init__(self, inner, exporter: OtlpExporter, now: Callable[[], int] = time.time_ns):
        self.inner, self.exporter, self.now = inner, exporter, now
        self._attempts: dict[str, dict] = {}
        self._lock = threading.Lock()

    def append_run_event(self, incident_id: str, node: str, phase: str, data: dict[str, Any]) -> None:
        if self.inner is not None:
            self.inner.append_run_event(incident_id, node, phase, data)
        try:
            self._trace(incident_id, node, phase, data or {})
        except Exception:                                    # tracing never fails the run
            log.warning("tracing: an event of %s could not be traced", incident_id)

    def end_open_attempts(self, reason: str) -> None:
        """Close every attempt still open (the worker stops): its root span ends with an error status."""
        with self._lock:
            ids = list(self._attempts)
        for incident_id in ids:
            self._end_attempt(incident_id, error=reason)

    # --- spans --------------------------------------------------------------------------------------------------------
    def _trace(self, incident_id: str, node: str, phase: str, data: dict) -> None:
        with self._lock:
            a = self._attempts.get(incident_id)
            if a is None:
                a = self._attempts[incident_id] = {
                    "trace": _id(16), "root": _id(8), "start": self.now(), "open": {},
                    "attrs": {"argus.incident_id": incident_id, "argus.attempt": uuid.uuid4().hex[:12]}}
            for k, name in ROOT_KEYS.items():
                if data.get(k):
                    a["attrs"][name] = data[k]
        if phase == "enter":
            a["open"][node] = (_id(8), self.now(), self._allowed(data))
        elif phase == "step":
            parent = a["open"].get(node, (a["root"],))[0]
            t = self.now()
            self.exporter.submit(self._span(a, "capability", _id(8), parent, t, t,
                                            {"argus.node": node, **self._allowed(data)}, data.get("status")))
        elif phase == "exit":
            span_id, start, attrs = a["open"].pop(node, (_id(8), self.now(), {}))
            self.exporter.submit(self._span(a, node, span_id, a["root"], start, self.now(),
                                            {"argus.node": node, **attrs, **self._allowed(data)}, None))
            if node == "record":
                self._end_attempt(incident_id)

    def _end_attempt(self, incident_id: str, error: str | None = None) -> None:
        with self._lock:
            a = self._attempts.pop(incident_id, None)
        if a is None:
            return
        for node, (span_id, start, attrs) in list(a["open"].items()):          # nodes left open by a dead attempt
            self.exporter.submit(self._span(a, node, span_id, a["root"], start, self.now(), {"argus.node": node, **attrs},
                                            "error"))
        self.exporter.submit(self._span(a, "argus.investigation", a["root"], None, a["start"], self.now(), a["attrs"],
                                        "error" if error else None))

    @staticmethod
    def _allowed(data: dict) -> dict:
        return {name: data[k] for k, name in ALLOWED.items() if data.get(k) not in (None, "", [])}

    @staticmethod
    def _span(a: dict, name: str, span_id: str, parent: str | None, start: int, end: int, attrs: dict,
              status: str | None) -> dict:
        span = {"traceId": a["trace"], "spanId": span_id, "name": name, "kind": 1,
                "startTimeUnixNano": str(start), "endTimeUnixNano": str(max(end, start)),
                "attributes": [_attr(k, v) for k, v in attrs.items()]}
        if parent:
            span["parentSpanId"] = parent
        if status in ("error", "refused", "timeout"):
            span["status"] = {"code": 2}
        return span
