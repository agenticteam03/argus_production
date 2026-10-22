import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { SecurityView } from "./Security.jsx";

const noop = () => {};
const view = (over = {}) => renderToStaticMarkup(
  <SecurityView status={{ enrolled: 0, verified: false }} keys={[]} browserOk busy={false} error={null} notice={null}
    onEnrol={noop} onAddAnother={noop} onConfirm={noop} {...over} />);

describe("SecurityView", () => {
  it("waits for the status, and says so when the API has no second factor", () => {
    expect(view({ status: undefined })).toContain("animate-pulse");
    expect(view({ status: null })).toContain("not set up on this Argus");
  });

  it("asks for another administrator's code before the first key, and offers no confirmation yet", () => {
    const out = view();
    expect(out).toContain("Enrolment code");
    expect(out).toContain("Register this key");
    expect(out).toContain("argus webauthn allow-enrol");
    expect(out).toContain("No key registered yet.");
    expect(out).not.toContain("Confirm with my key");
    expect(out).toMatch(/<button type="submit"[^>]*disabled=""/);            // no code typed yet
  });

  it("lists the keys, offers to confirm this login and to add a second key with a step-up", () => {
    const keys = [{ credential: "Bwg", label: "laptop", created_at: "2026-10-22T10:00:00Z", last_used_at: null }];
    const out = view({ status: { enrolled: 1, verified: false }, keys });
    expect(out).toContain("laptop");
    expect(out).toContain("Confirm with my key");
    expect(out).toContain("Add another key");
    expect(out).not.toContain("Enrolment code");
    expect(out).toContain("Add a second key");
    expect(out).toContain("confirm with one you already have");
  });

  it("shows a confirmed login with two keys without the prompts", () => {
    const out = view({ status: { enrolled: 2, verified: true }, keys: [] });
    expect(out).toContain("Confirmed with a key.");
    expect(out).not.toContain("Confirm with my key");
    expect(out).not.toContain("Add a second key");
  });

  it("announces errors and results, and says when the browser cannot use keys", () => {
    expect(view({ error: "the enrolment ticket was used or has expired" })).toMatch(/role="alert"[^>]*>the enrolment ticket was used/);
    expect(view({ notice: "Key registered." })).toMatch(/role="status"[^>]*>Key registered\./);
    const out = view({ browserOk: false, status: { enrolled: 1, verified: false } });
    expect(out).toContain("This browser cannot use security keys.");
    expect(out).toMatch(/disabled=""[^>]*>Confirm with my key/);
  });
});
