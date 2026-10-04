import { Link } from "react-router-dom";
import { Arrow, Chapter, RV } from "../../design/primitives.jsx";
import { deltaList, eventTime, shortDate } from "../../design/data.js";
import { ChangeBlock, HealthSnapshot, OpenItems } from "../../design/home.jsx";
import ThreadExplorer from "../../design/ThreadExplorer.jsx";
import { MedicationList } from "../../design/medication.jsx";
import { useState } from "react";
import { useT } from "../../i18n.js";

// A health check risk shown as an open care item (same row design as an alert).
const riskItem = (r) => ({
  id: `risk-${r.key}`, severity: r.level === "watch" ? "medium" : "high", kind: "risk",
  title: r.title, message: r.message, messageMl: r.messageMl, cta: null,
});

const STATUS_LABEL = { good: "In range", watch: "Watch", alert: "Out of range" };

// Latest value of every test, most recent first. Units and ranges are as stored (the printed range when we have no rule).
function ResultsTable({ labs }) {
  const [all, setAll] = useState(false);
  if (!labs?.length) return <p className="mt-quiet">No lab results on record.</p>;
  const sorted = [...labs].sort((a, b) => (a.status === "alert") === (b.status === "alert") ? 0 : a.status === "alert" ? -1 : 1);
  const rows = all ? sorted : sorted.slice(0, 8);
  return (
    <>
      <table className="mt-results">
        <thead><tr><th>Test</th><th>Value</th><th>Usual range</th><th>Status</th><th>Date</th></tr></thead>
        <tbody>
          {rows.map((l) => (
            <tr key={l.code} className={`st-${l.status || "none"}`}>
              <td>{l.name}</td>
              <td className="v"><b>{l.value}</b> {l.unit}</td>
              <td>{l.range || "–"}</td>
              <td><span className={`mt-chip st-${l.status || "none"}`}>{STATUS_LABEL[l.status] || "–"}</span></td>
              <td>{shortDate(l.date)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {sorted.length > 8 && <button type="button" className="mt-link" onClick={() => setAll(!all)}>{all ? "Show fewer" : `Show all ${sorted.length} results`} <Arrow /></button>}
    </>
  );
}

// consultHref: read-only snapshot mode (the QR link a doctor opens). The last chapter links to the console instead of
// starting a recording here.
export function HistoryPanel({ snapshot, doctorName, setDoctorName, onStart, onDemo, busy, consultHref }) {
  const { t } = useT();
  const { patient, alerts = [], medicines = [], insights, timeline = [], expiresAt } = snapshot;
  const expiresText = expiresAt ? new Date(expiresAt).toLocaleString("en-IN") : "unknown";
  const deltas = deltaList(insights);
  const items = [
    ...alerts.filter((a) => !a.resolved && a.kind !== "risk"),
    ...(snapshot.risks || []).map(riskItem),
  ];
  const abnormal = (insights?.labs || []).filter((l) => l.status === "alert").length;
  const changed = deltas.filter((d) => d.dir !== "steady").length;
  const demographics = [patient.gender, patient.age ? `${patient.age} yrs` : null, patient.bloodGroup].filter(Boolean).join(" · ");
  const encounters = timeline.filter((d) => ["visit", "consultation", "prescription"].includes(d.type)).slice(0, 5);

  return (
    <div className="mt-page mt-console">
      {/* PATIENT */}
      <Chapter tone="ground">
        <div className="mt-grid mt-opening-grid">
          <RV className="c-8 mt-opening">
            <div className="mt-label">Patient</div>
            <h1 className="mt-display">{patient.name || "Patient"}</h1>
            <p className="mt-lede">{demographics}{demographics && patient.phone ? " · " : ""}{patient.phone}</p>
            {patient.allergies?.length > 0 && (
              <p className="mt-allergy"><b>Allergies</b> {patient.allergies.join(", ")}</p>
            )}
          </RV>
          <div className="c-4 mt-snap-col">
            <HealthSnapshot insights={insights} timeline={timeline} openCount={items.length} />
          </div>
        </div>
      </Chapter>

      {/* WHAT CHANGED */}
      <Chapter tone="soft" no="01" kicker="Since the last records" title="What changed since last visit?">
        <RV className="mt-tally-line">
          <span><b>{changed}</b> measurable {changed === 1 ? "change" : "changes"}</span>
          <span><b>{items.length}</b> open care {items.length === 1 ? "item" : "items"}</span>
          <span><b>{abnormal}</b> {abnormal === 1 ? "result" : "results"} out of range</span>
        </RV>
        {/* Use the full width for whichever side has something to show, so an empty column never leaves a gap. */}
        {deltas.length && items.length ? (
          <div className="mt-grid">
            <div className="c-8"><ChangeBlock deltas={deltas} /></div>
            <div className="c-4 mt-open-col">
              <div className="mt-label mt-col-label">Open care items</div>
              <OpenItems alerts={items} limit={3} />
            </div>
          </div>
        ) : items.length ? (
          <div className="mt-open-wide">
            <div className="mt-label mt-col-label">Open care items</div>
            <OpenItems alerts={items} limit={6} />
          </div>
        ) : (
          <ChangeBlock deltas={deltas} />
        )}
      </Chapter>

      {/* RESULTS */}
      <Chapter tone="ground" no="02" kicker="Latest values" title="Lab results" aside={<span className="mt-meta">{(insights?.labs || []).length} tests</span>}>
        <RV><ResultsTable labs={insights?.labs} /></RV>
      </Chapter>

      {/* THREAD */}
      <Chapter tone="warm" no="03" kicker="Their record" title="Health thread" aside={<span className="mt-meta">{timeline.length} records</span>}>
        <ThreadExplorer docs={timeline} limit={6} />
      </Chapter>

      {/* MEDICATIONS */}
      <Chapter tone="soft" no="04" kicker="Current" title="Medications" aside={<span className="mt-meta">{medicines.length} active</span>}>
        {medicines.length ? <MedicationList medicines={medicines} /> : <p className="mt-quiet">No active medicines on record.</p>}
      </Chapter>

      {/* RECENT ENCOUNTERS */}
      <Chapter tone="neutral" no="05" kicker="History" title="Recent encounters">
        {encounters.length === 0 ? <p className="mt-quiet">No encounters yet.</p> : (
          <RV as="ul" className="mt-enc" stagger={0.07} selector=":scope > li">
            {encounters.map((d) => (
              <li key={d.id}>
                <span className="when"><b>{shortDate(d.date)}</b>{eventTime(d) ? <i>{eventTime(d)}</i> : null}</span>
                <span className="what"><span className="mt-label">{t(d.type)}</span><strong>{d.title}</strong>{(d.source || d.doctor) && <em>{d.source || d.doctor}</em>}</span>
                <span className="how">{(d.items || []).slice(0, 3).map((it) => ("value" in it ? `${it.name} ${it.value}${it.unit ? ` ${it.unit}` : ""}` : [it.name, it.dose].filter(Boolean).join(" "))).join(" · ")}</span>
              </li>
            ))}
          </RV>
        )}
      </Chapter>

      {/* CONSULTATION */}
      {consultHref ? (
        <Chapter tone="warm" no="06" kicker="Visit" title="Start a consultation" last>
          <RV className="mt-consult">
            <p className="mt-lede">Speak the visit. A draft note appears with medicines, diagnoses and advice sorted out, and nothing reaches the patient until you approve it.</p>
            <div className="mt-consult-actions">
              <Link className="mt-btn" to={consultHref}>Open the consultation console <Arrow /></Link>
            </div>
            <p className="mt-small">Read-only record shared by the patient. Access is logged and expires {expiresText}.</p>
          </RV>
        </Chapter>
      ) : (
        <Chapter tone="warm" no="06" kicker="Visit" title="Start a consultation" last>
          <RV className="mt-consult">
            <label className="mt-field">
              <span className="mt-label">Doctor name</span>
              <input value={doctorName} onChange={(e) => setDoctorName(e.target.value)} placeholder="Dr. Suresh Menon" aria-label="Doctor name" />
            </label>
            <div className="mt-consult-actions">
              <button type="button" className="mt-btn" onClick={onStart} disabled={busy}>Start recording <Arrow /></button>
              <button type="button" className="mt-btn secondary" onClick={onDemo} disabled={busy}>Play demo conversation</button>
            </div>
            <p className="mt-small">Shared by the patient. Access expires {expiresText}. Voice is transcribed by Whisper, and the visit is sorted into diagnosis, medicines and tests for you to check before anything is saved.</p>
          </RV>
        </Chapter>
      )}
    </div>
  );
}
