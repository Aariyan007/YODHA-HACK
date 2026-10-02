import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { gsap } from "gsap";
import { askDoctors, getDoctorCities, getDoctorRecommendation, getNearbyDoctors } from "../api/client.js";
import { getProfile } from "../App.jsx";
import { reducedMotion, useReveal } from "../anim.js";
import { EmergencyBanner, RiskCard } from "../components/health.jsx";
import { Loading } from "../components/ui.jsx";
import { useT } from "../i18n.js";

const SPECIALTIES = ["General Physician", "Cardiologist", "Diabetologist", "Nephrologist", "Pulmonologist",
  "Gastroenterologist", "Endocrinologist", "Haematologist", "Neurologist", "Orthopaedician", "Gynaecologist",
  "Paediatrician", "Dermatologist", "Ophthalmologist", "ENT specialist", "Psychiatrist", "Urologist", "Dentist", "Emergency"];
const INDIA = [[6.0, 68.0], [37.6, 97.5]];

const directions = (d) => `https://www.google.com/maps/dir/?api=1&destination=${d.lat},${d.lng}`;

// ── Map (supporting context, not the hero) ──────────────────────────────────
function DoctorMap({ origin, results, pickIds, active, onSelect }) {
  const boxRef = useRef(null);
  const mapRef = useRef(null);
  const layerRef = useRef(null);
  const markersRef = useRef({});

  useEffect(() => {
    if (!boxRef.current || mapRef.current) return;
    const map = L.map(boxRef.current, {
      maxBounds: INDIA, maxBoundsViscosity: 1.0, minZoom: 4, maxZoom: 17, zoomControl: true, attributionControl: true,
    }).fitBounds(INDIA);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "© OpenStreetMap contributors", bounds: INDIA, noWrap: true,
    }).addTo(map);
    layerRef.current = L.layerGroup().addTo(map);
    mapRef.current = map;
    // The map may mount after its container animates open; settle its size.
    setTimeout(() => map.invalidateSize(), 60);
    return () => { map.remove(); mapRef.current = null; };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    const layer = layerRef.current;
    if (!map || !layer || !origin) return;
    layer.clearLayers();
    markersRef.current = {};
    const me = L.marker([origin.lat, origin.lng], {
      icon: L.divIcon({ className: "pin-me-wrap", html: `<div class="pin-me"><span></span></div>`, iconSize: [22, 22], iconAnchor: [11, 11] }),
      zIndexOffset: 1000, title: origin.label,
    }).addTo(layer);
    me.bindTooltip(origin.label, { direction: "top", offset: [0, -10] });
    const pts = [[origin.lat, origin.lng]];
    results.forEach((d, i) => {
      const pick = pickIds.includes(d.id);
      const html = `<div class="pin ${pick ? "pick" : ""} ${d.emergency24x7 ? "er" : ""}"><b>${pick ? pickIds.indexOf(d.id) + 1 : "·"}</b></div>`;
      const m = L.marker([d.lat, d.lng], {
        icon: L.divIcon({ className: "pin-wrap", html, iconSize: [44, 30], iconAnchor: [22, 30] }),
        zIndexOffset: pick ? 500 - i : -i, title: d.name,
      }).addTo(layer);
      m.on("click", () => onSelect(d.id));
      markersRef.current[d.id] = m;
      if (i < 6) pts.push([d.lat, d.lng]);
    });
    map.flyToBounds(L.latLngBounds(pts).pad(0.25), { duration: reducedMotion() ? 0 : 0.9, maxZoom: 13 });
    if (!reducedMotion()) {
      requestAnimationFrame(() => {
        const els = boxRef.current?.querySelectorAll(".pin");
        if (els?.length) gsap.from(els, { y: -24, opacity: 0, duration: 0.45, stagger: 0.035, ease: "bounce.out", delay: 0.3, clearProps: "transform,opacity" });
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [origin?.lat, origin?.lng, results, pickIds.join(",")]);

  useEffect(() => {
    Object.entries(markersRef.current).forEach(([id, m]) => {
      const el = m.getElement()?.querySelector(".pin");
      el?.classList.toggle("active", id === active);
    });
    const m = markersRef.current[active];
    if (m && mapRef.current) mapRef.current.panTo(m.getLatLng(), { animate: !reducedMotion() });
  }, [active]);

  return <div ref={boxRef} className="doctor-map" role="region" aria-label="Map of doctors in India" />;
}

// ── "Why this match" — built only from real doctor fields ───────────────────
function whyItems(d, ctx) {
  const { data, ml, mode, specialty, wantsMl } = ctx;
  const out = [];
  out.push(d.department ? `${d.department} department` : d.specialty);
  const pk = (data.picks || []).find((p) => p.id === d.id);
  if (pk) out.push((ml && pk.whyMl) || pk.why);
  else if (data.risk?.specialist && d.specialty === data.risk.specialist) out.push(ml ? `${data.risk.title}-ന് പ്രസക്തം` : `Relevant to: ${data.risk.title}`);
  else if (mode === "search" && specialty) out.push(ml ? "നിങ്ങൾ തിരഞ്ഞതുമായി യോജിക്കുന്നു" : "Matches the care you searched for");
  if (d.openNow) out.push(d.closesAt ? (ml ? `ഇന്ന് തുറന്ന് · ${d.closesAt} വരെ` : `Available today · open till ${d.closesAt}`) : (ml ? "എപ്പോഴും തുറന്ന്" : "Open 24 hours"));
  if (wantsMl && d.languages?.some((l) => /malayalam/i.test(l))) out.push(ml ? "മലയാളം സംസാരിക്കും" : "Speaks Malayalam");
  if (d.teleconsult) out.push(ml ? "വീഡിയോ കൺസൾട്ട് ലഭ്യം" : "Video consult available");
  return out.slice(0, 5);
}

// ── One care match (clinical/editorial, not a restaurant card) ──────────────
function CareDoctor({ d, rank, active, onSelect, ctx }) {
  const { ml } = ctx;
  const ref = useRef(null);
  useEffect(() => {
    if (active && ref.current) ref.current.scrollIntoView({ block: "nearest", behavior: reducedMotion() ? "auto" : "smooth" });
  }, [active]);
  const title = d.department ? d.clinic : d.name;
  const role = d.department ? `${d.department} · ${d.city}` : `${d.specialty} · ${d.clinic}, ${d.city}`;
  const why = whyItems(d, ctx);
  return (
    <article ref={ref} className={`care-doc${active ? " active" : ""}${rank ? " picked" : ""}`} onClick={() => onSelect(d.id)}>
      <div className="cd-head">
        {rank ? <span className="cd-rank">{ml ? `ഏറ്റവും അനുയോജ്യം ${rank}` : `Best match ${rank}`}</span> : null}
        {d.emergency24x7 && <span className="cd-er">24×7 {ml ? "അത്യാഹിതം" : "emergency"}</span>}
        <h4 className="cd-name">{title}</h4>
        <div className="cd-role">{role}</div>
      </div>

      <div className="cd-why">
        <div className="cd-why-label">{ml ? "എന്തുകൊണ്ട് ഈ യോജിപ്പ്" : "Why this match"}</div>
        <ul className="cd-why-list">
          {why.map((w, i) => (
            <li key={i}><span className="cd-tick" aria-hidden="true">✓</span>{w}</li>
          ))}
        </ul>
      </div>

      <div className="cd-foot">
        <div className="cd-meta">
          <span>~{d.distanceKm} km {ml ? "അകലെ" : "away"}</span>
          {d.feeInr ? <span className="sep">·</span> : null}
          {d.feeInr ? <span>₹{d.feeInr}</span> : null}
          {d.rating ? <span className="sep">·</span> : null}
          {d.rating ? <span className="cd-rating">{d.rating.toFixed(1)} {ml ? "റേറ്റിംഗ്" : "rating"} ({d.reviews})</span> : null}
        </div>
        <div className="cd-actions" onClick={(e) => e.stopPropagation()}>
          <a className="ed-cta" style={{ padding: "10px 18px", minHeight: 44 }} href={`tel:${d.phone.replace(/\s/g, "")}`}>{ml ? "വിളിക്കുക" : "Call"}</a>
          <a className="ed-link" href={directions(d)} target="_blank" rel="noreferrer">{ml ? "വഴി കാണിക്കുക" : "Get directions"} →</a>
        </div>
      </div>
    </article>
  );
}

// ── Page: Care Match ────────────────────────────────────────────────────────
export default function Doctors() {
  const { lang, pick } = useT();
  const ml = lang === "ml";
  const [params, setParams] = useSearchParams();
  const profile = getProfile();
  const [cities, setCities] = useState([]);
  const [city, setCity] = useState(profile?.city || "");
  const [geo, setGeo] = useState(null);
  const [geoMsg, setGeoMsg] = useState(null);
  const [q, setQ] = useState("");
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [active, setActive] = useState(null);
  const [onlyOpen, setOnlyOpen] = useState(false);
  const [malayalam, setMalayalam] = useState(false);
  const [asked, setAsked] = useState(false);
  const [showMap, setShowMap] = useState(false);

  const specialty = params.get("specialty") || "";
  const emergency = params.get("emergency") === "1";
  const mode = specialty || emergency ? "search" : "foryou";

  useEffect(() => { getDoctorCities().then(setCities).catch(() => {}); }, []);

  const locate = useCallback(() => {
    if (!navigator.geolocation) { setGeoMsg(ml ? "ഈ ബ്രൗസറിൽ ലൊക്കേഷൻ ലഭ്യമല്ല." : "Location is not available in this browser."); return; }
    setGeoMsg(ml ? "ലൊക്കേഷൻ കണ്ടെത്തുന്നു…" : "Finding your location…");
    navigator.geolocation.getCurrentPosition(
      (p) => { setGeo({ lat: p.coords.latitude, lng: p.coords.longitude }); setGeoMsg(null); },
      () => setGeoMsg(ml ? "ലൊക്കേഷൻ കിട്ടിയില്ല. നഗരം തിരഞ്ഞെടുക്കുക." : "Could not get your location. Pick a town instead."),
      { timeout: 8000, maximumAge: 600000 },
    );
  }, [ml]);

  useEffect(() => { if (emergency) { locate(); setShowMap(true); } }, [emergency, locate]);

  const load = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const loc = { lat: geo?.lat, lng: geo?.lng, city: geo ? undefined : city || undefined };
      const res = mode === "foryou"
        ? await getDoctorRecommendation(loc)
        : await getNearbyDoctors({ ...loc, specialty: emergency ? undefined : specialty, emergency, openNow: onlyOpen,
                                   language: malayalam ? "Malayalam" : undefined });
      setData(res);
      setAsked(false);
      setActive(res.picks?.[0]?.id || res.results?.[0]?.id || null);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }, [geo, city, mode, specialty, emergency, onlyOpen, malayalam]);

  useEffect(() => { load(); }, [load]);

  const ask = async (e) => {
    e.preventDefault();
    if (q.trim().length < 2) return;
    setBusy(true);
    setError(null);
    try {
      const res = await askDoctors(q.trim(), geo?.lat, geo?.lng);
      setData(res);
      setAsked(true);
      setActive(res.picks?.[0]?.id || res.results?.[0]?.id || null);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const setSpecialty = (s) => {
    if (asked && !s && !params.get("specialty") && !params.get("emergency")) load();
    const p = new URLSearchParams(params);
    if (s) p.set("specialty", s); else p.delete("specialty");
    p.delete("emergency");
    if (s === "Emergency") p.set("emergency", "1");
    setParams(p, { replace: true });
  };

  const picks = data?.picks || [];
  const pickIds = useMemo(() => picks.map((p) => p.id), [picks]);
  const rankOf = (id) => (pickIds.indexOf(id) >= 0 ? pickIds.indexOf(id) + 1 : null);
  const listRef = useReveal([data], { selector: ".care-doc", y: 18, stagger: 0.06 });

  const wantsMl = malayalam || profile?.language === "ml";
  const ctx = { data: data || {}, ml, mode, specialty, wantsMl };

  // The recommended type of care, and why.
  const recSpecialty = data?.specialty || data?.risk?.specialist || (emergency ? "Emergency" : specialty) || "General Physician";
  const careContext = useMemo(() => {
    const out = [];
    if (asked && data?.filters) Object.values(data.filters).forEach((v) => out.push(String(v)));
    else if (mode === "search") { if (specialty) out.push(specialty); if (emergency) out.push(ml ? "അത്യാഹിതം" : "Emergency"); }
    else {
      if (data?.risk) {
        out.push(data.risk.title);
        (data.risk.evidence || []).forEach((e) => out.push(`${e.name} ${e.value}${e.unit ? ` ${e.unit}` : ""}`));
      }
      (profile?.conditions || []).forEach((c) => out.push(c));
    }
    return [...new Set(out)].slice(0, 6);
  }, [data, asked, mode, specialty, emergency, profile, ml]);

  const reason = (() => {
    if (asked && data?.filters) return ml ? "നിങ്ങളുടെ അഭ്യർത്ഥന മനസ്സിലാക്കി, ഇവ നിർദ്ദേശിക്കുന്നു." : "Based on what you asked for.";
    if (mode === "search") return ml ? `${specialty || (emergency ? "അത്യാഹിത" : "")} പരിചരണം നിങ്ങളുടെ അടുത്ത്.` : `${emergency ? "Emergency" : specialty} care near you.`;
    if (data?.risk) return pick(data.risk, "message");
    return ml ? "നിങ്ങളുടെ രേഖയിൽ അടിയന്തരമായി ഒന്നുമില്ല — പതിവ് പരിശോധനയ്ക്ക് ജനറൽ ഫിസിഷ്യൻമാർ."
              : "Nothing in your record needs urgent care — these are General Physicians for a routine review.";
  })();

  return (
    <>
      <header className="ph" style={{ paddingTop: "clamp(20px,4vw,40px)" }}>
        <div className="ed-kicker">{ml ? "കെയർ മാച്ച്" : "Care match"}</div>
        <h1 className="ph-greet">{ml ? "ശരിയായ " : "Find the "}<span className="nm">{ml ? "പരിചരണം" : "right care"}</span>.</h1>
        <p className="ph-sub" style={{ marginTop: "var(--sp-3)" }}>
          {ml ? "നിങ്ങളുടെ ആരോഗ്യ കഥയുമായി ചേർത്ത്, വെറും ലൊക്കേഷൻ കൊണ്ടല്ല."
              : "Matched to your health story — not just who's nearest."}
        </p>
      </header>

      {/* Ask bar */}
      <form className="care-ask" onSubmit={ask}>
        <span className="ca-spark" aria-hidden="true">✦</span>
        <input value={q} onChange={(e) => setQ(e.target.value)} maxLength={300}
               placeholder={ml ? "ഉദാ: ഞായറാഴ്ച തുറക്കുന്ന കാക്കനാട്ടെ ഹൃദ്രോഗ ഡോക്ടർ" : "Describe it: a Malayalam-speaking heart doctor near Kakkanad, open Sunday"}
               aria-label="Describe the care you need" />
        <button className="ed-cta" disabled={busy || q.trim().length < 2}>{ml ? "ചോദിക്കുക" : "Ask"}</button>
      </form>

      {/* Emergency / risk lead */}
      {data?.risk && mode === "foryou" && !asked && data.emergency && <EmergencyBanner risk={data.risk} />}

      {/* CARE CONTEXT → RECOMMENDED CARE */}
      <section className="care-context">
        <div className="cc-you">
          <div className="ed-kicker bare">{ml ? "നിങ്ങൾ പരിചരണം തേടുന്നത്" : "You're looking for care for"}</div>
          {careContext.length > 0 ? (
            <div className="cc-chips">
              {careContext.map((c, i) => <span key={i} className="cc-chip">{c}</span>)}
            </div>
          ) : (
            <p className="ed-meta">{ml ? "പൊതുവായ പരിശോധന." : "A general check-up."}</p>
          )}
        </div>
        <div className="cc-arrow" aria-hidden="true">
          <svg viewBox="0 0 24 48" width="24" height="48" fill="none"><path d="M12 2v40m0 0l-6-7m6 7l6-7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
        </div>
        <div className="cc-rec">
          <div className="ed-kicker bare">{ml ? "MediThread നിർദ്ദേശിക്കുന്നു" : "MediThread suggests"}</div>
          <div className="cc-spec">{recSpecialty}</div>
          <p className="cc-reason">{reason}</p>
          {data?.risk && !data.emergency && mode === "foryou" && !asked && (
            <div style={{ marginTop: "var(--sp-4)" }}><RiskCard risk={data.risk} showFinder={false} /></div>
          )}
        </div>
      </section>

      {/* Refine */}
      <div className="care-refine">
        <div className="chips" role="group" aria-label="Mode">
          <button type="button" className={`chip${mode === "foryou" && !asked ? " on" : ""}`} onClick={() => setSpecialty("")}>
            {ml ? "എന്റെ കഥയ്ക്കായി" : "For my story"}
          </button>
          <button type="button" className={`chip er${emergency && !asked ? " on" : ""}`} onClick={() => setSpecialty("Emergency")}>
            {ml ? "അത്യാഹിതം" : "Emergency"}
          </button>
          <select className="chip-select" value={emergency ? "" : specialty} onChange={(e) => setSpecialty(e.target.value)} aria-label="Specialty">
            <option value="">{ml ? "സ്പെഷ്യാലിറ്റി…" : "Any specialty…"}</option>
            {SPECIALTIES.filter((s) => s !== "Emergency").map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          {mode === "search" && (
            <>
              <button type="button" className={`chip${onlyOpen ? " on" : ""}`} onClick={() => setOnlyOpen((x) => !x)}>{ml ? "ഇപ്പോൾ തുറന്നത്" : "Open now"}</button>
              <button type="button" className={`chip${malayalam ? " on" : ""}`} onClick={() => setMalayalam((x) => !x)}>Malayalam</button>
            </>
          )}
        </div>
        <div className="row" style={{ gap: "var(--sp-2)", alignItems: "center", flexWrap: "wrap" }}>
          <button type="button" className="ed-link" onClick={locate}>📍 {ml ? "എന്റെ ലൊക്കേഷൻ" : "Use my location"}</button>
          <select value={geo ? "__geo" : city} onChange={(e) => { setGeo(null); setCity(e.target.value); }} aria-label="Town">
            {geo && <option value="__geo">{ml ? "എന്റെ ലൊക്കേഷൻ" : "My location"}</option>}
            <option value="">{ml ? "നഗരം…" : "Town…"}</option>
            {cities.map((c) => <option key={c.city} value={c.city}>{c.city}{c.state !== "Kerala" ? `, ${c.state}` : ""}</option>)}
          </select>
        </div>
      </div>
      {geoMsg && <p className="ed-meta" style={{ marginTop: "var(--sp-2)" }}>{geoMsg}</p>}
      {data?.origin?.outsideIndia && (
        <p className="notice">{ml ? "നിങ്ങൾ ഇന്ത്യക്ക് പുറത്താണ്. ഈ ഫൈൻഡർ ഇന്ത്യയിൽ മാത്രം; കാണിക്കുന്നത്:" : "You seem to be outside India. This finder covers India only, so it is showing results around"} <b>{data.origin.label}</b>.</p>
      )}
      {data?.relaxed?.map((r, i) => <p key={i} className="notice">{r}</p>)}

      {/* CARE MATCHES */}
      <section className="ed-section" style={{ marginTop: "clamp(28px,4vw,44px)" }}>
        <div className="ed-section-head">
          <div><div className="ed-kicker">{recSpecialty}</div><h3>{ml ? "നിങ്ങൾക്കായുള്ള ഡോക്ടർമാർ" : "Doctors matched to you"}</h3></div>
          {data?.results?.length > 0 && (
            <button type="button" className="ed-link" onClick={() => setShowMap((x) => !x)}>
              {showMap ? (ml ? "മാപ്പ് മറയ്ക്കുക" : "Hide map") : (ml ? "മാപ്പിൽ കാണുക" : "Show on map")} →
            </button>
          )}
        </div>

        <div ref={listRef} className="care-list">
          {busy && !data && <Loading />}
          {error && <Loading error={error} onRetry={load} />}
          {data?.results?.length === 0 && <p className="notice">{ml ? "ഒന്നും കണ്ടില്ല. ഫിൽട്ടർ മാറ്റുക." : "No doctors matched. Try fewer filters."}</p>}
          {data?.results?.map((d) => (
            <CareDoctor key={d.id} d={d} rank={rankOf(d.id)} active={active === d.id} onSelect={setActive} ctx={ctx} />
          ))}
          {data?.nearbyGp?.length > 0 && (
            <>
              <div className="ed-kicker" style={{ margin: "var(--sp-6) 0 var(--sp-2)" }}>{ml ? "അടുത്തുള്ള ഒരു ഓപ്ഷൻ" : "A closer option first"}</div>
              {data.nearbyGp.map((d) => <CareDoctor key={d.id} d={d} active={active === d.id} onSelect={setActive} ctx={ctx} />)}
            </>
          )}
        </div>

        {/* Map as supporting context, revealed on demand */}
        {showMap && data?.results?.length > 0 && (
          <div className="care-map animate-in-fast">
            <DoctorMap origin={data?.origin} results={data?.results || []} pickIds={pickIds} active={active} onSelect={setActive} />
            <p className="ed-meta" style={{ marginTop: 6 }}>
              {ml ? "സാമ്പിൾ ഡാറ്റ: പേരുകളും നമ്പറുകളും റിവ്യൂകളും സാങ്കൽപ്പികം." : "Sample data: doctor names, clinics, phone numbers and reviews are fictional."}
            </p>
          </div>
        )}
      </section>

      {/* CARE PATH — connect discovery back to the MediThread story */}
      {data?.results?.length > 0 && (
        <section className="ed-section care-path">
          <div className="ed-section-head"><div><div className="ed-kicker">{ml ? "അടുത്ത ഘട്ടം" : "The care path"}</div><h3>{ml ? "ഡോക്ടർ നിങ്ങളുടെ കഥ കാണട്ടെ" : "Let the doctor see your story"}</h3></div></div>
          <ol className="path-steps">
            {[
              ml ? "ആരോഗ്യ ഡാറ്റ" : "Your health data",
              ml ? "MediThread മനസ്സിലാക്കുന്നു" : "MediThread's understanding",
              ml ? "കെയർ മാച്ച്" : "Care match",
              ml ? "ഡോക്ടറെ തിരഞ്ഞെടുക്കുക" : "Choose a doctor",
              ml ? "കഥ പങ്കിടുക" : "Share your story",
            ].map((s, i, arr) => (
              <li key={i} className={`path-step${i === arr.length - 1 ? " last" : ""}`}>
                <span className="path-node" aria-hidden="true" />
                <span className="path-label">{s}</span>
              </li>
            ))}
          </ol>
          {data?.bring?.length > 0 && (
            <div className="path-bring">
              <div className="ed-kicker bare">{ml ? "ഡോക്ടറുടെ അടുത്ത് കൊണ്ടുപോകേണ്ടത്" : "Take these to the visit"}</div>
              <ul>{data.bring.map((b, i) => <li key={i}>{(ml && b.textMl) || b.text}</li>)}</ul>
            </div>
          )}
          <Link className="ed-cta ghost" to="/sharing" style={{ marginTop: "var(--sp-5)" }}>
            {ml ? "ഡോക്ടറുമായി പങ്കിടുക" : "Share with a doctor"} →
          </Link>
        </section>
      )}
    </>
  );
}
