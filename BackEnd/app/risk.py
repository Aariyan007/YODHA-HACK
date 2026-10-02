"""Danger checks over a patient's whole record. Pure Python, no AI.

Reads every stored Observation (uploads, hospital imports, home readings, seed)
and returns a list of risks: blood pressure, sugar, kidney, salts, oxygen, pulse,
blood counts, liver, cholesterol, thyroid, temperature, weight change, and
values that keep rising across reports.

Each risk states the real numbers, the level (emergency / high / watch), which
kind of doctor to see, and nothing else. The wording never names a cause and
never suggests a medicine or a dose.

`refresh_risk_alerts` keeps ONE open Alert (kind "risk") per risk key, updates
it when the numbers change, and resolves it when a newer reading is fine.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .labs import RULES, lab_name
from .models import Alert, Observation, now
from .trends import HIGHER_IS_WORSE, _series, rising_run, test_key

LEVELS = ("emergency", "high", "watch")
LEVEL_RANK = {"emergency": 0, "high": 1, "watch": 2}
SEVERITY_FOR_LEVEL = {"emergency": "high", "high": "high", "watch": "medium"}
# An emergency is only an emergency when the reading is recent. Older readings drop to "high".
EMERGENCY_FRESH_DAYS = 3
OLD_READING_DAYS = 180

# Doctor types used by the doctor finder (app/doctors.py uses the same names).
GP = "General Physician"
CARDIO = "Cardiologist"
DIABETES = "Diabetologist"
NEPHRO = "Nephrologist"
PULMO = "Pulmonologist"
GASTRO = "Gastroenterologist"
ENDO = "Endocrinologist"
HAEM = "Haematologist"
EMERGENCY = "Emergency"


@dataclass
class Risk:
    key: str
    level: str
    title: str
    message: str
    message_ml: str
    specialist: str
    evidence: list[dict] = field(default_factory=list)
    reason: str = ""  # short tag for the doctor finder, e.g. "high_bp"

    def out(self) -> dict:
        return {
            "key": self.key, "level": self.level, "title": self.title, "message": self.message,
            "messageMl": self.message_ml, "specialist": self.specialist, "evidence": self.evidence,
            "reason": self.reason or self.key, "emergency": self.level == "emergency",
        }


def _fmt(v: float) -> str:
    return f"{v:g}"


def _days_old(d: str | None, today: date) -> int:
    try:
        return (today - date.fromisoformat(d)).days
    except (TypeError, ValueError):
        return 9999


def _when(d: str, today: date) -> str:
    age = _days_old(d, today)
    if age <= 0:
        return "today"
    if age == 1:
        return "yesterday"
    return f"on {d}"


def _ev(o: Observation) -> dict:
    return {"code": o.code, "name": lab_name(o.code, o.name), "value": o.value, "unit": o.unit or RULES.get(o.code, {}).get("unit"),
            "date": o.date}


def _latest_by_key(obs: list[Observation]) -> dict[str, Observation]:
    out: dict[str, Observation] = {}
    for o in sorted(obs, key=lambda o: o.date or ""):
        out[test_key(o)] = o  # the newest wins; same-date rows keep insert order
    return out


def _fresh(level: str, o_date: str, today: date) -> str:
    if level == "emergency" and _days_old(o_date, today) > EMERGENCY_FRESH_DAYS:
        return "high"
    return level


def _old_note(o_date: str, today: date) -> tuple[str, str]:
    if _days_old(o_date, today) > OLD_READING_DAYS:
        return (" This reading is more than 6 months old; a new test will tell you where you stand now.",
                " ഈ ഫലം 6 മാസത്തിലേറെ പഴയതാണ്; പുതിയ പരിശോധന നടത്തുക.")
    return ("", "")


# ---------- blood pressure ----------

def _bp(latest: dict[str, Observation], today: date) -> list[Risk]:
    s, d = latest.get("sbp"), latest.get("dbp")
    if s is None and d is None:
        return []
    # Use the pair from the same day when both exist, else whichever is newest.
    when = max((o.date for o in (s, d) if o is not None), default="")
    sv = s.value if s is not None and s.date == when else None
    dv = d.value if d is not None and d.date == when else None
    shown = f"{_fmt(sv) if sv is not None else '?'}/{_fmt(dv) if dv is not None else '?'}"
    ev = [_ev(o) for o in (s, d) if o is not None and o.date == when]
    old_en, old_ml = _old_note(when, today)
    sv0, dv0 = sv or 0, dv or 0
    if sv0 >= 180 or dv0 >= 120:
        level = _fresh("emergency", when, today)
        if level == "emergency":
            return [Risk("bp", level, "Very high blood pressure",
                         f"Your blood pressure was {shown} mmHg {_when(when, today)}. This is in the danger zone. "
                         "If you also have chest pain, a bad headache, blurred vision, weakness or trouble speaking, call 108 now. "
                         "Otherwise sit and rest for 5 minutes, check again, and see a doctor today.",
                         f"നിങ്ങളുടെ ബിപി {shown} mmHg ആയിരുന്നു. ഇത് അപകട നിലയാണ്. നെഞ്ചുവേദന, കടുത്ത തലവേദന, കാഴ്ച മങ്ങൽ, "
                         "തളർച്ച എന്നിവയുണ്ടെങ്കിൽ ഉടൻ 108 വിളിക്കുക. ഇല്ലെങ്കിൽ 5 മിനിറ്റ് വിശ്രമിച്ച് വീണ്ടും നോക്കുക, ഇന്നുതന്നെ ഡോക്ടറെ കാണുക.",
                         EMERGENCY, ev, "bp_crisis")]
        return [Risk("bp", "high", "Very high blood pressure reading",
                     f"Your blood pressure was {shown} mmHg {_when(when, today)}, which is very high. "
                     "Check it again and show your doctor soon." + old_en,
                     f"നിങ്ങളുടെ ബിപി {shown} mmHg ആയിരുന്നു, ഇത് വളരെ കൂടുതലാണ്. വീണ്ടും പരിശോധിച്ച് ഡോക്ടറെ കാണിക്കുക." + old_ml,
                     CARDIO, ev, "high_bp")]
    if sv0 >= 140 or dv0 >= 90:
        return [Risk("bp", "high", "High blood pressure",
                     f"Your blood pressure was {shown} mmHg {_when(when, today)}. The usual target is below 130/80. "
                     "Please see a doctor in the next few days and take your readings with you." + old_en,
                     f"നിങ്ങളുടെ ബിപി {shown} mmHg ആയിരുന്നു. സാധാരണ ലക്ഷ്യം 130/80-ൽ താഴെയാണ്. "
                     "അടുത്ത ദിവസങ്ങളിൽ ഡോക്ടറെ കാണുക, റീഡിംഗുകൾ കൂടെ കൊണ്ടുപോകുക." + old_ml,
                     CARDIO if (sv0 >= 160 or dv0 >= 100) else GP, ev, "high_bp")]
    if (sv is not None and sv < 90) or (dv is not None and dv < 55):
        return [Risk("bp", "high", "Low blood pressure",
                     f"Your blood pressure was {shown} mmHg {_when(when, today)}, which is low. If you feel dizzy or faint, "
                     "sit or lie down and tell someone. Show this reading to your doctor." + old_en,
                     f"നിങ്ങളുടെ ബിപി {shown} mmHg ആയിരുന്നു, ഇത് കുറവാണ്. തലകറക്കം ഉണ്ടെങ്കിൽ ഇരിക്കുക/കിടക്കുക. "
                     "ഡോക്ടറെ കാണിക്കുക." + old_ml,
                     GP, ev, "low_bp")]
    if sv0 >= 130 or dv0 >= 80:
        return [Risk("bp", "watch", "Blood pressure a little high",
                     f"Your blood pressure was {shown} mmHg {_when(when, today)}, slightly above the 130/80 target. "
                     "Keep checking it and mention it at your next visit." + old_en,
                     f"നിങ്ങളുടെ ബിപി {shown} mmHg ആയിരുന്നു, 130/80 ലക്ഷ്യത്തേക്കാൾ അൽപം കൂടുതൽ. "
                     "പരിശോധന തുടരുക, അടുത്ത സന്ദർശനത്തിൽ പറയുക." + old_ml,
                     GP, ev, "high_bp")]
    return []


# ---------- simple single-value rules ----------
# (code, level, test, title, en_template, ml_template, specialist, reason)
# test is (op, threshold); templates get {v}, {unit}, {when}.
SINGLE_RULES: list[tuple] = [
    # Sugar
    ("glucose_low", "emergency", ("<", 54), "Very low blood sugar",
     "Your blood sugar was {v} {unit} {when}. This is dangerously low. Eat or drink something sweet now and get help; "
     "call 108 if the person is drowsy or confused.",
     "നിങ്ങളുടെ പഞ്ചസാര {v} {unit} ആയിരുന്നു. ഇത് അപകടകരമായി കുറവാണ്. ഉടൻ മധുരം കഴിക്കുക; മയക്കമോ ആശയക്കുഴപ്പമോ ഉണ്ടെങ്കിൽ 108 വിളിക്കുക.",
     EMERGENCY, "low_sugar"),
    ("glucose_low", "high", ("<", 70), "Low blood sugar",
     "Your blood sugar was {v} {unit} {when}, below 70. Low sugar can make you shaky or faint. Tell your doctor soon.",
     "നിങ്ങളുടെ പഞ്ചസാര {v} {unit} ആയിരുന്നു, 70-ൽ താഴെ. ഇത് വിറയലോ തളർച്ചയോ ഉണ്ടാക്കാം. ഡോക്ടറോട് പറയുക.",
     DIABETES, "low_sugar"),
    ("glucose_high", "emergency", (">=", 400), "Very high blood sugar",
     "Your blood sugar was {v} {unit} {when}. This is very high. If there is vomiting, heavy breathing or drowsiness, "
     "call 108. Otherwise see a doctor today.",
     "നിങ്ങളുടെ പഞ്ചസാര {v} {unit} ആയിരുന്നു. ഇത് വളരെ കൂടുതലാണ്. ഛർദ്ദി, ശ്വാസംമുട്ടൽ, മയക്കം ഉണ്ടെങ്കിൽ 108 വിളിക്കുക. "
     "ഇല്ലെങ്കിൽ ഇന്നുതന്നെ ഡോക്ടറെ കാണുക.",
     EMERGENCY, "high_sugar"),
    ("glucose_high", "high", (">=", 250), "High blood sugar",
     "Your blood sugar was {v} {unit} {when}, well above target. Please see your doctor in the next few days.",
     "നിങ്ങളുടെ പഞ്ചസാര {v} {unit} ആയിരുന്നു, ലക്ഷ്യത്തേക്കാൾ വളരെ കൂടുതൽ. അടുത്ത ദിവസങ്ങളിൽ ഡോക്ടറെ കാണുക.",
     DIABETES, "high_sugar"),
    ("hba1c", "high", (">=", 9), "Sugar average (HbA1c) is high",
     "Your 3-month sugar average (HbA1c) was {v}% {when}. The usual target is below 7%. Show this to your doctor.",
     "നിങ്ങളുടെ 3 മാസത്തെ പഞ്ചസാര ശരാശരി (HbA1c) {v}% ആയിരുന്നു. സാധാരണ ലക്ഷ്യം 7%-ൽ താഴെ. ഡോക്ടറെ കാണിക്കുക.",
     DIABETES, "high_sugar"),
    ("hba1c", "watch", (">=", 8), "Sugar average (HbA1c) above target",
     "Your 3-month sugar average (HbA1c) was {v}% {when}, above the 7% target. Mention it at your next visit.",
     "നിങ്ങളുടെ HbA1c {v}% ആയിരുന്നു, 7% ലക്ഷ്യത്തേക്കാൾ കൂടുതൽ. അടുത്ത സന്ദർശനത്തിൽ പറയുക.",
     DIABETES, "high_sugar"),
    # Kidney
    ("creatinine", "high", (">=", 2.0), "Kidney test (creatinine) is high",
     "Your creatinine was {v} {unit} {when}. The usual range is 0.5 to 1.2. A kidney check-up is a good idea soon.",
     "നിങ്ങളുടെ ക്രിയാറ്റിനിൻ {v} {unit} ആയിരുന്നു. സാധാരണ 0.5–1.2. വേഗം വൃക്ക പരിശോധന നടത്തുക.",
     NEPHRO, "kidney"),
    ("creatinine", "watch", (">", 1.3), "Kidney test (creatinine) a little high",
     "Your creatinine was {v} {unit} {when}, a little above the usual 0.5 to 1.2. Mention it at your next visit.",
     "നിങ്ങളുടെ ക്രിയാറ്റിനിൻ {v} {unit} ആയിരുന്നു, സാധാരണയിലും അൽപം കൂടുതൽ. അടുത്ത സന്ദർശനത്തിൽ പറയുക.",
     NEPHRO, "kidney"),
    ("egfr", "high", ("<", 30), "Kidney filter rate (eGFR) is low",
     "Your eGFR was {v} {when}. Below 30 means the kidneys need a specialist's attention soon.",
     "നിങ്ങളുടെ eGFR {v} ആയിരുന്നു. 30-ൽ താഴെയാണെങ്കിൽ വൃക്ക വിദഗ്ധനെ വേഗം കാണണം.",
     NEPHRO, "kidney"),
    ("egfr", "watch", ("<", 60), "Kidney filter rate (eGFR) is reduced",
     "Your eGFR was {v} {when}, below 60. Ask your doctor about it at the next visit.",
     "നിങ്ങളുടെ eGFR {v} ആയിരുന്നു, 60-ൽ താഴെ. അടുത്ത സന്ദർശനത്തിൽ ചോദിക്കുക.",
     NEPHRO, "kidney"),
    # Salts
    ("potassium", "emergency", (">=", 6.0), "Potassium is dangerously high",
     "Your potassium was {v} {unit} {when}. This level can upset the heart rhythm. Go to a hospital today.",
     "നിങ്ങളുടെ പൊട്ടാസ്യം {v} {unit} ആയിരുന്നു. ഇത് ഹൃദയമിടിപ്പിനെ ബാധിക്കാം. ഇന്നുതന്നെ ആശുപത്രിയിൽ പോകുക.",
     EMERGENCY, "salts"),
    ("potassium", "high", (">", 5.5), "Potassium is high",
     "Your potassium was {v} {unit} {when}, above the usual 3.5 to 5.0. Show this to a doctor soon.",
     "നിങ്ങളുടെ പൊട്ടാസ്യം {v} {unit} ആയിരുന്നു, സാധാരണയിലും കൂടുതൽ. വേഗം ഡോക്ടറെ കാണിക്കുക.",
     GP, "salts"),
    ("potassium", "high", ("<", 3.0), "Potassium is low",
     "Your potassium was {v} {unit} {when}, below the usual 3.5 to 5.0. Show this to a doctor soon.",
     "നിങ്ങളുടെ പൊട്ടാസ്യം {v} {unit} ആയിരുന്നു, സാധാരണയിലും കുറവ്. വേഗം ഡോക്ടറെ കാണിക്കുക.",
     GP, "salts"),
    ("sodium", "high", ("<", 125), "Sodium (salt) is very low",
     "Your sodium was {v} {unit} {when}. Very low sodium can cause confusion or falls. See a doctor soon.",
     "നിങ്ങളുടെ സോഡിയം {v} {unit} ആയിരുന്നു. ഇത് ആശയക്കുഴപ്പമോ വീഴ്ചയോ ഉണ്ടാക്കാം. വേഗം ഡോക്ടറെ കാണുക.",
     GP, "salts"),
    ("sodium", "watch", ("<", 132), "Sodium (salt) is low",
     "Your sodium was {v} {unit} {when}, below the usual 135 to 145. Mention it at your next visit.",
     "നിങ്ങളുടെ സോഡിയം {v} {unit} ആയിരുന്നു, സാധാരണയിലും കുറവ്. അടുത്ത സന്ദർശനത്തിൽ പറയുക.",
     GP, "salts"),
    # Oxygen and pulse
    ("spo2", "emergency", ("<", 90), "Oxygen level is very low",
     "Your oxygen (SpO2) was {v}% {when}. Below 90% needs urgent care. Call 108 or go to the nearest emergency room.",
     "നിങ്ങളുടെ ഓക്സിജൻ (SpO2) {v}% ആയിരുന്നു. 90%-ൽ താഴെ അടിയന്തര ചികിത്സ വേണം. 108 വിളിക്കുക.",
     EMERGENCY, "low_oxygen"),
    ("spo2", "high", ("<", 94), "Oxygen level is low",
     "Your oxygen (SpO2) was {v}% {when}, below the usual 95 to 100. Check again, and see a doctor today if it stays low.",
     "നിങ്ങളുടെ ഓക്സിജൻ {v}% ആയിരുന്നു, സാധാരണയിലും കുറവ്. വീണ്ടും നോക്കുക; കുറഞ്ഞുതന്നെയെങ്കിൽ ഇന്ന് ഡോക്ടറെ കാണുക.",
     PULMO, "low_oxygen"),
    ("pulse", "high", (">", 130), "Pulse is very fast",
     "Your pulse was {v} beats a minute {when}. Rest and check again; if it stays fast or you feel unwell, see a doctor today.",
     "നിങ്ങളുടെ നാഡിമിടിപ്പ് മിനിറ്റിൽ {v} ആയിരുന്നു. വിശ്രമിച്ച് വീണ്ടും നോക്കുക; തുടർന്നാൽ ഇന്ന് ഡോക്ടറെ കാണുക.",
     CARDIO, "pulse"),
    ("pulse", "high", ("<", 45), "Pulse is very slow",
     "Your pulse was {v} beats a minute {when}. If you feel dizzy or faint, get help. Show this to a doctor soon.",
     "നിങ്ങളുടെ നാഡിമിടിപ്പ് മിനിറ്റിൽ {v} ആയിരുന്നു. തലകറക്കം ഉണ്ടെങ്കിൽ സഹായം തേടുക. വേഗം ഡോക്ടറെ കാണിക്കുക.",
     CARDIO, "pulse"),
    ("pulse", "watch", (">", 110), "Pulse is fast",
     "Your pulse was {v} beats a minute {when}, above the usual 60 to 100. Mention it to your doctor.",
     "നിങ്ങളുടെ നാഡിമിടിപ്പ് മിനിറ്റിൽ {v} ആയിരുന്നു, സാധാരണയിലും കൂടുതൽ. ഡോക്ടറോട് പറയുക.",
     CARDIO, "pulse"),
    # Blood counts
    ("hb", "high", ("<", 7), "Haemoglobin is very low",
     "Your haemoglobin was {v} {unit} {when}. This is very low. See a doctor soon.",
     "നിങ്ങളുടെ ഹീമോഗ്ലോബിൻ {v} {unit} ആയിരുന്നു. ഇത് വളരെ കുറവാണ്. വേഗം ഡോക്ടറെ കാണുക.",
     HAEM, "low_hb"),
    ("hb", "watch", ("<", 10), "Haemoglobin is low",
     "Your haemoglobin was {v} {unit} {when}, below the usual 12 to 16. Mention it at your next visit.",
     "നിങ്ങളുടെ ഹീമോഗ്ലോബിൻ {v} {unit} ആയിരുന്നു, സാധാരണയിലും കുറവ്. അടുത്ത സന്ദർശനത്തിൽ പറയുക.",
     GP, "low_hb"),
    ("platelets", "high", ("<", 50), "Platelets are very low",
     "Your platelet count was {v} {unit} {when}. Watch for unusual bleeding or bruising and see a doctor today.",
     "നിങ്ങളുടെ പ്ലേറ്റ്‌ലെറ്റ് {v} {unit} ആയിരുന്നു. അസാധാരണ രക്തസ്രാവം ശ്രദ്ധിക്കുക, ഇന്ന് ഡോക്ടറെ കാണുക.",
     HAEM, "platelets"),
    ("platelets", "watch", ("<", 100), "Platelets are low",
     "Your platelet count was {v} {unit} {when}, below the usual 150 to 450. Mention it to your doctor.",
     "നിങ്ങളുടെ പ്ലേറ്റ്‌ലെറ്റ് {v} {unit} ആയിരുന്നു, സാധാരണയിലും കുറവ്. ഡോക്ടറോട് പറയുക.",
     GP, "platelets"),
    # Liver
    ("sgpt", "high", (">", 135), "Liver test (SGPT) is high",
     "Your SGPT (ALT) was {v} {unit} {when}, more than three times the usual limit. Show this to a doctor soon.",
     "നിങ്ങളുടെ SGPT {v} {unit} ആയിരുന്നു, സാധാരണയുടെ മൂന്നിരട്ടിയിലധികം. വേഗം ഡോക്ടറെ കാണിക്കുക.",
     GASTRO, "liver"),
    ("sgpt", "watch", (">", 90), "Liver test (SGPT) raised",
     "Your SGPT (ALT) was {v} {unit} {when}, above the usual limit of 45. Mention it at your next visit.",
     "നിങ്ങളുടെ SGPT {v} {unit} ആയിരുന്നു, സാധാരണയിലും കൂടുതൽ. അടുത്ത സന്ദർശനത്തിൽ പറയുക.",
     GASTRO, "liver"),
    ("bilirubin", "high", (">", 3), "Bilirubin is high",
     "Your bilirubin was {v} {unit} {when}. If your eyes or skin look yellow, see a doctor soon.",
     "നിങ്ങളുടെ ബിലിറൂബിൻ {v} {unit} ആയിരുന്നു. കണ്ണോ ചർമ്മമോ മഞ്ഞയാണെങ്കിൽ വേഗം ഡോക്ടറെ കാണുക.",
     GASTRO, "liver"),
    # Cholesterol
    ("ldl", "high", (">=", 190), "LDL cholesterol is very high",
     "Your LDL (bad cholesterol) was {v} {unit} {when}. The usual target is below 100. Show this to your doctor.",
     "നിങ്ങളുടെ LDL {v} {unit} ആയിരുന്നു. സാധാരണ ലക്ഷ്യം 100-ൽ താഴെ. ഡോക്ടറെ കാണിക്കുക.",
     CARDIO, "cholesterol"),
    ("ldl", "watch", (">=", 130), "LDL cholesterol above target",
     "Your LDL (bad cholesterol) was {v} {unit} {when}, above the target of 100. Mention it at your next visit.",
     "നിങ്ങളുടെ LDL {v} {unit} ആയിരുന്നു, 100 ലക്ഷ്യത്തേക്കാൾ കൂടുതൽ. അടുത്ത സന്ദർശനത്തിൽ പറയുക.",
     GP, "cholesterol"),
    ("tg", "high", (">=", 500), "Triglycerides are very high",
     "Your triglycerides were {v} {unit} {when}. Above 500 needs a doctor's attention soon.",
     "നിങ്ങളുടെ ട്രൈഗ്ലിസറൈഡ് {v} {unit} ആയിരുന്നു. 500-ന് മുകളിൽ വേഗം ഡോക്ടറെ കാണണം.",
     CARDIO, "cholesterol"),
    # Thyroid
    ("tsh", "high", (">", 10), "Thyroid test (TSH) is high",
     "Your TSH was {v} {unit} {when}, well above the usual 0.4 to 4.0. Show this to your doctor.",
     "നിങ്ങളുടെ TSH {v} {unit} ആയിരുന്നു, സാധാരണയിലും വളരെ കൂടുതൽ. ഡോക്ടറെ കാണിക്കുക.",
     ENDO, "thyroid"),
    ("tsh", "high", ("<", 0.1), "Thyroid test (TSH) is very low",
     "Your TSH was {v} {unit} {when}, well below the usual 0.4 to 4.0. Show this to your doctor.",
     "നിങ്ങളുടെ TSH {v} {unit} ആയിരുന്നു, സാധാരണയിലും വളരെ കുറവ്. ഡോക്ടറെ കാണിക്കുക.",
     ENDO, "thyroid"),
    # Temperature
    ("temp", "high", (">=", 103), "High fever",
     "Your temperature was {v}°F {when}. A fever this high should be seen by a doctor today.",
     "നിങ്ങളുടെ താപനില {v}°F ആയിരുന്നു. ഇത്ര കൂടിയ പനിക്ക് ഇന്നുതന്നെ ഡോക്ടറെ കാണുക.",
     GP, "fever"),
]

GLUCOSE_CODES = ("fbs", "ppbs", "rbs")


def _test(op: str, v: float, t: float) -> bool:
    return {"<": v < t, "<=": v <= t, ">": v > t, ">=": v >= t}[op]


def _singles(latest: dict[str, Observation], today: date) -> list[Risk]:
    out: list[Risk] = []
    done: set[str] = set()  # one risk per (rule key + direction); rules are ordered worst first
    # Newest glucose of any kind stands for "glucose".
    gl = [latest[c] for c in GLUCOSE_CODES if c in latest]
    newest_glucose = max(gl, key=lambda o: o.date or "") if gl else None
    for code, level, (op, thr), title, en, ml, spec, reason in SINGLE_RULES:
        o = newest_glucose if code.startswith("glucose_") else latest.get(code)
        if o is None:
            continue
        slot = f"{code}:{'low' if op.startswith('<') else 'high'}"
        if slot in done or not _test(op, o.value, thr):
            continue
        done.add(slot)
        lvl = _fresh(level, o.date, today)
        if lvl != level and lvl == "high":
            spec = GP if spec == EMERGENCY else spec
        unit = o.unit or RULES.get(o.code, {}).get("unit") or ""
        old_en, old_ml = _old_note(o.date, today)
        key = code if code.startswith("glucose_") or op.startswith(">") else f"{code}_low"
        out.append(Risk(key, lvl, title,
                        en.format(v=_fmt(o.value), unit=unit, when=_when(o.date, today)) + old_en,
                        ml.format(v=_fmt(o.value), unit=unit, when=_when(o.date, today)) + old_ml,
                        spec, [_ev(o)], reason))
    return out


# ---------- across reports ----------

def _rising(obs: list[Observation]) -> list[Risk]:
    groups: dict[str, list[Observation]] = {}
    for o in obs:
        groups.setdefault(test_key(o), []).append(o)
    out = []
    for key, rows in groups.items():
        if key not in HIGHER_IS_WORSE:
            continue
        run = rising_run(_series(rows))
        if len(run) < 3:
            continue
        name = RULES[key]["name"]
        nums = ", ".join(_fmt(v) for v in run)
        spec = {"hba1c": DIABETES, "fbs": DIABETES, "ppbs": DIABETES, "creatinine": NEPHRO,
                "sbp": CARDIO, "dbp": CARDIO}.get(key, GP)
        dated = sorted(rows, key=lambda o: o.date)[-len(run):]
        out.append(Risk(f"rising_{key}", "watch", f"{name} keeps rising",
                        f"Your {name} has gone up in each of your last {len(run)} reports: {nums}. Show this to your doctor.",
                        f"നിങ്ങളുടെ {name} അവസാന {len(run)} റിപ്പോർട്ടുകളിലും കൂടി: {nums}. ഡോക്ടറെ കാണിക്കുക.",
                        spec, [_ev(o) for o in dated], "trend"))
    return out


def _weight(obs: list[Observation], today: date) -> list[Risk]:
    rows = sorted((o for o in obs if test_key(o) == "weight"), key=lambda o: o.date)
    if len(rows) < 2:
        return []
    last = rows[-1]
    window = [o for o in rows if 0 <= _days_old(o.date, date.fromisoformat(last.date)) <= 90]
    first = window[0]
    if first is last or first.value <= 0:
        return []
    change = (last.value - first.value) / first.value * 100
    if abs(change) < 5:
        return []
    word, word_ml = ("gone down", "കുറഞ്ഞു") if change < 0 else ("gone up", "കൂടി")
    return [Risk("weight_change", "watch", f"Weight has {word} quickly",
                 f"Your weight has {word} from {_fmt(first.value)} kg to {_fmt(last.value)} kg "
                 f"({abs(change):.0f}%) between {first.date} and {last.date}. Mention this to your doctor.",
                 f"നിങ്ങളുടെ ഭാരം {_fmt(first.value)} kg-ൽ നിന്ന് {_fmt(last.value)} kg ആയി {word_ml}. ഡോക്ടറോട് പറയുക.",
                 GP, [_ev(first), _ev(last)], "weight")]


def assess(db: Session, patient_id: str, today: date | None = None) -> list[dict]:
    """All current risks for a patient, worst first. Read-only."""
    today = today or datetime.now(timezone.utc).date()
    obs = list(db.scalars(select(Observation).where(Observation.patient_id == patient_id)))
    if not obs:
        return []
    latest = _latest_by_key(obs)
    risks = _bp(latest, today) + _singles(latest, today) + _rising(obs) + _weight(obs, today)
    # A rising-trend risk is redundant when the same test already has a high/emergency risk.
    strong = {e["code"] for r in risks if r.level != "watch" for e in r.evidence}
    risks = [r for r in risks if not (r.key.startswith("rising_") and r.key[7:] in strong)]
    risks.sort(key=lambda r: (LEVEL_RANK[r.level], r.key))
    return [r.out() for r in risks]


def refresh_risk_alerts(db: Session, patient_id: str, today: date | None = None) -> tuple[list[dict], list[dict]]:
    """Keep one open "risk" Alert per risk key. Returns (risks, newly_created_emergencies).

    Does not commit; the caller owns the transaction. Rising trends stay with app/trends.py
    (kind "trend"), so they are not duplicated here.
    """
    risks = assess(db, patient_id, today)
    wanted = {r["key"]: r for r in risks if not r["key"].startswith("rising_")}
    open_rows = list(db.scalars(select(Alert).where(
        Alert.patient_id == patient_id, Alert.kind == "risk", Alert.resolved.is_(False))))
    # Alerts are matched by title: a change of level (watch -> high) changes the title, which
    # resolves the old alert and opens a new one, so an escalation is never hidden in an old card.
    by_title = {row.title: row for row in open_rows}
    new_emergencies: list[dict] = []
    seen_titles = set()
    for r in wanted.values():
        title = r["title"]
        seen_titles.add(title)
        row = by_title.get(title)
        sev = SEVERITY_FOR_LEVEL[r["level"]]
        if row is None:
            db.add(Alert(patient_id=patient_id, severity=sev, kind="risk", title=title,
                         message=r["message"], message_ml=r["messageMl"]))
            if r["level"] == "emergency":
                new_emergencies.append(r)
        elif row.message != r["message"] or row.severity != sev:
            row.message, row.message_ml, row.severity, row.created_at = r["message"], r["messageMl"], sev, now()
    # A risk that went away (newer reading is fine): resolve its alert.
    for row in open_rows:
        if row.title not in seen_titles:
            row.resolved = True
    db.flush()
    return risks, new_emergencies
