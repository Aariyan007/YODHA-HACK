import { useState } from "react";
import { createInvite, createShare, getAccessLog, getFamily, listMyDoctors, removeDoctor } from "../api/client.js";
import { Empty, Loading } from "../components/ui.jsx";
import { useT } from "../i18n.js";
import { appPath, appUrl } from "../routing.js";
import { useApi } from "../useApi.js";
import { Chapter, RV } from "../design/primitives.jsx";
import { AccessRow, ActivityItem, SharePanel } from "../design/share.jsx";

// ── Invite your doctor: a one-time code for a doctor's MediThread account ───
function InviteCode({ ml }) {
  const [invite, setInvite] = useState(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState(null);
  const make = async () => {
    setBusy(true); setNote(null);
    try { setInvite(await createInvite()); } catch (e) { setNote({ kind: "error", text: e.message }); } finally { setBusy(false); }
  };
  const copy = async () => {
    try { await navigator.clipboard.writeText(invite.code); setNote({ kind: "ok", text: ml ? "പകർത്തി." : "Copied." }); }
    catch { setNote({ kind: "error", text: ml ? "പകർത്താനായില്ല." : "Could not copy. Tap the code to select it." }); }
  };
  return (
    <div className="mt-invite">
      <div className="mt-label">{ml ? "അക്കൗണ്ട് ക്ഷണം" : "Invite by code"}</div>
      <h3 className="mt-share-title">{ml ? "ഡോക്ടറുടെ അക്കൗണ്ടിലേക്ക്" : "For a doctor's account"}</h3>
      <p className="mt-share-help">
        {ml ? "ഡോക്ടർ അവരുടെ MediThread ഡോക്ടർ അക്കൗണ്ടിൽ ഈ കോഡ് നൽകണം. കോഡ് ഒരു തവണ മാത്രം, 24 മണിക്കൂർ."
            : "They enter this code in their MediThread doctor account to see your record. It works once and expires after 24 hours."}
      </p>
      <button type="button" className="mt-btn secondary" onClick={make} disabled={busy}>
        {busy ? "…" : invite ? (ml ? "പുതിയ കോഡ്" : "New code") : ml ? "കോഡ് ഉണ്ടാക്കുക" : "Make a code"}
      </button>
      {invite && (
        <div className="mt-invite-code">
          <div className="invite-code" aria-label={`Invite code ${invite.code}`}>{invite.code}</div>
          <div className="row between">
            <span className="mt-small">{ml ? "കാലാവധി" : "Expires"}: {new Date(invite.expiresAt).toLocaleString("en-IN")}</span>
            <button type="button" className="mt-btn secondary sm" onClick={copy}>{ml ? "പകർത്തുക" : "Copy"}</button>
          </div>
        </div>
      )}
      {note && <p className={note.kind === "error" ? "mt-error" : "mt-small"} role={note.kind === "error" ? "alert" : "status"}>{note.text}</p>}
    </div>
  );
}

export default function Sharing() {
  const { t, lang } = useT();
  const ml = lang === "ml";
  const family = useApi(getFamily);
  const log = useApi(getAccessLog);
  const doctors = useApi(listMyDoctors);
  const [share, setShare] = useState(null);
  const [hours, setHours] = useState(24);
  const [error, setError] = useState(null);
  const [creating, setCreating] = useState(false);
  const [removeNote, setRemoveNote] = useState(null);

  const create = async () => {
    setError(null); setCreating(true);
    try { setShare(await createShare(hours)); } catch (e) { setError(e.message); } finally { setCreating(false); }
  };
  const remove = async (d) => {
    setRemoveNote(null);
    try { await removeDoctor(d.linkId); await doctors.reload(); } catch (e) { setRemoveNote(e.message); }
  };

  const fullUrl = share ? appUrl(share.url) : "";
  const hasFamily = (family.data?.length ?? 0) > 0;
  const nAccess = doctors.data?.length ?? 0;

  return (
    <div className="mt-page">
      <Chapter tone="ground">
        <RV className="mt-opening">
          <div className="mt-label">{t("sharing")}</div>
          <h1 className="mt-display">{ml ? "നിങ്ങളുടെ ആരോഗ്യ കഥ " : "Share your "}<em>{ml ? "പങ്കിടുക" : "health story"}</em>.</h1>
          <p className="mt-lede">{ml ? "ആർക്കൊക്കെ, എങ്ങനെ നിങ്ങളുടെ രേഖകൾ കാണാമെന്ന് തീരുമാനിക്കുക." : "Choose how someone can see your health story, for how long, and take that access back whenever you want."}</p>
        </RV>
        <div className="mt-grid mt-gap-top">
          <RV className="c-7"><SharePanel share={share} fullUrl={fullUrl} hours={hours} setHours={setHours} creating={creating} error={error}
            onCreate={create} previewHref={share ? appPath(share.url) : "#"} consoleHref={share ? appPath(`/console/${share.token}`) : "#"} t={t} ml={ml} /></RV>
          <RV className="c-5"><InviteCode ml={ml} /></RV>
        </div>
      </Chapter>

      <Chapter tone="soft" no="01" kicker={ml ? "ഇപ്പോൾ" : "Current access"}
        title={ml ? "നിങ്ങളുടെ രേഖ കാണാൻ കഴിയുന്നവർ" : "Who can see your record now"}>
        {doctors.loading || doctors.error ? <Loading error={doctors.error} onRetry={doctors.reload} />
          : nAccess === 0 ? (
            <Empty>{ml ? "ഇതുവരെ ആരുമില്ല." : "No doctors are connected yet. Share a link or an invite code above."}</Empty>
          ) : (
            <RV as="ul" className="mt-acc-list" stagger={0.08} selector=":scope > li">
              {doctors.data.map((d) => <AccessRow key={d.linkId} d={d} onRemove={remove} ml={ml} />)}
            </RV>
          )}
        {removeNote && <p className="mt-error" role="alert">{removeNote}</p>}
      </Chapter>

      <Chapter tone="warm" no="02" kicker={ml ? "പ്രവർത്തനം" : "Activity"} title={t("accessLog")} last={!hasFamily}>
        {log.loading || log.error ? <Loading error={log.error} onRetry={log.reload} />
          : log.data.length === 0 ? <p className="mt-quiet">{ml ? "ഇതുവരെ ആരും കണ്ടിട്ടില്ല." : "No one has viewed your records yet."}</p>
          : (
            <RV as="ul" className="mt-act-list" stagger={0.05} selector=":scope > li">
              {log.data.slice(0, 12).map((a) => <ActivityItem key={a.id} a={a} />)}
            </RV>
          )}
      </Chapter>

      {hasFamily && (
        <Chapter tone="neutral" no="03" kicker={ml ? "പരിചരണം" : "Caregivers"} title={t("family")} last>
          <RV as="ul" className="mt-acc-list" stagger={0.08} selector=":scope > li">
            {family.data.map((f) => (
              <li key={f.id} className="mt-acc">
                <span className="av" aria-hidden="true">{(f.name || "?").charAt(0).toUpperCase()}</span>
                <div className="who"><strong>{f.name}</strong><span>{f.relation} · {f.phone}</span></div>
                <div className="can">
                  <span className="mt-label">{ml ? "അനുമതി" : "Access"}</span>
                  <span>{[f.canView && t("canView"), f.notify && t("notify")].filter(Boolean).join(" · ")}</span>
                </div>
              </li>
            ))}
          </RV>
        </Chapter>
      )}
    </div>
  );
}
