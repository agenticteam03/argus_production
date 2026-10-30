// DEMO ONLY: lets the mock "server" know who is calling, like the real one derives it from the token.
// `keyConfirmed`: the demo's security key confirmed this session (ACR-0032), so the console and Actions open.
export const demoSession = { role: null, name: null, keyConfirmed: false };

// T-0016: the demo's security keys, per role, in memory: an operator and an approver start with two, a viewer with
// none (the console's "ask your administrator" case). The Security keys page registers more, like the real one.
const now = () => new Date().toISOString();
const START = () => ({
  viewer: [],
  operator: [{ credential: "demo-op-1", label: "Laptop passkey", created_at: now(), last_used_at: null },
    { credential: "demo-op-2", label: "Phone passkey", created_at: now(), last_used_at: null }],
  approver: [{ credential: "demo-ap-1", label: "Laptop passkey", created_at: now(), last_used_at: null },
    { credential: "demo-ap-2", label: "Phone passkey", created_at: now(), last_used_at: null }],
});
let keys = START();

export const resetDemoKeys = () => { keys = START(); demoSession.keyConfirmed = false; };
export const demoKeysOf = (role) => keys[role] ?? [];
export const addDemoKey = (role, label) => {
  const list = demoKeysOf(role);
  keys[role] = [...list, { credential: `demo-${role}-${list.length + 1}`, label, created_at: now(), last_used_at: null }];
};
// /me's `second_factor` for the demo's session
export const demoSecondFactor = (role) => ({ enrolled: demoKeysOf(role).length, verified: demoSession.keyConfirmed });
