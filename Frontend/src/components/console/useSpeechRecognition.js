import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Thin wrapper around the Web SpeechRecognition API.
 *
 * - supported: true when the browser exposes SpeechRecognition / webkitSpeechRecognition.
 * - listening: whether we are currently listening.
 * - interim: the current interim transcript (not yet "final").
 * - start(): asks for mic permission on first click; begins listening (continuous).
 * - stop(): user-initiated stop; stays stopped until start() is called again.
 * - error: the latest error reason, if any (e.g. "not-allowed", "no-speech").
 *
 * The caller passes onFinal(text, event) — fired once per completed sentence
 * (isFinal=true). The hook auto-restarts the recognizer if it ends while the
 * user still wants to listen (browsers sometimes drop it after silence).
 */
export function useSpeechRecognition({ onFinal, lang = "en-IN" } = {}) {
  const Ctor = typeof window !== "undefined" &&
    (window.SpeechRecognition || window.webkitSpeechRecognition);
  const supported = Boolean(Ctor);

  const [listening, setListening] = useState(false);
  const [interim, setInterim] = useState("");
  const [error, setError] = useState(null);

  const recRef = useRef(null);
  const wantRef = useRef(false); // whether the USER wants us to be listening
  const onFinalRef = useRef(onFinal);
  onFinalRef.current = onFinal;

  // Create (or recreate) the recognizer.
  const build = useCallback(() => {
    if (!Ctor) return null;
    const rec = new Ctor();
    rec.continuous = true;
    rec.interimResults = true;
    rec.lang = lang;
    rec.onresult = (ev) => {
      let final = "";
      let interimText = "";
      for (let i = ev.resultIndex; i < ev.results.length; i++) {
        const r = ev.results[i];
        if (r.isFinal) final += r[0].transcript;
        else interimText += r[0].transcript;
      }
      if (interimText) setInterim(interimText.trim());
      if (final.trim()) {
        setInterim("");
        onFinalRef.current && onFinalRef.current(final.trim(), ev);
      }
    };
    rec.onerror = (ev) => {
      // "no-speech" is normal silence; don't surface to the user as a failure.
      if (ev.error && ev.error !== "no-speech") setError(ev.error);
    };
    rec.onend = () => {
      // Auto-restart if the user still wants to listen.
      setListening(false);
      if (wantRef.current) {
        try { rec.start(); setListening(true); }
        catch { /* already starting; let the browser settle */ }
      }
    };
    return rec;
  }, [Ctor, lang]);

  const start = useCallback(() => {
    if (!supported) { setError("unsupported"); return; }
    setError(null);
    wantRef.current = true;
    if (!recRef.current) recRef.current = build();
    try {
      recRef.current.start();
      setListening(true);
    } catch (e) {
      // Chrome throws "InvalidStateError" if start() is called twice; ignore.
    }
  }, [supported, build]);

  const stop = useCallback(() => {
    wantRef.current = false;
    setInterim("");
    if (recRef.current) {
      try { recRef.current.stop(); } catch { /* no-op */ }
    }
    setListening(false);
  }, []);

  // Cleanup on unmount.
  useEffect(() => () => {
    wantRef.current = false;
    if (recRef.current) {
      try { recRef.current.abort(); } catch { /* no-op */ }
    }
  }, []);

  return { supported, listening, interim, start, stop, error };
}
