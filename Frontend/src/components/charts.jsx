// One chart engine for every lab trend (big HbA1c view, per-test cards, doctor console, sparklines).
// - smooth curve that never overshoots the data, gradient area, healthy zone band behind the target line
// - hover, touch and keyboard focus show a tooltip and a crosshair, the latest point pulses
// - entrance: the line draws, the area wipes in, dots pop (GSAP, inside gsap.context, skipped for reduced motion)
// Colours come only from CSS tokens, so dark mode works without changes.
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { gsap } from "gsap";
import { reducedMotion } from "../anim.js";

// Which direction is healthy for each test. Anything not listed: lower is better.
const HIGHER_IS_BETTER = new Set(["spo2", "hdl", "hb"]);

export function statusFor(code, value, target) {
  if (target == null) return "good";
  const better = HIGHER_IS_BETTER.has(code) ? "higher" : "lower";
  if (code === "hba1c") return value <= 7 ? "good" : value <= 8 ? "watch" : "alert";
  const ratio = better === "lower" ? value / target : target / value;
  return ratio <= 1 ? "good" : ratio <= 1.15 ? "watch" : "alert";
}

// Fritsch-Carlson monotone cubic interpolation -> SVG path.
function monotonePath(xs, ys) {
  const n = xs.length;
  if (n === 1) return `M${xs[0]},${ys[0]}`;
  const dx = [], m = [], t = new Array(n);
  for (let i = 0; i < n - 1; i++) {
    dx[i] = xs[i + 1] - xs[i];
    m[i] = (ys[i + 1] - ys[i]) / (dx[i] || 1);
  }
  t[0] = m[0];
  t[n - 1] = m[n - 2];
  for (let i = 1; i < n - 1; i++) t[i] = m[i - 1] * m[i] <= 0 ? 0 : (m[i - 1] + m[i]) / 2;
  for (let i = 0; i < n - 1; i++) {
    if (m[i] === 0) { t[i] = 0; t[i + 1] = 0; continue; }
    const a = t[i] / m[i], b = t[i + 1] / m[i], s = a * a + b * b;
    if (s > 9) { const k = 3 / Math.sqrt(s); t[i] = k * a * m[i]; t[i + 1] = k * b * m[i]; }
  }
  let d = `M${xs[0].toFixed(1)},${ys[0].toFixed(1)}`;
  for (let i = 0; i < n - 1; i++) {
    const h = dx[i] / 3;
    d += ` C${(xs[i] + h).toFixed(1)},${(ys[i] + t[i] * h).toFixed(1)} ${(xs[i + 1] - h).toFixed(1)},${(ys[i + 1] - t[i + 1] * h).toFixed(1)} ${xs[i + 1].toFixed(1)},${ys[i + 1].toFixed(1)}`;
  }
  return d;
}

const fmtDate = (iso, short) =>
  new Date(iso).toLocaleDateString("en-IN", short ? { month: "short", year: "2-digit" } : { day: "numeric", month: "short", year: "numeric" });
const fmtVal = (v) => (Math.abs(v) >= 100 ? String(Math.round(v)) : String(Math.round(v * 10) / 10));

const withUnit = (v, unit) => (unit ? (unit === "%" ? `${v}%` : `${v} ${unit}`) : String(v));

export function changeSummary(points, code, unit) {
  if (!points || points.length < 2) return null;
  const first = points[0], last = points[points.length - 1];
  const diff = Math.round((last.value - first.value) * 10) / 10;
  if (diff === 0) return { tone: "steady", text: `Unchanged since ${fmtDate(first.date, true)}` };
  const down = diff < 0;
  const good = HIGHER_IS_BETTER.has(code) ? !down : down;
  return { tone: good ? "good" : "watch", text: `${down ? "Down" : "Up"} ${withUnit(fmtVal(Math.abs(diff)), unit)} since ${fmtDate(first.date, true)}` };
}

