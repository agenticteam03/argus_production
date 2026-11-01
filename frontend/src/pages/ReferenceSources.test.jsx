import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { ReferenceSourcesView } from "./ReferenceSources.jsx";
import { bundles } from "../services/corpusSources.js";

const noop = () => {};
const SOURCES = [
  { name: "nginx", source: "nginx", ref: "159f0a3", licence: "BSD-2-Clause", status: "installed", passages: 845,
    quarantined: 0, at: "2026-10-27T06:10:00Z", sha256: "a".repeat(64) },
  { name: "redis", source: "redis", ref: "7.2.5", licence: "BSD-3-Clause", status: "staged", passages: 1204,
    quarantined: 2, at: "2026-10-27T07:00:00Z", sha256: "b".repeat(64) },
];
// A bundle named apart from its sources, identical to what is installed (vm-095's `base`).
const BASE = [
  { name: "man-pages", source: "man-pages", ref: "man-pages-6.20", licence: "various", status: "installed", passages: 2642,
    quarantined: 1, at: "2026-10-27T06:13:36Z", sha256: "c".repeat(64) },
  { name: "systemd", source: "systemd", ref: "v257", licence: "LGPL-2.1-or-later", status: "installed", passages: 4000,
    quarantined: 2, at: "2026-10-27T06:13:36Z", sha256: "c".repeat(64) },
  { name: "base", source: "man-pages", ref: "man-pages-6.20", licence: "various", status: "staged", passages: 2642,
    quarantined: 1, at: "2026-10-27T06:13:36Z", sha256: "c".repeat(64) },
  { name: "base", source: "systemd", ref: "v257", licence: "LGPL-2.1-or-later", status: "staged", passages: 4000,
    quarantined: 2, at: "2026-10-27T06:13:36Z", sha256: "c".repeat(64) },
];
const view = (over = {}) => renderToStaticMarkup(
  <ReferenceSourcesView sources={SOURCES} canManage busy={false} error={null} notice={null} reasons={{}}
    onReason={noop} onApprove={noop} onReject={noop} {...over} />);

describe("ReferenceSourcesView", () => {
  it("lists each source with its status, ref, licence, passages and quarantine count", () => {
    const out = view();
    expect(out).toContain("nginx");
    expect(out).toContain("Installed");
    expect(out).toContain("redis");
    expect(out).toContain("Waiting for review");
    expect(out).toContain("1204 passages · 2 quarantined");
    expect(out).toContain("BSD-3-Clause");
    expect(out).toContain("b".repeat(16));
  });

  it("groups a staged bundle's sources under one decision, names each source, and says when it is identical", () => {
    expect(bundles(BASE).map((b) => [b.key, b.sources.length])).toEqual([["installed", 2], ["staged:base", 2]]);
    const out = view({ sources: BASE });
    expect(out.match(/Approve with security key/g)).toHaveLength(1);
    expect(out).toContain("Staged bundle");
    expect(out.match(/>systemd</g)).toHaveLength(2);         // the source's own name, installed and staged
    expect(out).toContain("Identical to the installed corpus");
    expect(view()).not.toContain("Identical to the installed corpus");
  });

  it("shows when a bundle was built", () => {
    expect(view()).toContain("built");
    expect(view()).toMatch(/2026/);
  });

  it("offers decisions only on a staged source, and only to a manager", () => {
    expect(view().match(/Approve with security key/g)).toHaveLength(1);
    const reader = view({ canManage: false });
    expect(reader).not.toContain("Approve with security key");
    expect(reader).toContain("No decisions for this account");
  });

  it("keeps Reject disabled until a reason is typed", () => {
    expect(view()).toMatch(/<button type="button" disabled=""[^>]*>Reject<\/button>/);
    expect(view({ reasons: { redis: "not ours" } })).not.toMatch(/disabled=""[^>]*>Reject<\/button>/);
  });

  it("shows an API refusal inline (409: nothing staged or a hash mismatch)", () => {
    const out = view({ error: "staged bundle hash mismatch" });
    expect(out).toMatch(/role="alert"/);
    expect(out).toContain("staged bundle hash mismatch");
  });

  it("waits for the list, and says when there is none", () => {
    expect(view({ sources: null })).toContain("skeleton");       // T-0016: a shimmer, not a blink
    expect(view({ sources: [] })).toContain("No reference source is installed or staged.");
  });
});
