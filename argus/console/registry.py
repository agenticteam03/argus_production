"""ACR-0043 (CON-1): the allowlist of console commands. Pure data: a handler is bound to a command id in a later card.

A command has a class (`meta`, `read`, `write`), at most one service argument chosen from the lab services below, and
optional `--since HH:MM`. A write command stands for exactly one released (capability, target) pair; the pair itself is
resolved by the write path, never here.
"""
from __future__ import annotations

from dataclasses import dataclass

META, READ, WRITE = "meta", "read", "write"

# the alias the operator types -> the lab container name (the three scenarios only)
LAB_SERVICES: dict[str, str] = {"cache": "argus-lab-cache", "api": "argus-lab-api", "worker": "argus-lab-jobworker"}

SETTLE_WRITE_S = 45      # two 15 s scrape intervals plus margin (ACR-0043 §3)
SETTLE_READ_S = 0


@dataclass(frozen=True)
class Command:
    id: str                              # e.g. "cache.status"; the key a handler is bound to
    words: tuple[str, ...]               # the verb as typed, e.g. ("cache", "status")
    cls: str                             # meta | read | write
    summary: str                         # one line for `help`
    scenario: str = "all"                # "1", "2", "4" or "all"
    service_arg: bool = False            # takes one service from LAB_SERVICES
    since: bool = False                  # accepts --since HH:MM
    timeout_s: int = 20
    settle_s: int = SETTLE_READ_S

    @property
    def usage(self) -> str:
        text = " ".join(self.words)
        if self.service_arg:
            text += " <service>"
        if self.since:
            text += " [--since HH:MM]"
        return text


def _c(cid, words, cls, summary, **kw) -> Command:
    if cls == WRITE:
        kw.setdefault("settle_s", SETTLE_WRITE_S)
        kw.setdefault("timeout_s", 60)
    return Command(cid, tuple(words.split()), cls, summary, **kw)


COMMANDS: tuple[Command, ...] = (
    _c("help", "help", META, "List the commands"),
    _c("clear", "clear", META, "Clear the screen"),
    _c("history", "history", META, "Show the commands of this incident"),
    _c("status", "status", READ, "State and health of the lab services"),
    _c("map", "map", READ, "Edges of a service with state and change time", service_arg=True),
    # scenario 1: cache failure with a red herring
    _c("cache.status", "cache status", READ, "State, since and health of the cache", scenario="1"),
    _c("api.errors", "api errors", READ, "API error rate and types", scenario="1", since=True),
    _c("api.cpu", "api cpu", READ, "API CPU with its onset", scenario="1", since=True),
    _c("host.metrics", "host metrics", READ, "CPU, memory, disk and load of the host", scenario="1"),
    _c("cache.restart", "cache restart", WRITE, "Bring the cache back (start, only while it is stopped)", scenario="1"),
    # scenario 4: frozen worker
    _c("worker.status", "worker status", READ, "State and health of the job worker", scenario="4"),
    _c("worker.heartbeat", "worker heartbeat", READ, "Time since the worker last processed a job", scenario="4"),
    _c("worker.throughput", "worker throughput", READ, "Jobs per minute", scenario="4"),
    _c("queue.depth", "queue depth", READ, "Queue depth and trend", scenario="4"),
    _c("worker.restart", "worker restart", WRITE, "Restart the job worker", scenario="4"),
    # scenario 2: wrong network
    _c("net.inspect", "net inspect", READ, "Networks a service is attached to", scenario="2", service_arg=True),
    _c("net.expected", "net expected", READ, "Networks a service should be on", scenario="2", service_arg=True),
    _c("net.diff", "net diff", READ, "Expected against actual networks", scenario="2", service_arg=True),
    _c("net.reconnect", "net reconnect api", WRITE, "Reconnect the API to its expected network", scenario="2"),
)

BY_ID: dict[str, Command] = {c.id: c for c in COMMANDS}
assert len(BY_ID) == len(COMMANDS), "duplicate command id"


def catalog() -> list[dict]:
    """The list `GET /api/v1/console/commands` returns and `help` prints."""
    return [{"id": c.id, "usage": c.usage, "class": c.cls, "scenario": c.scenario, "summary": c.summary}
            for c in COMMANDS]


def help_lines() -> list[str]:
    width = max(len(c.usage) for c in COMMANDS)
    return ["Available commands:"] + [
        f"  {c.usage.ljust(width)}  {c.summary}" + ("  (needs approval)" if c.cls == WRITE else "") for c in COMMANDS]
