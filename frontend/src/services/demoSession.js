// DEMO ONLY: lets the mock "server" know who is calling, like the real one derives it from the token.
// `keyConfirmed`: the demo's security key confirmed the private session (ACR-0032), so the console and Actions open.
export const demoSession = { role: null, keyConfirmed: false };
