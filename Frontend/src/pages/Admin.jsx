import { useEffect, useState } from "react";
import { getAdminLive, getAdminMetrics } from "../api/client.js";
import { Chapter } from "../design/primitives.jsx";

const Stat = ({ label, value, sub }) => (
  <div className="adm-stat"><div className="adm-n">{value ?? 0}</div><div className="adm-l">{label}</div>{sub && <div className="adm-s">{sub}</div>}</div>
);

const ago = (t) => (t ? `${Math.max(0, Math.round(Date.now() / 1000 - t))}s ago` : "");

// The whole running system, refreshed every 2 s: every API copy, worker and scheduler, the upload queue,
// requests per second, latency and the circuit breakers. Counts only.
function LiveSystem() {
  const [d, setD] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => {
    let on = true;
    const tick = () => getAdminLive().then((x) => { if (on) { setD(x); setErr(null); } }).catch((e) => on && setErr(e.message));
    tick();
    const id = setInterval(tick, 2000);
    return () => { on = false; clearInterval(id); };
  }, []);
  if (err && !d) return <Chapter no="00" kicker="Live" title="Live system" tone="soft"><p>{err}</p></Chapter>;
  if (!d) return <Chapter no="00" kicker="Live" title="Live system" tone="soft"><p>Connecting…</p></Chapter>;
  const max = Math.max(1, ...d.series.map((x) => x.rps));
  const open = d.breakers.filter((b) => b.state === "open");
  return (
    <Chapter no="00" kicker="Live · refreshes every 2 s" title="The running system" tone="soft">
      <div className="adm-grid">
        <Stat label="Requests / second" value={d.rpsNow} sub={`${d.lastMinute.req} in the last minute`} />
        <Stat label="Response time" value={d.p50 != null ? `${d.p50} ms` : "–"} sub={d.p95 != null ? `p95 under ${d.p95} ms` : "no traffic yet"} />
        <Stat label="Errors (1 min)" value={d.lastMinute.e5} sub={`busy replies ${d.lastMinute.shed} · rate limited ${d.lastMinute.e429}`} />
        <Stat label="API copies" value={d.api.length} sub="behind the nginx load balancer" />
        <Stat label="Upload workers" value={d.workers.length} sub={`queue: ${d.queue} waiting`} />
        <Stat label="Schedulers" value={d.schedulers.length} sub={d.schedulerLeader ? `leader ${d.schedulerLeader.slice(0, 8)}` : "no leader"} />
        <Stat label="Circuit breakers" value={open.length ? `${open.length} open` : "all closed"} sub={open.map((b) => b.name).join(", ") || `${d.breakers.length} watched`} />
      </div>
      <div className="adm-bars adm-live" role="img" aria-label="Requests per second over the last minute">
        {d.series.map((x) => <div key={x.t} className={`adm-bar${x.errors ? " bad" : ""}`} title={`${new Date(x.t * 1000).toLocaleTimeString()}: ${x.rps}/s${x.avgMs ? `, avg ${x.avgMs} ms` : ""}${x.errors ? `, ${x.errors} errors` : ""}`}><i style={{ height: `${Math.max(3, (x.rps / max) * 100)}%` }} /><span>{x.rps}</span></div>)}
      </div>
      <table className="adm-table"><thead><tr><th>Part</th><th>Id</th><th>State</th><th>Now</th></tr></thead>
        <tbody>
          {d.api.map((a) => <tr key={a.id}><td>API copy</td><td>{a.id.slice(0, 12)}</td><td className="ok">up · {ago(a.t)}</td><td>fast {a.lanes?.fast?.active ?? 0}/{a.lanes?.fast?.size ?? "?"} (waiting {a.lanes?.fast?.waiting ?? 0}) · AI {a.lanes?.ai?.active ?? 0}/{a.lanes?.ai?.size ?? "?"}</td></tr>)}
          {d.workers.map((w) => <tr key={w.id}><td>Worker</td><td>{w.id.slice(0, 12)}</td><td className="ok">{w.busy ? "working" : "idle"} · {ago(w.t)}</td><td>done {w.done ?? 0} · failed {w.failed ?? 0}</td></tr>)}
          {d.schedulers.map((s) => <tr key={s.id}><td>Scheduler</td><td>{s.id.slice(0, 12)}</td><td className={s.role === "leader" ? "ok" : ""}>{s.role}</td><td>{s.role === "leader" ? "sends the reminders" : "standing by"}</td></tr>)}
          {d.breakers.map((b) => <tr key={b.name}><td>Breaker</td><td>{b.name}</td><td className={b.state === "open" ? "bad" : "ok"}>{b.state}{b.reopensIn ? ` · retry in ${b.reopensIn}s` : ""}</td><td>opened {b.opened} times{b.lastError ? ` · last ${b.lastError}` : ""}</td></tr>)}
        </tbody></table>
    </Chapter>
  );
}

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
      <LiveSystem />
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
