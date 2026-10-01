"""Drug-safety logic. Named jev_client.py to match the brief's filename, but
there is no Jev / no paid API. Everything is plain dicts plus an optional
OpenFDA fallback.
"""
from __future__ import annotations

import httpx

from app.labs import lab_range, lab_status

# ---------- Common Indian brand names → generic ----------
# Keys are lowercase; look up by any token in the brand name.
BRAND_TO_GENERIC: dict[str, str] = {
    # Diabetes
    "glycomet": "metformin",
    "glucophage": "metformin",
    "gluformin": "metformin",
    "carbophage": "metformin",
    "metformin": "metformin",
    # Pain / fever
    "dolo": "paracetamol",
    "crocin": "paracetamol",
    "calpol": "paracetamol",
    "paracetamol": "paracetamol",
    "combiflam": "ibuprofen",   # ibuprofen + paracetamol combo; flag ibuprofen
    "brufen": "ibuprofen",
    "ibugesic": "ibuprofen",
    "voveran": "diclofenac",
    "diclofenac": "diclofenac",
    "ecosprin": "aspirin",
    "sprinter": "aspirin",
    "aspirin": "aspirin",
    # BP / heart
    "amlokind": "amlodipine",
    "amlogard": "amlodipine",
    "amlodac": "amlodipine",
    "amlodipine": "amlodipine",
    "telma": "telmisartan",
    "telmikind": "telmisartan",
    "micardis": "telmisartan",
    "telmisartan": "telmisartan",
    "metocard": "metoprolol",
    "betacard": "metoprolol",
    "metoprolol": "metoprolol",
    "zestril": "lisinopril",
    "lisinopril": "lisinopril",
    "lasix": "furosemide",
    "furosemide": "furosemide",
    # Cholesterol
    "atorva": "atorvastatin",
    "atorlip": "atorvastatin",
    "lipikind": "atorvastatin",
    "atorvastatin": "atorvastatin",
    "rosuvas": "rosuvastatin",
    "rosuvastatin": "rosuvastatin",
    "zocor": "simvastatin",
    "simvastatin": "simvastatin",
    # Antibiotics
    "clavam": "amoxicillin",
    "augmentin": "amoxicillin",
    "clamp": "amoxicillin",
    "amoxicillin": "amoxicillin",
    "ampicillin": "ampicillin",
    "mox": "amoxicillin",
    "taxim-o": "cefixime",
    "topcef": "cefixime",
    "cefixime": "cefixime",
    "clariwin": "clarithromycin",
    "claribid": "clarithromycin",
    "clarithro": "clarithromycin",
    "clarithromycin": "clarithromycin",
    "azee": "azithromycin",
    "azithral": "azithromycin",
    "azithromycin": "azithromycin",
    "erythromycin": "erythromycin",
    "ciplox": "ciprofloxacin",
    "cifran": "ciprofloxacin",
    "ciprofloxacin": "ciprofloxacin",
    "metrogyl": "metronidazole",
    "flagyl": "metronidazole",
    "metronidazole": "metronidazole",
    # Stomach / acid
    "pan-d": "pantoprazole",
    "pantop": "pantoprazole",
    "pantocid": "pantoprazole",
    "pantoprazole": "pantoprazole",
    "omee": "omeprazole",
    "omez": "omeprazole",
    "omeprazole": "omeprazole",
    # Allergy / cough
    "allegra": "fexofenadine",
    "cetzine": "cetirizine",
    "cetirizine": "cetirizine",
    "montek-lc": "montelukast",
    "montelukast": "montelukast",
    "ascoril": "cough-syrup",
    "benadryl": "diphenhydramine",
    # Thyroid / steroid
    "thyronorm": "levothyroxine",
    "eltroxin": "levothyroxine",
    "levothyroxine": "levothyroxine",
    "wysolone": "prednisolone",
    "prednisolone": "prednisolone",
    # Anticoagulant
    "warfarin": "warfarin",
    "warf": "warfarin",
    "acitrom": "acenocoumarol",
    "clopilet": "clopidogrel",
    "clopidogrel": "clopidogrel",
    # Antifungal / antivirals
    "fluconazole": "fluconazole",
    # Heart rhythm
    "cordarone": "amiodarone",
    "amiodarone": "amiodarone",
    "digoxin": "digoxin",
    # Neurology
    "tegretol": "carbamazepine",
    "carbamazepine": "carbamazepine",
    "phenytoin": "phenytoin",
    "eptoin": "phenytoin",
    "lithosun": "lithium",
    "lithium": "lithium",
    # Pain / tramadol
    "tramadol": "tramadol",
    # SSRIs
    "fluoxetine": "fluoxetine",
    "sertraline": "sertraline",
    "escitalopram": "escitalopram",
    # Nitrates / PDE5
    "sorbitrate": "nitroglycerin",
    "nitroglycerin": "nitroglycerin",
    "sildenafil": "sildenafil",
    "viagra": "sildenafil",
    # Insulin brands (treat as "insulin")
    "mixtard": "insulin",
    "humalog": "insulin",
    "lantus": "insulin",
    "insulin": "insulin",
    # Sulfa / methotrexate
    "septran": "sulfamethoxazole",
    "bactrim": "sulfamethoxazole",
    "sulfamethoxazole": "sulfamethoxazole",
    "trimethoprim": "trimethoprim",
    "methotrexate": "methotrexate",
    "spironolactone": "spironolactone",
    "aldactone": "spironolactone",
    "colchicine": "colchicine",
    "verapamil": "verapamil",
    "diltiazem": "diltiazem",
    "atenolol": "atenolol",
    "propranolol": "propranolol",
}

