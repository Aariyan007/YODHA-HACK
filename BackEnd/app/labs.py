"""Lab status rules. Plain thresholds, no AI.

Each rule: (good_low, good_high, watch_low, watch_high). Values inside the
good band are "good", inside the watch band are "watch", anything else "alert".
"""
import re

RULES: dict[str, dict] = {
    "hba1c": {"name": "HbA1c", "unit": "%", "good": (0, 7.0), "watch": (0, 8.0), "range": "< 7.0 (diabetic target)"},
    "fbs": {"name": "Fasting blood sugar", "unit": "mg/dL", "good": (70, 130), "watch": (60, 180), "range": "70 - 130"},
    "ppbs": {"name": "Post-meal blood sugar", "unit": "mg/dL", "good": (70, 180), "watch": (60, 250), "range": "< 180"},
    "rbs": {"name": "Random blood sugar", "unit": "mg/dL", "good": (70, 160), "watch": (60, 200), "range": "70 - 160"},
    "ldl": {"name": "LDL cholesterol", "unit": "mg/dL", "good": (0, 100), "watch": (0, 160), "range": "< 100"},
    "hdl": {"name": "HDL cholesterol", "unit": "mg/dL", "good": (40, 999), "watch": (35, 999), "range": "> 40"},
    "tg": {"name": "Triglycerides", "unit": "mg/dL", "good": (0, 150), "watch": (0, 200), "range": "< 150"},
    "total_chol": {"name": "Total cholesterol", "unit": "mg/dL", "good": (0, 200), "watch": (0, 240), "range": "< 200"},
    "creatinine": {"name": "Creatinine", "unit": "mg/dL", "good": (0.5, 1.2), "watch": (0.4, 1.6), "range": "0.5 - 1.2"},
    "egfr": {"name": "eGFR", "unit": "mL/min/1.73m2", "good": (90, 999), "watch": (60, 999), "range": "> 90"},
    "urea": {"name": "Blood urea", "unit": "mg/dL", "good": (15, 45), "watch": (10, 60), "range": "15 - 45"},
    "uric_acid": {"name": "Uric acid", "unit": "mg/dL", "good": (2.5, 7.0), "watch": (2.0, 8.5), "range": "2.5 - 7.0"},
    "potassium": {"name": "Potassium", "unit": "mmol/L", "good": (3.5, 5.0), "watch": (3.2, 5.5), "range": "3.5 - 5.0"},
    "sodium": {"name": "Sodium", "unit": "mmol/L", "good": (135, 145), "watch": (130, 148), "range": "135 - 145"},
    "hb": {"name": "Haemoglobin", "unit": "g/dL", "good": (12.0, 16.0), "watch": (10.0, 17.5), "range": "12 - 16"},
    "platelets": {"name": "Platelets", "unit": "x10^3/uL", "good": (150, 450), "watch": (100, 500), "range": "150 - 450"},
    "wbc": {"name": "White cells (WBC)", "unit": "x10^3/uL", "good": (4.0, 11.0), "watch": (3.0, 13.0), "range": "4 - 11"},
    "sgpt": {"name": "SGPT (ALT)", "unit": "U/L", "good": (0, 45), "watch": (0, 90), "range": "< 45"},
    "sgot": {"name": "SGOT (AST)", "unit": "U/L", "good": (0, 40), "watch": (0, 80), "range": "< 40"},
    "bilirubin": {"name": "Total bilirubin", "unit": "mg/dL", "good": (0.2, 1.2), "watch": (0.1, 2.0), "range": "0.2 - 1.2"},
    "tsh": {"name": "TSH", "unit": "mIU/L", "good": (0.4, 4.0), "watch": (0.2, 6.0), "range": "0.4 - 4.0"},
    "vit_d": {"name": "Vitamin D", "unit": "ng/mL", "good": (30, 100), "watch": (20, 150), "range": "30 - 100"},
    "vit_b12": {"name": "Vitamin B12", "unit": "pg/mL", "good": (200, 900), "watch": (150, 1200), "range": "200 - 900"},
    "sbp": {"name": "Systolic BP", "unit": "mmHg", "good": (90, 130), "watch": (85, 150), "range": "90 - 130"},
    "dbp": {"name": "Diastolic BP", "unit": "mmHg", "good": (60, 85), "watch": (55, 95), "range": "60 - 85"},
    "pulse": {"name": "Pulse", "unit": "bpm", "good": (60, 100), "watch": (50, 110), "range": "60 - 100"},
    "spo2": {"name": "Oxygen (SpO2)", "unit": "%", "good": (95, 100), "watch": (92, 100), "range": "95 - 100"},
    "weight": {"name": "Weight", "unit": "kg", "good": (0, 999), "watch": (0, 999), "range": None},
    "temp": {"name": "Temperature", "unit": "°F", "good": (97, 99.5), "watch": (96, 100.4), "range": "97 - 99.5"},
}

