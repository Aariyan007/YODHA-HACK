// Medication as a timeline and as rows, never as a grid of identical cards.
// Timing, course and instructions are shown only when the prescription record actually has them.
import { useEffect, useRef } from "react";
import { gsap } from "gsap";
import { reducedMotion } from "../anim.js";
import { useT } from "../i18n.js";
import { RV } from "./primitives.jsx";
import { courseOf, longDate } from "./data.js";

export function to12h(hhmm) {
  const [h, m] = String(hhmm || "").split(":").map(Number);
  if (Number.isNaN(h)) return hhmm || "";
  return `${((h + 11) % 12) + 1}:${String(m || 0).padStart(2, "0")} ${h >= 12 ? "PM" : "AM"}`;
}

export function courseText(c) {
  if (!c) return null;
  if (c.day == null) return `${c.total}-day course`;
  if (c.notStarted) return `Starts ${longDate(`${c.start.getFullYear()}-${String(c.start.getMonth() + 1).padStart(2, "0")}-${String(c.start.getDate()).padStart(2, "0")}`)}`;
  if (c.over) return "Course complete";
  return `Day ${c.day} of ${c.total}`;
}

// ── Today ───────────────────────────────────────────────────────────────────
export function MedicationTimeline({ reminders = [], medicines = [], onTake, readOnly = false }) {
  const { t, lang } = useT();
  const ml = lang === "ml";
  const byId = Object.fromEntries(medicines.map((m) => [m.id, m]));
  const total = reminders.length;
  const taken = reminders.filter((r) => r.taken).length;
  const barRef = useRef(null);

  useEffect(() => {
    const bar = barRef.current;
    if (!bar) return;
    const pct = total ? (taken / total) * 100 : 0;
    if (reducedMotion()) { bar.style.width = `${pct}%`; return; }
    const tw = gsap.to(bar, { width: `${pct}%`, duration: 0.7, ease: "power3.out" });
    return () => tw.kill();
  }, [taken, total]);

  if (!total) return <p className="mt-quiet">{ml ? "ഇന്ന് ഷെഡ്യൂൾ ചെയ്ത മരുന്നുകളൊന്നുമില്ല." : "No medicines are scheduled today. Add a prescription to get reminders."}</p>;
  return (
    <div className="mt-meds-wrap">
      <div className="mt-meds-prog">
        <span className="mt-label">{ml ? "ഇന്ന്" : "Today"}</span>
        <span className="mt-meds-count"><b>{taken}</b> {ml ? "/" : "of"} {total} {ml ? "കഴിച്ചു" : "taken"}</span>
        <span className="bar" aria-hidden="true"><span ref={barRef} style={{ width: 0 }} /></span>
      </div>
      <RV as="ol" className="mt-meds" stagger={0.07} selector=":scope > li">
        {reminders.map((r) => {
          const med = byId[r.medicineId];
          const course = courseText(courseOf(med));
          return (
            <li key={r.key} className={`mt-med${r.taken ? " taken" : ""}`}>
              <span className="t">{to12h(r.time)}</span>
              <span className="n" aria-hidden="true">{r.taken ? "✓" : ""}</span>
              <div className="b">
                <div className="nm">{r.name}{r.dose && <span className="ds"> {r.dose}</span>}</div>
                {(r.instructions || course) && (
                  <div className="sb">
                    {r.instructions && <span>{r.instructions}</span>}
                    {course && <span className="cr">{course}</span>}
                  </div>
                )}
              </div>
              <div className="a">
                {r.taken ? <span className="ok">✓ {t("taken")}</span>
                  : !readOnly && <button type="button" className="mt-btn sm secondary" onClick={() => onTake?.(r.key)}>{t("markTaken")}</button>}
              </div>
            </li>
          );
        })}
      </RV>
    </div>
  );
}

// ── All active medicines, as rows ───────────────────────────────────────────
export function MedicationList({ medicines = [] }) {
  const { t, lang } = useT();
  const ml = lang === "ml";
  return (
    <div className="mt-rx">
      <div className="mt-rx-head" aria-hidden="true">
        <span>{ml ? "മരുന്ന്" : "Medicine"}</span><span>{ml ? "അളവ്" : "Dose"}</span>
        <span>{ml ? "എപ്പോൾ" : "When"}</span><span>{ml ? "കോഴ്സ്" : "Course"}</span>
      </div>
      <RV as="ul" className="mt-rx-list" stagger={0.06} selector=":scope > li">
        {medicines.map((m) => {
          const c = courseOf(m);
          const text = courseText(c);
          const when = [m.frequency, m.instructions].filter(Boolean).join(" · ");
          return (
            <li key={m.id} className="mt-rx-row">
              <span className="ind" aria-hidden="true" />
              <div className="nm">
                <strong>{m.name}</strong>
                {m.generic && m.generic.toLowerCase() !== m.name.toLowerCase() && <span className="gn">{m.generic}</span>}
              </div>
              <div className="ds" data-label={ml ? "അളവ്" : "Dose"}>{m.dose || <i className="none">—</i>}</div>
              <div className="wh" data-label={ml ? "എപ്പോൾ" : "When"}>
                {when ? <span>{when}</span> : <i className="none">—</i>}
                {(m.times || []).length > 0 && <span className="tm">{m.times.map(to12h).join(" · ")}</span>}
              </div>
              <div className="cs" data-label={ml ? "കോഴ്സ്" : "Course"}>
                {text ? <span>{text}</span> : <i className="none">—</i>}
                {c?.pct != null && !c.notStarted && <span className="pr" aria-hidden="true"><span style={{ width: `${c.pct}%` }} /></span>}
              </div>
              {(m.prescribedBy || m.startDate) && (
                <div className="by">
                  {m.prescribedBy && <>{t("prescribedBy")} {m.prescribedBy}</>}
                  {m.prescribedBy && m.startDate && " · "}
                  {m.startDate && longDate(m.startDate)}
                </div>
              )}
            </li>
          );
        })}
      </RV>
    </div>
  );
}
