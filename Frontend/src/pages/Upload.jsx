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
  en: { read: "Reading image", understand: "Understanding content", code: "Checking medicines", explain: "Writing plain summary", check: "Final checks" },
  ml: { read: "ചിത്രം വായിക്കുന്നു", understand: "ഉള്ളടക്കം മനസ്സിലാക്കുന്നു", code: "മരുന്നുകൾ പരിശോധിക്കുന്നു", explain: "ലളിതമായ സംഗ്രഹം", check: "അവസാന പരിശോധനകൾ" },
};

export default function Upload() {
  const { t, pick, lang } = useT();
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

  const stageIdx = currentStage ? STAGES.indexOf(currentStage) : -1;

  return (
    <>
      <h2>{lang === "ml" ? "പുതിയ രേഖ ചേർക്കുക" : "Add a new record"}</h2>
      <p className="muted">
        {lang === "ml"
          ? "പ്രിസ്ക്രിപ്ഷന്റെയോ ലാബ് റിപ്പോർട്ടിന്റെയോ ഫോട്ടോ അപ്‌ലോഡ് ചെയ്യുക."
          : "Upload a clear photo of a prescription or lab report."}
      </p>

      {!done && (
        <div className="card">
          <input ref={inputRef} type="file" accept="image/*,application/pdf" onChange={pick1} />
          {preview && <img src={preview} alt="preview" className="preview" />}
          <div className="row">
            <button className="primary" onClick={upload} disabled={!file || !!currentStage}>
              {lang === "ml" ? "ഉപയോഗം തുടങ്ങുക" : "Analyse"}
            </button>
            {(file || error) && (
              <button className="link" onClick={reset}>
                {lang === "ml" ? "പുതിയത്" : "Clear"}
              </button>
            )}
          </div>
          {error && <p className="error">{error}</p>}
        </div>
      )}

      {currentStage && !done && !error && (
        <ol className="stages">
          {STAGES.map((s, i) => (
            <li key={s} className={i < stageIdx ? "stage done" : i === stageIdx ? "stage now" : "stage"}>
              <span className="dot" /> {STAGE_LABELS[lang][s] || s}
            </li>
          ))}
        </ol>
      )}

      {done && <UploadResult result={done} onReset={reset} />}

      {!done && !currentStage && <HospitalImport />}
    </>
  );
}

