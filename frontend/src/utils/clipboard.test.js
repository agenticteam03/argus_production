import { afterEach, describe, expect, it, vi } from "vitest";
import { copyText, downloadText } from "./clipboard.js";

// Node has no DOM: the browser objects these helpers use are stubbed per test.
function fakeDocument({ copies = true } = {}) {
  const made = [];
  const doc = {
    body: { appendChild: vi.fn() },
    createElement: (tag) => {
      const el = { tag, style: {}, setAttribute: vi.fn(), select: vi.fn(), remove: vi.fn(), click: vi.fn() };
      made.push(el);
      return el;
    },
    execCommand: vi.fn(() => copies),
  };
  return { doc, made };
}

afterEach(() => vi.unstubAllGlobals());

describe("copyText", () => {
  it("uses the Clipboard API when it is available", async () => {
    const writeText = vi.fn(async () => {});
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    expect(await copyText("summary")).toBe(true);
    expect(writeText).toHaveBeenCalledWith("summary");
  });

  it("falls back to a hidden read-only textarea outside a secure context, and removes it", async () => {
    vi.stubGlobal("navigator", {});
    const { doc, made } = fakeDocument();
    vi.stubGlobal("document", doc);
    expect(await copyText("summary")).toBe(true);
    const [area] = made;
    expect(area.tag).toBe("textarea");
    expect(area.value).toBe("summary");
    expect(area.setAttribute).toHaveBeenCalledWith("readonly", "");
    expect(area.style.opacity).toBe("0");
    expect(doc.execCommand).toHaveBeenCalledWith("copy");
    expect(area.remove).toHaveBeenCalled();
  });

  it("reports false when the fallback cannot copy either", async () => {
    vi.stubGlobal("navigator", {});
    vi.stubGlobal("document", fakeDocument({ copies: false }).doc);
    expect(await copyText("summary")).toBe(false);
    vi.stubGlobal("document", undefined);
    expect(await copyText("summary")).toBe(false);
  });
});

describe("downloadText", () => {
  it("saves through a temporary object URL and releases it", () => {
    const { doc, made } = fakeDocument();
    vi.stubGlobal("document", doc);
    const create = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:argus/1");
    const revoke = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
    downloadText("incident.json", "{}");
    const [a] = made;
    expect(a.href).toBe("blob:argus/1");
    expect(a.download).toBe("incident.json");
    expect(a.click).toHaveBeenCalled();
    expect(create.mock.calls[0][0].type).toBe("application/json");
    expect(revoke).toHaveBeenCalledWith("blob:argus/1");
    create.mockRestore();
    revoke.mockRestore();
  });
});
