import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import AnswerBlock from "./AnswerBlock.jsx";

const html = (incident, active = false) => renderToStaticMarkup(<AnswerBlock incident={incident} active={active} />);

describe("AnswerBlock", () => {
  it("says no diagnosis yet while the run is active, and none was produced once it is final", () => {
    expect(html({}, true)).toContain("No diagnosis yet");
    expect(html({}, false)).toContain("No diagnosis was produced");
  });

  it("shows the root cause target and only the diagnosis' first sentence, without a 'Root cause:' prefix", () => {
    const out = html({
      root_cause_target: "vm-166/container:argus-lab-cache",
      diagnosis: "**Root cause:** the cache container is stopped. The API cannot resolve its name.",
    });
    expect(out).toContain("vm-166/container:argus-lab-cache");
    expect(out).toContain("the cache container is stopped.");
    expect(out).not.toMatch(/root cause:/i);
    expect(out).not.toContain("cannot resolve");
  });

  it("shows a next step only when the backend gives one", () => {
    expect(html({ diagnosis: "Stopped." })).not.toContain("Next step for a person");
    const out = html({ diagnosis: "Stopped.", recommendation: "Start `argus-lab-cache`." });
    expect(out).toContain("Next step for a person");
    expect(out).toContain("<code>argus-lab-cache</code>");
  });
});
