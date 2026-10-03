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
import { Arrow, Chapter, RV } from "../design/primitives.jsx";

const SPECIALTIES = ["General Physician", "Cardiologist", "Diabetologist", "Nephrologist", "Pulmonologist",
  "Gastroenterologist", "Endocrinologist", "Haematologist", "Neurologist", "Orthopaedician", "Gynaecologist",
  "Paediatrician", "Dermatologist", "Ophthalmologist", "ENT specialist", "Psychiatrist", "Urologist", "Dentist", "Emergency"];
const INDIA = [[6.0, 68.0], [37.6, 97.5]];

const directions = (d) => `https://www.google.com/maps/dir/?api=1&destination=${d.lat},${d.lng}`;

// -- Map (supporting context, not the main thing) --
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
    // The map can mount before its container finishes animating open, so settle its size.
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

// -- "Why this match", built only from real doctor fields --
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

// -- One care match (clinical, not a restaurant card) --
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
    <article ref={ref} className={`mt-dm${active ? " active" : ""}${rank ? " picked" : ""}`} onClick={() => onSelect(d.id)}>
      <div className="mt-dm-id">
        {rank ? <span className="mt-dm-rank">{ml ? `ഏറ്റവും അനുയോജ്യം ${rank}` : `Best match ${rank}`}</span> : null}
        {d.emergency24x7 && <span className="mt-dm-er">24×7 {ml ? "അത്യാഹിതം" : "emergency"}</span>}
        <h4 className="mt-dm-name">{title}</h4>
        <div className="mt-dm-role">{role}</div>
      </div>

      <div className="mt-dm-why">
        <div className="mt-label">{ml ? "എന്തുകൊണ്ട് ഈ യോജിപ്പ്" : "Why this match"}</div>
        <ul>
          {why.map((w, i) => (<li key={i}><span className="tick" aria-hidden="true">✓</span>{w}</li>))}
        </ul>
      </div>

      <div className="mt-dm-side">
        <dl className="mt-dm-meta">
          <div><dt>{ml ? "ദൂരം" : "Distance"}</dt><dd>{d.distanceKm} km</dd></div>
          {d.feeInr ? <div><dt>{ml ? "ഫീസ്" : "Fee"}</dt><dd>₹{d.feeInr}</dd></div> : null}
          {d.rating ? <div><dt>{ml ? "റേറ്റിംഗ്" : "Rating"}</dt><dd>{d.rating.toFixed(1)} <small>({d.reviews})</small></dd></div> : null}
        </dl>
        <div className="mt-dm-actions" onClick={(e) => e.stopPropagation()}>
          <a className="mt-btn" href={`tel:${d.phone.replace(/\s/g, "")}`}>{ml ? "വിളിക്കുക" : "Call"} <Arrow /></a>
          <a className="mt-link" href={directions(d)} target="_blank" rel="noreferrer">{ml ? "വഴി കാണിക്കുക" : "Get directions"} <Arrow /></a>
        </div>
      </div>
    </article>
  );
}

