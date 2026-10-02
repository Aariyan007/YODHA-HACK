// Home hero: a glowing 3D-style "living health" orb with an animated ECG heartbeat
// and floating glass vital chips. Decorative but data-backed; the headline + CTA sit
// beside it. All motion is GSAP and skipped for reduced motion.
import { useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import { gsap } from "gsap";
import { reducedMotion, useCountUp } from "../anim.js";
import { useT } from "../i18n.js";

const OVERALL = { good: "On track", watch: "Keep an eye", alert: "Needs attention" };

export default function Hero({ name, subtitle, insights, reminders, worst }) {
  const { t, lang } = useT();
  const ml = lang === "ml";
  const root = useRef(null);
  const ecg = useRef(null);

  const labs = insights?.labs || [];
  const get = (c) => labs.find((l) => l.code === c);
  const a1c = get("hba1c"), sbp = get("sbp"), dbp = get("dbp");
  const total = reminders?.length ?? 0;
  const taken = reminders?.filter((r) => r.taken).length ?? 0;
  const status = worst || a1c?.status || "good";

  const a1cVal = useCountUp(a1c?.value ?? 0, { decimals: 1 });
  const sbpVal = useCountUp(sbp?.value ?? 0);
  const dbpVal = useCountUp(dbp?.value ?? 0);

  useEffect(() => {
    if (!root.current || reducedMotion()) return;
    const ctx = gsap.context(() => {
      gsap.from(".hero-text > *", { y: 18, opacity: 0, stagger: 0.09, duration: 0.6, ease: "power3.out", clearProps: "all" });
      gsap.from(".orb-wrap", { scale: 0.86, opacity: 0, duration: 0.9, ease: "power3.out" });
      gsap.from(".orb-chip", { scale: 0.7, opacity: 0, stagger: 0.12, delay: 0.3, duration: 0.5, ease: "back.out(2)" });
      gsap.to(".orb-wrap", { y: -12, duration: 3.4, ease: "sine.inOut", repeat: -1, yoyo: true });
      gsap.to(".orb-ring", { rotate: 360, duration: 26, ease: "none", repeat: -1, transformOrigin: "50% 50%" });
      gsap.to(".orb-chip", { y: "+=7", duration: 2.6, ease: "sine.inOut", repeat: -1, yoyo: true, stagger: 0.4 });
      const path = ecg.current;
      if (path) {
        const len = path.getTotalLength();
        gsap.set(path, { strokeDasharray: len, strokeDashoffset: len });
        gsap.to(path, { strokeDashoffset: 0, duration: 1.6, ease: "power1.inOut", repeat: -1, repeatDelay: 0.5 });
      }
    }, root);
    return () => ctx.revert();
  }, []);

  return (
    <section ref={root} className={`hero3d status-${status}`}>
      <div className="hero-text">
        <span className={`hero-status-pill ${status}`}>{OVERALL[status]}</span>
        <h2>{name ? <>Welcome, <span className="greet-name">{name}</span></> : "Welcome"}</h2>
        <p className="greet-sub">{subtitle}</p>
        <div className="hero-cta">
          <Link className="primary-link" to="/insights">{ml ? "ആരോഗ്യ പരിശോധന" : "View health check"}</Link>
          <Link className="btn-link" to="/upload">{ml ? "രേഖ ചേർക്കുക" : "Add a record"} →</Link>
        </div>
      </div>

      <div className="orb-stage" aria-hidden="true">
        <div className="orb-wrap">
          <span className="orb-ring" />
          <span className="orb-ring r2" />
          <span className="orb">
            <svg className="orb-ecg" viewBox="0 0 220 120" preserveAspectRatio="none">
              <path ref={ecg} d="M0 60 H70 l10 -34 l14 64 l12 -52 l10 22 H220" />
            </svg>
          </span>
          {a1c && <span className="orb-chip c1"><b>{a1cVal}%</b><span>sugar avg</span></span>}
          {sbp && dbp && <span className="orb-chip c2"><b>{sbpVal}/{dbpVal}</b><span>mmHg</span></span>}
          {total > 0 && <span className="orb-chip c3"><b>{taken}/{total}</b><span>doses</span></span>}
        </div>
      </div>
    </section>
  );
}
