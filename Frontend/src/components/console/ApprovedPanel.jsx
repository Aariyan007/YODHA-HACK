import { useRef, useState } from "react";
import { TimelineItem } from "../ui.jsx";
import { LangContext } from "../../i18n.js";
import { VisitClassification } from "./VisitClassification.jsx";

/**
 * State 4 — Approved.
 *
 * Shows a success message and a preview of what the patient sees on their
 * timeline (reuses TimelineItem). The EN/ML toggle wraps the preview in a
 * local LangContext.Provider so the global app language is not disturbed.
 */
export function ApprovedPanel({ result, patient, onNewConsultation, onBack }) {
  const [lang, setLang] = useState("en");
  const [speaking, setSpeaking] = useState(false);
  const rec = result?.record;
  const firstName = (patient?.name || "the patient").split(" ")[0];

  const utterRef = useRef(null);

  const readAloud = () => {
    const text = (rec?.summary?.[lang]) || "";
    if (!text || typeof window.speechSynthesis === "undefined") return;
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = lang === "ml" ? "ml-IN" : "en-IN";
    u.rate = 0.95;
    u.onend = () => setSpeaking(false);
    u.onerror = () => setSpeaking(false);
    utterRef.current = u;
    setSpeaking(true);
    window.speechSynthesis.speak(u);
  };

  const stopReading = () => {
    if (typeof window.speechSynthesis !== "undefined") window.speechSynthesis.cancel();
    setSpeaking(false);
  };

  if (!rec) {
    return (
      <div className="card">
        <h3 style={{ marginTop: 0 }}>Approved</h3>
        <p className="muted">The note was approved but no preview is available.</p>
      </div>
    );
  }

  return (
    <div className="console-approved">
      <section className="card approved-banner">
        <div className="row" style={{ gap: 12, alignItems: "center" }}>
          <span className="approved-tick" aria-hidden="true">✓</span>
          <div>
            <h2 style={{ margin: 0 }}>Note approved.</h2>
            <p className="muted" style={{ margin: 0 }}>It is now on {firstName}'s timeline.</p>
          </div>
        </div>
      </section>

      <section>
        <div className="row between" style={{ marginBottom: 8, flexWrap: "wrap", gap: 8 }}>
          <h3 style={{ margin: 0 }}>What the patient sees</h3>
          <div className="row" style={{ gap: 6 }}>
            <button
              className={lang === "en" ? "primary small" : "small"}
              onClick={() => { stopReading(); setLang("en"); }}
              aria-pressed={lang === "en"}
            >
              English
            </button>
            <button
              className={lang === "ml" ? "primary small" : "small"}
              onClick={() => { stopReading(); setLang("ml"); }}
              aria-pressed={lang === "ml"}
            >
              മലയാളം
            </button>
            {speaking ? (
              <button className="small" onClick={stopReading} aria-label="Stop reading">■ Stop</button>
            ) : (
              <button className="small" onClick={readAloud} aria-label="Read aloud">🔊 Read aloud</button>
            )}
          </div>
        </div>

        <LangContext.Provider value={{ lang, setLang }}>
          <ul className="timeline">
            <TimelineItem doc={toTimelineDoc(rec)} />
          </ul>
        </LangContext.Provider>

        {result.alerts?.length > 0 && (
          <p className="muted small">{result.alerts.length} warning(s) attached.</p>
        )}
        {result.reminders?.length > 0 && (
          <p className="muted small">{result.reminders.length} reminder(s) created.</p>
        )}
      </section>

      <VisitClassification data={result.classification} readOnly stopped={result.stoppedMedicines || []} />

      <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
        <button className="primary" onClick={onNewConsultation}>Start new consultation</button>
        <button onClick={onBack}>Back to patient summary</button>
      </div>
    </div>
  );
}

/**
 * The record returned by /approve matches the backend timeline shape but with
 * a `summary: {en, ml}` object. TimelineItem reads `summary` + `summaryMl` as
 * flat fields via pick(), so we normalise here.
 */
function toTimelineDoc(rec) {
  return {
    ...rec,
    summary: rec.summary?.en || "",
    summaryMl: rec.summary?.ml || rec.summary?.en || "",
    items: rec.medications?.map((m) => ({
      name: m.name, dose: m.dose, frequency: m.schedule || m.frequency, duration: m.duration,
    })) || [],
    source: rec.doctor || rec.provider || "",
    tags: rec.tags || [],
  };
}
