// Turns the Agent Engine's structured blocks into the result shape AgentResult already renders.
// Presentation only: every value shown here came from the server's tool results.
const TITLES = {
  latest_records: "Your latest records", search: "Matching records", medications: "Your medicines", care_loop: "Today's doses",
  labs: "Your latest results", alerts: "What needs attention", find_doctor: "Doctors (sample directory)", sharing_status: "Sharing",
  trend: "How it has changed", file_summary: "About this file", file_entities: "What the file contains", file_compare: "Compared with your thread", file_evidence: "Where it says that", allergies: "Allergies", conditions: "Conditions", navigate: "Opening",
};
const tone = (s) => (s === "alert" || s === "high" ? "alert" : s === "watch" || s === "medium" ? "watch" : s === "good" ? "good" : "steady");
const cite = (e) => (e?.quote ? `Page ${e.page || 1}: "${e.quote}"` : undefined);
const when = (d) => (d ? new Date(`${d}T00:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" }) : undefined);

function item(b) {
  switch (b.type) {
    case "document": return { label: b.title, value: when(b.date) || "", sub: [b.docType, b.provider || b.doctor].filter(Boolean).join(" · ") || undefined, tone: tone(b.status) };
    case "medication": return { label: b.name, value: b.dose || "", sub: [b.frequency, (b.times || []).join(", "), cite(b.evidence)].filter(Boolean).join(" · ") || undefined, tone: "steady" };
    case "metric": return { label: b.name, value: `${b.value}${b.unit ? ` ${b.unit}` : ""}`, sub: [when(b.date), b.range && `usual ${b.range}`, cite(b.evidence)].filter(Boolean).join(" · "), tone: tone(b.status) };
    case "evidence": return { label: b.label || "Line", value: b.quote || "", sub: `Page ${b.page || 1}, line ${(b.lines || []).join(", ")}`, tone: "steady" };
    case "comparison": return { label: b.name, value: `${b.before.value} → ${b.after.value}${b.unit ? ` ${b.unit}` : ""}`, sub: `${b.points} results, ${when(b.before.date)} to ${when(b.after.date)}`, glyph: b.change > 0 ? "↑" : b.change < 0 ? "↓" : "→", tone: "steady" };
    case "care_item": return { label: b.name, value: b.time || "", sub: b.taken === undefined ? undefined : b.taken ? "Marked taken" : "Not marked taken yet", tone: b.taken ? "good" : "steady" };
    case "warning": return { label: b.title || "Note", value: b.severity || "", sub: b.text, tone: tone(b.severity) };
    case "doctor_match": return { label: b.name, value: Array.isArray(b.specialty) ? b.specialty[0] : b.specialty || "", sub: [b.hospital, b.distanceKm != null && `${b.distanceKm} km`, "sample listing"].filter(Boolean).join(" · "), tone: "steady" };
    default: return null;
  }
}

export function resultFromResponse(r) {
  const blocks = r.blocks || [];
  const nav = blocks.find((b) => b.type === "navigation");
  const texts = blocks.filter((b) => b.type === "text" || b.type === "error").map((b) => b.text);
  const items = blocks.map(item).filter(Boolean);
  const title = nav ? `Opening ${nav.label}` : TITLES[r.intent] || (items.length ? "Result" : texts.length ? "Agent" : "Nothing to show");
  const failed = blocks.some((b) => b.type === "error");
  return {
    title: failed ? "That did not work" : title,
    lead: texts[0],
    items,
    note: [texts.slice(1).join(" "), r.disclaimer].filter(Boolean).join(" ") || undefined,
    navigate: nav?.route,
    confirmation: r.confirmation || undefined,
    steps: r.steps,
  };
}
