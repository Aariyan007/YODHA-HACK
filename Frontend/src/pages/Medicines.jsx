import { getMedicines } from "../api/client.js";
import { Empty, Loading, formatDate } from "../components/ui.jsx";
import { Reveal } from "../components/editorial.jsx";
import { useT } from "../i18n.js";
import { useApi } from "../useApi.js";

// Course progress from real start_date + duration_days only.
// Parse a YYYY-MM-DD string as a LOCAL date (not UTC), so day counts match the user's calendar.
function localDate(s) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s || "");
  return m ? new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3])) : null;
}
function course(m) {
  if (!m.durationDays && !m.startDate) return null;
  const start = localDate(m.startDate);
  const dur = m.durationDays || null;
  if (start && !Number.isNaN(start.getTime()) && dur) {
    const end = new Date(start); end.setDate(end.getDate() + dur);
    const today = new Date(); today.setHours(0, 0, 0, 0);
    const day = Math.floor((today - start) / 86400000) + 1;
    const ongoing = day >= 1 && day <= dur;
    return {
      dur,
      range: `${formatDate(m.startDate)} → ${end.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })}`,
      dayText: ongoing ? `Day ${day} of ${dur}` : day > dur ? "Completed" : `Starts ${formatDate(m.startDate)}`,
      pct: ongoing ? Math.round((day / dur) * 100) : day > dur ? 100 : 0,
    };
  }
  if (dur) return { dur, dayText: null, range: null, pct: null, label: `${dur}-day course` };
  return null;
}

function MedCard({ m }) {
  const { t, lang } = useT();
  const ml = lang === "ml";
  // Timing comes only from the source record; nothing is inferred.
  const timing = [m.frequency, m.instructions].filter(Boolean).join(" · ");
  const times = m.times || [];
  const c = course(m);
  return (
    <article className="rx-card card-hover" role="listitem">
      <div>
        <div className="rx-head">
          <h4 className="rx-name">{m.name}</h4>
          {m.generic && <span className="rx-generic">{m.generic}</span>}
        </div>
        {m.dose && <div className="rx-dose">{m.dose}</div>}
      </div>

      {(timing || times.length > 0 || c) && (
        <div className="rx-rows">
          {(timing || times.length > 0) && (
            <div className="rx-row">
              <span className="rx-row-label">{ml ? "എപ്പോൾ" : "When"}</span>
              {timing && <span className="rx-row-value">{timing}</span>}
              {times.length > 0 && (
                <div className="rx-times">{times.map((tm, i) => <span key={i} className="rx-time">{tm}</span>)}</div>
              )}
            </div>
          )}
          {c && (
            <div className="rx-row">
              <span className="rx-row-label">Course</span>
              <span className="rx-row-value">{c.dayText || c.label}</span>
              {c.range && <span className="rx-row-value" style={{ color: "var(--text-3)", fontSize: "var(--font-xs)" }}>{c.range}</span>}
              {c.pct != null && (
                <div className="rx-course" style={{ marginTop: 4 }}>
                  <span className="rx-progress"><span style={{ width: `${c.pct}%` }} /></span>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {(m.prescribedBy || m.startDate) && (
        <div className="rx-foot">
          {m.prescribedBy && <span>{t("prescribedBy")} {m.prescribedBy}</span>}
          {m.prescribedBy && m.startDate && <span className="sep">·</span>}
          {m.startDate && <span>{formatDate(m.startDate)}</span>}
        </div>
      )}
    </article>
  );
}

export default function Medicines() {
  const { t } = useT();
  const { data, loading, error, reload } = useApi(getMedicines);
  if (loading || error) return <Loading error={error} onRetry={reload} />;

  return (
    <>
      <div className="page-header">
        <h2>{t("medicines")}</h2>
        {data.length > 0 && <span className="pill accent">{data.length} active</span>}
      </div>

      {data.length === 0 ? (
        <Empty>No medicines yet. They appear here when you add a prescription.</Empty>
      ) : (
        <Reveal className="rx-grid-page" stagger={0.07} y={18}>
          {data.map((m) => <MedCard key={m.id} m={m} />)}
        </Reveal>
      )}
    </>
  );
}
