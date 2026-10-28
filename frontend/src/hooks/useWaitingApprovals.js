import { useEffect, useState } from "react";
import { argus } from "../services/index.js";

const POLL_MS = 30_000;

// ACR-0042: the bell's count, asked every 30 s while /me lists count_waiting_approvals (an approver). Inside a confirmed
// private session (/me lists approve_action) it also reads the private list, so the bell can name each approval.
// A failed poll keeps the last answer: the bell never invents a count.
export function useWaitingApprovals(user) {
  const canCount = !!user?.actions?.includes("count_waiting_approvals");
  const canList = !!user?.actions?.includes("approve_action");
  const [state, setState] = useState({ count: null, items: null });

  useEffect(() => {
    if (!canCount) return undefined;
    let alive = true;
    const tick = async () => {
      try {
        const { waiting } = await argus.countWaitingApprovals();
        const items = canList ? await argus.listApprovals() : null;
        if (alive) setState({ count: waiting, items });
      } catch {
        /* keep the last answer; the next poll tries again */
      }
    };
    tick();
    const timer = setInterval(tick, POLL_MS);
    return () => { alive = false; clearInterval(timer); };
  }, [canCount, canList]);

  return canCount ? state : { count: null, items: null };
}
