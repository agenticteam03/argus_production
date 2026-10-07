// Turns the raw Markdown of a runbook into the data shown on its card.
const clean = (s) => s.replace(/\[([^\]]+)\]\([^)]*\)/g, "$1").replace(/[`*]/g, "").replace(/\s+/g, " ").trim();
const sentences = (s, n) => clean(s).split(/(?<=[.!?])\s+/).slice(0, n).join(" ");

function section(md, name) {
  const m = md.match(new RegExp(`^## ${name}\\s*$([\\s\\S]*?)(?=^## |(?![\\s\\S]))`, "mi"));
  return m ? m[1].trim() : "";
}

export function parseRunbook({ file, markdown }) {
  const yaml = section(markdown, "Metadata").match(/```yaml\n([\s\S]*?)```/)?.[1] ?? "";
  const meta = Object.fromEntries(
    yaml.split("\n").map((l) => l.match(/^(\w+):\s*(.*)$/)).filter(Boolean).map(([, k, v]) => [k, v === "null" ? null : v])
  );

  // "Required Argus tools" table: | `tool(args)` | purpose | `SAFETY_CLASS` |
  const tools = [];
  for (const row of section(markdown, "Required Argus tools").split("\n")) {
    if (!row.startsWith("|")) continue;
    const cells = row.split("|").map((c) => c.trim());
    const safety = cells[cells.length - 2]?.replace(/`/g, "");
    if (!/^[A-Z_]+$/.test(safety)) continue; // skips header and separator rows
    for (const m of cells[1].matchAll(/`([a-z0-9_]+)\(/g)) tools.push({ name: m[1], safety });
  }

  return {
    file,
    markdown,
    id: meta.id ?? file,
    title: meta.title ?? markdown.match(/^# (.+)$/m)?.[1] ?? file,
    version: meta.version,
    status: meta.status ?? "unknown",
    owner: meta.owner,
    lastReviewed: meta.last_reviewed,
    detector: meta.detector,
    summary: sentences(section(markdown, "Incident definition"), 2),
    scope: sentences(section(markdown, "Scope"), 1),
    tools,
    risk: tools.some((t) => t.safety.includes("HIGH_RISK")) ? "high" : tools.some((t) => t.safety.startsWith("MUTATING")) ? "mutating" : "read-only",
    missing: (markdown.match(/MISSING TOOL REQUIREMENT/g) ?? []).length,
  };
}
