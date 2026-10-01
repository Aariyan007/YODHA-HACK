import { AlertCard, HbA1cChart, Status, TimelineItem, formatDate } from "../ui.jsx";

// State 1 of the Doctor Console: read-only patient history.
// Receives the share-snapshot payload from the parent so we don't double-fetch.
export function HistoryPanel({ snapshot, doctorName, setDoctorName, onStart, onDemo, busy }) {
  const { patient, alerts = [], medicines = [], insights, timeline = [], expiresAt } = snapshot;
  const openAlerts = alerts.filter((a) => !a.resolved);
  const encounters = timeline.slice(0, 5);
  const expires = expiresAt ? new Date(expiresAt) : null;
  const expiresText = expires ? expires.toLocaleString("en-IN") : "unknown";

  return (
    <div className="console-grid">
      <section className="card console-patient">
        <h2 style={{ marginTop: 0 }}>{patient.name}</h2>
        <div className="muted">
          {patient.age} · {patient.gender} · {patient.bloodGroup} · ABHA {patient.abhaId}
        </div>
        {patient.conditions?.length > 0 && (
          <p className="small">
            <span className="muted">Conditions: </span>
            {patient.conditions.join(", ")}
          </p>
        )}
        <div className="console-lock" role="note">
          <span aria-hidden="true">🔒</span>
          <span>
            Read-only view, shared by the patient. Access ends on {expiresText}. This view is logged.
          </span>
        </div>
      </section>

      {patient.allergies?.length > 0 && (
        <section className="card console-allergy" aria-labelledby="allergy-h">
          <h3 id="allergy-h" style={{ margin: 0, color: "var(--alert)" }}>⚠ Allergies</h3>
          <p style={{ color: "var(--alert)", fontWeight: 600, margin: "6px 0 0" }}>
            {patient.allergies.join(", ")}
          </p>
        </section>
      )}

      {openAlerts.length > 0 && (
        <section>
          <h3>Open warnings</h3>
          <div className="list">
            {openAlerts.map((a) => <AlertCard key={a.id} alert={a} />)}
          </div>
        </section>
      )}

      <section>
        <h3>Current medicines</h3>
        <div className="card">
          <table className="labs">
            <tbody>
              {medicines.map((m) => (
                <tr key={m.id}>
                  <td>
                    <strong>{m.name}</strong>
                    <div className="muted small">{m.generic}</div>
                  </td>
                  <td>{m.dose}</td>
                  <td>{m.frequency}</td>
                </tr>
              ))}
              {medicines.length === 0 && (
                <tr><td className="muted small">No active medicines recorded.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {insights?.labs?.length > 0 && (
        <section>
          <h3>Latest lab results</h3>
          <div className="card">
            <table className="labs">
              <tbody>
                {insights.labs.map((o) => (
                  <tr key={o.code}>
                    <td>
                      <strong>{o.name}</strong>
                      <div className="muted small">{formatDate(o.date)}</div>
                    </td>
                    <td>
                      <b>{o.value}</b> {o.unit}
                    </td>
                    <td><Status value={o.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {insights?.hba1c?.length > 1 && (
        <section>
          <h3>HbA1c trend</h3>
          <div className="card">
            <HbA1cChart points={insights.hba1c} />
          </div>
        </section>
      )}

      <section>
        <h3>Last {encounters.length} encounter{encounters.length === 1 ? "" : "s"}</h3>
        <ul className="timeline">
          {encounters.map((d) => <TimelineItem key={d.id} doc={d} />)}
          {encounters.length === 0 && <li className="muted small">No encounters yet.</li>}
        </ul>
      </section>

      <section className="card console-cta">
        <label>
          Doctor name
          <input
            value={doctorName}
            onChange={(e) => setDoctorName(e.target.value)}
            placeholder="Dr. Suresh Menon"
            aria-label="Doctor name"
          />
        </label>
        <div className="row" style={{ gap: 8, marginTop: 8 }}>
          <button className="primary" onClick={onStart} disabled={busy}>
            🎙 Start recording
          </button>
          <button onClick={onDemo} disabled={busy}>
            ▶ Play demo conversation
          </button>
        </div>
        <p className="muted small" style={{ marginTop: 6 }}>
          The demo plays a scripted 14-line visit — useful if the microphone is unavailable.
        </p>
      </section>
    </div>
  );
}
