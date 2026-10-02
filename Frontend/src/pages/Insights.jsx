import { useEffect, useRef } from "react";
import { gsap } from "gsap";
import { getHealthCheck, getInsights } from "../api/client.js";
import { useReveal } from "../anim.js";
import { HealthCheckPanel, TrendChart, VitalsForm, useChartSeries } from "../components/health.jsx";
import { Loading, Status, formatDate } from "../components/ui.jsx";
import { useT } from "../i18n.js";
import { useApi } from "../useApi.js";

// ── Premium HbA1c chart ───────────────────────────────────────
function HbA1cChart({ points }) {
  const svgRef = useRef(null);

  useEffect(() => {
    const svg = svgRef.current;
    if (!svg || !points?.length) return;

    const trendLine = svg.querySelector(".trend-line");
    const dots  = svg.querySelectorAll(".data-dot");
    const vals  = svg.querySelectorAll(".val-label");
    const dates = svg.querySelectorAll(".date-label");

    if (trendLine) {
      const len = trendLine.getTotalLength?.() || 400;
      gsap.set(trendLine, { strokeDasharray: len, strokeDashoffset: len });
    }
    gsap.set(dots,  { scale: 0, opacity: 0, transformOrigin: "center center" });
    gsap.set(vals,  { opacity: 0, y: 4 });
    gsap.set(dates, { opacity: 0, y: -4 });

    const tl = gsap.timeline({ delay: 0.05 });
    if (trendLine) tl.to(trendLine, { strokeDashoffset: 0, duration: 0.9, ease: "power2.inOut" }, 0);
    tl.to(dots,  { scale: 1, opacity: 1, duration: 0.28, stagger: 0.1,  ease: "back.out(2)" },  0.6);
    tl.to(vals,  { opacity: 1, y: 0, duration: 0.25, stagger: 0.08, ease: "power2.out" },  0.8);
    tl.to(dates, { opacity: 1, y: 0, duration: 0.2,  stagger: 0.08, ease: "power2.out" },  0.9);

    return () => tl.kill();
  }, [points]);

  if (!points?.length) return null;

  // Chart layout constants
  const W = 520, H = 200;
  const PL = 46, PR = 32, PT = 38, PB = 40;
  const cw = W - PL - PR;
  const ch = H - PT - PB;

  const rawVals = points.map((p) => p.value);
  const minV = Math.min(6.2, ...rawVals) - 0.3;
  const maxV = Math.max(...rawVals) + 0.5;

  const cx = (i) => PL + (i * cw) / Math.max(points.length - 1, 1);
  const cy = (v) => PT + ch - ((v - minV) * ch) / (maxV - minV);

  const targetV = 7.0;
  const targetY = cy(targetV);

  // Smooth path
  const pathD = points
    .map((p, i) => `${i === 0 ? "M" : "L"}${cx(i).toFixed(1)},${cy(p.value).toFixed(1)}`)
    .join(" ");

  // Area fill path
  const areaD = `${pathD} L${cx(points.length - 1).toFixed(1)},${(H - PB).toFixed(1)} L${PL.toFixed(1)},${(H - PB).toFixed(1)} Z`;

  const dotClass = (v) => v <= 7.0 ? "good" : v <= 8.0 ? "watch" : "alert";

  // Axis grid lines (only within chart range, avoid cluttering target)
  const gridVals = [7, 7.5, 8, 8.5, 9].filter((v) => v > minV && v < maxV && Math.abs(v - targetV) > 0.15);

  return (
    <svg
      ref={svgRef}
      viewBox={`0 0 ${W} ${H}`}
      className="hba1c-chart"
      role="img"
      aria-label="HbA1c trend over time"
    >
      {/* Subtle horizontal grid */}
      {gridVals.map((v) => {
        const yy = cy(v);
        return (
          <g key={v}>
            <line
              x1={PL} y1={yy} x2={W - PR} y2={yy}
              className="grid-line"
            />
            <text x={PL - 6} y={yy} className="axis-label">{v}</text>
          </g>
        );
      })}

      {/* Target 7% line */}
      <line x1={PL} y1={targetY} x2={W - PR} y2={targetY} className="target-line" />
      <text x={W - PR + 4} y={targetY - 3} className="target-label">7%</text>
      <text x={W - PR + 4} y={targetY + 10} className="target-label" style={{ fontSize: "8px", opacity: 0.7 }}>target</text>

      {/* Area fill */}
      <path d={areaD} className="trend-area" />

      {/* Trend line */}
      <path d={pathD} className="trend-line" />

      {/* Data points */}
      {points.map((p, i) => {
        const px = cx(i);
        const py = cy(p.value);
        const isLast = i === points.length - 1;
        const cls = dotClass(p.value);

        // Avoid label overlap with target line
        const labelY = Math.abs(py - targetY) < 20
          ? (py < targetY ? py - 18 : py - 18)
          : py - 16;

        return (
          <g key={`${p.date}-${i}`}>
            <text
              x={px} y={labelY}
              className={`val-label ${cls}`}
              fontSize={isLast ? "13" : "11"}
              fontWeight={isLast ? "700" : "600"}
            >
              {p.value}%
            </text>
            <circle
              cx={px} cy={py}
              r={isLast ? 6.5 : 5}
              className={`data-dot ${cls}`}
            />
            <text
              x={px} y={H - PB + 18}
              className="date-label"
            >
              {p.date.slice(2, 7)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

// ── Lab result row ────────────────────────────────────────────
function LabRow({ l }) {
  const statusColor = { good: "var(--success)", watch: "var(--warning)", alert: "var(--danger)" };
  return (
    <tr>
      <td className="labs-name">{l.name}</td>
      <td className="labs-value">
        <span style={{ color: statusColor[l.status] || "var(--text)", fontWeight: 600 }}>{l.value}</span>
        <span className="text-dim" style={{ fontSize: "var(--font-xs)", marginLeft: 4 }}>{l.unit}</span>
      </td>
      <td className="labs-range">{l.range}</td>
      <td><Status value={l.status} /></td>
      <td className="text-dim" style={{ fontSize: "var(--font-xs)" }}>{formatDate(l.date)}</td>
    </tr>
  );
}

// ── Condition card ────────────────────────────────────────────
function ConditionCard({ c }) {
  const { t } = useT();
  const statusEmoji = { good: "🟢", watch: "🟠", alert: "🔴" };
  return (
    <div className="card-sm" style={{ display: "flex", alignItems: "center", gap: "var(--sp-3)" }}>
      <span style={{ fontSize: "1rem", flexShrink: 0 }} aria-hidden="true">
        {statusEmoji[c.status] || "🔵"}
      </span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontWeight: "var(--fw-medium)" }}>{c.name}</div>
        {c.since && (
          <div className="text-dim" style={{ fontSize: "var(--font-xs)", marginTop: 2 }}>
            {t("since")} {c.since}
          </div>
        )}
      </div>
      {c.status && <Status value={c.status} />}
    </div>
  );
}

// ── InsightsView (shared with Snapshot) ──────────────────────
export function InsightsView({ data }) {
  const { t, pick } = useT();
  const charts = useChartSeries(data);
  const gridRef = useReveal([charts.length], { selector: ".trend-card", stagger: 0.07 });
  const conditions = (data.conditions || []).map((c) => (typeof c === "string" ? { name: c } : c));
  return (
    <div className="stack-lg">
      {data.summary && (
        <p className="lead">{pick(data, "summary")}</p>
      )}

      {/* HbA1c chart */}
      {data.hba1c?.length > 0 && (
        <div className="section" style={{ marginTop: 0, marginBottom: 0 }}>
          <h3>{t("sugarTrend")}</h3>
          <div className="card" style={{ padding: "var(--sp-5) var(--sp-4) var(--sp-3)" }}>
            <HbA1cChart points={data.hba1c} />
          </div>
        </div>
      )}

      {/* Every other test with 2+ results */}
      {charts.length > 0 && (
        <div className="section" style={{ marginTop: 0, marginBottom: 0 }}>
          <h3>Trends</h3>
          <div ref={gridRef} className="trend-grid">
            {charts.map((s) => (
              <TrendChart key={s.code} series={s} status={data.labs?.find((l) => l.code === s.code)?.status} />
            ))}
          </div>
        </div>
      )}

      {/* Labs table */}
      {data.labs?.length > 0 && (
        <div className="section" style={{ marginTop: 0, marginBottom: 0 }}>
          <h3>{t("latestLabs")}</h3>
          <div className="card table-wrap" style={{ padding: 0, overflow: "auto" }}>
            <table className="labs">
              <thead>
                <tr>
                  <th>Test</th>
                  <th>Value</th>
                  <th>Range</th>
                  <th>Status</th>
                  <th>Date</th>
                </tr>
              </thead>
              <tbody>
                {data.labs.map((l) => <LabRow key={l.code} l={l} />)}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Conditions */}
      {conditions.length > 0 && (
        <div className="section" style={{ marginTop: 0, marginBottom: 0 }}>
          <h3>{t("conditions")}</h3>
          <div className="list">
            {conditions.map((c) => <ConditionCard key={c.name} c={c} />)}
          </div>
        </div>
      )}
    </div>
  );
}

export default function Insights() {
  const { t, lang } = useT();
  const ml = lang === "ml";
  const { data, loading, error, reload } = useApi(getInsights);
  const health = useApi(getHealthCheck);
  if (loading || error) return <Loading error={error} onRetry={reload} />;
  return (
    <>
      <div className="page-header"><h2>{t("insights")}</h2></div>
      <div className="insights-top">
        <section className="section" style={{ marginTop: 0 }}>
          <h3>{t("healthCheck")}</h3>
          {health.loading || health.error ? <Loading error={health.error} onRetry={health.reload} /> : <HealthCheckPanel data={health.data} />}
        </section>
        <section className="section" style={{ marginTop: 0 }}>
          <h3>{ml ? "വീട്ടിലെ റീഡിംഗ് ചേർക്കുക" : "Add a home reading"}</h3>
          <VitalsForm onSaved={() => { reload(); health.reload(); }} />
        </section>
      </div>
      <InsightsView data={data} />
    </>
  );
}
