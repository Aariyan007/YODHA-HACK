import { Link, useParams } from "react-router-dom";
import { getShareSnapshot } from "../api/client.js";
import { Loading } from "../components/ui.jsx";
import { HistoryPanel } from "../components/console/HistoryPanel.jsx";
import { useT } from "../i18n.js";
import { useApi } from "../useApi.js";

// The read-only record a doctor opens from the patient's QR link. Same layout as the consultation console's history,
// with a link to the console at the end instead of a recorder.
export default function Snapshot({ toggle }) {
  const { t } = useT();
  const { token } = useParams();
  const { data, loading, error } = useApi(() => getShareSnapshot(token), [token]);

  const errMsg = error === "Share link expired"
    ? "This share link has expired. Ask the patient for a new QR code."
    : error === "Share link not found"
      ? "This share link is not valid. Ask the patient for a new QR code."
      : error;

  return (
    <div className="shell mt-snapshot">
      <header className="top" role="banner">
        <span className="brand" aria-label="MediThread patient snapshot">
          MediThread <span className="pill accent" style={{ marginLeft: 8 }}>{t("snapshotTitle")}</span>
        </span>
        <div className="top-actions">
          {data && <span className="mt-snap-ro" title="Read-only. Access is logged.">Read-only</span>}
          {toggle}
        </div>
      </header>
      <main className="page-shell" role="main">
        {loading || error ? (
          <Loading error={errMsg} />
        ) : (
          <HistoryPanel snapshot={data} consultHref={`/console/${token}`} />
        )}
        {error && <p className="mt-small" style={{ textAlign: "center" }}><Link to="/">Go to MediThread</Link></p>}
      </main>
    </div>
  );
}
