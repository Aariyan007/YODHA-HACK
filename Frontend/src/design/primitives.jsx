// MediThread design-system primitives.
//
// Chapter   a full-bleed band of the page with its own tone, a numbered label and a serif title.
//           The PAGE is part of the design: tone changes tell the reader a new section started.
// RV        reveal-on-scroll wrapper (opacity + translateY), once, observer based.
// useMedia  responsive hook for layout decisions that CSS alone cannot make.
// threadLink  tiny store that links a document preview to its node in the Health Thread.
//
// Reveal uses IntersectionObserver + GSAP instead of ScrollTrigger positions: pages here load data late, and
// ScrollTrigger start positions go stale whenever content above them changes height. Observers do not.
import { useLayoutEffect, useRef, useState, useSyncExternalStore } from "react";
import { gsap } from "gsap";
import { reducedMotion } from "../anim.js";

// ── scroll reveal ───────────────────────────────────────────────────────────
export function useRevealOnView(ref, { y = 20, stagger = 0.08, duration = 0.6, delay = 0, selector = null } = {}) {
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el || reducedMotion() || typeof IntersectionObserver === "undefined") return;
    const targets = selector ? [...el.querySelectorAll(selector)] : [el];
    if (!targets.length) return;
    gsap.set(targets, { opacity: 0, y });
    let tween;
    const io = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) return;
        io.disconnect();
        tween = gsap.to(targets, { opacity: 1, y: 0, duration, delay, stagger, ease: "power3.out", clearProps: "transform,opacity" });
      },
      { threshold: 0.1, rootMargin: "0px 0px -6% 0px" },
    );
    io.observe(el);
    return () => {
      io.disconnect();
      tween?.kill();
      gsap.set(targets, { clearProps: "transform,opacity" });
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return ref;
}

/** Reveal one element, or (with `stagger`) its direct children one after another. */
export function RV({ as: Tag = "div", children, className = "", stagger = 0, selector, y, delay, ...rest }) {
  const ref = useRef(null);
  useRevealOnView(ref, { selector: stagger ? selector || ":scope > *" : null, stagger: stagger || 0, y, delay });
  return <Tag ref={ref} className={className} {...rest}>{children}</Tag>;
}

// ── Chapter ─────────────────────────────────────────────────────────────────
/**
 * tone: "ground" (page colour) | "soft" (soft sage region) | "warm" (warm white) | "neutral" (quiet grey-green)
 * last: the final chapter of a page (the band runs to the bottom edge).
 * no:   "01" style chapter number; kicker: small label; title: serif heading; aside: right-aligned slot (links).
 */
export function Chapter({ no, kicker, title, aside, tone = "ground", id, className = "", children, last = false }) {
  return (
    <section id={id} className={`mt-chapter t-${tone}${last ? " last" : ""} ${className}`}>
      {(title || kicker) && (
        <RV as="header" className="mt-ch-head">
          <div>
            {(no || kicker) && (
              <div className="mt-label">
                {no && <span className="mt-ch-no">{no}</span>}
                {kicker}
              </div>
            )}
            {title && <h2 className="mt-ch-title">{title}</h2>}
          </div>
          {aside && <div className="mt-ch-aside">{aside}</div>}
        </RV>
      )}
      {children}
    </section>
  );
}

// ── responsive hook ─────────────────────────────────────────────────────────
export function useMedia(query) {
  const get = () => (typeof window !== "undefined" && window.matchMedia ? window.matchMedia(query).matches : false);
  const [match, setMatch] = useState(get);
  useLayoutEffect(() => {
    const mq = window.matchMedia(query);
    const on = () => setMatch(mq.matches);
    on();
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, [query]);
  return match;
}

// ── document <-> thread link ────────────────────────────────────────────────
let activeDoc = null;
const subs = new Set();
export const threadLink = {
  set(id) {
    if (activeDoc !== id) {
      activeDoc = id;
      subs.forEach((f) => f());
    }
  },
  get: () => activeDoc,
  subscribe(f) {
    subs.add(f);
    return () => subs.delete(f);
  },
};
export const useLinkedDoc = () => useSyncExternalStore(threadLink.subscribe, threadLink.get, () => null);

/** An arrow that slides forward when its parent link / button is hovered or focused (CSS does the movement). */
export const Arrow = () => <span className="mt-arrow" aria-hidden="true">→</span>;
