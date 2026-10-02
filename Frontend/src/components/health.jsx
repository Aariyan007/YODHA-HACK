import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { gsap } from "gsap";
import { addVitals } from "../api/client.js";
import { drawPath, pulse, reducedMotion, useReveal } from "../anim.js";
import { useT } from "../i18n.js";
import { CountUp } from "./ui.jsx";

const LEVEL_LABEL = {
  en: { emergency: "Urgent", high: "See a doctor soon", watch: "Keep an eye" },
  ml: { emergency: "അടിയന്തരം", high: "വേഗം ഡോക്ടറെ കാണുക", watch: "ശ്രദ്ധിക്കുക" },
};

export const doctorsLink = (specialty, extra = {}) => {
  const p = new URLSearchParams({ ...(specialty ? { specialty } : {}), ...extra });
  return `/doctors?${p.toString()}`;
};

// ── Emergency banner: always Python-driven, never waits for AI ───────────────
export function EmergencyBanner({ risk }) {
  const { lang, pick } = useT();
  const ref = useRef(null);
  useEffect(() => { pulse(ref.current, { scale: 1.015, repeat: 2 }); }, [risk?.key]);
  if (!risk) return null;
  const ml = lang === "ml";
  return (
    <div ref={ref} className="emergency-banner" role="alert">
      <div className="emergency-icon" aria-hidden="true">!</div>
      <div className="grow">
        <div className="emergency-title">{risk.title}</div>
        <p className="emergency-text">{pick(risk, "message")}</p>
        <div className="row" style={{ gap: "var(--sp-3)", marginTop: "var(--sp-3)", flexWrap: "wrap" }}>
          <a className="btn-emergency" href="tel:108">{ml ? "108 വിളിക്കുക" : "Call 108"}</a>
          <Link className="btn-ghost-light" to={doctorsLink("Emergency", { emergency: "1" })}>
            {ml ? "അടുത്തുള്ള ആശുപത്രി" : "Nearest hospital"}
          </Link>
        </div>
      </div>
    </div>
  );
}

// ── One risk ────────────────────────────────────────────────────────────────
export function RiskCard({ risk, showFinder = true }) {
  const { lang, pick } = useT();
  const ml = lang === "ml";
  return (
    <div className={`risk-card lvl-${risk.level}`}>
      <div className="row between" style={{ gap: "var(--sp-3)", alignItems: "flex-start" }}>
        <strong className="risk-title">{risk.title}</strong>
        <span className={`risk-level ${risk.level}`}>{LEVEL_LABEL[lang]?.[risk.level] || risk.level}</span>
      </div>
      <p className="risk-msg">{pick(risk, "message")}</p>
      {risk.evidence?.length > 0 && (
        <div className="evidence-row">
          {risk.evidence.map((e, i) => (
            <span key={i} className="evidence-chip">
              {e.name} <b>{e.value}</b> {e.unit} <span className="text-dim">· {e.date}</span>
            </span>
          ))}
        </div>
      )}
      {showFinder && risk.level !== "watch" && (
        <Link className="risk-cta" to={doctorsLink(risk.specialist, risk.emergency ? { emergency: "1" } : { reason: risk.reason })}>
          {risk.specialist === "Emergency"
            ? (ml ? "അടുത്തുള്ള അത്യാഹിത ആശുപത്രി →" : "Nearest emergency hospital →")
            : (ml ? `അടുത്തുള്ള ${risk.specialist} →` : `Find a ${risk.specialist.toLowerCase()} near me →`)}
        </Link>
      )}
    </div>
  );
}

const KIND_ICON = { worse: "↗", better: "↘", steady: "→", missing: "?", info: "•" };

