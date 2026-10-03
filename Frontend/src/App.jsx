import { Suspense, lazy, useEffect, useLayoutEffect, useRef, useState } from "react";
import { gsap } from "gsap";
import { reducedMotion } from "./anim.js";
import { Navigate, NavLink, Outlet, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { getToken, setToken } from "./api/client.js";
import { LangContext, useT } from "./i18n.js";
import { getTheme, setTheme } from "./theme.js";
import MediThreadAgent from "./components/agent/MediThreadAgent.jsx";
import { Tour, TourButton, TourWelcome } from "./components/tour/Tour.jsx";
import StartupScreen from "./components/StartupScreen.jsx";
import Login from "./pages/Login.jsx";
import Home from "./pages/Home.jsx";
import Timeline from "./pages/Timeline.jsx";
import Medicines from "./pages/Medicines.jsx";
import Insights from "./pages/Insights.jsx";
import Sharing from "./pages/Sharing.jsx";
import Snapshot from "./pages/Snapshot.jsx";
import Triage from "./pages/Triage.jsx";
import Upload from "./pages/Upload.jsx";
import Reminders from "./pages/Reminders.jsx";
import DoctorConsole from "./pages/DoctorConsole.jsx";
// The map page pulls in Leaflet; load it only when opened.
const Doctors = lazy(() => import("./pages/Doctors.jsx"));
import Profile from "./pages/Profile.jsx";
import Admin from "./pages/Admin.jsx";
import DoctorHome from "./pages/doctor/DoctorHome.jsx";

const PROFILE_KEY = "medithread_profile";
const LANG_KEY    = "medithread_lang";
// Only show startup once per browser session
const STARTUP_KEY = "medithread_started";

export function getProfile() {
  try { return JSON.parse(localStorage.getItem(PROFILE_KEY)); } catch { return null; }
}
export function saveSession({ token, profile }) {
  setToken(token);
  localStorage.setItem(PROFILE_KEY, JSON.stringify(profile));
}
export function saveProfile(profile) {
  localStorage.setItem(PROFILE_KEY, JSON.stringify(profile));
}
// "Skip for now" on the welcome form lasts for this browser session.
const SKIP_PROFILE_KEY = "medithread_skip_profile";
export const skipProfileForNow = () => sessionStorage.setItem(SKIP_PROFILE_KEY, "1");

// ── Language toggle ─────────────────────────────────────────
function LangToggle() {
  const { lang, setLang } = useT();
  return (
    <button className="lang" onClick={() => setLang(lang === "en" ? "ml" : "en")} aria-label="Switch language">
      {lang === "en" ? "മലയാളം" : "English"}
    </button>
  );
}

// ── Nav icons ────────────────────────────────────────────────
const NAV_ICONS = {
  "/":          <svg viewBox="0 0 18 18" fill="none" width="15" height="15"><path d="M2 7.5 9 2l7 5.5V16a1 1 0 01-1 1H3a1 1 0 01-1-1V7.5z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/><path d="M6.5 17v-6h5v6" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/></svg>,
  "/upload":    <svg viewBox="0 0 18 18" fill="none" width="15" height="15"><path d="M9 11.5V3M6 6l3-3 3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/><path d="M2 13v1.5A1.5 1.5 0 003.5 16h11A1.5 1.5 0 0016 14.5V13" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>,
  "/timeline":  <svg viewBox="0 0 18 18" fill="none" width="15" height="15"><circle cx="9" cy="9" r="2" fill="currentColor"/><path d="M9 2v4M9 12v4M2 9h4M12 9h4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>,
  "/medicines": <svg viewBox="0 0 18 18" fill="none" width="15" height="15"><rect x="2" y="6" width="14" height="9" rx="2" stroke="currentColor" strokeWidth="1.5"/><path d="M6 6V4a3 3 0 016 0v2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/><path d="M9 10v3M7.5 11.5h3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>,
  "/reminders": <svg viewBox="0 0 18 18" fill="none" width="15" height="15"><path d="M9 2a5 5 0 015 5v3l1.5 2.5H2.5L4 10V7a5 5 0 015-5z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/><path d="M7 14.5a2 2 0 004 0" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>,
  "/insights":  <svg viewBox="0 0 18 18" fill="none" width="15" height="15"><path d="M2 14 6 9l3 3 3-4 4 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>,
  "/triage":    <svg viewBox="0 0 18 18" fill="none" width="15" height="15"><path d="M9 2v8M6.5 4.5 9 2l2.5 2.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/><circle cx="9" cy="13" r="2" stroke="currentColor" strokeWidth="1.5"/></svg>,
  "/doctors":   <svg viewBox="0 0 18 18" fill="none" width="15" height="15"><path d="M9 16s5-4.6 5-8.5A5 5 0 004 7.5C4 11.4 9 16 9 16z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/><path d="M9 5.5v4M7 7.5h4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>,
  "/sharing":   <svg viewBox="0 0 18 18" fill="none" width="15" height="15"><circle cx="14" cy="4" r="2" stroke="currentColor" strokeWidth="1.5"/><circle cx="4" cy="9" r="2" stroke="currentColor" strokeWidth="1.5"/><circle cx="14" cy="14" r="2" stroke="currentColor" strokeWidth="1.5"/><path d="M6 8l6-3M6 10l6 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>,
};

// ── Page transition wrapper ──────────────────────────────────
// GSAP fade/rise on every route change, plus a thin sage "thread" that sweeps across the top.
function PageTransition({ children }) {
  const ref = useRef(null);
  useLayoutEffect(() => {
    if (!ref.current || reducedMotion()) return;
    const ctx = gsap.context(() => {
      gsap.fromTo(ref.current, { opacity: 0, y: 14, filter: "blur(3px)" },
        { opacity: 1, y: 0, filter: "blur(0px)", duration: 0.45, ease: "power3.out", clearProps: "all" });
      // Sections already on screen rise in one after another.
      const parts = ref.current.querySelectorAll(":scope > * > .section, :scope > * > .card, :scope > .section, :scope > .card");
      if (parts.length) gsap.from(parts, { y: 18, opacity: 0, duration: 0.5, stagger: 0.07, delay: 0.08, ease: "power3.out", clearProps: "transform,opacity" });
      gsap.fromTo(".route-thread", { scaleX: 0, opacity: 1, transformOrigin: "0% 50%" },
        { scaleX: 1, duration: 0.55, ease: "power2.inOut", onComplete: () => gsap.to(".route-thread", { opacity: 0, duration: 0.3 }) });
    });
    return () => ctx.revert();
  }, []);
  return <div ref={ref}>{children}</div>;
}

// Sliding indicator under the active tab.
function useTabIndicator(navRef, pathname) {
  useLayoutEffect(() => {
    const nav = navRef.current;
    const bar = nav?.querySelector(".tab-indicator");
    const active = nav?.querySelector("a.active");
    if (!nav || !bar) return;
    if (!active) { gsap.set(bar, { opacity: 0 }); return; }
    const x = active.offsetLeft, w = active.offsetWidth;
    if (reducedMotion() || !bar.dataset.ready) {
      gsap.set(bar, { x, width: w, opacity: 1 });
      bar.dataset.ready = "1";
    } else {
      gsap.to(bar, { x, width: w, opacity: 1, duration: 0.45, ease: "power3.out" });
    }
    active.scrollIntoView?.({ block: "nearest", inline: "nearest" });
  }, [navRef, pathname]);
}

// Primary buttons lean a few px toward the pointer (desktop only), via one delegated listener.
function useMagneticButtons() {
  useEffect(() => {
    if (reducedMotion() || window.matchMedia?.("(pointer: coarse)").matches) return;
    let current = null;
    const move = (e) => {
      const el = e.target.closest?.("button.primary:not(:disabled), .primary-link");
      if (current && current !== el) gsap.to(current, { x: 0, y: 0, duration: 0.4, ease: "elastic.out(1, 0.5)" });
      current = el;
      if (!el) return;
      const r = el.getBoundingClientRect();
      gsap.to(el, { x: ((e.clientX - r.left) / r.width - 0.5) * 6, y: ((e.clientY - r.top) / r.height - 0.5) * 5,
                    duration: 0.3, ease: "power2.out" });
    };
    document.addEventListener("pointermove", move);
    return () => document.removeEventListener("pointermove", move);
  }, []);
}

// ── App Layout ───────────────────────────────────────────────
function Layout() {
  const { t } = useT();
  const navigate = useNavigate();
  const location = useLocation();
  const navRef = useRef(null);
  useTabIndicator(navRef, location.pathname);
  useMagneticButtons();

  if (!getToken()) return <Navigate to="/login" replace />;
  const profile = getProfile();
  if (profile?.role === "doctor") return <Navigate to="/doctor" replace />;
  if (profile?.profileComplete === false && location.pathname !== "/profile" && !sessionStorage.getItem(SKIP_PROFILE_KEY)) {
    return <Navigate to="/profile?welcome=1" replace />;
  }

  const logout = () => {
    setToken(null);
    localStorage.removeItem(PROFILE_KEY);
    navigate("/login");
  };

  const tabs = [
    ["/",          t("home")],
    ["/upload",    t("upload")],
    ["/timeline",  t("timeline")],
    ["/medicines", t("medicines")],
    ["/reminders", t("reminders")],
    ["/insights",  t("insights")],
    ["/triage",    t("triage")],
    ["/doctors",   t("doctors")],
    ["/sharing",   t("sharing")],
  ];

  return (
    <div className="shell">
      <header className="top" role="banner">
        <span className="brand" aria-label="MediThread">MediThread</span>
        <div className="top-actions">
          <TourButton />
          <LangToggle />
          <NavLink to="/profile" className="profile-chip" aria-label="My profile">
            <span className="avatar" aria-hidden="true">{(profile?.name || "?").trim().charAt(0).toUpperCase()}</span>
            <span className="profile-chip-name">{profile?.name && profile.name !== "New patient" ? profile.name.split(" ")[0] : t("profile")}</span>
          </NavLink>
          <button className="ghost" onClick={logout} style={{ fontSize: "var(--font-size-sm)" }}>
            {t("logout")}
          </button>
        </div>
      </header>
      <div className="route-thread" aria-hidden="true" />
      <nav ref={navRef} className="tabs" role="navigation" aria-label="Main navigation">
        <span className="tab-indicator" aria-hidden="true" />
        {tabs.map(([to, label]) => (
          <NavLink key={to} to={to} end className={({ isActive }) => isActive ? "active" : ""}>
            <span className="tab-icon-wrap" aria-hidden="true">{NAV_ICONS[to]}</span>
            <span className="tab-label">{label}</span>
          </NavLink>
        ))}
      </nav>
      <main role="main" id="main-content">
        <div className="page-shell">
          <PageTransition key={location.pathname}>
            <Outlet />
          </PageTransition>
        </div>
      </main>
      <MediThreadAgent />
      <Tour />
      <TourWelcome />
    </div>
  );
}

// ── Doctor layout (no patient tabs) ──────────────────────────
function DoctorLayout() {
  const { t } = useT();
  const navigate = useNavigate();
  const location = useLocation();
  if (!getToken()) return <Navigate to="/login" replace />;
  const profile = getProfile();
  if (profile?.role !== "doctor") return <Navigate to="/" replace />;

  const logout = () => {
    setToken(null);
    localStorage.removeItem(PROFILE_KEY);
    navigate("/login");
  };

  return (
    <div className="shell">
      <header className="top" role="banner">
        <span className="brand" aria-label="MediThread">MediThread <span className="pill accent" style={{ marginLeft: 8 }}>Doctor</span></span>
        <div className="top-actions">
          <TourButton />
          <LangToggle />
          <span className="profile-chip">
            <span className="avatar" aria-hidden="true">{(profile?.name || "?").trim().charAt(0).toUpperCase()}</span>
            <span className="profile-chip-name">{profile?.name}</span>
          </span>
          <button className="ghost" onClick={logout}>{t("logout")}</button>
        </div>
      </header>
      <div className="route-thread" aria-hidden="true" />
      <main role="main" id="main-content">
        <div className="page-shell">
          <PageTransition key={location.pathname}>
            <Outlet />
          </PageTransition>
        </div>
      </main>
      <MediThreadAgent />
      <Tour />
      <TourWelcome />
    </div>
  );
}

// ── Root App ─────────────────────────────────────────────────
export default function App() {
  const [lang, setLangState] = useState(() => localStorage.getItem(LANG_KEY) || "en");
  const [showStartup, setShowStartup] = useState(() => !sessionStorage.getItem(STARTUP_KEY));

  const setLang = (l) => {
    localStorage.setItem(LANG_KEY, l);
    setLangState(l);
  };

  const handleStartupDone = () => {
    sessionStorage.setItem(STARTUP_KEY, "1");
    setShowStartup(false);
  };

  // Ensure the saved theme is applied as an attribute (the pre-paint inline
  // script can be missing in some embeds); default is the editorial paper look.
  useEffect(() => { setTheme(getTheme()); }, []);

  // Lenis smooth scroll, driven by the GSAP ticker so ScrollTrigger stays in sync.
  // Cleaned up on unmount (StrictMode mounts twice in dev) and skipped for reduced motion.
  useEffect(() => {
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
    let cancelled = false;
    let cleanup = () => {};
    Promise.all([import("lenis"), import("gsap"), import("gsap/ScrollTrigger")]).then(
      ([{ default: Lenis }, { gsap }, { ScrollTrigger }]) => {
        if (cancelled) return;
        gsap.registerPlugin(ScrollTrigger);
        const lenis = new Lenis({ duration: 1.1, easing: (t) => Math.min(1, 1.001 - Math.pow(2, -10 * t)) });
        lenis.on("scroll", ScrollTrigger.update);
        const tick = (time) => lenis.raf(time * 1000);
        gsap.ticker.add(tick);
        gsap.ticker.lagSmoothing(0);
        cleanup = () => {
          gsap.ticker.remove(tick);
          lenis.destroy();
        };
      },
    );
    return () => {
      cancelled = true;
      cleanup();
    };
  }, []);

  return (
    <LangContext.Provider value={{ lang, setLang }}>
      {showStartup && <StartupScreen onDone={handleStartupDone} />}
      <Routes>
        <Route path="/login"          element={<Login toggle={<LangToggle />} />} />
        <Route path="/share/:token"   element={<Snapshot toggle={<LangToggle />} />} />
        <Route path="/console/:token" element={<DoctorConsole />} />
        <Route path="doctor" element={<DoctorLayout />}>
          <Route index element={<DoctorHome />} />
        </Route>
        <Route element={<Layout />}>
          <Route index                element={<Home />} />
          <Route path="upload"        element={<Upload />} />
          <Route path="timeline"      element={<Timeline />} />
          <Route path="medicines"     element={<Medicines />} />
          <Route path="reminders"     element={<Reminders />} />
          <Route path="insights"      element={<Insights />} />
          <Route path="triage"        element={<Triage />} />
          <Route path="sharing"       element={<Sharing />} />
          <Route path="doctors"       element={<Suspense fallback={<div className="loading-state"><div className="spinner" /></div>}><Doctors /></Suspense>} />
          <Route path="profile"       element={<Profile />} />
          <Route path="admin"         element={<Admin />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </LangContext.Provider>
  );
}

