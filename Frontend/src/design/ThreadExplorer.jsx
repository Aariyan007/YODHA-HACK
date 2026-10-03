// The Health Thread: MediThread's signature component.
//
// Wide screens: a compact vertical thread on the left; the record behind whichever node you hover or focus
// appears in an evidence panel beside it, joined to the node by a tether line. The panel moves with the node
// (transform only), so hovering never changes the height of anything.
// Narrow screens: tapping an event expands its record in place.
//
// A document preview elsewhere on the page can light up its node here (see threadLink in primitives.jsx).
import { Fragment, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { gsap } from "gsap";
import { Link } from "react-router-dom";
import { reducedMotion } from "../anim.js";
import { useT } from "../i18n.js";
import { Arrow, useLinkedDoc, useMedia } from "./primitives.jsx";
import { docFigures, eventTime, longDate, shortDate, yearOf } from "./data.js";

const clamp = (n, lo, hi) => Math.min(Math.max(n, lo), hi);

export function EvidenceBody({ doc, compact = false }) {
  const { t, pick } = useT();
  const time = eventTime(doc);
  const figures = docFigures(doc);
  const lines = doc.sourceDoc?.lines || [];
  return (
    <div className="mt-ev-body">
      <div className="mt-label">{t(doc.type)} · {shortDate(doc.date)}{time ? ` · ${time}` : ""}</div>
      {!compact && <h3 className="mt-ev-title">{doc.title}</h3>}
      {doc.source && <div className="mt-ev-src">{doc.source}</div>}
      {pick(doc, "summary") && <p className="mt-ev-sum">{pick(doc, "summary")}</p>}
      {figures.length > 0 && (
        <dl className="mt-ev-fig">
          {figures.slice(0, 8).map((f, i) => (
            <div key={i} className={`st-${f.status || "none"}`}>
              <dt>{f.name}</dt>
              <dd>
                {f.value}
                {f.status && f.status !== "good" && <small>{t(f.status)}</small>}
              </dd>
            </div>
          ))}
        </dl>
      )}
      {doc.followUp && (
        <div className="mt-ev-follow"><span className="mt-label">Follow-up</span>{doc.followUp}</div>
      )}
      {lines.length > 0 && (
        <details className="mt-ev-orig">
          <summary>Original text</summary>
          <pre>{lines.join("\n")}</pre>
        </details>
      )}
    </div>
  );
}

export default function ThreadExplorer({
  docs = [], limit, panel = true, initialId, newId, showToday = true, moreHref, moreLabel,
}) {
  const { t, lang } = useT();
  const sideBySide = useMedia("(min-width: 960px)") && panel;
  const list = useMemo(() => (limit ? docs.slice(0, limit) : docs), [docs, limit]);
  const listKey = list.map((d) => d.id).join("|");

  const [activeId, setActive] = useState(initialId || list[0]?.id);
  const [openId, setOpenId] = useState(initialId || null); // narrow screens: which event is expanded
  const linked = useLinkedDoc();

  useEffect(() => {
    if (initialId && list.some((d) => d.id === initialId)) {
      setActive(initialId);
      setOpenId(initialId);
      // "View evidence" on a Documents card only changes the URL hash on this same page, and the thread is far above it:
      // bring the record into view, or nothing visibly happens.
      const t = setTimeout(() => document.getElementById(`ev-${initialId}`)?.scrollIntoView({ behavior: reducedMotion() ? "auto" : "smooth", block: "center" }), 120);
      return () => clearTimeout(t);
    }
  }, [initialId, listKey]); // eslint-disable-line react-hooks/exhaustive-deps

  const shownId = linked && list.some((d) => d.id === linked) ? linked
    : list.some((d) => d.id === activeId) ? activeId : list[0]?.id;
  const shown = list.find((d) => d.id === shownId);

  const wrapRef = useRef(null);
  const panelRef = useRef(null);
  const nodes = useRef({});
  const [geo, setGeo] = useState({ y: 0, x: 0, nodeY: 0, w: 0, ready: false });
  const [revealed, setRevealed] = useState(false); // the panel and tether appear once the thread has finished drawing

  // Place the panel beside the active node and stretch the tether between them. Transforms only.
  const measure = () => {
    const wrap = wrapRef.current, pnl = panelRef.current, node = nodes.current[shownId];
    if (!sideBySide || !wrap || !pnl || !node) return;
    const w = wrap.getBoundingClientRect(), n = node.getBoundingClientRect();
    const col = wrap.querySelector(".mt-th")?.getBoundingClientRect();
    const nodeY = n.top - w.top + n.height / 2;
    // The tether is a bridge from the right edge of the active row to the panel, so it never crosses the text.
    const nodeX = (col ? col.right : n.right) - w.left;
    const y = clamp(nodeY - 44, 0, Math.max(0, w.height - pnl.offsetHeight));
    const tw = Math.max(0, pnl.offsetLeft - nodeX - 4);
    // Only update when something really moved, otherwise this effect would re-render forever.
    setGeo((g) => (g.ready && Math.abs(g.y - y) < 0.5 && Math.abs(g.x - nodeX) < 0.5 && Math.abs(g.nodeY - nodeY) < 0.5 && Math.abs(g.w - tw) < 0.5
      ? g : { y, x: nodeX, nodeY, w: tw, ready: true }));
  };
  const measureRef = useRef(measure);
  measureRef.current = measure;
  useLayoutEffect(() => { measure(); }, [shownId, sideBySide, listKey, lang]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!sideBySide) return;
    const ro = new ResizeObserver(() => measure());
    if (wrapRef.current) ro.observe(wrapRef.current);
    if (panelRef.current) ro.observe(panelRef.current);
    return () => ro.disconnect();
  }, [sideBySide, shownId, listKey]); // eslint-disable-line react-hooks/exhaustive-deps

  // The thread draws itself once when it scrolls into view: each rail segment, then its event, in order.
  useLayoutEffect(() => {
    const el = wrapRef.current;
    if (!el || reducedMotion() || typeof IntersectionObserver === "undefined") { setRevealed(true); return; }
    setRevealed(false);
    const evs = [...el.querySelectorAll(".mt-th-ev, .mt-th-today, .mt-th-year")];
    const segs = [...el.querySelectorAll(".mt-th-seg")];
    if (!evs.length) { setRevealed(true); return; }
    gsap.set(evs, { opacity: 0, y: 14 });
    gsap.set(segs, { scaleY: 0 });
    let tl;
    const io = new IntersectionObserver(([e]) => {
      if (!e.isIntersecting) return;
      io.disconnect();
      // The entrance moves events by 14px; measure again once they have settled so the tether lines up exactly.
      tl = gsap.timeline({ defaults: { ease: "power3.out" }, onComplete: () => { measureRef.current?.(); setRevealed(true); } });
      evs.forEach((ev, i) => {
        const seg = ev.querySelector(".mt-th-seg");
        tl.to(ev, { opacity: 1, y: 0, duration: 0.45, clearProps: "transform,opacity" }, i * 0.09);
        if (seg) tl.to(seg, { scaleY: 1, duration: 0.5, ease: "power2.inOut", clearProps: "transform" }, i * 0.09 + 0.05);
      });
    }, { threshold: 0.12, rootMargin: "0px 0px -6% 0px" });
    io.observe(el);
    return () => { io.disconnect(); tl?.kill(); gsap.set([...evs, ...segs], { clearProps: "transform,opacity" }); };
  }, [listKey]);

  if (!list.length) return null;

  let lastYear = null;
  const todayLabel = longDate(new Date().toISOString().slice(0, 10));

  return (
    <div className={`mt-tx${sideBySide ? " side" : ""}`} ref={wrapRef}>
      <ol className="mt-th" role="list">
        {showToday && (
          <li className="mt-th-today">
            <span className="mt-th-seg" aria-hidden="true" />
            <span className="mt-th-node big" aria-hidden="true" />
            <div className="mt-th-todaytxt">
              <span className="mt-label">Today</span>
              <span className="mt-th-todaydate">{todayLabel}</span>
            </div>
          </li>
        )}
        {list.map((doc) => {
          const y = yearOf(doc.date);
          const yearRow = y !== lastYear;
          lastYear = y;
          const active = shownId === doc.id;
          const open = openId === doc.id;
          const time = eventTime(doc);
          return (
            <Fragment key={doc.id}>
              {yearRow && <li className="mt-th-year" aria-hidden="true"><span>{y}</span></li>}
              <li
                id={`ev-${doc.id}`}
                className={`mt-th-ev cat-${doc.type}${active ? " is-active" : ""}${linked === doc.id ? " is-linked" : ""}${newId === doc.id ? " is-new" : ""}`}
                onMouseEnter={() => setActive(doc.id)}
              >
                <span className="mt-th-seg" aria-hidden="true" />
                <span className="mt-th-node" ref={(n) => { nodes.current[doc.id] = n; }} aria-hidden="true" />
                <button
                  type="button"
                  className="mt-th-head"
                  aria-expanded={sideBySide ? undefined : open}
                  aria-controls={sideBySide ? undefined : `evb-${doc.id}`}
                  onFocus={() => setActive(doc.id)}
                  onClick={() => { setActive(doc.id); if (!sideBySide) setOpenId(open ? null : doc.id); }}
                >
                  <span className="mt-th-meta">
                    <span className="mt-th-date">{shortDate(doc.date)}{time ? ` · ${time}` : ""}</span>
                    <span className="mt-th-type">{t(doc.type)}</span>
                    {newId === doc.id && <span className="mt-th-new">Just added</span>}
                  </span>
                  <span className="mt-th-title">{doc.title}</span>
                  {doc.source && <span className="mt-th-src">{doc.source}</span>}
                </button>
                {!sideBySide && open && (
                  <div id={`evb-${doc.id}`} className="mt-th-inline"><EvidenceBody doc={doc} compact /></div>
                )}
              </li>
            </Fragment>
          );
        })}
      </ol>

      {moreHref && (
        <Link className="mt-link mt-th-more" to={moreHref}>{moreLabel || "See the full thread"} <Arrow /></Link>
      )}

      {sideBySide && shown && (
        <>
          <span
            className="mt-tether"
            aria-hidden="true"
            style={{ transform: `translate(${geo.x}px, ${geo.nodeY}px)`, width: geo.w, opacity: geo.ready && revealed ? 1 : 0 }}
          />
          <aside
            className="mt-ev"
            ref={panelRef}
            aria-live="polite"
            aria-label="Record details"
            style={{ transform: `translateY(${geo.y}px)`, opacity: geo.ready && revealed ? 1 : 0 }}
          >
            <EvidenceBody key={shown.id} doc={shown} />
          </aside>
        </>
      )}
    </div>
  );
}
