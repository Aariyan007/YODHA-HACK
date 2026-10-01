import { useEffect, useRef } from "react";
import { gsap } from "gsap";
import { getAlerts, getInsights, getReminders, markReminderTaken } from "../api/client.js";
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
  if (!total) return null;
  const pct = Math.round((taken / total) * 100);
  return (
    <div className="dose-progress" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
      <div className="dose-progress-bar" style={{ width: `${pct}%` }} />
    </div>
  );
}

// ── Home page ─────────────────────────────────────────────────
export default function Home() {
  const { t, pick } = useT();
  const profile = getProfile();
  const reminders = useApi(getReminders);
  const alerts = useApi(getAlerts);
  const insights = useApi(getInsights);

  const take = async (key) => {
    await markReminderTaken(key);
    reminders.setData((rs) => rs.map((r) => (r.key === key ? { ...r, taken: true } : r)));
  };

  const open = alerts.data?.filter((a) => !a.resolved) ?? [];
  const totalDoses  = reminders.data?.length ?? 0;
  const takenDoses  = reminders.data?.filter((r) => r.taken).length ?? 0;

  return (
    <>
      <Greeting
        name={profile?.name?.split(" ")[0]}
        summary={insights.data ? pick(insights.data, "summary") : null}
      />

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
