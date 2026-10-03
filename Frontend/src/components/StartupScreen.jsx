import { useEffect, useRef } from "react";
import { gsap } from "gsap";

/* MediThread startup screen: warm white and muted sage. A thin sage thread draws, the wordmark appears, then it fades into the app. */
export default function StartupScreen({ onDone }) {
  const rootRef = useRef(null);
  const svgRef  = useRef(null);

  useEffect(() => {
    const root = rootRef.current;
    const svg  = svgRef.current;
    if (!root || !svg) return;

    const orb     = svg.querySelector("#orb");
    const thread1 = svg.querySelector("#t1");
    const thread2 = svg.querySelector("#t2");
    const thread3 = svg.querySelector("#t3");
    const nodes   = svg.querySelectorAll(".nd");
    const wordMedi   = root.querySelector("#wm");
    const wordThread = root.querySelector("#wt");
    const tagline    = root.querySelector("#tg");

    // Prepare stroke animations
    [thread1, thread2, thread3].forEach((el) => {
      if (!el) return;
      const len = el.getTotalLength?.() || 180;
      gsap.set(el, { strokeDasharray: len, strokeDashoffset: len });
    });
    gsap.set(orb,  { scale: 0, opacity: 0, transformOrigin: "center center" });
    gsap.set(nodes, { scale: 0, opacity: 0, transformOrigin: "center center" });
    gsap.set([wordMedi, wordThread, tagline], { opacity: 0, y: 10 });
    gsap.set(root, { opacity: 1 });

    const tl = gsap.timeline({
      onComplete: () => {
        gsap.to(root, {
          opacity: 0, duration: 0.5, ease: "power2.inOut",
          onComplete: onDone,
        });
      },
    });

    tl
      .to(orb, { scale: 1, opacity: 1, duration: 0.3, ease: "back.out(2)" }, 0.1)
      .to(thread1, { strokeDashoffset: 0, duration: 0.5, ease: "power2.inOut" }, 0.4)
      .to(".nd-1", { scale: 1, opacity: 1, duration: 0.2, ease: "back.out(2)" }, 0.85)
      .to(thread2, { strokeDashoffset: 0, duration: 0.4, ease: "power2.inOut" }, 0.95)
      .to(".nd-2", { scale: 1, opacity: 1, duration: 0.2, ease: "back.out(2)" }, 1.3)
      .to(thread3, { strokeDashoffset: 0, duration: 0.35, ease: "power2.inOut" }, 1.4)
      .to(".nd-3", { scale: 1, opacity: 1, duration: 0.2, ease: "back.out(2)" }, 1.68)
      .to(wordMedi,   { opacity: 1, y: 0, duration: 0.35, ease: "power2.out" }, 1.75)
      .to(wordThread, { opacity: 1, y: 0, duration: 0.35, ease: "power2.out" }, 1.92)
      .to(tagline,    { opacity: 1, y: 0, duration: 0.28, ease: "power2.out" }, 2.1)
      .to({}, { duration: 0.45 }, 2.4);

    return () => tl.kill();
  }, [onDone]);

  // Brand colors (MediThread sage system)
  const SAGE     = "#659287";
  const SAGE_LT  = "#88BDA4";
  const SAGE_BG  = "#E6F2DD";
  const TEXT_MED = "var(--text-2)";
  const TEXT_DIM = "var(--text-3)";

  return (
    <div
      ref={rootRef}
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 9999,
        background: "var(--bg)",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        opacity: 0,
        gap: "2rem",
      }}
      aria-label="MediThread loading"
      aria-live="polite"
    >
      {/* SVG Thread Animation */}
      <svg
        ref={svgRef}
        width="300"
        height="160"
        viewBox="0 0 300 160"
        aria-hidden="true"
        style={{ display: "block" }}
      >
        {/* Origin orb */}
        <circle
          id="orb"
          cx="30" cy="80" r="5"
          fill={SAGE}
          opacity="0.9"
        />

        {/* Thread 1 */}
        <path
          id="t1"
          d="M 30 80 C 70 80 90 55 130 55"
          stroke={SAGE}
          strokeWidth="1.5"
          strokeLinecap="round"
          fill="none"
          opacity="0.8"
        />
        {/* Thread 2 */}
        <path
          id="t2"
          d="M 130 55 C 165 55 165 80 200 80"
          stroke={SAGE}
          strokeWidth="1.5"
          strokeLinecap="round"
          fill="none"
          opacity="0.8"
        />
        {/* Thread 3 */}
        <path
          id="t3"
          d="M 200 80 C 228 80 240 105 265 105"
          stroke={SAGE}
          strokeWidth="1.5"
          strokeLinecap="round"
          fill="none"
          opacity="0.8"
        />

        {/* Nodes */}
        <circle className="nd nd-1" cx="130" cy="55" r="5.5"
          fill={SAGE_BG} stroke={SAGE} strokeWidth="2" />
        <circle className="nd nd-2" cx="200" cy="80" r="4.5"
          fill={SAGE_BG} stroke={SAGE} strokeWidth="2" />
        <circle className="nd nd-3" cx="265" cy="105" r="4"
          fill={SAGE_BG} stroke={SAGE} strokeWidth="2" />

        {/* Node micro-labels */}
        <text className="nd nd-1" x="130" y="42"
          textAnchor="middle" fontFamily="Inter, sans-serif"
          fontSize="8" fill={SAGE_LT}>lab</text>
        <text className="nd nd-2" x="200" y="67"
          textAnchor="middle" fontFamily="Inter, sans-serif"
          fontSize="8" fill={SAGE_LT}>rx</text>
        <text className="nd nd-3" x="265" y="92"
          textAnchor="middle" fontFamily="Inter, sans-serif"
          fontSize="8" fill={SAGE_LT}>visit</text>
      </svg>

      {/* Wordmark */}
      <div style={{ textAlign: "center", userSelect: "none" }}>
        <div style={{ display: "flex", alignItems: "baseline", justifyContent: "center" }}>
          <span
            id="wm"
            style={{
              fontFamily: "Inter, system-ui, sans-serif",
              fontSize: "clamp(1.6rem, 5vw, 2.2rem)",
              fontWeight: 700,
              color: TEXT_MED,
              letterSpacing: "-0.03em",
              lineHeight: 1,
            }}
          >
            Medi
          </span>
          <span
            id="wt"
            style={{
              fontFamily: "Inter, system-ui, sans-serif",
              fontSize: "clamp(1.6rem, 5vw, 2.2rem)",
              fontWeight: 700,
              color: "var(--brand)",
              letterSpacing: "-0.03em",
              lineHeight: 1,
            }}
          >
            Thread
          </span>
        </div>
        <p
          id="tg"
          style={{
            marginTop: "0.55rem",
            fontFamily: "Inter, system-ui, sans-serif",
            fontSize: "0.75rem",
            color: TEXT_DIM,
            letterSpacing: "0.08em",
            textTransform: "uppercase",
          }}
        >
          Your health story, in one thread
        </p>
      </div>
    </div>
  );
}
