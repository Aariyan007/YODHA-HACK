import { useRef, useState } from "react";

// An action command, not a chat composer. The paperclip hands a file to the agent (PDF or photo).
export default function AgentInput({ onSubmit, onFile, disabled }) {
  const [text, setText] = useState("");
  const pick = useRef(null);
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
      <label className="sr-only" htmlFor="ag-cmd">What should I help you complete?</label>
      <input id="ag-cmd" value={text} onChange={(e) => setText(e.target.value)} maxLength={200} disabled={disabled}
             placeholder="What should I help you complete?" autoComplete="off" />
      <button type="submit" disabled={disabled || !text.trim()} aria-label="Run this request">↑</button>
    </form>
  );
}
