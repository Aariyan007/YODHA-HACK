// "At a glance" strip for the patient Home: four numbers that answer "how am I doing today?".
// Values count up, the dose ring fills, sparklines draw; all of it is skipped for reduced motion.
import { useEffect, useRef } from "react";
import { gsap } from "gsap";
import { Link } from "react-router-dom";
import { reducedMotion, useCountUp, useReveal } from "../anim.js";
import { Sparkline } from "./charts.jsx";

const STATUS_TEXT = { good: "On track", watch: "Keep an eye", alert: "Needs attention" };

function Tile({ label, to, status, children, foot }) {
  const body = (
    <>
      <span className="gl-label">{label}</span>
      {children}
      {foot && <span className={`gl-foot ${status || ""}`}>{foot}</span>}
    </>
  );
  return to ? <Link to={to} className={`gl-tile ${status || ""}`}>{body}</Link> : <div className={`gl-tile ${status || ""}`}>{body}</div>;
}

function DoseRing({ taken, total }) {
  const ref = useRef(null);
  const R = 26, C = 2 * Math.PI * R;
  const frac = total ? taken / total : 0;
  useEffect(() => {
    const arc = ref.current;
    if (!arc) return;
    if (reducedMotion()) { arc.style.strokeDashoffset = String(C * (1 - frac)); return; }
    const tw = gsap.fromTo(arc, { strokeDashoffset: C }, { strokeDashoffset: C * (1 - frac), duration: 1, ease: "power3.out" });
    return () => tw.kill();
  }, [frac, C]);
  return (
    <svg viewBox="0 0 64 64" className="gl-ring" aria-hidden="true">
      <circle cx="32" cy="32" r={R} className="gl-ring-bg" />
      <circle ref={ref} cx="32" cy="32" r={R} className="gl-ring-arc" strokeDasharray={C} strokeDashoffset={C} transform="rotate(-90 32 32)" />
    </svg>
  );
}

export default function GlanceStrip({ insights, reminders, warnings }) {
  const labs = insights?.labs || [];
  const get = (c) => labs.find((l) => l.code === c);
  const a1c = get("hba1c"), sbp = get("sbp"), dbp = get("dbp");
  const series = (c) => insights?.series?.find((s) => s.code === c)?.points;
  const total = reminders?.length ?? 0;
  const taken = reminders?.filter((r) => r.taken).length ?? 0;
  const ref = useReveal([!!insights, total], { selector: ".gl-tile", stagger: 0.07, y: 14 });
  const a1cVal = useCountUp(a1c?.value ?? 0, { decimals: 1 });
  const sbpVal = useCountUp(sbp?.value ?? 0);
  const dbpVal = useCountUp(dbp?.value ?? 0);
  const takenVal = useCountUp(taken);
  const warnVal = useCountUp(warnings ?? 0);
  const bpStatus = [sbp?.status, dbp?.status].includes("alert") ? "alert" : [sbp?.status, dbp?.status].includes("watch") ? "watch" : sbp ? "good" : "";

  return (
    <div ref={ref} className="gl-strip" role="group" aria-label="Today at a glance">
      {a1c && (
        <Tile label="Sugar average" to="/insights" status={a1c.status} foot={STATUS_TEXT[a1c.status]}>
          <span className="gl-value">{a1cVal}<small>%</small></span>
          <Sparkline points={series("hba1c") || insights.hba1c} code="hba1c" />
        </Tile>
      )}
      {sbp && dbp && (
        <Tile label="Blood pressure" to="/insights" status={bpStatus} foot={STATUS_TEXT[bpStatus]}>
          <span className="gl-value">{sbpVal}<span className="gl-slash">/</span>{dbpVal}<small>mmHg</small></span>
        </Tile>
      )}
      {total > 0 && (
        <Tile label="Doses today" status={taken === total ? "good" : ""} foot={taken === total ? "All done" : `${total - taken} to go`}>
          <span className="gl-value">{takenVal}<small>of {total}</small></span>
          <DoseRing taken={taken} total={total} />
        </Tile>
      )}
      <Tile label="Warnings" status={warnings ? "watch" : "good"} foot={warnings ? "Open below" : "All clear"}>
        <span className="gl-value">{warnVal}</span>
      </Tile>
    </div>
  );
}
