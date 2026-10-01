import { Link, useParams } from "react-router-dom";
import { getShareSnapshot } from "../api/client.js";
import { AlertCard, Loading, TimelineItem } from "../components/ui.jsx";
import { useT } from "../i18n.js";
import { useApi } from "../useApi.js";
import { InsightsView } from "./Insights.jsx";

// Read-only view a doctor sees after scanning the patient's QR.
export default function Snapshot({ toggle }) {
  const { t } = useT();
  const { token } = useParams();
  const { data, loading, error } = useApi(() => getShareSnapshot(token), [token]);

  return (
    <div className="shell">
      <header className="top">
        <span className="brand">MediThread · {t("snapshotTitle")}</span>
        {toggle}
      </header>
      <main>
        {loading ? (
          <Loading error={error} />
        ) : (
          <>
            <div className="card">
              <h2>{data.patient.name}</h2>
              <div className="muted">
                {data.patient.age} · {data.patient.gender} · {data.patient.bloodGroup} · ABHA {data.patient.abhaId}
              </div>
              <div>{data.patient.conditions.join(", ")}</div>
              {data.patient.allergies.length > 0 && <div className="error">Allergies: {data.patient.allergies.join(", ")}</div>}
              <div className="muted small">
                {t("readOnly")} {t("expires")}: {new Date(data.expiresAt).toLocaleString("en-IN")}
              </div>
              <div className="row" style={{ marginTop: 10 }}>
                <Link to={`/console/${token}`}>
                  <button className="primary">🎙 Start consultation</button>
                </Link>
              </div>
            </div>

            {data.alerts.some((a) => !a.resolved) && (
              <section>
                <h3>{t("alerts")}</h3>
                <div className="list">
                  {data.alerts.filter((a) => !a.resolved).map((a) => (
                    <AlertCard key={a.id} alert={a} />
                  ))}
                </div>
              </section>
            )}

            <section>
              <h3>{t("medicines")}</h3>
              <div className="card">
                <table className="labs">
                  <tbody>
                    {data.medicines.map((m) => (
                      <tr key={m.id}>
                        <td>
                          <strong>{m.name}</strong> <span className="muted small">{m.generic}</span>
                        </td>
                        <td>{m.dose}</td>
                        <td>{m.frequency}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>

            {data.insights && <InsightsView data={data.insights} />}

            <section>
              <h3>{t("timeline")}</h3>
              <ul className="timeline">
                {data.timeline.map((d) => (
                  <TimelineItem key={d.id} doc={d} />
                ))}
              </ul>
            </section>
          </>
        )}
      </main>
    </div>
  );
}
