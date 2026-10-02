import { useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import { createInvite, createShare, getAccessLog, getFamily, listMyDoctors, removeDoctor } from "../api/client.js";
import { Empty, Loading } from "../components/ui.jsx";
import { useT } from "../i18n.js";
import { appPath, appUrl } from "../routing.js";
import { useApi } from "../useApi.js";

// ── Invite your doctor (Phase 8) ──────────────────────────────
function InviteDoctor() {
  const { lang } = useT();
  const ml = lang === "ml";
  const doctors = useApi(listMyDoctors);
  const [invite, setInvite] = useState(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState(null); // { kind, text }

  const make = async () => {
    setBusy(true);
    setNote(null);
    try {
      setInvite(await createInvite());
    } catch (e) {
      setNote({ kind: "error", text: e.message });
    } finally {
      setBusy(false);
    }
  };
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(invite.code);
      setNote({ kind: "ok", text: ml ? "പകർത്തി." : "Copied." });
    } catch {
      setNote({ kind: "error", text: ml ? "പകർത്താനായില്ല. കോഡ് തൊട്ട് തിരഞ്ഞെടുക്കുക." : "Could not copy. Tap the code to select it." });
    }
  };
  const remove = async (d) => {
    setNote(null);
    try {
      await removeDoctor(d.linkId);
      await doctors.reload();
    } catch (e) {
      setNote({ kind: "error", text: e.message });
    }
  };

  return (
    <div className="section stagger-1" style={{ marginTop: 0 }}>
      <h3>{ml ? "നിങ്ങളുടെ ഡോക്ടറെ ക്ഷണിക്കുക" : "Invite your doctor"}</h3>
      <div className="card">
        <p className="text-sm text-muted" style={{ marginBottom: "var(--sp-4)" }}>
          {ml
            ? "ഡോക്ടർ അവരുടെ MediThread ഡോക്ടർ അക്കൗണ്ടിൽ ഈ കോഡ് നൽകണം. കോഡ് ഒരു തവണ മാത്രം, 24 മണിക്കൂർ."
            : "Give this code to your doctor. They enter it in their MediThread doctor account to see your record. It works once and expires after 24 hours."}
        </p>
        <button className="primary" onClick={make} disabled={busy}>
          {busy ? "…" : invite ? (ml ? "പുതിയ കോഡ്" : "New code") : ml ? "കോഡ് ഉണ്ടാക്കുക" : "Make a code"}
        </button>
        {invite && (
          <div style={{ marginTop: "var(--sp-4)", display: "grid", gap: "var(--sp-3)" }}>
            <div className="invite-code" aria-label={`Invite code ${invite.code}`}>{invite.code}</div>
            <div className="row between">
              <span className="text-dim text-xs">{ml ? "കാലാവധി" : "Expires"}: {new Date(invite.expiresAt).toLocaleString("en-IN")}</span>
              <button onClick={copy}>{ml ? "പകർത്തുക" : "Copy"}</button>
            </div>
          </div>
        )}
        {note && (
          <p className={note.kind === "error" ? "error text-sm" : "text-sm"} role={note.kind === "error" ? "alert" : "status"}>{note.text}</p>
        )}

        <h4 style={{ marginTop: "var(--sp-5)" }}>{ml ? "നിങ്ങളുടെ രേഖ കാണാൻ കഴിയുന്നവർ" : "Doctors who can see your record"}</h4>
        {doctors.loading || doctors.error ? (
          <Loading error={doctors.error} onRetry={doctors.reload} />
        ) : doctors.data.length === 0 ? (
          <Empty>{ml ? "ഇതുവരെ ആരുമില്ല." : "No doctors yet."}</Empty>
        ) : (
          <div className="list">
            {doctors.data.map((d) => (
              <div key={d.linkId} className="row between">
                <div style={{ minWidth: 0 }}>
                  <strong>{d.name}</strong>
                  <div className="text-dim text-xs">{[d.specialty, d.hospital].filter(Boolean).join(" · ")}</div>
                </div>
                <button onClick={() => remove(d)}>{ml ? "നീക്കം ചെയ്യുക" : "Remove access"}</button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

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
          <InviteDoctor />
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
