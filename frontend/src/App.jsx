import { BrowserRouter, Navigate, Outlet, Route, Routes } from "react-router-dom";
import Header from "./components/Header.jsx";
import { AuthProvider, useAuth } from "./context/AuthContext.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import Login from "./pages/Login.jsx";
import Runbooks from "./pages/Runbooks.jsx";
import { canSee, flat } from "./routes.js";

const Placeholder = ({ title }) => (
  <div className="grid place-items-center rounded-2xl border border-dashed border-line py-24 text-center">
    <h1 className="text-xl font-semibold">{title}</h1>
    <p className="mt-1 text-sm text-muted">Coming soon.</p>
  </div>
);

const Shell = () => (
  <>
    <Header />
    <main className="mx-auto w-full max-w-[1200px] px-4 py-6 sm:px-6"><Outlet /></main>
  </>
);

function AppRoutes() {
  const { user, login } = useAuth();
  if (!user) return <Login onLogin={login} />;
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route index element={<Dashboard />} />
        {flat.filter((r) => r.path !== "/" && canSee(r, user)).map((r) => (
          <Route key={r.path} path={r.path} element={r.path === "/tools/runbooks" ? <Runbooks /> : <Placeholder title={r.label} />} />
        ))}
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
