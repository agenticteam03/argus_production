import { useEffect } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext.jsx";
import { ROLES, canSee, routes } from "../routes.js";
import { useTheme } from "../hooks/useTheme.js";
import { useConsoleDock } from "./console/dock/ConsoleDockContext.jsx";
import { TerminalIcon } from "./console/dock/icons.jsx";
import NotificationBell from "./NotificationBell.jsx";
import { Chevron, Logo, Moon, Sun } from "./ui.jsx";

// Compact pills below 64rem so the menu stays on one row with the logo and the buttons from 40rem up. The sizes are of
// the header's container (App.jsx), not the window: a docked console narrows it (T-0016).
// Below 52rem the less used pages move into Tools, so the row never overflows.
const COMPACT = new Set(["/agent", "/actions"]);
const pill = "whitespace-nowrap rounded-lg border px-2.5 py-2 text-sm transition motion-reduce:transition-none @min-[64rem]:px-3.5";
const on = "border-line bg-ink/5 text-ink";
const off = "border-transparent text-muted hover:text-ink";
const summary = "flex cursor-pointer list-none items-center gap-1.5 [&::-webkit-details-marker]:hidden";
const menu = "menu-pop absolute z-20 mt-2 min-w-60 rounded-xl border border-line bg-card p-1.5 shadow-2xl";
// T-0016: a menu's chevron turns while it is open (its panel drops in: motion.css .menu-pop).
const turn = "transition-transform group-open:rotate-180 motion-reduce:transition-none";
const closeMenu = (e) => e.currentTarget.closest("details")?.removeAttribute("open");

export default function Header() {
  const dock = useConsoleDock();
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
    <header className="relative z-30 mx-auto mt-4 flex w-[calc(100%-2rem)] max-w-[1200px] flex-wrap items-center justify-between gap-2 rounded-2xl border border-line bg-card/80 p-2.5 backdrop-blur @min-[40rem]:w-[calc(100%-3rem)] @min-[40rem]:flex-nowrap @min-[64rem]:gap-3">
      <Link to="/" aria-label="Argus home" className="grid size-11 place-items-center rounded-xl border border-line bg-field">
        <Logo width="20" height="20" className="text-ink" />
      </Link>

      <nav className="order-last flex w-full flex-wrap items-center justify-center gap-0.5 @min-[40rem]:order-none @min-[40rem]:w-auto @min-[40rem]:flex-nowrap @min-[64rem]:gap-1">
        {items.map((r) =>
          r.children ? (
            <details key={r.label} className="group relative">
              <summary className={`${summary} ${pill} ${pathname.startsWith("/tools") ? on : off}`}>
                {r.label} <Chevron width="14" height="14" className={turn} />
              </summary>
              <div className={`${menu} left-1/2 -translate-x-1/2`}>
                {/* the pages that leave the row below 52rem (a docked console) wait here */}
                {r.label === "Tools" && items.filter((x) => COMPACT.has(x.path)).map((x) => (
                  <NavLink key={x.path} to={x.path} onClick={closeMenu}
                    className={({ isActive }) => `block rounded-lg px-3 py-2 text-sm hover:bg-ink/5 @min-[52rem]:hidden ${isActive ? "text-ink" : ""}`}>
                    {x.label}
                  </NavLink>
                ))}
                {r.children.filter((c) => canSee(c, user.role, user.actions)).map((c) => (
                  <Link key={c.path} to={c.path} onClick={closeMenu} className="block rounded-lg px-3 py-2 hover:bg-ink/5">
                    <span className="text-sm">{c.label}</span>
                    <span className="block text-xs text-muted">{c.desc}</span>
                  </Link>
                ))}
                {/* T-0016: the operator console opens as a side panel, not a page (an approver's, like Actions) */}
                {r.label === "Tools" && dock.visible && (
                  <button type="button" onClick={(e) => { closeMenu(e); dock.open(); }}
                    className="block w-full cursor-pointer rounded-lg px-3 py-2 text-left hover:bg-ink/5">
                    <span className="flex items-center gap-1.5 text-sm"><TerminalIcon width="14" height="14" /> Console</span>
                    <span className="block text-xs text-muted">Run Argus&apos;s commands on a lab host</span>
                  </button>
                )}
              </div>
            </details>
          ) : (
            <NavLink key={r.path} to={r.path} end={r.path === "/"}
              className={({ isActive }) => `${pill} ${isActive ? on : off} ${COMPACT.has(r.path) ? "@max-[52rem]:hidden" : ""}`}>
              {r.label}
            </NavLink>
          )
        )}
      </nav>

      <div className="flex items-center gap-2">
        <button type="button" onClick={toggleTheme} aria-label={theme === "light" ? "Switch to dark theme" : "Switch to light theme"} title={theme === "light" ? "Dark theme" : "Light theme"} className="grid size-10 cursor-pointer place-items-center rounded-xl border border-line bg-field text-muted hover:text-ink">
          {/* keyed on the theme, so the new icon pops in as the page recolours (T-0016) */}
          <span key={theme} className="animate-pop">{theme === "light" ? <Moon /> : <Sun />}</span>
        </button>
        <NotificationBell />
        <details className="group relative">
          <summary className={summary} aria-label="Account menu">
            <span className="grid size-10 place-items-center rounded-full bg-accent/20 text-sm font-medium text-accent-hover">{user.name[0].toUpperCase()}</span>
            <Chevron width="14" height="14" className={`text-muted ${turn}`} />
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
