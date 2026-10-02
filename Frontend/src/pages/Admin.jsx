import { useEffect, useState } from "react";
import { getAdminMetrics } from "../api/client.js";
import { Chapter } from "../design/primitives.jsx";

const Stat = ({ label, value, sub }) => (
  <div className="adm-stat"><div className="adm-n">{value ?? 0}</div><div className="adm-l">{label}</div>{sub && <div className="adm-s">{sub}</div>}</div>
);

// Operator view for the emails in ADMIN_EMAILS. Anyone else gets "not found" from the server.
export default function Admin() {
  const [days, setDays] = useState(7);
  const [m, setM] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => {
    let live = true;
    setErr(null);
    getAdminMetrics(days).then((d) => live && setM(d)).catch((e) => live && setErr(e.message === "Not found" ? "This page is not available for your account." : e.message));
    return () => { live = false; };
  }, [days]);

  if (err) return <Chapter kicker="Admin" title="Not available" last><p>{err}</p></Chapter>;
  if (!m) return <Chapter kicker="Admin" title="Loading" last><p>Reading the numbers…</p></Chapter>;
  const a = m.agent, t = m.tasks;
  const max = Math.max(1, ...a.daily.map((d) => d.calls));
  return (
    <>
      <Chapter no="01" kicker="Admin" title="How the agents are doing" aside={
        <div className="seg" role="group" aria-label="Time window">
          {[1, 7, 30].map((d) => <button key={d} type="button" className={days === d ? "on" : ""} aria-pressed={days === d} onClick={() => setDays(d)}>{d === 1 ? "24 h" : `${d} days`}</button>)}
        </div>}>
        <div className="adm-grid">
          <Stat label="Tool calls" value={a.toolCalls} sub={Object.entries(a.byAgent).map(([k, v]) => `${k} ${v}`).join(" · ")} />
          <Stat label="Tasks" value={t.total} sub={Object.entries(t.byStatus).map(([k, v]) => `${k} ${v}`).join(" · ")} />
          <Stat label="Answered by" value={t.answeredBy.llm || 0} sub={`model · rules ${t.answeredBy.rules || 0}`} />
          <Stat label="Confirmations" value={a.confirmations.asked} sub={`approved ${a.confirmations.approved} · declined ${a.confirmations.declined}`} />
          <Stat label="Voice clips" value={m.voice.clips} sub={Object.entries(m.voice.byEngine).map(([k, v]) => `${k} ${v}`).join(" · ")} />
          <Stat label="Files stored" value={m.files.stored} sub={`${(m.files.bytes / 1048576).toFixed(1)} MB encrypted`} />
          <Stat label="Patients" value={m.users.patients} sub={`new ${m.users.newInWindow}`} />
          <Stat label="Doctors" value={m.users.doctors} />
        </div>
      </Chapter>
      <Chapter no="02" kicker="Usage" title="Calls per day" tone="soft">
        <div className="adm-bars" role="img" aria-label="Tool calls per day">
          {a.daily.length ? a.daily.map((d) => <div key={d.date} className="adm-bar" title={`${d.date}: ${d.calls}`}><i style={{ height: `${Math.max(6, (d.calls / max) * 100)}%` }} /><span>{d.date.slice(5)}</span></div>) : <p>No calls in this window.</p>}
        </div>
        <table className="adm-table"><thead><tr><th>Tool</th><th>Calls</th><th>OK</th><th>Failed</th><th>Denied</th><th>Asked</th><th>Declined</th></tr></thead>
          <tbody>{a.perTool.map((r) => <tr key={r.tool}><td>{r.tool}</td><td>{r.total}</td><td>{r.ok}</td><td className={r.failed ? "bad" : ""}>{r.failed}</td><td>{r.denied}</td><td>{r.asked}</td><td>{r.declined}</td></tr>)}</tbody></table>
      </Chapter>
      <Chapter no="03" kicker="Health" title="Services and problems" last>
        <ul className="adm-svc">{Object.entries(m.services).map(([k, v]) => <li key={k} className={v ? "ok" : "off"}><b>{k}</b> {v === true ? "configured" : v === false ? "not set" : v}</li>)}</ul>
        <h3>Recent problems</h3>
        {m.recentProblems.length ? <table className="adm-table"><thead><tr><th>When</th><th>Agent</th><th>Tool</th><th>Status</th><th>Detail</th></tr></thead>
          <tbody>{m.recentProblems.map((r, i) => <tr key={i}><td>{new Date(r.at).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" })}</td><td>{r.agent}</td><td>{r.tool}</td><td className="bad">{r.status}</td><td>{r.detail}</td></tr>)}</tbody></table> : <p>No failed or refused calls in this window.</p>}
      </Chapter>
    </>
  );
}
