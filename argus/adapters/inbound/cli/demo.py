"""`argus demo`: a paced replay of a recorded run, for presenting the agent live while someone narrates.

The events are the REAL run events of a recorded investigation, drawn by the same `Formatter` as `argus diagnose`,
only slowed down so the whole story (failure → investigation → diagnosis) fills `--duration` seconds. It stops at the
human-approval gate: the nodes after `record` (propose_action … verify) are not implemented yet, so the closing panel
is labelled as a preview and lists them as pending. Nothing here talks to the API, a model or a host.
"""
from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path
from typing import Callable

from argus.adapters.inbound.cli.render import Formatter

DEFAULT_EVENTS = Path("contracts/samples/events.json")      # a real OOM restart-loop run, relative to the repo root
LINE_PAUSE_S = 0.2                                          # between the lines of one block, so it reads as it appears
PENDING_NODES = ("propose_action", "request_approval", "await_approval", "precheck_action", "execute_write", "verify")

# Relative pause BEFORE a block (the audience reads / the narrator talks). The "decides" blocks are where the agent
# thinks, so they get the longest pause and a spinner.
_WEIGHT = {("detect", "enter"): 5, ("detect", "exit"): 14, ("recall", "exit"): 10, ("investigate", "exit"): 16,
           ("act", "step"): 12, ("evidence_pack", "step"): 12, ("record", "exit"): 18}
_THINKS = {("investigate", "exit")}
_SPIN = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


def load_events(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def _failure_banner(fmt: Formatter, events: list[dict]) -> list[str]:
    first = next((e for e in events if e["node"] == "detect" and e["phase"] == "enter"), None)
    if first is None:
        return []
    d = first["data"]
    symptom = next((e["data"].get("result") for e in events if e["node"] == "act" and e["phase"] == "step"
                    and e["data"].get("executor") == "docker_read"), "")
    out = fmt.box("FAILURE DETECTED", f"{d.get('target')}  ·  trigger {d.get('trigger')}", "r")
    if symptom:
        out.append(fmt._k("r", "  what the platform reports: ") + symptom)
    return out


def _proposal(fmt: Formatter, events: list[dict]) -> list[list[str]]:
    rec = next((e["data"] for e in events if e["node"] == "record" and e["phase"] == "exit"), {})
    target = rec.get("root_cause_target") or "?"
    k = fmt._k
    approval = ["", k("b", "▌ PROPOSED ACTION") + k("d", "  (preview of the next phase, not agent output yet)"),
                *fmt.box("proposal · preview", f"Bounded restart of {target} (runbook RB-001, step 7). Never enlarge the "
                         "memory limit just to test a guess. Rechecked right before dispatch: target identity, host "
                         "capacity, dependencies, incident still open, explicit human approval.", "y")]
    gate = [*fmt.box("AWAITING HUMAN APPROVAL", "Human-in-the-loop is not implemented yet. Today Argus is read-only: "
                     "it diagnoses and a person decides; the write gate stays empty. The agent will propose the action "
                     "and wait here for an explicit approval.", "m"),
            k("d", "  next in implementation: ") + k("d", " → ".join(PENDING_NODES)),
            k("d", "  " + "  ".join(f"○ {n}" for n in PENDING_NODES))]
    return [approval, gate]


def _steps(fmt: Formatter, events: list[dict]) -> list[tuple[float, list[str], bool]]:
    """(weight, lines, thinks) per block, in the order shown."""
    steps = [(6.0, _failure_banner(fmt, events), False)]
    for ev in events:
        lines = fmt.event(ev)
        if lines:
            key = (ev["node"], ev["phase"])
            steps.append((float(_WEIGHT.get(key, 8)), lines, key in _THINKS))
    for lines in _proposal(fmt, events):
        steps.append((12.0, lines, False))
    return [s for s in steps if s[1]]


def play(events: list[dict], *, duration_s: float = 180.0, color: bool = True, width: int | None = None,
         sleep: Callable[[float], None] = time.sleep, write: Callable[[str], None] = print,
         spinner: bool = False) -> None:
    """Show `events` so the pauses add up to `duration_s` (line-by-line reveal included)."""
    fmt = Formatter(color=color, width=width)
    steps = _steps(fmt, events)
    line_pause = min(LINE_PAUSE_S, duration_s / (4 * max(1, sum(len(s[1]) for s in steps))))
    budget = max(0.0, duration_s - line_pause * sum(len(s[1]) for s in steps))
    total_w = sum(s[0] for s in steps)
    for weight, lines, thinks in steps:
        pause = budget * weight / total_w
        if thinks and spinner:
            ticks = max(1, int(pause / 0.1))
            for i in range(ticks):
                sys.stdout.write(f"\r  {fmt._k('m', _SPIN[i % len(_SPIN)])} {fmt._k('d', 'the agent is deciding…')}")
                sys.stdout.flush()
                sleep(pause / ticks)
            sys.stdout.write("\r" + " " * 40 + "\r")
        else:
            sleep(pause)
        for ln in lines:
            write(ln)
            sleep(line_pause)


def run(args) -> int:
    path = Path(args.events)
    if not path.is_file():
        print(f"recorded events not found: {path} (run from the repository root or pass --events)", file=sys.stderr)
        return 1
    color = sys.stdout.isatty() and not args.no_color
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if color and sys.platform == "win32":
        import os
        os.system("")                                       # turns on ANSI escape handling in the Windows console
    try:
        play(load_events(path), duration_s=args.duration, color=color,
             width=min(shutil.get_terminal_size((100, 30)).columns, 110),
             write=lambda s: print(s, flush=True), spinner=color)
    except KeyboardInterrupt:
        print()
        return 130
    return 0


def main(argv: list[str] | None = None) -> int:
    """`python3 -m argus.adapters.inbound.cli.demo`: stdlib only, so it runs on a VM without the Argus dependencies."""
    import argparse
    p = argparse.ArgumentParser(prog="argus-demo")
    p.add_argument("--duration", type=float, default=180.0, help="total seconds (default 180)")
    p.add_argument("--events", default=str(DEFAULT_EVENTS), help="recorded run events (JSON list)")
    p.add_argument("--no-color", action="store_true")
    return run(p.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
