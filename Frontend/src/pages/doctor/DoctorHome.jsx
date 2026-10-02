import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { linkPatient, listDoctorPatients, startDoctorConsole } from "../../api/client.js";
import { getProfile } from "../../App.jsx";
import { Empty, Loading, formatDate } from "../../components/ui.jsx";
import { useT } from "../../i18n.js";
import { useApi } from "../../useApi.js";

export default function DoctorHome() {
  const { lang } = useT();
  const ml = lang === "ml";
  const navigate = useNavigate();
  const me = getProfile();
  const { data, loading, error, reload } = useApi(listDoctorPatients);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(null); // "link" | patientId
  const [msg, setMsg] = useState(null); // { kind: "ok" | "error", text }

  const add = async (e) => {
    e.preventDefault();
    setBusy("link");
    setMsg(null);
    try {
      const r = await linkPatient(code);
      setCode("");
      setMsg({ kind: "ok", text: ml ? `${r.name} ചേർത്തു.` : `${r.name} was added to your patients.` });
      await reload();
    } catch (err) {
      setMsg({ kind: "error", text: err.message });
    } finally {
      setBusy(null);
    }
  };

  const open = async (p) => {
    setBusy(p.patientId);
    setMsg(null);
    try {
      const { token } = await startDoctorConsole(p.patientId);
      navigate(`/console/${token}`);
    } catch (err) {
      setMsg({ kind: "error", text: err.message });
      setBusy(null);
    }
  };

  return (
    <>
      <div className="page-header">
        <h2>{ml ? "എന്റെ രോഗികൾ" : "My patients"}</h2>
        <p className="text-dim text-sm">
          {me?.name}
          {me?.specialty ? ` · ${me.specialty}` : ""}
          {me?.hospital ? ` · ${me.hospital}` : ""}
        </p>
      </div>

      <section className="card">
        <h3>{ml ? "കോഡ് ഉപയോഗിച്ച് രോഗിയെ ചേർക്കുക" : "Add a patient with their code"}</h3>
        <p className="text-dim text-sm">
          {ml
            ? "രോഗി അവരുടെ ആപ്പിൽ Sharing ടാബിൽ നിന്ന് കോഡ് ഉണ്ടാക്കി നിങ്ങൾക്ക് നൽകും."
            : "The patient makes a code in their app (Sharing tab, Invite your doctor) and gives it to you. It works once and expires after 24 hours."}
        </p>
        <form onSubmit={add} className="row" style={{ marginTop: "var(--sp-3)" }}>
          <input
            style={{ flex: "1 1 180px", textTransform: "uppercase", letterSpacing: "0.1em" }}
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="ABCD-2345"
            aria-label={ml ? "രോഗിയുടെ കോഡ്" : "Patient code"}
            autoCapitalize="characters"
            autoComplete="off"
            spellCheck={false}
            maxLength={12}
          />
          <button className="primary" disabled={busy !== null || code.replace(/\W/g, "").length < 8}>
            {busy === "link" ? "…" : ml ? "ചേർക്കുക" : "Add patient"}
          </button>
        </form>
        {msg && (
          <p className={msg.kind === "error" ? "error text-sm" : "text-sm"} role={msg.kind === "error" ? "alert" : "status"}>
            {msg.text}
          </p>
        )}
      </section>

      <section>
        <h3>{ml ? "രോഗികൾ" : "Patients"}</h3>
        {loading || error ? (
          <Loading error={error} onRetry={reload} />
        ) : data.length === 0 ? (
          <Empty>{ml ? "ഇതുവരെ രോഗികളില്ല. ഒരു കോഡ് ചേർക്കുക." : "No patients yet. Add one with a code above."}</Empty>
        ) : (
          <div className="list">
            {data.map((p) => (
              <div key={p.patientId} className="card row between" style={{ gap: "var(--sp-4)" }}>
                <div style={{ minWidth: 0 }}>
                  <strong>{p.name}</strong>
                  <div className="text-dim text-sm">
                    {[p.age ? `${p.age} yrs` : null, p.gender].filter(Boolean).join(" · ") || (ml ? "പ്രൊഫൈൽ പൂർത്തിയായിട്ടില്ല" : "Profile not filled in yet")}
                  </div>
                  <div className="text-dim text-xs">
                    {p.lastRecord ? `${ml ? "അവസാന രേഖ" : "Last record"}: ${formatDate(p.lastRecord)}` : ml ? "രേഖകളില്ല" : "No records yet"}
                    {p.openAlerts > 0 ? ` · ${p.openAlerts} ${ml ? "മുന്നറിയിപ്പ്" : p.openAlerts === 1 ? "warning" : "warnings"}` : ""}
                  </div>
                </div>
                <button className="primary" onClick={() => open(p)} disabled={busy !== null}>
                  {busy === p.patientId ? "…" : ml ? "രേഖ തുറക്കുക" : "Open record"}
                </button>
              </div>
            ))}
          </div>
        )}
      </section>
    </>
  );
}
