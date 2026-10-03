// What the Agent knows. All of it comes from the existing patient API (the same calls the pages make),
// loaded only when the panel is opened, cached briefly, and never invented.
import { useEffect, useState } from "react";
import { getAlerts, getInsights, getMedicines, getReminders, getTimeline } from "../../api/client.js";

let cache = null, at = 0, inflight = null;
const TTL = 45_000;

export function loadAgentData(force = false) {
  if (!force && cache && Date.now() - at < TTL) return Promise.resolve(cache);
  if (inflight) return inflight;
  inflight = Promise.allSettled([getTimeline(), getAlerts(), getMedicines(), getInsights(), getReminders()]).then((rs) => {
    const v = rs.map((r) => (r.status === "fulfilled" ? r.value : null));
    cache = { timeline: v[0] || [], alerts: v[1] || [], medicines: v[2] || [], insights: v[3] || null, reminders: v[4] || [], failed: rs.every((r) => r.status === "rejected") };
    at = Date.now();
    inflight = null;
    return cache;
  });
  return inflight;
}
export const clearAgentData = () => { cache = null; at = 0; };

export function useAgentData(enabled) {
  const [data, setData] = useState(cache);
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    if (!enabled) return;
    let alive = true;
    setLoading(true);
    loadAgentData().then((d) => { if (alive) { setData(d); setLoading(false); } });
    return () => { alive = false; };
  }, [enabled]);
  return { data, loading };
}
