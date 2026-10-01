import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { viteSingleFile } from "vite-plugin-singlefile";

// `npm run build:single` (mode "single") makes dist-single/index.html: one file that runs from file://
// with no backend. It is pinned to mock data (VITE_USE_MOCK=true) and uses hash routes, because a
// file:// page cannot reach /api and has no server to answer deep links.
export default defineConfig(({ mode }) => {
  const single = mode === "single";
  return {
    plugins: [react(), ...(single ? [viteSingleFile()] : [])],
    envDir: "..", // shared .env in the repo root
    ...(single && {
      base: "./",
      define: {
        "import.meta.env.VITE_USE_MOCK": JSON.stringify("true"),
        "import.meta.env.VITE_SINGLE": JSON.stringify("true"),
      },
      build: { outDir: "dist-single", emptyOutDir: true },
    }),
    server: {
      port: 5173,
      proxy: { "/api": "http://localhost:8000" },
    },
  };
});
