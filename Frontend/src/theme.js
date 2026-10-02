// Theme control. Two themes: "glass" (deep-navy glassmorphism, default) and "light" (clinical sage).
// Applied to <html data-theme>, persisted in localStorage, set pre-paint by the inline script in index.html.
const KEY = "medithread_theme";
export const THEMES = ["glass", "light"];

export function getTheme() {
  try { return localStorage.getItem(KEY) || "glass"; } catch { return "glass"; }
}
export function setTheme(t) {
  document.documentElement.setAttribute("data-theme", t);
  try { localStorage.setItem(KEY, t); } catch { /* private mode */ }
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", t === "light" ? "#e9edea" : "#0a0e1a");
}
export function toggleTheme() {
  const next = getTheme() === "glass" ? "light" : "glass";
  setTheme(next);
  return next;
}
