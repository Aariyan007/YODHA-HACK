import { useState } from "react";
import { triage } from "../api/client.js";
import { useT } from "../i18n.js";

export default function Triage() {
  const { lang } = useT();
  const [text, setText] = useState("");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const check = async (e) => {
    e.preventDefault();
    if (!text.trim()) return;
    setBusy(true);
    setError(null);
    try {
      setResult(await triage(text.trim()));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <h2>{lang === "ml" ? "ഏത് ഡോക്ടറെ കാണണം?" : "Which doctor should I see?"}</h2>
      <p className="muted small">
        {lang === "ml"
          ? "നിങ്ങളുടെ ലക്ഷണങ്ങൾ ചുരുക്കമായി എഴുതുക. ഇത് രോഗനിർണയമല്ല."
          : "Describe your symptoms in a sentence or two. This is not a diagnosis."}
      </p>

      <form className="card" onSubmit={check}>
        <textarea
          rows={3}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={lang === "ml" ? "ഉദാ: രാവിലെ മുതൽ നെഞ്ചുവേദന" : "e.g. chest pain since this morning"}
        />
        <button className="primary" disabled={busy || !text.trim()}>
          {lang === "ml" ? "ഉപദേശം തേടുക" : "Ask"}
        </button>
        {error && <p className="error">{error}</p>}
      </form>

      {result && (
        <div className={`card result ${result.urgent ? "urgent" : ""}`}>
          {result.urgent && (
            <div className="emergency">
              {lang === "ml" ? "⚠ അടിയന്തിരം: 108 വിളിക്കുക" : "⚠ Emergency: call 108"}
            </div>
          )}
          <h3 style={{ marginTop: 0 }}>{result.specialist}</h3>
          <p>{result.why}</p>
        </div>
      )}
    </>
  );
}
