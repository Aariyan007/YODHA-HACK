// Page -> what the Agent says it is working with, and which actions make sense there.
import { deltaList } from "../../design/data.js";

const ACTION = (id, title, sub) => ({ id, title, sub });

export const CONTEXTS = [
  { match: (p) => p === "/", id: "home", label: "Your health story", title: "Home",
    actions: [ACTION("changes", "What changed recently?", "Compare your latest records"), ACTION("open", "What still needs attention?", "Find open care items"),
      ACTION("explain", "Explain a report", "In simple language"), ACTION("prepare", "Prepare for my next visit", "Questions and what to bring"), ACTION("doctor", "Find a relevant doctor", "Match care to your records"), ACTION("tour", "Show me how to use MediThread", "A one-minute guided tour")] },
  { match: (p) => p.startsWith("/timeline"), id: "thread", label: "Your health thread", title: "Health thread",
    actions: [ACTION("explain", "Explain this thread", "How your records connect"), ACTION("changes", "Show what changed", "Compare results over time"),
      ACTION("open", "Find unresolved follow-ups", "Open care items"), ACTION("summary", "Summarise this period", "A short written summary")] },
  { match: (p) => p.startsWith("/insights"), id: "check", label: "Today's health context", title: "Health check",
    actions: [ACTION("changes", "What does today's reading change?", "Compare with your history"), ACTION("prepare", "What should I ask my doctor?", "From your records"),
      ACTION("open", "What still needs attention?", "Open care items"), ACTION("doctor", "Find a relevant doctor", "Match care to your records")] },
  { match: (p) => p.startsWith("/medicines"), id: "meds", label: "Medication context", title: "Medications",
    actions: [ACTION("meds", "Review medication history", "Active medicines and courses"), ACTION("rxchanges", "Find prescription changes", "Compare prescriptions"),
      ACTION("consistency", "Check record consistency", "Cross-check your records"), ACTION("prepare", "Prepare a medication summary", "To bring to a visit")] },
  { match: (p) => p.startsWith("/upload"), id: "docs", label: "Document context", title: "Documents",
    actions: [ACTION("connect", "Connect these records", "Link them to your thread"), ACTION("changes", "Find important changes", "Across your results"),
      ACTION("explain", "Explain a report", "In simple language"), ACTION("addthread", "Add this to my thread", "After you upload it")] },
  { match: (p) => p.startsWith("/doctors"), id: "care", label: "Care match context", title: "Care match",
    actions: [ACTION("doctor", "Find the most relevant doctor", "From your records"), ACTION("whymatch", "Explain why a doctor matches", "The reasons behind a match"),
      ACTION("prepare", "Prepare my health summary", "Questions and what to bring")] },
  { match: (p) => p.startsWith("/sharing"), id: "share", label: "Sharing context", title: "Sharing",
    actions: [ACTION("whocansee", "Who can see my record?", "Current access"), ACTION("prepare", "Prepare what a doctor will see", "Your summary"), ACTION("open", "What still needs attention?", "Open care items")] },
  { match: (p) => p.startsWith("/reminders"), id: "remind", label: "Reminders context", title: "Reminders",
    actions: [ACTION("meds", "Review my medicines", "Active medicines and courses"), ACTION("open", "What still needs attention?", "Open care items")] },
  { match: (p) => p.startsWith("/triage"), id: "triage", label: "Which doctor? context", title: "Which doctor?",
    actions: [ACTION("doctor", "Find a relevant doctor", "Match care to your records"), ACTION("open", "What still needs attention?", "Open care items")] },
  { match: (p) => p.startsWith("/profile"), id: "profile", label: "Profile context", title: "Profile",
    actions: [ACTION("changes", "What changed recently?", "Compare your latest records"), ACTION("open", "What still needs attention?", "Open care items")] },
  { match: (p) => p.startsWith("/doctor"), id: "doctorhome", label: "Doctor workspace", title: "Doctor home", doctor: true,
    actions: [ACTION("dpatients", "Open a linked patient", "Then ask about them here")] },
  { match: (p) => p.startsWith("/console"), id: "console", label: "Consultation context", title: "Doctor console", doctor: true,
    actions: [ACTION("dbrief", "Pre-visit brief", "Who they are, medicines, results"), ACTION("dchanges", "What changed since the last visit?", "New records and results"),
      ACTION("dconflicts", "Check the record for conflicts", "Where records disagree"), ACTION("dmissing", "What is missing?", "Gaps to ask about"), ACTION("dpdf", "Make a PDF brief", "With sources")] },
];

export const contextFor = (pathname) => CONTEXTS.find((c) => c.match(pathname)) || CONTEXTS[0];

/** Up to three real facts about the current page, from loaded data. Empty until data arrives. */
export function factsFor(ctx, data) {
  if (!data || ctx.doctor) return [];
  const open = (data.alerts || []).filter((a) => !a.resolved).length;
  const recs = data.timeline?.length ?? 0;
  const doses = { t: data.reminders?.length ?? 0, k: (data.reminders || []).filter((r) => r.taken).length };
  const d0 = deltaList(data.insights)[0];
  const change = d0 ? `${d0.name} ${d0.dir === "down" ? "↓" : d0.dir === "up" ? "↑" : "→"}` : null;
  const f = {
    home: [["Records", recs], ["Open items", open], ["Active medicines", data.medicines?.length ?? 0]],
    thread: [["Connected records", recs], ["Open items", open], change && ["Latest change", change]],
    check: [["Tests tracked", data.insights?.series?.length ?? 0], change && ["Latest change", change], ["Open items", open]],
    meds: [["Active medicines", data.medicines?.length ?? 0], doses.t && ["Doses today", `${doses.k} of ${doses.t}`]],
    docs: [["Records", recs], change && ["Latest change", change]],
    care: [["Records", recs], ["Open items", open]],
    share: [["Records", recs], ["Open items", open]],
    remind: [["Active medicines", data.medicines?.length ?? 0], doses.t && ["Doses today", `${doses.k} of ${doses.t}`]],
    triage: [["Records", recs], ["Open items", open]],
    profile: [["Records", recs], ["Open items", open]],
  }[ctx.id] || [["Records", recs]];
  return f.filter(Boolean).slice(0, 3);
}
