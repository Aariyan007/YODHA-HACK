"""Lab status rules. Plain thresholds, no AI.

Each rule: (good_low, good_high, watch_low, watch_high). Values inside the
good band are "good", inside the watch band are "watch", anything else "alert".
"""

RULES: dict[str, dict] = {
    "hba1c": {"name": "HbA1c", "unit": "%", "good": (0, 7.0), "watch": (0, 8.0), "range": "< 7.0 (diabetic target)"},
    "fbs": {"name": "Fasting blood sugar", "unit": "mg/dL", "good": (70, 130), "watch": (60, 180), "range": "70 - 130"},
    "ppbs": {"name": "Post-meal blood sugar", "unit": "mg/dL", "good": (70, 180), "watch": (60, 250), "range": "< 180"},
    "ldl": {"name": "LDL cholesterol", "unit": "mg/dL", "good": (0, 100), "watch": (0, 160), "range": "< 100"},
    "hdl": {"name": "HDL cholesterol", "unit": "mg/dL", "good": (40, 999), "watch": (35, 999), "range": "> 40"},
    "tg": {"name": "Triglycerides", "unit": "mg/dL", "good": (0, 150), "watch": (0, 200), "range": "< 150"},
    "total_chol": {"name": "Total cholesterol", "unit": "mg/dL", "good": (0, 200), "watch": (0, 240), "range": "< 200"},
    "creatinine": {"name": "Creatinine", "unit": "mg/dL", "good": (0.5, 1.2), "watch": (0.4, 1.6), "range": "0.5 - 1.2"},
    "hb": {"name": "Haemoglobin", "unit": "g/dL", "good": (12.0, 16.0), "watch": (10.0, 17.5), "range": "12 - 16"},
    "tsh": {"name": "TSH", "unit": "mIU/L", "good": (0.4, 4.0), "watch": (0.2, 6.0), "range": "0.4 - 4.0"},
    "sbp": {"name": "Systolic BP", "unit": "mmHg", "good": (90, 130), "watch": (85, 150), "range": "90 - 130"},
    "dbp": {"name": "Diastolic BP", "unit": "mmHg", "good": (60, 85), "watch": (55, 95), "range": "60 - 85"},
}


def lab_status(code: str, value: float) -> str:
    rule = RULES.get(code)
    if rule is None:
        return "watch"
    lo, hi = rule["good"]
    if lo <= value <= hi:
        return "good"
    lo, hi = rule["watch"]
    if lo <= value <= hi:
        return "watch"
    return "alert"


def lab_range(code: str) -> str | None:
    rule = RULES.get(code)
    return rule["range"] if rule else None


# Primary LOINC code per lab code (stored on Observation.loinc).
LOINC_BY_CODE: dict[str, str] = {
    "hba1c": "4548-4", "fbs": "1558-6", "ppbs": "1521-4", "ldl": "13457-7", "hdl": "2085-9",
    "tg": "2571-8", "total_chol": "2093-3", "creatinine": "2160-0", "hb": "718-7",
    "tsh": "3016-3", "sbp": "8480-6", "dbp": "8462-4",
}

# Every LOINC we accept on import -> our lab code (a few tests have several LOINC ids).
CODE_BY_LOINC: dict[str, str] = {
    **{v: k for k, v in LOINC_BY_CODE.items()},
    "17856-6": "hba1c", "59261-8": "hba1c", "41995-2": "hba1c",
    "1556-0": "fbs", "76629-5": "fbs", "2345-7": "ppbs",
    "2089-1": "ldl", "18262-6": "ldl",
}


def loinc_for(code: str | None) -> str | None:
    return LOINC_BY_CODE.get(code or "")
