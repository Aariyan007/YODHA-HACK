import { useEffect, useRef, useState } from "react";
import { gsap } from "gsap";
import { Link } from "react-router-dom";
import { getAlerts, getHealthCheck, getInsights, getReminders, markReminderTaken } from "../api/client.js";
import { useCountUp } from "../anim.js";
import { HealthCheckPanel, VitalsForm } from "../components/health.jsx";
import { getProfile } from "../App.jsx";
import { AlertCard, Empty, Loading } from "../components/ui.jsx";
import { useT } from "../i18n.js";
import { useApi } from "../useApi.js";

// ── Greeting ─────────────────────────────────────────────────
function Greeting({ name, summary }) {
  const ref = useRef(null);
  useEffect(() => {
    if (ref.current) {
      gsap.from(ref.current.children, {
        y: 18, opacity: 0, stagger: 0.08, duration: 0.45, ease: "power2.out",
        clearProps: "all",
      });
    }
  }, []);
  return (
    <div ref={ref} className="home-greeting">
      <h2>
        {name ? `Hello, ${name}` : "Hello"}
      </h2>
      {summary && (
        <p className="lead" style={{ marginTop: "var(--sp-3)" }}>{summary}</p>
      )}
    </div>
  );
}

// ── Medicine reminder card ────────────────────────────────────
function ReminderCard({ r, onTake }) {
  const { t } = useT();
  const ref = useRef(null);

  const handleTake = async () => {
    if (!ref.current) return onTake(r.key);
    gsap.to(ref.current, {
      scale: 0.97, opacity: 0.5, duration: 0.15, ease: "power1.in",
      onComplete: () => {
        onTake(r.key);
        gsap.to(ref.current, { scale: 1, opacity: 1, duration: 0.2, ease: "power1.out" });
      },
    });
  };

  return (
    <div
      ref={ref}
      className={`reminder-card${r.taken ? " taken" : ""}`}
      role="listitem"
    >
      <div className="reminder-time">{r.time}</div>
      <div className="grow">
        <div className="reminder-name">{r.name}</div>
        {(r.dose || r.instructions) && (
          <div className="reminder-detail">
            {[r.dose, r.instructions].filter(Boolean).join(" · ")}
          </div>
        )}
      </div>
      {r.taken ? (
        <span className="pill good" role="status">{t("taken")}</span>
      ) : (
        <button className="primary small" onClick={handleTake}>
          {t("markTaken")}
        </button>
      )}
    </div>
  );
}

// ── Today's progress bar ──────────────────────────────────────
function DoseProgress({ total, taken }) {
  const pct = total ? Math.round((taken / total) * 100) : 0;
  const ref = useRef(null);
  useEffect(() => {
    if (ref.current) gsap.fromTo(ref.current, { width: "0%" }, { width: `${pct}%`, duration: 0.8, ease: "power3.out" });
  }, [pct]);
  if (!total) return null;
  return (
    <div className="dose-progress" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
      <div ref={ref} className="dose-progress-bar" style={{ width: `${pct}%` }} />
    </div>
  );
}

