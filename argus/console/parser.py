"""ACR-0043 (CON-1): the console parser. Rejects shell syntax, unknown verbs and unknown services before anything runs.

`parse(text)` returns a `ParsedCommand` or raises `ConsoleRefused` with a terminal-style message. It never runs anything and
never touches the network; a handler and the write gate come later.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from argus.console.registry import COMMANDS, LAB_SERVICES, Command

MAX_INPUT = 200
SHELL_SYNTAX = re.compile(r"[;&|<>$`(){}\[\]\\\"'*?!~#\n\r\t\x00]|\.\.|/")
SINCE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
SHOWN = {"\n": "newline", "\r": "newline", "\t": "tab", "\x00": "NUL"}


class ConsoleRefused(ValueError):
    """The input is not an allowed command; the message is what the terminal prints."""


@dataclass(frozen=True)
class ParsedCommand:
    command: Command
    args: dict = field(default_factory=dict)      # {"service": "api", "since": "10:30"}
    text: str = ""                                 # the normalised input

    @property
    def id(self) -> str:
        return self.command.id

    @property
    def cls(self) -> str:
        return self.command.cls


def parse(text: str) -> ParsedCommand:
    if not isinstance(text, str) or not text.strip():
        raise ConsoleRefused("Type 'help' to see available commands.")
    if len(text) > MAX_INPUT:
        raise ConsoleRefused(f"input too long (at most {MAX_INPUT} characters)")
    bad = SHELL_SYNTAX.search(text)
    if bad:
        found = bad.group(0)
        raise ConsoleRefused(f"syntax not allowed: {SHOWN.get(found, found)}. Only plain console commands are accepted; "
                             "type 'help'.")
    tokens = text.lower().split()
    command, rest = _match(tokens)
    return ParsedCommand(command, _arguments(command, rest), " ".join(tokens))


def _match(tokens: list[str]) -> tuple[Command, list[str]]:
    best: Command | None = None
    for c in COMMANDS:
        if tuple(tokens[:len(c.words)]) == c.words and (best is None or len(c.words) > len(best.words)):
            best = c
    if best is not None:
        return best, tokens[len(best.words):]
    first = tokens[0]
    subs = [c.words[1] for c in COMMANDS if c.words[0] == first and len(c.words) > 1]
    if subs:
        raise ConsoleRefused(f"unknown subcommand for {first}. Try: {', '.join(subs)}.")
    raise ConsoleRefused(f"command not found: {first}. Type 'help' to see available commands.")


def _arguments(command: Command, rest: list[str]) -> dict:
    args: dict = {}
    if command.since and "--since" in rest:
        i = rest.index("--since")
        value = rest[i + 1] if i + 1 < len(rest) else ""
        if not SINCE.fullmatch(value):
            raise ConsoleRefused("--since needs a time as HH:MM, for example --since 10:30")
        args["since"] = value
        del rest[i:i + 2]
    if command.service_arg:
        if len(rest) != 1:
            raise ConsoleRefused(f"usage: {command.usage}")
        service = rest.pop()
        if service not in LAB_SERVICES:
            raise ConsoleRefused(f"unknown service: {service}. Known services: {', '.join(sorted(LAB_SERVICES))}.")
        args["service"] = service
    if rest:
        raise ConsoleRefused(f"unexpected argument: {rest[0]}. usage: {command.usage}")
    return args
