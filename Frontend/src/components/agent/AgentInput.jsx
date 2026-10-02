import { useState } from "react";

// An action command, not a chat composer.
export default function AgentInput({ onSubmit, disabled }) {
  const [text, setText] = useState("");
  const go = (e) => {
    e.preventDefault();
    const t = text.trim();
    if (!t || disabled) return;
    onSubmit(t);
    setText("");
  };
  return (
    <form className="ag-input" onSubmit={go} data-a>
      <label className="sr-only" htmlFor="ag-cmd">What should I help you complete?</label>
      <input id="ag-cmd" value={text} onChange={(e) => setText(e.target.value)} maxLength={200} disabled={disabled}
             placeholder="What should I help you complete?" autoComplete="off" />
      <button type="submit" disabled={disabled || !text.trim()} aria-label="Run this request">↑</button>
    </form>
  );
}
