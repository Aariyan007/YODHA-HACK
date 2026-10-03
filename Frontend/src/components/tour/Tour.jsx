import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { closeWelcome, goStep, openWelcome, setAuto, startTour, stopTour, togglePause, tourDone, useTourState } from "./tourStore.js";
import { getProfile } from "../../App.jsx";
import "./tour.css";

const AUTO_MS = 6500;
const PAD = 10;

function findTarget(selectors) {
  for (const s of selectors || []) {
    try {
      const el = document.querySelector(s);
      if (el) { const r = el.getBoundingClientRect(); if (r.width > 0 && r.height > 0) return el; }
    } catch { /* a bad selector must not break the tour */ }
  }
  return null;
}

// The step card and the spotlight. It goes to the right screen, finds the element and highlights it. If the element is missing the
// card is simply centred.
export function Tour() {
  const { run } = useTourState();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const [rect, setRect] = useState(null);
  const [tick, setTick] = useState(0);
  const step = run?.steps[run.index];
  const cardRef = useRef(null);
  const [nudge, setNudge] = useState(0);
  const [measured, setMeasured] = useState(0);

  // go to the screen this step is about
  useEffect(() => {
    if (!step?.route) return;
    const here = pathname.replace(/\/$/, "") || "/";
    if (here !== step.route) navigate(step.route);
  }, [step, pathname, navigate]);

  // find the element (it can show up a moment after the page changes), then keep the spotlight on it
  useLayoutEffect(() => {
    if (!step) { setRect(null); return; }
    let alive = true, tries = 0, timer;
    const locate = (fromScroll) => {
      if (!alive) return;
      const el = findTarget(step.target);
      if (el) {
        // bring it on screen unless the person is scrolling (the page may still be loading and moving things)
        if (!fromScroll) {
          const b = el.getBoundingClientRect();
          if (b.top < 0 || b.bottom > window.innerHeight) el.scrollIntoView({ block: "center", behavior: "auto" });
        }
        const r = el.getBoundingClientRect();
        setRect({ x: r.left - PAD, y: r.top - PAD, w: r.width + PAD * 2, h: r.height + PAD * 2 });
      } else if (tries++ < 20 && step.target?.length) {
        timer = setTimeout(locate, 150);
      } else setRect(null);
    };
    locate();
    const settle = setInterval(() => locate(), 500); // content that loads late shifts the page: follow it for a few seconds
    const stopSettle = setTimeout(() => clearInterval(settle), 4000);
    const onResize = () => locate();
    const onScroll = () => locate(true);
    window.addEventListener("resize", onResize);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => { alive = false; clearTimeout(timer); clearInterval(settle); clearTimeout(stopSettle); window.removeEventListener("resize", onResize); window.removeEventListener("scroll", onScroll); };
  }, [step, pathname]);

  // the demo moves on by itself
  useEffect(() => {
    if (!run?.auto || run.paused) return;
    setTick((t) => t + 1);
    const id = setTimeout(() => goStep(1), AUTO_MS);
    return () => clearTimeout(id);
  }, [run?.auto, run?.paused, run?.index]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!run) return;
    const onKey = (e) => {
      if (e.key === "Escape") stopTour();
      else if (e.key === "ArrowRight") goStep(1);
      else if (e.key === "ArrowLeft") goStep(-1);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [run]);

  useEffect(() => { if (run) cardRef.current?.focus({ preventScroll: true }); }, [run?.index]); // eslint-disable-line react-hooks/exhaustive-deps

  // the card can be taller than I guessed on some steps, so slide it up to keep its bottom edge on screen
  useLayoutEffect(() => {
    setMeasured((t) => t + 1);
    setNudge(0);
    const el = cardRef.current;
    if (!el || window.innerWidth < 640) return;
    const r = el.getBoundingClientRect();
    const over = r.bottom - (window.innerHeight - 12);
    if (over > 0) setNudge(-Math.min(over, Math.max(0, r.top - 12)));
  }, [run?.index, rect]);

  const place = useCallback(() => {
    const w = Math.min(380, window.innerWidth - 24);
    if (window.innerWidth < 640 || !rect) return { centered: true, w };
    const vw = window.innerWidth, vh = window.innerHeight, gap = 16;
    const h = cardRef.current?.offsetHeight || 300; // real card height, so it never lands on the thing it explains
    const clampL = (x) => Math.min(Math.max(12, x), vw - w - 12);
    const clampT = (y) => Math.min(Math.max(12, y), vh - h - 12);
    if (rect.y + rect.h + gap + h <= vh - 12) return { left: clampL(rect.x), top: rect.y + rect.h + gap, w };
    if (rect.y - gap - h >= 12) return { left: clampL(rect.x), top: rect.y - gap - h, w };
    if (rect.x + rect.w + gap + w <= vw - 12) return { left: rect.x + rect.w + gap, top: clampT(rect.y), w };
    if (rect.x - gap - w >= 12) return { left: rect.x - gap - w, top: clampT(rect.y), w };
    return { left: clampL(vw - w - 24), top: clampT(12), w }; // target fills the screen: park the card at the top edge
  }, [rect, measured]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!run || !step) return null;
  const p = place();
  const last = run.index === run.steps.length - 1;
  const style = p.centered
    ? (window.innerWidth < 640 ? { left: 12, right: 12, bottom: 12, width: "auto" } : { left: "50%", top: "50%", transform: "translate(-50%, -50%)", width: p.w })
    : { left: p.left, top: p.top, width: p.w, ...(nudge ? { transform: `translateY(${nudge}px)` } : {}) };
  return (
    <div className="mt-tour" aria-live="polite">
      {rect && <div className="mt-tour-spot" style={{ left: rect.x, top: rect.y, width: rect.w, height: rect.h }} aria-hidden="true" />}
      {!rect && <div className="mt-tour-dim" aria-hidden="true" />}
      <div className="mt-tour-card" ref={cardRef} tabIndex={-1} role="dialog" aria-label={step.title} style={style}>
        <div className="mt-tour-top">
          <span>{run.auto ? "Demo" : "Tour"} · {run.index + 1} of {run.steps.length}</span>
          <button type="button" className="mt-tour-skip" onClick={stopTour}>Skip</button>
        </div>
        <h3>{step.title}</h3>
        <p>{step.text}</p>
        {run.auto && !run.paused && <div className="mt-tour-bar"><i key={`${run.index}-${tick}`} style={{ animationDuration: `${AUTO_MS}ms` }} /></div>}
        <div className="mt-tour-actions">
          <button type="button" className="mt-btn secondary sm" onClick={() => goStep(-1)} disabled={run.index === 0}>Back</button>
          {run.auto && <button type="button" className="mt-btn secondary sm" onClick={togglePause}>{run.paused ? "Play" : "Pause"}</button>}
          <button type="button" className="mt-btn sm" onClick={() => (last ? stopTour() : goStep(1))}>{last ? "Done" : "Next"}</button>
        </div>
        {run.auto && <button type="button" className="mt-tour-link" onClick={() => setAuto(false)}>Take control</button>}
      </div>
    </div>
  );
}

