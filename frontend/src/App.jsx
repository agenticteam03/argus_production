import { BrowserRouter, Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";
import ErrorBoundary from "./components/ErrorBoundary.jsx";
import Header from "./components/Header.jsx";
import { ConsoleDockProvider } from "./components/console/dock/ConsoleDockContext.jsx";
import { AuthProvider, useAuth } from "./context/AuthContext.jsx";
import Agent from "./pages/Agent.jsx";
import Actions from "./pages/Actions.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import IncidentDetail from "./pages/IncidentDetail.jsx";
import Incidents from "./pages/Incidents.jsx";
import Login from "./pages/Login.jsx";
import ReferenceSources from "./pages/ReferenceSources.jsx";
import Runbooks from "./pages/Runbooks.jsx";
import Security from "./pages/Security.jsx";
import { canSee, flat, subRoutes } from "./routes.js";

const Placeholder = ({ title }) => (
  <div className="grid place-items-center rounded-2xl border border-dashed border-line py-24 text-center">
    <h1 className="text-xl font-semibold">{title}</h1>
    <p className="mt-1 text-sm text-muted">Coming soon.</p>
  </div>
);

const pages = { "/agent": Agent, "/actions": Actions, "/incidents": Incidents, "/incidents/:id": IncidentDetail, "/tools/runbooks": Runbooks,
  "/tools/reference-sources": ReferenceSources,
  "/account/security": Security };

// Keyed on the path so an error on one page does not stick when the user navigates elsewhere.
const Shell = () => {
  const { pathname } = useLocation();
  return (
    <ConsoleDockProvider>
      {/* T-0016: a docked console panel takes the right side on wide screens; the page shrinks beside it */}
      {/* @container: the header lays itself out by the room it has, not by the window's width */}
      <div className="@container lg:pr-[var(--console-w,0px)]">
        <Header />
        <main className="mx-auto w-full max-w-[1200px] px-4 py-6 sm:px-6">
          {/* T-0016: a new element per path, so each page fades in (motion.css page-in) */}
          <ErrorBoundary key={pathname}><div className="animate-page-in"><Outlet /></div></ErrorBoundary>
        </main>
      </div>
    </ConsoleDockProvider>
  );
};

function AppRoutes() {
  const { user, login } = useAuth();
  if (!user) return <Login onLogin={login} />;
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route index element={<Dashboard />} />
        {[...flat, ...subRoutes].filter((r) => r.path !== "/" && canSee(r, user.role, user.actions)).map((r) => {
          const Page = pages[r.path];
          return <Route key={r.path} path={r.path} element={Page ? <Page /> : <Placeholder title={r.label} />} />;
        })}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </AuthProvider>
  );
}
