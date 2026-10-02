import { useEffect, useRef, useState } from "react";
import { gsap } from "gsap";
import { useNavigate } from "react-router-dom";
import { requestOtp, verifyOtp } from "../api/client.js";
import { saveSession } from "../App.jsx";
import { useT } from "../i18n.js";

// ── Animated thread background ────────────────────────────────
function ThreadBackground() {
  const svgRef = useRef(null);
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const paths = svg.querySelectorAll("path");
    const dots  = svg.querySelectorAll("circle");

    paths.forEach((p) => {
      const len = p.getTotalLength?.() || 300;
      gsap.set(p, { strokeDasharray: len, strokeDashoffset: len });
    });
    gsap.set(dots, { scale: 0, opacity: 0, transformOrigin: "center center" });

    const tl = gsap.timeline({ delay: 0.1 });
    paths.forEach((p, i) => {
      tl.to(p, { strokeDashoffset: 0, duration: 0.9, ease: "power2.inOut" }, i * 0.2);
    });
    dots.forEach((d, i) => {
      tl.to(d, { scale: 1, opacity: 1, duration: 0.3, ease: "back.out(2)" }, 0.4 + i * 0.15);
    });

    return () => tl.kill();
  }, []);

  return (
    <svg
      ref={svgRef}
      aria-hidden="true"
      style={{
        position: "absolute",
        inset: 0,
        width: "100%",
        height: "100%",
        pointerEvents: "none",
        zIndex: 0,
        opacity: 0.6,
      }}
      viewBox="0 0 800 600"
      preserveAspectRatio="xMidYMid slice"
      fill="none"
    >
      <defs>
        <filter id="login-glow">
          <feGaussianBlur stdDeviation="2" result="blur" />
          <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
        </filter>
      </defs>
      {/* Long curved thread — muted sage */}
      <path d="M -20 500 C 100 450 150 350 200 280 S 300 180 380 150 S 520 130 600 100 S 720 60 820 40"
        stroke="rgba(85,122,106,0.18)" strokeWidth="1.5" strokeLinecap="round" />
      {/* Branch */}
      <path d="M 380 150 C 400 200 390 260 420 310 S 450 380 480 420"
        stroke="rgba(85,122,106,0.12)" strokeWidth="1" strokeLinecap="round" />
      {/* Second thread */}
      <path d="M -20 80 C 80 100 160 150 220 200 S 300 260 320 300"
        stroke="rgba(85,122,106,0.12)" strokeWidth="1" strokeLinecap="round" />
      {/* Nodes */}
      <circle cx="200" cy="280" r="4" fill="rgba(85,122,106,0.35)" />
      <circle cx="380" cy="150" r="5" fill="rgba(85,122,106,0.40)" />
      <circle cx="600" cy="100" r="3.5" fill="rgba(85,122,106,0.30)" />
      <circle cx="480" cy="420" r="3" fill="rgba(85,122,106,0.25)" />
      <circle cx="220" cy="200" r="3" fill="rgba(85,122,106,0.25)" />
    </svg>
  );
}

// ── Form panel with staggered entry ──────────────────────────
function LoginPanel({ toggle, children }) {
  const ref = useRef(null);
  useEffect(() => {
    if (!ref.current) return;
    const els = ref.current.querySelectorAll("[data-anim]");
    gsap.from(els, {
      opacity: 0, y: 18, duration: 0.45, stagger: 0.07, ease: "power2.out", delay: 0.05,
      clearProps: "all",
    });
  }, []);

  return (
    <div
      ref={ref}
      style={{
        width: "100%",
        maxWidth: 380,
        position: "relative",
        zIndex: 1,
      }}
    >
      {/* Language toggle */}
      <div data-anim style={{ display: "flex", justifyContent: "flex-end", marginBottom: "var(--sp-8)" }}>
        {toggle}
      </div>

      {/* Brand */}
      <div data-anim style={{ marginBottom: "var(--sp-6)" }}>
        <div className="brand big" aria-label="MediThread" style={{ marginBottom: "var(--sp-2)" }}>
          MediThread
        </div>
        <p style={{
          fontSize: "var(--font-size-lg)",
          color: "var(--text-2)",
          lineHeight: 1.4,
          fontWeight: 300,
          margin: 0,
        }}>
          Your health story,<br />in one thread.
        </p>
      </div>

      {/* Auth card */}
      <div data-anim className="card" style={{ padding: "var(--sp-6)" }}>
        {children}
      </div>
    </div>
  );
}

