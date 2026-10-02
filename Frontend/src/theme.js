// MediThread has one look: the sage palette on a pale ground. (An earlier dark "glass" theme was retired.)
// The attribute is still set so any legacy CSS keyed on [data-theme] resolves to the light/default branch.
const KEY = "medithread_theme";

export function getTheme() { return "light"; }
export function setTheme() {
  document.documentElement.setAttribute("data-theme", "light");
  try { localStorage.setItem(KEY, "light"); } catch { /* private mode */ }
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", "#e6f2dd");
}
export const toggleTheme = () => "light";
