"""One Redactor for every model-bound, stored and view-bound text (v1.8 §10.8)."""
from __future__ import annotations

import re
from typing import Any, Iterable

_SECRET_NAME = r"[\w.-]*(?:password|passwd|pwd|secret|token|api[_-]?key|apikey|access[_-]?key)[\w.-]*"
_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S), "[REDACTED PRIVATE KEY]"),
    # a named secret (`password=...`) after `Bearer`, on this line or the next, is no token: the next rule masks its value
    # (without the look-ahead `Bearer\npassword=x` became `Bearer [REDACTED]x`). `\s+` stays: a short token on the next
    # line is masked too, at the cost of over-masking a log line after the word (#278 review)
    (re.compile(r"(?i)\bbearer\s+(?!" + _SECRET_NAME + r"\s*[=:]\s*[^\s=])[A-Za-z0-9._~+/-]{8,}=*", re.ASCII),
     "Bearer [REDACTED]"),
    (re.compile(r"(?i)\b(" + _SECRET_NAME + r")\s*[=:]\s*(\"[^\"]*\"|'[^']*'|\S+)"), r"\1=[REDACTED]"),
    (re.compile(r"(?i)\b(postgres(?:ql)?|mysql|redis|mongodb|amqp)://[^\s:@/]+:[^\s@/]+@"), r"\1://[REDACTED]@"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{16,}", re.ASCII), "[REDACTED KEY]"),
]
# re.ASCII (OP-014 step 10): with Unicode `\b` a non-ASCII letter glued to a token ("é<token>") is a word character, so
# no boundary was found and the token was not masked
_HIGH_ENTROPY = re.compile(r"\b[A-Za-z0-9+/_=-]{40,}\b", re.ASCII)
_PATH_CHARS = re.compile(r"[A-Za-z0-9._/-]*")
# #110 review: a declared path counts only where a path starts (not inside a URL or another path), and under a declared
# directory a segment that holds a token is not kept (the high-entropy rule masks it)
_IN_PATH = re.compile(r"[A-Za-z0-9._/:~%-]")
_TOKEN = re.compile(r"[A-Za-z0-9+_=-]{40,}")
_SECRET_KEYS = re.compile(r"(?i)(password|secret|token|api[_-]?key|private[_-]?key|^env$)")
# X-5: Docker's full container ID (64 lower-case hex) under the target service's own `container_id` key is the identity
# the action gateway compares before a write; masked, every approved action would fail as "identity changed". Only that
# key and exactly that shape are kept: the same 64 hex in any text or under any other key is still masked.
_IDENTITY_KEYS = frozenset({"container_id"})
_DOCKER_ID = re.compile(r"[0-9a-f]{64}", re.ASCII)


class Redactor:
    """`declared`: the paths Argus itself declared (the inspection policy's `service_config` and `files`, the
    inventory's mounts; `wiring.declared_paths`). The high-entropy rule leaves those readable: a file exactly, a
    directory (an entry ending in `/`; mounts are given that way) with what lies under it; `/` declares nothing. Any
    other path is masked like any other long token: a lower-case secret can sit in a URL path (#107 review)."""

    def __init__(self, declared: Iterable[str] = ()):
        paths = {p for p in declared if isinstance(p, str) and p.startswith("/") and p.rstrip("/")}
        self._files = sorted((p for p in paths if not p.endswith("/")), key=len, reverse=True)
        self._dirs = sorted((p for p in paths if p.endswith("/")), key=len, reverse=True)

    def _kept(self, value: str) -> list[tuple[int, int]]:
        """The spans of `value` that are a declared file, or a path under a declared directory."""
        spans = []

        def at_start(i: int) -> bool:
            return i == 0 or not _IN_PATH.match(value[i - 1])
        for d in self._dirs:
            start = value.find(d)
            while start >= 0:
                if at_start(start):
                    end = start + len(d)
                    for seg in value[end:_PATH_CHARS.match(value, end).end()].split("/"):
                        if _TOKEN.search(seg):
                            break
                        end += len(seg) + 1
                    spans.append((start, min(end, _PATH_CHARS.match(value, start + len(d)).end())))
                start = value.find(d, start + 1)
        for f in self._files:
            start = value.find(f)
            while start >= 0:
                end = start + len(f)
                if at_start(start) and (end == len(value) or not re.match(r"[A-Za-z0-9_/-]", value[end])):
                    spans.append((start, end))                                  # not inside a path, not a longer name
                start = value.find(f, start + 1)
        merged: list[tuple[int, int]] = []
        for a, b in sorted(spans):
            if merged and a <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(b, merged[-1][1]))
            else:
                merged.append((a, b))
        return merged

    def text(self, value: str) -> tuple[str, int]:
        count = 0
        for pattern, repl in _PATTERNS:
            value, n = pattern.subn(repl, value)
            count += n
        # declared paths are set aside (a short private-use marker the high-entropy rule cannot match), then put back
        if self._files or self._dirs:
            value = value.replace("", "�").replace("", "�")   # never a marker from the input
        kept = self._kept(value) if self._files or self._dirs else []
        parts = [value[a:b] for a, b in kept]
        for i, (a, b) in reversed(list(enumerate(kept))):
            value = f"{value[:a]}{i}{value[b:]}"
        masked = 0

        def mask(m: re.Match) -> str:
            nonlocal masked
            masked += 1
            return "[REDACTED HIGH-ENTROPY]"
        value = _HIGH_ENTROPY.sub(mask, value)
        value = re.sub("(\\d+)", lambda m: parts[int(m.group(1))], value)
        return value, count + masked

    def value(self, obj: Any) -> tuple[Any, int]:
        if isinstance(obj, str):
            return self.text(obj)
        if isinstance(obj, dict):
            out, total = {}, 0
            for k, v in obj.items():
                if k in _IDENTITY_KEYS and isinstance(v, str) and _DOCKER_ID.fullmatch(v):
                    out[k] = v
                    continue
                if isinstance(k, str) and _SECRET_KEYS.search(k):
                    out[k] = "[REDACTED]"
                    total += 1
                    continue
                out[k], n = self.value(v)
                total += n
            return out, total
        if isinstance(obj, list):
            out_l, total = [], 0
            for v in obj:
                r, n = self.value(v)
                out_l.append(r)
                total += n
            return out_l, total
        return obj, 0
