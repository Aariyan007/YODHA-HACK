// One small global store for the guided tour / demo, so the header button, the welcome card and the Agent can all start it.
import { useSyncExternalStore } from "react";
import { TOURS } from "./tours.js";

let state = { run: null, welcome: false }; // run: { name, steps, index, auto, paused }
const subs = new Set();
const emit = () => subs.forEach((f) => f());
const set = (patch) => { state = { ...state, ...patch }; emit(); };

export const useTourState = () => useSyncExternalStore((f) => { subs.add(f); return () => subs.delete(f); }, () => state);

const KEY = "medithread_tour_done";
export const tourDone = () => { try { return localStorage.getItem(KEY) === "1"; } catch { return true; } };
const markDone = () => { try { localStorage.setItem(KEY, "1"); } catch { /* private mode */ } };

export const openWelcome = () => set({ welcome: true });
export const closeWelcome = () => { markDone(); set({ welcome: false }); };

export function startTour(name = "full", { auto = false } = {}) {
  const steps = TOURS[name];
  if (!steps) return false;
  set({ welcome: false, run: { name, steps, index: 0, auto, paused: false } });
  return true;
}
export const stopTour = () => { markDone(); set({ run: null }); };
export const goStep = (delta) => {
  const r = state.run;
  if (!r) return;
  const i = r.index + delta;
  if (i >= r.steps.length) return stopTour();
  set({ run: { ...r, index: Math.max(0, i) } });
};
export const togglePause = () => state.run && set({ run: { ...state.run, paused: !state.run.paused } });
export const setAuto = (auto) => state.run && set({ run: { ...state.run, auto, paused: false } });
