import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { gsap } from "gsap";
import { reducedMotion } from "../../anim.js";
import { factsFor } from "./agentContext.js";
import { loadAgentData, useAgentData } from "./agentData.js";
import { intentFor, runAction } from "./agentActions.js";
import AgentHeader from "./AgentHeader.jsx";
import AgentContext from "./AgentContext.jsx";
import { AgentActionList } from "./AgentAction.jsx";
import AgentInput from "./AgentInput.jsx";
import AgentProcessing from "./AgentProcessing.jsx";
import AgentResult from "./AgentResult.jsx";

// The expanded Agent: a small workspace that grows out of the launcher's corner.
export default function AgentPanel({ open, ctx, onClose, onExited, id }) {
  const navigate = useNavigate();
  const ref = useRef(null);
  const alive = useRef(true);
  const [view, setView] = useState({ kind: "home" });
  const { data, loading } = useAgentData(!ctx.doctor);

  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);

  // Moving to another page while open: the agent stays, its context updates, and any old result is cleared.
  useEffect(() => { setView({ kind: "home" }); }, [ctx.id]);

  // Open and close. Transform and opacity only, from the bottom-right corner where the launcher sits.
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const parts = el.querySelectorAll("[data-a]");
    if (reducedMotion()) { gsap.set(el, { opacity: open ? 1 : 0 }); if (!open) onExited?.(); return; }
    if (open) {
      gsap.fromTo(el, { opacity: 0, scale: 0.94, y: 14, transformOrigin: "100% 100%" }, { opacity: 1, scale: 1, y: 0, duration: 0.34, ease: "power3.out" });
      gsap.fromTo(parts, { opacity: 0, y: 10 }, { opacity: 1, y: 0, duration: 0.3, stagger: 0.05, delay: 0.1, ease: "power2.out", clearProps: "transform,opacity" });
      const t = setTimeout(() => el.querySelector("[data-first]")?.focus({ preventScroll: true }), 120);
      return () => clearTimeout(t);
    }
    const tw = gsap.to(el, { opacity: 0, scale: 0.96, y: 10, duration: 0.2, ease: "power2.in", transformOrigin: "100% 100%", onComplete: () => onExited?.() });
    return () => tw.kill();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const go = (to) => { onClose(); navigate(to); };

  const run = useCallback(async (actionId, label) => {
    setView({ kind: "processing", label });
    const started = Date.now();
    let result;
    try { result = await runAction(actionId, data || (await loadAgentData())); }
    catch { result = { title: "That did not work", lead: "Something went wrong reading your records.", note: "Try again in a moment." }; }
    const wait = Math.max(0, 1100 - (Date.now() - started)); // long enough to see the thread being worked through
    setTimeout(() => { if (alive.current) setView({ kind: "result", result }); }, wait);
  }, [data]);

  const submit = (text) => {
    const actionId = intentFor(text);
    if (actionId) return run(actionId, text);
    setView({
      kind: "result",
      result: { title: "I can't do that yet", lead: "In this preview I can work on these from this page.", note: "Typed requests are matched to a fixed set of actions. No model reads them.", suggestions: ctx.actions },
    });
  };

  const facts = factsFor(ctx, data);
  const busy = view.kind === "processing";

  return (
    <div ref={ref} id={id} className="ag-panel" role="dialog" aria-modal="false" aria-label="MediThread Agent" aria-describedby={`${id}-ctx`}>
      <AgentHeader ctx={ctx} onClose={onClose} />
      <div className="ag-body" id={`${id}-ctx`}>
        <AgentContext ctx={ctx} facts={facts} loading={loading} />
        {view.kind === "home" && <AgentActionList actions={ctx.actions} onRun={run} />}
        {view.kind === "processing" && <AgentProcessing label={view.label} />}
        {view.kind === "result" && (
          <AgentResult result={view.result} onBack={() => setView({ kind: "home" })} onGo={go} ctxActions={ctx.actions} onRun={run} />
        )}
      </div>
      <AgentInput onSubmit={submit} disabled={busy} />
    </div>
  );
}
