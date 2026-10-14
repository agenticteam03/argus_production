import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "../context/AuthContext.jsx";
import { argus } from "../services/index.js";
import { isActive } from "../utils/format.js";
import { POLL_MS } from "../utils/polling.js";
import { usePoll } from "./usePoll.js";

const merge = (prev, batch) => {
  const bySeq = new Map(prev.map((e) => [e.seq, e]));
  batch.forEach((e) => bySeq.set(e.seq, e));
  return [...bySeq.values()].sort((a, b) => a.seq - b.seq);
};

// Incident + its run timeline. While queued/running: incident every 3 s, events every 2 s with the `after` cursor.
// When it finishes: one last fetch of both, then polling stops.
export function useIncident(id) {
  const { logout } = useAuth();
  const [view, setView] = useState("loading"); // loading | ready | notfound | error
  const [incident, setIncident] = useState(null);
  const [events, setEvents] = useState([]);
  const [incidentOk, setIncidentOk] = useState(true);
  const [eventsOk, setEventsOk] = useState(true);
  const lastSeq = useRef(0);
  const sawActive = useRef(false);
  const finished = useRef(false);
  const currentId = useRef(id);
  currentId.current = id;

  const loadIncident = useCallback(async () => {
    try {
      const data = await argus.getIncident(id);
      if (currentId.current !== id) return null;
      setIncident(data);
      setView("ready");
      setIncidentOk(true);
      return data;
    } catch (err) {
      if (currentId.current !== id) return null;
      if (err.status === 401) logout();
      else if (err.status === 404) setView("notfound");
      else { setView((v) => (v === "ready" ? v : "error")); setIncidentOk(false); }
      return null;
    }
  }, [id, logout]);

  const loadEvents = useCallback(async () => {
    try {
      const batch = await argus.getIncidentEvents(id, { after: lastSeq.current });
      if (currentId.current !== id) return;
      if (batch.length) {
        lastSeq.current = Math.max(lastSeq.current, ...batch.map((e) => e.seq));
        setEvents((prev) => merge(prev, batch));
      }
      setEventsOk(true);
    } catch (err) {
      if (err.status === 401) logout();
      else if (currentId.current === id) setEventsOk(false);
    }
  }, [id, logout]);

  useEffect(() => {
    let cancelled = false;
    setView("loading"); setIncident(null); setEvents([]); setIncidentOk(true); setEventsOk(true);
    lastSeq.current = 0; sawActive.current = false; finished.current = false;
    (async () => {
      const data = await loadIncident();
      if (data && !cancelled) await loadEvents();
    })();
    return () => { cancelled = true; };
  }, [id, loadIncident, loadEvents]);

  const status = incident?.status;
  const running = !!status && isActive(status);
  usePoll(loadIncident, POLL_MS.runningIncident, running);
  usePoll(loadEvents, POLL_MS.runningEvents, running);

  useEffect(() => {
    if (!status) return;
    if (isActive(status)) { sawActive.current = true; return; }
    if (!sawActive.current || finished.current) return; // opened already finished: nothing more to fetch
    finished.current = true;
    loadIncident();
    loadEvents();
  }, [status, loadIncident, loadEvents]);

  const retry = useCallback(() => {
    setView("loading");
    loadIncident().then((data) => data && loadEvents());
  }, [loadIncident, loadEvents]);

  return { view, incident, events, reconnecting: !incidentOk || !eventsOk, retry };
}
