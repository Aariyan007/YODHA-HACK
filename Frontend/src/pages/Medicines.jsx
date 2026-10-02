import { getMedicines, getReminders, markReminderTaken } from "../api/client.js";
import { Empty, Loading } from "../components/ui.jsx";
import { useT } from "../i18n.js";
import { useApi } from "../useApi.js";
import { Chapter, RV } from "../design/primitives.jsx";
import { MedicationList, MedicationTimeline } from "../design/medication.jsx";

export default function Medicines() {
  const { t, lang } = useT();
  const ml = lang === "ml";
  const meds = useApi(getMedicines);
  const reminders = useApi(getReminders);

  const take = async (key) => {
    await markReminderTaken(key);
    reminders.setData((rs) => rs.map((r) => (r.key === key ? { ...r, taken: true } : r)));
  };

  return (
    <div className="mt-page">
      <Chapter tone="ground">
        <RV className="mt-opening">
          <div className="mt-label">{t("medicines")}</div>
          <h1 className="mt-display">{ml ? "നിങ്ങളുടെ " : "Your "}<em>{ml ? "മരുന്നുകൾ" : "medicines"}</em>{ml ? "" : ", in order."}</h1>
          <p className="mt-lede">{ml ? "ഇന്ന് എപ്പോൾ എന്ത് കഴിക്കണം, കുറിപ്പടിയിൽ എഴുതിയതുപോലെ." : "What to take today and when, exactly as the prescription says. Nothing is guessed."}</p>
        </RV>
        <div className="mt-gap-top">
          {reminders.loading && !reminders.data ? <Loading error={reminders.error} onRetry={reminders.reload} /> : (
            <MedicationTimeline reminders={reminders.data || []} medicines={meds.data || []} onTake={take} />
          )}
        </div>
      </Chapter>

      <Chapter tone="warm" no="01" kicker={ml ? "സജീവം" : "Active"} title={ml ? "എല്ലാ മരുന്നുകളും" : "All active medicines"} last
        aside={meds.data?.length ? <span className="mt-meta">{meds.data.length} {ml ? "സജീവം" : "active"}</span> : null}>
        {meds.loading && !meds.data ? <Loading error={meds.error} onRetry={meds.reload} /> : (meds.data || []).length === 0 ? (
          <Empty>No medicines yet. They appear here when you add a prescription.</Empty>
        ) : <MedicationList medicines={meds.data} />}
      </Chapter>
    </div>
  );
}
