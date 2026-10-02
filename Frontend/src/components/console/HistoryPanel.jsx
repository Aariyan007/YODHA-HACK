import { CountUp, formatDate } from "../ui.jsx";
import { EdSection, WhatChanged, Attention } from "../editorial.jsx";
import HealthThread from "../thread.jsx";
import { HbA1cChart } from "../ui.jsx";

export function HistoryPanel({ snapshot, doctorName, setDoctorName, onStart, onDemo, busy }) {
  const { patient, alerts = [], medicines = [], insights, timeline = [], expiresAt } = snapshot;
  const openAlerts = alerts.filter((a) => !a.resolved && a.kind !== "risk");
  const expiresText = expiresAt ? new Date(expiresAt).toLocaleString("en-IN") : "unknown";

  const lab = (code) => insights?.labs?.find((l) => l.code === code);
  const hba1cLab = lab("hba1c");
  const sugarLab = lab("fbs") || lab("rbs") || lab("ppbs");
  const sbp = lab("sbp"), dbp = lab("dbp");
  const hba1c = hba1cLab ? hba1cLab.value : "--";
  const sugar = sugarLab ? sugarLab.value : "--";
  const bp = sbp && dbp && sbp.date === dbp.date ? `${sbp.value}/${dbp.value}` : "--";
  const risks = snapshot.risks || [];
  const demographics = [patient.gender, patient.age ? `${patient.age} yrs` : null, patient.bloodGroup].filter(Boolean).join(" · ");
  const attnCount = openAlerts.length + risks.length;

  return (
    <div style={{ paddingBottom: "var(--sp-16)" }}>
      {/* Patient identity */}
      <header className="ph" style={{ paddingTop: "var(--sp-8)" }}>
        <div className="ed-kicker">Patient</div>
        <div className="ph-top">
          <h1 className="ph-greet" style={{ fontSize: "clamp(1.9rem,1.4rem+2.4vw,3rem)" }}>{patient.name || "Patient"}</h1>
          {attnCount > 0 && <span className="ph-status alert">{attnCount} to review</span>}
        </div>
        <p className="ph-sub" style={{ fontSize: "1.05rem", marginTop: 8 }}>
          {demographics}{demographics && patient.phone ? " · " : ""}{patient.phone}
        </p>
        {patient.allergies?.length > 0 && (
          <div className="snapshot-allergy" style={{ marginTop: "var(--sp-4)", display: "inline-flex" }}>
            <span aria-hidden="true">⚠</span>
            <strong>Allergies:</strong> {patient.allergies.join(", ")}
          </div>
        )}
      </header>

      {/* Snapshot metrics */}
      <div className="console-metrics" style={{ marginTop: "var(--sp-6)" }}>
        <div className="cm">
          <div className="cm-l">HbA1c</div>
          <div className="cm-v"><CountUp value={hba1c} />{hba1c !== "--" ? "%" : ""}</div>
          <div className="cm-s">{hba1cLab ? hba1cLab.date : "No result"}</div>
        </div>
        <div className="cm">
          <div className="cm-l">Blood pressure</div>
          <div className="cm-v">{bp}</div>
          <div className="cm-s">{bp !== "--" ? `mmHg · ${sbp.date}` : "No reading"}</div>
        </div>
        <div className="cm">
          <div className="cm-l">{sugarLab ? sugarLab.name : "Blood sugar"}</div>
          <div className="cm-v"><CountUp value={sugar} /></div>
          <div className="cm-s">{sugarLab ? `mg/dL · ${sugarLab.date}` : "No result"}</div>
        </div>
        <div className="cm">
          <div className="cm-l">Active meds</div>
          <div className="cm-v"><CountUp value={medicines.length} /></div>
          <div className="cm-s">Prescribed</div>
        </div>
      </div>

      {/* What changed */}
      {insights?.series?.length > 0 && (
        <EdSection kicker="Since last records" title="What changed">
          <WhatChanged insights={insights} review={null} />
        </EdSection>
      )}

      {/* Needs review */}
      {attnCount > 0 && (
        <EdSection kicker="Clinical" title="Needs review">
          {risks.length > 0 && (
            <div className="list" style={{ marginBottom: openAlerts.length ? "var(--sp-5)" : 0 }}>
              {risks.map((r) => (
                <div key={r.key} className={`risk-card lvl-${r.level}`}>
                  <div className="row between"><strong className="risk-title">{r.title}</strong><span className={`risk-level ${r.level}`}>{r.level}</span></div>
                  <p className="risk-msg">{r.message}</p>
                </div>
              ))}
            </div>
          )}
          {openAlerts.length > 0 && <Attention alerts={openAlerts} />}
        </EdSection>
      )}

      {/* Trend */}
      {insights?.hba1c?.length > 1 && (
        <EdSection kicker="Trend" title="HbA1c over time">
          <div className="card" style={{ padding: "var(--sp-5)" }}><HbA1cChart points={insights.hba1c} /></div>
        </EdSection>
      )}

      {/* Medications */}
      {medicines.length > 0 && (
        <EdSection kicker="Current" title="Medications" meta={`${medicines.length} active`}>
          <div className="care-loop">
            {medicines.map((m) => (
              <div key={m.id} className="care-step done" style={{ gridTemplateColumns: "1fr auto" }}>
                <div>
                  <span className="care-label" style={{ fontWeight: 600 }}>{m.name}</span>
                  {m.generic && <span className="ed-meta" style={{ marginLeft: 8 }}>{m.generic}</span>}
                </div>
                <span className="care-when">{[m.dose, m.frequency].filter(Boolean).join(" · ")}</span>
              </div>
            ))}
          </div>
        </EdSection>
      )}

      {/* Recent encounters as the thread */}
      <EdSection kicker="History" title="Recent encounters">
        {timeline.length === 0 ? (
          <p className="ed-meta">No encounters yet.</p>
        ) : (
          <HealthThread docs={timeline} limit={5} />
        )}
      </EdSection>

      {/* Consultation */}
      <EdSection kicker="Visit" title="Start a consultation">
        <div className="card" style={{ padding: "var(--sp-6)" }}>
          <label style={{ marginBottom: "var(--sp-4)", display: "block" }}>
            Doctor name
            <input value={doctorName} onChange={(e) => setDoctorName(e.target.value)} placeholder="Dr. Suresh Menon" aria-label="Doctor name" style={{ marginTop: "var(--sp-2)" }} />
          </label>
          <div className="row" style={{ gap: "var(--sp-3)", flexWrap: "wrap" }}>
            <button className="ed-cta" onClick={onStart} disabled={busy}>🎙 Start recording</button>
            <button className="ed-cta ghost" onClick={onDemo} disabled={busy}>▶ Demo conversation</button>
          </div>
          <div className="ed-meta" style={{ marginTop: "var(--sp-4)" }}>
            <span aria-hidden="true">🔒</span> Shared by patient. Access expires {expiresText}.
          </div>
        </div>
      </EdSection>
    </div>
  );
}
