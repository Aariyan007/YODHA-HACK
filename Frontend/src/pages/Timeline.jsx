import { useState } from "react";
import { useLocation } from "react-router-dom";
import { getTimeline } from "../api/client.js";
import { Empty, Loading } from "../components/ui.jsx";
import { useT } from "../i18n.js";
import { useApi } from "../useApi.js";
import { Chapter, RV } from "../design/primitives.jsx";
import { DocumentStrip } from "../design/home.jsx";
import ThreadExplorer from "../design/ThreadExplorer.jsx";

const FILTERS = ["all", "prescription", "lab", "consultation", "vitals"];
const matches = (d, f) => f === "all" || d.type === f || (f === "consultation" && d.type === "visit");

export default function Timeline() {
  const { t, lang } = useT();
  const ml = lang === "ml";
  const { data, loading, error, reload } = useApi(getTimeline);
  const [filter, setFilter] = useState("all");
  const { hash } = useLocation();
  const initialId = hash ? hash.slice(1) : undefined; // arrives from a document preview ("View evidence")

  const docs = data ?? [];
  const shown = docs.filter((d) => matches(d, filter));

  return (
    <div className="mt-page">
      <Chapter tone="ground">
        <RV className="mt-opening">
          <div className="mt-label">{t("timeline")}</div>
          <h1 className="mt-display">{ml ? "നിങ്ങളുടെ ആരോഗ്യ " : "Your health "}<em>{ml ? "ത്രെഡ്" : "thread"}</em>.</h1>
          <p className="mt-lede">
            {data ? (ml ? `${docs.length} രേഖകൾ ഒരു കഥയായി.` : `${docs.length} ${docs.length === 1 ? "record" : "records"} woven into one story, newest first. Hover or tap any point to see the record behind it.`)
              : (ml ? "നിങ്ങളുടെ രേഖകൾ ബന്ധിപ്പിക്കുന്നു." : "Your records, connected.")}
          </p>
        </RV>
        <div className="mt-seg" role="group" aria-label="Filter records">
          {FILTERS.map((f) => (
            <button key={f} type="button" className={f === filter ? "on" : ""} aria-pressed={f === filter} onClick={() => setFilter(f)}>
              {t(f)}<span>{docs.filter((d) => matches(d, f)).length}</span>
            </button>
          ))}
        </div>
      </Chapter>

      <Chapter tone="warm" no="01" kicker={ml ? "കഥ" : "The story"} title={ml ? "എല്ലാം ഒറ്റ ത്രെഡിൽ" : "Everything on one thread"}>
        {loading ? <Loading /> : error ? <Loading error={error} onRetry={reload} /> : shown.length === 0 ? (
          <Empty>{docs.length === 0 ? "No records yet. Tap Add to upload a prescription or lab report." : "No records of this kind yet."}</Empty>
        ) : (
          <ThreadExplorer docs={shown} initialId={initialId} />
        )}
      </Chapter>

      {docs.length > 0 && (
        <Chapter tone="neutral" no="02" kicker={ml ? "തെളിവ്" : "Evidence"} title={ml ? "രേഖകൾ" : "Documents"} last>
          <DocumentStrip docs={docs} limit={7} />
        </Chapter>
      )}
    </div>
  );
}
