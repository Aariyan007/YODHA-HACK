import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
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

function Stars({ value }) {
  const full = Math.round(value * 2) / 2;
  return (
    <span className="stars" aria-label={`${value} out of 5`}>
      {[1, 2, 3, 4, 5].map((i) => (
        <span key={i} className={i <= full ? "on" : i - 0.5 === full ? "half" : ""}>★</span>
      ))}
    </span>
  );
}

const directions = (d) => `https://www.google.com/maps/dir/?api=1&destination=${d.lat},${d.lng}`;

// ── Map ────────────────────────────────────────────────────────────────────
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
      const html = `<div class="pin ${pick ? "pick" : ""} ${d.emergency24x7 ? "er" : ""}"><b>${d.rating.toFixed(1)}</b>${pick ? `<i>${pickIds.indexOf(d.id) + 1}</i>` : ""}</div>`;
      const m = L.marker([d.lat, d.lng], {
        icon: L.divIcon({ className: "pin-wrap", html, iconSize: [44, 30], iconAnchor: [22, 30] }),
        zIndexOffset: pick ? 500 - i : -i, title: d.name,
      }).addTo(layer);
      m.on("click", () => onSelect(d.id));
      markersRef.current[d.id] = m;
      if (i < 6) pts.push([d.lat, d.lng]);
    });
    map.flyToBounds(L.latLngBounds(pts).pad(0.25), { duration: reducedMotion() ? 0 : 0.9, maxZoom: 13 });
    // Drop the pins in, picks last so they land on top.
    if (!reducedMotion()) {
      requestAnimationFrame(() => {
        const els = boxRef.current?.querySelectorAll(".pin");
        if (els?.length) gsap.from(els, { y: -24, opacity: 0, duration: 0.45, stagger: 0.035, ease: "bounce.out", delay: 0.5, clearProps: "transform,opacity" });
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

// ── One doctor card ───────────────────────────────────────────────────────
function DoctorCard({ d, pick, rank, active, onSelect, ml }) {
  const ref = useRef(null);
  useEffect(() => {
    if (active && ref.current) ref.current.scrollIntoView({ block: "nearest", behavior: reducedMotion() ? "auto" : "smooth" });
  }, [active]);
  const title = d.department ? d.clinic : d.name;
  const sub = d.department ? `${d.department} department · ${d.city}` : `${d.specialty} · ${d.clinic}, ${d.city}`;
  return (
    <article ref={ref} className={`doc-card${active ? " active" : ""}${pick ? " picked" : ""}`} onClick={() => onSelect(d.id)}>
      <div className="row between" style={{ alignItems: "flex-start", gap: "var(--sp-3)" }}>
        <div style={{ minWidth: 0 }}>
          <div className="row" style={{ gap: "var(--sp-2)", alignItems: "center", flexWrap: "wrap" }}>
            {pick && <span className="ai-pick">{ml ? `AI നിർദ്ദേശം ${rank}` : `AI pick ${rank}`}</span>}
            {d.emergency24x7 && <span className="er-tag">24×7 {ml ? "അത്യാഹിതം" : "emergency"}</span>}
          </div>
          <h4 className="doc-name">{title}</h4>
          <div className="doc-sub">{sub}</div>
        </div>
        <div className="doc-dist">
          <b>{d.distanceKm}</b><span>km</span>
        </div>
      </div>
      <div className="doc-meta">
        <span className="row" style={{ gap: 6, alignItems: "center" }}>
          <Stars value={d.rating} /> <b>{d.rating.toFixed(1)}</b> <span className="text-dim">({d.reviews})</span>
        </span>
        <span className={d.openNow ? "open-now" : "closed-now"}>
          {d.openNow ? (d.closesAt ? `${ml ? "തുറന്നിരിക്കുന്നു" : "Open"} · ${ml ? "അടയ്ക്കുന്നത്" : "till"} ${d.closesAt}` : (ml ? "എപ്പോഴും തുറന്ന്" : "Open 24 h")) : (ml ? "ഇപ്പോൾ അടച്ചിരിക്കുന്നു" : "Closed now")}
        </span>
        <span>₹{d.feeInr || 0}</span>
        <span className="text-dim">{d.languages.slice(0, 3).join(", ")}</span>
      </div>
      {pick && (
        <div className="doc-ai">
          <p>{(ml && pick.whyMl) || pick.why}</p>
          {pick.reviewSummary && <p className="doc-reviews">💬 {(ml && pick.reviewSummaryMl) || pick.reviewSummary}</p>}
        </div>
      )}
      {!pick && d.reviewSnippets?.[0] && <p className="doc-reviews">💬 “{d.reviewSnippets[0]}”</p>}
      <div className="doc-actions" onClick={(e) => e.stopPropagation()}>
        <a className="btn-sm primary-sm" href={`tel:${d.phone.replace(/\s/g, "")}`}>{ml ? "വിളിക്കുക" : "Call"}</a>
        <a className="btn-sm" href={directions(d)} target="_blank" rel="noreferrer">{ml ? "വഴി" : "Directions"}</a>
        {d.teleconsult && <span className="tele-tag">{ml ? "വീഡിയോ" : "Video consult"}</span>}
      </div>
    </article>
  );
}

// ── Page ─────────────────────────────────────────────────────────────────
export default function Doctors() {
  const { lang } = useT();
  const ml = lang === "ml";
  const [params, setParams] = useSearchParams();
  const profile = getProfile();
  const [cities, setCities] = useState([]);
  const [city, setCity] = useState(profile?.city || "");
  const [geo, setGeo] = useState(null); // {lat,lng} from the browser
  const [geoMsg, setGeoMsg] = useState(null);
  const [q, setQ] = useState("");
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [active, setActive] = useState(null);
  const [onlyOpen, setOnlyOpen] = useState(false);
  const [malayalam, setMalayalam] = useState(false);
  const [asked, setAsked] = useState(false); // showing the result of a typed question

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

  // In an emergency, try the device location straight away.
  useEffect(() => { if (emergency) locate(); }, [emergency, locate]);

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
    if (asked && !s && !params.get("specialty") && !params.get("emergency")) load(); // back to "for my health"
    const p = new URLSearchParams(params);
    if (s) p.set("specialty", s); else p.delete("specialty");
    p.delete("emergency");
    if (s === "Emergency") p.set("emergency", "1");
    setParams(p, { replace: true });
  };

  const picks = data?.picks || [];
  const pickIds = useMemo(() => picks.map((p) => p.id), [picks]);
  const pickOf = (id) => picks.find((p) => p.id === id);
  const listRef = useReveal([data], { selector: ".doc-card", y: 18, stagger: 0.05 });

  return (
    <>
      <div className="page-header">
        <div>
          <h2>{ml ? "അടുത്തുള്ള ഡോക്ടർമാർ" : "Doctors near you"}</h2>
          <p className="text-dim text-sm" style={{ margin: "4px 0 0" }}>
            {ml ? "മാപ്പ് ഇന്ത്യയിൽ മാത്രം. AI റേറ്റിംഗ്, ദൂരം, ഭാഷ എന്നിവ നോക്കി തിരഞ്ഞെടുക്കുന്നു."
                : "India only. Ranked by distance, rating and reviews, language and hours; AI explains the top picks."}
          </p>
        </div>
      </div>

      <form className="ask-bar card" onSubmit={ask}>
        <span className="ask-spark" aria-hidden="true">✦</span>
        <input value={q} onChange={(e) => setQ(e.target.value)} maxLength={300}
               placeholder={ml ? "ഉദാ: ഞായറാഴ്ച തുറക്കുന്ന കാക്കനാട്ടെ ഹൃദ്രോഗ ഡോക്ടർ" : "Ask: a Malayalam-speaking heart doctor near Kakkanad open on Sunday"}
               aria-label="Describe the doctor you need" />
        <button className="primary" disabled={busy || q.trim().length < 2}>{ml ? "തിരയുക" : "Ask AI"}</button>
      </form>

      <div className="finder-controls">
        <div className="chips" role="group" aria-label="Mode">
          <button type="button" className={`chip${mode === "foryou" && !asked ? " on" : ""}`} onClick={() => setSpecialty("")}>
            {ml ? "എനിക്കായി" : "For my health"}
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
          <button type="button" className="ghost small" onClick={locate}>📍 {ml ? "എന്റെ ലൊക്കേഷൻ" : "Use my location"}</button>
          <select value={geo ? "__geo" : city} onChange={(e) => { setGeo(null); setCity(e.target.value); }} aria-label="Town">
            {geo && <option value="__geo">{ml ? "എന്റെ ലൊക്കേഷൻ" : "My location"}</option>}
            <option value="">{ml ? "നഗരം…" : "Town…"}</option>
            {cities.map((c) => <option key={c.city} value={c.city}>{c.city}{c.state !== "Kerala" ? `, ${c.state}` : ""}</option>)}
          </select>
        </div>
      </div>
      {geoMsg && <p className="text-dim text-sm">{geoMsg}</p>}
      {data?.origin?.outsideIndia && (
        <p className="notice">{ml ? "നിങ്ങൾ ഇന്ത്യക്ക് പുറത്താണ്. ഈ ഫൈൻഡർ ഇന്ത്യയിൽ മാത്രം; കാണിക്കുന്നത്:" : "You seem to be outside India. This finder covers India only, so it is showing results around"} <b>{data.origin.label}</b>.</p>
      )}
      {data?.filters && Object.keys(data.filters).length > 0 && (
        <div className="filters-read">
          <span className="ai-badge">{data.filtersSource?.includes("ai") ? (ml ? "AI മനസ്സിലാക്കിയത്" : "AI understood") : (ml ? "മനസ്സിലാക്കിയത്" : "Understood")}</span>
          {Object.entries(data.filters).map(([k, v]) => <span key={k} className="evidence-chip">{k}: <b>{String(v)}</b></span>)}
        </div>
      )}

      {data?.risk && mode === "foryou" && !asked && (
        data.emergency ? <EmergencyBanner risk={data.risk} /> : <RiskCard risk={data.risk} showFinder={false} />
      )}
      {mode === "foryou" && !asked && data && !data.risk && (
        <p className="notice">{ml ? "നിങ്ങളുടെ രേഖയിൽ അപകട സൂചനകളില്ല. പതിവ് പരിശോധനയ്ക്ക് ജനറൽ ഫിസിഷ്യൻമാരെ കാണിക്കുന്നു." : "Nothing in your record needs urgent care, so these are General Physicians for a routine check-up."}</p>
      )}
      {data?.relaxed?.map((r, i) => <p key={i} className="notice">{r}</p>)}

      <div className="finder-grid">
        <div className="finder-map-col">
          <DoctorMap origin={data?.origin} results={data?.results || []} pickIds={pickIds} active={active} onSelect={setActive} />
          <p className="text-dim text-xs" style={{ marginTop: 6 }}>
            {ml ? "സാമ്പിൾ ഡാറ്റ: പേരുകളും നമ്പറുകളും റിവ്യൂകളും സാങ്കൽപ്പികം." : "Sample data: doctor names, clinics, phone numbers and reviews are fictional."}
          </p>
          {data?.bring?.length > 0 && (
            <div className="card bring-card">
              <h4>{ml ? "ഡോക്ടറുടെ അടുത്ത് കൊണ്ടുപോകേണ്ടത്" : "Take these to the doctor"}</h4>
              <ul>{data.bring.map((b, i) => <li key={i}>{(ml && b.textMl) || b.text}</li>)}</ul>
            </div>
          )}
        </div>
        <div ref={listRef} className="finder-list">
          {busy && !data && <Loading />}
          {error && <Loading error={error} onRetry={load} />}
          {data?.results?.length === 0 && <p className="notice">{ml ? "ഒന്നും കണ്ടില്ല. ഫിൽട്ടർ മാറ്റുക." : "No doctors matched. Try fewer filters."}</p>}
          {data?.results?.map((d) => (
            <DoctorCard key={d.id} d={d} pick={pickOf(d.id)} rank={pickIds.indexOf(d.id) + 1}
                        active={active === d.id} onSelect={setActive} ml={ml} />
          ))}
          {data?.nearbyGp?.length > 0 && (
            <>
              <h4 style={{ margin: "var(--sp-4) 0 var(--sp-2)" }}>{ml ? "അടുത്തുള്ള ജനറൽ ഫിസിഷ്യൻ ആദ്യം കാണാം" : "Closer option: see a General Physician first"}</h4>
              {data.nearbyGp.map((d) => <DoctorCard key={d.id} d={d} active={active === d.id} onSelect={setActive} ml={ml} />)}
            </>
          )}
        </div>
      </div>
    </>
  );
}
