import { useEffect, useRef, useState } from "react";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { getTimeline } from "../api/client.js";
import { Empty, TimelineItem } from "../components/ui.jsx";
import { useT } from "../i18n.js";
import { useApi } from "../useApi.js";

gsap.registerPlugin(ScrollTrigger);

const FILTERS = ["all", "prescription", "lab", "consultation", "vitals"];

// ── Thread skeleton loading state ─────────────────────────────
function TimelineSkeleton() {
  return (
    <div className="tl-skeleton" role="status" aria-label="Loading your health story…">
      <div className="tl-skeleton-label">
        Building your health story…
      </div>
      <div className="tl-skeleton-thread">
        {/* Animated thread line */}
        <div className="tl-sk-line" aria-hidden="true" />

        {/* Skeleton nodes + cards */}
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="tl-sk-row" style={{ animationDelay: `${i * 0.15}s` }}>
            <div className="tl-sk-date">
              <div className="skeleton skeleton-text" style={{ width: 42, height: 12 }} />
              <div className="skeleton skeleton-text" style={{ width: 28, height: 10, marginTop: 4 }} />
            </div>
            <div className="tl-sk-node" aria-hidden="true" />
            <div className="tl-sk-card">
              <div className="skeleton skeleton-text" style={{ width: "60%", height: 14, marginBottom: 8 }} />
              <div className="skeleton skeleton-text" style={{ width: "90%", height: 11, marginBottom: 6 }} />
              <div className="skeleton skeleton-text" style={{ width: "75%", height: 11 }} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Error state ───────────────────────────────────────────────
function TimelineError({ error, onRetry }) {
  return (
    <div className="card-alert" style={{ borderRadius: "var(--r-lg)", padding: "var(--sp-5)" }}>
      <p className="text-alert font-medium text-sm">{error}</p>
      {onRetry && <button className="mt-3" onClick={onRetry}>Try again</button>}
    </div>
  );
}

export default function Timeline() {
  const { t } = useT();
  const { data, loading, error, reload } = useApi(getTimeline);
  const [filter, setFilter] = useState("all");
  const listRef = useRef(null);

  // Scroll-triggered reveal on data load
  useEffect(() => {
    if (!listRef.current || !data?.length) return;
    const items = listRef.current.querySelectorAll(".tl-item");
    items.forEach((el, i) => {
      gsap.fromTo(el,
        { opacity: 0, x: -8 },
        {
          opacity: 1, x: 0,
          duration: 0.3, ease: "power2.out",
          delay: Math.min(i * 0.05, 0.4),
          scrollTrigger: { trigger: el, start: "top 94%", once: true },
        }
      );
    });
    return () => ScrollTrigger.getAll().forEach((t) => t.kill());
  }, [data, filter]);

  const docs = !data ? [] : filter === "all"
    ? data
    : data.filter((d) => d.type === filter || (filter === "consultation" && d.type === "visit"));

  return (
    <>
      {/* Header — always visible immediately */}
      <div className="page-header">
        <h2>{t("timeline")}</h2>
        {data && <span className="text-dim text-sm">{data.length} records</span>}
      </div>

      {/* Filter chips — always visible */}
      <div className="chips" role="group" aria-label="Filter records">
        {FILTERS.map((f) => (
          <button
            key={f}
            id={`filter-${f}`}
            className={`chip${f === filter ? " on" : ""}`}
            onClick={() => setFilter(f)}
            aria-pressed={f === filter}
          >
            {t(f)}
          </button>
        ))}
      </div>

      {/* Content area */}
      {loading ? (
        <TimelineSkeleton />
      ) : error ? (
        <TimelineError error={error} onRetry={reload} />
      ) : docs.length === 0 ? (
        <Empty icon="📋">
          {data.length === 0
            ? "No records yet. Tap Add to upload a prescription or lab report."
            : "No records of this kind yet."}
        </Empty>
      ) : (
        <div style={{ position: "relative" }}>
          <ul className="timeline animate-in" ref={listRef} role="list">
            {docs.map((d) => (
              <TimelineItem key={d.id} doc={d} />
            ))}
          </ul>
        </div>
      )}
    </>
  );
}