// Second way to add records: a FHIR R4 Bundle exported by a hospital (or the fictional sample).
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
    <section>
      <h3>{ml ? "ആശുപത്രിയിൽ നിന്ന് ഇറക്കുമതി ചെയ്യുക (FHIR ഫയൽ)" : "Import from hospital (FHIR file)"}</h3>
      <div className="card">
        <p className="muted small">
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
        <div className="row" style={{ marginTop: 10 }}>
          <button className="primary" disabled={!file || busy} onClick={() => run(() => importFhirFile(file))}>
            {busy ? "…" : ml ? "ഇറക്കുമതി ചെയ്യുക" : "Import file"}
          </button>
          <button disabled={busy} onClick={() => run(importFhirSample)}>
            {ml ? "സാമ്പിൾ ആശുപത്രി രേഖ ഉപയോഗിക്കുക" : "Use sample hospital record"}
          </button>
        </div>
        {busy && (
          <p className="muted" role="status">
            {ml ? "രേഖകൾ വായിച്ച് പരിശോധിക്കുന്നു…" : "Reading and checking the records…"}
          </p>
        )}
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
      </div>

      {result && (
        <div role="status">
          <div className="card result" style={{ marginTop: 12 }}>
            <strong>{result.message}</strong>
            {result.total > 0 && counts && (
              <ul className="items">
                <li>{counts.timelineCards} {ml ? "ടൈംലൈൻ കാർഡുകൾ" : "timeline cards"}</li>
                <li>{counts.observations} {ml ? "ഫലങ്ങൾ" : "results"}</li>
                <li>{counts.medicines} {ml ? "മരുന്നുകൾ" : "medicines"}</li>
                <li>{counts.conditions} {ml ? "രോഗാവസ്ഥകൾ" : "conditions"}</li>
              </ul>
            )}
            {result.duplicates > 0 && !result.alreadyImported && (
              <p className="muted small">
                {result.duplicates} {ml ? "കാർഡുകൾ നേരത്തെ ചേർത്തിരുന്നു, ഒഴിവാക്കി." : "already imported, skipped."}
              </p>
            )}
            {result.ignored?.length > 0 && (
              <p className="muted small">
                {ml ? "ഒഴിവാക്കിയവ" : "Skipped types"}: {result.ignored.map((x) => `${x.type} (${x.count})`).join(", ")}
              </p>
            )}
          </div>
          {result.alerts.length > 0 && (
            <div className="list" style={{ marginTop: 12 }}>
              {result.alerts.map((a) => (
                <AlertCard key={a.id} alert={a} />
              ))}
            </div>
          )}
          {result.records.length > 0 && (
            <ul className="timeline" style={{ marginTop: 12 }}>
              {result.records.map((d) => (
                <TimelineItem key={d.id} doc={d} />
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}

function UploadResult({ result, onReset }) {
  const { t, pick, lang } = useT();
  const { record, alerts, reminders } = result;
  const [showSource, setShowSource] = useState(false);
  const [remBusy, setRemBusy] = useState(false);
  const [remNote, setRemNote] = useState(null); // { kind: "ok" | "error", text }

  // Saves "reminders on" + Telegram channel, then sends a test message so the phone buzzes right away.
  const turnOnReminders = async () => {
    setRemBusy(true);
    setRemNote(null);
    try {
      const cur = await getReminderSettings();
      await saveReminderSettings({ ...cur, remindersEnabled: true, channels: { ...cur.channels, telegram: true } });
      await testTelegram();
      setRemNote({ kind: "ok", text: lang === "ml" ? "നിങ്ങളുടെ ടെലിഗ്രാമിലേക്ക് അയച്ചു" : "Sent to your Telegram" });
    } catch (e) {
      setRemNote({ kind: "error", text: e.message });
    } finally {
      setRemBusy(false);
    }
  };

  return (
    <>
      <div className="card result">
        <div className="row between">
          <strong>{record.title}</strong>
          <Status value={record.status || "watch"} />
        </div>
        <div className="muted small">
          {formatDate(record.date)} · {record.provider} {record.doctor && `· ${record.doctor}`}
        </div>
        <p className="lead">{pick(record.summary, "en")}</p>

        {record.medications.length > 0 && (
          <>
            <h4>{lang === "ml" ? "മരുന്നുകൾ" : "Medicines in this record"}</h4>
            <ul className="items">
              {record.medications.map((m, i) => (
                <li key={i}>
                  <b>{m.name}</b> · {m.dose} · {m.schedule} {m.purpose ? `· ${m.purpose}` : ""}
                </li>
              ))}
            </ul>
          </>
        )}

        {record.observations?.length > 0 && (
          <>
            <h4>{lang === "ml" ? "ഫലങ്ങൾ" : "Results"}</h4>
            <table className="labs">
              <tbody>
                {record.observations.map((o, i) => (
                  <tr key={i}>
                    <td>{o.plain || o.name}</td>
                    <td><b>{o.value}</b> {o.unit}</td>
                    <td className="muted small">{o.range}</td>
                    <td>{o.status && <Status value={o.status} />}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}

        {record.followUp && (
          <p className="muted small">
            {lang === "ml" ? "തുടർ നടപടി" : "Follow-up"}: {record.followUp}
          </p>
        )}

        {record.source?.lines?.length > 0 && (
          <>
            <button className="link small" onClick={() => setShowSource((s) => !s)}>
              {showSource
                ? (lang === "ml" ? "മറയ്ക്കുക" : "Hide source lines")
                : (lang === "ml" ? "മൂല ഡോക്യുമെന്റ് കാണുക" : "See the original")}
            </button>
            {showSource && (
              <pre className="source">
                {record.source.lines.map((line, i) => (
                  <span key={i} className={record.source.highlight?.includes(i) ? "hl" : ""}>
                    {line}
                    {"\n"}
                  </span>
                ))}
              </pre>
            )}
          </>
        )}
      </div>

      {alerts.length > 0 && (
        <section>
          <h3>{lang === "ml" ? "മുന്നറിയിപ്പുകൾ" : "Warnings"}</h3>
          <div className="list">
            {alerts.map((a) => (
              <AlertCard key={a.id} alert={a} />
            ))}
          </div>
          <p className="muted small">{t("askDoctor")}</p>
        </section>
      )}

      {reminders.length > 0 && (
        <section>
          <h3>{lang === "ml" ? "പുതിയ ഓർമ്മപ്പെടുത്തലുകൾ" : "New reminders"}</h3>
          <div className="list">
            {reminders.map((r) => (
              <div key={r.id} className="card reminder">
                <div className="time">{r.time}</div>
                <div className="grow">
                  <strong>{r.title}</strong>
                  {r.until && (
                    <div className="muted small">
                      {lang === "ml" ? "വരെ" : "until"} {formatDate(r.until)}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
          <div className="row" style={{ marginTop: 10 }}>
            <button className="primary" onClick={turnOnReminders} disabled={remBusy}>
              {remBusy ? "…" : lang === "ml" ? "ഈ ഓർമ്മപ്പെടുത്തലുകൾ ഓണാക്കുക" : "Turn on these reminders"}
            </button>
          </div>
          {remNote && (
            <p className={remNote.kind === "error" ? "error" : "muted"} role={remNote.kind === "error" ? "alert" : "status"}>
              {remNote.text}
            </p>
          )}
        </section>
      )}

      <button className="primary" onClick={onReset}>
        {lang === "ml" ? "മറ്റൊരു രേഖ ചേർക്കുക" : "Add another record"}
      </button>
    </>
  );
}
