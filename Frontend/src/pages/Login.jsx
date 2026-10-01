import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { requestOtp, verifyOtp } from "../api/client.js";
import { saveSession } from "../App.jsx";
import { useT } from "../i18n.js";

export default function Login({ toggle }) {
  const { t } = useT();
  const navigate = useNavigate();
  const [phone, setPhone] = useState("9876543210");
  const [otp, setOtp] = useState("");
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const run = async (fn) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const send = (e) => {
    e.preventDefault();
    run(async () => {
      await requestOtp(phone);
      setSent(true);
    });
  };

  const verify = (e) => {
    e.preventDefault();
    run(async () => {
      saveSession(await verifyOtp(phone, otp));
      navigate("/");
    });
  };

  return (
    <div className="login">
      <div className="login-top">{toggle}</div>
      <h1 className="brand big">MediThread</h1>
      <p className="muted">{t("loginTitle")}</p>
      <form className="card" onSubmit={sent ? verify : send}>
        <label>
          {t("phone")}
          <input inputMode="tel" value={phone} onChange={(e) => setPhone(e.target.value)} disabled={sent} required />
        </label>
        {sent && (
          <label>
            {t("otp")}
            <input
              inputMode="numeric"
              maxLength={6}
              pattern="\d{6}"
              value={otp}
              onChange={(e) => setOtp(e.target.value.replace(/\D/g, ""))}
              autoFocus
              required
            />
          </label>
        )}
        <button className="primary" disabled={busy}>
          {sent ? t("verify") : t("sendOtp")}
        </button>
        {error && <p className="error">{error}</p>}
        <p className="muted small">{t("demoHint")}</p>
      </form>
    </div>
  );
}
