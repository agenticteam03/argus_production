import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { AuditSection, EvidenceSection, RestrictedNotice } from "./EvidenceAudit.jsx";

const CACHE = "vm-166/container:argus-lab-cache";
const item = (id, extra = {}) => ({ evidence_id: id, kind: "observation", capability: "container.status", target: CACHE, status: "ok",
  collected_at: "2026-10-21T12:00:00Z", model_text: "exited (0)", sha256: "a".repeat(64), ...extra });
const evidence = (props) =>
  renderToStaticMarkup(<EvidenceSection items={[]} cited={[]} host="vm-166" open={new Set()} onToggle={() => {}} {...props} />);
const audit = (items, evidenceIds = new Set()) => renderToStaticMarkup(<AuditSection items={items} evidenceIds={evidenceIds} onJump={() => {}} />);

describe("RestrictedNotice", () => {
  it("tells a viewer who may see the section, not an error", () => {
    expect(renderToStaticMarkup(<RestrictedNotice title="Evidence" label="Evidence" />)).toContain("Evidence is visible to operators and approvers.");
  });
});

describe("EvidenceSection", () => {
  it("says when nothing was collected", () => {
    expect(evidence()).toContain("No evidence was collected.");
  });

  it("lists each record with its status, marks the cited ones and keeps the content folded until opened", () => {
    const items = [item("ev_1"), item("ev_2", { status: "timeout" })];
    const closed = evidence({ items, cited: ["ev_1"] });
    expect(closed).toContain("ev_1");
    expect(closed).toContain("timeout");
    expect(closed.match(/>cited</g)).toHaveLength(1);
    expect(closed).toMatch(/id="evidence-panel-ev_1" hidden=""/);
    expect(closed).toContain('aria-expanded="false"');
    const open = evidence({ items, cited: ["ev_1"], open: new Set(["ev_1"]) });
    expect(open).not.toMatch(/id="evidence-panel-ev_1" hidden=""/);
    expect(open).toContain("Hide content");
  });
});

describe("AuditSection", () => {
  it("says when there are no entries", () => {
    expect(audit([])).toContain("No audit entries.");
  });

  it("links an entry to evidence it has, shows text detail inline, and offers Details only for JSON or a policy rule", () => {
    const out = audit([
      { at: "2026-10-21T12:00:00Z", event: "tool.read", evidence_id: "ev_1", actor: "worker" },
      { at: "2026-10-21T12:00:01Z", event: "decision.conclude", detail: "concluded", actor: "worker" },
      { at: "2026-10-21T12:00:02Z", event: "decision.escalate", detail: { reason: "unsupported" }, actor: "worker" },
      { at: "2026-10-21T12:00:03Z", event: "tool.read", evidence_id: "ev_gone", actor: "worker" },
    ], new Set(["ev_1"]));
    expect(out).toMatch(/<button[^>]*>ev_1<\/button>/);
    expect(out).toContain("concluded");
    expect(out.match(/>Details</g)).toHaveLength(1);
    expect(out).toMatch(/<span[^>]*>ev_gone<\/span>/);
  });
});
