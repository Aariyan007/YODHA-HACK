import { useState } from "react";
import { getHealthCheck, getInsights, getTimeline } from "../api/client.js";
import { useReveal, useScrollIn } from "../anim.js";
import { HealthCheckPanel, TrendChart, VitalsForm, useChartSeries } from "../components/health.jsx";
import { LineChart, Sparkline, changeSummary } from "../components/charts.jsx";
import { Loading, Status, formatDate } from "../components/ui.jsx";
import { useT } from "../i18n.js";
import { useApi } from "../useApi.js";
import { Chapter, RV } from "../design/primitives.jsx";
import ThreadExplorer from "../design/ThreadExplorer.jsx";

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
  const timeline = useApi(getTimeline);
  const [newId, setNewId] = useState(null);

  // After a reading is saved: refresh what depends on it and find the record that was just added to the thread.
  const onSaved = async () => {
    const before = new Set((timeline.data || []).map((d) => d.id));
    reload();
    health.reload();
    try {
      const next = await getTimeline();
      timeline.setData(next);
      setNewId(next.find((d) => !before.has(d.id))?.id || null);
    } catch { /* the thread refreshes on the next visit */ }
  };

  // Only block on the first load. Background reloads after saving must not unmount the form and lose its result.
  if (!data) return <Loading error={error} onRetry={reload} />;
  return (
    <div className="mt-page">
      <Chapter tone="ground">
        <RV className="mt-opening">
          <div className="mt-label">{ml ? "ആരോഗ്യ പരിശോധന" : "Health check"}</div>
          <h1 className="mt-display">{ml ? "ഇന്ന്, നിങ്ങളുടെ " : "Today, against your "}<em>{ml ? "കഥയോട് ചേർത്ത്" : "story"}</em>.</h1>
          <p className="mt-lede">{ml ? "ഇന്നത്തെ അളവ് നിങ്ങളുടെ ഹെൽത്ത് ത്രെഡുമായി MediThread താരതമ്യം ചെയ്യുന്നു."
            : "Add a reading. MediThread compares it with your previous record, explains the change, and adds it to your thread."}</p>
        </RV>
        <div className="mt-grid mt-gap-top">
          <RV className="c-7"><VitalsForm onSaved={onSaved} insights={data} /></RV>
          <RV className="c-5 mt-thread-side">
            <div className="mt-label mt-col-label">{ml ? "നിങ്ങളുടെ ത്രെഡ്" : "Your thread so far"}</div>
            {timeline.data ? <ThreadExplorer docs={timeline.data} limit={4} panel={false} newId={newId} moreHref="/timeline" moreLabel={ml ? "മുഴുവൻ ത്രെഡ്" : "Open the thread"} /> : <Loading />}
          </RV>
        </div>
      </Chapter>

      <Chapter tone="soft" no="01" kicker={ml ? "ഇത് എന്ത് അർത്ഥമാക്കുന്നു" : "What it means"} title={t("healthCheck")}>
        {health.loading && !health.data ? <Loading error={health.error} onRetry={health.reload} /> : <HealthCheckPanel data={health.data} />}
      </Chapter>

      <Chapter tone="warm" no="02" kicker={ml ? "ഫലങ്ങൾ" : "Results"} title={ml ? "ട്രെൻഡുകളും ഫലങ്ങളും" : "Trends and results"} last>
        <InsightsView data={data} />
      </Chapter>
    </div>
  );
}
