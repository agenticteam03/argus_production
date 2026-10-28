import { useState } from "react";
import { Card } from "./ui.jsx";

// ACR-0032: sign in again on the private path for a full token that works only there (15 minutes idle, one hour
// at most). It is kept in
// memory only: a reload returns to the ordinary login.
export default function PrivateLogin({ busy, onSubmit }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  return <Card title="Private sign-in">
    <p className="mb-3 text-sm text-muted">Decisions need a private session: this password and then your security key
      (and your team certificate where the edge asks for one). It ends after 15 minutes without use, after one hour, or
      if the page reloads.</p>
    <form className="grid gap-2 sm:grid-cols-[1fr_1fr_auto]" onSubmit={(event) => {
      event.preventDefault(); if (username && password) onSubmit({ username, password }); }}>
      <label htmlFor="private-user" className="sr-only">Username</label>
      <input id="private-user" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username"
        placeholder="Username" className="rounded-lg border border-line bg-field px-3 py-2 text-sm" />
      <label htmlFor="private-password" className="sr-only">Password</label>
      <input id="private-password" type="password" value={password} onChange={(e) => setPassword(e.target.value)}
        autoComplete="current-password" placeholder="Password" className="rounded-lg border border-line bg-field px-3 py-2 text-sm" />
      <button type="submit" disabled={busy || !username || !password}
        className="cursor-pointer rounded-lg bg-accent-solid px-4 py-2 text-sm text-white disabled:opacity-50">Sign in privately</button>
    </form>
  </Card>;
}
