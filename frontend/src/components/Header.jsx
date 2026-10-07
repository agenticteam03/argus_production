import { useEffect } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import logo from "../../public/images/argus-logo.png";
import { useAuth } from "../context/AuthContext.jsx";
import { ROLES, canSee, routes } from "../routes.js";
import { Bell, Chevron } from "./ui.jsx";

const pill = "rounded-lg border px-3.5 py-2 text-sm transition motion-reduce:transition-none";
const on = "border-line bg-white/5 text-white";
const off = "border-transparent text-muted hover:text-white";
const summary = "flex cursor-pointer list-none items-center gap-1.5 [&::-webkit-details-marker]:hidden";
const menu = "absolute z-20 mt-2 min-w-60 rounded-xl border border-line bg-card p-1.5 shadow-2xl";
const closeMenu = (e) => e.currentTarget.closest("details")?.removeAttribute("open");

export default function Header() {
  const { user, logout } = useAuth();
  const { pathname } = useLocation();

  // Close any open dropdown when clicking outside of it.
  useEffect(() => {
    const close = (e) =>
      document.querySelectorAll("header details[open]").forEach((d) => !d.contains(e.target) && d.removeAttribute("open"));
    document.addEventListener("click", close);
    return () => document.removeEventListener("click", close);
  }, []);

  const items = routes.filter((r) => (r.children ? r.children.some((c) => canSee(c, user)) : canSee(r, user)));

  return (
    <header className="relative z-30 mx-auto mt-4 flex w-[calc(100%-2rem)] max-w-[1200px] flex-wrap items-center justify-between gap-3 rounded-2xl border border-line bg-card/80 p-2.5 backdrop-blur sm:w-[calc(100%-3rem)] md:flex-nowrap">
      <Link to="/" aria-label="Argus home" className="grid size-11 place-items-center rounded-xl border border-line bg-field">
        <img src={logo} alt="" className="size-6" />
      </Link>

      <nav className="order-last flex w-full flex-wrap items-center justify-center gap-1 md:order-none md:w-auto">
        {items.map((r) =>
          r.children ? (
            <details key={r.label} className="relative">
              <summary className={`${summary} ${pill} ${pathname.startsWith("/tools") ? on : off}`}>
                {r.label} <Chevron width="14" height="14" />
              </summary>
              <div className={`${menu} left-1/2 -translate-x-1/2`}>
                {r.children.filter((c) => canSee(c, user)).map((c) => (
                  <Link key={c.path} to={c.path} onClick={closeMenu} className="block rounded-lg px-3 py-2 hover:bg-white/5">
                    <span className="text-sm">{c.label}</span>
                    <span className="block text-xs text-muted">{c.desc}</span>
                  </Link>
                ))}
              </div>
            </details>
          ) : (
            <NavLink key={r.path} to={r.path} end={r.path === "/"} className={({ isActive }) => `${pill} ${isActive ? on : off}`}>
              {r.label}
            </NavLink>
          )
        )}
      </nav>

      <div className="flex items-center gap-2">
        <button type="button" aria-label="Notifications" className="grid size-10 place-items-center rounded-xl border border-line bg-field text-muted hover:text-white">
          <Bell />
        </button>
        <details className="relative">
          <summary className={summary} aria-label="Account menu">
            <span className="grid size-10 place-items-center rounded-full bg-accent/20 text-sm font-medium text-accent-hover">{user.name[0].toUpperCase()}</span>
            <Chevron width="14" height="14" className="text-muted" />
          </summary>
          <div className={`${menu} right-0`}>
            <div className="px-3 py-2">
              <p className="truncate text-sm">{user.name}</p>
              <p className="text-xs text-muted">{ROLES[user.role]}</p>
            </div>
            <button onClick={logout} className="w-full cursor-pointer rounded-lg px-3 py-2 text-left text-sm hover:bg-white/5">Log out</button>
          </div>
        </details>
      </div>
    </header>
  );
}
