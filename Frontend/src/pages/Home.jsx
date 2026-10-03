import { Link } from "react-router-dom";
import { getAlerts, getHealthCheck, getInsights, getMedicines, getReminders, getTimeline, markReminderTaken } from "../api/client.js";
import { EmergencyBanner, doctorsLink } from "../components/health.jsx";
import { getProfile } from "../App.jsx";
import { Loading } from "../components/ui.jsx";
import { useT } from "../i18n.js";
import { useApi } from "../useApi.js";
import { Arrow, Chapter, RV } from "../design/primitives.jsx";
import { deltaList, eventTime, greeting, longDate } from "../design/data.js";
import { CareLoop, ChangeBlock, DocumentStrip, HealthSnapshot, InsightHero, OpenItems } from "../design/home.jsx";
import ThreadExplorer from "../design/ThreadExplorer.jsx";
import { MedicationTimeline } from "../design/medication.jsx";

// A health check risk shown as an open care item (same row design as an alert).
const riskItem = (r) => ({
  id: `risk-${r.key}`, severity: r.level === "watch" ? "medium" : "high", kind: "risk",
  title: r.title, message: r.message, messageMl: r.messageMl,
  cta: r.level !== "watch" && r.specialist
    ? { to: doctorsLink(r.specialist, r.emergency ? { emergency: "1" } : { reason: r.reason }), label: `Find a ${r.specialist.toLowerCase()}` }
    : null,
});

export default function Home() {
  const { t, lang } = useT();
  const ml = lang === "ml";
  const profile = getProfile();
  const reminders = useApi(getReminders);
  const alerts = useApi(getAlerts);
  const insights = useApi(getInsights);
  const health = useApi(getHealthCheck);
  const timeline = useApi(getTimeline);
  const medicines = useApi(getMedicines);

  const take = async (key) => {
    await markReminderTaken(key);
    reminders.setData((rs) => rs.map((r) => (r.key === key ? { ...r, taken: true } : r)));
  };

  const name = profile?.name && profile.name !== "New patient" ? profile.name.split(" ")[0] : null;
  const risks = health.data?.risks ?? [];
  const emergency = risks.find((r) => r.emergency);
  const items = [
    ...(alerts.data?.filter((a) => !a.resolved && a.kind !== "risk") ?? []),
    ...risks.filter((r) => !r.emergency).map(riskItem),
  ];
  const deltas = deltaList(insights.data);
  const docs = timeline.data ?? [];
  const latest = docs[0];
  const doses = { total: reminders.data?.length ?? 0, taken: reminders.data?.filter((r) => r.taken).length ?? 0 };
  const followUp = docs.find((d) => d.followUp);
  const lastTime = latest ? eventTime(latest) : null;

  return (
    <div className="mt-page">
      {emergency && <div className="mt-emergency-wrap"><EmergencyBanner risk={emergency} /></div>}

      {/* OPENING: who, now, and the one thing to read first */}
      <Chapter tone="ground">
        <div className="mt-grid mt-opening-grid">
          <RV className="c-8 mt-opening">
            <div className="mt-label">{greeting(ml)}{name ? `, ${name}` : ""}</div>
            <h1 className="mt-display">{ml ? "നിങ്ങളുടെ ആരോഗ്യ കഥ, " : "Your health story,"}<br /><em>{ml ? "ഒറ്റനോട്ടത്തിൽ." : "at a glance."}</em></h1>
            {latest && (
              <p className="mt-asof">
                <i aria-hidden="true" />{ml ? "അവസാന രേഖ" : "Last record"} · {longDate(latest.date)}{lastTime ? ` · ${lastTime}` : ""}
              </p>
            )}
            <div className="mt-open-actions">
              <Link className="mt-link" to="/insights">{ml ? "ഇന്നത്തെ റീഡിംഗ് ചേർക്കുക" : "Add today's reading"} <Arrow /></Link>
              <Link className="mt-link" to="/upload">{ml ? "രേഖ ചേർക്കുക" : "Add a record"} <Arrow /></Link>
            </div>
          </RV>
          <div className="c-4 mt-snap-col">
            {insights.loading && !insights.data ? <Loading /> : <HealthSnapshot insights={insights.data} timeline={docs} openCount={items.length} doses={doses} />}
          </div>
          <div className="c-8 mt-hero-col">
            <InsightHero review={health.data?.review} deltas={deltas} openCount={items.length} loading={health.loading && !health.data} />
          </div>
        </div>
      </Chapter>

      {/* 01: what changed, and what is still open */}
      <Chapter tone="soft" no="01" kicker={ml ? "മുൻ രേഖകളിൽ നിന്ന്" : "Since your previous records"} title={ml ? "എന്ത് മാറി" : "What changed"}>
        <div className="mt-grid">
          <div className="c-8">
            {insights.loading && !insights.data ? <Loading /> : <ChangeBlock deltas={deltas} review={health.data?.review} />}
          </div>
          <div className="c-4 mt-open-col">
            <div className="mt-label mt-col-label">{ml ? "തുറന്ന പരിചരണ കാര്യങ്ങൾ" : "Open care items"}</div>
            {(alerts.loading || health.loading) && !items.length ? <Loading /> : <OpenItems alerts={items} limit={3} />}
            <p className="mt-fine">{t("askDoctor")}</p>
          </div>
        </div>
      </Chapter>

      {/* 02: the thread itself */}
      <Chapter tone="warm" no="02" kicker={ml ? "നിങ്ങളുടെ രേഖ" : "Your record"} title={ml ? "ആരോഗ്യ ത്രെഡ്" : "Health thread"}
        aside={<span className="mt-meta">{docs.length} {ml ? "രേഖകൾ" : "records"}</span>}>
        {timeline.loading && !timeline.data ? <Loading /> : (
          <ThreadExplorer docs={docs} limit={5} moreHref="/timeline" moreLabel={ml ? "മുഴുവൻ ത്രെഡ് കാണുക" : "See the full thread"} />
        )}
      </Chapter>

      {/* 03: care today */}
      <Chapter tone="ground" no="03" kicker={ml ? "ഇന്ന്" : "Care loop"} title={ml ? "ഇന്നത്തെ പരിചരണം" : "Your care today"}>
        <div className="mt-grid">
          <div className="c-7">
            {reminders.loading && !reminders.data ? <Loading error={reminders.error} onRetry={reminders.reload} /> : (
              <MedicationTimeline reminders={reminders.data || []} medicines={medicines.data || []} onTake={take} />
            )}
          </div>
          <div className="c-5">
            <div className="mt-label mt-col-label">{ml ? "പരിചരണ ചക്രം" : "Your care loop"}</div>
            <CareLoop doses={doses} openCount={items.length} followUp={followUp ? { text: followUp.followUp, date: followUp.date } : null} />
          </div>
        </div>
      </Chapter>

      {/* 04: the documents behind the thread */}
      <Chapter tone="neutral" no="04" kicker={ml ? "തെളിവ്" : "Evidence"} title={ml ? "സമീപകാല രേഖകൾ" : "Recent records"} last
        aside={<Link className="mt-link" to="/timeline">{ml ? "എല്ലാ രേഖകളും" : "All records"} <Arrow /></Link>}>
        {timeline.loading && !timeline.data ? <Loading /> : <DocumentStrip docs={docs} limit={3} />}
      </Chapter>
    </div>
  );
}
