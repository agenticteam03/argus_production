import { createContext, lazy, Suspense, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useAuth } from "../../../context/AuthContext.jsx";
import { argus, dataSource } from "../../../services/index.js";
import { hostOf } from "../../../utils/incidentView.js";
import { Toast } from "../../ui.jsx";
import { canSeeConsole, consoleBuilt, MAX_TABS } from "./consoleDock.js";

// T-0016: the operator console (ACR-0043) in a side panel, opened from Tools or an incident, several at once (one tab
// per incident: the console's routes are scoped to one). The dialog and the panel load only when first used.
const ConsoleAccessDialog = lazy(() => import("./ConsoleAccessDialog.jsx"));
const ConsoleDock = lazy(() => import("./ConsoleDock.jsx"));

const DockContext = createContext({ visible: false, open: () => {} });
export const useConsoleDock = () => useContext(DockContext);

export function ConsoleDockProvider({ children }) {
  const { user } = useAuth();
  const visible = consoleBuilt(dataSource, import.meta.env) && canSeeConsole(user);
  const [tabs, setTabs] = useState([]);             // { incidentId, host, target, reason, sessionId, expiresAt }
  const [activeId, setActiveId] = useState(null);
  const [access, setAccess] = useState(null);      // the dialog's request: { host?, incident? }
  const [mode, setMode] = useState("docked");      // docked | minimized | fullscreen
  const [notice, setNotice] = useState("");

  // Open the console: the incident's tab when it is already open, else the access dialog.
  const open = useCallback((request = {}) => {
    if (!visible) return;
    const existing = request.incident && tabs.find((t) => t.incidentId === request.incident.id);
    if (existing) {
      setActiveId(existing.incidentId);
      setMode((m) => (m === "minimized" ? "docked" : m));
      return;
    }
    setAccess(request);
  }, [visible, tabs]);

  // After the dialog: the session is recorded with its reason (the API's audit), then its tab opens.
  const start = useCallback(async (incident, reason) => {
    const s = await argus.openConsoleSession(incident.id, reason);
    setTabs((all) => [...all, { incidentId: incident.id, host: hostOf(incident.target), target: incident.target, reason,
      sessionId: s.session_id, expiresAt: s.expires_at }]);
    setActiveId(incident.id);
    setMode((m) => (m === "minimized" ? "docked" : m));
    setAccess(null);
  }, []);

  const close = useCallback((incidentId, why, message) => {
    const tab = tabs.find((t) => t.incidentId === incidentId);
    if (!tab) return;
    argus.closeConsoleSession(incidentId, tab.sessionId, why).catch(() => {});   // best effort: it is a record
    setTabs((all) => all.filter((t) => t.incidentId !== incidentId));
    setNotice(message);
  }, [tabs]);

  // The active tab always exists; with none left the panel goes away.
  useEffect(() => {
    if (!tabs.some((t) => t.incidentId === activeId)) setActiveId(tabs.at(-1)?.incidentId ?? null);
    if (!tabs.length) setMode("docked");
  }, [tabs, activeId]);

  // Signed out (or no longer allowed): every session ends; the API's token is gone, so nothing more is sent.
  useEffect(() => {
    if (visible) return;
    setTabs([]);
    setAccess(null);
  }, [visible]);

  const value = useMemo(() => ({ visible, open, full: tabs.length >= MAX_TABS,
    openIds: tabs.map((t) => t.incidentId) }), [visible, open, tabs]);

  return (
    <DockContext.Provider value={value}>
      {children}
      {visible && (
        <Suspense fallback={null}>
          {access && <ConsoleAccessDialog request={access} openIds={value.openIds} full={value.full}
            onCancel={() => setAccess(null)} onEnter={start} />}
          {tabs.length > 0 && <ConsoleDock tabs={tabs} activeId={activeId} onSelect={setActiveId} mode={mode} onMode={setMode}
            onAdd={(host) => open({ host })} onClose={close} full={value.full} />}
        </Suspense>
      )}
      {notice && <Toast onDone={() => setNotice("")}>{notice}</Toast>}
    </DockContext.Provider>
  );
}
