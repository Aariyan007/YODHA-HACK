import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { gsap } from "gsap";
import { reducedMotion } from "../../anim.js";
import { factsFor } from "./agentContext.js";
import { loadAgentData, useAgentData } from "./agentData.js";
import { DOCTOR_ASK, intentFor, runAction } from "./agentActions.js";
import { apiFor } from "./agentApi.js";
import { useAgentPatient } from "./agentPatient.js";
import { resultFromResponse } from "./agentBlocks.js";
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
  const submitRef = useRef(() => {});
  const conv = useRef(null);
  const fileId = useRef(null); // the file the person last gave the agent
  const [view, setView] = useState({ kind: "home" });
  const { data, loading } = useAgentData(!ctx.doctor);
  const dp = useAgentPatient();
  const api = apiFor(ctx, dp?.id);

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
    if (ctx.doctor) return submitRef.current(DOCTOR_ASK[actionId] || label);
    setView({ kind: "processing", label });
    const started = Date.now();
    let result;
    try { result = await runAction(actionId, data || (await loadAgentData())); }
    catch { result = { title: "That did not work", lead: "Something went wrong reading your records.", note: "Try again in a moment." }; }
    const wait = Math.max(0, 1100 - (Date.now() - started)); // long enough to see the thread being worked through
    setTimeout(() => { if (alive.current) setView({ kind: "result", result }); }, wait);
  }, [data]);

  const noPatient = () => setView({ kind: "result", result: { title: "Open a patient first", lead: "The doctor agent works on one linked patient at a time.", note: "Open a patient's record, then ask again." } });

  const localAnswer = (text) => {
    const actionId = intentFor(text);
    if (actionId) return run(actionId, text);
    setView({
      kind: "result",
      result: { title: "I can't do that yet", lead: "I can work on these from this page.", note: "I did not understand that request.", suggestions: ctx.actions },
    });
  };

  // Typed requests go to the Agent Engine on the server (planner -> permitted tools -> verified result).
  // The offline build and doctor pages have no patient engine, so they keep the local actions.
  const submit = async (text) => {
    if (!api.ready) return ctx.doctor ? noPatient() : localAnswer(text);
    setView({ kind: "processing", label: text });
    const started = Date.now();
    let result;
    try {
      let r = await api.chat(text, conv.current, fileId.current);
      conv.current = r.conversationId || conv.current;
      // A slow job (reading a file) runs on the server as a task; follow its steps until it settles.
      for (let n = 0; r.status === "running" && n < 90 && alive.current; n++) {
        await new Promise((ok) => setTimeout(ok, 1000));
        const t = await api.task(r.taskId);
        const cur = t.steps.find((x) => x.status === "running") || t.steps.find((x) => x.status === "queued");
        if (cur) setView({ kind: "processing", label: cur.label });
        if (t.status !== "running" && t.status !== "queued") r = { ...t.result, status: t.status, intent: t.intent, taskId: t.taskId, steps: t.steps };
      }
      if (r.status === "running") throw new Error("That is taking longer than expected. Check back in a moment.");
      result = resultFromResponse(r);
    } catch (e) {
      result = { title: "That did not work", lead: e?.message && e.message.length < 140 ? e.message : "I could not reach the assistant.", note: "Try again in a moment." };
    }
    const wait = Math.max(0, 700 - (Date.now() - started));
    setTimeout(() => {
      if (!alive.current) return;
      setView({ kind: "result", result });
      if (result.navigate) go(result.navigate); // a navigation request really navigates
    }, wait);
  };

  const typeLabel = { lab: "lab report", prescription: "prescription", visit: "visit or discharge note", scan: "scan report" };
  const fileResult = (f) => {
    fileId.current = f.fileId;
    const kind = f.type && typeLabel[f.type];
    return {
      title: f.duplicate ? "You already gave me this file" : "File received",
      lead: `${f.name} is stored privately and encrypted.`,
      items: [{ label: "Looks like", value: kind || "I am not sure yet", sub: f.needsType ? f.reason || "Tell me what it is and I will go on." : undefined, tone: kind ? "good" : "watch" }],
      note: "Nothing was added to your health thread. I will ask before I save anything.",
      typeChoices: f.needsType && api.setType ? Object.entries(typeLabel).map(([id, title]) => ({ id, title })) : undefined,
    };
  };

  const attach = async (file) => {
    setView({ kind: "processing", label: `Reading ${file.name}` });
    let result;
    try { result = fileResult(await api.upload(file)); }
    catch (e) { result = { title: "I could not take that file", lead: e?.message && e.message.length < 160 ? e.message : "The upload failed.", note: "Try a PDF, JPG, PNG or WEBP under 10 MB." }; }
    if (alive.current) setView({ kind: "result", result });
  };

  // The person's answer to "Save this to your health thread?". Nothing was written before this.
  const answer = async (confirmationId, approve) => {
    setView({ kind: "processing", label: approve ? "Saving" : "Cancelling" });
    let result;
    try { result = resultFromResponse(await api.confirm(confirmationId, approve)); }
    catch (e) { result = { title: "That did not work", lead: e?.message && e.message.length < 140 ? e.message : "I could not finish that.", note: "Nothing was saved." }; }
    if (alive.current) setView({ kind: "result", result });
  };

  const download = async (f) => {
    try { await api.download(f); }
    catch (e) { setView({ kind: "result", result: { title: "I could not download that", lead: e?.message || "The download failed.", note: "Ask me to make it again." } }); }
  };

  const chooseType = async (type) => {
    try { setView({ kind: "result", result: fileResult(await api.setType(fileId.current, type)) }); }
    catch { setView({ kind: "result", result: { title: "That did not work", lead: "I could not save your answer.", note: "Try again." } }); }
  };

  submitRef.current = submit;

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
          <AgentResult result={view.result} onBack={() => setView({ kind: "home" })} onGo={go} ctxActions={ctx.actions} onRun={run} onType={chooseType} onAnswer={answer} onDownload={download} />
        )}
      </div>
      <AgentInput onSubmit={submit} onFile={api.ready ? attach : undefined} disabled={busy} />
    </div>
  );
}
