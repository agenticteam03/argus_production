import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import PrivateLogin from "./PrivateLogin.jsx";

describe("PrivateLogin", () => {
  it("explains the private path and asks for the password again", () => {
    const out = renderToStaticMarkup(<PrivateLogin busy={false} onSubmit={() => {}} />);
    for (const text of ["private", "15 minutes without use", "type=\"password\"", "Sign in privately"]) expect(out).toContain(text);
  });
});
