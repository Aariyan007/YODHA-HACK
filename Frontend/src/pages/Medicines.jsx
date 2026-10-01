import { getMedicines } from "../api/client.js";
import { Loading, formatDate } from "../components/ui.jsx";
import { useT } from "../i18n.js";
import { useApi } from "../useApi.js";

export default function Medicines() {
  const { t } = useT();
  const { data, loading, error } = useApi(getMedicines);
  if (loading) return <Loading error={error} />;

  return (
    <>
      <h2>{t("medicines")}</h2>
      <div className="list">
        {data.map((m) => (
          <div key={m.id} className="card">
            <div className="row between">
              <strong>{m.name}</strong>
              <span className="muted small">{m.generic}</span>
            </div>
            <div>
              {m.dose} · {m.frequency} · {m.times.join(", ")}
            </div>
            <div className="muted small">{m.instructions}</div>
            <div className="muted small">
              {t("prescribedBy")} {m.prescribedBy} · {formatDate(m.startDate)}
            </div>
          </div>
        ))}
      </div>
    </>
  );
}
