import { Suspense, lazy, useCallback, useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import AgentLauncher from "./AgentLauncher.jsx";
import { contextFor } from "./agentContext.js";
import "./agent.css";

// Mounted once by each layout, so it stays while the page underneath changes.
// Only the launcher is in the main bundle's render path, the panel loads the first time it's opened.
const AgentPanel = lazy(() => import("./AgentPanel.jsx"));
const PANEL_ID = "mt-agent-panel";

export default function MediThreadAgent() {
  const { pathname } = useLocation();
  const ctx = contextFor(pathname);
  const [open, setOpen] = useState(false);
  const [mounted, setMounted] = useState(false);
  const launcher = useRef(null);

  const close = useCallback(() => { setOpen(false); launcher.current?.focus({ preventScroll: true }); }, []);
  const toggle = () => { if (open) close(); else { setMounted(true); setOpen(true); } };

  useEffect(() => {
    if (!open) return;
    const onKey = (e) => { if (e.key === "Escape") { e.stopPropagation(); close(); } };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, close]);

  return (
    <div className="ag-root">
      <AgentLauncher ref={launcher} open={open} onClick={toggle} controls={mounted ? PANEL_ID : undefined} />
      {mounted && (
        <Suspense fallback={null}>
          <AgentPanel id={PANEL_ID} open={open} ctx={ctx} onClose={close} onExited={() => setMounted(false)} />
        </Suspense>
      )}
    </div>
  );
}
