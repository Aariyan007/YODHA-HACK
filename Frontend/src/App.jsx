import { useState } from "react";
import { Navigate, NavLink, Outlet, Route, Routes, useNavigate } from "react-router-dom";
import { getToken, setToken } from "./api/client.js";
import { LangContext, useT } from "./i18n.js";
import Login from "./pages/Login.jsx";
import Home from "./pages/Home.jsx";
import Timeline from "./pages/Timeline.jsx";
import Medicines from "./pages/Medicines.jsx";
import Insights from "./pages/Insights.jsx";
import Sharing from "./pages/Sharing.jsx";
import Snapshot from "./pages/Snapshot.jsx";

const PROFILE_KEY = "medithread_profile";
const LANG_KEY = "medithread_lang";

export function getProfile() {
  try {
    return JSON.parse(localStorage.getItem(PROFILE_KEY));
  } catch {
    return null;
  }
}

export function saveSession({ token, profile }) {
  setToken(token);
  localStorage.setItem(PROFILE_KEY, JSON.stringify(profile));
}

function LangToggle() {
  const { lang, setLang } = useT();
  return (
    <button className="lang" onClick={() => setLang(lang === "en" ? "ml" : "en")}>
      {lang === "en" ? "മലയാളം" : "English"}
    </button>
  );
}

function Layout() {
  const { t } = useT();
  const navigate = useNavigate();
  if (!getToken()) return <Navigate to="/login" replace />;
  const logout = () => {
    setToken(null);
    localStorage.removeItem(PROFILE_KEY);
    navigate("/login");
  };
  const tabs = [
    ["/", t("home")],
    ["/timeline", t("timeline")],
    ["/medicines", t("medicines")],
    ["/insights", t("insights")],
    ["/sharing", t("sharing")],
  ];
  return (
    <div className="shell">
      <header className="top">
        <span className="brand">MediThread</span>
        <div className="top-actions">
          <LangToggle />
          <button className="link" onClick={logout}>
            {t("logout")}
          </button>
        </div>
      </header>
      <nav className="tabs">
        {tabs.map(([to, label]) => (
          <NavLink key={to} to={to} end>
            {label}
          </NavLink>
        ))}
      </nav>
      <main>
        <Outlet />
      </main>
    </div>
  );
}

export default function App() {
  const [lang, setLangState] = useState(() => localStorage.getItem(LANG_KEY) || "en");
  const setLang = (l) => {
    localStorage.setItem(LANG_KEY, l);
    setLangState(l);
  };
  return (
    <LangContext.Provider value={{ lang, setLang }}>
      <Routes>
        <Route path="/login" element={<Login toggle={<LangToggle />} />} />
        <Route path="/share/:token" element={<Snapshot toggle={<LangToggle />} />} />
        <Route element={<Layout />}>
          <Route index element={<Home />} />
          <Route path="timeline" element={<Timeline />} />
          <Route path="medicines" element={<Medicines />} />
          <Route path="insights" element={<Insights />} />
          <Route path="sharing" element={<Sharing />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </LangContext.Provider>
  );
}
