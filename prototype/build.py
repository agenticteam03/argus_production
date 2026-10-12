"""Bundle the offline prototype into one portable HTML file; no dependencies."""
from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parent
source = ROOT / "src"
html = (source / "template.html").read_text(encoding="utf-8")
books = []
for path in sorted((ROOT.parent / "argus" / "runbooks").glob("RB-*.md")):
    body = path.read_text(encoding="utf-8")
    def field(name, default=""):
        match = re.search(rf"^{name}:\s*(.+)$", body, re.MULTILINE)
        return match.group(1).strip() if match else default
    books.append({"id": field("id", path.name[:6]), "title": field("title", path.stem),
                  "status": field("status", "draft"), "version": field("version"),
                  "detector": field("detector"), "body": body, "file": path.name})
for marker, name in [("STYLES", "styles.css"), ("ENGINE", "simulation.js"), ("APP", "app.js")]:
    content = (source / name).read_text(encoding="utf-8")
    if name == "app.js":
        content = content.replace("/*__RUNBOOKS__*/[]", json.dumps(books, ensure_ascii=True).replace("</", "<\\/"))
    if name.endswith(".js") and "</script" in content.lower():
        raise ValueError(f"Unsafe inline script terminator in {name}")
    html = html.replace(f"/*__{marker}__*/", content)
(ROOT / "index.html").write_bytes(html.replace("\r\n", "\n").encode("utf-8"))
print(f"Built prototype/index.html ({len(html.encode('utf-8')):,} bytes); fully offline")
