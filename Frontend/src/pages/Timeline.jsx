import { useState } from "react";
import { getTimeline } from "../api/client.js";
import { Empty, Loading, TimelineItem } from "../components/ui.jsx";
import { useT } from "../i18n.js";
import { useApi } from "../useApi.js";

const FILTERS = ["all", "prescription", "lab", "consultation"];

export default function Timeline() {
  const { t } = useT();
  const { data, loading, error, reload } = useApi(getTimeline);
  const [filter, setFilter] = useState("all");

  if (loading || error) return <Loading error={error} onRetry={reload} />;
  const docs = filter === "all" ? data : data.filter((d) => d.type === filter || (filter === "consultation" && d.type === "visit"));

  return (
    <>
      <h2>{t("timeline")}</h2>
      <div className="chips">
        {FILTERS.map((f) => (
          <button key={f} className={f === filter ? "chip on" : "chip"} onClick={() => setFilter(f)}>
            {t(f)}
          </button>
        ))}
      </div>
      {docs.length === 0 && (
        <Empty>
          {data.length === 0
            ? "No records yet. Tap Add to upload a prescription or lab report."
            : "No records of this kind yet."}
        </Empty>
      )}
      <ul className="timeline">
        {docs.map((d) => (
          <TimelineItem key={d.id} doc={d} />
        ))}
      </ul>
    </>
  );
}
