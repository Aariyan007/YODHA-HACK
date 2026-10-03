// What each Agent action does in this preview. Nothing here calls a model and nothing is written to the
// patient's record. Results are built from the patient's own data (see agentData.js). Anything the agent
// cannot really do yet returns an honest "not connected yet" result instead of invented content.
import { getHealthCheck, listMyDoctors } from "../../api/client.js";
import { courseOf, deltaList, fmt, longDate, unitText } from "../../design/data.js";
import { courseText } from "../../design/medication.jsx";

const profileNow = () => { try { return JSON.parse(localStorage.getItem("medithread_profile")); } catch { return null; } };
const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

const preview = (title, text) => ({
  title, preview: true,
  lead: "This arrives with the connected agent.",
  note: text || "MediThread Agent is a preview. It can read your existing records, but it cannot write, summarise or explain with a model yet.",
});

// Doctor quick actions are plain questions to the doctor agent on the server.
export const DOCTOR_ASK = {
  dbrief: "pre-visit brief", dchanges: "what changed since the last visit", dconflicts: "any conflicts in the record",
  dmissing: "what am I missing", dpdf: "make a pdf brief", dsummary: "pre-visit brief", dask: "what am I missing",
};

const RUN = {
  async tour() {
    return { title: "Guided tour", lead: "I will show you around the app, one screen at a time. Use Next to move on, or Skip any time.", tour: { name: "full", auto: false } };
  },
  async changes(d) {
    const deltas = deltaList(d.insights);
    if (!deltas.length) return { title: "What changed", lead: "Nothing to compare yet.", note: "Two results of the same test are needed to show a change." };
    return {
      title: "What changed",
      lead: `${plural(deltas.length, "measurable change", "measurable changes")} across ${plural(d.timeline.length, "record", "records")}.`,
      items: deltas.slice(0, 6).map((x) => ({
        label: x.name, value: `${fmt(x.from)} → ${fmt(x.to)}${unitText(x.unit)}`, sub: `since ${longDate(x.since)}`,
        tone: x.tone === "good" ? "good" : x.tone === "watch" ? "watch" : "steady", glyph: x.dir === "down" ? "↓" : x.dir === "up" ? "↑" : "→",
      })),
      cta: { label: "Review your thread", to: "/timeline" },
    };
  },
  async open(d) {
    const open = (d.alerts || []).filter((a) => !a.resolved);
    const follow = (d.timeline || []).find((x) => x.followUp);
    const items = open.slice(0, 5).map((a) => ({ label: a.title, value: a.severity, tone: a.severity === "high" ? "alert" : "watch" }));
    if (follow) items.push({ label: "Follow-up note", value: follow.followUp, sub: longDate(follow.date), tone: "steady" });
    return {
      title: items.length ? `Found ${plural(items.length, "open item", "open items")}` : "Nothing is open",
      lead: items.length ? "These are still waiting for you or your doctor." : "No warnings or follow-up notes are open right now.",
      items, cta: items.length ? { label: "Review in your thread", to: "/timeline" } : null,
    };
  },
  async meds(d) {
    const meds = d.medicines || [];
    if (!meds.length) return { title: "Medications", lead: "No active medicines on record.", note: "They appear here when a prescription is added." };
    return {
      title: "Medications",
      lead: `${plural(meds.length, "active medicine", "active medicines")}.`,
      items: meds.map((m) => ({
        label: `${m.name}${m.dose ? ` ${m.dose}` : ""}`,
        value: courseText(courseOf(m)) || [m.frequency, m.instructions].filter(Boolean).join(" · ") || "No course recorded",
        sub: m.prescribedBy ? `Prescribed by ${m.prescribedBy}` : undefined, tone: "steady",
      })),
      cta: { label: "Open Medications", to: "/medicines" },
    };
  },
  async rxchanges(d) {
    const meds = [...(d.medicines || [])].filter((m) => m.startDate).sort((a, b) => (a.startDate < b.startDate ? 1 : -1));
    if (!meds.length) return { title: "Prescription changes", lead: "No dated prescriptions yet.", note: "Start dates come from the prescription records." };
    return {
      title: "Most recently started",
      lead: "Medicines, newest first, from your prescription records.",
      items: meds.slice(0, 5).map((m) => ({ label: `${m.name}${m.dose ? ` ${m.dose}` : ""}`, value: longDate(m.startDate), sub: m.prescribedBy ? `Prescribed by ${m.prescribedBy}` : undefined, tone: "steady" })),
      cta: { label: "Open Medications", to: "/medicines" },
    };
  },
  async prepare(d) {
    let review = null;
    try { review = (await getHealthCheck())?.review; } catch { /* shown below */ }
    const p = profileNow();
    const items = [];
    (review?.askDoctor || []).slice(0, 4).forEach((q) => items.push({ label: "Ask", value: q.text, tone: "steady" }));
    if (d.medicines?.length) items.push({ label: "Bring", value: `Your medicine list: ${d.medicines.map((m) => m.name).join(", ")}`, tone: "steady" });
    if (p?.allergies?.length) items.push({ label: "Tell them", value: `Allergies: ${p.allergies.join(", ")}`, tone: "steady" });
    return {
      title: "For your next visit",
      lead: items.length ? "Built from your records. Nothing here is a diagnosis." : "There is nothing to prepare from yet.",
      note: review ? undefined : "The questions need the health review, which could not be loaded right now.",
      items, cta: { label: "Share with a doctor", to: "/sharing" },
    };
  },
  async doctor() {
    return {
      title: "Care match",
      lead: "Care Match reads your records, suggests a type of care, then lists doctors with the reasons they match.",
      note: "It only uses doctors in the directory and the details they list.",
      cta: { label: "Open Care Match", to: "/doctors" },
    };
  },
  async whymatch() {
    return {
      title: "Why a doctor matches",
      lead: "Each doctor in Care Match shows a 'Why this match' list.",
      note: "Those reasons come from the directory: specialty, availability, languages and video consultation. Nothing is guessed.",
      cta: { label: "Open Care Match", to: "/doctors" },
    };
  },
  async whocansee() {
    let rows = [];
    try { rows = await listMyDoctors(); } catch { /* none */ }
    return {
      title: rows.length ? `${plural(rows.length, "doctor", "doctors")} can see your record` : "No doctors connected",
      lead: rows.length ? "You can remove access at any time below." : "Share a link or an invite code to let a doctor see your record.",
      items: rows.map((r) => ({ label: r.name, value: r.since ? `Since ${longDate(r.since)}` : "Can view", sub: [r.specialty, r.hospital].filter(Boolean).join(" · ") || undefined, tone: "steady" })),
    };
  },
  async explain() {
    return {
      title: "Explaining a report",
      lead: "The agent cannot explain a single report yet.",
      note: "Every record in your thread already carries a plain-language summary. Open one to read it.",
      cta: { label: "Open your health thread", to: "/timeline" },
    };
  },
};

const PREVIEW_TITLES = {
  summary: "Summarise this period", connect: "Connect these records", addthread: "Add to my thread", consistency: "Check record consistency",
  dpatients: "Open a linked patient", dsummary: "Summarise a patient", dask: "What should I ask?",
};

export async function runAction(id, data) {
  const fn = RUN[id];
  if (fn) return fn(data || { timeline: [], alerts: [], medicines: [], insights: null, reminders: [] });
  return preview(PREVIEW_TITLES[id] || "This action");
}

/** A typed request is matched to an action with plain keywords. No model is involved. */
export function intentFor(text) {
  const t = (text || "").toLowerCase();
  const rules = [
    [/change|differ|compar|improv|worse|better/, "changes"],
    [/attention|open|follow|unresolved|pending|warning|alert|outstanding/, "open"],
    [/doctor|specialist|who should i see|consult/, "doctor"],
    [/medic|tablet|prescri|drug|dose|pill/, "meds"],
    [/visit|ask|prepare|question|bring/, "prepare"],
    [/explain|understand|mean|report/, "explain"],
    [/share|access|who can see/, "whocansee"],
  ];
  return rules.find(([re]) => re.test(t))?.[1] || null;
}
