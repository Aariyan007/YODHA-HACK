import { getInsights } from "../api/client.js";
import { Empty, HbA1cChart, Loading, Status, formatDate } from "../components/ui.jsx";
import { useT } from "../i18n.js";
import { useApi } from "../useApi.js";

export function InsightsView({ data }) {
  const { t, pick } = useT();
  return (
    <>
      <p className="lead">{pick(data, "summary")}</p>

      <section>
        <h3>{t("sugarTrend")}</h3>
        <div className="card">
          {data.hba1c?.length ? <HbA1cChart points={data.hba1c} /> : <p className="muted">No HbA1c results yet.</p>}
        </div>
      </section>

      <section>
        <h3>{t("latestLabs")}</h3>
        <div className="card">
          <table className="labs">
            <tbody>
              {data.labs.map((l) => (
                <tr key={l.code}>
                  <td>{l.name}</td>
                  <td>
                    <b>{l.value}</b> {l.unit}
                  </td>
                  <td className="muted small">{l.range}</td>
                  <td>
                    <Status value={l.status} />
                  </td>
                  <td className="muted small">{formatDate(l.date)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section>
        <h3>{t("conditions")}</h3>
        <div className="list">
          {data.conditions.map((c) => (
            <div key={c.name} className="card row between">
              <span>
                {c.name} <span className="muted small">({t("since")} {c.since})</span>
              </span>
              <Status value={c.status} />
            </div>
          ))}
        </div>
      </section>
    </>
  );
}

export default function Insights() {
  const { t } = useT();
  const { data, loading, error, reload } = useApi(getInsights);
  if (loading || error) return <Loading error={error} onRetry={reload} />;
  return (
    <>
      <h2>{t("insights")}</h2>
      <InsightsView data={data} />
    </>
  );
}
