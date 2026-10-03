// The patient the doctor is working with right now (set by the console page once it has loaded the record).
// The Agent uses it, and the server still checks the doctor's care link on every request.
import { useSyncExternalStore } from "react";

let current = null;
const subs = new Set();
export const setAgentPatient = (p) => { current = p; subs.forEach((f) => f()); };
export const useAgentPatient = () => useSyncExternalStore((f) => { subs.add(f); return () => subs.delete(f); }, () => current);