# ---------- Dangerous pairs ----------
# Each entry: ((drug_a_generic, drug_b_generic), plain-language warning).
_PAIRS: list[tuple[tuple[str, str], str]] = [
    (("clarithromycin", "atorvastatin"),
     "Clarithromycin raises atorvastatin levels in blood, which can cause serious muscle damage. Doctor should pause atorvastatin while on clarithromycin."),
    (("clarithromycin", "simvastatin"),
     "Clarithromycin greatly raises simvastatin levels, risking muscle damage. Avoid taking both together."),
    (("erythromycin", "simvastatin"),
     "Erythromycin raises simvastatin levels, risking muscle damage. Avoid taking both together."),
    (("clarithromycin", "colchicine"),
     "Clarithromycin raises colchicine levels, which can be severely toxic."),
    (("clarithromycin", "digoxin"),
     "Clarithromycin raises digoxin levels and can cause heart rhythm problems."),
    (("warfarin", "aspirin"),
     "Warfarin and aspirin together greatly raise bleeding risk. Only take with doctor's clear instruction."),
    (("warfarin", "ibuprofen"),
     "Ibuprofen with warfarin raises bleeding risk and can harm the kidneys."),
    (("warfarin", "clarithromycin"),
     "Clarithromycin raises warfarin levels and bleeding risk."),
    (("warfarin", "ciprofloxacin"),
     "Ciprofloxacin raises warfarin levels and bleeding risk."),
    (("warfarin", "fluconazole"),
     "Fluconazole raises warfarin levels and bleeding risk."),
    (("warfarin", "amiodarone"),
     "Amiodarone raises warfarin levels and bleeding risk."),
    (("warfarin", "carbamazepine"),
     "Carbamazepine lowers warfarin levels and the blood thinning may not work."),
    (("warfarin", "phenytoin"),
     "Phenytoin and warfarin interact in both directions. INR must be watched closely."),
    (("digoxin", "verapamil"),
     "Verapamil raises digoxin levels; risk of slow heart rate and nausea."),
    (("digoxin", "amiodarone"),
     "Amiodarone raises digoxin levels; risk of toxicity."),
    (("amiodarone", "simvastatin"),
     "Amiodarone raises simvastatin levels, risking muscle damage."),
    (("methotrexate", "ibuprofen"),
     "NSAIDs like ibuprofen raise methotrexate levels and risk serious toxicity."),
    (("methotrexate", "diclofenac"),
     "NSAIDs like diclofenac raise methotrexate levels and risk serious toxicity."),
    (("methotrexate", "trimethoprim"),
     "Trimethoprim with methotrexate greatly raises risk of bone marrow suppression."),
    (("methotrexate", "sulfamethoxazole"),
     "Co-trimoxazole with methotrexate greatly raises risk of bone marrow suppression."),
    (("lithium", "ibuprofen"),
     "Ibuprofen raises lithium levels and risks toxicity."),
    (("lithium", "diclofenac"),
     "NSAIDs raise lithium levels and risk toxicity."),
    (("tramadol", "fluoxetine"),
     "Tramadol with SSRIs can cause serotonin syndrome (fever, confusion, fast heart rate)."),
    (("tramadol", "sertraline"),
     "Tramadol with SSRIs can cause serotonin syndrome."),
    (("tramadol", "escitalopram"),
     "Tramadol with SSRIs can cause serotonin syndrome."),
    (("fluoxetine", "aspirin"),
     "SSRIs with aspirin raise stomach bleeding risk."),
    (("sertraline", "ibuprofen"),
     "SSRIs with NSAIDs raise stomach bleeding risk."),
    (("verapamil", "metoprolol"),
     "Verapamil with a beta-blocker can slow the heart dangerously."),
    (("diltiazem", "metoprolol"),
     "Diltiazem with a beta-blocker can slow the heart dangerously."),
    (("sildenafil", "nitroglycerin"),
     "Sildenafil with nitrates can cause a dangerous drop in blood pressure."),
    (("clopidogrel", "omeprazole"),
     "Omeprazole may reduce clopidogrel's blood-thinning effect."),
    (("spironolactone", "lisinopril"),
     "Spironolactone with an ACE inhibitor can raise potassium to dangerous levels."),
    (("ibuprofen", "lisinopril"),
     "Ibuprofen with an ACE inhibitor can harm the kidneys and reduce blood pressure control."),
    (("fluconazole", "simvastatin"),
     "Fluconazole raises simvastatin levels, risking muscle damage."),
]
PAIRS: dict[tuple[str, str], str] = {}
for (a, b), msg in _PAIRS:
    PAIRS[tuple(sorted((a, b)))] = msg

