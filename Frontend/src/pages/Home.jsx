import { getAlerts, getInsights, getReminders, markReminderTaken } from "../api/client.js";
import { getProfile } from "../App.jsx";
import { AlertCard, Empty, Loading } from "../components/ui.jsx";
import { useT } from "../i18n.js";
import { useApi } from "../useApi.js";

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

  return (
    <>
      <h2>
        {t("hello")}, {profile?.name?.split(" ")[0]}
      </h2>
      {insights.data && <p className="lead">{pick(insights.data, "summary")}</p>}

      <section>
        <h3>{t("todayMeds")}</h3>
        {reminders.loading || reminders.error ? (
          <Loading error={reminders.error} onRetry={reminders.reload} />
        ) : reminders.data.length === 0 ? (
          <Empty>No medicines scheduled. Add a prescription to get reminders.</Empty>
        ) : (
          <div className="list">
            {reminders.data.map((r) => (
              <div key={r.key} className={`card reminder ${r.taken ? "done" : ""}`}>
                <div className="time">{r.time}</div>
                <div className="grow">
                  <strong>{r.name}</strong>
                  <div className="muted small">
                    {[r.dose, r.instructions].filter(Boolean).join(" · ")}
                  </div>
                </div>
                {r.taken ? (
                  <span className="pill good">{t("taken")}</span>
                ) : (
                  <button className="primary small" onClick={() => take(r.key)}>
                    {t("markTaken")}
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </section>

      <section>
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
          <p className="muted">{t("noAlerts")}</p>
        )}
        <p className="muted small">{t("askDoctor")}</p>
      </section>
    </>
  );
}
