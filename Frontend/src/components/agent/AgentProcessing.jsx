import { useEffect, useRef } from "react";
import { gsap } from "gsap";
import { reducedMotion } from "../../anim.js";

// "Working through your health thread": a thread being walked, node by node. Not typing dots.
export default function AgentProcessing({ label }) {
  const ref = useRef(null);
  useEffect(() => {
    const el = ref.current;
    if (!el || reducedMotion()) return;
    const ctx = gsap.context(() => {
      const nodes = el.querySelectorAll(".n");
      const line = el.querySelector(".ln");
      gsap.set(nodes, { scale: 0.6, opacity: 0.35 });
      gsap.set(line, { scaleY: 0, transformOrigin: "top" });
      const tl = gsap.timeline({ repeat: -1, repeatDelay: 0.25 });
      tl.to(line, { scaleY: 1, duration: 1.1, ease: "power1.inOut" }, 0);
      nodes.forEach((n, i) => tl.to(n, { scale: 1, opacity: 1, duration: 0.3, ease: "power2.out" }, 0.1 + i * 0.4));
      tl.to([...nodes, line], { opacity: 0.2, duration: 0.3 }, 1.5).set(nodes, { scale: 0.6 }).set([...nodes, line], { opacity: 1 });
    }, el);
    return () => ctx.revert();
  }, []);
  return (
    <div className="ag-proc" ref={ref} role="status" aria-live="polite" data-a>
      <div className="ag-proc-art" aria-hidden="true">
        <span className="ln" />
        <span className="n a" /><span className="n b" /><span className="n c" />
      </div>
      <div>
        <div className="ag-proc-t">Working through your health thread…</div>
        {label && <div className="ag-proc-s">{label}</div>}
      </div>
    </div>
  );
}
