import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Records the microphone and hands back sentence-sized audio clips for server-side Whisper.
 *
 * Why not the browser's own speech recognition: it is weak on Indian accents, drug names and
 * Malayalam. Whisper is much better, but needs audio clips. So:
 *
 * - One MediaRecorder always runs on a single mic stream.
 * - A small voice-activity detector (RMS level vs. an adaptive noise floor) watches the stream.
 * - When the speaker pauses (~0.9 s) after speaking, the current clip is cut and a new recorder starts
 *   immediately on the same stream, so the next sentence never loses its first word.
 * - Clips with no real speech are thrown away and never uploaded (silence is what makes Whisper invent text).
 * - Clips are uploaded strictly in order, so transcript lines keep the order they were spoken.
 *
 * onClip(blob, speakerAtStart) must return a promise; it is retried on network errors.
 * If it rejects with err.unavailable === true, the hook stops and calls onUnavailable(message) so the
 * caller can fall back to browser speech recognition.
 */

const PAUSE_MS = 900;        // silence after speech that ends a clip
const MAX_CLIP_MS = 14000;   // hard cap so one clip is never huge
const IDLE_CUT_MS = 6000;    // a clip with no speech at all is discarded after this long
const MIN_SPEECH_MS = 300;   // less speech than this is a cough / click, not a sentence
const TICK_MS = 80;

function pickMime() {
  if (typeof MediaRecorder === "undefined") return null;
  for (const m of ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"]) {
    if (MediaRecorder.isTypeSupported?.(m)) return m;
  }
  return "";
}