# Lower-case name fragment -> lab code. Checked longest first, so "post meal blood sugar" beats "blood sugar".
NAME_TO_CODE: dict[str, str] = {
    "hba1c": "hba1c", "a1c": "hba1c", "glycated": "hba1c", "glycosylated": "hba1c",
    "fasting blood sugar": "fbs", "fasting glucose": "fbs", "fasting plasma glucose": "fbs", "fbs": "fbs", "fpg": "fbs",
    "post meal": "ppbs", "post prandial": "ppbs", "postprandial": "ppbs", "ppbs": "ppbs", "pp blood sugar": "ppbs",
    "random blood sugar": "rbs", "random glucose": "rbs", "rbs": "rbs", "grbs": "rbs", "blood sugar": "rbs",
    "ldl": "ldl", "hdl": "hdl", "triglyceride": "tg", "tg": "tg",
    "total cholesterol": "total_chol", "cholesterol, total": "total_chol", "serum cholesterol": "total_chol",
    "creatinine": "creatinine", "egfr": "egfr", "gfr": "egfr",
    "blood urea": "urea", "urea": "urea", "bun": "urea", "uric acid": "uric_acid",
    "potassium": "potassium", "k+": "potassium", "sodium": "sodium", "na+": "sodium",
    "haemoglobin": "hb", "hemoglobin": "hb", "hb": "hb", "hgb": "hb",
    "platelet": "platelets", "wbc": "wbc", "white blood cell": "wbc", "total leucocyte": "wbc", "tlc": "wbc",
    "sgpt": "sgpt", "alt": "sgpt", "alanine": "sgpt", "sgot": "sgot", "ast": "sgot", "aspartate": "sgot",
    "bilirubin": "bilirubin",
    "tsh": "tsh", "thyroid stimulating": "tsh",
    "vitamin d": "vit_d", "25-oh": "vit_d", "vitamin b12": "vit_b12", "b12": "vit_b12",
    "systolic": "sbp", "diastolic": "dbp",
    "pulse": "pulse", "heart rate": "pulse", "spo2": "spo2", "oxygen saturation": "spo2",
    "weight": "weight", "temperature": "temp",
}
_NAME_KEYS = sorted(NAME_TO_CODE, key=len, reverse=True)


def code_for_name(name: str | None) -> str | None:
    """Best lab code for a free-text test name, or None if we do not know the test.

    The earliest match in the name wins ("HbA1c (Glycated Haemoglobin)" is HbA1c, not haemoglobin);
    on a tie the longer fragment wins ("Fasting blood sugar" beats "blood sugar").
    """
    key = (name or "").lower().strip()
    if not key:
        return None
    best: tuple[int, int, str] | None = None
    for frag in _NAME_KEYS:
        # Short fragments (hb, tg, alt...) must match a whole word, long ones can be substrings.
        pat = rf"(?<![a-z0-9]){re.escape(frag)}(?![a-z0-9])" if len(frag) <= 4 else re.escape(frag)
        m = re.search(pat, key)
        if m and (best is None or (m.start(), -len(frag)) < (best[0], best[1])):
            best = (m.start(), -len(frag), NAME_TO_CODE[frag])
    return best[2] if best else None


def slug(name: str | None) -> str:
    """Stable code for a test we have no rule for, so different tests never collide."""
    s = re.sub(r"[^a-z0-9]+", "_", (name or "").lower()).strip("_")
    return ("x_" + s)[:40] if s else "unknown"