// Offered once to a new account, and any time from the header "Tour" button.
export function TourWelcome() {
  const { welcome, run } = useTourState();
  const name = (getProfile()?.role === "doctor") ? "doctor" : "full";
  useEffect(() => {
    // first visit on this browser: offer it once (never forced, never while a tour is running)
    const id = setTimeout(() => { if (!tourDone() && !sessionStorage.getItem("medithread_tour_offered")) { sessionStorage.setItem("medithread_tour_offered", "1"); openWelcome(); } }, 4800); // after the start-up screen
    return () => clearTimeout(id);
  }, []);
  useEffect(() => {
    if (!welcome) return;
    const onKey = (e) => { if (e.key === "Escape") closeWelcome(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [welcome]);
  if (!welcome || run) return null;
  return (
    <div className="mt-tour-welcome" role="presentation" onMouseDown={(e) => { if (e.target === e.currentTarget) closeWelcome(); }}>
      <div className="mt-tour-wbox" role="dialog" aria-modal="true" aria-label="Welcome to MediThread">
        <h2>New to MediThread?</h2>
        <p>See how it works in about a minute. You can also ask the assistant "how do I…" at any time, and it will show you or do it for you.</p>
        <div className="mt-tour-wacts">
          <button type="button" className="mt-btn" onClick={() => startTour(name)}>Take the guided tour</button>
          <button type="button" className="mt-btn secondary" onClick={() => startTour(name, { auto: true })}>Play the demo</button>
          <button type="button" className="mt-tour-link" onClick={closeWelcome}>Not now</button>
        </div>
      </div>
    </div>
  );
}

export function TourButton() {
  return <button type="button" className="mt-tour-btn" onClick={openWelcome} aria-label="How to use MediThread: tour and demo">Tour</button>;
}