// ── Home page ─────────────────────────────────────────────────
export default function Home() {
  const { t, pick, lang } = useT();
  const profile = getProfile();
  const reminders = useApi(getReminders);
  const alerts = useApi(getAlerts);
  const insights = useApi(getInsights);
  const health = useApi(getHealthCheck);
  const [showVitals, setShowVitals] = useState(false);
  const ml = lang === "ml";

  const take = async (key) => {
    await markReminderTaken(key);
    reminders.setData((rs) => rs.map((r) => (r.key === key ? { ...r, taken: true } : r)));
  };

  // Risk alerts are shown in the Health check panel, so the Warnings list skips them.
  const open = alerts.data?.filter((a) => !a.resolved && a.kind !== "risk") ?? [];
  const nRisks = health.data?.risks?.length ?? 0;
  const riskCount = useCountUp(nRisks);
  const totalDoses  = reminders.data?.length ?? 0;
  const takenDoses  = reminders.data?.filter((r) => r.taken).length ?? 0;

  return (
    <>
      <Greeting
        name={profile?.name && profile.name !== "New patient" ? profile.name.split(" ")[0] : null}
        summary={insights.data ? pick(insights.data, "summary") : null}
      />

      <section className="section health-section">
        <div className="row between mb-2" style={{ alignItems: "center", flexWrap: "wrap", gap: "var(--sp-2)" }}>
          <h3 style={{ margin: 0 }}>
            {t("healthCheck")}
            {health.data && <span className={`count-badge${nRisks ? " warn" : ""}`}>{riskCount}</span>}
          </h3>
          <div className="row" style={{ gap: "var(--sp-2)" }}>
            <button className="ghost small" onClick={() => setShowVitals((x) => !x)} aria-expanded={showVitals}>
              {showVitals ? (ml ? "അടയ്ക്കുക" : "Close") : (ml ? "+ റീഡിംഗ് ചേർക്കുക" : "+ Log a reading")}
            </button>
            <Link className="btn-link" to="/doctors">{ml ? "ഡോക്ടറെ കണ്ടെത്തുക" : "Find a doctor"} →</Link>
          </div>
        </div>
        {showVitals && (
          <div className="animate-in-fast mb-4">
            <VitalsForm onSaved={() => { health.reload(); alerts.reload(); insights.reload(); }} />
          </div>
        )}
        {health.loading || health.error ? (
          <Loading error={health.error} onRetry={health.reload} />
        ) : (
          <HealthCheckPanel data={health.data} compact />
        )}
      </section>

      <div className="grid-2">
        {/* Main Column: Medicines */}
        <div className="stack" style={{ gap: "var(--sp-8)" }}>
          {/* Today's doses progress */}
          {totalDoses > 0 && (
            <div className="section stagger-1" style={{ marginTop: 0 }}>
              <div className="row between mb-2" style={{ alignItems: "center" }}>
                <h3>{t("todayMeds")}</h3>
                <span className="text-dim text-xs">
                  {takenDoses}/{totalDoses} done
                </span>
              </div>
              <DoseProgress total={totalDoses} taken={takenDoses} />
            </div>
          )}

          {/* Medicine cards */}
          <div className="section stagger-2" style={{ marginTop: 0 }}>
            {!totalDoses && <h3>{t("todayMeds")}</h3>}
            {reminders.loading || reminders.error ? (
              <Loading error={reminders.error} onRetry={reminders.reload} />
            ) : reminders.data.length === 0 ? (
              <Empty icon="💊">
                No medicines scheduled. Add a prescription to get reminders.
              </Empty>
            ) : (
              <div className="list" role="list">
                {reminders.data.map((r) => (
                  <ReminderCard key={r.key} r={r} onTake={take} />
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Sidebar Column: Alerts */}
        <div className="stack" style={{ gap: "var(--sp-8)" }}>
          <div className="section stagger-3" style={{ marginTop: 0 }}>
            <h3>{t("alerts")}</h3>
            {alerts.loading || alerts.error ? (
              <Loading error={alerts.error} onRetry={alerts.reload} />
            ) : open.length ? (
              <div className="list">
                {open.map((a) => (
                  <AlertCard key={a.id} alert={a} />
                ))}
              </div>
            ) : (
              <div className="card" style={{ padding: "var(--sp-4)" }}>
                <p className="text-muted text-sm" style={{ display: "flex", alignItems: "center", gap: "var(--sp-2)" }}>
                  <span style={{ fontSize: "1rem" }}>🟢</span>
                  {t("noAlerts")}
                </p>
              </div>
            )}
            <p className="text-dim text-xs mt-3">{t("askDoctor")}</p>
          </div>
        </div>
      </div>
    </>
  );
}
