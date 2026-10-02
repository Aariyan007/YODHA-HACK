import { useCountUp } from "../anim.js";
import { LineChart } from "./charts.jsx";
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
    <div className="skeleton-stack" role="status" aria-live="polite">
      <span className="sr-only">{lang === "ml" ? "ലോഡ് ചെയ്യുന്നു…" : "Loading…"}</span>
      <div className="skeleton w-40" style={{ height: 28 }} aria-hidden="true" />
      <div className="skeleton w-70" aria-hidden="true" />
      <div className="skeleton card-shape" aria-hidden="true" />
      <div className="skeleton card-shape" aria-hidden="true" />
    </div>
  );
}

// ── Empty state ───────────────────────────────────────────────
export function Empty({ children }) {
  return (
    <div className="empty animate-in">
      <svg className="empty-mark" viewBox="0 0 64 64" aria-hidden="true">
        <circle cx="32" cy="32" r="26" className="em-ring" />
        <path d="M18 34h8l5-12 7 22 5-10h5" className="em-pulse" />
      </svg>
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
  return <LineChart points={points} code="hba1c" name="HbA1c" unit="%" target={7} size="lg" />;
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

// ── Animated number (GSAP count-up). Non-numbers are shown as-is. ──
export function CountUp({ value, decimals }) {
  const n = typeof value === "number" ? value : Number.NaN;
  const dec = decimals ?? (Number.isInteger(n) ? 0 : 1);
  const shown = useCountUp(Number.isNaN(n) ? null : n, { decimals: dec });
  return <>{Number.isNaN(n) ? value : shown}</>;
}
