"""Nearby doctor finder over the FICTIONAL sample directory in BackEnd/data/doctors.json.

Python does the ranking (distance, review-weighted rating, specialty fit, open now,
language, fee). India only: a location outside India's bounding box falls back to
the patient's city, then Kochi.

The AI layer (ai/doctor_ai.py) only explains and parses; it never invents a doctor.
"""
from __future__ import annotations

import json
import math
import re
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

DATA = Path(__file__).resolve().parents[1] / "data" / "doctors.json"
IST = ZoneInfo("Asia/Kolkata")

# India's bounding box (mainland + islands, generous). Anything outside is "not in India".
INDIA_BOUNDS = {"south": 6.0, "north": 37.6, "west": 68.0, "east": 97.5}
DEFAULT_ORIGIN = {"lat": 9.9312, "lng": 76.2673, "label": "Kochi", "source": "default"}
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
DAY_WORDS = {"monday": "mon", "tuesday": "tue", "wednesday": "wed", "thursday": "thu", "friday": "fri",
             "saturday": "sat", "sunday": "sun", "today": "today", "tonight": "today", "now": "today"}

SPECIALTIES = ["General Physician", "Cardiologist", "Diabetologist", "Nephrologist", "Pulmonologist",
               "Gastroenterologist", "Endocrinologist", "Haematologist", "Neurologist", "Orthopaedician",
               "Gynaecologist", "Paediatrician", "Dermatologist", "Ophthalmologist", "ENT specialist",
               "Psychiatrist", "Urologist", "Dentist", "Emergency"]
LANGUAGES = ["Malayalam", "English", "Hindi", "Tamil", "Kannada", "Telugu", "Marathi", "Bengali", "Arabic"]

# Free-text words -> specialty. Longest match wins.
SPECIALTY_WORDS = {
    "heart": "Cardiologist", "cardio": "Cardiologist", "cardiac": "Cardiologist", "bp": "Cardiologist",
    "blood pressure": "Cardiologist", "chest pain": "Emergency",
    "sugar": "Diabetologist", "diabet": "Diabetologist", "hba1c": "Diabetologist",
    "kidney": "Nephrologist", "creatinine": "Nephrologist", "nephro": "Nephrologist", "dialysis": "Nephrologist",
    "lung": "Pulmonologist", "breath": "Pulmonologist", "asthma": "Pulmonologist", "chest": "Pulmonologist", "oxygen": "Pulmonologist",
    "stomach": "Gastroenterologist", "liver": "Gastroenterologist", "gastro": "Gastroenterologist", "acid": "Gastroenterologist",
    "thyroid": "Endocrinologist", "hormone": "Endocrinologist", "endocrin": "Endocrinologist",
    "blood count": "Haematologist", "anaemia": "Haematologist", "anemia": "Haematologist", "platelet": "Haematologist",
    "brain": "Neurologist", "nerve": "Neurologist", "stroke": "Emergency", "seizure": "Neurologist", "neuro": "Neurologist",
    "bone": "Orthopaedician", "joint": "Orthopaedician", "knee": "Orthopaedician", "back pain": "Orthopaedician", "ortho": "Orthopaedician",
    "women": "Gynaecologist", "pregnan": "Gynaecologist", "gyna": "Gynaecologist", "period": "Gynaecologist",
    "child": "Paediatrician", "baby": "Paediatrician", "kid": "Paediatrician", "paediatric": "Paediatrician", "pediatric": "Paediatrician",
    "skin": "Dermatologist", "rash": "Dermatologist", "derma": "Dermatologist",
    "eye": "Ophthalmologist", "vision": "Ophthalmologist", "ear": "ENT specialist", "nose": "ENT specialist", "throat": "ENT specialist",
    "ent": "ENT specialist", "mind": "Psychiatrist", "stress": "Psychiatrist", "depress": "Psychiatrist", "anxiety": "Psychiatrist",
    "sleep": "Psychiatrist", "urine": "Urologist", "prostate": "Urologist", "uro": "Urologist",
    "tooth": "Dentist", "teeth": "Dentist", "dental": "Dentist", "gum": "Dentist",
    "general": "General Physician", "physician": "General Physician", "family doctor": "General Physician", "fever": "General Physician",
    "emergency": "Emergency", "casualty": "Emergency", "urgent": "Emergency", "24x7": "Emergency", "24 hour": "Emergency",
    "icu": "Emergency",
}
LANG_WORDS = {"malayalam": "Malayalam", "english": "English", "hindi": "Hindi", "tamil": "Tamil", "kannada": "Kannada",
              "telugu": "Telugu", "marathi": "Marathi", "bengali": "Bengali", "arabic": "Arabic"}


@lru_cache(maxsize=1)
def directory() -> list[dict]:
    return json.loads(DATA.read_text())["doctors"]


