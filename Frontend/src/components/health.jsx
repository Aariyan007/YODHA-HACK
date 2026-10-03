import { useEffect, useMemo, useRef, useState } from "react";
import { gsap } from "gsap";
import { Link } from "react-router-dom";
import { addVitals } from "../api/client.js";
import { pulse, reducedMotion, useReveal } from "../anim.js";
import { useT } from "../i18n.js";
import { CountUp } from "./ui.jsx";
import { LineChart, Sparkline, changeSummary } from "./charts.jsx";

const LEVEL_LABEL = {
  en: { emergency: "Urgent", high: "See a doctor soon", watch: "Keep an eye" },
  ml: { emergency: "അടിയന്തരം", high: "വേഗം ഡോക്ടറെ കാണുക", watch: "ശ്രദ്ധിക്കുക" },
};

export const doctorsLink = (specialty, extra = {}) => {
  const p = new URLSearchParams({ ...(specialty ? { specialty } : {}), ...extra });
  return `/doctors?${p.toString()}`;
};

// -- Emergency banner: always driven by Python, never waits for AI --
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

// -- One risk --
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
// Which review points count as "attention" vs "normal".
const ATTENTION_KINDS = new Set(["worse", "missing"]);

// -- Health Check review: what it means, what to know, questions --
export function HealthCheckPanel({ data, compact = false }) {
  const { lang, pick } = useT();
  const ml = lang === "ml";
  const listRef = useReveal([data?.checkedAt], { selector: ".hc-point, .hc-know-cell, .hc-q, .risk-card" });
  if (!data) return null;
  const { risks = [], review } = data;
  const emergency = risks.find((r) => r.emergency);
  const others = risks.filter((r) => r !== emergency);

  const points = review?.points || [];
  const group = (k) => points.filter((p) => p.kind === k);
  const know = [
    { key: "changed", kinds: ["better"], label: ml ? "എന്ത് മാറി" : "What changed" },
    { key: "stable",  kinds: ["steady"], label: ml ? "സ്ഥിരമായത്" : "What stayed stable" },
    { key: "missing", kinds: ["missing"], label: ml ? "എന്ത് കുറവാണ്" : "What is missing" },
    { key: "discuss", kinds: ["worse"], label: ml ? "ചർച്ച ചെയ്യേണ്ടത്" : "Worth discussing" },
  ].map((g) => ({ ...g, items: g.kinds.flatMap((k) => group(k)) })).filter((g) => g.items.length);

  return (
    <div ref={listRef} className="healthcheck">
      {emergency && <EmergencyBanner risk={emergency} />}

      {review && (
        <div className="hc-review">
          <span className={`ai-tag ${review.source === "ai" ? "" : "rules"}`}>
            <svg className="spark" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
              <path d="M8 0l1.6 4.8L14.4 6.4 9.6 8 8 12.8 6.4 8 1.6 6.4 6.4 4.8z" />
            </svg>
            {review.source === "ai" ? (ml ? "AI ആരോഗ്യ വായന" : "AI health review") : (ml ? "നിയമ പരിശോധന" : "Rule-based review")}
          </span>
          <p className="hc-headline">{pick(review, "headline")}</p>

          {/* WHAT IT MEANS: evidence split into normal / attention */}
          {points.length > 0 && (
            <ul className="hc-points">
              {points.map((p, i) => {
                const attn = ATTENTION_KINDS.has(p.kind);
                return (
                  <li key={i} className={`hc-point ${attn ? "attn" : "ok"}`}>
                    <span className="hc-point-mark" aria-hidden="true">{attn ? "!" : "✓"}</span>
                    <span>{pick(p, "text")}</span>
                  </li>
                );
              })}
            </ul>
          )}

          {/* WHAT SHOULD I KNOW? */}
          {!compact && know.length > 0 && (
            <div className="hc-know">
              <div className="ed-kicker bare" style={{ margin: "0 0 2px" }}>{ml ? "ഞാൻ അറിയേണ്ടത്" : "What should I know?"}</div>
              <div className="hc-know-grid">
                {know.map((g) => (
                  <div key={g.key} className={`hc-know-cell ${g.key}`}>
                    <div className="hc-know-label">{g.label}</div>
                    <ul>{g.items.map((it, i) => <li key={i}>{pick(it, "text")}</li>)}</ul>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* QUESTIONS FOR YOUR NEXT VISIT */}
          {!compact && review.askDoctor?.length > 0 && (
            <div className="hc-questions">
              <div className="ed-kicker bare" style={{ margin: "0 0 4px" }}>{ml ? "അടുത്ത സന്ദർശനത്തിന് ചോദ്യങ്ങൾ" : "Questions for your next visit"}</div>
              <ol className="hc-q-list">
                {review.askDoctor.map((q, i) => (
                  <li key={i} className="hc-q">
                    <span className="hc-q-n">{String(i + 1).padStart(2, "0")}</span>
                    <span className="hc-q-text">“{pick(q, "text")}”</span>
                  </li>
                ))}
              </ol>
            </div>
          )}

          <p className="hc-disclaim">
            {ml ? "ഇത് രോഗനിർണയമല്ല. സ്വയം മരുന്ന് മാറ്റരുത്; ഡോക്ടറോട് ചോദിക്കുക."
                : "Not a diagnosis. Never change a medicine on your own; ask your doctor."}
          </p>
        </div>
      )}

      {(compact ? others.slice(0, 3) : others).map((r) => <RiskCard key={r.key} risk={r} />)}
    </div>
  );
}

// -- "Check yourself": add a reading and see it against your thread --
const fmtN = (v) => (Math.abs(v) >= 100 ? String(Math.round(v)) : String(Math.round(v * 10) / 10));

// Reading result: today vs previous recorded reading + a small trend.
function ReadingResult({ today, insights, result, ml }) {
  const prevLab = (code) => insights?.labs?.find((l) => l.code === code);
  const prevSeries = (code) => insights?.series?.find((s) => s.code === code)?.points;
  const sugarCode = today.sugar != null ? today.sugarType : null;

  // Builds the main comparison (BP first, else the first vital that has an earlier value).
  const bpSbp = prevLab("sbp"), bpDbp = prevLab("dbp");
  let primary = null;
  if (today.sbp != null && today.dbp != null) {
    primary = {
      kind: "bp",
      label: ml ? "രക്തസമ്മർദ്ദം" : "Blood pressure",
      todayText: `${today.sbp}/${today.dbp}`,
      unit: "mmHg",
      prev: bpSbp && bpDbp ? { text: `${bpSbp.value}/${bpDbp.value}`, date: bpSbp.date } : null,
      deltas: bpSbp && bpDbp
        ? [{ l: ml ? "സിസ്റ്റോളിക്" : "systolic", d: today.sbp - bpSbp.value },
           { l: ml ? "ഡയസ്റ്റോളിക്" : "diastolic", d: today.dbp - bpDbp.value }]
        : [],
      series: (() => { const p = prevSeries("sbp"); return p ? [...p, { date: new Date().toISOString(), value: today.sbp }] : null; })(),
      code: "sbp",
      lower: bpSbp && bpDbp ? (today.sbp <= bpSbp.value && today.dbp <= bpDbp.value) : null,
    };
  } else {
    const order = [["sugar", sugarCode], ["pulse", "pulse"], ["spo2", "spo2"], ["weight", "weight"]];
    for (const [field, code] of order) {
      if (today[field] == null || !code) continue;
      const pv = prevLab(code);
      const unit = code === "weight" ? "kg" : code === "spo2" ? "%" : code === "pulse" ? "bpm" : "mg/dL";
      const p = prevSeries(code);
      primary = {
        kind: field,
        label: pv?.name || field,
        todayText: fmtN(today[field]),
        unit,
        prev: pv ? { text: fmtN(pv.value), date: pv.date } : null,
        deltas: pv ? [{ l: "", d: today[field] - pv.value }] : [],
        series: p ? [...p, { date: new Date().toISOString(), value: today[field] }] : null,
        code,
        lower: pv ? today[field] <= pv.value : null,
      };
      break;
    }
  }

  const top = result?.risks?.[0];
  const noChange = primary?.deltas?.length > 0 && primary.deltas.every((d) => d.d === 0);
  const note = primary?.prev == null
    ? (ml ? "ഇത് ഈ അളവിന്റെ ആദ്യ രേഖയാണ്." : "This is the first recorded reading for this measurement.")
    : noChange ? (ml ? "നിങ്ങളുടെ പുതിയ റീഡിംഗ് മുൻ രേഖയ്ക്ക് തുല്യമാണ്." : "Your latest reading is in line with your previous recorded reading.")
    : primary.lower === true ? (ml ? "നിങ്ങളുടെ പുതിയ റീഡിംഗ് മുൻ രേഖയേക്കാൾ കുറവാണ്." : "Your latest reading is lower than your previous recorded reading.")
    : primary.lower === false ? (ml ? "നിങ്ങളുടെ പുതിയ റീഡിംഗ് മുൻ രേഖയേക്കാൾ കൂടുതലാണ്." : "Your latest reading is higher than your previous recorded reading.")
    : (ml ? "നിങ്ങളുടെ പുതിയ റീഡിംഗ് മുൻ രേഖയിൽ നിന്ന് വ്യത്യസ്തമാണ്." : "Your latest reading differs from your previous recorded reading.");

  // Reveals the comparison step by step: today, previous, changes, trend, insight.
  const rrRef = useRef(null);
  useEffect(() => {
    if (!rrRef.current || reducedMotion()) return;
    const ctx = gsap.context(() => {
      gsap.from(".rr-step", { opacity: 0, y: 18, duration: 0.5, stagger: 0.12, ease: "power3.out", clearProps: "all" });
    }, rrRef);
    return () => ctx.revert();
  }, []);

  return (
    <div ref={rrRef} className="reading-result" role="status">
      {primary && (
        <>
          <div className="rr-flow rr-step">
            <div className="rr-col today">
              <span className="rr-tag">{ml ? "ഇന്ന്" : "Today"}</span>
              <span className="rr-big">{primary.todayText}<small>{primary.unit}</small></span>
            </div>
            {primary.prev && (
              <>
                <span className="rr-vs" aria-hidden="true">compared with</span>
                <div className="rr-col prev">
                  <span className="rr-tag">{ml ? "മുൻ രേഖ" : "Previous record"}</span>
                  <span className="rr-big">{primary.prev.text}<small>{primary.unit}</small></span>
                  <span className="rr-date">{primary.prev.date}</span>
                </div>
              </>
            )}
          </div>
          {primary.deltas.length > 0 && (
            <div className="rr-deltas rr-step">
              {primary.deltas.map((d, i) => d.d === 0 ? null : (
                <span key={i} className={`rr-delta ${d.d < 0 ? "down" : "up"}`}>
                  <span aria-hidden="true">{d.d < 0 ? "↓" : "↑"}</span> {fmtN(Math.abs(d.d))} {d.l}
                </span>
              ))}
            </div>
          )}
          {primary.series && primary.series.length >= 2 && (
            <div className="rr-trend rr-step">
              <span className="rr-trend-label">{ml ? "നിങ്ങളുടെ ട്രെൻഡ്" : "Your trend"}</span>
              <Sparkline points={primary.series} code={primary.code} />
            </div>
          )}
          <p className="rr-note rr-step">{note}</p>
          <div className="rr-thread rr-step" role="status">
            <span className={`n prev${primary.prev ? "" : " none"}`} aria-hidden="true" />
            <span className="line" aria-hidden="true"><i /></span>
            <span className="n today" aria-hidden="true" />
            <span className="txt">{ml ? "നിങ്ങളുടെ ഹെൽത്ത് ത്രെഡിൽ ചേർത്തു" : "Added to your health thread"}</span>
          </div>
          <Link className="ed-link rr-step" to="/timeline">{ml ? "ഇതിന്റെ പിന്നിലെ രേഖകൾ കാണുക" : "View the records behind this"} →</Link>
        </>
      )}
      {top?.emergency ? (
        <p className="error text-sm" style={{ marginTop: "var(--sp-4)" }}>
          {ml ? "ഈ റീഡിംഗ് അപകട നിലയിലാണ്: താഴെയുള്ള ചുവന്ന മുന്നറിയിപ്പ് കാണുക." : "This reading is in the danger zone: see the red alert."}
        </p>
      ) : top ? (
        <div style={{ marginTop: "var(--sp-4)" }}><RiskCard risk={top} /></div>
      ) : primary ? null : (
        <p className="text-good text-sm">{ml ? "സേവ് ചെയ്തു. അപകട സൂചനകളൊന്നുമില്ല." : "Saved. Nothing worrying in this reading."}</p>
      )}
    </div>
  );
}

export function VitalsForm({ onSaved, insights }) {
  const { lang } = useT();
  const ml = lang === "ml";
  const [v, setV] = useState({ sbp: "", dbp: "", pulse: "", spo2: "", sugar: "", sugarType: "rbs", weight: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const [submitted, setSubmitted] = useState(null);
  // Snapshot of the record BEFORE this save, so the comparison shows the
  // genuinely previous reading (not the one we just added).
  const [snapshot, setSnapshot] = useState(null);
  const set = (k) => (e) => setV((s) => ({ ...s, [k]: e.target.value }));
  const num = (x) => (x === "" ? undefined : Number(x));

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setSnapshot(insights); // capture the record as it was before this reading
      const body = { sbp: num(v.sbp), dbp: num(v.dbp), pulse: num(v.pulse), spo2: num(v.spo2), weight: num(v.weight),
                     sugar: num(v.sugar), sugarType: v.sugarType };
      const res = await addVitals(body);
      setSubmitted({ _id: Date.now(), sbp: num(v.sbp) ?? null, dbp: num(v.dbp) ?? null, pulse: num(v.pulse) ?? null,
                     spo2: num(v.spo2) ?? null, weight: num(v.weight) ?? null,
                     sugar: num(v.sugar) ?? null, sugarType: v.sugarType });
      setResult(res);
      setV({ sbp: "", dbp: "", pulse: "", spo2: "", sugar: "", sugarType: v.sugarType, weight: "" });
      onSaved?.(res);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="checkself" onSubmit={submit} noValidate>
      <div className="cs-kicker">{ml ? "സ്വയം പരിശോധിക്കുക" : "Check yourself"}</div>
      <h3 className="cs-title">{ml ? "ഇന്നത്തെ റീഡിംഗ് ചേർക്കുക" : "Add today's reading"}</h3>

      <div className="cs-primary">
        <label className="cs-field-label" htmlFor="cs-sbp">{ml ? "രക്തസമ്മർദ്ദം" : "Blood pressure"}</label>
        <div className="cs-bp">
          <input id="cs-sbp" inputMode="numeric" placeholder="120" value={v.sbp} onChange={set("sbp")} aria-label="Systolic (top number)" />
          <span className="cs-slash" aria-hidden="true">/</span>
          <input inputMode="numeric" placeholder="80" value={v.dbp} onChange={set("dbp")} aria-label="Diastolic (bottom number)" />
          <span className="cs-unit">mmHg</span>
        </div>
      </div>

      <div className="cs-secondary">
        <label className="cs-sfield">
          <span>{ml ? "നാഡിമിടിപ്പ്" : "Pulse"}</span>
          <input inputMode="numeric" placeholder="72" value={v.pulse} onChange={set("pulse")} />
        </label>
        <label className="cs-sfield">
          <span>SpO₂ <small>%</small></span>
          <input inputMode="numeric" placeholder="98" value={v.spo2} onChange={set("spo2")} />
        </label>
        <label className="cs-sfield sugar">
          <span>{ml ? "പഞ്ചസാര" : "Sugar"} <small>mg/dL</small></span>
          <div className="cs-sugar">
            <input inputMode="numeric" placeholder="110" value={v.sugar} onChange={set("sugar")} />
            <select value={v.sugarType} onChange={set("sugarType")} aria-label="Sugar test type">
              <option value="fbs">{ml ? "വെറുംവയറ്" : "Fasting"}</option>
              <option value="ppbs">{ml ? "ഭക്ഷണശേഷം" : "After food"}</option>
              <option value="rbs">{ml ? "ഏതുസമയം" : "Random"}</option>
            </select>
          </div>
        </label>
        <label className="cs-sfield">
          <span>{ml ? "ഭാരം" : "Weight"} <small>kg</small></span>
          <input inputMode="decimal" placeholder="64" value={v.weight} onChange={set("weight")} />
        </label>
      </div>

      <div className="row" style={{ gap: "var(--sp-3)", marginTop: "var(--sp-5)", alignItems: "center", flexWrap: "wrap" }}>
        <button className="ed-cta" disabled={busy}>{busy ? "…" : ml ? "പരിശോധിച്ച് ത്രെഡിൽ ചേർക്കുക" : "Check & add to thread"}</button>
        {error && <span className="error text-sm" role="alert">{error}</span>}
      </div>

      {result && submitted && <ReadingResult key={submitted._id} today={submitted} insights={snapshot || insights} result={result} ml={ml} />}
    </form>
  );
}

// ── Generic trend chart for any test ───────────────────────────────────────
const TARGETS = { hba1c: 7, sbp: 130, dbp: 80, fbs: 130, ppbs: 180, rbs: 160, ldl: 100, creatinine: 1.2, spo2: 95, pulse: 100 };

export function TrendChart({ series, status }) {
  const pts = series.points;
  const target = TARGETS[series.code];
  const last = pts[pts.length - 1];
  const fmt = (v) => (Math.abs(v) >= 100 ? Math.round(v) : Math.round(v * 10) / 10);
  const sum = changeSummary(pts, series.code, series.unit);
  return (
    <div className={`trend-card ${status || ""}`}>
      <div className="row between" style={{ alignItems: "baseline" }}>
        <span className="trend-name">{series.name}</span>
        <span className="trend-last"><CountUp value={fmt(last.value)} /> <small>{series.unit}</small></span>
      </div>
      {sum && <span className={`chart-chip ${sum.tone}`}>{sum.text}</span>}
      <LineChart points={pts} code={series.code} name={series.name} unit={series.unit} target={target} size="sm" />
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
