import { useEffect, useRef, useState } from "react";
import { gsap } from "gsap";
import { useNavigate } from "react-router-dom";
import { getAuthConfig, loginAccount, registerAccount, requestOtp, verifyOtp } from "../api/client.js";
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
  const { lang } = useT();
  const ml = lang === "ml";
  const navigate = useNavigate();

  const [mode,    setMode]    = useState("signin"); // signin | register
  const [role,    setRole]    = useState("patient");
  const [name,    setName]    = useState("");
  const [email,   setEmail]   = useState("");
  const [password, setPassword] = useState("");
  const [specialty, setSpecialty] = useState("");
  const [hospital,  setHospital]  = useState("");
  const [show,    setShow]    = useState(false);
  const [busy,    setBusy]    = useState(false);
  const [error,   setError]   = useState(null);
  const [demoLogin, setDemoLogin] = useState(false);
  const [transitioning, setTransitioning] = useState(false);
  const [dest, setDest] = useState("/");

  useEffect(() => {
    getAuthConfig().then((c) => setDemoLogin(!!c.demoLogin)).catch(() => {});
  }, []);

  const finish = (session) => {
    saveSession(session);
    setDest(session.profile?.role === "doctor" ? "/doctor" : "/");
    setTransitioning(true);
  };

  const run = async (fn) => {
    setBusy(true);
    setError(null);
    try { await fn(); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  };

  const submit = (e) => {
    e.preventDefault();
    if (mode === "register" && password.length < 8) {
      setError(ml ? "പാസ്‌വേഡിൽ കുറഞ്ഞത് 8 അക്ഷരം വേണം." : "Your password needs at least 8 characters.");
      return;
    }
    run(async () => {
      finish(
        mode === "register"
          ? await registerAccount({ role, name: name.trim(), email: email.trim(), password, specialty, hospital })
          : await loginAccount(email.trim(), password),
      );
    });
  };

  const tryDemo = () =>
    run(async () => {
      await requestOtp("9876543210");
      finish(await verifyOtp("9876543210", "123456"));
    });

  const L = {
    signin: ml ? "സൈൻ ഇൻ" : "Sign in",
    create: ml ? "അക്കൗണ്ട് ഉണ്ടാക്കുക" : "Create account",
    patient: ml ? "ഞാൻ രോഗിയാണ്" : "I'm a patient",
    doctor: ml ? "ഞാൻ ഡോക്ടറാണ്" : "I'm a doctor",
    name: ml ? "പേര്" : role === "doctor" ? "Your name (as patients see it)" : "Full name",
    email: ml ? "ഇമെയിൽ" : "Email",
    password: ml ? "പാസ്‌വേഡ്" : "Password",
    hint: ml ? "കുറഞ്ഞത് 8 അക്ഷരം" : "At least 8 characters",
    specialty: ml ? "വിഭാഗം (ഓപ്ഷണൽ)" : "Specialty (optional)",
    hospital: ml ? "ആശുപത്രി / ക്ലിനിക് (ഓപ്ഷണൽ)" : "Hospital or clinic (optional)",
    show: show ? (ml ? "മറയ്ക്കുക" : "Hide") : (ml ? "കാണിക്കുക" : "Show"),
    demo: ml ? "ഡെമോ രോഗിയെ പരീക്ഷിക്കുക" : "Try the demo patient",
    note: ml ? "ഇമെയിൽ പരിശോധനയോ പാസ്‌വേഡ് റീസെറ്റോ ഇല്ല. പാസ്‌വേഡ് മറന്നാൽ പുതിയ അക്കൗണ്ട് ഉണ്ടാക്കുക." : "No email check or password reset yet. If you forget your password, make a new account.",
  };
  const submitLabel = mode === "register" ? L.create : L.signin;

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

      {transitioning && <LoginTransition onDone={() => navigate(dest)} />}

      <LoginPanel toggle={toggle}>
        <div className="seg" role="tablist" aria-label="Sign in or create account">
          {[["signin", L.signin], ["register", L.create]].map(([m, label]) => (
            <button key={m} type="button" role="tab" aria-selected={mode === m} className={mode === m ? "on" : ""}
              onClick={() => { setMode(m); setError(null); }}>
              {label}
            </button>
          ))}
        </div>

        <form onSubmit={submit} noValidate style={{ marginTop: "var(--sp-5)" }}>
          <div style={{ display: "grid", gap: "var(--sp-4)" }}>
            {mode === "register" && (
              <div className="seg" role="radiogroup" aria-label="Account type">
                {[["patient", L.patient], ["doctor", L.doctor]].map(([r, label]) => (
                  <button key={r} type="button" role="radio" aria-checked={role === r} className={role === r ? "on" : ""}
                    onClick={() => setRole(r)}>
                    {label}
                  </button>
                ))}
              </div>
            )}

            {mode === "register" && (
              <label>
                <span>{L.name}</span>
                <input value={name} onChange={(e) => setName(e.target.value)} required minLength={2} autoComplete="name" />
              </label>
            )}

            <label>
              <span>{L.email}</span>
              <input type="email" inputMode="email" value={email} onChange={(e) => setEmail(e.target.value)}
                required autoComplete="email" autoCapitalize="none" spellCheck={false} />
            </label>

            <label>
              <span>{L.password}</span>
              <div className="pw-row">
                <input type={show ? "text" : "password"} value={password} onChange={(e) => setPassword(e.target.value)}
                  required autoComplete={mode === "register" ? "new-password" : "current-password"} />
                <button type="button" className="ghost" onClick={() => setShow((v) => !v)} aria-pressed={show}>{L.show}</button>
              </div>
              {mode === "register" && <span className="text-dim text-xs">{L.hint}</span>}
            </label>

            {mode === "register" && role === "doctor" && (
              <>
                <label>
                  <span>{L.specialty}</span>
                  <input value={specialty} onChange={(e) => setSpecialty(e.target.value)} maxLength={80} />
                </label>
                <label>
                  <span>{L.hospital}</span>
                  <input value={hospital} onChange={(e) => setHospital(e.target.value)} maxLength={120} />
                </label>
              </>
            )}

            <button id="login-submit-btn" className="primary w-full" disabled={busy || !email || !password || (mode === "register" && !name.trim())}>
              {busy
                ? <span style={{ display: "flex", alignItems: "center", gap: "var(--sp-2)", justifyContent: "center" }}>
                    <span className="spinner" style={{ width: 16, height: 16, borderWidth: 2 }} />
                    {submitLabel}
                  </span>
                : submitLabel}
            </button>
          </div>

          {error && <p className="error text-sm mt-3" role="alert">{error}</p>}

          {demoLogin && (
            <button type="button" className="w-full" style={{ marginTop: "var(--sp-4)" }} onClick={tryDemo} disabled={busy}>
              {L.demo}
            </button>
          )}
          {mode === "register" && <p className="text-dim text-xs mt-4" style={{ textAlign: "center" }}>{L.note}</p>}
        </form>
      </LoginPanel>
    </div>
  );
}