# ---------- Allergy families ----------
ALLERGY_FAMILIES: dict[str, set[str]] = {
    "sulfa": {"sulfamethoxazole", "sulfadiazine", "sulfasalazine", "trimethoprim"},
    "penicillin": {"penicillin", "amoxicillin", "ampicillin", "piperacillin", "cloxacillin"},
    "nsaid": {"ibuprofen", "diclofenac", "naproxen", "aspirin"},
    "aspirin": {"aspirin"},
    "statin": {"atorvastatin", "simvastatin", "rosuvastatin"},
}

# ---------- helpers ----------

def to_generic(name: str) -> str | None:
    """Return the generic drug name for a brand or generic string, or None."""
    if not name:
        return None
    key = name.strip().lower()
    # Try full lowercase first (handles "glycomet 500" prefix stripping below).
    if key in BRAND_TO_GENERIC:
        return BRAND_TO_GENERIC[key]
    # Split on spaces, dashes, and digits-boundary; try each token.
    import re
    for tok in re.split(r"[\s\-/]+", key):
        tok = re.sub(r"\d.*$", "", tok)  # strip "500" etc.
        if tok and tok in BRAND_TO_GENERIC:
            return BRAND_TO_GENERIC[tok]
    return None


def _openfda_check(a: str, b: str) -> str | None:
    """Optional OpenFDA fallback. Opt-in via OPENFDA_ENABLE=1.

    OpenFDA's event database has co-reports for almost any two common
    drugs, so a raw hit tells us nothing. We only surface pairs with a
    very large number of co-reports relative to each drug alone.
    """
    import os
    if os.getenv("OPENFDA_ENABLE") != "1":
        return None
    try:
        def _count(expr: str) -> int:
            with httpx.Client(timeout=3.0) as cx:
                r = cx.get(f"https://api.fda.gov/drug/event.json?search={expr}&limit=1")
            if r.status_code != 200:
                return 0
            try:
                return int(r.json().get("meta", {}).get("results", {}).get("total", 0))
            except Exception:
                return 0

        both = _count(f'(patient.drug.medicinalproduct:"{a}"+AND+patient.drug.medicinalproduct:"{b}")')
        if both < 500:
            return None
        a_total = _count(f'patient.drug.medicinalproduct:"{a}"') or 1
        if both / a_total < 0.05:
            return None
        return (
            f"OpenFDA shows a large number of adverse-event reports when {a} and {b} are taken together. "
            "Please check with your doctor before taking both."
        )
    except Exception:
        return None


def check_pair(a: str, b: str) -> str | None:
    """Return a plain-language warning if the pair is dangerous, else None."""
    key = tuple(sorted((a, b)))
    hit = PAIRS.get(key)
    if hit:
        return hit
    return _openfda_check(a, b)


