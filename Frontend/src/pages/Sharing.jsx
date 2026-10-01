import { useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import { createShare, getAccessLog, getFamily } from "../api/client.js";
import { Loading } from "../components/ui.jsx";
import { useT } from "../i18n.js";
import { useApi } from "../useApi.js";

export default function Sharing() {
  const { t } = useT();
  const family = useApi(getFamily);
  const log = useApi(getAccessLog);
  const [share, setShare] = useState(null);
  const [hours, setHours] = useState(24);
  const [error, setError] = useState(null);

  const create = async () => {
    setError(null);
    try {
      setShare(await createShare(hours));
    } catch (e) {
      setError(e.message);
    }
  };

  const fullUrl = share ? `${window.location.origin}${share.url}` : "";

  return (
    <>
      <h2>{t("sharing")}</h2>

      <section className="card">
        <h3>{t("shareTitle")}</h3>
        <p className="muted small">{t("shareHelp")}</p>
        <div className="row">
          <select value={hours} onChange={(e) => setHours(Number(e.target.value))}>
            <option value={1}>1 hour</option>
            <option value={24}>24 hours</option>
            <option value={72}>3 days</option>
          </select>
          <button className="primary" onClick={create}>
            {t("createLink")}
          </button>
        </div>
        {error && <p className="error">{error}</p>}
        {share && (
          <div className="qr">
            <QRCodeSVG value={fullUrl} size={180} />
            <a href={share.url} target="_blank" rel="noreferrer" className="small">
              {fullUrl}
            </a>
            <span className="muted small">
              {t("expires")}: {new Date(share.expiresAt).toLocaleString("en-IN")}
            </span>
          </div>
        )}
      </section>

      <section>
        <h3>{t("family")}</h3>
        {family.loading ? (
          <Loading error={family.error} />
        ) : (
          <div className="list">
            {family.data.map((f) => (
              <div key={f.id} className="card row between">
                <span>
                  <strong>{f.name}</strong> <span className="muted small">({f.relation})</span>
                  <div className="muted small">{f.phone}</div>
                </span>
                <span className="small">
                  {f.canView && <span className="pill good">{t("canView")}</span>}{" "}
                  {f.notify && <span className="pill watch">{t("notify")}</span>}
                </span>
              </div>
            ))}
          </div>
        )}
      </section>

      <section>
        <h3>{t("accessLog")}</h3>
        {log.loading ? (
          <Loading error={log.error} />
        ) : (
          <div className="card">
            <table className="labs">
              <tbody>
                {log.data.map((a) => (
                  <tr key={a.id}>
                    <td>
                      <strong>{a.who}</strong>
                      <div className="muted small">{a.role}</div>
                    </td>
                    <td>{a.action}</td>
                    <td className="muted small">{a.via}</td>
                    <td className="muted small">{new Date(a.at).toLocaleDateString("en-IN")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}
