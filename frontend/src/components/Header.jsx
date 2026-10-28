import { useEffect } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext.jsx";
import { ROLES, canSee, routes } from "../routes.js";
import { useTheme } from "../hooks/useTheme.js";
import NotificationBell from "./NotificationBell.jsx";
import { Chevron, Logo, Moon, Sun } from "./ui.jsx";

// Compact pills up to lg so the menu stays on one row with the logo and the buttons from sm (640 px) up.
const pill = "whitespace-nowrap rounded-lg border px-2.5 py-2 text-sm transition motion-reduce:transition-none lg:px-3.5";
const on = "border-line bg-ink/5 text-ink";
const off = "border-transparent text-muted hover:text-ink";
const summary = "flex cursor-pointer list-none items-center gap-1.5 [&::-webkit-details-marker]:hidden";
const menu = "absolute z-20 mt-2 min-w-60 rounded-xl border border-line bg-card p-1.5 shadow-2xl";
const closeMenu = (e) => e.currentTarget.closest("details")?.removeAttribute("open");

export default function Header() {
  const { user, logout } = useAuth();
  const { pathname } = useLocation();
  const [theme, toggleTheme] = useTheme();

  // Close any open dropdown when clicking outside of it.
  useEffect(() => {
    const close = (e) =>
      document.querySelectorAll("header details[open]").forEach((d) => !d.contains(e.target) && d.removeAttribute("open"));
    document.addEventListener("click", close);
    return () => document.removeEventListener("click", close);
  }, []);

  const items = routes.filter((r) => (r.children ? r.children.some((c) => canSee(c, user.role, user.actions)) : canSee(r, user.role, user.actions)));

  return (
    <header className="relative z-30 mx-auto mt-4 flex w-[calc(100%-2rem)] max-w-[1200px] flex-wrap items-center justify-between gap-2 rounded-2xl border border-line bg-card/80 p-2.5 backdrop-blur sm:w-[calc(100%-3rem)] sm:flex-nowrap lg:gap-3">
      <Link to="/" aria-label="Argus home" className="grid size-11 place-items-center rounded-xl border border-line bg-field">
        <Logo width="20" height="20" className="text-ink" />
      </Link>

      <nav className="order-last flex w-full flex-wrap items-center justify-center gap-0.5 sm:order-none sm:w-auto sm:flex-nowrap lg:gap-1">
        {items.map((r) =>
          r.children ? (
            <details key={r.label} className="relative">
              <summary className={`${summary} ${pill} ${pathname.startsWith("/tools") ? on : off}`}>
                {r.label} <Chevron width="14" height="14" />
              </summary>
              <div className={`${menu} left-1/2 -translate-x-1/2`}>
                {r.children.filter((c) => canSee(c, user.role, user.actions)).map((c) => (
                  <Link key={c.path} to={c.path} onClick={closeMenu} className="block rounded-lg px-3 py-2 hover:bg-ink/5">
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
        <button type="button" onClick={toggleTheme} aria-label={theme === "light" ? "Switch to dark theme" : "Switch to light theme"} title={theme === "light" ? "Dark theme" : "Light theme"} className="grid size-10 cursor-pointer place-items-center rounded-xl border border-line bg-field text-muted hover:text-ink">
          {theme === "light" ? <Moon /> : <Sun />}
        </button>
        <NotificationBell />
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
            {user.actions?.includes("manage_second_factor") && (   // ACR-0018 step 3: only when Argus offers it
              <Link to="/account/security" onClick={closeMenu} className="block rounded-lg px-3 py-2 text-sm hover:bg-ink/5">Security keys</Link>
            )}
            <button onClick={logout} className="w-full cursor-pointer rounded-lg px-3 py-2 text-left text-sm hover:bg-ink/5">Log out</button>
          </div>
        </details>
      </div>
    </header>
  );
}
