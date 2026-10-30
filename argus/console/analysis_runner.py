"""ACR-0043 (CON-4b): Argus's comment on what a console command did, run in the background and kept per command.

The flow (spec section 8): a snapshot of the related metrics and the hypotheses when the command starts; after the
command, wait its settle delay, take two consecutive metric samples, call `analyse` with the model the application
already holds, append the evidence it cited to the incident, refresh the ranking with the deterministic `rank()`, and
store the result. The HTTP answer of the command never waits for any of it; the history route builds the analysis the
UI reads from what is stored (`view`). A failing model or missing metrics store an `error` with a short message and
never a made-up comment; a person can ask for a re-check of a retryable one.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from threading import BoundedSemaphore, Lock

from argus.application.ranking import rank
from argus.console.analysis import _sources, analyse, analysis_status
from argus.console.config import ConsoleConfig
from argus.console.parser import parse
from argus.console.registry import BY_ID, LAB_SERVICES, READ
from argus.domain.model import EvidenceRecord, EvidenceRef, Hypothesis, TargetRef, utcnow

log = logging.getLogger("argus.console")

# The metrics a command relates to: its services (a command that takes one uses it), and per service the signals of
# config/signals.yaml worth comparing before and after.
SIGNALS = {
    "cache": ("container_restart_count", "health_unhealthy", "last_exit_code", "container_memory_bytes"),
    "api": ("container_cpu_cores", "dependency_probe_min", "http_gateway_error_ratio_5m", "health_unhealthy"),
    "worker": ("jobs_processed_rate", "queue_depth", "worker_last_processed_age_s", "container_restart_count"),
    "host": ("host_cpu_busy_ratio", "host_memory_available_ratio", "host_disk_used_ratio"),
}
RELATED = {
    "status": ("api", "cache", "worker"), "cache.status": ("cache", "api"), "cache.restart": ("cache", "api"),
    "api.errors": ("api", "cache"), "api.cpu": ("api", "cache"), "host.metrics": ("host",),
    "worker.status": ("worker",), "worker.heartbeat": ("worker",), "worker.throughput": ("worker",),
    "queue.depth": ("worker",), "worker.restart": ("worker", "cache"), "net.reconnect": ("api", "cache"),
}
NOT_RETRYABLE = "this analysis is not retryable"


class DaemonPool:
    """One daemon thread per job: a job that sleeps for its settle delay never holds up the API's shutdown. The pool
    holds no slot; the runner takes one (`AnalysisRunner._slots`) only around a sample and the model call, so a job
    that is asleep never keeps another from starting. The quota bounds how many jobs can queue."""

    def submit(self, fn, *args) -> None:
        threading.Thread(target=fn, args=args, daemon=True, name="console-analysis").start()


class UnknownCommand(Exception):
    pass


class NotRetryable(Exception):
    pass


def _iso(at: datetime | None) -> str | None:
    return at.astimezone(timezone.utc).isoformat() if at else None


def _at(text: str) -> datetime:
    return datetime.fromisoformat(text)


class AnalysisRunner:
    def __init__(self, app_ctx, config: ConsoleConfig, *, now=utcnow, sleep=time.sleep, executor=None):
        self.app, self.config, self.now, self.sleep = app_ctx, config, now, sleep
        self.pool = executor or DaemonPool()
        self._slots = BoundedSemaphore(max(1, config.analysis_workers))     # sampling and the model call, never a sleep
        self._hypotheses_lock = Lock()
        self._recheck_lock = Lock()
        self._sync_lock = Lock()
        self._hold_lock = Lock()

    # --- what is related to a command ------------------------------------------------------------------------------
    def eligible(self, parsed, status: str) -> bool:
        """A read that answered ok. A write's `ok` is a proposal waiting for approval, not an action that ran: it is
        held (`hold_write`) and analysed only when its action has executed (`sync_writes`). Meta commands and refusals
        have nothing to say."""
        return self.config.analysis_enabled and parsed.cls == READ and status == "ok"

    def _targets(self, parsed) -> list[tuple[str, tuple[str, ...]]]:
        host = self.config.lab_host
        aliases = [parsed.args["service"]] if parsed.args.get("service") else list(RELATED.get(parsed.id, ()))
        found = []
        for alias in aliases:
            ref = f"{host}/host:{host}" if alias == "host" else f"{host}/container:{LAB_SERVICES[alias]}"
            try:
                known = self.app.inventory.target(TargetRef.parse(ref)) is not None
            except ValueError:
                known = False
            if known:
                found.append((ref, SIGNALS[alias]))
        return found

    # --- samples ---------------------------------------------------------------------------------------------------
    def _sample(self, targets) -> list[dict]:
        """One reading of every related target; a target with no value at all is left out (missing, never zero)."""
        samples = []
        for ref, signals in targets:
            try:
                snapshot = self.app.metrics.snapshot(TargetRef.parse(ref), set(signals))
            except Exception:                    # Prometheus down or stale: the same as no sample
                log.warning("console analysis: no metric sample for %s", ref)
                continue
            values = {k: v for k, v in snapshot.values.items() if v is not None}
            if values:
                samples.append({"target": ref, "observed_at": _iso(snapshot.observed_at), "values": values})
        return samples

    def before(self, parsed, incident) -> dict:
        """Taken when the command starts: the related metrics and the hypotheses as they are. Never in its way."""
        if not self.config.analysis_enabled:
            return {"samples": [], "hypotheses": []}
        try:
            return {"samples": self._sample(self._targets(parsed)),
                    "hypotheses": [{"id": h.id, "status": h.status, "target": h.target}
                                   for h in self._current_hypotheses(incident.id)]}
        except Exception:
            log.exception("console analysis: no before snapshot")
            return {"samples": [], "hypotheses": []}

    # --- starting, re-checking -------------------------------------------------------------------------------------
    def submit(self, row: dict, parsed, before: dict, person: str) -> None:
        settle = BY_ID[parsed.id].settle_s
        body = {"input": row["input"], "command": parsed.id, "class": parsed.cls, "person": person,
                "clock_start": _iso(row["finished_at"]), "settle_s": settle, "before": before, "after": [],
                "result": None, "rechecks": 0}
        self._put(row["command_id"], row["incident_id"], body)
        self.pool.submit(self._job, row, body)

    def hold_write(self, row: dict, incident, person: str, approval_id: str) -> None:
        """A write that created a proposal: keep the metrics from before it, and wait for its action. Nothing is
        shown, analysed or cited until the action has executed."""
        if not self.config.analysis_enabled:
            return
        parsed = parse(row["input"])
        with self._hold_lock:                    # repeating `yes` reuses the proposal: one analysis per approval
            held = self.app.store.console_analyses(row["incident_id"]).values()
            if any(b.get("approval_id") == approval_id for b in held):
                return
            body = {"input": row["input"], "command": parsed.id, "class": parsed.cls, "person": person,
                    "awaiting_action": True, "approval_id": approval_id, "clock_start": None,
                    "settle_s": BY_ID[parsed.id].settle_s, "before": self.before(parsed, incident), "after": [],
                    "result": None, "rechecks": 0}
            self._put(row["command_id"], row["incident_id"], body)

    def sync_writes(self, incident_id: str) -> None:
        """Start the analysis of every held write whose action has executed (read from the action row at read time,
        no new table): the settle delay counts from the moment the action finished, so the after-samples describe
        the lab after the change. An action that failed or is indeterminate changed nothing to compare."""
        held = {c: b for c, b in self.app.store.console_analyses(incident_id).items() if b.get("awaiting_action")}
        if not held:
            return
        with self._sync_lock:
            current = self.app.store.console_analyses(incident_id)
            for command_id in held:
                body = current.get(command_id)
                if not body or not body.get("awaiting_action"):
                    continue                     # another request started it
                action = self.app.store.get_action_for_approval(body["approval_id"])
                if action is None or action["state"] in ("unstarted", "attempting"):
                    continue
                row = next((r for r in self.app.store.console_history(incident_id, 500)
                            if r["command_id"] == command_id), None)
                if row is None:
                    continue
                body = {k: v for k, v in body.items() if k != "awaiting_action"}
                if action["state"] != "confirmed":
                    body["clock_start"] = _iso(self.now())
                    self._finish(row, body, {"status": "error", "retryable": False,
                                             "message": "The action did not complete, so there is nothing to compare"})
                    continue
                result_at = action["result_at"]
                body["clock_start"] = result_at if isinstance(result_at, str) else _iso(result_at or self.now())
                self._put(command_id, incident_id, body)
                self.pool.submit(self._job, row, body)

    def recheck(self, incident, command_id: str, person: str) -> dict:
        with self._recheck_lock:                 # check and store as one step: a second quick POST sees it running
            row, body = self._find(incident.id, command_id)
            if body.get("awaiting_action"):
                raise NotRetryable(NOT_RETRYABLE)
            if not self.view(row, body)["retryable"]:
                raise NotRetryable(NOT_RETRYABLE)
            body = {**body, "clock_start": _iso(self.now()), "settle_s": 0, "after": [], "result": None,
                    "rechecks": body.get("rechecks", 0) + 1, "rechecked_by": person}
            self._put(command_id, incident.id, body)
        self.pool.submit(self._job, row, body)
        return self.view(row, body)

    def _find(self, incident_id: str, command_id: str) -> tuple[dict, dict]:
        body = self.app.store.console_analyses(incident_id).get(command_id)
        row = next((r for r in self.app.store.console_history(incident_id, 500) if r["command_id"] == command_id), None)
        if body is None or row is None:
            raise UnknownCommand(command_id)
        return row, body

    def _put(self, command_id: str, incident_id: str, body: dict) -> None:
        self.app.store.put_console_analysis(command_id, incident_id, self._status(body), body, self.now())

    # --- the job ---------------------------------------------------------------------------------------------------
    def _job(self, row: dict, body: dict) -> None:
        try:
            self._run(row, body)
        except Exception:                        # never an exception into the pool: an honest error instead
            log.exception("console analysis of %s failed", row["command_id"])
            self._finish(row, body, {"status": "error", "message": "Analysis could not be completed",
                                     "retryable": True})

    def _run(self, row: dict, body: dict) -> None:
        start, settle = _at(body["clock_start"]), timedelta(seconds=body["settle_s"])
        wait = (start + settle - self.now()).total_seconds()
        if wait > 0:
            self.sleep(wait)
        parsed = parse(row["input"])
        targets = self._targets(parsed)
        deadline = start + settle + timedelta(seconds=self.config.analysis_metrics_timeout_s)
        after: list[dict] = []
        while len(after) < 2 and self.now() <= deadline:
            with self._slots:
                fresh = self._sample(targets)
            if fresh:
                after.append({"target": fresh[0]["target"], "observed_at": fresh[0]["observed_at"],
                              "values": {k: v for s in fresh for k, v in s["values"].items()}, "samples": fresh})
                body = {**body, "after": after}
                self._put(row["command_id"], row["incident_id"], body)
            if len(after) < 2:
                self.sleep(self.config.analysis_gap_s)
        if len(after) < 2:
            return self._finish(row, body, {"status": "error", "message": "Metrics not available yet",
                                            "retryable": True})
        model = getattr(self.app, "analysis_model", None)
        if model is None:
            return self._finish(row, body, {"status": "error", "message": "Analysis model not configured",
                                            "retryable": False})
        with self._slots:
            result = self._analyse(row, body, model)
        self._finish(row, body, result)

    def _analyse(self, row: dict, body: dict, model) -> dict:
        record = self._record(row, body)
        samples_after = [s for a in body["after"] for s in a["samples"]]
        bundle, weights, inputs = self._bundle(row["incident_id"])
        started = time.time_ns()
        result = analyse(record, body["before"]["samples"], samples_after, bundle, model,
                         tracing=getattr(self.app, "tracing", None), started_ns=started, finished_ns=None)
        if result.status != "done":
            return {"status": "error", "message": "Analysis could not be completed", "retryable": result.retryable}
        refs = self._append_evidence(row, record, body, result)
        ranking = rank(result.hypotheses, bundle["evidence"] + refs, weights, **inputs)
        if result.evidence:
            self._refresh_hypotheses(row["incident_id"], result.hypotheses, ranking)
        suggestion = ({"id": "sug_" + row["command_id"].removeprefix("cmd_"), **result.suggestion}
                      if result.suggestion else None)
        return {"status": "done", "comment": result.comment, "comment_references": result.comment_references,
                "evidence": result.evidence, "suggestion": suggestion, "retryable": False,
                "ranking": [{"id": r.id, "rank": r.rank, "score": r.score, "counted_for": r.counted_for,
                             "counted_against": r.counted_against} for r in sorted(ranking, key=lambda r: r.rank)]}

    def _finish(self, row: dict, body: dict, result: dict) -> None:
        self._put(row["command_id"], row["incident_id"], {**body, "result": result})

    @staticmethod
    def _record(row: dict, body: dict) -> dict:
        targets = [s["target"] for s in body["before"]["samples"]] or [None]
        return {"command_id": row["command_id"], "incident_id": row["incident_id"], "input": row["input"],
                "class": body["class"], "status": row["status"], "output": row["output"],
                "target": targets[0], "finished_at": _iso(row["finished_at"])}

    # --- hypotheses, evidence, ranking -----------------------------------------------------------------------------
    def _current_hypotheses(self, incident_id: str) -> list[Hypothesis]:
        rows = self.app.store.hypotheses(incident_id)
        if not rows:
            return []
        step = max(r["step"] for r in rows)
        return [Hypothesis(id=r["hypothesis_id"], statement=r["statement"], cause_class=r["cause_class"],
                           target=r["target"], relation=r["relation"], status=r["status"],
                           support=r["support_ids"], against=r["against_ids"]) for r in rows if r["step"] == step]

    def _bundle(self, incident_id: str):
        """What `analyse` and `rank` need: the hypotheses, every evidence ref of the incident, and the same onset
        inputs and weights the investigation ranks with."""
        hypotheses = self._current_hypotheses(incident_id)
        evidence = [self._ref(r) for r in self.app.store.list_evidence(incident_id)]
        runner = getattr(self.app, "runner", None)
        inputs = {}
        try:
            onset_inputs = getattr(runner, "_onset_inputs", None)
            inputs = onset_inputs(hypotheses, evidence) if onset_inputs and hypotheses else {}
        except Exception:
            log.exception("console analysis: onset inputs unavailable")
        bundle = {"hypotheses": hypotheses, "evidence": evidence, "onsets": inputs.get("onsets", {}),
                  "depends_on": inputs.get("depends_on", {})}
        return bundle, getattr(runner, "ranking", None), inputs

    @staticmethod
    def _ref(record: EvidenceRecord) -> EvidenceRef:
        return EvidenceRef(evidence_id=record.evidence_id, sha256=record.sha256, capability=record.capability,
                           status=record.status, model_text=record.model_text, target=record.target, kind=record.kind)

    def _append_evidence(self, row: dict, record: dict, body: dict, result) -> list[EvidenceRef]:
        """The evidence `analyse` cited, through the incident's own evidence path; once per id (a re-check cites the
        same sources again)."""
        sources, _ = _sources(record, body["before"]["samples"], [s for a in body["after"] for s in a["samples"]])
        ids = list(dict.fromkeys(c["evidence_id"] for c in result.evidence))
        have = {r.evidence_id for r in self.app.store.get_evidence(ids)} if ids else set()
        refs = []
        for change in result.evidence:
            evidence_id = change["evidence_id"]
            if evidence_id in {r.evidence_id for r in refs}:
                continue
            source = sources[change["reference"]]
            target = source["target"]
            text = f"Operator console source {change['reference']}: {source['value']}"[:500]
            made = EvidenceRecord(
                evidence_id=evidence_id, incident_id=row["incident_id"], kind=source["kind"],
                capability="operator_console", target=target, host=TargetRef.parse(target).host if target else None,
                executor="operator_console", caller=f"console:{body.get('person', 'unknown')}", source_time=None,
                collected_at=self.now(), status="ok",
                values={"reference": change["reference"], "value": source["value"], "command_id": row["command_id"]},
                model_text=text).with_hash()
            if evidence_id not in have:
                self.app.store.append_evidence(made)
            refs.append(self._ref(made))
        return refs

    def _refresh_hypotheses(self, incident_id: str, hypotheses: list[Hypothesis], ranking) -> None:
        """A new step of the incident's hypotheses with the evidence and the rank `rank()` computed (insert-only).
        The investigation runner may add a step at the same moment (UNIQUE incident, step, hypothesis): read the
        steps again and retry a few times before giving up."""
        ranked = {r.id: r for r in ranking}
        for attempt in range(3):
            with self._hypotheses_lock:
                previous = self.app.store.hypotheses(incident_id)
                step = max((r["step"] for r in previous), default=0) + 1
                chosen = {r["hypothesis_id"] for r in previous if r["step"] == step - 1 and r["chosen"]}
                try:
                    return self.app.store.add_hypotheses(incident_id, step, [
                        {"hypothesis_id": h.id, "statement": h.statement, "cause_class": h.cause_class,
                         "target": h.target, "relation": h.relation, "status": h.status, "support_ids": h.support,
                         "against_ids": h.against, "score": ranked[h.id].score, "rank": ranked[h.id].rank,
                         "chosen": h.id in chosen} for h in hypotheses], self.now())
                except Exception:
                    if attempt == 2:
                        raise
                    log.warning("console analysis: step %s of %s was taken, retrying", step, incident_id)

    # --- what the UI reads -----------------------------------------------------------------------------------------
    def _status(self, body: dict) -> str:
        if body.get("awaiting_action"):
            return "waiting"                     # stored only; the history shows nothing for it
        if body.get("result"):
            return "done" if body["result"]["status"] == "done" else "error"
        return "analyzing" if body.get("after") or body["settle_s"] == 0 else "waiting"

    def view(self, row: dict, body: dict, now: datetime | None = None) -> dict:
        """The `analysis` of a history entry (mockup spec section 5), from what is stored and the clock."""
        now = now or self.now()
        result = body.get("result")
        if result and result["status"] == "done":
            out = {"status": "done", "comment": result["comment"], "evidence": result["evidence"],
                   "ranking": result["ranking"], "retryable": False}
            if result.get("suggestion"):
                out["suggestion"] = result["suggestion"]
            return out
        if result:
            return {"status": "error", "message": result["message"], "reason": result["message"],
                    "retryable": bool(result["retryable"])}
        start = _at(body["clock_start"])
        elapsed = (now - start).total_seconds()
        original = BY_ID[body["command"]].settle_s
        state = analysis_status({"input": row["input"], "command_id": row["command_id"]},
                                elapsed + (original - body["settle_s"]), body["after"])
        out = {k: state[k] for k in ("status", "countdown_s", "message", "retryable")}
        out["settle_until"] = _iso(start + timedelta(seconds=body["settle_s"]))
        if out["status"] == "analyzing" and elapsed - body["settle_s"] > self.config.analysis_stuck_s:
            out["retryable"] = True              # still running long after the metrics settled: ask again
        return out