@lru_cache(maxsize=1)
def cities() -> list[dict]:
    """Unique towns in the directory with their centre, for the city picker and geocoding."""
    acc: dict[str, dict] = {}
    for d in directory():
        c = acc.setdefault(d["city"], {"city": d["city"], "district": d["district"], "state": d["state"],
                                        "lat": 0.0, "lng": 0.0, "n": 0})
        c["lat"] += d["lat"]
        c["lng"] += d["lng"]
        c["n"] += 1
    out = []
    for c in acc.values():
        out.append({"city": c["city"], "district": c["district"], "state": c["state"],
                    "lat": round(c["lat"] / c["n"], 4), "lng": round(c["lng"] / c["n"], 4), "doctors": c["n"]})
    out.sort(key=lambda c: (c["state"] != "Kerala", c["city"]))
    return out


def in_india(lat: float | None, lng: float | None) -> bool:
    if lat is None or lng is None:
        return False
    b = INDIA_BOUNDS
    return b["south"] <= lat <= b["north"] and b["west"] <= lng <= b["east"]


def city_coords(name: str | None) -> dict | None:
    key = (name or "").strip().lower()
    if not key:
        return None
    for c in cities():
        if c["city"].lower() == key:
            return c
    in_district = [c for c in cities() if c["district"].lower() == key]
    if in_district:
        return max(in_district, key=lambda c: c["doctors"])
    for c in cities():
        if key in c["city"].lower() or c["city"].lower() in key:
            return c
    return None


def resolve_origin(lat: float | None, lng: float | None, city: str | None,
                   patient_lat: float | None = None, patient_lng: float | None = None,
                   patient_city: str | None = None) -> dict:
    """Where to measure distance from. Browser location > chosen city > profile > Kochi. India only."""
    outside = lat is not None and lng is not None and not in_india(lat, lng)
    if lat is not None and lng is not None and in_india(lat, lng):
        return {"lat": lat, "lng": lng, "label": "Your location", "source": "device", "outsideIndia": False}
    for name, source in ((city, "city"), (patient_city, "profile")):
        c = city_coords(name)
        if c:
            return {"lat": c["lat"], "lng": c["lng"], "label": c["city"], "source": source, "outsideIndia": outside}
    if in_india(patient_lat, patient_lng):
        return {"lat": patient_lat, "lng": patient_lng, "label": "Saved location", "source": "profile", "outsideIndia": outside}
    return {**DEFAULT_ORIGIN, "outsideIndia": outside}


