"""One Redactor for every model-bound, stored and view-bound text (v1.8 §10.8)."""
from __future__ import annotations

import re
from typing import Any

_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S), "[REDACTED PRIVATE KEY]"),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]{8,}=*"), "Bearer [REDACTED]"),
    (re.compile(r"(?i)\b([\w.-]*(?:password|passwd|pwd|secret|token|api[_-]?key|apikey|access[_-]?key)[\w.-]*)\s*[=:]\s*(\"[^\"]*\"|'[^']*'|\S+)"),
     r"\1=[REDACTED]"),
    (re.compile(r"(?i)\b(postgres(?:ql)?|mysql|redis|mongodb|amqp)://[^\s:@/]+:[^\s@/]+@"), r"\1://[REDACTED]@"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"), "[REDACTED KEY]"),
]
_HIGH_ENTROPY = re.compile(r"\b[A-Za-z0-9+/_=-]{40,}\b")
# a file path, not a token: lower-case segments of at most 32 characters, no + or = (T-0019 3b: a config path was masked)
_PATH_LIKE = re.compile(r"(?:[a-z_]{1,32}=)?/?[a-z0-9._-]{1,32}(?:/[a-z0-9._-]{1,32})+/?")   # also `path=/a/b`
_SECRET_KEYS = re.compile(r"(?i)(password|secret|token|api[_-]?key|private[_-]?key|^env$)")


class Redactor:
    def text(self, value: str) -> tuple[str, int]:
        count = 0
        for pattern, repl in _PATTERNS:
            value, n = pattern.subn(repl, value)
            count += n
        masked = 0

        def mask(m: re.Match) -> str:
            nonlocal masked
            if _PATH_LIKE.fullmatch(m.group(0)):
                return m.group(0)
            masked += 1
            return "[REDACTED HIGH-ENTROPY]"
        value = _HIGH_ENTROPY.sub(mask, value)
        return value, count + masked

    def value(self, obj: Any) -> tuple[Any, int]:
        if isinstance(obj, str):
            return self.text(obj)
        if isinstance(obj, dict):
            out, total = {}, 0
            for k, v in obj.items():
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
