import { AlertCard, CountUp, HbA1cChart, Status, formatDate } from "../ui.jsx";

export function HistoryPanel({ snapshot, doctorName, setDoctorName, onStart, onDemo, busy }) {
  const { patient, alerts = [], medicines = [], insights, timeline = [], expiresAt } = snapshot;
  const openAlerts = alerts.filter((a) => !a.resolved && a.kind !== "risk");
  const encounters = timeline.slice(0, 5);
  const expiresText = expiresAt ? new Date(expiresAt).toLocaleString("en-IN") : "unknown";

  const lab = (code) => insights?.labs?.find((l) => l.code === code);
  const hba1cLab = lab("hba1c");
  const sugarLab = lab("fbs") || lab("rbs") || lab("ppbs");
  const sbp = lab("sbp"), dbp = lab("dbp");
  const hba1c = hba1cLab ? hba1cLab.value : "--";
  const sugar = sugarLab ? sugarLab.value : "--";
  // Only show BP when both numbers come from the same day; never invent a value.
  const bp = sbp && dbp && sbp.date === dbp.date ? `${sbp.value}/${dbp.value}` : "--";
  const risks = snapshot.risks || [];
  const demographics = [patient.gender, patient.age ? `${patient.age} yrs` : null, patient.bloodGroup].filter(Boolean).join(", ");

  return (
    <div className="stack-lg animate-in" style={{ padding: "var(--sp-8) 0" }}>

      {/* Patient Header */}
      <div className="section" style={{ marginBottom: 0 }}>
        <h2>{patient.name || "Patient"}</h2>
        <div className="row text-dim text-sm" style={{ marginTop: "var(--sp-2)" }}>
          {demographics && <><span>{demographics}</span><span className="sep">·</span></>}
          <span>{patient.phone}</span>
        </div>
      </div>

      {/* Patient Snapshot */}
      <section className="section" style={{ marginBottom: 0 }}>
        <h3>Patient Snapshot</h3>
        <div className="grid-4" style={{ marginBottom: "var(--sp-4)" }}>
          <div className="metric-card stagger-1">
            <div className="metric-label">HbA1c</div>
            <div className="metric-value"><CountUp value={hba1c} />{hba1c !== "--" ? "%" : ""}</div>
            <div className="metric-sub">{hba1cLab ? hba1cLab.date : "No result"}</div>
          </div>
          <div className="metric-card stagger-2">
            <div className="metric-label">Blood Pressure</div>
            <div className="metric-value">{bp}</div>
            <div className="metric-sub">{bp !== "--" ? `mmHg · ${sbp.date}` : "No reading"}</div>
          </div>
          <div className="metric-card stagger-3">
            <div className="metric-label">{sugarLab ? sugarLab.name : "Blood sugar"}</div>
            <div className="metric-value"><CountUp value={sugar} /></div>
            <div className="metric-sub">{sugarLab ? `mg/dL · ${sugarLab.date}` : "No result"}</div>
          </div>
          <div className="metric-card stagger-4">
            <div className="metric-label">Active Meds</div>
            <div className="metric-value"><CountUp value={medicines.length} /></div>
            <div className="metric-sub">Prescribed</div>
          </div>
        </div>

        {patient.allergies?.length > 0 && (
          <div className="snapshot-allergy" style={{ marginTop: "var(--sp-3)" }}>
            <span aria-hidden="true">⚠</span>
            <strong>Allergies:</strong> {patient.allergies.join(", ")}
          </div>
        )}

        {risks.length > 0 && (
          <div className="list" style={{ marginTop: "var(--sp-3)" }}>
            {risks.map((r) => (
              <div key={r.key} className={`risk-card lvl-${r.level}`}>
                <div className="row between"><strong className="risk-title">{r.title}</strong><span className={`risk-level ${r.level}`}>{r.level}</span></div>
                <p className="risk-msg">{r.message}</p>
              </div>
            ))}
          </div>
        )}

        {openAlerts.length > 0 && (
          <div className="list" style={{ marginTop: "var(--sp-3)" }}>
            {openAlerts.map((a) => <AlertCard key={a.id} alert={a} />)}
          </div>
        )}
      </section>

      {/* Health Trend */}
      {insights?.hba1c?.length > 1 && (
        <section className="section" style={{ marginBottom: 0 }}>
          <h3>Health Trend</h3>
          <div className="card">
            <HbA1cChart points={insights.hba1c} />
          </div>
        </section>
      )}

      {/* Current Medications */}
      {medicines.length > 0 && (
        <section className="section" style={{ marginBottom: 0 }}>
          <h3>Current Medications</h3>
          <div className="card" style={{ padding: 0, overflow: "hidden" }}>
            <table className="labs">
              <thead>
                <tr>
                  <th>Medicine</th>
                  <th>Dose</th>
                  <th>Schedule</th>
                </tr>
              </thead>
              <tbody>
                {medicines.map((m) => (
                  <tr key={m.id}>
                    <td className="labs-name">
                      <strong>{m.name}</strong>
                      {m.generic && (
                        <div style={{ fontSize: "var(--font-xs)", color: "var(--text-3)", marginTop: 2 }}>
                          {m.generic}
                        </div>
                      )}
                    </td>
                    <td className="labs-value">{m.dose}</td>
                    <td>{m.frequency}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* Recent Encounters */}
      <section className="section" style={{ marginBottom: 0 }}>
        <h3>Recent Encounters</h3>
        {encounters.length === 0 ? (
          <p className="text-dim text-sm">No encounters yet.</p>
        ) : (
          <div className="encounter-list">
            {encounters.map((d) => (
              <div key={d.id} className="encounter-card">
                <div className="ec-header">
                  <div>
                    <div className="ec-date">{formatDate(d.date)}</div>
                    <div className="ec-type">{d.type}</div>
                  </div>
                </div>
                <div className="ec-title">{d.title}</div>
                {(d.source || d.doctor) && (
                  <div className="ec-meta">{d.source || d.doctor}</div>
                )}
                {d.items?.length > 0 && (
                  <div className="ec-items">
                    {d.items.map((it, i) => (
                      <div key={i} className="ec-item">
                        <div className="ec-item-name">{it.name}</div>
                        <div className="ec-item-desc">
                          {"value" in it ? `${it.value} ${it.unit || ""}` : [it.dose, it.frequency].filter(Boolean).join(" · ")}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Consultation */}
      <section className="section" style={{ marginBottom: 0 }}>
        <h3>Consultation</h3>
        <div className="card">
          <label style={{ marginBottom: "var(--sp-4)" }}>
            Doctor name
            <input
              value={doctorName}
              onChange={(e) => setDoctorName(e.target.value)}
              placeholder="Dr. Suresh Menon"
              aria-label="Doctor name"
              style={{ marginTop: "var(--sp-2)" }}
            />
          </label>
          <div className="row" style={{ gap: "var(--sp-3)" }}>
            <button className="primary" onClick={onStart} disabled={busy}>
              🎙 Start recording
            </button>
            <button className="ghost" onClick={onDemo} disabled={busy}>
              ▶ Demo conversation
            </button>
          </div>
          <div className="text-dim text-xs" style={{ marginTop: "var(--sp-3)" }}>
            <span aria-hidden="true">🔒</span> Shared by patient. Access expires {expiresText}.
          </div>
        </div>
      </section>
    </div>
  );
}
