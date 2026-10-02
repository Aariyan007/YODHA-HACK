import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { getDoctorCities, updateProfile } from "../api/client.js";
import { getProfile, saveProfile, skipProfileForNow } from "../App.jsx";
import { useReveal } from "../anim.js";
import { useT } from "../i18n.js";

const split = (s) => s.split(",").map((x) => x.trim()).filter(Boolean);

export default function Profile() {
  const { lang, setLang } = useT();
  const ml = lang === "ml";
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const welcome = params.get("welcome") === "1";
  const p = getProfile() || {};
  const [f, setF] = useState({
    name: p.name && p.name !== "New patient" ? p.name : "",
    age: p.age ?? "",
    gender: p.gender || "",
    bloodGroup: p.bloodGroup || "",
    city: p.city || "",
    allergies: (p.allergies || []).join(", "),
    conditions: (p.conditions || []).join(", "),
  });
  const [cities, setCities] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [saved, setSaved] = useState(false);
  const ref = useReveal([], { selector: ".reveal" });

  useEffect(() => { getDoctorCities().then(setCities).catch(() => {}); }, []);
  const set = (k) => (e) => setF((s) => ({ ...s, [k]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    if (!f.name.trim()) { setError(ml ? "പേര് നൽകുക." : "Please enter a name."); return; }
    setBusy(true);
    setError(null);
    try {
      const out = await updateProfile({
        name: f.name.trim(), age: f.age === "" ? undefined : Number(f.age), gender: f.gender || undefined,
        bloodGroup: f.bloodGroup || undefined, city: f.city || undefined, language: lang,
        allergies: split(f.allergies), conditions: split(f.conditions),
      });
      saveProfile(out);
      setSaved(true);
      if (welcome) navigate("/", { replace: true });
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div ref={ref} className="profile-page">
      <div className="page-header reveal">
        <div>
          <h2>{welcome ? (ml ? "സ്വാഗതം! നിങ്ങളെക്കുറിച്ച് പറയൂ" : "Welcome! Tell us about you") : (ml ? "എന്റെ പ്രൊഫൈൽ" : "My profile")}</h2>
          <p className="text-dim text-sm" style={{ margin: "4px 0 0" }}>
            {ml ? "അലർജിയും രോഗാവസ്ഥകളും ഉപയോഗിച്ച് പുതിയ മരുന്നുകൾ പരിശോധിക്കും. നഗരം ഉപയോഗിച്ച് അടുത്തുള്ള ഡോക്ടർമാരെ കണ്ടെത്തും."
                : "Allergies and conditions are used to check every new medicine. Your town is used to find doctors near you."}
          </p>
        </div>
      </div>
      <form className="card profile-form" onSubmit={submit} noValidate>
        <div className="form-grid">
          <label className="reveal">{ml ? "പേര്" : "Name"}
            <input value={f.name} onChange={set("name")} autoComplete="name" required />
          </label>
          <label className="reveal">{ml ? "പ്രായം" : "Age"}
            <input inputMode="numeric" value={f.age} onChange={set("age")} />
          </label>
          <label className="reveal">{ml ? "ലിംഗം" : "Gender"}
            <select value={f.gender} onChange={set("gender")}>
              <option value="">—</option>
              <option value="Female">{ml ? "സ്ത്രീ" : "Female"}</option>
              <option value="Male">{ml ? "പുരുഷൻ" : "Male"}</option>
              <option value="Other">{ml ? "മറ്റുള്ളവ" : "Other"}</option>
            </select>
          </label>
          <label className="reveal">{ml ? "രക്ത ഗ്രൂപ്പ്" : "Blood group"}
            <select value={f.bloodGroup} onChange={set("bloodGroup")}>
              <option value="">—</option>
              {["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"].map((b) => <option key={b}>{b}</option>)}
            </select>
          </label>
          <label className="reveal">{ml ? "നഗരം" : "Town"}
            <select value={f.city} onChange={set("city")}>
              <option value="">—</option>
              {cities.map((c) => <option key={c.city} value={c.city}>{c.city}{c.state !== "Kerala" ? `, ${c.state}` : ""}</option>)}
            </select>
          </label>
          <label className="reveal">{ml ? "ഭാഷ" : "Language"}
            <select value={lang} onChange={(e) => setLang(e.target.value)}>
              <option value="en">English</option>
              <option value="ml">മലയാളം</option>
            </select>
          </label>
          <label className="reveal span-2">{ml ? "അലർജികൾ (കോമ ഇട്ട്)" : "Allergies (comma separated)"}
            <input value={f.allergies} onChange={set("allergies")} placeholder={ml ? "ഉദാ: Penicillin, Sulfa" : "e.g. Penicillin, Sulfa drugs"} />
          </label>
          <label className="reveal span-2">{ml ? "രോഗാവസ്ഥകൾ (കോമ ഇട്ട്)" : "Conditions (comma separated)"}
            <input value={f.conditions} onChange={set("conditions")} placeholder={ml ? "ഉദാ: പ്രമേഹം, ബിപി" : "e.g. Diabetes, High BP"} />
          </label>
        </div>
        <div className="row reveal" style={{ gap: "var(--sp-3)", alignItems: "center", marginTop: "var(--sp-5)" }}>
          <button className="primary" disabled={busy}>{busy ? "…" : welcome ? (ml ? "തുടങ്ങാം" : "Save and start") : (ml ? "സേവ് ചെയ്യുക" : "Save")}</button>
          {welcome && (
            <button type="button" className="ghost" onClick={() => { skipProfileForNow(); navigate("/", { replace: true }); }}>{ml ? "പിന്നീട്" : "Skip for now"}</button>
          )}
          {saved && !welcome && <span className="text-good text-sm">{ml ? "സേവ് ചെയ്തു" : "Saved"}</span>}
          {error && <span className="error text-sm" role="alert">{error}</span>}
        </div>
      </form>
    </div>
  );
}
