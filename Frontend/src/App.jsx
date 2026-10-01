import { useEffect, useRef, useState } from "react";
import { Navigate, NavLink, Outlet, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { getToken, setToken } from "./api/client.js";
import { LangContext, useT } from "./i18n.js";
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
  "/sharing":   <svg viewBox="0 0 18 18" fill="none" width="15" height="15"><circle cx="14" cy="4" r="2" stroke="currentColor" strokeWidth="1.5"/><circle cx="4" cy="9" r="2" stroke="currentColor" strokeWidth="1.5"/><circle cx="14" cy="14" r="2" stroke="currentColor" strokeWidth="1.5"/><path d="M6 8l6-3M6 10l6 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>,
};

// ── Page transition wrapper ──────────────────────────────────
function PageTransition({ children }) {
  const location = useLocation();
  return (
    <div key={location.pathname} className="animate-in">
      {children}
    </div>
  );
}

// ── App Layout ───────────────────────────────────────────────
function Layout() {
  const { t } = useT();
  const navigate = useNavigate();
  const location = useLocation();

  if (!getToken()) return <Navigate to="/login" replace />;

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
    ["/sharing",   t("sharing")],
  ];

  return (
    <div className="shell">
      <header className="top" role="banner">
        <span className="brand" aria-label="MediThread">MediThread</span>
        <div className="top-actions">
          <LangToggle />
          <button className="ghost" onClick={logout} style={{ fontSize: "var(--font-size-sm)" }}>
            {t("logout")}
          </button>
        </div>
      </header>
      <nav className="tabs" role="navigation" aria-label="Main navigation">
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

  // Setup Lenis smooth scroll
  useEffect(() => {
    // Dynamically import lenis so it works only in browser
    import("lenis").then(({ default: Lenis }) => {
      const lenis = new Lenis({
        duration: 1.2,
        easing: (t) => Math.min(1, 1.001 - Math.pow(2, -10 * t)),
        direction: "vertical",
        gestureDirection: "vertical",
        smooth: true,
        mouseMultiplier: 1,
        smoothTouch: false,
        touchMultiplier: 2,
      });

      // Integrate with GSAP
      import("gsap").then(({ gsap }) => {
        import("gsap/ScrollTrigger").then(({ ScrollTrigger }) => {
          gsap.registerPlugin(ScrollTrigger);
          lenis.on("scroll", ScrollTrigger.update);
          gsap.ticker.add((time) => {
            lenis.raf(time * 1000);
          });
          gsap.ticker.lagSmoothing(0);
        });
      });

      return () => {
        lenis.destroy();
      };
    });
  }, []);

  return (
    <LangContext.Provider value={{ lang, setLang }}>
      {showStartup && <StartupScreen onDone={handleStartupDone} />}
      <Routes>
        <Route path="/login"          element={<Login toggle={<LangToggle />} />} />
        <Route path="/share/:token"   element={<Snapshot toggle={<LangToggle />} />} />
        <Route path="/console/:token" element={<DoctorConsole />} />
        <Route element={<Layout />}>
          <Route index                element={<Home />} />
          <Route path="upload"        element={<Upload />} />
          <Route path="timeline"      element={<Timeline />} />
          <Route path="medicines"     element={<Medicines />} />
          <Route path="reminders"     element={<Reminders />} />
          <Route path="insights"      element={<Insights />} />
          <Route path="triage"        element={<Triage />} />
          <Route path="sharing"       element={<Sharing />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </LangContext.Provider>
  );
}

