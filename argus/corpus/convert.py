"""ACR-0034: source formats to plain text with `#` headings, statically (no renderer, no template, nothing executed).

markdown (Hugo shortcodes dropped), reStructuredText (directives' markers dropped, underlined titles become headings),
roff man pages (`.SH`/`.SS` headings, font escapes dropped), DocBook/SGML/XML (titles become headings, every tag
dropped, entities decoded) and OpenAPI (one section per operation: method, path, summary, description).
"""
from __future__ import annotations

import html
import re

import yaml

_SHORTCODE = re.compile(r"\{\{[<%].*?[%>]\}\}", re.S)
_RST_ROLE = re.compile(r":[\w:-]+:`([^`<]*?)(?:\s*<[^>]*>)?`")
_RST_UNDERLINE = re.compile(r"^([=\-~^\"'`#*+]){3,}\s*$")
_ROFF_ESC = re.compile(r"\\f(\[[^\]]*\]|\(..|.)|\\\*(\[[^\]]*\]|\(..|.)|\\&|\\[|^]")
_XML_COMMENT = re.compile(r"<!--.*?-->", re.S)
_XML_TITLE = re.compile(r"<(title|refname|refpurpose)\b[^>]*>(.*?)</\1\s*>", re.S | re.I)
_XML_BLOCK = re.compile(r"</?(para|section|sect\d|refsect\d|refsection|listitem|varlistentry|programlisting|screen|"
                        r"note|warning|tip|example|table|row|entry|simpara|p|item|list|section_title)\b[^>]*>", re.I)
_XML_TAG = re.compile(r"<[^>\n]+>")
_ROFF_HEAD = {"SH": "## ", "SS": "### "}
_ROFF_FONT = {"B", "I", "BR", "BI", "IB", "RB", "RI", "IR", "SM", "SB"}


def markdown(text: str) -> str:
    return _SHORTCODE.sub("", text)


def rst(text: str) -> str:
    lines, out = text.splitlines(), []
    for i, line in enumerate(lines):
        if _RST_UNDERLINE.match(line):
            if out and out[-1].strip() and not out[-1].startswith("#"):
                out[-1] = "## " + out[-1].strip()
            continue
        if line.startswith(".. ") and "::" not in line:
            continue                                     # comments, labels, substitutions
        out.append(_RST_ROLE.sub(r"\1", line.replace("``", "`")))
    return "\n".join(out)


def roff(text: str) -> str:
    out = []
    for line in text.splitlines():
        if line.startswith(('.\\"', "'\\\"", '.\\\\"')):
            continue
        if line.startswith((".", "'")):
            macro, _, rest = line[1:].partition(" ")
            rest = rest.replace('"', "").strip()
            if macro == "TH":
                out.append("# " + " ".join(rest.split()[:2]))
            elif macro in _ROFF_HEAD:
                out.append(_ROFF_HEAD[macro] + rest.title())
            elif macro in _ROFF_FONT:
                out.append(rest)
            elif macro in ("PP", "P", "LP", "TP", "IP", "sp", "br"):
                out.append("")
            continue
        out.append(line)
    text = "\n".join(out)
    text = _ROFF_ESC.sub("", text).replace("\\-", "-").replace("\\(em", "—").replace("\\e", "\\")
    return text


def docbook(text: str) -> str:
    text = _XML_COMMENT.sub("", text)
    text = _XML_TITLE.sub(lambda m: f"\n\n## {_XML_TAG.sub('', m.group(2)).strip()}\n\n", text)
    text = _XML_BLOCK.sub("\n", text)
    text = _XML_TAG.sub("", text)
    text = html.unescape(text)
    return re.sub(r"\n{3,}", "\n\n", text)


def openapi(text: str) -> str:
    try:
        spec = yaml.safe_load(text) or {}
    except yaml.YAMLError:
        return ""
    title = ((spec.get("info") or {}).get("title") or "API reference") if isinstance(spec, dict) else "API reference"
    out = [f"# {title}"]
    for path, ops in sorted(((spec.get("paths") or {}) if isinstance(spec, dict) else {}).items()):
        if not isinstance(ops, dict):
            continue
        for method, op in ops.items():
            if not isinstance(op, dict):
                continue
            out.append(f"## {method.upper()} {path}")
            for key in ("summary", "description"):
                if op.get(key):
                    out.append(str(op[key]).strip())
            for p in op.get("parameters") or []:
                if isinstance(p, dict) and p.get("name"):
                    out.append(f"- parameter `{p['name']}` ({p.get('in', '?')}): {str(p.get('description', '')).strip()}")
            out.append("")
    return "\n".join(out)


CONVERTERS = {"markdown": markdown, "rst": rst, "roff": roff, "docbook": docbook, "openapi": openapi}


def to_text(fmt: str, text: str) -> str:
    return CONVERTERS[fmt](text)
