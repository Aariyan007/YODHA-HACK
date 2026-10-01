import { useT } from "../i18n.js";

export function Status({ value }) {
  const { t } = useT();
  return <span className={`pill ${value}`}>{t(value)}</span>;
}

export function Loading({ error, onRetry }) {
  const { t, lang } = useT();
  if (error)
    return (
      <div role="alert">
        <p className="error">{error}</p>
        {onRetry && <button onClick={onRetry}>{lang === "ml" ? "വീണ്ടും ശ്രമിക്കുക" : "Try again"}</button>}
      </div>
    );
  return (
    <p className="muted" role="status">
      {t("loading")}
    </p>
  );
}

export function Empty({ children }) {
  return <p className="card muted">{children}</p>;
}

export function AlertCard({ alert }) {
  const { pick } = useT();
  return (
    <div className={`card alert-card ${alert.severity}`}>
      <div className="row between">
        <strong>{alert.title}</strong>
        <span className={`sev ${alert.severity}`}>{alert.severity}</span>
      </div>
      <p>{pick(alert, "message")}</p>
    </div>
  );
}

export function TimelineItem({ doc }) {
  const { t, pick } = useT();
  return (
    <li className={`tl-item ${doc.type}`}>
      <div className="tl-date">{formatDate(doc.date)}</div>
      <div className="card">
        <div className="row between">
          <strong>{doc.title}</strong>
          <span className="type">{t(doc.type)}</span>
        </div>
        {doc.source && <div className="muted small">{doc.source}</div>}
        <p>{pick(doc, "summary")}</p>
        {doc.items?.length > 0 && (
          <ul className="items">
            {doc.items.map((it, i) =>
              "value" in it ? (
                <li key={i}>
                  {it.name}: <b>{it.value}</b> {it.unit} <Status value={it.status} />
                </li>
              ) : (
                <li key={i}>
                  <b>{it.name}</b> · {it.dose} · {it.frequency} · {it.duration}
                </li>
              ),
            )}
          </ul>
        )}
      </div>
    </li>
  );
}

export function HbA1cChart({ points }) {
  if (!points?.length) return null;
  const W = 320, H = 140, P = 28;
  const vals = points.map((p) => p.value);
  const min = Math.min(6, ...vals) - 0.5;
  const max = Math.max(...vals) + 0.5;
  const x = (i) => P + (i * (W - 2 * P)) / Math.max(points.length - 1, 1);
  const y = (v) => H - P - ((v - min) * (H - 2 * P)) / (max - min);
  const targetY = y(7);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img" aria-label="HbA1c trend">
      <line x1={P} x2={W - P} y1={targetY} y2={targetY} className="target" />
      <text x={W - P} y={targetY - 4} textAnchor="end" className="axis">target 7%</text>
      <polyline points={points.map((p, i) => `${x(i)},${y(p.value)}`).join(" ")} className="line" />
      {points.map((p, i) => (
        <g key={`${p.date}-${i}`}>
          <circle cx={x(i)} cy={y(p.value)} r="4" className={p.value <= 7 ? "dot good" : p.value <= 8 ? "dot watch" : "dot alert"} />
          <text x={x(i)} y={y(p.value) - 9} textAnchor="middle" className="val">{p.value}</text>
          <text x={x(i)} y={H - 8} textAnchor="middle" className="axis">{p.date.slice(2, 7)}</text>
        </g>
      ))}
    </svg>
  );
}

export function formatDate(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}
