import { useRef, useState } from "react";
import { useVoice } from "./useVoice.js";

// An action command, not a chat box. The paperclip hands a file (PDF or photo) to the agent.
export default function AgentInput({ onSubmit, onFile, onVoice, disabled }) {
  const [text, setText] = useState("");
  const pick = useRef(null);
  const voice = useVoice(onVoice || (async () => ({})), (t) => setText((cur) => (cur ? `${cur} ${t}` : t)));
  const go = (e) => {
    e.preventDefault();
    const t = text.trim();
    if (!t || disabled) return;
    onSubmit(t);
    setText("");
  };
  return (
    <form className="ag-input" onSubmit={go} data-a>
      {onFile && (
        <>
          <input ref={pick} type="file" className="sr-only" tabIndex={-1} accept="application/pdf,image/jpeg,image/png,image/webp"
                 onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) onFile(f); }} />
          <button type="button" className="ag-attach" disabled={disabled} aria-label="Attach a PDF or photo of a record" onClick={() => pick.current?.click()}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M21 11.5l-8.6 8.6a5 5 0 0 1-7.1-7.1l8.6-8.6a3.3 3.3 0 0 1 4.7 4.7l-8.6 8.6a1.7 1.7 0 0 1-2.4-2.4l7.9-7.9" /></svg>
          </button>
        </>
      )}
      {onVoice && (
        <button type="button" className={`ag-attach ag-mic ${voice.state}`} disabled={disabled || voice.state === "transcribing"}
                aria-label={voice.state === "listening" ? "Stop recording" : "Speak your request"} aria-pressed={voice.state === "listening"}
                onClick={voice.state === "listening" ? voice.stop : voice.start}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            {voice.state === "listening" ? <rect x="6" y="6" width="12" height="12" rx="2" /> : <><rect x="9" y="3" width="6" height="12" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3" /></>}
          </svg>
        </button>
      )}
      <label className="sr-only" htmlFor="ag-cmd">What should I help you complete?</label>
      <input id="ag-cmd" value={text} onChange={(e) => setText(e.target.value)} maxLength={200} disabled={disabled}
             placeholder={voice.state === "listening" ? "Listening… tap to stop" : voice.state === "transcribing" ? "Turning your voice into text…" : "What should I help you complete?"} autoComplete="off" />
      <button type="submit" disabled={disabled || !text.trim()} aria-label="Run this request">↑</button>
      {voice.error && <p className="ag-voice-err" role="alert">{voice.error}</p>}
    </form>
  );
}
