/**
 * Output port: what the UI needs from any authentication provider.
 * Adapters (mock today, HTTP tomorrow) must implement this shape.
 *
 * @typedef {Object} AuthPort
 * @property {(credentials: {email: string, password: string}) => Promise<{user: {email: string}}>} signIn
 *           Resolves with the session, rejects with an Error whose message is safe to show.
 * @property {() => Promise<void>} signOut
 */
export {};
