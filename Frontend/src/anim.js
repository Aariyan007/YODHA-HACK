// Shared GSAP motion helpers. Every effect:
//  - respects prefers-reduced-motion (content just appears),
//  - runs inside gsap.context() so React StrictMode's double mount cleans up properly,
//  - ends with clearProps so CSS hover/active styles keep working afterwards.
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { gsap } from "gsap";

export const reducedMotion = () =>
  typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

const useIsoLayoutEffect = typeof window !== "undefined" ? useLayoutEffect : useEffect;

// Stagger the direct children (or `selector` matches) of a container in when `deps` change.
export function useReveal(deps = [], { selector = ":scope > *", y = 16, stagger = 0.06, duration = 0.5, delay = 0 } = {}) {
  const ref = useRef(null);
  useIsoLayoutEffect(() => {
    const el = ref.current;
    if (!el || reducedMotion()) return;
    const ctx = gsap.context(() => {
      const items = el.querySelectorAll(selector);
      if (!items.length) return;
      gsap.from(items, { y, opacity: 0, duration, stagger, delay, ease: "power3.out", clearProps: "transform,opacity" });
    }, el);
    return () => ctx.revert();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return ref;
}

// Count a number up from 0 when it first appears or changes. Returns the text to show.
export function useCountUp(value, { duration = 0.9, decimals = 0 } = {}) {
  const [shown, setShown] = useState(reducedMotion() ? value : 0);
  useEffect(() => {
    if (value == null || Number.isNaN(Number(value))) return;
    if (reducedMotion()) {
      setShown(value);
      return;
    }
    const obj = { v: 0 };
    const tween = gsap.to(obj, {
      v: Number(value), duration, ease: "power2.out",
      onUpdate: () => setShown(obj.v),
    });
    return () => tween.kill();
  }, [value, duration]);
  return value == null ? "" : Number(shown).toFixed(decimals);
}

// A short "attention" pulse, e.g. when a new emergency banner appears.
export function pulse(el, { scale = 1.02, repeat = 2 } = {}) {
  if (!el || reducedMotion()) return;
  gsap.fromTo(el, { scale: 1 }, { scale, duration: 0.35, yoyo: true, repeat: repeat * 2 - 1, ease: "sine.inOut", clearProps: "transform" });
}

// Draw an SVG path from start to end.
export function drawPath(path, { duration = 1.1, delay = 0 } = {}) {
  if (!path || reducedMotion()) return null;
  const len = path.getTotalLength?.() || 400;
  return gsap.fromTo(path, { strokeDasharray: len, strokeDashoffset: len },
    { strokeDashoffset: 0, duration, delay, ease: "power2.inOut", clearProps: "strokeDasharray,strokeDashoffset" });
}

// Magnetic hover for primary buttons: follow the pointer a few px. Returns cleanup.
export function magnet(el, strength = 6) {
  if (!el || reducedMotion() || window.matchMedia?.("(pointer: coarse)").matches) return () => {};
  const move = (e) => {
    const r = el.getBoundingClientRect();
    const x = ((e.clientX - r.left) / r.width - 0.5) * strength;
    const y = ((e.clientY - r.top) / r.height - 0.5) * strength;
    gsap.to(el, { x, y, duration: 0.3, ease: "power2.out" });
  };
  const leave = () => gsap.to(el, { x: 0, y: 0, duration: 0.4, ease: "elastic.out(1, 0.5)" });
  el.addEventListener("pointermove", move);
  el.addEventListener("pointerleave", leave);
  return () => {
    el.removeEventListener("pointermove", move);
    el.removeEventListener("pointerleave", leave);
  };
}

// Reveal items that start below the fold when they scroll into view (IntersectionObserver, no scroll listeners).
// Items already on screen are left alone, so this never fights the page-load stagger.
export function useScrollIn(deps = [], { selector = ".section, .trend-card, .card", y = 22 } = {}) {
  const ref = useRef(null);
  useIsoLayoutEffect(() => {
    const root = ref.current;
    if (!root || reducedMotion() || typeof IntersectionObserver === "undefined") return;
    const vh = window.innerHeight;
    const items = [...root.querySelectorAll(selector)].filter((el) => el.getBoundingClientRect().top > vh * 0.92);
    if (!items.length) return;
    gsap.set(items, { opacity: 0, y });
    const io = new IntersectionObserver((entries) => {
      entries.forEach((en) => {
        if (!en.isIntersecting) return;
        io.unobserve(en.target);
        gsap.to(en.target, { opacity: 1, y: 0, duration: 0.6, ease: "power3.out", clearProps: "transform,opacity" });
      });
    }, { threshold: 0.12 });
    items.forEach((el) => io.observe(el));
    return () => {
      io.disconnect();
      gsap.set(items, { clearProps: "transform,opacity" });
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return ref;
}