export function useWhisperRecorder({ onClip, onUnavailable, getSpeaker } = {}) {
  const mime = pickMime();
  const supported = typeof navigator !== "undefined" && !!navigator.mediaDevices?.getUserMedia && mime !== null;

  const [listening, setListening] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [pending, setPending] = useState(0);
  const [error, setError] = useState(null);

  const onClipRef = useRef(onClip);
  onClipRef.current = onClip;
  const onUnavailRef = useRef(onUnavailable);
  onUnavailRef.current = onUnavailable;
  const getSpeakerRef = useRef(getSpeaker);
  getSpeakerRef.current = getSpeaker;

  const mounted = useRef(true);
  const s = useRef({
    starting: false,
    stream: null, ctx: null, analyser: null, buf: null, timer: null,
    rec: null, chunks: [], segStart: 0, speechMs: 0, lastVoiceAt: 0, speakerAtStart: null,
    noise: 0.01, running: false, speakingNow: false, chain: Promise.resolve(), dead: false,
  });

  const upload = useCallback((blob, speaker) => {
    const st = s.current;
    setPending((n) => n + 1);
    // Strict order: each upload waits for the previous one.
    st.chain = st.chain.then(async () => {
      if (st.dead) return;
      for (let attempt = 0; attempt < 3; attempt++) {
        try {
          await onClipRef.current(blob, speaker);
          return;
        } catch (e) {
          if (e?.unavailable) {
            st.dead = true;
            stopAll();
            onUnavailRef.current?.(e.message);
            return;
          }
          if (e?.skip) return; // a clip the server could not read; do not retry it
          await new Promise((r) => setTimeout(r, 600 * (attempt + 1)));
        }
      }
    }).finally(() => setPending((n) => Math.max(0, n - 1)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const startRecorder = useCallback(() => {
    const st = s.current;
    if (!st.stream) return;
    const rec = new MediaRecorder(st.stream, mime ? { mimeType: mime } : undefined);
    st.chunks = [];
    st.segStart = performance.now();
    st.speechMs = 0;
    st.speakerAtStart = null;
    rec.ondataavailable = (e) => { if (e.data && e.data.size) st.chunks.push(e.data); };
    st.rec = rec;
    rec.start();
  }, [mime]);

  const cut = useCallback((keep) => {
    const st = s.current;
    const rec = st.rec;
    if (!rec || rec.state === "inactive") return;
    const chunks = st.chunks;
    const speaker = st.speakerAtStart || getSpeakerRef.current?.() || "unknown";
    rec.onstop = () => {
      if (!keep || !chunks.length) return;
      const blob = new Blob(chunks, { type: rec.mimeType || mime || "audio/webm" });
      if (blob.size > 800) upload(blob, speaker);
    };
    // Start the next clip before the old one finishes stopping, so no audio is lost between them.
    if (st.running) startRecorder();
    rec.stop();
  }, [mime, startRecorder, upload]);

  const tick = useCallback(() => {
    const st = s.current;
    if (!st.running || !st.analyser) return;
    st.analyser.getFloatTimeDomainData(st.buf);
    let sum = 0;
    for (let i = 0; i < st.buf.length; i++) sum += st.buf[i] * st.buf[i];
    const rms = Math.sqrt(sum / st.buf.length);
    const now = performance.now();

    const voiced = rms > Math.max(0.018, st.noise * 3.2);
    if (!voiced) st.noise = st.noise * 0.96 + rms * 0.04; // learn the room's noise floor from quiet moments
    if (voiced) {
      if (!st.speakerAtStart) st.speakerAtStart = getSpeakerRef.current?.() || "unknown";
      st.speechMs += TICK_MS;
      st.lastVoiceAt = now;
    }
    if (voiced !== st.speakingNow) {
      st.speakingNow = voiced;
      setSpeaking(voiced);
    }

    const age = now - st.segStart;
    const hadSpeech = st.speechMs >= MIN_SPEECH_MS;
    if (hadSpeech && now - st.lastVoiceAt >= PAUSE_MS) cut(true);
    else if (age >= MAX_CLIP_MS && hadSpeech) cut(true);
    else if (!hadSpeech && age >= IDLE_CUT_MS) cut(false);
  }, [cut]);

  // Returns a promise that resolves once the sentence in progress has been queued for upload.
  const stopAll = useCallback(() => {
    const st = s.current;
    st.running = false;
    clearInterval(st.timer);
    st.timer = null;
    let queued = Promise.resolve();
    try {
      if (st.rec && st.rec.state !== "inactive") {
        const rec = st.rec;
        const chunks = st.chunks;
        const speaker = st.speakerAtStart || getSpeakerRef.current?.() || "unknown";
        const had = st.speechMs >= MIN_SPEECH_MS;
        queued = new Promise((resolve) => {
          rec.onstop = () => {
            if (had && chunks.length) {
              const blob = new Blob(chunks, { type: rec.mimeType || mime || "audio/webm" });
              if (blob.size > 800) upload(blob, speaker);
            }
            resolve();
          };
        });
        rec.stop(); // flush the sentence in progress instead of dropping it
      }
    } catch { /* already stopped */ }
    st.rec = null;
    st.stream?.getTracks().forEach((t) => t.stop());
    st.stream = null;
    try { st.ctx?.close(); } catch { /* ignore */ }
    st.ctx = null;
    st.analyser = null;
    st.speakingNow = false;
    setSpeaking(false);
    setListening(false);
    return queued;
  }, [mime, upload]);

  const start = useCallback(async () => {
    const st = s.current;
    if (!supported) { setError("unsupported"); return; }
    if (st.running || st.starting) return; // StrictMode runs effects twice; never open two mic streams
    setError(null);
    st.starting = true;
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
    } catch (e) {
      st.starting = false;
      setError(e?.name === "NotAllowedError" || e?.name === "SecurityError" ? "not-allowed" : "no-mic");
      return;
    }
    st.starting = false;
    if (!mounted.current) { stream.getTracks().forEach((t) => t.stop()); return; } // left the screen while asking for the mic
    st.dead = false;
    st.stream = stream;
    const Ctx = window.AudioContext || window.webkitAudioContext;
    st.ctx = new Ctx();
    const src = st.ctx.createMediaStreamSource(st.stream);
    st.analyser = st.ctx.createAnalyser();
    st.analyser.fftSize = 1024;
    st.buf = new Float32Array(st.analyser.fftSize);
    src.connect(st.analyser);
    st.running = true;
    st.lastVoiceAt = performance.now();
    startRecorder();
    st.timer = setInterval(tick, TICK_MS);
    setListening(true);
  }, [supported, startRecorder, tick]);

  const stop = useCallback(() => { stopAll(); }, [stopAll]);

  // Stop listening, then wait until every clip (including the last sentence) has been transcribed and saved.
  const flush = useCallback(async () => {
    await stopAll();
    await s.current.chain;
  }, [stopAll]);

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; s.current.dead = true; stopAll(); };
  }, [stopAll]);

  return { supported, listening, speaking, pending, error, start, stop, flush };
}
