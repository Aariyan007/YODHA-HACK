import { useEffect, useState } from "react";
import {
  fireDemoMissed,
  fireDemoReminder,
  getDeepHealth,
  getReminderSettings,
  resetDemo,
  saveReminderSettings,
  testTelegram,
} from "../api/client.js";
import { Loading } from "../components/ui.jsx";
import { useT } from "../i18n.js";

// Browser notifications: ask for permission only when the user turns the toggle on.
async function ensureNotificationPermission() {
  if (typeof Notification === "undefined") return "unsupported";
  if (Notification.permission === "granted") return "granted";
  if (Notification.permission === "denied") return "denied";
  return Notification.requestPermission();
}

const HEALTH_LABELS = [
  ["database", "Database"],
  ["redis", "Redis"],
  ["gemini", "Gemini"],
  ["groq", "Groq"],
  ["telegram", "Telegram"],
  ["scheduler", "Scheduler"],
];
const HEALTH_WORDS = {
  ok: { telegram: "ready", scheduler: "running", _: "ok" },
  fallback: { _: "fallback" },
  down: { _: "down" },
};

function healthLine(h, err) {
  if (err) return `Status check failed: ${err}`;
  if (!h) return "Checking services…";
  return HEALTH_LABELS.map(([k, label]) => {
    const st = h[k]?.status || "down";
    const words = HEALTH_WORDS[st] || HEALTH_WORDS.down;
    return `${label} ${words[k] || words._}`;
  }).join(" · ");
}

