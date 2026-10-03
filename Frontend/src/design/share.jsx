// Sharing as an access control workspace: the QR you show, who can see your record now, and what happened.
import { QRCodeSVG } from "qrcode.react";
import { Arrow } from "./primitives.jsx";
import { longDate, shortDate } from "./data.js";

const initial = (name = "?") => (name.replace(/^dr\.?\s+/i, "").trim().charAt(0) || "?").toUpperCase();

/* The QR frame: a soft sage region with scan corners. The QR itself is always real (value = the live share link). */
export function ScanFrame({ value, size = 188 }) {
  return (
    <div className={`mt-scan${value ? " live" : ""}`}>
      <span className="c tl" /><span className="c tr" /><span className="c bl" /><span className="c br" />
      {value ? (
        <div className="qr"><QRCodeSVG value={value} size={size} bgColor="#FCFEF9" fgColor="#1E2A25" /></div>
      ) : (
        <div className="ghost" aria-hidden="true">
          <span className="g a" /><span className="g b" /><span className="g c2" /><span className="g d" />
        </div>
      )}
    </div>
  );
}

export function SharePanel({ share, fullUrl, hours, setHours, creating, error, onCreate, previewHref, consoleHref, t, ml }) {
  return (
    <div className="mt-share">
      <ScanFrame value={share ? fullUrl : null} />
      <div className="mt-share-body">
        <div className="mt-label">{ml ? "ഡോക്ടർ ആക്സസ്" : "Doctor access"}</div>
        <h3 className="mt-share-title">{share ? (ml ? "രേഖകൾ കാണാൻ സ്കാൻ ചെയ്യുക" : "Scan to view your records") : (ml ? "ഒരു ലിങ്ക് ഉണ്ടാക്കുക" : "Make a link to share")}</h3>
        <p className="mt-share-help">{t("shareHelp")}</p>
        <div className="mt-share-controls">
          <label className="sr-only" htmlFor="share-hours-select">{ml ? "കാലാവധി" : "Link lasts"}</label>
          <select id="share-hours-select" value={hours} onChange={(e) => setHours(Number(e.target.value))}>
            <option value={1}>1 hour</option>
            <option value={24}>24 hours</option>
            <option value={72}>3 days</option>
          </select>
          <button id="create-share-btn" type="button" className="mt-btn" onClick={onCreate} disabled={creating}>
            {creating ? "Creating…" : share ? (ml ? "പുതിയ ലിങ്ക്" : "New link") : t("createLink")} {!creating && <Arrow />}
          </button>
        </div>
        {error && <p className="mt-error" role="alert">{error}</p>}
        {share && (
          <div className="mt-share-live">
            <div className="exp"><i aria-hidden="true" />{t("expires")}: <b>{new Date(share.expiresAt).toLocaleString("en-IN")}</b></div>
            <a className="url" href={previewHref} target="_blank" rel="noreferrer">{fullUrl}</a>
            <div className="acts">
              <a className="mt-btn secondary sm" href={previewHref} target="_blank" rel="noreferrer">Preview patient view</a>
              <a className="mt-btn sm" href={consoleHref} target="_blank" rel="noreferrer">Open doctor console <Arrow /></a>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export function AccessRow({ d, onRemove, ml }) {
  return (
    <li className="mt-acc">
      <span className="av" aria-hidden="true">{initial(d.name)}</span>
      <div className="who">
        <strong>{d.name}</strong>
        <span>{[d.specialty, d.hospital].filter(Boolean).join(" · ") || (ml ? "ഡോക്ടർ" : "Doctor")}</span>
      </div>
      <div className="can">
        <span className="mt-label">{ml ? "അനുമതി" : "Can view"}</span>
        <span>{d.since ? `${ml ? "മുതൽ" : "Since"} ${longDate(d.since)}` : (ml ? "എല്ലാ രേഖകളും" : "Your records")}</span>
      </div>
      <button type="button" className="mt-btn secondary sm danger" onClick={() => onRemove(d)}>{ml ? "നീക്കം ചെയ്യുക" : "Remove access"}</button>
    </li>
  );
}

export function ActivityItem({ a }) {
  return (
    <li className="mt-act">
      <span className="dot" aria-hidden="true" />
      <div className="tx">
        <span className="ac">{a.action}</span>
        <span className="mt-label">{a.who} · {a.role}{a.via ? ` · ${a.via}` : ""}</span>
      </div>
      <time className="when" dateTime={a.at}>{shortDate(a.at)}</time>
    </li>
  );
}
