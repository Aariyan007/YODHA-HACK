import { useState } from "react";
import { Link } from "react-router-dom";
import { doctorsLink } from "../components/health.jsx";
import { triage } from "../api/client.js";
import { useT } from "../i18n.js";

// Triage names like "Diabetologist / Endocrinologist" -> the finder's single specialty.
const FINDER = ["General Physician", "Cardiologist", "Diabetologist", "Nephrologist", "Pulmonologist", "Gastroenterologist",
  "Endocrinologist", "Haematologist", "Neurologist", "Orthopaedician", "Gynaecologist", "Paediatrician", "Dermatologist",
  "Ophthalmologist", "ENT specialist", "Psychiatrist", "Urologist", "Dentist"];
function toFinderSpecialty(name = "") {
  const first = name.split("/").map((x) => x.trim()).find((x) => FINDER.includes(x));
  return first || FINDER.find((f) => name.toLowerCase().includes(f.toLowerCase().split(" ")[0])) || "General Physician";
}

// ── Result card ───────────────────────────────────────────────
function TriageResult({ result, lang }) {
  return (
    <div
      className={`card animate-in-fast${result.urgent ? " card-alert" : ""}`}
      role="region"
      aria-label="Triage result"
      style={{ marginTop: "var(--sp-4)" }}
    >
      {result.urgent && (
        <div className="emergency" role="alert">
          {lang === "ml" ? "⚠ അടിയന്തിരം: 108 വിളിക്കുക" : "⚠ Emergency: call 108 immediately"}
        </div>
      )}

      <div className="row" style={{ gap: "var(--sp-3)", alignItems: "flex-start", marginBottom: "var(--sp-3)" }}>
        <span style={{ fontSize: "1.6rem" }} aria-hidden="true">
          {result.urgent ? "🚨" : "👨‍⚕️"}
        </span>
        <div>
          <div className="text-xs text-dim uppercase" style={{ marginBottom: 2 }}>
            {lang === "ml" ? "ശുപാർശ" : "Recommended specialist"}
          </div>
          <div className="font-semibold text-lg">{result.specialist}</div>
        </div>
      </div>

      <p className="text-sm" style={{ color: "var(--text-2)", lineHeight: 1.6 }}>
        {result.why}
      </p>

      <div className="row" style={{ gap: "var(--sp-3)", marginTop: "var(--sp-4)", flexWrap: "wrap" }}>
        {result.urgent && <a className="btn-emergency" href="tel:108">{lang === "ml" ? "108 വിളിക്കുക" : "Call 108"}</a>}
        <Link className="primary-link"
              to={result.urgent ? doctorsLink("Emergency", { emergency: "1" }) : doctorsLink(toFinderSpecialty(result.specialist))}>
          {result.urgent
            ? (lang === "ml" ? "അടുത്തുള്ള ആശുപത്രി →" : "Nearest emergency hospital →")
            : (lang === "ml" ? `അടുത്തുള്ള ${result.specialist} →` : `Find a ${result.specialist} near me →`)}
        </Link>
      </div>

      <p className="text-xs text-dim" style={{ marginTop: "var(--sp-4)", borderTop: "1px solid var(--border)", paddingTop: "var(--sp-3)" }}>
        {lang === "ml"
          ? "ഈ ഉപദേശം ഒരു രോഗനിർണ്ണയമല്ല. ഒരു ഡോക്ടറെ കാണുക."
          : "This is not a diagnosis. Please consult a doctor."}
      </p>
    </div>
  );
}

export default function Triage() {
  const { lang } = useT();
  const ml = lang === "ml";

  const [text, setText] = useState("");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const check = async (e) => {
    e.preventDefault();
    if (!text.trim()) return;
    setBusy(true);
    setError(null);
    setResult(null);
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
      <div className="page-header">
        <h2>{ml ? "ഏത് ഡോക്ടറെ കാണണം?" : "Which doctor should I see?"}</h2>
      </div>

      <p className="text-muted text-sm" style={{ marginBottom: "var(--sp-5)" }}>
        {ml
          ? "നിങ്ങളുടെ ലക്ഷണങ്ങൾ ചുരുക്കമായി എഴുതുക. ഇത് രോഗനിർണ്ണയമല്ല."
          : "Describe your symptoms briefly. This is not a medical diagnosis."}
      </p>

      <div className="card">
        <form onSubmit={check} noValidate>
          <label>
            <span className="text-sm font-medium" style={{ display: "block", marginBottom: "var(--sp-2)" }}>
              {ml ? "ലക്ഷണങ്ങൾ" : "Your symptoms"}
            </span>
            <textarea
              id="triage-textarea"
              rows={4}
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder={ml ? "ഉദാ: രാവിലെ മുതൽ നെഞ്ചുവേദന" : "e.g. chest pain and shortness of breath since this morning"}
              style={{ marginBottom: "var(--sp-4)" }}
            />
          </label>
          <button
            id="triage-ask-btn"
            className="primary"
            disabled={busy || !text.trim()}
          >
            {busy ? (
              <span style={{ display: "flex", alignItems: "center", gap: "var(--sp-2)" }}>
                <span className="spinner" style={{ width: 16, height: 16, borderWidth: 2 }} />
                {ml ? "പരിശോധിക്കുന്നു…" : "Checking…"}
              </span>
            ) : (
              ml ? "ഉപദേശം തേടുക" : "Ask"
            )}
          </button>

          {error && (
            <p className="error text-sm mt-3" role="alert">{error}</p>
          )}
        </form>
      </div>

      {result && <TriageResult result={result} lang={lang} />}
    </>
  );
}
