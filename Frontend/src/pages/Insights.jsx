import { getHealthCheck, getInsights } from "../api/client.js";
import { useReveal, useScrollIn } from "../anim.js";
import { HealthCheckPanel, TrendChart, VitalsForm, useChartSeries } from "../components/health.jsx";
import { LineChart, Sparkline, changeSummary } from "../components/charts.jsx";
import { Loading, Status, formatDate } from "../components/ui.jsx";
import { useT } from "../i18n.js";
import { useApi } from "../useApi.js";

// ── Lab result row ────────────────────────────────────────────
function LabRow({ l, series }) {
  const statusColor = { good: "var(--success)", watch: "var(--warning)", alert: "var(--danger)" };
  return (
    <tr>
      <td className="labs-name">{l.name}</td>
      <td className="labs-value">
        <span style={{ color: statusColor[l.status] || "var(--text)", fontWeight: 600 }}>{l.value}</span>
        <span className="text-dim" style={{ fontSize: "var(--font-xs)", marginLeft: 4 }}>{l.unit}</span>
      </td>
      <td className="labs-spark">{series ? <Sparkline points={series.points} code={l.code} /> : null}</td>
      <td className="labs-range">{l.range}</td>
      <td><Status value={l.status} /></td>
      <td className="text-dim" style={{ fontSize: "var(--font-xs)" }}>{formatDate(l.date)}</td>
    </tr>
  );
}

// ── Condition clinical tag ────────────────────────────────────
// Shows only data that exists (name, optional status, optional since).
// No invented medical metadata.
function ConditionCard({ c }) {
  const { t, lang } = useT();
  const ml = lang === "ml";
  const tag = c.status ? t(c.status) : (ml ? "സജീവം" : "Active");
  const meta = c.since
    ? `${ml ? "മുതൽ" : "Since"} ${c.since}`
    : (ml ? "രേഖയിൽ" : "On record");
  return (
    <li className="cond-item">
      <span className={`cond-dot ${c.status || ""}`} aria-hidden="true" />
      <div className="cond-body">
        <span className="cond-name" title={c.name}>{c.name}</span>
        <span className="cond-meta">{meta}</span>
      </div>
      <span className={`cond-tag ${c.status || ""}`}>{tag}</span>
    </li>
  );
}

// ── InsightsView (shared with Snapshot) ──────────────────────
export function InsightsView({ data }) {
  const { t, pick } = useT();
  const charts = useChartSeries(data);
  const gridRef = useReveal([charts.length], { selector: ".trend-card", stagger: 0.07 });
  const viewRef = useScrollIn([data], { selector: ":scope > .section" });
  const conditions = (data.conditions || []).map((c) => (typeof c === "string" ? { name: c } : c));
  return (
    <div className="stack-lg" ref={viewRef}>
      {data.summary && (
        <p className="lead">{pick(data, "summary")}</p>
      )}

      {/* HbA1c chart */}
      {data.hba1c?.length > 0 && (
        <div className="section" style={{ marginTop: 0, marginBottom: 0 }}>
          <h3>{t("sugarTrend")}</h3>
          <div className="card chart-card">
            {(() => {
              const sum = changeSummary(data.hba1c, "hba1c", "%");
              return sum ? <span className={`chart-chip ${sum.tone}`}>{sum.text}</span> : null;
            })()}
            <LineChart points={data.hba1c} code="hba1c" name="HbA1c" unit="%" target={7} size="lg" />
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
                  <th><span className="sr-only">Trend</span></th>
                  <th>Range</th>
                  <th>Status</th>
                  <th>Date</th>
                </tr>
              </thead>
              <tbody>
                {data.labs.map((l) => <LabRow key={l.code} l={l} series={data.series?.find((x) => x.code === l.code)} />)}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Conditions */}
      {conditions.length > 0 && (
        <div className="section" style={{ marginTop: 0, marginBottom: 0 }}>
          <h3>{t("conditions")}</h3>
          <ul className="cond-grid">
            {conditions.map((c) => <ConditionCard key={c.name} c={c} />)}
          </ul>
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
  // Only block on the first load; background reloads (after saving a reading)
  // must not unmount the form and lose its comparison result.
  if (!data) return <Loading error={error} onRetry={reload} />;
  return (
    <>
      <header className="ph" style={{ paddingTop: "clamp(20px,4vw,40px)" }}>
        <div className="ed-kicker">{ml ? "ആരോഗ്യ പരിശോധന" : "Health check"}</div>
        <h1 className="ph-greet">{ml ? "ഇന്ന്, നിങ്ങളുടെ " : "Today, against your "}<span className="nm">{ml ? "കഥയോട് ചേർത്ത്" : "story"}</span>.</h1>
        <p className="ph-sub" style={{ marginTop: "var(--sp-3)" }}>
          {ml ? "ഇന്നത്തെ അളവ് നിങ്ങളുടെ ഹെൽത്ത് ത്രെഡുമായി MediThread താരതമ്യം ചെയ്യുന്നു."
              : "MediThread connects today's measurement to your health thread."}
        </p>
      </header>

      <section className="ed-section" style={{ marginTop: "clamp(28px,4vw,44px)" }}>
        <VitalsForm onSaved={() => { reload(); health.reload(); }} insights={data} />
      </section>

      <section className="ed-section">
        <div className="ed-section-head">
          <div><div className="ed-kicker">{ml ? "ഇത് എന്ത് അർത്ഥമാക്കുന്നു" : "What it means"}</div><h3>{t("healthCheck")}</h3></div>
        </div>
        {health.loading || health.error ? <Loading error={health.error} onRetry={health.reload} /> : <HealthCheckPanel data={health.data} />}
      </section>

      <InsightsView data={data} />
    </>
  );
}
