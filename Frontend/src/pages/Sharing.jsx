import { useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import { createShare, getAccessLog, getFamily } from "../api/client.js";
import { Loading } from "../components/ui.jsx";
import { useT } from "../i18n.js";
import { appPath, appUrl } from "../routing.js";
import { useApi } from "../useApi.js";

// ── Family member row ─────────────────────────────────────────
function FamilyRow({ f }) {
  const { t } = useT();
  return (
    <div className="card" style={{ display: "flex", alignItems: "center", gap: "var(--sp-4)", padding: "var(--sp-3) var(--sp-4)" }}>
      <div
        style={{
          width: 36, height: 36, borderRadius: "50%",
          background: "var(--accent-subtle)",
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: "1rem", flexShrink: 0,
        }}
        aria-hidden="true"
      >
        👤
      </div>
      <div className="grow">
        <div className="font-medium">{f.name}</div>
        <div className="text-dim text-xs">{f.relation} · {f.phone}</div>
      </div>
      <div style={{ display: "flex", gap: "var(--sp-1)", flexWrap: "wrap" }}>
        {f.canView && <span className="pill good">{t("canView")}</span>}
        {f.notify  && <span className="pill watch">{t("notify")}</span>}
      </div>
    </div>
  );
}

// ── Access log row ────────────────────────────────────────────
function AccessRow({ a }) {
  return (
    <tr>
      <td style={{ padding: "var(--sp-3) var(--sp-3)", borderBottom: "1px solid var(--border)" }}>
        <div className="font-medium text-sm">{a.who}</div>
        <div className="text-dim text-xs">{a.role}</div>
      </td>
      <td style={{ padding: "var(--sp-3) var(--sp-2)", borderBottom: "1px solid var(--border)", fontSize: "var(--font-size-sm)", color: "var(--text-2)" }}>{a.action}</td>
      <td style={{ padding: "var(--sp-3) var(--sp-2)", borderBottom: "1px solid var(--border)", fontSize: "var(--font-size-xs)", color: "var(--text-3)" }}>{a.via}</td>
      <td style={{ padding: "var(--sp-3) var(--sp-2)", borderBottom: "1px solid var(--border)", fontSize: "var(--font-size-xs)", color: "var(--text-3)" }}>
        {new Date(a.at).toLocaleDateString("en-IN")}
      </td>
    </tr>
  );
}

export default function Sharing() {
  const { t } = useT();
  const family = useApi(getFamily);
  const log    = useApi(getAccessLog);
  const [share, setShare] = useState(null);
  const [hours, setHours] = useState(24);
  const [error, setError] = useState(null);
  const [creating, setCreating] = useState(false);

  const create = async () => {
    setError(null);
    setCreating(true);
    try {
      setShare(await createShare(hours));
    } catch (e) {
      setError(e.message);
    } finally {
      setCreating(false);
    }
  };

  const fullUrl = share ? appUrl(share.url) : "";

  return (
    <>
      <div className="page-header">
        <h2>{t("sharing")}</h2>
      </div>

      <div className="grid-2">
        <div className="stack" style={{ gap: "var(--sp-8)" }}>
          {/* Share with doctor */}
          <div className="section stagger-1" style={{ marginTop: 0 }}>
            <h3>{t("shareTitle")}</h3>
            <div className="card">
              <p className="text-sm text-muted" style={{ marginBottom: "var(--sp-4)" }}>{t("shareHelp")}</p>

              <div className="row" style={{ gap: "var(--sp-3)", flexWrap: "wrap" }}>
                <select
                  id="share-hours-select"
                  value={hours}
                  onChange={(e) => setHours(Number(e.target.value))}
                  style={{ flexShrink: 0 }}
                >
                  <option value={1}>1 hour</option>
                  <option value={24}>24 hours</option>
                  <option value={72}>3 days</option>
                </select>
                <button
                  id="create-share-btn"
                  className="primary"
                  onClick={create}
                  disabled={creating}
                >
                  {creating ? "Creating…" : t("createLink")}
                </button>
              </div>

              {error && <p className="error text-sm mt-3" role="alert">{error}</p>}

              {share && (
                <div className="qr animate-in" style={{ marginTop: "var(--sp-6)" }}>
                  <div style={{ background: "white", padding: "var(--sp-3)", borderRadius: "var(--r-md)", display: "inline-block", boxShadow: "var(--shadow-md)" }}>
                    <QRCodeSVG value={fullUrl} size={180} />
                  </div>
                  <a
                    href={appPath(share.url)}
                    target="_blank"
                    rel="noreferrer"
                    className="qr-url text-xs text-dim"
                    style={{ maxWidth: 300, wordBreak: "break-all", textAlign: "center" }}
                  >
                    {fullUrl}
                  </a>
                  <span className="text-xs text-dim">
                    {t("expires")}: {new Date(share.expiresAt).toLocaleString("en-IN")}
                  </span>
                  <div className="row qr-actions">
                    <a className="btn" href={appPath(share.url)} target="_blank" rel="noreferrer">
                      Preview patient view
                    </a>
                    <a className="btn primary" href={appPath(`/console/${share.token}`)} target="_blank" rel="noreferrer">
                      Open doctor console
                    </a>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Access log */}
          <div className="section stagger-3" style={{ marginTop: 0 }}>
            <h3>{t("accessLog")}</h3>
            {log.loading || log.error ? (
              <Loading error={log.error} onRetry={log.reload} />
            ) : (
              <div className="card" style={{ padding: 0, overflow: "hidden" }}>
                <table style={{ width: "100%", borderCollapse: "collapse" }}>
                  <tbody>
                    {log.data.map((a) => <AccessRow key={a.id} a={a} />)}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>

        <div className="stack" style={{ gap: "var(--sp-8)" }}>
          {/* Family */}
          <div className="section stagger-2" style={{ marginTop: 0 }}>
            <h3>{t("family")}</h3>
            {family.loading || family.error ? (
              <Loading error={family.error} onRetry={family.reload} />
            ) : (
              <div className="list">
                {family.data.map((f) => <FamilyRow key={f.id} f={f} />)}
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
