import { useState } from "react";
import { Link } from "react-router-dom";
import { getAlerts, getHealthCheck, getInsights, getReminders, getTimeline, markReminderTaken } from "../api/client.js";
import { EmergencyBanner, RiskCard, VitalsForm } from "../components/health.jsx";
import { PatientHeader, NowRail, WhatChanged, AIInsight, Attention, MedTimeline, EdSection } from "../components/editorial.jsx";
import HealthThread from "../components/thread.jsx";
import { Loading } from "../components/ui.jsx";
import { getProfile } from "../App.jsx";
import { useT } from "../i18n.js";
import { useApi } from "../useApi.js";

const toStatus = (level) =>
  level === "emergency" || level === "high" ? "alert" : level === "watch" ? "watch" : "good";

export default function Home() {
  const { t, lang } = useT();
  const ml = lang === "ml";
  const profile = getProfile();
  const reminders = useApi(getReminders);
  const alerts = useApi(getAlerts);
  const insights = useApi(getInsights);
  const health = useApi(getHealthCheck);
  const timeline = useApi(getTimeline);
  const [showVitals, setShowVitals] = useState(false);

  const take = async (key) => {
    await markReminderTaken(key);
    reminders.setData((rs) => rs.map((r) => (r.key === key ? { ...r, taken: true } : r)));
  };

  const open = alerts.data?.filter((a) => !a.resolved && a.kind !== "risk") ?? [];
  const risks = health.data?.risks ?? [];
  const emergency = risks.find((r) => r.emergency);
  const otherRisks = risks.filter((r) => r !== emergency);
  const status = toStatus(risks[0]?.level);
  const name = profile?.name && profile.name !== "New patient" ? profile.name.split(" ")[0] : null;
  const recordCount = timeline.data?.length ?? 0;

  return (
    <>
      <PatientHeader
        name={name}
        subtitle={ml ? "നിങ്ങളുടെ ആരോഗ്യ കഥ ഒറ്റനോട്ടത്തിൽ." : "Your health story, at a glance."}
        updatedAt={health.data ? Date.now() : null}
        status={health.data ? status : null}
      />

      {emergency && <div style={{ marginTop: "var(--sp-6)" }}><EmergencyBanner risk={emergency} /></div>}

      {(insights.data || reminders.data) && (
        <NowRail insights={insights.data} reminders={reminders.data} warnings={open.length} />
      )}

      {/* WHAT CHANGED */}
      {insights.data?.series?.length > 0 && (
        <EdSection kicker={ml ? "മുൻ രേഖകളിൽ നിന്ന്" : "Since your previous records"} title={ml ? "എന്ത് മാറി" : "What changed"}>
          <WhatChanged insights={insights.data} review={health.data?.review} />
        </EdSection>
      )}

      {/* AI HEALTH REVIEW */}
      {(health.loading || health.error) ? (
        <EdSection kicker="AI" title={t("healthCheck")}><Loading error={health.error} onRetry={health.reload} /></EdSection>
      ) : (health.data?.review || otherRisks.length > 0) && (
        <EdSection
          kicker={ml ? "വ്യാഖ്യാനം" : "Interpretation"}
          title={ml ? "ആരോഗ്യ അവലോകനം" : "Health review"}
          action={<Link className="ed-link" to="/doctors">{ml ? "ഡോക്ടറെ കണ്ടെത്തുക" : "Find a doctor"} →</Link>}
        >
          <AIInsight review={health.data?.review} recordCount={recordCount} />
          {otherRisks.length > 0 && (
            <div className="stack" style={{ gap: "var(--sp-4)", marginTop: "var(--sp-8)" }}>
              {otherRisks.slice(0, 3).map((r) => <RiskCard key={r.key} risk={r} />)}
            </div>
          )}
        </EdSection>
      )}

      {/* HEALTH THREAD */}
      {timeline.data?.length > 0 && (
        <EdSection
          kicker={ml ? "നിങ്ങളുടെ കഥ" : "Your record"}
          title={ml ? "ആരോഗ്യ ത്രെഡ്" : "Health thread"}
          meta={`${recordCount} ${ml ? "രേഖകൾ" : "records"}`}
          action={<Link className="ed-link" to="/timeline">{ml ? "എല്ലാം കാണുക" : "See the full thread"} →</Link>}
        >
          <HealthThread docs={timeline.data} limit={5} />
        </EdSection>
      )}

      {/* NEEDS ATTENTION */}
      <EdSection kicker={ml ? "ശ്രദ്ധിക്കുക" : "Flagged for you"} title={ml ? "ശ്രദ്ധ വേണ്ടത്" : "What needs attention"}>
        {alerts.loading || alerts.error
          ? <Loading error={alerts.error} onRetry={alerts.reload} />
          : <Attention alerts={open} />}
        <p className="ai-disclaim" style={{ marginTop: "var(--sp-4)" }}>{t("askDoctor")}</p>
      </EdSection>

      {/* TODAY'S MEDICINES */}
      <EdSection
        kicker={ml ? "ഇന്ന്" : "Care loop"}
        title={t("todayMeds")}
        action={
          <button className="ed-link" onClick={() => setShowVitals((x) => !x)} aria-expanded={showVitals}>
            {showVitals ? (ml ? "അടയ്ക്കുക" : "Close") : (ml ? "+ റീഡിംഗ്" : "+ Log a reading")}
          </button>
        }
      >
        {showVitals && (
          <div className="animate-in-fast" style={{ marginBottom: "var(--sp-6)" }}>
            <VitalsForm onSaved={() => { health.reload(); alerts.reload(); insights.reload(); }} />
          </div>
        )}
        {reminders.loading || reminders.error ? (
          <Loading error={reminders.error} onRetry={reminders.reload} />
        ) : reminders.data.length === 0 ? (
          <p className="ed-meta">{ml ? "മരുന്നുകളൊന്നും ഷെഡ്യൂൾ ചെയ്തിട്ടില്ല. ഓർമ്മപ്പെടുത്തലുകൾക്കായി ഒരു പ്രിസ്ക്രിപ്ഷൻ ചേർക്കുക." : "No medicines scheduled. Add a prescription to get reminders."}</p>
        ) : (
          <MedTimeline reminders={reminders.data} onTake={take} />
        )}
      </EdSection>
    </>
  );
}
