import { useState } from "react";
import { getTimeline } from "../api/client.js";
import { Empty } from "../components/ui.jsx";
import HealthThread from "../components/thread.jsx";
import { useT } from "../i18n.js";
import { useApi } from "../useApi.js";

const FILTERS = ["all", "prescription", "lab", "consultation", "vitals"];

function ThreadSkeleton() {
  return (
    <div className="thread" role="status" aria-label="Building your health story…" style={{ "--thread-scale": 1 }}>
      {[0, 1, 2, 3].map((i) => (
        <div key={i} className="thread-item" style={{ opacity: 0.6 }}>
          <span className="thread-node" aria-hidden="true" />
          <div className="skeleton skeleton-text" style={{ width: 90, height: 11, marginBottom: 10 }} />
          <div className="skeleton skeleton-text" style={{ width: "55%", height: 18, marginBottom: 8 }} />
          <div className="skeleton skeleton-text" style={{ width: "80%", height: 11 }} />
        </div>
      ))}
    </div>
  );
}

export default function Timeline() {
  const { t } = useT();
  const { data, loading, error, reload } = useApi(getTimeline);
  const [filter, setFilter] = useState("all");

  const docs = !data ? [] : filter === "all"
    ? data
    : data.filter((d) => d.type === filter || (filter === "consultation" && d.type === "visit"));

  return (
    <>
      <header className="ph" style={{ paddingTop: "clamp(20px,4vw,40px)" }}>
        <div className="ed-kicker">{t("timeline")}</div>
        <h1 className="ph-greet">Your health <span className="nm">thread</span>.</h1>
        <p className="ph-sub" style={{ marginTop: "var(--sp-3)" }}>
          {data ? `${data.length} records woven into one story — newest first.` : "Your records, connected."}
        </p>
      </header>

      <div className="chips" role="group" aria-label="Filter records" style={{ marginTop: "var(--sp-5)" }}>
        {FILTERS.map((f) => (
          <button key={f} className={`chip${f === filter ? " on" : ""}`} onClick={() => setFilter(f)} aria-pressed={f === filter}>
            {t(f)}
          </button>
        ))}
      </div>

      <div style={{ marginTop: "var(--sp-8)" }}>
        {loading ? (
          <ThreadSkeleton />
        ) : error ? (
          <div className="card-alert" style={{ borderRadius: "var(--r-lg)", padding: "var(--sp-5)" }}>
            <p className="text-alert font-medium text-sm">{error}</p>
            <button className="mt-3" onClick={reload}>Try again</button>
          </div>
        ) : docs.length === 0 ? (
          <Empty>
            {data.length === 0
              ? "No records yet. Tap Add to upload a prescription or lab report."
              : "No records of this kind yet."}
          </Empty>
        ) : (
          <HealthThread docs={docs} groupByYear />
        )}
      </div>
    </>
  );
}