def parse_range(text: str | None) -> tuple[float | None, float | None] | None:
    """Read a printed reference range: "70 - 110", "<5.7", "> 40", "3.5-5.0 mmol/L"."""
    if not text:
        return None
    t = text.replace("–", "-").replace("—", "-").replace(",", "")
    m = re.search(r"(-?\d+(?:\.\d+)?)\s*(?:-|to)\s*(-?\d+(?:\.\d+)?)", t)
    if m:
        lo, hi = float(m.group(1)), float(m.group(2))
        return (min(lo, hi), max(lo, hi))
    m = re.search(r"(<|≤|less than|upto|up to)\s*=?\s*(\d+(?:\.\d+)?)", t, re.I)
    if m:
        return (None, float(m.group(2)))
    m = re.search(r"(>|≥|more than|above)\s*=?\s*(\d+(?:\.\d+)?)", t, re.I)
    if m:
        return (float(m.group(2)), None)
    return None


def status_from_range(value: float, text: str | None) -> str | None:
    """good / watch (within 10% of a limit) / alert from a printed range. None if the range cannot be read."""
    rng = parse_range(text)
    if rng is None:
        return None
    lo, hi = rng
    if lo is not None and value < lo:
        return "watch" if value >= lo - 0.1 * abs(lo) else "alert"
    if hi is not None and value > hi:
        return "watch" if value <= hi + 0.1 * abs(hi) else "alert"
    return "good"


def lab_status(code: str, value: float, printed_range: str | None = None) -> str:
    rule = RULES.get(code)
    if rule is None:
        return status_from_range(value, printed_range) or "watch"
    lo, hi = rule["good"]
    if lo <= value <= hi:
        return "good"
    lo, hi = rule["watch"]
    if lo <= value <= hi:
        return "watch"
    return "alert"


def direction(code: str, value: float, printed_range: str | None = None) -> str | None:
    """"high" or "low" when a value is outside its good band, else None."""
    rule = RULES.get(code)
    if rule is not None:
        lo, hi = rule["good"]
    else:
        rng = parse_range(printed_range)
        if rng is None:
            return None
        lo, hi = rng
        lo = lo if lo is not None else float("-inf")
        hi = hi if hi is not None else float("inf")
    if value > hi:
        return "high"
    if value < lo:
        return "low"
    return None


def lab_range(code: str) -> str | None:
    rule = RULES.get(code)
    return rule["range"] if rule else None


def lab_name(code: str, fallback: str | None = None) -> str:
    rule = RULES.get(code)
    return rule["name"] if rule else (fallback or code)


# Primary LOINC code per lab code (stored on Observation.loinc).
LOINC_BY_CODE: dict[str, str] = {
    "hba1c": "4548-4", "fbs": "1558-6", "ppbs": "1521-4", "rbs": "2345-7", "ldl": "13457-7", "hdl": "2085-9",
    "tg": "2571-8", "total_chol": "2093-3", "creatinine": "2160-0", "egfr": "33914-3", "urea": "3094-0",
    "uric_acid": "3084-1", "potassium": "2823-3", "sodium": "2951-2", "hb": "718-7", "platelets": "777-3",
    "wbc": "6690-2", "sgpt": "1742-6", "sgot": "1920-8", "bilirubin": "1975-2",
    "tsh": "3016-3", "vit_d": "1989-3", "vit_b12": "2132-9",
    "sbp": "8480-6", "dbp": "8462-4", "pulse": "8867-4", "spo2": "59408-5", "weight": "29463-7", "temp": "8310-5",
}

# Every LOINC we accept on import -> our lab code (a few tests have several LOINC ids).
CODE_BY_LOINC: dict[str, str] = {
    **{v: k for k, v in LOINC_BY_CODE.items()},
    "17856-6": "hba1c", "59261-8": "hba1c", "41995-2": "hba1c",
    "1556-0": "fbs", "76629-5": "fbs",
    "2089-1": "ldl", "18262-6": "ldl",
    "62238-1": "egfr", "48642-3": "egfr", "2708-6": "spo2", "3141-9": "weight",
}


def loinc_for(code: str | None) -> str | None:
    return LOINC_BY_CODE.get(code or "")