export function LineChart({ points, code, name, unit = "", target, size = "lg", className = "" }) {
  const uid = useId().replace(/:/g, "");
  const svgRef = useRef(null);
  const [active, setActive] = useState(null);
  const lg = size === "lg";
  const W = lg ? 560 : 340, H = lg ? 240 : 150;
  const PL = lg ? 44 : 30, PR = lg ? 28 : 16, PT = lg ? 30 : 24, PB = lg ? 34 : 24;

  const geo = useMemo(() => {
    if (!points?.length) return null;
    const vals = points.map((p) => p.value);
    const lo = Math.min(...vals, target ?? Infinity), hi = Math.max(...vals, target ?? -Infinity);
    const pad = (hi - lo) * 0.22 || 1;
    const min = lo - pad, max = hi + pad;
    const xs = points.map((_, i) => PL + (i * (W - PL - PR)) / Math.max(points.length - 1, 1));
    const ys = vals.map((v) => PT + (H - PT - PB) - ((v - min) * (H - PT - PB)) / (max - min));
    const line = monotonePath(xs, ys);
    const base = H - PB;
    const area = `${line} L${xs[xs.length - 1].toFixed(1)},${base} L${xs[0].toFixed(1)},${base} Z`;
    const yOf = (v) => PT + (H - PT - PB) - ((v - min) * (H - PT - PB)) / (max - min);
    const ticks = [0, 1, 2, 3].map((k) => min + ((max - min) * k) / 3).map((v) => ({ v, y: yOf(v) }));
    return { xs, ys, line, area, base, yOf, ticks };
  }, [points, target, W, H, PL, PR, PT, PB]);

  useEffect(() => {
    const svg = svgRef.current;
    if (!svg || !geo || reducedMotion()) return;
    const ctx = gsap.context(() => {
      const path = svg.querySelector(".lc-line");
      const len = path?.getTotalLength?.() || 500;
      const tl = gsap.timeline({ delay: 0.05 });
      tl.fromTo(svg.querySelector(".lc-clip rect"), { attr: { width: 0 } }, { attr: { width: W }, duration: 1.1, ease: "power2.inOut" }, 0);
      tl.fromTo(path, { strokeDasharray: len, strokeDashoffset: len }, { strokeDashoffset: 0, duration: 1, ease: "power2.inOut", clearProps: "strokeDasharray,strokeDashoffset" }, 0);
      tl.from(svg.querySelectorAll(".lc-zone, .lc-target"), { opacity: 0, duration: 0.5, ease: "power1.out" }, 0.1);
      tl.from(svg.querySelectorAll(".lc-dot"), { scale: 0, transformOrigin: "center", duration: 0.35, stagger: 0.08, ease: "back.out(2.2)" }, 0.55);
      tl.from(svg.querySelectorAll(".lc-val"), { opacity: 0, y: 4, duration: 0.3, stagger: 0.06, ease: "power2.out" }, 0.8);
    }, svg);
    return () => ctx.revert();
  }, [geo, W]);

  if (!geo) return null;
  const n = points.length;
  const last = n - 1;
  const better = HIGHER_IS_BETTER.has(code) ? "higher" : "lower";
  const targetY = target != null ? geo.yOf(target) : null;

  const nearest = (clientX) => {
    const r = svgRef.current.getBoundingClientRect();
    const x = ((clientX - r.left) / r.width) * W;
    let best = 0;
    geo.xs.forEach((px, i) => { if (Math.abs(px - x) < Math.abs(geo.xs[best] - x)) best = i; });
    return best;
  };
  const showLabels = (i) => lg ? n <= 8 || i === 0 || i === last : i === 0 || i === last || n <= 4;
  const tip = active != null ? points[active] : null;
  const tipText = tip ? `${withUnit(fmtVal(tip.value), unit)} on ${fmtDate(tip.date)}` : "";
  const tipW = Math.max(96, tipText.length * 5.9 + 16);
  const tipX = active != null ? Math.min(Math.max(geo.xs[active] - tipW / 2, 2), W - tipW - 2) : 0;
  const tipY = active != null ? Math.max(geo.ys[active] - 38, 2) : 0;

  return (
    <svg
      ref={svgRef}
      viewBox={`0 0 ${W} ${H}`}
      className={`lc ${lg ? "lc-lg" : "lc-sm"} ${className}`}
      role="group"
      aria-label={`${name || code} trend, ${n} results. Use the points to read each value.`}
      onPointerMove={(e) => setActive(nearest(e.clientX))}
      onPointerLeave={() => setActive(null)}
    >
      <defs>
        <linearGradient id={`g${uid}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" className="lc-grad-top" />
          <stop offset="100%" className="lc-grad-bottom" />
        </linearGradient>
        <clipPath id={`c${uid}`} className="lc-clip"><rect x="0" y="0" width={W} height={H} /></clipPath>
      </defs>

      {geo.ticks.map((t, i) => (
        <g key={i}>
          <line x1={PL} x2={W - PR} y1={t.y} y2={t.y} className="lc-grid" />
          {lg && <text x={PL - 8} y={t.y + 3} textAnchor="end" className="lc-axis">{fmtVal(t.v)}</text>}
        </g>
      ))}

      {targetY != null && (
        <g>
          <rect
            className="lc-zone"
            x={PL} width={W - PL - PR}
            y={better === "lower" ? targetY : PT} height={better === "lower" ? Math.max(geo.base - targetY, 0) : Math.max(targetY - PT, 0)}
          />
          <line x1={PL} x2={W - PR} y1={targetY} y2={targetY} className="lc-target" />
          <text x={PL + 6} y={targetY - 5} textAnchor="start" className="lc-axis lc-target-label">target {fmtVal(target)}</text>
        </g>
      )}

      <g clipPath={`url(#c${uid})`}>
        <path d={geo.area} fill={`url(#g${uid})`} className="lc-area" />
      </g>
      <path d={geo.line} className="lc-line" />

      {active != null && <line x1={geo.xs[active]} x2={geo.xs[active]} y1={PT - 6} y2={geo.base} className="lc-cross" />}

      {points.map((p, i) => {
        const st = statusFor(code, p.value, target);
        return (
          <g key={`${p.date}-${i}`}>
            {i === last && <circle cx={geo.xs[i]} cy={geo.ys[i]} r="6" className={`lc-ping ${st}`} />}
            <circle
              cx={geo.xs[i]} cy={geo.ys[i]} r={i === last ? 5.5 : 4}
              className={`lc-dot ${st}${active === i ? " on" : ""}`}
              tabIndex={0}
              role="img"
              aria-label={`${withUnit(fmtVal(p.value), unit)} on ${fmtDate(p.date)}`}
              onFocus={() => setActive(i)}
              onBlur={() => setActive(null)}
            />
            {showLabels(i) && active !== i && (
              <text x={geo.xs[i]} y={geo.ys[i] - 11} textAnchor="middle" className={`lc-val ${st}`}>{fmtVal(p.value)}</text>
            )}
            {(lg ? (n <= 8 || i === 0 || i === last) : i === 0 || i === last) && (
              <text x={geo.xs[i]} y={H - (lg ? 10 : 6)} textAnchor={i === 0 && !lg ? "start" : i === last && !lg ? "end" : "middle"} className="lc-axis">{fmtDate(p.date, true)}</text>
            )}
          </g>
        );
      })}

      {tip && (
        <g className="lc-tip" pointerEvents="none">
          <rect x={tipX} y={tipY} width={tipW} height="24" rx="8" />
          <text x={tipX + tipW / 2} y={tipY + 16} textAnchor="middle">{tipText}</text>
        </g>
      )}
    </svg>
  );
}

// Tiny trend line for table rows: no axes, draws in once.
export function Sparkline({ points, code, target }) {
  const ref = useRef(null);
  const geo = useMemo(() => {
    if (!points || points.length < 2) return null;
    const W = 84, H = 26, P = 3;
    const vals = points.map((p) => p.value);
    const min = Math.min(...vals), max = Math.max(...vals);
    const xs = vals.map((_, i) => P + (i * (W - 2 * P)) / (vals.length - 1));
    const ys = vals.map((v) => H - P - ((v - min) * (H - 2 * P)) / (max - min || 1));
    return { W, H, xs, ys, d: monotonePath(xs, ys) };
  }, [points]);
  useEffect(() => {
    const p = ref.current?.querySelector("path");
    if (!p || !geo || reducedMotion()) return;
    const len = p.getTotalLength?.() || 80;
    const t = gsap.fromTo(p, { strokeDasharray: len, strokeDashoffset: len }, { strokeDashoffset: 0, duration: 0.8, ease: "power2.out", clearProps: "strokeDasharray,strokeDashoffset" });
    return () => t.kill();
  }, [geo]);
  if (!geo) return null;
  const st = statusFor(code, points[points.length - 1].value, target);
  return (
    <svg ref={ref} viewBox={`0 0 ${geo.W} ${geo.H}`} className={`spark ${st}`} aria-hidden="true">
      <path d={geo.d} className="spark-line" />
      <circle cx={geo.xs[geo.xs.length - 1]} cy={geo.ys[geo.ys.length - 1]} r="2.6" className="spark-dot" />
    </svg>
  );
}
