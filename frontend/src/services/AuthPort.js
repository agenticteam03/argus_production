/**
 * Output port: what the UI needs from any authentication provider.
 * Adapters (mock today, HTTP tomorrow) must implement this shape.
 *
 * @typedef {Object} AuthPort
 * @property {(credentials: {username: string, password: string}) => Promise<{user: {name: string, role: string, access: string, actions: string[]}}>} signIn
 *           Resolves with the session, rejects with an Error whose message is safe to show.
 * @property {() => ({user: {name: string, role: string, access: string, actions: string[]}} | null)} restore
 *           Sync: restores a persisted session after a page reload. The mock adapter restores its no-token
 *           session; the HTTP adapter returns null (the token lives in memory only, T-0016 rule 4).
 * @property {() => Promise<void>} signOut
 */
export {};
