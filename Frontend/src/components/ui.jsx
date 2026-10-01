import { useT } from "../i18n.js";

// ── Status pill (good / watch / alert) ────────────────────────
export function Status({ value }) {
  const { t } = useT();
  return <span className={`pill ${value}`}>{t(value)}</span>;
}

// ── Loading / Error state ─────────────────────────────────────
export function Loading({ error, onRetry }) {
  const { lang } = useT();
  if (error) {
    return (
      <div role="alert" className="animate-in">
        <div className="card-alert">
          <p className="text-alert font-medium">{error}</p>
          {onRetry && (
            <button className="mt-3" onClick={onRetry}>
              {lang === "ml" ? "വീണ്ടും ശ്രമിക്കുക" : "Try again"}
            </button>
          )}
        </div>
      </div>
    );
  }
  return (
    <div className="loading-state animate-in" role="status" aria-live="polite">
      <div className="spinner" aria-hidden="true" />
      <p className="text-dim text-sm">{lang === "ml" ? "ലോഡ് ചെയ്യുന്നു…" : "Loading…"}</p>
    </div>
  );
}

// ── Empty state ───────────────────────────────────────────────
export function Empty({ icon = "📋", children }) {
  return (
    <div className="empty animate-in">
      <span className="empty-icon" aria-hidden="true">{icon}</span>
      <p>{children}</p>
    </div>
  );
}

// ── Alert card ────────────────────────────────────────────────
export function AlertCard({ alert }) {
  const { pick } = useT();
  return (
    <div className={`alert-card ${alert.severity}`} role="alert">
      <div className="row between mb-2">
        <strong className="text-sm font-semibold">{alert.title}</strong>
        <span className={`sev ${alert.severity}`}>{alert.severity}</span>
      </div>
      <p className="text-sm text-muted">{pick(alert, "message")}</p>
    </div>
  );
}

// ── Timeline item ─────────────────────────────────────────────
export function TimelineItem({ doc }) {
  const { t, pick } = useT();
  return (
    <li className={`tl-item ${doc.type}`}>
      <div className="tl-date">
        <span>{formatDateShort(doc.date)}</span>
      </div>
      <div className="tl-dot" aria-hidden="true" />
      <div className="tl-card">
        <div className="row between">
          <strong className="text-sm font-semibold truncate">{doc.title}</strong>
          <span className="tl-type">{t(doc.type)}</span>
        </div>
        {doc.source && <div className="tl-source">{doc.source}</div>}
        <p className="tl-summary">{pick(doc, "summary")}</p>
        {doc.items?.length > 0 && (
          <ul className="tl-items">
            {doc.items.map((it, i) =>
              "value" in it ? (
                <li key={i}>
                  <span className="text-dim">{it.name}</span>
                  <b className={`num-${it.status}`}>{it.value} {it.unit}</b>
                  <Status value={it.status} />
                </li>
              ) : (
                <li key={i}>
                  <b>{it.name}</b>
                  <span className="sep">·</span>
                  <span>{it.dose}</span>
                  <span className="sep">·</span>
                  <span>{it.frequency}</span>
                  {it.duration && (
                    <><span className="sep">·</span><span className="text-dim">{it.duration}</span></>
                  )}
                </li>
              )
            )}
          </ul>
        )}
      </div>
    </li>
  );
}

// ── HbA1c chart ───────────────────────────────────────────────
export function HbA1cChart({ points }) {
  if (!points?.length) return null;
  const W = 340, H = 150, P = 30;
  const vals = points.map((p) => p.value);
  const min = Math.min(6, ...vals) - 0.5;
  const max = Math.max(...vals) + 0.5;
  const x = (i) => P + (i * (W - 2 * P)) / Math.max(points.length - 1, 1);
  const y = (v) => H - P - ((v - min) * (H - 2 * P)) / (max - min);
  const targetY = y(7);
  const path = points.map((p, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(p.value).toFixed(1)}`).join(" ");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img" aria-label="HbA1c trend chart">
      <line x1={P} x2={W - P} y1={targetY} y2={targetY} className="target" />
      <text x={W - P} y={targetY - 5} textAnchor="end" className="axis">target 7%</text>
      <path d={path} className="line" />
      {points.map((p, i) => (
        <g key={`${p.date}-${i}`}>
          <circle cx={x(i)} cy={y(p.value)} r="5" className={`dot ${p.value <= 7 ? "good" : p.value <= 8 ? "watch" : "alert"}`} />
          <text x={x(i)} y={y(p.value) - 10} textAnchor="middle" className="val">{p.value}</text>
          <text x={x(i)} y={H - 8} textAnchor="middle" className="axis">{p.date.slice(2, 7)}</text>
        </g>
      ))}
    </svg>
  );
}

// ── Date helpers ──────────────────────────────────────────────
export function formatDate(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}

function formatDateShort(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  const day = d.getDate();
  const mon = d.toLocaleDateString("en-IN", { month: "short" });
  const yr  = String(d.getFullYear()).slice(2);
  return `${day} ${mon}\n'${yr}`;
}