// ── Risks + AI review, used on Home ────────────────────────────────────────
export function HealthCheckPanel({ data, compact = false }) {
  const { lang, pick } = useT();
  const ml = lang === "ml";
  const listRef = useReveal([data?.checkedAt], { selector: ".risk-card, .ai-point, .ask-q" });
  if (!data) return null;
  const { risks = [], review } = data;
  const emergency = risks.find((r) => r.emergency);
  const others = risks.filter((r) => r !== emergency);
  const shown = compact ? others.slice(0, 3) : others;
  return (
    <div ref={listRef} className="stack" style={{ gap: "var(--sp-4)" }}>
      {emergency && <EmergencyBanner risk={emergency} />}

      {review && (
        <div className="ai-review card">
          <div className="ai-review-head">
            <span className={`ai-badge ${review.source === "ai" ? "" : "rules"}`}>
              {review.source === "ai" ? (ml ? "AI വായന" : "AI read your record") : (ml ? "നിയമ പരിശോധന" : "Rule check")}
            </span>
          </div>
          <p className="ai-headline">{pick(review, "headline")}</p>
          {review.points?.length > 0 && (
            <ul className="ai-points">
              {review.points.map((p, i) => (
                <li key={i} className={`ai-point ${p.kind}`}>
                  <span className="ai-point-icon" aria-hidden="true">{KIND_ICON[p.kind] || "•"}</span>
                  <span>{pick(p, "text")}</span>
                </li>
              ))}
            </ul>
          )}
          {!compact && review.askDoctor?.length > 0 && (
            <div className="ask-box">
              <div className="ask-title">{ml ? "ഡോക്ടറോട് ചോദിക്കാൻ" : "Questions to ask your doctor"}</div>
              {review.askDoctor.map((q, i) => (
                <div key={i} className="ask-q">“{pick(q, "text")}”</div>
              ))}
            </div>
          )}
          <p className="text-dim text-xs" style={{ marginTop: "var(--sp-3)" }}>
            {ml ? "ഇത് രോഗനിർണയമല്ല. മരുന്ന് മാറ്റരുത്; ഡോക്ടറോട് ചോദിക്കുക."
                : "Not a diagnosis. Never change a medicine on your own; ask your doctor."}
          </p>
        </div>
      )}

      {shown.map((r) => <RiskCard key={r.key} risk={r} />)}
      {compact && others.length > shown.length && (
        <Link to="/insights" className="text-sm text-brand">
          {ml ? `${others.length - shown.length} കൂടി കാണുക →` : `See ${others.length - shown.length} more →`}
        </Link>
      )}
    </div>
  );
}