// -- Page: Care Match --
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
  const seq = useRef(0); // only the newest request may update the page (fast chip clicks and the location lookup used to race)
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
    const mine = ++seq.current;
    setBusy(true);
    setError(null);
    try {
      const loc = { lat: geo?.lat, lng: geo?.lng, city: geo ? undefined : city || undefined };
      const res = mode === "foryou"
        ? await getDoctorRecommendation(loc)
        : await getNearbyDoctors({ ...loc, specialty: emergency ? undefined : specialty, emergency, openNow: onlyOpen,
                                   language: malayalam ? "Malayalam" : undefined });
      if (mine !== seq.current) return;
      setData(res);
      setAsked(false);
      setActive(res.picks?.[0]?.id || res.results?.[0]?.id || null);
    } catch (e) {
      if (mine === seq.current) setError(e.message);
    } finally {
      if (mine === seq.current) setBusy(false);
    }
  }, [geo, city, mode, specialty, emergency, onlyOpen, malayalam]);

  useEffect(() => { load(); }, [load]);

  const ask = async (e) => {
    e.preventDefault();
    if (q.trim().length < 2) return;
    const mine = ++seq.current;
    setBusy(true);
    setError(null);
    try {
      const res = await askDoctors(q.trim(), geo?.lat, geo?.lng);
      if (mine !== seq.current) return;
      setData(res);
      setAsked(true);
      setActive(res.picks?.[0]?.id || res.results?.[0]?.id || null);
    } catch (err) {
      if (mine === seq.current) setError(err.message);
    } finally {
      if (mine === seq.current) setBusy(false);
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
  const listRef = useReveal([data], { selector: ".mt-dm", y: 18, stagger: 0.06 });

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
    <div className="mt-page">
      {/* OPENING: the care context, and what MediThread suggests from it */}
      <Chapter tone="ground">
        <RV className="mt-opening">
          <div className="mt-label">{ml ? "കെയർ മാച്ച്" : "Care match"}</div>
          <h1 className="mt-display">{ml ? "ശരിയായ " : "Find the "}<em>{ml ? "പരിചരണം" : "right care"}</em>.</h1>
          <p className="mt-lede">{ml ? "നിങ്ങളുടെ ആരോഗ്യ കഥയുമായി ചേർത്ത്, വെറും ലൊക്കേഷൻ കൊണ്ടല്ല." : "Matched to your health story, not just to who is nearest."}</p>
        </RV>

        <RV as="form" className="mt-ask" onSubmit={ask}>
          <span className="sp" aria-hidden="true">✦</span>
          <input value={q} onChange={(e) => setQ(e.target.value)} maxLength={300}
                 placeholder={ml ? "ഉദാ: ഞായറാഴ്ച തുറക്കുന്ന കാക്കനാട്ടെ ഹൃദ്രോഗ ഡോക്ടർ" : "Describe it: a Malayalam-speaking heart doctor near Kakkanad, open Sunday"}
                 aria-label="Describe the care you need" />
          <button className="mt-btn" disabled={busy || q.trim().length < 2}>{ml ? "ചോദിക്കുക" : "Ask"} <Arrow /></button>
        </RV>

        {data?.risk && mode === "foryou" && !asked && data.emergency && <div className="mt-gap-top"><EmergencyBanner risk={data.risk} /></div>}

        <RV className="mt-flow mt-gap-top">
          <div className="you">
            <div className="mt-label">{ml ? "നിങ്ങൾ പരിചരണം തേടുന്നത്" : "You're looking for care for"}</div>
            {careContext.length > 0 ? (
              <div className="chips">{careContext.map((c, i) => <span key={i}>{c}</span>)}</div>
            ) : <p className="mt-quiet">{ml ? "പൊതുവായ പരിശോധന." : "A general check-up."}</p>}
          </div>
          <div className="thread" aria-hidden="true"><i /><b /></div>
          <div className="rec">
            <div className="mt-label">{ml ? "MediThread നിർദ്ദേശിക്കുന്നു" : "MediThread suggests"}</div>
            <div className="spec">{recSpecialty}</div>
            <p className="why">{reason}</p>
            {data?.risk && !data.emergency && mode === "foryou" && !asked && (
              <div className="mt-flow-risk"><RiskCard risk={data.risk} showFinder={false} /></div>
            )}
          </div>
        </RV>

        <div className="mt-refine mt-gap-top">
          <div className="mt-seg" role="group" aria-label="Mode">
            <button type="button" className={mode === "foryou" && !asked ? "on" : ""} aria-pressed={mode === "foryou" && !asked} onClick={() => setSpecialty("")}>{ml ? "എന്റെ കഥയ്ക്കായി" : "For my story"}</button>
            <button type="button" className={emergency && !asked ? "on er" : "er"} aria-pressed={emergency && !asked} onClick={() => setSpecialty("Emergency")}>{ml ? "അത്യാഹിതം" : "Emergency"}</button>
            {mode === "search" && (
              <>
                <button type="button" className={onlyOpen ? "on" : ""} aria-pressed={onlyOpen} onClick={() => setOnlyOpen((x) => !x)}>{ml ? "ഇപ്പോൾ തുറന്നത്" : "Open now"}</button>
                <button type="button" className={malayalam ? "on" : ""} aria-pressed={malayalam} onClick={() => setMalayalam((x) => !x)}>Malayalam</button>
              </>
            )}
          </div>
          <div className="mt-refine-sel">
            <select value={emergency ? "" : specialty} onChange={(e) => setSpecialty(e.target.value)} aria-label="Specialty">
              <option value="">{ml ? "സ്പെഷ്യാലിറ്റി…" : "Any specialty…"}</option>
              {SPECIALTIES.filter((s) => s !== "Emergency").map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
            <select value={geo ? "__geo" : city} onChange={(e) => { setGeo(null); setCity(e.target.value); }} aria-label="Town">
              {geo && <option value="__geo">{ml ? "എന്റെ ലൊക്കേഷൻ" : "My location"}</option>}
              <option value="">{ml ? "നഗരം…" : "Town…"}</option>
              {cities.map((c) => <option key={c.city} value={c.city}>{c.city}{c.state !== "Kerala" ? `, ${c.state}` : ""}</option>)}
            </select>
            <button type="button" className="mt-link" onClick={locate}>{ml ? "എന്റെ ലൊക്കേഷൻ" : "Use my location"} <Arrow /></button>
          </div>
        </div>
        {geoMsg && <p className="mt-small">{geoMsg}</p>}
        {data?.origin?.outsideIndia && (
          <p className="notice">{ml ? "നിങ്ങൾ ഇന്ത്യക്ക് പുറത്താണ്. ഈ ഫൈൻഡർ ഇന്ത്യയിൽ മാത്രം; കാണിക്കുന്നത്:" : "You seem to be outside India. This finder covers India only, so it is showing results around"} <b>{data.origin.label}</b>.</p>
        )}
        {data?.relaxed?.map((r, i) => <p key={i} className="notice">{r}</p>)}
      </Chapter>

      {/* 01: the doctors, led by why they match */}
      <Chapter tone="soft" no="01" kicker={recSpecialty} title={ml ? "നിങ്ങൾക്കായുള്ള ഡോക്ടർമാർ" : "Doctors matched to you"} last={!(data?.results?.length > 0)}
        aside={data?.results?.length > 0 ? (
          <button type="button" className="mt-link" onClick={() => setShowMap((x) => !x)} aria-expanded={showMap}>
            {showMap ? (ml ? "മാപ്പ് മറയ്ക്കുക" : "Hide map") : (ml ? "മാപ്പിൽ കാണുക" : "Show on map")} <Arrow />
          </button>) : null}>
        <div ref={listRef} className="mt-dm-list">
          {busy && !data && <Loading />}
          {error && <Loading error={error} onRetry={load} />}
          {data?.results?.length === 0 && <p className="notice">{ml ? "ഒന്നും കണ്ടില്ല. ഫിൽട്ടർ മാറ്റുക." : "No doctors matched. Try fewer filters."}</p>}
          {data?.results?.map((d) => (
            <CareDoctor key={d.id} d={d} rank={rankOf(d.id)} active={active === d.id} onSelect={setActive} ctx={ctx} />
          ))}
          {data?.nearbyGp?.length > 0 && (
            <>
              <div className="mt-label mt-col-label">{ml ? "അടുത്തുള്ള ഒരു ഓപ്ഷൻ" : "A closer option first"}</div>
              {data.nearbyGp.map((d) => <CareDoctor key={d.id} d={d} active={active === d.id} onSelect={setActive} ctx={ctx} />)}
            </>
          )}
        </div>

        {/* The map is supporting context, shown on request */}
        {showMap && data?.results?.length > 0 && (
          <div className="mt-map animate-in-fast">
            <DoctorMap origin={data?.origin} results={data?.results || []} pickIds={pickIds} active={active} onSelect={setActive} />
            <p className="mt-small">{ml ? "സാമ്പിൾ ഡാറ്റ: പേരുകളും നമ്പറുകളും റിവ്യൂകളും സാങ്കൽപ്പികം." : "Sample data: doctor names, clinics, phone numbers and reviews are fictional."}</p>
          </div>
        )}
      </Chapter>

      {/* 02: the care path, back into the MediThread story */}
      {data?.results?.length > 0 && (
        <Chapter tone="warm" no="02" kicker={ml ? "അടുത്ത ഘട്ടം" : "The care path"} title={ml ? "ഡോക്ടർ നിങ്ങളുടെ കഥ കാണട്ടെ" : "Let the doctor see your story"} last>
          <RV as="ol" className="mt-path" stagger={0.1} selector=":scope > li">
            {[
              ml ? "ആരോഗ്യ ഡാറ്റ" : "Your health data",
              ml ? "MediThread മനസ്സിലാക്കുന്നു" : "MediThread's understanding",
              ml ? "കെയർ മാച്ച്" : "Care match",
              ml ? "ഡോക്ടറെ തിരഞ്ഞെടുക്കുക" : "Choose a doctor",
              ml ? "കഥ പങ്കിടുക" : "Share your story",
            ].map((st, i, arr) => (
              <li key={i} className={i === arr.length - 1 ? "last" : ""}><span className="n" aria-hidden="true">{i + 1}</span><span>{st}</span></li>
            ))}
          </RV>
          <div className="mt-grid mt-gap-top">
            {data?.bring?.length > 0 && (
              <RV className="c-7 mt-bring">
                <div className="mt-label">{ml ? "ഡോക്ടറുടെ അടുത്ത് കൊണ്ടുപോകേണ്ടത്" : "Take these to the visit"}</div>
                <ul>{data.bring.map((b, i) => <li key={i}>{(ml && b.textMl) || b.text}</li>)}</ul>
              </RV>
            )}
            <RV className="c-5"><Link className="mt-btn" to="/sharing">{ml ? "ഡോക്ടറുമായി പങ്കിടുക" : "Share with a doctor"} <Arrow /></Link></RV>
          </div>
        </Chapter>
      )}
    </div>
  );
}
