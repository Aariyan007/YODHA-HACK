/**
 * The visit, sorted into what a clinician cares about: what the patient reported, what the doctor diagnosed,
 * the prescription, tests, advice, referrals and follow-up. Small talk is left out entirely.
 *
 * The AI only proposes; the server has already checked every item against the transcript. On the review
 * screen the doctor can remove any item (it then is not saved). Removal is sent as indexes, so the doctor
 * can drop things but nothing can be added from the browser.
 */
const ACTION = {
  start: { label: "Start", tone: "good" },
  continue: { label: "Continue", tone: "info" },
  change: { label: "Change", tone: "watch" },
  stop: { label: "Stop", tone: "alert" },
};

const SECTIONS = [
  { key: "diagnoses", title: "Diagnosis", hint: "Only what the doctor said out loud." },
  { key: "medicines", title: "Prescription", hint: "Medicines started, continued, changed or stopped." },
  { key: "tests", title: "Tests ordered" },
  { key: "advice", title: "Advice" },
  { key: "referrals", title: "Referral" },
  { key: "complaints", title: "Patient reported" },
];

function Row({ kind, item, idx, removed, onToggle, onSource, readOnly, children }) {
  const gone = removed?.[kind]?.has(idx);
  return (
    <li className={`vc-item${gone ? " gone" : ""}`}>
      <div className="vc-main">{children}</div>
      {!readOnly && (
        <div className="vc-tools">
          {item.source_lines?.length > 0 && (
            <button type="button" className="vc-src" onClick={() => onSource?.(item.source_lines)}
                    aria-label="Show the transcript lines for this item">
              Source [{item.source_lines.join(", ")}]
            </button>
          )}
          <button type="button" className="vc-x" onClick={() => onToggle?.(kind, idx)}
                  aria-label={gone ? "Put this item back" : "Remove this item"}>
            {gone ? "Undo" : "✕"}
          </button>
        </div>
      )}
      {gone && <div className="vc-gone-note">Removed. This will not be saved.</div>}
    </li>
  );
}

function MedicineBody({ m }) {
  const a = ACTION[m.action] || ACTION.start;
  const bits = [
    ["Dose", m.dose], ["How often", m.frequency], ["When", m.timing], ["For", m.duration], ["Note", m.instructions],
  ].filter(([, v]) => v); // a detail the doctor did not say is simply not shown
  return (
    <>
      <div className="vc-med-head">
        <span className={`vc-act ${a.tone}`}>{a.label}</span>
        <strong className="vc-med-name">{m.name}</strong>
        {m.generic && m.generic.toLowerCase() !== m.name.toLowerCase() && <span className="vc-generic">{m.generic}</span>}
      </div>
      {bits.length > 0 && (
        <dl className="vc-det">
          {bits.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}
        </dl>
      )}
      {m.action === "stop" && <div className="vc-warn">Reminders for this medicine will switch off.</div>}
      {m.action === "change" && <div className="vc-warn">Replaces the medicine on the patient's list.</div>}
    </>
  );
}

export function VisitClassification({ data, removed, onToggle, onSource, readOnly = false, stopped = [] }) {
  if (!data) return null;
  const sections = SECTIONS.filter((s) => (data[s.key] || []).length > 0);
  const hasFollow = !!data.follow_up;
  const ignored = (data.ignored_lines || []).length;
  const nothing = sections.length === 0 && !hasFollow;

  return (
    <section className="card vc" aria-label="Visit sorted by type">
      <div className="row between" style={{ alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
        <h3 style={{ margin: 0 }}>{readOnly ? "What was recorded" : "What the AI found in this visit"}</h3>
        <span className="muted small">Checked against the transcript</span>
      </div>
      {!readOnly && <p className="muted small" style={{ margin: "4px 0 0" }}>
        Remove anything that is wrong. Removed items are not saved to the patient's record.
      </p>}

      {nothing && <p className="muted" style={{ margin: "14px 0 0" }}>No medicines, diagnosis or tests were clearly stated in this visit.</p>}

      {sections.map((s) => (
        <div className="vc-block" key={s.key}>
          <div className="vc-title">{s.title}{s.hint && <span className="vc-hint"> · {s.hint}</span>}</div>
          <ul className="vc-list">
            {data[s.key].map((item, i) => (
              <Row key={`${s.key}-${i}`} kind={s.key} item={item} idx={i} removed={removed}
                   onToggle={onToggle} onSource={onSource} readOnly={readOnly}>
                {s.key === "medicines" ? <MedicineBody m={item} /> : <span>{item.text}</span>}
              </Row>
            ))}
          </ul>
        </div>
      ))}

      {hasFollow && (
        <div className="vc-block">
          <div className="vc-title">Follow-up</div>
          <ul className="vc-list">
            <Row kind="follow_up" item={data.follow_up} idx={0} removed={removed}
                 onToggle={onToggle} onSource={onSource} readOnly={readOnly}>
              <span>{data.follow_up.text}</span>
            </Row>
          </ul>
        </div>
      )}

      {readOnly && stopped.length > 0 && (
        <p className="vc-warn" style={{ marginTop: 12 }}>Switched off: {stopped.join(", ")}.</p>
      )}
      {ignored > 0 && (
        <p className="muted small" style={{ margin: "14px 0 0" }}>
          {ignored} non-clinical {ignored === 1 ? "line was" : "lines were"} left out (greetings and small talk).
        </p>
      )}
    </section>
  );
}
