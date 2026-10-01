import { getMedicines } from "../api/client.js";
import { Empty, Loading, formatDate } from "../components/ui.jsx";
import { useT } from "../i18n.js";
import { useApi } from "../useApi.js";

export default function Medicines() {
  const { t } = useT();
  const { data, loading, error, reload } = useApi(getMedicines);
  if (loading || error) return <Loading error={error} onRetry={reload} />;

  return (
    <>
      <h2>{t("medicines")}</h2>
      {data.length === 0 && <Empty>No medicines yet. They appear here when you add a prescription.</Empty>}
      <div className="list">
        {data.map((m) => (
          <div key={m.id} className="card">
            <div className="row between">
              <strong>{m.name}</strong>
              <span className="muted small">{m.generic}</span>
            </div>
            <div>
              {[m.dose, m.frequency, (m.times || []).join(", ")].filter(Boolean).join(" · ")}
            </div>
            <div className="muted small">{m.instructions}</div>
            <div className="muted small">
              {m.prescribedBy ? `${t("prescribedBy")} ${m.prescribedBy}` : ""}{m.prescribedBy && m.startDate ? " · " : ""}{formatDate(m.startDate)}
            </div>
          </div>
        ))}
      </div>
    </>
  );
}
