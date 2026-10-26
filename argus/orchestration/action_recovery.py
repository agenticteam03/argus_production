"""Bounded, recording-only Phase 18 outbox and approval-resume worker."""
from __future__ import annotations

from datetime import datetime, timezone


class OfflineActionRecovery:
    def __init__(self, rows, runner, *, clock=lambda: datetime.now(timezone.utc)):
        self.rows, self.runner, self.clock = rows, runner, clock

    def run_once(self, limit: int = 20) -> dict[str, int]:
        count = {"notified": 0, "resumed": 0, "pending": 0, "failed": 0}
        for item in self.rows.pending_action_notifications(self.clock(), limit):
            if item["channel"] != "recording":
                self.rows.mark_action_notification(item["key"], at=self.clock(), delivered=False,
                                                   result="unknown channel refused")
                count["failed"] += 1
                continue
            try:
                self.rows.notify(item["key"], item["payload"])
            except Exception as exc:
                self.rows.mark_action_notification(item["key"], at=self.clock(), delivered=False,
                                                   result=f"{type(exc).__name__}: {str(exc)[:100]}")
                count["failed"] += 1
            else:
                self.rows.mark_action_notification(item["key"], at=self.clock(), delivered=True,
                                                   result="recorded locally")
                count["notified"] += 1
        for intent in self.rows.pending_resume_intents(limit):
            try:
                incident = self.runner.run(intent["incident_id"])
            except Exception as exc:
                terminal = intent["attempts"] >= 2
                self.rows.mark_resume_intent(intent["approval_id"], "failed" if terminal else "pending",
                                             f"{type(exc).__name__}: {str(exc)[:100]}")
                count["failed"] += 1
                continue
            if incident.outcome is None:
                self.rows.mark_resume_intent(intent["approval_id"], "pending", "still awaiting graph checkpoint")
                count["pending"] += 1
            else:
                self.rows.mark_resume_intent(intent["approval_id"], "done", str(incident.outcome))
                count["resumed"] += 1
        return count