def allergy_hit(med_generic: str, allergies: list[str]) -> str | None:
    """Return the matched family name if the medicine conflicts with an allergy."""
    for allergy in allergies or []:
        key = allergy.strip().lower()
        for family, members in ALLERGY_FAMILIES.items():
            if family in key and med_generic in members:
                return family
    return None


# ---------- entry point used by the pipeline ----------

def analyse(
    *,
    patient_name: str,
    patient_allergies: list[str],
    existing_medicines: list[dict],  # [{name, generic}] from DB
    new_medicines: list[dict],       # [{name, generic?, dose, schedule}] from the extractor
    observations: list[dict],        # [{name, code?, value, unit, range?}]
) -> dict:
    """Return {alerts, medications, observations, worst_status}.

    - alerts: list of plain dicts shaped like the Alert serializer (plus kind).
    - medications: new_medicines enriched with resolved `generic` and `purpose`.
    - observations: enriched with `status` (good/watch/alert) and `range`.
    - worst_status: overall status of the record.
    """
    alerts: list[dict] = []

    # Resolve generics for the new meds.
    for m in new_medicines:
        if not m.get("generic"):
            m["generic"] = to_generic(m.get("name", "")) or (m.get("name") or "").strip().lower()

    existing = [dict(e, generic=(e.get("generic") or to_generic(e.get("name", "")) or "").lower()) for e in existing_medicines]

    def _mk_alert(severity, kind, title, message):
        alerts.append({"severity": severity, "kind": kind, "title": title, "message": message})

    # Duplicate check: new drug's generic matches an existing active med's generic.
    for nm in new_medicines:
        g = nm["generic"]
        if not g:
            continue
        dup = next((e for e in existing if e["generic"] == g), None)
        if dup is not None:
            _mk_alert(
                "high", "duplicate",
                f"{nm['name']} duplicates {dup['name']}",
                f"{nm['name']} is the same medicine as {dup['name']} you are already taking (both are {g}). "
                "Taking both doubles the dose. Ask your doctor which one to continue.",
            )

    # Allergy check against new meds.
    for nm in new_medicines:
        hit = allergy_hit(nm["generic"], patient_allergies)
        if hit:
            _mk_alert(
                "high", "allergy",
                f"Possible allergy: {nm['name']}",
                f"{nm['name']} belongs to the {hit} family, which you are listed as allergic to. "
                "Tell the doctor before taking the first dose.",
            )

    # Clash check: each new med against every existing med and every other new med.
    checked: set[tuple[str, str]] = set()
    universe = [{"name": e["name"], "generic": e["generic"]} for e in existing] + \
               [{"name": nm["name"], "generic": nm["generic"]} for nm in new_medicines]
    for i, nm in enumerate(new_medicines):
        for other in existing + new_medicines[:i] + new_medicines[i + 1:]:
            g1, g2 = nm["generic"], (other.get("generic") or "").lower()
            if not g1 or not g2 or g1 == g2:
                continue
            key = tuple(sorted((g1, g2)))
            if key in checked:
                continue
            checked.add(key)
            msg = check_pair(g1, g2)
            if msg:
                _mk_alert(
                    "high", "clash",
                    f"{nm['name']} + {other['name']}",
                    f"{nm['name']} ({g1}) with {other['name']} ({g2}): {msg}",
                )

    # Lab observation status.
    worst = "good"
    rank = {"good": 0, "watch": 1, "alert": 2}
    for ob in observations:
        code = ob.get("code")
        try:
            val = float(ob["value"])
        except (KeyError, TypeError, ValueError):
            continue
        status = lab_status(code, val) if code else "watch"
        ob["status"] = status
        if not ob.get("range"):
            ob["range"] = lab_range(code) if code else None
        if rank[status] > rank[worst]:
            worst = status
        if status == "alert":
            _mk_alert(
                "medium", "lab",
                f"{ob.get('name', 'Lab value')} is above the healthy range",
                f"{ob.get('name', 'This value')} is {ob['value']} {ob.get('unit', '')}, outside the usual range of {ob['range']}. Discuss at your next visit.",
            )

    return {
        "alerts": alerts,
        "medications": new_medicines,
        "observations": observations,
        "worst_status": worst,
    }
