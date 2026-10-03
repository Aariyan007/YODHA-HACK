import { Arrow, Chapter, RV } from "../../design/primitives.jsx";
import { deltaList, eventTime, shortDate } from "../../design/data.js";
import { ChangeBlock, HealthSnapshot, OpenItems } from "../../design/home.jsx";
import ThreadExplorer from "../../design/ThreadExplorer.jsx";
import { MedicationList } from "../../design/medication.jsx";
import { useT } from "../../i18n.js";

// A health check risk shown as an open care item (same row design as an alert).
const riskItem = (r) => ({
  id: `risk-${r.key}`, severity: r.level === "watch" ? "medium" : "high", kind: "risk",
  title: r.title, message: r.message, messageMl: r.messageMl, cta: null,
});

export function HistoryPanel({ snapshot, doctorName, setDoctorName, onStart, onDemo, busy }) {
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
        <div className="mt-grid">
          <div className="c-8"><ChangeBlock deltas={deltas} /></div>
          <div className="c-4 mt-open-col">
            <div className="mt-label mt-col-label">Open care items</div>
            <OpenItems alerts={items} limit={3} />
          </div>
        </div>
      </Chapter>

      {/* THREAD */}
      <Chapter tone="warm" no="02" kicker="Their record" title="Health thread" aside={<span className="mt-meta">{timeline.length} records</span>}>
        <ThreadExplorer docs={timeline} limit={6} />
      </Chapter>

      {/* MEDICATIONS */}
      <Chapter tone="ground" no="03" kicker="Current" title="Medications" aside={<span className="mt-meta">{medicines.length} active</span>}>
        {medicines.length ? <MedicationList medicines={medicines} /> : <p className="mt-quiet">No active medicines on record.</p>}
      </Chapter>

      {/* RECENT ENCOUNTERS */}
      <Chapter tone="neutral" no="04" kicker="History" title="Recent encounters">
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
      <Chapter tone="warm" no="05" kicker="Visit" title="Start a consultation" last>
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
    </div>
  );
}
