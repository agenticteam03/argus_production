import { describe, expect, it } from "vitest";
import { b64urlToBytes, bytesToB64url, credentialToJSON, toCreationOptions, toRequestOptions } from "./webauthn.js";

const bytes = (...n) => new Uint8Array(n);

describe("base64url", () => {
  it("round-trips any bytes, with the URL alphabet and no padding", () => {
    const data = bytes(0, 251, 255, 62, 63, 1, 2);
    const text = bytesToB64url(data);
    expect(text).not.toMatch(/[+/=]/);
    expect([...b64urlToBytes(text)]).toEqual([...data]);
    expect(bytesToB64url(data.buffer)).toBe(text);                          // an ArrayBuffer too
    expect([...b64urlToBytes("-_8")]).toEqual([251, 255]);
  });
});

describe("options from the API", () => {
  it("turn the challenge, the user id and the excluded keys into bytes for create()", () => {
    const o = toCreationOptions({ challenge: "AQID", rp: { id: "argus.test" }, user: { id: "BAU", name: "alice" },
      excludeCredentials: [{ id: "Bwg", type: "public-key" }], timeout: 300000 });
    expect([...o.challenge]).toEqual([1, 2, 3]);
    expect([...o.user.id]).toEqual([4, 5]);
    expect(o.user.name).toBe("alice");
    expect([...o.excludeCredentials[0].id]).toEqual([7, 8]);
    expect(o.rp).toEqual({ id: "argus.test" });
    expect(o.timeout).toBe(300000);
  });

  it("turn the challenge and the allowed keys into bytes for get(), with none allowed when absent", () => {
    const o = toRequestOptions({ challenge: "AQID", allowCredentials: [{ id: "Bwg", type: "public-key" }] });
    expect([...o.challenge]).toEqual([1, 2, 3]);
    expect([...o.allowCredentials[0].id]).toEqual([7, 8]);
    expect(toRequestOptions({ challenge: "AQID" }).allowCredentials).toEqual([]);
  });
});

describe("credentialToJSON", () => {
  it("encodes a new key with its attestation and transports", () => {
    const j = credentialToJSON({ id: "Bwg", rawId: bytes(7, 8), type: "public-key", authenticatorAttachment: "platform",
      getClientExtensionResults: () => ({ credProps: { rk: true } }),
      response: { clientDataJSON: bytes(1), attestationObject: bytes(2), getTransports: () => ["internal"] } });
    expect(j).toEqual({ id: "Bwg", rawId: "Bwg", type: "public-key", authenticatorAttachment: "platform",
      clientExtensionResults: { credProps: { rk: true } },
      response: { clientDataJSON: "AQ", attestationObject: "Ag", transports: ["internal"] } });
  });

  it("encodes an assertion with its signature, and the user handle only when there is one", () => {
    const base = { id: "Bwg", rawId: bytes(7, 8), type: "public-key" };
    const j = credentialToJSON({ ...base, response: { clientDataJSON: bytes(1), authenticatorData: bytes(3),
      signature: bytes(4), userHandle: bytes(5) } });
    expect(j.response).toEqual({ clientDataJSON: "AQ", authenticatorData: "Aw", signature: "BA", userHandle: "BQ" });
    expect(j.clientExtensionResults).toEqual({});
    const none = credentialToJSON({ ...base, response: { clientDataJSON: bytes(1), authenticatorData: bytes(3),
      signature: bytes(4), userHandle: null } });
    expect(none.response).not.toHaveProperty("userHandle");
  });
});