// ── Home reading form ──────────────────────────────────────────────────────
export function VitalsForm({ onSaved }) {
  const { lang } = useT();
  const ml = lang === "ml";
  const [v, setV] = useState({ sbp: "", dbp: "", pulse: "", spo2: "", sugar: "", sugarType: "rbs", weight: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const set = (k) => (e) => setV((s) => ({ ...s, [k]: e.target.value }));
  const num = (x) => (x === "" ? undefined : Number(x));

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const body = { sbp: num(v.sbp), dbp: num(v.dbp), pulse: num(v.pulse), spo2: num(v.spo2), weight: num(v.weight),
                     sugar: num(v.sugar), sugarType: v.sugarType };
      const res = await addVitals(body);
      setResult(res);
      setV({ sbp: "", dbp: "", pulse: "", spo2: "", sugar: "", sugarType: v.sugarType, weight: "" });
      onSaved?.(res);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const top = result?.risks?.[0];
  return (
    <form className="card vitals-form" onSubmit={submit} noValidate>
      <div className="vitals-grid">
        <label className="vital-field bp">
          <span>{ml ? "ബിപി (മുകളിൽ / താഴെ)" : "Blood pressure"}</span>
          <div className="bp-inputs">
            <input inputMode="numeric" placeholder="120" value={v.sbp} onChange={set("sbp")} aria-label="Systolic (top number)" />
            <span className="bp-slash">/</span>
            <input inputMode="numeric" placeholder="80" value={v.dbp} onChange={set("dbp")} aria-label="Diastolic (bottom number)" />
          </div>
        </label>
        <label className="vital-field">
          <span>{ml ? "നാഡിമിടിപ്പ്" : "Pulse"}</span>
          <input inputMode="numeric" placeholder="72" value={v.pulse} onChange={set("pulse")} />
        </label>
        <label className="vital-field">
          <span>SpO2 %</span>
          <input inputMode="numeric" placeholder="98" value={v.spo2} onChange={set("spo2")} />
        </label>
        <label className="vital-field">
          <span>{ml ? "പഞ്ചസാര" : "Sugar"} mg/dL</span>
          <div className="bp-inputs">
            <input inputMode="numeric" placeholder="110" value={v.sugar} onChange={set("sugar")} />
            <select value={v.sugarType} onChange={set("sugarType")} aria-label="Sugar test type">
              <option value="fbs">{ml ? "വെറുംവയറ്" : "Fasting"}</option>
              <option value="ppbs">{ml ? "ഭക്ഷണശേഷം" : "After food"}</option>
              <option value="rbs">{ml ? "ഏതുസമയം" : "Random"}</option>
            </select>
          </div>
        </label>
        <label className="vital-field">
          <span>{ml ? "ഭാരം" : "Weight"} kg</span>
          <input inputMode="decimal" placeholder="64" value={v.weight} onChange={set("weight")} />
        </label>
      </div>
      <div className="row" style={{ gap: "var(--sp-3)", marginTop: "var(--sp-4)", alignItems: "center" }}>
        <button className="primary" disabled={busy}>{busy ? "…" : ml ? "സേവ് ചെയ്ത് പരിശോധിക്കുക" : "Save and check"}</button>
        {error && <span className="error text-sm" role="alert">{error}</span>}
      </div>
      {result && (
        <div className="vitals-result animate-in-fast" role="status">
          {top?.emergency ? (
            <p className="error text-sm">{ml ? "സേവ് ചെയ്തു. ഈ റീഡിംഗ് അപകട നിലയിലാണ്: താഴെയുള്ള ചുവന്ന മുന്നറിയിപ്പ് കാണുക." : "Saved. This reading is in the danger zone: see the red alert."}</p>
          ) : top ? <RiskCard risk={top} /> : (
            <p className="text-good text-sm">{ml ? "സേവ് ചെയ്തു. ഈ റീഡിംഗിൽ അപകട സൂചനകളൊന്നുമില്ല." : "Saved. Nothing worrying in this reading."}</p>
          )}
        </div>
      )}
    </form>
  );
}

// ── Generic trend chart for any test ───────────────────────────────────────
const TARGETS = { hba1c: 7, sbp: 130, dbp: 80, fbs: 130, ppbs: 180, rbs: 160, ldl: 100, creatinine: 1.2, spo2: 95, pulse: 100 };

export function TrendChart({ series, status }) {
  const pathRef = useRef(null);
  const svgRef = useRef(null);
  const pts = series.points;
  useEffect(() => {
    const t = drawPath(pathRef.current, { duration: 0.9 });
    if (svgRef.current && !reducedMotion()) {
      gsap.from(svgRef.current.querySelectorAll(".tc-dot"), { scale: 0, transformOrigin: "center", duration: 0.3, stagger: 0.07, delay: 0.5, ease: "back.out(2)" });
    }
    return () => t?.kill();
  }, [series.code, pts.length]);
  const W = 320, H = 120, PL = 30, PR = 14, PT = 22, PB = 22;
  const vals = pts.map((p) => p.value);
  const target = TARGETS[series.code];
  const lo = Math.min(...vals, target ?? Infinity), hi = Math.max(...vals, target ?? -Infinity);
  const pad = (hi - lo) * 0.18 || 1;
  const min = lo - pad, max = hi + pad;
  const x = (i) => PL + (i * (W - PL - PR)) / Math.max(pts.length - 1, 1);
  const y = (v) => PT + (H - PT - PB) - ((v - min) * (H - PT - PB)) / (max - min);
  const d = pts.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.value).toFixed(1)}`).join(" ");
  const last = pts[pts.length - 1];
  const fmt = (v) => (Math.abs(v) >= 100 ? Math.round(v) : Math.round(v * 10) / 10);
  return (
    <div className={`trend-card ${status || ""}`}>
      <div className="row between" style={{ alignItems: "baseline" }}>
        <span className="trend-name">{series.name}</span>
        <span className="trend-last"><CountUp value={fmt(last.value)} /> <small>{series.unit}</small></span>
      </div>
      <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} className="trend-svg" role="img" aria-label={`${series.name} trend`}>
        {target != null && (
          <g>
            <line x1={PL} x2={W - PR} y1={y(target)} y2={y(target)} className="tc-target" />
            <text x={W - PR} y={y(target) - 4} textAnchor="end" className="tc-axis">target {target}</text>
          </g>
        )}
        <path ref={pathRef} d={d} className="tc-line" />
        {pts.map((p, i) => (
          <g key={i}>
            <circle cx={x(i)} cy={y(p.value)} r={i === pts.length - 1 ? 4.5 : 3.2} className="tc-dot" />
            {(i === 0 || i === pts.length - 1 || pts.length <= 5) && (
              <text x={x(i)} y={y(p.value) - 8} textAnchor="middle" className="tc-val">{fmt(p.value)}</text>
            )}
          </g>
        ))}
        <text x={PL} y={H - 6} className="tc-axis">{pts[0].date.slice(2, 7)}</text>
        <text x={W - PR} y={H - 6} textAnchor="end" className="tc-axis">{last.date.slice(2, 7)}</text>
      </svg>
    </div>
  );
}

// Every charted test except HbA1c, which keeps its own large chart.
export function useChartSeries(insights) {
  return useMemo(() => {
    const list = insights?.series || [];
    return list.filter((s) => s.code !== "hba1c"); // HbA1c keeps its own large chart
  }, [insights]);
}
