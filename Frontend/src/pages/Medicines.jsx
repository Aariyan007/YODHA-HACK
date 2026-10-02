import { useEffect, useRef } from "react";
import { gsap } from "gsap";
import { getMedicines } from "../api/client.js";
import { Empty, Loading, formatDate } from "../components/ui.jsx";
import { useT } from "../i18n.js";
import { useApi } from "../useApi.js";

// Medicine card with stagger animation
function MedCard({ m, index }) {
  const { t } = useT();
  const ref = useRef(null);
  useEffect(() => {
    if (!ref.current) return;
    gsap.from(ref.current, {
      opacity: 0, y: 12,
      duration: 0.3, ease: "power2.out",
      delay: index * 0.06,
      clearProps: "all",
    });
  }, [index]);

  return (
    <div ref={ref} className="card" style={{ borderLeft: "3px solid var(--accent)", display: "grid", gap: "var(--sp-2)" }}>
      <div className="row between">
        <strong className="font-semibold">{m.name}</strong>
        {m.generic && <span className="text-dim text-xs">{m.generic}</span>}
      </div>

      <p className="text-sm" style={{ color: "var(--text-2)" }}>
        {[m.dose, m.frequency, (m.times || []).join(", ")].filter(Boolean).join(" · ")}
      </p>

      {m.instructions && (
        <p className="text-xs text-dim">{m.instructions}</p>
      )}

      <div className="row text-xs text-dim" style={{ marginTop: "var(--sp-1)" }}>
        {m.prescribedBy && (
          <span>{t("prescribedBy")} {m.prescribedBy}</span>
        )}
        {m.prescribedBy && m.startDate && <span className="sep">·</span>}
        {m.startDate && <span>{formatDate(m.startDate)}</span>}
      </div>
    </div>
  );
}

export default function Medicines() {
  const { t } = useT();
  const { data, loading, error, reload } = useApi(getMedicines);
  if (loading || error) return <Loading error={error} onRetry={reload} />;

  return (
    <>
      <div className="page-header">
        <h2>{t("medicines")}</h2>
        {data.length > 0 && (
          <span className="pill accent">{data.length} active</span>
        )}
      </div>

      {data.length === 0 ? (
        <Empty>
          No medicines yet. They appear here when you add a prescription.
        </Empty>
      ) : (
        <div className="grid-3" role="list">
          {data.map((m, i) => (
            <MedCard key={m.id} m={m} index={i} />
          ))}
        </div>
      )}
    </>
  );
}
