import { useRef, useState } from "react";
import {
  STAGES,
  getReminderSettings,
  importFhirFile,
  importFhirSample,
  saveReminderSettings,
  testTelegram,
  uploadDocument,
} from "../api/client.js";
import { AlertCard, Status, TimelineItem, formatDate } from "../components/ui.jsx";
import { useT } from "../i18n.js";

const STAGE_LABELS = {
  en: {
    read: "Reading image",
    understand: "Understanding content",
    code: "Checking medicines",
    explain: "Writing plain summary",
    check: "Final checks",
  },
  ml: {
    read: "ചിത്രം വായിക്കുന്നു",
    understand: "ഉള്ളടക്കം മനസ്സിലാക്കുന്നു",
    code: "മരുന്നുകൾ പരിശോധിക്കുന്നു",
    explain: "ലളിതമായ സംഗ്രഹം",
    check: "അവസാന പരിശോധനകൾ",
  },
};

// ── Upload form ───────────────────────────────────────────────
export default function Upload() {
  const { t, pick, lang } = useT();
  const ml = lang === "ml";
  const inputRef = useRef(null);
  const [file, setFile] = useState(null);
  const [done, setDone] = useState(null);
  const [error, setError] = useState(null);
  const [currentStage, setCurrentStage] = useState(null);
  const [preview, setPreview] = useState(null);

  const pick1 = (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setFile(f);
    setDone(null);
    setError(null);
    setCurrentStage(null);
    setPreview(URL.createObjectURL(f));
  };

  const upload = () => {
    if (!file) return;
    setError(null);
    setDone(null);
    setCurrentStage("read");
    uploadDocument(file, {
      onStage: setCurrentStage,
      onDone: (result) => {
        setCurrentStage("check");
        setDone(result);
      },
      onError: (msg) => {
        setError(msg);
        setCurrentStage(null);
      },
    });
  };

  const reset = () => {
    setFile(null);
    setDone(null);
    setError(null);
    setPreview(null);
    setCurrentStage(null);
    if (inputRef.current) inputRef.current.value = "";
  };

  const [dragging, setDragging] = useState(false);
  const onDrop = (e) => {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files?.[0];
    if (!f) return;
    setFile(f); setDone(null); setError(null); setCurrentStage(null);
    setPreview(URL.createObjectURL(f));
  };

  const stageIdx = currentStage ? STAGES.indexOf(currentStage) : -1;

  return (
    <>
      <div className="page-header">
        <h2>{ml ? "പുതിയ രേഖ ചേർക്കുക" : "Add a new record"}</h2>
      </div>
      <p className="text-muted text-sm" style={{ marginBottom: "var(--sp-5)" }}>
        {ml
          ? "പ്രിസ്ക്രിപ്ഷന്റെയോ ലാബ് റിപ്പോർട്ടിന്റെയോ ഫോട്ടോ അപ്‌ലോഡ് ചെയ്യുക."
          : "Upload a clear photo of a prescription or lab report."}
      </p>

      {/* Upload card */}
      {!done && (
        <div className="card stagger-1">
          <label
            htmlFor="doc-file-input"
            className={`dropzone${dragging ? " dragging" : ""}${file ? " has-file" : ""}`}
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
          >
            <span className="dz-icon" aria-hidden="true">
              <svg viewBox="0 0 48 48" width="34" height="34">
                {file ? (
                  <>
                    <path d="M14 6h14l8 8v28a2 2 0 0 1-2 2H14a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2Z" className="dz-doc" />
                    <path d="M28 6v8h8" className="dz-fold" />
                    <path d="M19 26l4 4 7-8" className="dz-check" />
                  </>
                ) : (
                  <>
                    <path d="M24 31V13m0 0-7 7m7-7 7 7" className="dz-arrow" />
                    <path d="M9 30v6a3 3 0 0 0 3 3h24a3 3 0 0 0 3-3v-6" className="dz-tray" />
                  </>
                )}
              </svg>
            </span>
            <div className="dz-title">
              {file ? file.name : (ml ? "ഫോട്ടോ തിരഞ്ഞെടുക്കുക" : "Drop a photo or PDF here")}
            </div>
            <div className="dz-sub">
              {file
                ? (ml ? "ഉപയോഗം തുടങ്ങാൻ തയ്യാറാണ്" : "Ready to analyse")
                : (ml ? "ക്ലിക്ക് ചെയ്ത് ഫയൽ തിരഞ്ഞെടുക്കുക" : "or click to browse  ·  JPG, PNG, PDF up to 10 MB")}
            </div>
          </label>
          <input
            ref={inputRef}
            id="doc-file-input"
            type="file"
            accept="image/*,application/pdf"
            onChange={pick1}
            style={{ display: "none" }}
          />

          {preview && (
            <img src={preview} alt="Document preview" className="preview" />
          )}

          <div className="row" style={{ marginTop: "var(--sp-4)" }}>
            <button
              id="upload-analyse-btn"
              className="primary"
              onClick={upload}
              disabled={!file || !!currentStage}
            >
              {ml ? "ഉപയോഗം തുടങ്ങുക" : "Analyse"}
            </button>
            {(file || error) && (
              <button className="ghost" onClick={reset} id="upload-clear-btn">
                {ml ? "പുതിയത്" : "Clear"}
              </button>
            )}
          </div>
          {error && <p className="error text-sm mt-3" role="alert">{error}</p>}
        </div>
      )}

      {/* Processing stages */}
      {currentStage && !done && !error && (
        <div className="card stagger-2 animate-in" style={{ marginTop: "var(--sp-4)" }}>
          <div className="text-sm font-medium" style={{ marginBottom: "var(--sp-4)", color: "var(--accent-text)" }}>
            {ml ? "പ്രോസസ്സ് ചെയ്യുന്നു…" : "Processing your document…"}
          </div>
          <ol className="stages" aria-live="polite" aria-label="Processing stages">
            {STAGES.map((s, i) => (
              <li
                key={s}
                className={i < stageIdx ? "stage done" : i === stageIdx ? "stage now" : "stage"}
              >
                <span className="dot" aria-hidden="true" />
                {STAGE_LABELS[lang]?.[s] || s}
                {i < stageIdx && <span className="text-good text-xs" style={{ marginLeft: "auto" }}>✓</span>}
              </li>
            ))}
          </ol>
        </div>
      )}

      {done && <UploadResult result={done} onReset={reset} />}

      {!done && !currentStage && <HospitalImport />}
    </>
  );
}

