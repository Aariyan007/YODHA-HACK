import { useCallback, useEffect, useRef, useState } from "react";

// idle -> listening -> transcribing -> idle (text handed back) | error. One recording at a time, 45 s at most.
// The text goes into the input for the person to read and edit; nothing is sent or run from voice.
export function useVoice(transcribe, onText) {
  const [state, setState] = useState("idle");
  const [error, setError] = useState(null);
  const rec = useRef(null), stream = useRef(null), chunks = useRef([]), timer = useRef(null), alive = useRef(true);

  useEffect(() => { alive.current = true; return () => { alive.current = false; clearTimeout(timer.current); stream.current?.getTracks().forEach((t) => t.stop()); }; }, []);

  const stop = useCallback(() => { clearTimeout(timer.current); if (rec.current?.state === "recording") rec.current.stop(); }, []);

  const start = useCallback(async () => {
    if (state !== "idle" && state !== "error") return;
    setError(null);
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") { setState("error"); setError("This browser cannot record audio."); return; }
    try {
      stream.current = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
    } catch { setState("error"); setError("Microphone access was blocked. Allow it in the browser and try again."); return; }
    chunks.current = [];
    const r = new MediaRecorder(stream.current);
    rec.current = r;
    r.ondataavailable = (e) => e.data.size && chunks.current.push(e.data);
    r.onstop = async () => {
      stream.current?.getTracks().forEach((t) => t.stop());
      const blob = new Blob(chunks.current, { type: r.mimeType || "audio/webm" });
      if (!alive.current) return;
      if (blob.size < 2000) { setState("error"); setError("I did not hear anything. Try again."); return; }
      setState("transcribing");
      try {
        const out = await transcribe(blob);
        if (!alive.current) return;
        if (!out.text) { setState("error"); setError("I could not make out any words. Try again, closer to the microphone."); return; }
        setState("idle");
        onText(out.text);
      } catch (e) { if (alive.current) { setState("error"); setError(e?.message && e.message.length < 140 ? e.message : "Voice did not work. Try again."); } }
    };
    r.start();
    setState("listening");
    timer.current = setTimeout(stop, 45000);
  }, [state, transcribe, onText, stop]);

  return { state, error, start, stop };
}