// ── Post-login thread transition overlay ──────────────────────
function LoginTransition({ onDone }) {
  const ref = useRef(null);
  useEffect(() => {
    if (!ref.current) return;
    gsap.fromTo(ref.current,
      { opacity: 0 },
      {
        opacity: 1, duration: 0.2, ease: "power1.in",
        onComplete: () => {
          gsap.to(ref.current, {
            opacity: 0, duration: 0.4, delay: 0.25, ease: "power2.inOut",
            onComplete: onDone,
          });
        },
      }
    );
  }, [onDone]);

  return (
    <div
      ref={ref}
      aria-hidden="true"
      style={{
        position: "fixed", inset: 0, zIndex: 8888,
        background: "var(--bg-glass)",
        backdropFilter: "blur(8px)",
        display: "flex", alignItems: "center", justifyContent: "center",
        opacity: 0,
      }}
    >
      <svg width="160" height="50" viewBox="0 0 160 50" fill="none" aria-hidden="true">
        <path d="M 8 25 C 40 8 64 42 96 25 S 128 8 152 25"
          stroke="#557A6A" strokeWidth="1.5" strokeLinecap="round"
          strokeDasharray="200" strokeDashoffset="0" />
        <circle cx="96" cy="25" r="4" fill="#557A6A" />
      </svg>
    </div>
  );
}

export default function Login({ toggle }) {
  const { t } = useT();
  const navigate = useNavigate();

  const [phone,        setPhone]        = useState("9876543210");
  const [otp,          setOtp]          = useState("");
  const [sent,         setSent]         = useState(false);
  const [busy,         setBusy]         = useState(false);
  const [error,        setError]        = useState(null);
  const [transitioning, setTransitioning] = useState(false);

  const run = async (fn) => {
    setBusy(true);
    setError(null);
    try { await fn(); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  };

  const send = (e) => {
    e.preventDefault();
    run(async () => { await requestOtp(phone); setSent(true); });
  };

  const verify = (e) => {
    e.preventDefault();
    run(async () => {
      saveSession(await verifyOtp(phone, otp));
      // Trigger brief thread transition before navigating
      setTransitioning(true);
    });
  };

  const handleTransitionDone = () => {
    navigate("/");
  };

  return (
    <div style={{
      minHeight: "100dvh",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      padding: "var(--sp-8) var(--sp-4)",
      background: "var(--bg)",
      position: "relative",
      overflow: "hidden",
    }}>
      <ThreadBackground />

      {transitioning && <LoginTransition onDone={handleTransitionDone} />}

      <LoginPanel toggle={toggle}>
        <form onSubmit={sent ? verify : send} noValidate>
          <div style={{ display: "grid", gap: "var(--sp-4)" }}>
            <label>
              <span>{t("phone")}</span>
              <input
                id="phone-input"
                inputMode="tel"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                disabled={sent}
                required
                autoComplete="tel"
              />
            </label>

            {sent && (
              <label className="animate-in-fast">
                <span>{t("otp")}</span>
                <input
                  id="otp-input"
                  inputMode="numeric"
                  maxLength={6}
                  pattern="\d{6}"
                  value={otp}
                  onChange={(e) => setOtp(e.target.value.replace(/\D/g, ""))}
                  autoFocus
                  required
                  autoComplete="one-time-code"
                />
              </label>
            )}

            <button
              id="login-submit-btn"
              className="primary w-full"
              disabled={busy}
              style={{ marginTop: "var(--sp-2)" }}
            >
              {busy
                ? <span style={{ display: "flex", alignItems: "center", gap: "var(--sp-2)", justifyContent: "center" }}>
                    <span className="spinner" style={{ width: 16, height: 16, borderWidth: 2 }} />
                    {sent ? t("verify") : t("sendOtp")}
                  </span>
                : (sent ? t("verify") : t("sendOtp"))
              }
            </button>
          </div>

          {error && <p className="error text-sm mt-3" role="alert">{error}</p>}
          <p className="text-dim text-xs mt-4" style={{ textAlign: "center" }}>{t("demoHint")}</p>
        </form>
      </LoginPanel>
    </div>
  );
}
