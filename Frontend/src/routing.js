// The offline build (`npm run build:single`) runs from file:// with hash routes.
// These helpers keep links, QR codes and redirects right in both modes.
export const SINGLE = import.meta.env.VITE_SINGLE === "true";

// Absolute href for a plain <a>.
export const appPath = (path) => (SINGLE ? `#${path}` : path);

// Full URL, e.g. for a QR code.
export const appUrl = (path) =>
  SINGLE ? `${window.location.href.split("#")[0]}#${path}` : `${window.location.origin}${path}`;

export const goLogin = () => {
  if (SINGLE) window.location.hash = "#/login";
  else window.location.assign("/login");
};
