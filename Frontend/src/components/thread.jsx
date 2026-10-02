// HealthThread — MediThread's signature visual element.
// A thin vertical thread that draws itself on scroll and reveals nodes +
// events one by one. Consumes the same timeline doc shape as the old
// TimelineItem, so no data/logic changes.
import { useEffect, useRef } from "react";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { reducedMotion } from "../anim.js";
import { useT } from "../i18n.js";

gsap.registerPlugin(ScrollTrigger);

function shortDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleDateString("en-IN", { day: "numeric", month: "short" });
}
function yearOf(iso) {
  return iso ? new Date(iso).getFullYear() : "";
}
// Show the time only when a real timestamp exists and falls on the record's own
// date — so historical seed/upload times are never shown as the event time.
function timeIfSameDay(doc) {
  if (!doc.createdAt) return null;
  const c = new Date(doc.createdAt);
  if (Number.isNaN(c.getTime())) return null;
  const local = `${c.getFullYear()}-${String(c.getMonth() + 1).padStart(2, "0")}-${String(c.getDate()).padStart(2, "0")}`;
  if (doc.date && local !== doc.date) return null;
  return c.toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" });
}

function ThreadEvent({ doc, isLatest }) {
  const { t, pick } = useT();
  const items = doc.items || [];
  const time = timeIfSameDay(doc);
  return (
    <li className={`thread-item ${doc.type}${isLatest ? " today" : ""} thread-reveal`}>
      <span className="thread-node" aria-hidden="true" />
      <div className="thread-head">
        <span className="thread-date">{shortDate(doc.date)}{time ? ` · ${time}` : ""}</span>
        <span className="thread-type">{t(doc.type)}</span>
        {isLatest && <span className="thread-latest">Latest</span>}
      </div>
      <h4 className="thread-title">{doc.title}</h4>
      {doc.source && <div className="thread-source">{doc.source}</div>}
      {pick(doc, "summary") && <p className="thread-summary">{pick(doc, "summary")}</p>}
      {items.length > 0 && (
        <ul className="thread-data">
          {items.slice(0, 6).map((it, i) =>
            "value" in it ? (
              <li key={i}>
                <span className="k">{it.name}</span>
                <span className={`v ${it.status || ""}`}>{it.value}{it.unit ? ` ${it.unit}` : ""}</span>
              </li>
            ) : (
              <li key={i}>
                <span className="med">{it.name}{it.dose ? ` · ${it.dose}` : ""}</span>
              </li>
            )
          )}
          {items.length > 6 && <li><span className="k">+{items.length - 6} more</span></li>}
        </ul>
      )}
    </li>
  );
}

export default function HealthThread({ docs = [], limit, groupByYear = false }) {
  const ref = useRef(null);
  const list = limit ? docs.slice(0, limit) : docs;

  useEffect(() => {
    const root = ref.current;
    if (!root || reducedMotion() || !list.length) return;
    const ctx = gsap.context(() => {
      // Draw the thread line as it scrolls into view.
      const line = root.querySelector(".thread");
      if (line) {
        gsap.fromTo(line, { "--thread-scale": 0 }, {
          "--thread-scale": 1, ease: "none",
          scrollTrigger: { trigger: line, start: "top 80%", end: "bottom 70%", scrub: 0.6 },
        });
      }
      // Reveal each event in sequence.
      root.querySelectorAll(".thread-reveal").forEach((el) => {
        gsap.fromTo(el, { opacity: 0, y: 20 }, {
          opacity: 1, y: 0, duration: 0.55, ease: "power3.out",
          scrollTrigger: { trigger: el, start: "top 92%", once: true },
          clearProps: "transform,opacity",
        });
      });
    }, root);
    return () => ctx.revert();
  }, [list.length]);

  if (!list.length) return null;

  // Optional year dividers.
  let lastYear = null;
  return (
    <div ref={ref}>
      <ul className="thread" role="list" style={{ "--thread-scale": 1 }}>
        {list.map((doc, i) => {
          const y = yearOf(doc.date);
          const showYear = groupByYear && y !== lastYear;
          lastYear = y;
          return (
            <span key={doc.id ?? i} style={{ display: "contents" }}>
              {showYear && <li className="thread-year" aria-hidden="true">{y}</li>}
              <ThreadEvent doc={doc} isLatest={i === 0} />
            </span>
          );
        })}
      </ul>
    </div>
  );
}