def km(a_lat: float, a_lng: float, b_lat: float, b_lng: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp, dl = p2 - p1, math.radians(b_lng - a_lng)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def _mins(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def open_on(doc: dict, day: str, at: datetime | None = None) -> bool:
    """Open on that day (any hours), or open right now when `at` is given."""
    span = (doc.get("hours") or {}).get(day)
    if not span:
        return False
    if at is None:
        return True
    start, end = span.split("-")
    now = at.hour * 60 + at.minute
    return _mins(start) <= now <= _mins(end)


def closes_at(doc: dict, now: datetime) -> str | None:
    span = (doc.get("hours") or {}).get(DAYS[now.weekday()])
    if not span or doc.get("emergency24x7"):
        return None
    return span.split("-")[1]


def bayes_rating(rating: float, reviews: int, prior: float = 4.0, weight: int = 25) -> float:
    """Rating pulled toward 4.0 when there are few reviews, so 5.0 from 6 reviews does not beat 4.6 from 900."""
    return (rating * reviews + prior * weight) / (reviews + weight)


def matches_specialty(doc: dict, specialty: str | None) -> int:
    """2 = primary specialty, 1 = also offered, 0 = no."""
    if not specialty:
        return 1
    if doc["specialty"] == specialty:
        return 2
    if specialty in doc.get("specialties", []):
        return 1
    if specialty == "Emergency" and doc.get("emergency24x7"):
        return 2
    return 0


def search(origin: dict, specialty: str | None = None, language: str | None = None, day: str | None = None,
           open_now: bool = False, emergency: bool = False, max_km: float | None = None, max_fee: int | None = None,
           min_rating: float | None = None, teleconsult: bool = False, limit: int = 12,
           now: datetime | None = None) -> dict:
    """Rank the directory. Returns {results, specialty, relaxed} where relaxed explains any widened filter."""
    now = now or datetime.now(IST)
    today = DAYS[now.weekday()]
    want_day = today if day in (None, "today") else day
    if emergency:
        specialty = "Emergency"
    relaxed: list[str] = []

    def rank(spec: str | None, radius: float | None) -> list[dict]:
        out = []
        for d in directory():
            sm = matches_specialty(d, spec)
            if spec and sm == 0:
                continue
            dist = km(origin["lat"], origin["lng"], d["lat"], d["lng"])
            if radius is not None and dist > radius:
                continue
            if language and language not in d["languages"]:
                continue
            if max_fee is not None and d["feeInr"] > max_fee:
                continue
            if min_rating is not None and d["rating"] < min_rating:
                continue
            if teleconsult and not d.get("teleconsult"):
                continue
            if day and day != "today" and not open_on(d, want_day):
                continue
            is_open = d.get("emergency24x7") or open_on(d, today, now)
            if open_now and not is_open:
                continue
            br = bayes_rating(d["rating"], d["reviews"])
            # Distance matters most in an emergency; otherwise balance it with quality.
            dist_w = 55 if spec == "Emergency" else 34
            parts = {
                "distance": round(dist_w * math.exp(-dist / (6 if spec == "Emergency" else 12)), 1),
                "rating": round(max(0.0, (br - 3.5) / 1.5) * 30, 1),
                "specialty": {2: 24, 1: 10, 0: 0}[sm] if spec else 8,
                "openNow": 8 if is_open else 0,
                "language": 5 if (language or "Malayalam") in d["languages"] else 0,
            }
            score = round(sum(parts.values()), 1)
            # At a hospital matched through a department, show the department, not the head doctor's specialty.
            dept = spec if (spec and d["type"] == "hospital" and d["specialty"] != spec
                            and (sm == 1 or spec == "Emergency")) else None
            out.append({**d, "department": dept, "distanceKm": round(dist, 1), "openNow": bool(is_open), "closesAt": closes_at(d, now),
                        "bayesRating": round(br, 2), "score": score, "scoreParts": parts})
        if spec == "Emergency":
            out.sort(key=lambda d: d["distanceKm"])  # in an emergency, nearest first, always
        else:
            out.sort(key=lambda d: (-d["score"], d["distanceKm"]))
        return out

    # Search close first, then widen: a great doctor 180 km away should not beat a good one 5 km away.
    # Inside the first radius we rank by score; places found by widening are added after, nearest first.
    tiers = [max_km] if max_km is not None else [40.0, 150.0, None]
    results = rank(specialty, tiers[0])
    for radius in tiers[1:]:
        if len(results) >= 3:
            break
        seen = {d["id"] for d in results}
        extra = sorted((d for d in rank(specialty, radius) if d["id"] not in seen), key=lambda d: d["distanceKm"])
        results += extra[: max(0, 6 - len(results))]
    if max_km is not None and len(results) < 3:
        seen = {d["id"] for d in results}
        extra = sorted((d for d in rank(specialty, None) if d["id"] not in seen), key=lambda d: d["distanceKm"])
        results += extra[: max(0, 6 - len(results))]
    if results and (max_km or 40.0) < max(d["distanceKm"] for d in results):
        n_near = sum(d["distanceKm"] <= (max_km or 40.0) for d in results)
        relaxed.append(f"Only {n_near} match{'es' if n_near != 1 else ''} within {max_km or 40.0:g} km, so farther places are listed too."
                       if n_near else "No match nearby, so the closest ones farther away are shown.")
    if not results and specialty and specialty not in ("General Physician", "Emergency"):
        relaxed.append(f"No {specialty} matched, so General Physicians are shown instead.")
        specialty = "General Physician"
        results = rank(specialty, max_km)
    # The nearest specialist is far: offer nearby General Physicians to be seen first.
    nearby_gp: list[dict] = []
    if results and specialty not in (None, "General Physician", "Emergency") and min(d["distanceKm"] for d in results) > 60:
        nearby_gp = rank("General Physician", 40.0)[:3]
    return {"results": results[:limit], "specialty": specialty, "relaxed": relaxed, "nearbyGp": nearby_gp}


def parse_query(q: str) -> dict:
    """Python reading of a free-text search. The AI parser (ai/doctor_ai.py) can fill in what this misses."""
    t = " " + (q or "").lower() + " "
    out: dict = {}
    for w in sorted(SPECIALTY_WORDS, key=len, reverse=True):
        # Short words must be whole words ("ear" is not in "early"); longer ones are stems ("diabet").
        tail = r"(?![a-z])" if len(w) <= 4 else ""
        if re.search(rf"(?<![a-z]){re.escape(w)}{tail}", t):
            out["specialty"] = SPECIALTY_WORDS[w]
            break
    for spec in SPECIALTIES:
        if spec.lower() in t:
            out["specialty"] = spec
    for w, lang in LANG_WORDS.items():
        if w in t:
            out["language"] = lang
            break
    for w, day in DAY_WORDS.items():
        if re.search(rf"\b{w}\b", t):
            out["day"] = day
            break
    if re.search(r"\bopen (now|today)\b|\bright now\b", t):
        out["openNow"] = True
    m = re.search(r"(?:under|below|less than|max|within)\s*(?:rs\.?|₹|inr)?\s*(\d{2,5})\s*(?:rs|rupees|₹|inr)", t) or \
        re.search(r"(?:under|below|less than)\s*(?:rs\.?|₹|inr)\s*(\d{2,5})", t)
    if m:
        out["maxFee"] = int(m.group(1))
    m = re.search(r"(?:within|under|less than)\s*(\d{1,3})\s*(?:km|kms|kilomet)", t)
    if m:
        out["maxKm"] = float(m.group(1))
    m = re.search(r"(\d(?:\.\d)?)\s*(?:\+|stars?|and above)", t)
    if m and 1 <= float(m.group(1)) <= 5:
        out["minRating"] = float(m.group(1))
    if re.search(r"\b(online|video|tele)", t):
        out["teleconsult"] = True
    for c in cities():
        if re.search(rf"\b{re.escape(c['city'].lower())}\b", t):
            out["city"] = c["city"]
            break
    if out.get("specialty") == "Emergency":
        out["emergency"] = True
    return out
