"""Statically check current-step code.bash blocks; never execute their commands.

This deliberately small lexer covers the supplied PowerShell/bash block conventions.
It is a format/trap checker, not a shell interpreter or an authorization mechanism.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path


LABEL = re.compile(r"(?P<label>(?:[A-Za-z][\w-]*\.\d+|\d+\.\d+)[\w.-]*)(?=\s|$)")
LOCATION = re.compile(r"\[(LAPTOP · PowerShell|VM vm-(?:095|166) · bash)\]")
RULE = re.compile(r"\s*#\s*-{3,}\s*")
IPV4 = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])")
SECRET_ASSIGN = re.compile(
    r"(?:^|[\s;])(?:\$(?:env:)?)?[\w]*(?:password|passwd|token|api_?key|secret)\s*[:=]",
    re.I | re.M,
)
TOKEN_VALUE = re.compile(
    r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}"
    r"|sk-(?:proj-)?[A-Za-z0-9_-]{20,}|AKIA[A-Z0-9]{16})\b"
)
COLON = re.compile(r"(?<!`)\$(?:\{[A-Za-z_]\w*\}:|[A-Za-z_]\w*:(?=\S))")
COUNT_IF = re.compile(r"\bif\s*\(\s*\$ok\s+-eq\s+(\d+)\s*\)", re.I)
PASS = re.compile(r"VERDICT:\s+(\S+)\s+PASS\s+\((\d+) of (\d+)\)")
FAIL = re.compile(r"VERDICT:\s+(\S+)\s+FAIL\s+\(\$ok of (\d+)\)")


@dataclass(frozen=True)
class Token:
    raw: str
    start: int
    end: int
    kind: str = "word"

    @property
    def value(self) -> str:
        if self.kind in ("single", "double"):
            return self.raw[1:-1]
        return self.raw


def lex(text: str, shell: str) -> list[Token]:
    """Keep quoted arguments intact and discard comments for structural checks."""
    tokens: list[Token] = []
    i = 0
    escape = "`" if shell == "powershell" else "\\"
    punctuation = "{}();|=&<>"
    while i < len(text):
        start = i
        char = text[i]
        if char in " \t\r":
            i += 1
            continue
        if char == "#":
            end = text.find("\n", i)
            i = len(text) if end == -1 else end
            continue
        if char == escape and text[i + 1:i + 2] == "\n":
            i += 2
            continue
        if text[i:i + 2] in ("@'", '@"'):
            marker = text[i:i + 2]
            end = re.search(r"(?m)^\s*" + re.escape(marker[1] + "@") + r"\s*$", text[i + 2:])
            i = i + 2 + end.end() if end else len(text)
            tokens.append(Token(text[start:i], start, i, "heredoc"))
            continue
        if char in "'\"":
            quote = char
            i += 1
            while i < len(text):
                if text[i] == escape and (quote == '"' or shell == "bash"):
                    i += 2
                elif text[i] == quote:
                    if shell == "powershell" and text[i + 1:i + 2] == quote:
                        i += 2
                    else:
                        i += 1
                        break
                else:
                    i += 1
            i = min(i, len(text))
            tokens.append(Token(text[start:i], start, i, "single" if quote == "'" else "double"))
            continue
        if char == "\n" or char in punctuation:
            i += 1
            if text[start:i + 1] in ("<<", ">>", "||", "&&"):
                i += 1
            tokens.append(Token(text[start:i], start, i, "symbol"))
            continue
        while i < len(text) and not text[i].isspace() and text[i] not in punctuation + "'\"#":
            if text[i] == escape and text[i + 1:i + 2] == "\n":
                break
            i += 1
        if i == start:  # A literal escape before a continuation is handled on the next iteration.
            i += 1
        tokens.append(Token(text[start:i], start, i))
    return tokens


def source_view(text: str, tokens: list[Token], *, mask_strings: bool = False) -> str:
    chars = ["\n" if char == "\n" else " " for char in text]
    for token in tokens:
        if not mask_strings or token.kind not in ("single", "double", "heredoc"):
            chars[token.start:token.end] = token.raw
    return "".join(chars)


def statements(tokens: list[Token]) -> list[list[Token]]:
    result: list[list[Token]] = []
    current: list[Token] = []
    for token in tokens:
        if token.kind == "symbol" and token.raw in ("\n", ";", "|", "||", "&&", "{", "}"):
            if current:
                result.append(current)
                current = []
        else:
            current.append(token)
    if current:
        result.append(current)
    return result


def command_index(tokens: list[Token]) -> int:
    index = 0
    if len(tokens) > 2 and tokens[0].raw.startswith("$") and tokens[1].raw == "=":
        index = 2
    if index < len(tokens) and tokens[index].raw == "&":
        index += 1
    return index


def native_name(value: str) -> bool:
    leaf = value.replace("\\", "/").rsplit("/", 1)[-1].lower()
    return bool(re.fullmatch(r"(?:gh|git|docker|python(?:\d+(?:\.\d+)?)?)(?:\.exe)?", leaf))


def check_laptop(text: str, tokens: list[Token], label: str) -> list[str]:
    problems: list[str] = []
    chunks = statements(tokens)
    commands = [chunk[command_index(chunk):] for chunk in chunks]
    if not any(command and command[0].value.lower() == "set-location" for command in commands):
        problems.append("missing Set-Location")
    if not any([token.value for token in command[:3]] == ["git", "rev-parse", "--show-toplevel"]
               for command in commands):
        problems.append("missing git rev-parse --show-toplevel")
    masked = source_view(text, tokens, mask_strings=True)
    if not re.search(r"\$ok\s*=\s*0\b", masked, re.I):
        problems.append("missing $ok = 0")
    executable = source_view(text, tokens)
    conditions = list(COUNT_IF.finditer(masked))
    tail = executable[conditions[-1].start():] if conditions else ""
    passed, failed = PASS.search(tail), FAIL.search(tail)
    if not passed or not failed or not re.fullmatch(r"[\s\"'}]*", tail[failed.end():]):
        problems.append("missing final PASS/FAIL verdict")
    else:
        if label != "UNLABELLED" and (passed[1] != label or failed[1] != label):
            problems.append("verdict label does not match block label")
        counts = [int(passed[2]), int(passed[3]), int(failed[2]), int(conditions[-1][1])]
        if len(set(counts)) != 1 or counts[0] < 1:
            problems.append("verdict counts do not match")
    for command in commands:
        if command and native_name(command[0].value) and any('"' in arg.raw for arg in command[1:]):
            problems.append("double quotes inside native command arguments")
    depth = 0
    for token in tokens:
        if token.kind == "double" and COLON.search(token.raw):
            problems.append("unsafe variable-colon interpolation")
        if token.kind == "word" and token.raw.lower() in ("else", "elseif") and depth == 0:
            line_start = text.rfind("\n", 0, token.start) + 1
            if not text[line_start:token.start].strip():
                problems.append("top-level else/elseif must follow } on the same line")
        if token.kind == "symbol" and token.raw in ("{", "}"):
            depth += 1 if token.raw == "{" else -1
    return problems


READ_COMMANDS = {
    "cat", "grep", "egrep", "fgrep", "head", "tail", "ls", "pwd", "printf", "echo", "true", "false", ":",
    "test", "[", "stat", "wc", "cut", "date", "id", "whoami", "uname", "df", "du",
    "readlink", "sha256sum", "ps", "ss", "getent", "set", "cd",
}


def vm_command(chunk: list[Token]) -> list[Token]:
    if chunk and chunk[0].value == "sudo":
        chunk = chunk[1:]
        while chunk and chunk[0].value.startswith("-"):
            chunk = chunk[1:]
    return chunk


def mutates_vm(command: list[Token]) -> bool:
    """Unknown commands need the guard too; known reads remain useful without it."""
    if not command:
        return False
    values = [token.value for token in command]
    for index, token in enumerate(command):
        # Expansion can execute another command even when the outer command only reads.
        if token.kind != "single" and ("`" in token.raw or "$(" in token.raw):
            return True
        if token.raw == "$" and index + 1 < len(command) and command[index + 1].raw == "(":
            return True
    for index, token in enumerate(command[:-1]):
        if token.kind == "symbol" and token.raw in (">", ">>"):
            target = values[index + 1]
            duplicate_fd = target == "&" and index + 2 < len(values) and values[index + 2] in ("1", "2")
            if target != "/dev/null" and not duplicate_fd:
                return True
    name, args = values[0], values[1:]
    if name == "docker":
        if not args:
            return False
        return args[0] not in {"ps", "logs", "inspect", "images", "stats", "version", "info", "top"}
    if name == "systemctl":
        return not args or args[0] not in {"status", "show", "is-active", "is-enabled", "list-units"}
    if name == "git":
        return not args or args[0] not in {"status", "log", "show", "diff", "rev-parse"}
    return name not in READ_COMMANDS


def check_vm(tokens: list[Token]) -> list[str]:
    problems: list[str] = []
    depth = 0
    pending_guard: int | None = None
    guard: int | None = None
    for chunk in statements(tokens):
        word = chunk[0].value
        if word == "if":
            depth += 1
            chunk = chunk[1:]
            values = [token.value for token in chunk]
            if (values and values[0] == "grep" and "/opt/argus-v18/SESSION" in values
                    and any(value.startswith("holder=") for value in values)
                    and any(value == "--quiet" or (value.startswith("-") and "q" in value) for value in values)):
                pending_guard = depth
        elif word == "then":
            if pending_guard == depth:
                guard = pending_guard
                pending_guard = None
            chunk = chunk[1:]
        elif word in ("else", "elif"):
            if guard is not None and depth <= guard:
                guard = None
            pending_guard = None
            chunk = chunk[1:]
        elif word == "fi":
            if guard is not None and depth <= guard:
                guard = None
            depth -= 1
            chunk = chunk[1:]
        command = vm_command(chunk)
        if not command:
            continue
        name = command[0].value
        if name == "exit":
            problems.append("exit is not allowed in a VM block")
        elif name == "reboot" or (name == "systemctl" and any(token.value == "reboot" for token in command[1:])):
            problems.append("reboot is not allowed in a VM block")
        elif mutates_vm(command) and guard is None:
            problems.append("mutation requires a preceding SESSION check on its successful branch")
    return problems


def header(line: str) -> tuple[str, str | None] | None:
    if not line.lstrip().startswith("#"):
        return None
    content = re.sub(r"^\s*#\s*(?:-+\s*)?", "", line)
    match = LABEL.match(content)
    if not match and not content.startswith(("[LAPTOP", "[VM")):
        return None
    location = LOCATION.search(content)
    return match["label"] if match else "UNLABELLED", location[1] if location else None


def check(text: str) -> list[str]:
    """Return one sanitized, labelled diagnostic per problem."""
    lines = text.splitlines(keepends=True)
    headers = []
    for index, line in enumerate(lines):
        preceded_by_rule = index > 0 and RULE.fullmatch(lines[index - 1])
        # CODE_BASH.md also permits '# --- 4.1 [VM ...]' on one line.
        inline_rule = re.match(r"\s*#\s*-{3,}\s+\S", line)
        if (preceded_by_rule or inline_rule) and (parsed := header(line)):
            headers.append((index, parsed))
    if not headers:
        return ["UNLABELLED: missing labelled block header"]
    problems: list[str] = []
    if any(token.raw != "\n" for token in lex("".join(lines[:headers[0][0]]), "powershell")):
        problems.append("UNLABELLED: commands before first block header")
    seen: set[str] = set()
    for number, (start, (label, location)) in enumerate(headers):
        end = headers[number + 1][0] if number + 1 < len(headers) else len(lines)
        block = "".join(lines[start:end])
        issues: list[str] = []
        if label == "UNLABELLED":
            issues.append("missing block label")
        elif label in seen:
            issues.append("duplicate block label")
        seen.add(label)
        if location is None:
            issues.append("missing or invalid location tag")
        if not re.search(r"(?mi)^\s*#\s*Expected:", block):
            issues.append("missing Expected: line")
        if any(all(int(part) <= 255 for part in match[0].split(".")) for match in IPV4.finditer(block)):
            issues.append("IPv4 address is not allowed")
        if SECRET_ASSIGN.search(block) or TOKEN_VALUE.search(block):
            issues.append("secret/token/password assignment is not allowed")
        shell = "bash" if location and location.startswith("VM") else "powershell"
        tokens = lex(block, shell)
        if any(token.kind == "heredoc" or (token.kind == "symbol" and token.raw == "<<") for token in tokens):
            issues.append("here-string/heredoc is not allowed")
        if location == "LAPTOP · PowerShell":
            issues.extend(check_laptop(block, tokens, label))
        elif location and location.startswith("VM"):
            issues.extend(check_vm(tokens))
        problems.extend(f"{label}: {issue}" for issue in issues)
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    args = parser.parse_args(argv)
    try:
        text = args.path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError):
        print("UNLABELLED: cannot read input as UTF-8")
        return 1
    problems = check(text)
    for problem in problems:
        print(problem)
    return int(bool(problems))


if __name__ == "__main__":
    raise SystemExit(main())
