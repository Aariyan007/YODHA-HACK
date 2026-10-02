// Editorial building blocks for the MediThread redesign.
// Presentation only — every piece consumes the existing API data shapes.
import { useEffect, useRef, useState } from "react";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { Link } from "react-router-dom";
import { reducedMotion } from "../anim.js";
import { Sparkline } from "./charts.jsx";
import { useT } from "../i18n.js";

gsap.registerPlugin(ScrollTrigger);

const HIGHER_IS_BETTER = new Set(["spo2", "hdl", "hb"]);
const fmt = (v) => (Math.abs(v) >= 100 ? String(Math.round(v)) : String(Math.round(v * 10) / 10));

// ── Reveal: fade + rise an element when it scrolls into view ───────────────
export function Reveal({ children, className = "", y = 24, delay = 0, as: Tag = "div", stagger }) {
  const ref = useRef(null);
  useEffect(() => {
    const el = ref.current;
    if (!el || reducedMotion()) return;
    const ctx = gsap.context(() => {
      const targets = stagger ? el.children : el;
      gsap.fromTo(targets,
        { opacity: 0, y },
        {
          opacity: 1, y: 0, duration: 0.6, ease: "power3.out", delay,
          stagger: stagger || 0,
          scrollTrigger: { trigger: el, start: "top 90%", once: true },
          clearProps: "transform,opacity",
        });
    }, el);
    return () => ctx.revert();
  }, []);
  return <Tag ref={ref} className={`ed-reveal ${className}`}>{children}</Tag>;
}

// ── Editorial section with kicker + serif title ────────────────────────────
export function EdSection({ kicker, title, meta, action, children, id }) {
  return (
    <section className="ed-section" id={id}>
      {(title || kicker) && (
        <div className="ed-section-head">
          <div>
            {kicker && <div className="ed-kicker">{kicker}</div>}
            {title && <h3>{title}</h3>}
          </div>
          {(meta || action) && (
            <div className="row" style={{ gap: "var(--sp-4)", alignItems: "center" }}>
              {meta && <span className="ed-meta">{meta}</span>}
              {action}
            </div>
          )}
        </div>
      )}
      {children}
    </section>
  );
}

// ── Patient header: identity + context + overall status ────────────────────
export function PatientHeader({ name, subtitle, updatedAt, status }) {
  const root = useRef(null);
  useEffect(() => {
    if (!root.current || reducedMotion()) return;
    const ctx = gsap.context(() => {
      gsap.from(root.current.querySelectorAll("[data-ph]"),
        { y: 22, opacity: 0, duration: 0.7, stagger: 0.08, ease: "power3.out", clearProps: "all" });
    }, root);
    return () => ctx.revert();
  }, []);
  const STATUS = { good: "On track", watch: "Keep an eye", alert: "Needs attention" };
  const when = updatedAt
    ? new Date(updatedAt).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" })
    : null;
  return (
    <header ref={root} className="ph">
      <div className="ph-top">
        <h1 className="ph-greet" data-ph>
          {name ? <>Hello, <span className="nm">{name}</span>.</> : "Welcome."}
        </h1>
        {status && <span className={`ph-status ${status}`} data-ph>{STATUS[status] || status}</span>}
      </div>
      {subtitle && <p className="ph-sub" data-ph>{subtitle}</p>}
      {when && (
        <div className="ph-updated" data-ph>
          <span className="dot" aria-hidden="true" /> Last updated {when}
        </div>
      )}
    </header>
  );
}

// ── Current-state rail: inline numbers, dividers, no boxes ─────────────────
export function NowRail({ insights, reminders, warnings }) {
  const labs = insights?.labs || [];
  const get = (c) => labs.find((l) => l.code === c);
  const series = (c) => insights?.series?.find((s) => s.code === c)?.points;
  const a1c = get("hba1c"), sbp = get("sbp"), dbp = get("dbp");
  const total = reminders?.length ?? 0;
  const taken = reminders?.filter((r) => r.taken).length ?? 0;
  const bpStatus = [sbp?.status, dbp?.status].includes("alert") ? "alert"
    : [sbp?.status, dbp?.status].includes("watch") ? "watch" : sbp ? "good" : "";

  return (
    <Reveal className="now-rail" as="div" y={16} stagger={0.06}>
      {a1c && (
        <Link to="/insights" className="now-cell">
          <span className="now-label">Sugar average <span className={`now-tick ${a1c.status}`} /></span>
          <span className="now-value">{fmt(a1c.value)}<small>%</small></span>
          {series("hba1c") ? <span className="now-spark"><Sparkline points={series("hba1c")} code="hba1c" /></span>
            : <span className="now-foot">HbA1c</span>}
        </Link>
      )}
      {sbp && dbp && (
        <Link to="/insights" className="now-cell">
          <span className="now-label">Blood pressure <span className={`now-tick ${bpStatus}`} /></span>
          <span className="now-value">{sbp.value}<span className="slash">/</span>{dbp.value}<small>mmHg</small></span>
          <span className="now-foot">Target under 130 / 80</span>
        </Link>
      )}
      {total > 0 && (
        <Link to="/medicines" className="now-cell">
          <span className="now-label">Doses today {taken === total && <span className="now-tick" />}</span>
          <span className="now-value">{taken}<small>of {total}</small></span>
          <span className="now-foot">{taken === total ? "All done" : `${total - taken} left today`}</span>
        </Link>
      )}
      <Link to="/timeline" className="now-cell">
        <span className="now-label">Attention <span className={`now-tick ${warnings ? "watch" : ""}`} /></span>
        <span className="now-value">{warnings ?? 0}</span>
        <span className="now-foot">{warnings ? "See below" : "All clear"}</span>
      </Link>
    </Reveal>
  );
}