export default function Reminders() {
  const { lang } = useT();
  const ml = lang === "ml";
  const [form, setForm] = useState(null);
  const [meta, setMeta] = useState({ telegramReady: true, demoMode: false });
  const [loadError, setLoadError] = useState(null);
  const [busy, setBusy] = useState(null); // "save" | "test" | "fire" | "missed"
  const [notice, setNotice] = useState(null); // { kind: "ok" | "error", text }
  const [demoOut, setDemoOut] = useState(null);
  const [confirmReset, setConfirmReset] = useState(false);
  const [health, setHealth] = useState(null);
  const [healthError, setHealthError] = useState(null);
  const [healthBusy, setHealthBusy] = useState(false);

  const loadHealth = () => {
    setHealthBusy(true);
    setHealthError(null);
    return getDeepHealth()
      .then(setHealth)
      .catch((e) => setHealthError(e.message))
      .finally(() => setHealthBusy(false));
  };

  useEffect(() => {
    getReminderSettings()
      .then((s) => {
        setForm(s);
        setMeta({ telegramReady: s.telegramReady, demoMode: s.demoMode });
        if (s.demoMode) loadHealth();
      })
      .catch((e) => setLoadError(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!form) return <Loading error={loadError} />;

  const setChannel = (name, value) => setForm((f) => ({ ...f, channels: { ...f.channels, [name]: value } }));

  const togglePhone = async (on) => {
    if (!on) return setChannel("phone", false);
    const result = await ensureNotificationPermission();
    if (result === "granted") {
      setChannel("phone", true);
      setNotice(null);
    } else {
      setChannel("phone", false);
      setNotice({
        kind: "error",
        text: result === "unsupported"
          ? "This browser cannot show notifications."
          : "Notifications are blocked. Allow them in your browser settings, then try again.",
      });
    }
  };

  const save = async () => {
    const saved = await saveReminderSettings(form);
    setForm(saved);
    setMeta({ telegramReady: saved.telegramReady, demoMode: saved.demoMode });
    return saved;
  };

  const run = async (name, fn, okText) => {
    setBusy(name);
    setNotice(null);
    try {
      await fn();
      setNotice({ kind: "ok", text: okText });
    } catch (e) {
      setNotice({ kind: "error", text: e.message });
    } finally {
      setBusy(null);
    }
  };

  const onSave = () => run("save", save, ml ? "സേവ് ചെയ്തു." : "Saved.");
  const onTest = () =>
    run("test", async () => {
      await save();
      await testTelegram();
    }, ml ? "ടെലിഗ്രാമിലേക്ക് അയച്ചു. നിങ്ങളുടെ ഫോൺ നോക്കൂ." : "Test message sent. Check your Telegram.");

  const demo = async (name, fn) => {
    setBusy(name);
    setDemoOut(null);
    try {
      const out = await fn();
      setDemoOut(out.sent ? out.message : out.error || "Nothing was sent.");
    } catch (e) {
      setDemoOut(e.message);
    } finally {
      setBusy(null);
    }
  };

  const onReset = async () => {
    setBusy("reset");
    setDemoOut(null);
    try {
      const out = await resetDemo();
      const r = out.restored;
      setDemoOut(`Demo reset: ${r.documents} records, ${r.medicines} medicines, ${r.alerts} alerts. Telegram reminders are on.`);
      setForm(await getReminderSettings());
      setConfirmReset(false);
    } catch (e) {
      setDemoOut(e.message);
    } finally {
      setBusy(null);
    }
  };

  return (
    <>
      <h2>{ml ? "ഓർമ്മപ്പെടുത്തലുകൾ" : "Reminders"}</h2>
      <div className="list">

      {!meta.telegramReady && (
        <p className="card error" role="alert">
          {ml ? "സെർവറിൽ ടെലിഗ്രാം ബോട്ട് സജ്ജമാക്കിയിട്ടില്ല." : "Telegram is not set up on the server, so Telegram messages cannot be sent."}
        </p>
      )}

      <section className="card">
        <label className="toggle">
          <input
            type="checkbox"
            checked={form.remindersEnabled}
            onChange={(e) => setForm({ ...form, remindersEnabled: e.target.checked })}
          />
          <span><strong>{ml ? "ഓർമ്മപ്പെടുത്തലുകൾ ഓൺ" : "Reminders on"}</strong></span>
        </label>

        <label className="toggle">
          <input type="checkbox" checked={form.channels.phone} onChange={(e) => togglePhone(e.target.checked)} />
          <span>{ml ? "ഈ ഫോണിൽ അറിയിപ്പ്" : "Notify on this phone"}</span>
        </label>
        <label className="toggle">
          <input type="checkbox" checked={form.channels.telegram} onChange={(e) => setChannel("telegram", e.target.checked)} />
          <span>{ml ? "ടെലിഗ്രാമിൽ അയയ്ക്കുക" : "Send to Telegram"}</span>
        </label>
        <label className="toggle">
          <input type="checkbox" checked={form.channels.family} onChange={(e) => setChannel("family", e.target.checked)} />
          <span>{ml ? "മരുന്ന് വിട്ടാൽ കുടുംബത്തെ അറിയിക്കുക" : "Tell family if a dose is missed"}</span>
        </label>
      </section>

      <section className="card">
        <label>
          {ml ? "ടെലിഗ്രാം ചാറ്റ് ഐഡി" : "Telegram chat ID"}
          <input
            inputMode="numeric"
            value={form.telegramChatId || ""}
            onChange={(e) => setForm({ ...form, telegramChatId: e.target.value })}
            placeholder="123456789"
          />
        </label>
        <p className="muted small">
          {ml ? "മെഡിത്രെഡ് ബോട്ടിന് സന്ദേശം അയച്ച ശേഷം നിങ്ങളുടെ ഐഡി ഇവിടെ പേസ്റ്റ് ചെയ്യുക." : "Message the MediThread bot, then paste your ID."}
        </p>

        {form.channels.family && (
          <>
            <label>
              {ml ? "കുടുംബാംഗത്തിന്റെ പേര്" : "Family member's name"}
              <input value={form.familyName || ""} onChange={(e) => setForm({ ...form, familyName: e.target.value })} />
            </label>
            <label>
              {ml ? "കുടുംബത്തിന്റെ ടെലിഗ്രാം ഐഡി (ഓപ്ഷണൽ)" : "Family Telegram chat ID (optional)"}
              <input
                inputMode="numeric"
                value={form.familyChatId || ""}
                onChange={(e) => setForm({ ...form, familyChatId: e.target.value })}
                placeholder={ml ? "ശൂന്യമെങ്കിൽ നിങ്ങളുടെ ചാറ്റിലേക്ക്" : "Blank = same chat as yours"}
              />
            </label>
            <label>
              {ml ? "എത്ര മിനിറ്റിന് ശേഷം അറിയിക്കണം" : "Tell family after (minutes)"}
              <input
                type="number"
                min="1"
                max="1440"
                value={form.missedAfterMinutes}
                onChange={(e) => setForm({ ...form, missedAfterMinutes: Number(e.target.value) || 60 })}
              />
            </label>
          </>
        )}

        <div className="row">
          <button className="primary" onClick={onSave} disabled={busy !== null}>
            {busy === "save" ? "…" : ml ? "സേവ് ചെയ്യുക" : "Save"}
          </button>
          <button onClick={onTest} disabled={busy !== null}>
            {busy === "test" ? "…" : ml ? "ടെസ്റ്റ് സന്ദേശം അയയ്ക്കുക" : "Send a test message"}
          </button>
        </div>
        {notice && (
          <p className={notice.kind === "error" ? "error" : "muted"} role={notice.kind === "error" ? "alert" : "status"}>
            {notice.text}
          </p>
        )}
      </section>

      {meta.demoMode && (
        <section className="card">
          <h3>Demo controls</h3>
          <div className="row">
            <button onClick={() => demo("fire", fireDemoReminder)} disabled={busy !== null}>
              Fire reminder now
            </button>
            <button onClick={() => demo("missed", fireDemoMissed)} disabled={busy !== null}>
              Fire missed dose alert now
            </button>
            <button onClick={() => setConfirmReset(true)} disabled={busy !== null || confirmReset}>
              Reset demo
            </button>
          </div>
          {confirmReset && (
            <div className="row" role="alertdialog" aria-label="Confirm demo reset">
              <span className="small">Reset Ammini to the clean demo state? Uploads, imports and visits are deleted.</span>
              <button className="primary" onClick={onReset} disabled={busy !== null}>
                {busy === "reset" ? "…" : "Yes, reset"}
              </button>
              <button onClick={() => setConfirmReset(false)} disabled={busy !== null}>
                Cancel
              </button>
            </div>
          )}
          {demoOut && <p className="muted small" role="status">{demoOut}</p>}
          <p className={health && !health.allOk ? "error small" : "muted small"} role="status">
            {healthLine(health, healthError)}{" "}
            <button className="link small" onClick={loadHealth} disabled={healthBusy}>
              {healthBusy ? "Checking…" : "Check again"}
            </button>
          </p>
        </section>
      )}
      </div>
    </>
  );
}