// ── FHIR Hospital import ──────────────────────────────────────
function HospitalImport() {
  const { lang } = useT();
  const ml = lang === "ml";
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  const run = async (fn) => {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setResult(await fn());
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const counts = result?.imported;

  return (
    <div className="section stagger-3">
      <h3>{ml ? "ആശുപത്രിയിൽ നിന്ന് ഇറക്കുമതി ചെയ്യുക (FHIR ഫയൽ)" : "Import from hospital (FHIR file)"}</h3>
      <div className="card">
        <p className="text-sm text-muted" style={{ marginBottom: "var(--sp-4)" }}>
          {ml
            ? "ആശുപത്രി നൽകിയ FHIR .json ഫയൽ തിരഞ്ഞെടുക്കുക. 2 MB വരെ."
            : "Choose the FHIR .json file your hospital gave you. Up to 2 MB."}
        </p>
        <input
          type="file"
          accept=".json,application/json,application/fhir+json"
          aria-label={ml ? "FHIR ഫയൽ" : "FHIR file"}
          onChange={(e) => {
            setFile(e.target.files?.[0] || null);
            setResult(null);
            setError(null);
          }}
        />
        <div className="row" style={{ marginTop: "var(--sp-4)" }}>
          <button
            id="fhir-import-btn"
            className="primary"
            disabled={!file || busy}
            onClick={() => run(() => importFhirFile(file))}
          >
            {busy ? "…" : ml ? "ഇറക്കുമതി ചെയ്യുക" : "Import file"}
          </button>
          <button
            id="fhir-sample-btn"
            disabled={busy}
            onClick={() => run(importFhirSample)}
          >
            {ml ? "സാമ്പിൾ ആശുപത്രി രേഖ ഉപയോഗിക്കുക" : "Use sample hospital record"}
          </button>
        </div>

        {busy && (
          <div className="loading-state" style={{ padding: "var(--sp-6) var(--sp-4)" }}>
            <div className="spinner" />
            <p className="text-dim text-sm">{ml ? "രേഖകൾ വായിച്ച് പരിശോധിക്കുന്നു…" : "Reading and checking the records…"}</p>
          </div>
        )}
        {error && <p className="error text-sm mt-3" role="alert">{error}</p>}
      </div>

      {result && (
        <div className="animate-in" role="status" style={{ marginTop: "var(--sp-4)" }}>
          <div className="card-good" style={{ borderRadius: "var(--r-lg)", padding: "var(--sp-4) var(--sp-5)" }}>
            <div className="font-semibold">{result.message}</div>
            {result.total > 0 && counts && (
              <ul className="items" style={{ marginTop: "var(--sp-3)" }}>
                <li>{counts.timelineCards} {ml ? "ടൈംലൈൻ കാർഡുകൾ" : counts.timelineCards === 1 ? "timeline card" : "timeline cards"}</li>
                <li>{counts.observations} {ml ? "ഫലങ്ങൾ" : counts.observations === 1 ? "result" : "results"}</li>
                <li>{counts.medicines} {ml ? "മരുന്നുകൾ" : counts.medicines === 1 ? "medicine" : "medicines"}</li>
                <li>{counts.conditions} {ml ? "രോഗാവസ്ഥകൾ" : counts.conditions === 1 ? "condition" : "conditions"}</li>
              </ul>
            )}
            {result.duplicates > 0 && !result.alreadyImported && (
              <p className="text-xs text-dim" style={{ marginTop: "var(--sp-2)" }}>
                {result.duplicates} {ml ? "കാർഡുകൾ നേരത്തെ ചേർത്തിരുന്നു, ഒഴിവാക്കി." : "already imported, skipped."}
              </p>
            )}
            {result.ignored?.length > 0 && (
              <p className="text-xs text-dim" style={{ marginTop: "var(--sp-1)" }}>
                {ml ? "ഒഴിവാക്കിയവ" : "Skipped types"}: {result.ignored.map((x) => `${x.type} (${x.count})`).join(", ")}
              </p>
            )}
          </div>

          {result.alerts?.length > 0 && (
            <div className="list" style={{ marginTop: "var(--sp-4)" }}>
              {result.alerts.map((a) => <AlertCard key={a.id} alert={a} />)}
            </div>
          )}
          {result.records?.length > 0 && (
            <ul className="timeline" style={{ marginTop: "var(--sp-4)" }} role="list">
              {result.records.map((d) => <TimelineItem key={d.id} doc={d} />)}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

// ── Upload result ─────────────────────────────────────────────
function UploadResult({ result, onReset }) {
  const { t, pick, lang } = useT();
  const ml = lang === "ml";
  const { record, alerts, reminders } = result;
  const [showSource, setShowSource] = useState(false);
  const [remBusy, setRemBusy] = useState(false);
  const [remNote, setRemNote] = useState(null);

  const turnOnReminders = async () => {
    setRemBusy(true);
    setRemNote(null);
    try {
      const cur = await getReminderSettings();
      await saveReminderSettings({ ...cur, remindersEnabled: true, channels: { ...cur.channels, telegram: true } });
      await testTelegram();
      setRemNote({ kind: "ok", text: ml ? "നിങ്ങളുടെ ടെലിഗ്രാമിലേക്ക് അയച്ചു" : "Sent to your Telegram" });
    } catch (e) {
      setRemNote({ kind: "error", text: e.message });
    } finally {
      setRemBusy(false);
    }
  };

  return (
    <>
      <div className="card animate-in" style={{ borderLeft: "3px solid var(--accent)" }}>
        <div className="row between" style={{ marginBottom: "var(--sp-2)" }}>
          <strong className="font-semibold">{record.title}</strong>
          <Status value={record.status || "watch"} />
        </div>
        <div className="text-xs text-dim">
          {formatDate(record.date)}
          {record.provider && <><span className="sep">·</span>{record.provider}</>}
          {record.doctor && <><span className="sep">·</span>{record.doctor}</>}
        </div>

        {record.summary && (
          <p className="lead" style={{ marginTop: "var(--sp-4)" }}>{pick(record.summary, "en")}</p>
        )}

        {record.medications?.length > 0 && (
          <>
            <h4 style={{ marginTop: "var(--sp-4)", marginBottom: "var(--sp-2)" }}>
              {ml ? "മരുന്നുകൾ" : "Medicines in this record"}
            </h4>
            <ul className="items">
              {record.medications.map((m, i) => (
                <li key={i}>
                  <b>{m.name}</b> · {m.dose} · {m.schedule}
                  {m.purpose && <><span className="sep">·</span>{m.purpose}</>}
                </li>
              ))}
            </ul>
          </>
        )}

        {record.observations?.length > 0 && (
          <>
            <h4 style={{ marginTop: "var(--sp-4)", marginBottom: "var(--sp-2)" }}>
              {ml ? "ഫലങ്ങൾ" : "Results"}
            </h4>
            <table className="labs" style={{ width: "100%" }}>
              <tbody>
                {record.observations.map((o, i) => (
                  <tr key={i}>
                    <td style={{ padding: "var(--sp-2)", borderBottom: "1px solid var(--border)" }}>{o.plain || o.name}</td>
                    <td style={{ padding: "var(--sp-2)", borderBottom: "1px solid var(--border)", fontWeight: "600" }}>{o.value} {o.unit}</td>
                    <td style={{ padding: "var(--sp-2)", borderBottom: "1px solid var(--border)", fontSize: "var(--font-size-xs)", color: "var(--text-3)" }}>{o.range}</td>
                    <td style={{ padding: "var(--sp-2)", borderBottom: "1px solid var(--border)" }}>{o.status && <Status value={o.status} />}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}

        {record.followUp && (
          <p className="text-xs text-dim" style={{ marginTop: "var(--sp-3)" }}>
            {ml ? "തുടർ നടപടി" : "Follow-up"}: {record.followUp}
          </p>
        )}

        {record.source?.lines?.length > 0 && (
          <div style={{ marginTop: "var(--sp-4)" }}>
            <button
              className="link small"
              onClick={() => setShowSource((s) => !s)}
              id="toggle-source-btn"
            >
              {showSource
                ? (ml ? "മറയ്ക്കുക" : "Hide source lines")
                : (ml ? "മൂല ഡോക്യുമെന്റ് കാണുക" : "See the original")}
            </button>
            {showSource && (
              <pre className="source">
                {record.source.lines.map((line, i) => (
                  <span key={i} className={record.source.highlight?.includes(i) ? "hl" : ""}>
                    {line}{"\n"}
                  </span>
                ))}
              </pre>
            )}
          </div>
        )}
      </div>

      {alerts?.length > 0 && (
        <div className="section stagger-2">
          <h3>{ml ? "മുന്നറിയിപ്പുകൾ" : "Warnings"}</h3>
          <div className="list">
            {alerts.map((a) => <AlertCard key={a.id} alert={a} />)}
          </div>
          <p className="text-xs text-dim mt-3">{t("askDoctor")}</p>
        </div>
      )}

      {reminders?.length > 0 && (
        <div className="section stagger-3">
          <h3>{ml ? "പുതിയ ഓർമ്മപ്പെടുത്തലുകൾ" : "New reminders"}</h3>
          <div className="list">
            {reminders.map((r) => (
              <div key={r.id} className="reminder-card">
                <div className="reminder-time">{r.time}</div>
                <div className="grow">
                  <div className="reminder-name">{r.title}</div>
                  {r.until && (
                    <div className="reminder-detail">
                      {ml ? "വരെ" : "until"} {formatDate(r.until)}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
          <div className="row" style={{ marginTop: "var(--sp-4)" }}>
            <button
              id="turn-on-reminders-btn"
              className="primary"
              onClick={turnOnReminders}
              disabled={remBusy}
            >
              {remBusy ? "…" : ml ? "ഈ ഓർമ്മപ്പെടുത്തലുകൾ ഓണാക്കുക" : "Turn on these reminders"}
            </button>
          </div>
          {remNote && (
            <p
              className={remNote.kind === "error" ? "error text-sm mt-2" : "text-good text-sm mt-2"}
              role={remNote.kind === "error" ? "alert" : "status"}
            >
              {remNote.text}
            </p>
          )}
        </div>
      )}

      <div style={{ marginTop: "var(--sp-6)" }}>
        <button
          id="upload-another-btn"
          className="primary"
          onClick={onReset}
        >
          {ml ? "മറ്റൊരു രേഖ ചേർക്കുക" : "Add another record"}
        </button>
      </div>
    </>
  );
}
