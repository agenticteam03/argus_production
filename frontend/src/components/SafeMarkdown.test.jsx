import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import SafeMarkdown from "./SafeMarkdown.jsx";

// SafeMarkdown renders runbooks and agent-generated text, which can carry text read from a target (a log line, an HTTP
// body). These are its safety rules, checked on the HTML it produces.
const html = (md) => renderToStaticMarkup(<SafeMarkdown>{md}</SafeMarkdown>);

describe("SafeMarkdown", () => {
  it("never renders raw HTML: a script or an inline handler stays text", () => {
    const out = html('Before <script>alert(1)</script> <img src=x onerror="alert(2)"> after');
    expect(out).not.toContain("<script");
    expect(out).not.toContain("<img");
    expect(out).toContain("Before");
  });

  it("drops images, even from an http(s) source", () => {
    expect(html("![logo](https://example.org/x.png)")).not.toContain("<img");
  });

  it("makes only http(s) links clickable, opened in a new tab without the opener", () => {
    const out = html("[docs](https://example.org/runbook)");
    expect(out).toContain('href="https://example.org/runbook"');
    expect(out).toContain('target="_blank"');
    expect(out).toContain('rel="noopener noreferrer"');
  });

  it.each([
    ["javascript", "[click](javascript:alert(1))"],
    ["data", "[click](data:text/html;base64,PHNjcmlwdD4=)"],
    ["relative", "[click](/api/v1/admin)"],
    ["mailto", "[click](mailto:someone@example.org)"],
  ])("renders a %s link as plain text", (_kind, md) => {
    const out = html(md);
    expect(out).not.toContain("<a");
    expect(out).toContain("<span>click</span>");
  });

  it("renders GitHub tables and treats a missing body as empty", () => {
    expect(html("| a | b |\n|---|---|\n| 1 | 2 |")).toContain("<table>");
    expect(html(undefined)).toBe("");
  });
});
