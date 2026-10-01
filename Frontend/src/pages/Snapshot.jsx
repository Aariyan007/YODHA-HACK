import { Link, useParams } from "react-router-dom";
import { getShareSnapshot } from "../api/client.js";
import { AlertCard, Loading, TimelineItem } from "../components/ui.jsx";
import { useT } from "../i18n.js";
import { useApi } from "../useApi.js";
import { InsightsView } from "./Insights.jsx";

// ── Patient header ────────────────────────────────────────────
function PatientHeader({ patient, expiresAt, token }) {
  const { t } = useT();
  return (
    <div className="snapshot-header animate-in">
      <div className="row" style={{ gap: "var(--sp-4)", alignItems: "flex-start", marginBottom: "var(--sp-4)" }}>
        <div
          style={{
            width: 52, height: 52, borderRadius: "50%",
            background: "var(--accent-subtle)", border: "2px solid var(--accent-border)",
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: "1.4rem", flexShrink: 0,
          }}
          aria-hidden="true"
        >
          👤
        </div>
        <div>
          <div className="snapshot-name">{patient.name}</div>
          <div className="snapshot-meta">
            {patient.age && <span>{patient.age}</span>}
            {patient.gender && <><span className="sep">·</span><span>{patient.gender}</span></>}
            {patient.bloodGroup && <><span className="sep">·</span><span>{patient.bloodGroup}</span></>}
            {patient.abhaId && <><span className="sep">·</span><span>ABHA {patient.abhaId}</span></>}
          </div>
          {patient.conditions?.length > 0 && (
            <div className="text-sm text-muted">{patient.conditions.join(" · ")}</div>
          )}
        </div>
      </div>

      {patient.allergies?.length > 0 && (
        <div className="snapshot-allergy" role="alert">
          <span aria-hidden="true">⚠️</span>
          Allergies: {patient.allergies.join(", ")}
        </div>
      )}

      <div className="row" style={{ marginTop: "var(--sp-4)", justifyContent: "space-between", flexWrap: "wrap", gap: "var(--sp-3)" }}>
        <span className="text-xs text-dim" style={{ display: "flex", alignItems: "center", gap: "var(--sp-1)" }}>
          🔒 {t("readOnly")} · {t("expires")}: {new Date(expiresAt).toLocaleString("en-IN")}
        </span>
        <Link to={`/console/${token}`}>
          <button className="primary" id="start-consultation-btn">
            🎙 Start consultation
          </button>
        </Link>
      </div>
    </div>
  );
}

// ── Medicine table ────────────────────────────────────────────
function MedTable({ medicines }) {
  return (
    <div className="card" style={{ padding: 0, overflow: "hidden" }}>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <tbody>
          {medicines.map((m) => (
            <tr key={m.id}>
              <td style={{ padding: "var(--sp-3) var(--sp-4)", borderBottom: "1px solid var(--border)" }}>
                <div className="font-medium text-sm">{m.name}</div>
                {m.generic && <div className="text-dim text-xs">{m.generic}</div>}
              </td>
              <td style={{ padding: "var(--sp-3) var(--sp-3)", borderBottom: "1px solid var(--border)", fontSize: "var(--font-size-sm)", color: "var(--text-2)" }}>{m.dose}</td>
              <td style={{ padding: "var(--sp-3) var(--sp-3)", borderBottom: "1px solid var(--border)", fontSize: "var(--font-size-sm)", color: "var(--text-3)" }}>{m.frequency}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Snapshot page (doctor's read-only view) ───────────────────
export default function Snapshot({ toggle }) {
  const { t } = useT();
  const { token } = useParams();
  const { data, loading, error } = useApi(() => getShareSnapshot(token), [token]);

  const errMsg = error === "Share link expired"
    ? "This share link has expired. Ask the patient for a new QR code."
    : error === "Share link not found"
      ? "This share link is not valid. Ask the patient for a new QR code."
      : error;

  return (
    <div className="shell">
      <header className="top" role="banner">
        <span className="brand" aria-label="MediThread Snapshot">
          MediThread · {t("snapshotTitle")}
        </span>
        <div className="top-actions">{toggle}</div>
      </header>

      <main role="main">
        {loading || error ? (
          <Loading error={errMsg} />
        ) : (
          <>
            <PatientHeader
              patient={data.patient}
              expiresAt={data.expiresAt}
              token={token}
            />

            {data.alerts.some((a) => !a.resolved) && (
              <div className="section stagger-1">
                <h3>{t("alerts")}</h3>
                <div className="list">
                  {data.alerts.filter((a) => !a.resolved).map((a) => (
                    <AlertCard key={a.id} alert={a} />
                  ))}
                </div>
              </div>
            )}

            <div className="section stagger-2">
              <h3>{t("medicines")}</h3>
              <MedTable medicines={data.medicines} />
            </div>

            {data.insights && (
              <div className="section stagger-3">
                <InsightsView data={data.insights} />
              </div>
            )}

            <div className="section stagger-4">
              <h3>{t("timeline")}</h3>
              <ul className="timeline" role="list">
                {data.timeline.map((d) => (
                  <TimelineItem key={d.id} doc={d} />
                ))}
              </ul>
            </div>
          </>
        )}
      </main>
    </div>
  );
}