// ── What changed: a dominant delta + supporting deltas ─────────────────────
const CHANGE_ORDER = ["hba1c", "fbs", "ppbs", "rbs", "ldl", "sbp", "dbp", "creatinine", "tg"];
function computeDelta(s) {
  const pts = s?.points;
  if (!pts || pts.length < 2) return null;
  const from = pts[0].value, to = pts[pts.length - 1].value;
  const diff = Math.round((to - from) * 10) / 10;
  if (diff === 0) return { ...s, from, to, dir: "steady", tone: "steady", diff: 0, since: pts[0].date };
  const down = to < from;
  const better = HIGHER_IS_BETTER.has(s.code) ? !down : down;
  return { ...s, from, to, dir: down ? "down" : "up", tone: better ? "good" : "watch", diff: Math.abs(diff), since: pts[0].date, down };
}
const ARROW = { down: "↓", up: "↑", steady: "→" };

export function WhatChanged({ insights, review }) {
  const seriesMap = Object.fromEntries((insights?.series || []).map((s) => [s.code, s]));
  const deltas = CHANGE_ORDER.map((c) => computeDelta(seriesMap[c])).filter(Boolean);
  if (!deltas.length) return null;
  const hero = deltas[0];
  const rows = deltas.slice(1, 5);

  // Summary counts from the AI review points when present, else from deltas.
  const points = review?.points || [];
  const counts = points.length
    ? {
        good: points.filter((p) => p.kind === "better").length,
        watch: points.filter((p) => p.kind === "worse").length,
        missing: points.filter((p) => p.kind === "missing").length,
      }
    : {
        good: deltas.filter((d) => d.tone === "good").length,
        watch: deltas.filter((d) => d.tone === "watch").length,
        missing: 0,
      };

  const sinceText = (iso) => new Date(iso).toLocaleDateString("en-IN", { month: "short", year: "numeric" });

  return (
    <div className="changed-grid">
      <Reveal className="change-hero" y={24}>
        <div className="ch-name">{hero.name}</div>
        <div className="ch-flow">
          <span className="ch-from">{fmt(hero.from)}</span>
          <span className="ch-arrow" aria-hidden="true">→</span>
          <span className="ch-to">{fmt(hero.to)}<small>{hero.unit ? ` ${hero.unit}` : ""}</small></span>
        </div>
        <div className={`ch-delta ${hero.tone}`}>
          <span aria-hidden="true">{ARROW[hero.dir]}</span>
          {hero.dir === "steady" ? "No change"
            : `${hero.down ? "Down" : "Up"} ${fmt(hero.diff)}${hero.unit === "%" ? "%" : ` ${hero.unit || ""}`}`}
          {hero.tone === "good" ? " · improving" : hero.tone === "watch" ? " · watch" : ""}
        </div>
        <div className="ch-span">Since {sinceText(hero.since)}</div>
      </Reveal>

      <div>
        <Reveal className="change-list" stagger={0.07} y={16}>
          {rows.map((d) => (
            <div className="change-row" key={d.code}>
              <span className="cr-name">{d.name}</span>
              <span className="cr-flow">
                <span className="from">{fmt(d.from)}</span>
                <span className="arrow" aria-hidden="true">→</span>
                {fmt(d.to)}{d.unit && d.unit !== "%" ? ` ${d.unit}` : d.unit === "%" ? "%" : ""}
              </span>
              <span className={`cr-dir ${d.tone}`} aria-hidden="true">{ARROW[d.dir]}</span>
            </div>
          ))}
        </Reveal>

        <div className="changed-summary">
          {counts.good > 0 && (
            <div className="cs-item good"><span className="cs-n">{counts.good}</span><span className="cs-l">{counts.good === 1 ? "improvement" : "improvements"}</span></div>
          )}
          {counts.watch > 0 && (
            <div className="cs-item watch"><span className="cs-n">{counts.watch}</span><span className="cs-l">{counts.watch === 1 ? "value needs attention" : "values need attention"}</span></div>
          )}
          {counts.missing > 0 && (
            <div className="cs-item missing"><span className="cs-n">{counts.missing}</span><span className="cs-l">{counts.missing === 1 ? "record missing" : "records missing"}</span></div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── AI insight: interpretation layer with progressive disclosure ───────────
const KIND_ICON = { better: "↘", worse: "↗", steady: "→", missing: "?", info: "•" };
export function AIInsight({ review, recordCount }) {
  const { lang, pick } = useT();
  const ml = lang === "ml";
  const [open, setOpen] = useState(false);
  if (!review) return null;
  const isAi = review.source === "ai";
  const asks = review.askDoctor || [];
  return (
    <Reveal className="ai-insight" y={20}>
      <span className={`ai-tag ${isAi ? "" : "rules"}`}>
        <svg className="spark" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
          <path d="M8 0l1.6 4.8L14.4 6.4 9.6 8 8 12.8 6.4 8 1.6 6.4 6.4 4.8z" />
        </svg>
        {isAi ? (ml ? "AI വായന" : "AI health review") : (ml ? "നിയമ പരിശോധന" : "Rule-based review")}
      </span>
      <p className="ai-headline-ed">{pick(review, "headline")}</p>
      {review.points?.length > 0 && (
        <ul className="ai-reading">
          {review.points.map((p, i) => (
            <li key={i} className={p.kind}>
              <span className="ar-icon" aria-hidden="true">{KIND_ICON[p.kind] || "•"}</span>
              <span>{pick(p, "text")}</span>
            </li>
          ))}
        </ul>
      )}
      <div className="ai-based">
        {recordCount > 0 && <span className="ab-count">{ml ? `${recordCount} രേഖകളിൽ നിന്ന്` : `Based on ${recordCount} medical records`}</span>}
        {asks.length > 0 && (
          <button className="ed-link" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
            {open ? (ml ? "മറയ്ക്കുക" : "Hide evidence") : (ml ? "തെളിവ് കാണുക" : "View evidence")} →
          </button>
        )}
      </div>
      {open && asks.length > 0 && (
        <div className="ai-evidence animate-in-fast">
          <div className="ed-kicker bare" style={{ margin: "4px 0 2px" }}>{ml ? "ഡോക്ടറോട് ചോദിക്കാൻ" : "Questions to ask your doctor"}</div>
          {asks.map((q, i) => <p key={i} className="ask-q-ed">“{pick(q, "text")}”</p>)}
        </div>
      )}
      <p className="ai-disclaim">
        {ml ? "ഇത് രോഗനിർണയമല്ല. സ്വയം മരുന്ന് മാറ്റരുത്; ഡോക്ടറോട് ചോദിക്കുക."
            : "Not a diagnosis. Never change a medicine on your own; ask your doctor."}
      </p>
    </Reveal>
  );
}

// ── Attention: compact clinical rows ───────────────────────────────────────
export function Attention({ alerts = [] }) {
  const { pick, lang } = useT();
  const ml = lang === "ml";
  if (!alerts.length) {
    return (
      <div className="attn-ok">
        <span className="ok-dot" aria-hidden="true" />
        {ml ? "ഇപ്പോൾ മുന്നറിയിപ്പുകളൊന്നുമില്ല." : "Nothing needs your attention right now."}
      </div>
    );
  }
  return (
    <Reveal className="attn-list" stagger={0.06} y={14}>
      {alerts.map((a) => (
        <div key={a.id} className={`attn ${a.severity === "high" ? "high" : ""}`}>
          <span className="attn-mark" aria-hidden="true">!</span>
          <div className="attn-body">
            <div className="attn-kind">{a.kind}</div>
            <div className="attn-title">{a.title}</div>
            <p className="attn-msg">{pick(a, "message")}</p>
          </div>
          <span className={`attn-sev ${a.severity === "high" ? "high" : ""}`}>{a.severity}</span>
        </div>
      ))}
    </Reveal>
  );
}

// ── Medication timeline: a dose time-rail ──────────────────────────────────
export function MedTimeline({ reminders = [], onTake }) {
  const { t, lang } = useT();
  const ml = lang === "ml";
  const total = reminders.length;
  const taken = reminders.filter((r) => r.taken).length;
  const barRef = useRef(null);
  useEffect(() => {
    if (!barRef.current) return;
    const pct = total ? (taken / total) * 100 : 0;
    if (reducedMotion()) { barRef.current.style.width = `${pct}%`; return; }
    const tw = gsap.fromTo(barRef.current, { width: "0%" }, { width: `${pct}%`, duration: 0.8, ease: "power3.out" });
    return () => tw.kill();
  }, [taken, total]);

  if (!total) return null;
  return (
    <div>
      <div className="med-progress">
        <span>{taken}/{total} {ml ? "കഴിച്ചു" : "taken"}</span>
        <span className="bar"><span ref={barRef} style={{ width: 0 }} /></span>
      </div>
      <ul className="med-rail" role="list">
        {reminders.map((r) => (
          <li key={r.key} className={`med-dose${r.taken ? " taken" : ""}`}>
            <span className="med-time">{r.time}</span>
            <span className="med-node" aria-hidden="true" />
            <div>
              <div className="med-name">{r.name}</div>
              {(r.dose || r.instructions) && (
                <div className="med-sub">{[r.dose, r.instructions].filter(Boolean).join(" · ")}</div>
              )}
            </div>
            {r.taken ? (
              <span className="med-status-taken">✓ {t("taken")}</span>
            ) : (
              <button className="ed-cta ghost" style={{ padding: "9px 16px", minHeight: 44 }} onClick={() => onTake(r.key)}>
                {t("markTaken")}
              </button>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
