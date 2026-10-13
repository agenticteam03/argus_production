## 2026-10-12 — REDACT-declared-boundary: a declared path counts only where a path starts (review of #110)

Type: fix
Who: conantkd (+ agent)
Context: the non-blocking finding of the #110 review. A declared directory was matched anywhere in the text and kept
everything under it, so these stayed unmasked: `https://hooks.example.com/srv/argus-lab-fill/<40-char token>` (the
declared directory inside a URL), `/evil/srv/argus-lab-fill/<token>` (after another path) and
`/srv/argus-lab-fill/<token>` (a token as a name under the declared directory).
Decision / result: in `Redactor._kept`:
- a declared file or directory counts only where a path starts: the character before it is not a path or URL
  character (`[A-Za-z0-9._/:~%-]`); `path=`, a quote, a bracket or a space before it are fine;
- under a declared directory the kept span stops before the first segment that holds a token (40+ token characters):
  the high-entropy rule masks that segment, the declared prefix stays readable.
Consequences: stricter only; every declared path written at a path start reads as before. Touches redaction (a safety
principle): needs a teammate's approval.
References: `argus/capabilities/redaction.py`, `tests/test_redaction_paths.py`.

### Test state

`tests/test_redaction_paths.py`: 8 tests added (red seen: the URL and the other-path cases unmasked, and a token under
the declared directory kept); 5 declared paths at a path start still readable.

### Next step

Open the PR when a reviewer is available.
