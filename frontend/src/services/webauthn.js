// ACR-0018 phase 16 step 3: the browser side of the WebAuthn ceremonies. The API sends its options as JSON
// (base64url strings where the browser wants bytes) and expects the PublicKeyCredential back as JSON. These helpers
// convert both ways; nothing here decides anything: the server checks every ceremony.

export const supported = () => typeof window !== "undefined" && typeof window.PublicKeyCredential === "function";

export function b64urlToBytes(text) {
  const b64 = text.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(text.length / 4) * 4, "=");
  return Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
}

export function bytesToB64url(data) {
  const bytes = data instanceof Uint8Array ? data : new Uint8Array(data);
  let s = "";
  for (const b of bytes) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

const descriptors = (list) => (list ?? []).map((d) => ({ ...d, id: b64urlToBytes(d.id) }));

// `navigator.credentials.create({ publicKey })` from the API's registration options.
export const toCreationOptions = (json) => ({
  ...json,
  challenge: b64urlToBytes(json.challenge),
  user: { ...json.user, id: b64urlToBytes(json.user.id) },
  excludeCredentials: descriptors(json.excludeCredentials),
});

// `navigator.credentials.get({ publicKey })` from the API's authentication options.
export const toRequestOptions = (json) => ({
  ...json,
  challenge: b64urlToBytes(json.challenge),
  allowCredentials: descriptors(json.allowCredentials),
});

// The PublicKeyCredential (a new key or an assertion) as the JSON the API verifies.
export function credentialToJSON(cred) {
  const r = cred.response;
  const response = { clientDataJSON: bytesToB64url(r.clientDataJSON) };
  if (r.attestationObject) {
    response.attestationObject = bytesToB64url(r.attestationObject);
    if (typeof r.getTransports === "function") response.transports = r.getTransports();
  } else {
    response.authenticatorData = bytesToB64url(r.authenticatorData);
    response.signature = bytesToB64url(r.signature);
    if (r.userHandle) response.userHandle = bytesToB64url(r.userHandle);
  }
  return {
    id: cred.id, rawId: bytesToB64url(cred.rawId), type: cred.type, response,
    ...(cred.authenticatorAttachment ? { authenticatorAttachment: cred.authenticatorAttachment } : {}),
    clientExtensionResults: typeof cred.getClientExtensionResults === "function" ? cred.getClientExtensionResults() : {},
  };
}
