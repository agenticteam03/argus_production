"""ACR-0034 layer 2 (sanitising): what a person reading the page would not see never reaches a passage.

Removed: HTML comments, elements hidden by `hidden`/`display:none`/`visibility:hidden`, images and data URIs, YAML
front matter (its `title` is kept as a heading), invisible Unicode (format characters such as zero-width and bidi
controls, soft hyphens) and control characters. Links keep their text and URL. Other HTML tags lose their markup
and keep their text; angle-bracket placeholders of the docs (`<container>`) are not tags and stay.
"""
from __future__ import annotations

import re
import unicodedata

import yaml

_COMMENT = re.compile(r"<!--.*?(-->|$)", re.S)
_HIDDEN = re.compile(r"<(\w+)\b[^>]*\b(?:hidden\b|style\s*=\s*[\"'][^\"']*(?:display\s*:\s*none|visibility\s*:\s*hidden)"
                     r"[^\"']*[\"'])[^>]*>.*?</\1\s*>", re.S | re.I)
_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_DATA_URI = re.compile(r"data:[\w/+.-]+;base64,[A-Za-z0-9+/=]+", re.I)
_LINK = re.compile(r"(?<!!)\[([^\]\n]+)\]\((https?://[^)\s]+)\)")
_REL_LINK = re.compile(r"(?<!!)\[([^\]\n]+)\]\(([^)\s]*)\)")
_HTML_TAGS = ("a|abbr|b|blockquote|br|code|dd|del|details|div|dl|dt|em|figure|figcaption|font|h[1-6]|hr|i|img|ins|kbd|"
              "li|mark|ol|p|pre|q|s|samp|small|span|strong|sub|summary|sup|table|tbody|td|tfoot|th|thead|tr|tt|u|ul|var")
_TAG = re.compile(rf"</?(?:{_HTML_TAGS})\b[^>]*>", re.I)
_FRONT = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)


def _invisible(ch: str) -> bool:
    cat = unicodedata.category(ch)
    return cat == "Cf" or (cat == "Cc" and ch not in "\n\t")


def clean(text: str) -> str:
    m = _FRONT.match(text)
    if m:
        try:
            meta = yaml.safe_load(m.group(1)) or {}
        except yaml.YAMLError:
            meta = {}
        title = meta.get("title") if isinstance(meta, dict) else None
        text = (f"# {title}\n" if isinstance(title, str) and title.strip() else "") + text[m.end():]
    text = "".join(ch for ch in text if not _invisible(ch))
    text = _COMMENT.sub("", text)
    text = _HIDDEN.sub("", text)
    text = _IMAGE.sub("", text)
    text = _DATA_URI.sub("", text)
    text = _LINK.sub(lambda m: f"{m.group(1)} ({m.group(2)})", text)
    text = _REL_LINK.sub(lambda m: m.group(1), text)
    text = _TAG.sub("", text)
    return text.strip()
