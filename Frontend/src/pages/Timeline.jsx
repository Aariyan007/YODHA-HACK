import { useState } from "react";
import { getTimeline } from "../api/client.js";
import { Loading, TimelineItem } from "../components/ui.jsx";
import { useT } from "../i18n.js";
import { useApi } from "../useApi.js";

const FILTERS = ["all", "prescription", "lab", "consultation"];

export default function Timeline() {
  const { t } = useT();
  const { data, loading, error } = useApi(getTimeline);
  const [filter, setFilter] = useState("all");

  if (loading) return <Loading error={error} />;
  const docs = filter === "all" ? data : data.filter((d) => d.type === filter);

  return (
    <>
      <h2>{t("timeline")}</h2>
      <div className="chips">
        {FILTERS.map((f) => (
          <button key={f} className={f === filter ? "chip on" : "chip"} onClick={() => setFilter(f)}>
            {f === "all" ? "All" : t(f)}
          </button>
        ))}
      </div>
      <ul className="timeline">
        {docs.map((d) => (
          <TimelineItem key={d.id} doc={d} />
        ))}
      </ul>
    </>
  );
}
