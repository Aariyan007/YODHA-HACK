import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { sendAudio, sendLine } from "../../api/client.js";
import { FlagList } from "./FlagBanner.jsx";
import { useSpeechRecognition } from "./useSpeechRecognition.js";
import { useWhisperRecorder } from "./useWhisperRecorder.js";

/**
 * State 2 — Recording.
 *
 * Owns:
 * - The live transcript, including the current interim result (grey italics).
 * - The current speaker ("doctor" | "patient"), toggleable via buttons or D/P keys.
 * - A queue that serialises sendLine calls so the backend receives lines in
 *   the order they were spoken, even if some requests take longer than others.
 * - Retry on failure: a failing line is marked "Not saved, retrying" and the
 *   queue keeps re-posting it until it succeeds. We never lose a line.
 */
export function RecordingPanel({
  consultationId,
  shareToken,
  initialState,
  autoFeed,
  onStop,
}) {
  const [state, setState] = useState(() => ({
    transcript: initialState?.transcript || [],
    flags: initialState?.flags || [],
    suggestions: initialState?.suggestions || [],
    partial_note: initialState?.partial_note || { subjective: null, objective: null, assessment: null, plan: null },
  }));
  const [speaker, setSpeaker] = useState("doctor");
  const [typed, setTyped] = useState("");
  const [queueStatus, setQueueStatus] = useState("idle"); // idle | sending | retrying
  const [startedAt] = useState(() => Date.now());
  const [elapsed, setElapsed] = useState(0);
  const [micError, setMicError] = useState(null);
  const [engine, setEngine] = useState("whisper"); // "whisper" (server) | "browser" (fallback)
  const [engineNote, setEngineNote] = useState(null);
  const [language, setLanguage] = useState(""); // "" = auto-detect, "en", "ml"
  const [stopping, setStopping] = useState(false);

  // Always-current copies for async callbacks (a clip finishes seconds after it was spoken).
  const stateRef = useRef(state);
  const commit = useCallback((next) => { stateRef.current = next; setState(next); }, []);
  const speakerRef = useRef(speaker);
  speakerRef.current = speaker;
  const engineRef = useRef(engine);
  engineRef.current = engine;

  // ---- queue (serial) ----
  // A tiny FIFO that posts one line at a time. If a POST fails, the queue
  // retries that line (with exponential-ish backoff capped at 4s) forever
  // until the user clicks Stop. The caller sees the line immediately in
  // the local transcript — the server round-trip is only used to update
  // flags / suggestions / partial note.
  const queueRef = useRef([]);
  const sendingRef = useRef(false);

  const pump = useCallback(async () => {
    if (sendingRef.current) return;
    const next = queueRef.current[0];
    if (!next) { setQueueStatus("idle"); return; }
    sendingRef.current = true;
    setQueueStatus(next.attempt > 0 ? "retrying" : "sending");
    try {
      const res = await sendLine(consultationId, next.text, next.speaker, shareToken);
      // Replace the local transcript with the server's authoritative version
      // (same shape as our local optimistic append), then update derived state.
      commit({
        transcript: res.transcript || [],
        flags: res.flags || [],
        suggestions: res.suggestions || [],
        partial_note: res.partial_note || stateRef.current.partial_note,
      });
      queueRef.current.shift();
      sendingRef.current = false;
      // Immediately pump the next one.
      pump();
    } catch (e) {
      sendingRef.current = false;
      next.attempt = (next.attempt || 0) + 1;
      setQueueStatus("retrying");
      const wait = Math.min(500 * 2 ** (next.attempt - 1), 4000);
      setTimeout(pump, wait);
    }
  }, [consultationId, shareToken, commit]);

  const enqueue = useCallback((text, who) => {
    const line = { text, speaker: who, attempt: 0 };
    queueRef.current.push(line);
    // Optimistic local append so the UI shows the line instantly.
    commit({ ...stateRef.current, transcript: [...stateRef.current.transcript, { speaker: who, text }] });
    pump();
  }, [pump, commit]);

  // ---- speech ----
  // Primary: Whisper on the server (accurate on accents, drug names, Malayalam). The browser engine keeps
  // running only as a live caption while Whisper works, and becomes the engine if Whisper is unavailable.
  const wr = useWhisperRecorder({
    getSpeaker: () => speakerRef.current,
    onClip: async (blob, who) => {
      const res = await sendAudio(consultationId, blob, who, language || undefined, shareToken);
      if (res.added) {
        commit({
          transcript: res.transcript || [],
          flags: res.flags || [],
          suggestions: res.suggestions || [],
          partial_note: res.partial_note || stateRef.current.partial_note,
        });
      }
    },
    onUnavailable: (msg) => {
      setEngine("browser");
      setEngineNote(`${msg} Using browser voice typing instead.`);
    },
  });
  const sr = useSpeechRecognition({
    onFinal: (text) => { if (engineRef.current === "browser") enqueue(text, speakerRef.current); },
    lang: language === "ml" ? "ml-IN" : "en-IN",
  });

  const whisperOn = engine === "whisper" && wr.supported;
  const micOn = whisperOn ? wr.listening : sr.listening;
  const micSupported = whisperOn || sr.supported;
  const micStart = () => { if (whisperOn) wr.start(); if (sr.supported) sr.start(); };
  const micStop = () => { wr.stop(); sr.stop(); };

  // Start listening as soon as the visit starts (not for the scripted demo).
  useEffect(() => {
    if (autoFeed && autoFeed.length) return;
    if (wr.supported && engineRef.current === "whisper") wr.start();
    if (sr.supported) sr.start();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const err = whisperOn ? wr.error : sr.error;
    if (err === "not-allowed" || err === "service-not-allowed") {
      setMicError("Microphone access was blocked. Allow it in your browser, or type lines below.");
    } else if (err === "no-mic") {
      setMicError("No microphone was found. Plug one in, or type lines below.");
    } else if (err === "unsupported" || !err) {
      setMicError(null);
    } else {
      setMicError(`Voice typing hiccuped (${err}). It will retry automatically.`);
    }
  }, [wr.error, sr.error, whisperOn]);

  // ---- D / P keyboard shortcuts ----
  useEffect(() => {
    const onKey = (e) => {
      if (e.target && ["INPUT", "TEXTAREA"].includes(e.target.tagName)) return;
      if (e.key === "d" || e.key === "D") { setSpeaker("doctor"); e.preventDefault(); }
      if (e.key === "p" || e.key === "P") { setSpeaker("patient"); e.preventDefault(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // ---- timer ----
  useEffect(() => {
    const t = setInterval(() => setElapsed(Math.floor((Date.now() - startedAt) / 1000)), 1000);
    return () => clearInterval(t);
  }, [startedAt]);

  // ---- auto-feed (demo conversation) ----
  // feedIdx survives effect re-runs (React StrictMode mounts effects twice in dev, and a cleanup that
  // killed the timer used to leave the demo stuck). enqueueRef avoids restarting when enqueue changes.
  const feedIdx = useRef(0);
  const enqueueRef = useRef(enqueue);
  enqueueRef.current = enqueue;
  useEffect(() => {
    if (!autoFeed || !autoFeed.length) return;
    let timer;
    const tick = () => {
      if (feedIdx.current >= autoFeed.length) return;
      const [who, text] = autoFeed[feedIdx.current++];
      enqueueRef.current(text, who);
      timer = setTimeout(tick, 650);
    };
    timer = setTimeout(tick, feedIdx.current ? 0 : 300);
    return () => clearTimeout(timer);
  }, [autoFeed]);

  const sendTyped = () => {
    const text = typed.trim();
    if (!text) return;
    enqueue(text, speaker);
    setTyped("");
  };

  const handleStop = async () => {
    if (stopping) return;
    setStopping(true);
    sr.stop();
    await wr.flush(); // finish transcribing the sentence in progress before reviewing
    onStop(stateRef.current);
  };

  const mmss = useMemo(() => {
    const m = String(Math.floor(elapsed / 60)).padStart(2, "0");
    const s = String(elapsed % 60).padStart(2, "0");
    return `${m}:${s}`;
  }, [elapsed]);

  return (
    <div className="console-record">
      {/* Status strip */}
      <div className="console-record-top">
        <div className="row" style={{ gap: 10, alignItems: "center" }}>
          <span className={`rec-dot ${micOn ? "live" : ""}`} aria-hidden="true" />
          <span aria-live="polite">
            {!micSupported ? "Voice typing unavailable"
              : !micOn ? "Paused"
              : wr.speaking && whisperOn ? "Hearing you…"
              : whisperOn && wr.pending > 0 ? "Transcribing…"
              : "Listening"}
            {" · "}
            <span className="muted">{mmss}</span>
            {whisperOn && micOn && <span className="muted small"> · Whisper</span>}
          </span>
        </div>
        <div className="row" style={{ gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          {micSupported && (
            <select value={language} onChange={(e) => setLanguage(e.target.value)} aria-label="Spoken language" style={{ minWidth: 0 }}>
              <option value="">Auto language</option>
              <option value="en">English</option>
              <option value="ml">Malayalam</option>
            </select>
          )}
          {micSupported && !micOn && <button onClick={micStart}>Resume mic</button>}
          {micSupported && micOn && <button onClick={micStop}>Pause mic</button>}
          <button className="primary" onClick={handleStop} disabled={stopping}>
            {stopping ? "Finishing…" : "Stop and review"}
          </button>
        </div>
      </div>

      {micError && <div className="card error" style={{ marginBottom: 12 }}>{micError}</div>}
      {engineNote && <div className="card" style={{ marginBottom: 12, background: "var(--accent-soft)" }}>{engineNote}</div>}
      {!micSupported && (
        <div className="card" style={{ marginBottom: 12, background: "var(--accent-soft)" }}>
          <strong>Voice typing works in Chrome, Edge and Safari.</strong>{" "}
          Use the demo conversation, or type lines below.
        </div>
      )}

      <FlagList flags={state.flags} />

      <div className="console-record-grid">
        {/* Transcript */}
        <section className="card">
          <div className="row between" style={{ alignItems: "center", marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>Transcript</h3>
            <div role="group" aria-label="Current speaker" className="speaker-toggle">
              <button
                className={speaker === "doctor" ? "primary small" : "small"}
                aria-pressed={speaker === "doctor"}
                onClick={() => setSpeaker("doctor")}
              >
                Doctor speaking (D)
              </button>
              <button
                className={speaker === "patient" ? "primary small" : "small"}
                aria-pressed={speaker === "patient"}
                onClick={() => setSpeaker("patient")}
              >
                Patient speaking (P)
              </button>
            </div>
          </div>
          <ul className="console-transcript" aria-live="polite">
            {state.transcript.map((ln, i) => (
              <li key={i} className={`t-line t-${ln.speaker}`}>
                <span className="t-stamp">{ln.speaker}</span>
                <span className="t-text">
                  {ln.text}
                  {ln.fixes?.length > 0 && (
                    <span className="t-fix" title="Medicine name corrected after speech-to-text. Check it is right.">
                      {" "}✎ {ln.fixes.map((f) => `${f.from} → ${f.to}`).join(", ")}
                    </span>
                  )}
                </span>
              </li>
            ))}
            {sr.interim && (
              <li className={`t-line t-${speaker} t-interim`}>
                <span className="t-stamp">{speaker}</span>
                <span className="t-text">{sr.interim}…</span>
              </li>
            )}
            {state.transcript.length === 0 && !sr.interim && (
              <li className="muted small">The transcript will appear here as the visit begins.</li>
            )}
          </ul>

          {queueStatus === "retrying" && (
            <div className="small" style={{ color: "var(--watch)" }}>
              Not saved, retrying…
            </div>
          )}

          <div className="row" style={{ gap: 6, marginTop: 10 }}>
            <input
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && sendTyped()}
              placeholder={`Type a ${speaker} line and press Enter`}
              aria-label={`Type a ${speaker} line`}
            />
            <button onClick={sendTyped} disabled={!typed.trim()}>Send</button>
          </div>
        </section>

        {/* Live SOAP */}
        <section className="card">
          <h3 style={{ marginTop: 0 }}>Live SOAP</h3>
          <SoapField label="S — Subjective" value={state.partial_note?.subjective} />
          <SoapField label="O — Objective"  value={state.partial_note?.objective} />
          <SoapField label="A — Assessment" value={state.partial_note?.assessment}
                     hint="AI restates only what the doctor says." />
          <SoapField label="P — Plan"       value={state.partial_note?.plan} />
        </section>
      </div>

      {/* Consider asking */}
      <section className="card">
        <h3 style={{ marginTop: 0 }}>Consider asking</h3>
        {state.suggestions?.length ? (
          <ul className="console-suggestions">
            {state.suggestions.map((q, i) => <li key={i}>{q}</li>)}
          </ul>
        ) : (
          <p className="muted small">
            Suggestions appear every few lines. They are prompts, not instructions — the doctor decides what to ask.
          </p>
        )}
      </section>
    </div>
  );
}

function SoapField({ label, value, hint }) {
  return (
    <div className="soap-field">
      <div className="soap-label">{label}</div>
      <div className={`soap-value ${value ? "" : "empty"}`}>
        {value || "Not mentioned yet"}
      </div>
      {hint && <div className="muted small" style={{ marginTop: 2 }}>{hint}</div>}
    </div>
  );
}
