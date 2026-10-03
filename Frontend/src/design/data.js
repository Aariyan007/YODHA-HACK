// Plain helpers that turn existing API data into what the design components show.
// Nothing here makes up data: every value comes from insights / timeline / alerts / medicines as the API returns them.

export const HIGHER_IS_BETTER = new Set(["spo2", "hdl", "hb"]);
export const CHANGE_ORDER = ["hba1c", "fbs", "ppbs", "rbs", "ldl", "sbp", "dbp", "creatinine", "tg"];
export const ARROW = { down: "↓", up: "↑", steady: "→" };

export const fmt = (v) => (Math.abs(v) >= 100 ? String(Math.round(v)) : String(Math.round(v * 10) / 10));

/* First to latest change for one charted test, or null with fewer than two results. */
export function computeDelta(series) {
  const pts = series?.points;
  if (!pts || pts.length < 2) return null;
  const from = pts[0].value, to = pts[pts.length - 1].value;
  const diff = Math.round((to - from) * 10) / 10;
  const base = { code: series.code, name: series.name, unit: series.unit, from, to, since: pts[0].date, points: pts };
  if (diff === 0) return { ...base, dir: "steady", tone: "steady", diff: 0 };
  const down = to < from;
  const better = HIGHER_IS_BETTER.has(series.code) ? !down : down;
  return { ...base, dir: down ? "down" : "up", tone: better ? "good" : "watch", diff: Math.abs(diff) };
}

/* Changes in the order a clinician would read them (HbA1c first), then any other charted test. */
export function deltaList(insights) {
  const series = insights?.series || [];
  const byCode = Object.fromEntries(series.map((s) => [s.code, s]));
  const ordered = CHANGE_ORDER.map((c) => byCode[c]).filter(Boolean);
  const rest = series.filter((s) => !CHANGE_ORDER.includes(s.code));
  return [...ordered, ...rest].map(computeDelta).filter(Boolean);
}

export const lab = (insights, code) => insights?.labs?.find((l) => l.code === code);

/** "02 Oct" */
export function shortDate(iso) {
  if (!iso) return "";
  const d = new Date(iso.length === 10 ? `${iso}T00:00:00` : iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString("en-IN", { day: "numeric", month: "short" });
}
export const longDate = (iso) => {
  if (!iso) return "";
  const d = new Date(iso.length === 10 ? `${iso}T00:00:00` : iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
};
export const yearOf = (iso) => (iso ? String(iso).slice(0, 4) : "");

/* A clock time for a record, only when a real timestamp is on the record's own day. Never made up. */
export function eventTime(doc) {
  if (!doc?.createdAt) return null;
  const c = new Date(doc.createdAt);
  if (Number.isNaN(c.getTime())) return null;
  const local = `${c.getFullYear()}-${String(c.getMonth() + 1).padStart(2, "0")}-${String(c.getDate()).padStart(2, "0")}`;
  if (doc.date && local !== doc.date) return null;
  return c.toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" });
}

export function greeting(ml = false) {
  const h = new Date().getHours();
  if (ml) return "നമസ്കാരം";
  return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
}

/* The values shown for a record: lab results, or medicines. A prescription leads with its medicines (readings
written on the same sheet, like BP or sugar, are left to the full evidence view), so a card never mixes the two. */
export function docFigures(doc) {
  const items = doc?.items || [];
  const labs = items.filter((i) => "value" in i);
  const meds = items.filter((i) => !("value" in i));
  const asLab = (i) => ({ name: i.name, value: `${i.value}${i.unit ? ` ${i.unit}` : ""}`, status: i.status });
  const asMed = (i) => ({ name: i.name, value: [i.dose, i.frequency].filter(Boolean).join(" · "), status: null });
  if (doc?.type === "prescription") return meds.map(asMed); // readings on the same sheet stay in the full evidence view
  if (labs.length) return labs.map(asLab);
  return meds.map(asMed);
}

/* Everything on the record (medicines first, then readings), for the full evidence view. */
export function docAllFigures(doc) {
  const items = doc?.items || [];
  const meds = items.filter((i) => !("value" in i)).map((i) => ({ name: i.name, value: [i.dose, i.frequency].filter(Boolean).join(" · "), status: null }));
  const labs = items.filter((i) => "value" in i).map((i) => ({ name: i.name, value: `${i.value}${i.unit ? ` ${i.unit}` : ""}`, status: i.status }));
  return [...meds, ...labs];
}

/* Every test in a lab report as { name, value, unit, status } (display only, nothing is changed or made up). */
export function labTests(doc) {
  return (doc?.items || []).filter((i) => "value" in i && i.name).map((i) => ({ name: i.name, value: i.value, unit: i.unit || "", status: i.status }));
}

/** 10^6 / uL -> 10⁶/µL for display only. */
export function prettyUnit(u) {
  if (!u) return "";
  const sup = { 0: "⁰", 1: "¹", 2: "²", 3: "³", 4: "⁴", 5: "⁵", 6: "⁶", 7: "⁷", 8: "⁸", 9: "⁹", "-": "⁻" };
  return String(u).replace(/10\^(-?\d+)/g, (_, n) => "×10" + [...n].map((c) => sup[c] || c).join("")).replace(/\s*\/\s*/g, "/").replace(/\buL\b/g, "µL").replace(/\bug\b/g, "µg");
}

/* Course progress for a medicine from its real start date and duration. null when either is missing. */
export function courseOf(m) {
  const dur = m?.durationDays;
  const m2 = /^(\d{4})-(\d{2})-(\d{2})$/.exec(m?.startDate || "");
  if (!dur || !m2) return dur ? { total: dur, day: null, pct: null } : null;
  const start = new Date(Number(m2[1]), Number(m2[2]) - 1, Number(m2[3]));
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const day = Math.floor((today - start) / 86400000) + 1;
  const end = new Date(start); end.setDate(end.getDate() + dur);
  return { total: dur, day, pct: Math.max(0, Math.min(100, Math.round((day / dur) * 100))), start, end, over: day > dur, notStarted: day < 1 };
}

/* Previous result to latest result for one charted test (what "compared with previous record" means). */
export function lastChange(series) {
  const pts = series?.points;
  if (!pts || pts.length < 2) return null;
  const prev = pts[pts.length - 2], last = pts[pts.length - 1];
  const diff = Math.round((last.value - prev.value) * 10) / 10;
  const down = diff < 0;
  const better = HIGHER_IS_BETTER.has(series.code) ? !down : down;
  return {
    name: series.name, unit: series.unit, code: series.code, from: prev.value, to: last.value, since: prev.date,
    dir: diff === 0 ? "steady" : down ? "down" : "up", tone: diff === 0 ? "steady" : better ? "good" : "watch",
    diff: Math.abs(diff), points: pts,
  };
}

export const unitText = (u) => (u === "%" ? "%" : u ? ` ${u}` : "");
export const KIND_LABEL = { interaction: "Interaction", duplicate: "Duplicate", clash: "Clash", allergy: "Allergy", lab: "Lab result", trend: "Trend", risk: "Health check" };
