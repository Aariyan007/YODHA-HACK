// Theme control. Two themes: "glass" (deep-navy glassmorphism, default) and "light" (clinical sage).
// Applied to <html data-theme>, persisted in localStorage, set pre-paint by the inline script in index.html.
const KEY = "medithread_theme";
export const THEMES = ["light", "glass"];

export function getTheme() {
  try { return localStorage.getItem(KEY) || "light"; } catch { return "light"; }
}
export function setTheme(t) {
  document.documentElement.setAttribute("data-theme", t);
  try { localStorage.setItem(KEY, t); } catch { /* private mode */ }
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", t === "glass" ? "#0a0e1a" : "#e8f1e1");
}
export function toggleTheme() {
  const next = getTheme() === "light" ? "glass" : "light";
  setTheme(next);
  return next;
}
