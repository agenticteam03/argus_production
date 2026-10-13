/**
 * Output port: what the UI needs from any authentication provider.
 * Adapters (mock today, HTTP tomorrow) must implement this shape.
 *
 * @typedef {Object} AuthPort
 * @property {(credentials: {username: string, password: string}) => Promise<{user: {name: string, role: string, access: string, actions: string[]}}>} signIn
 *           Resolves with the session, rejects with an Error whose message is safe to show.
 * @property {() => ({user: {name: string, role: string, access: string, actions: string[]}} | null)} restore
 *           Sync: restores a persisted session after a page reload in the same tab. Both adapters read it from
 *           `sessionStorage` (`sessionStore.js`); the HTTP adapter also puts the bearer token back in memory.
 * @property {() => Promise<void>} signOut
 */
export {};
