"""Demo data: Ammini Varghese. Loaded on startup when the DB is empty."""
import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AccessLog, Alert, Document, Medicine, Observation, Patient, ReminderSettings

DEMO_PHONE = "9876543210"
DEMO_ID = "ammini01"

PATIENT = dict(
    id=DEMO_ID,
    name="Ammini Varghese",
    phone=DEMO_PHONE,
    age=62,
    gender="Female",
    blood_group="B+",
    abha_id="91-4521-7788-3300",
    language="ml",
    conditions=[
        {"name": "Type 2 Diabetes", "since": "2016", "status": "watch"},
        {"name": "Hypertension", "since": "2018", "status": "good"},
        {"name": "High cholesterol", "since": "2025", "status": "watch"},
    ],
    allergies=["Sulfa drugs"],
    family=[
        {"id": "fam1", "name": "Joseph Varghese", "relation": "Son", "phone": "9847001122", "canView": True, "notify": True},
        {"id": "fam2", "name": "Mariamma Thomas", "relation": "Daughter", "phone": "9847003344", "canView": True, "notify": False},
    ],
)

# (id, date, type, title, source, summary, summary_ml, tags, items, observations)
# observations: list of (code, name, value, unit)
DOCUMENTS = [
    ("doc1", "2024-11-08", "lab", "HbA1c test", "DDRC Agilus, Kottayam",
     "Your 3-month sugar average (HbA1c) is 9.1%. This is high. Your doctor will likely adjust your diabetes medicine.",
     "നിങ്ങളുടെ മൂന്ന് മാസത്തെ ശരാശരി പഞ്ചസാര (HbA1c) 9.1% ആണ്. ഇത് കൂടുതലാണ്. ഡോക്ടർ മരുന്ന് മാറ്റിയേക്കാം.",
     ["diabetes"], [], [("hba1c", "HbA1c", 9.1, "%"), ("fbs", "Fasting blood sugar", 182, "mg/dL")]),
    ("doc2", "2024-11-12", "prescription", "Diabetes and BP medicines", "Dr. Thomas Kurian, Caritas Hospital",
     "Dr. Kurian started Glycomet 500 twice a day for sugar and Telma 40 once a day for blood pressure.",
     "ഡോ. കുര്യൻ പഞ്ചസാരയ്ക്ക് Glycomet 500 ദിവസം രണ്ടു നേരവും, ബിപിക്ക് Telma 40 ദിവസം ഒരു നേരവും തുടങ്ങി.",
     ["diabetes", "bp"],
     [{"name": "Glycomet 500", "generic": "metformin", "dose": "500 mg", "frequency": "Twice daily", "duration": "Ongoing"},
      {"name": "Telma 40", "generic": "telmisartan", "dose": "40 mg", "frequency": "Once daily", "duration": "Ongoing"}],
     []),
    ("doc3", "2025-03-12", "lab", "HbA1c and lipid profile", "DDRC Agilus, Kottayam",
     "Sugar average improved to 7.9%. LDL (bad cholesterol) is 142, which is above the target of 100.",
     "പഞ്ചസാര ശരാശരി 7.9% ആയി മെച്ചപ്പെട്ടു. LDL (ചീത്ത കൊളസ്ട്രോൾ) 142 ആണ്, ലക്ഷ്യമായ 100-ൽ കൂടുതൽ.",
     ["diabetes", "cholesterol"], [],
     [("hba1c", "HbA1c", 7.9, "%"), ("ldl", "LDL cholesterol", 142, "mg/dL"), ("hdl", "HDL cholesterol", 44, "mg/dL"), ("tg", "Triglycerides", 168, "mg/dL")]),
    ("doc4", "2025-03-15", "prescription", "Cholesterol medicine added", "Dr. Thomas Kurian, Caritas Hospital",
     "Atorva 20 added once at night to bring cholesterol down. Continue Glycomet and Telma.",
     "കൊളസ്ട്രോൾ കുറയ്ക്കാൻ രാത്രി Atorva 20 ചേർത്തു. Glycomet, Telma തുടരുക.",
     ["cholesterol"],
     [{"name": "Atorva 20", "generic": "atorvastatin", "dose": "20 mg", "frequency": "Once at night", "duration": "Ongoing"}],
     []),
    ("doc5", "2025-09-18", "consultation", "Diabetes follow-up visit", "Dr. Thomas Kurian, Caritas Hospital",
     "Routine check. BP 132/84. Feet checked, no wounds. Advised 30 minutes walking daily and less rice at dinner.",
     "പതിവ് പരിശോധന. ബിപി 132/84. കാലുകൾ പരിശോധിച്ചു, മുറിവുകളില്ല. ദിവസവും 30 മിനിറ്റ് നടക്കാനും രാത്രി ചോറ് കുറയ്ക്കാനും പറഞ്ഞു.",
     ["diabetes", "bp"], [], [("sbp", "Systolic BP", 132, "mmHg"), ("dbp", "Diastolic BP", 84, "mmHg")]),
    ("doc6", "2025-12-10", "lab", "HbA1c and kidney test", "DDRC Agilus, Kottayam",
     "Sugar average is 7.4%, getting better. Kidney test (creatinine 1.1) is normal.",
     "പഞ്ചസാര ശരാശരി 7.4%, മെച്ചപ്പെടുന്നു. വൃക്ക പരിശോധന (ക്രിയാറ്റിനിൻ 1.1) സാധാരണമാണ്.",
     ["diabetes", "kidney"], [], [("hba1c", "HbA1c", 7.4, "%"), ("creatinine", "Creatinine", 1.1, "mg/dL")]),
    ("doc7", "2026-03-05", "lab", "HbA1c and lipid profile", "DDRC Agilus, Kottayam",
     "Sugar average is 7.2%, close to target. LDL dropped to 118, better but still above 100.",
     "പഞ്ചസാര ശരാശരി 7.2%, ലക്ഷ്യത്തോട് അടുത്തു. LDL 118 ആയി കുറഞ്ഞു, പക്ഷേ ഇപ്പോഴും 100-ൽ കൂടുതൽ.",
     ["diabetes", "cholesterol"], [],
     [("hba1c", "HbA1c", 7.2, "%"), ("ldl", "LDL cholesterol", 118, "mg/dL"), ("hdl", "HDL cholesterol", 46, "mg/dL"), ("fbs", "Fasting blood sugar", 128, "mg/dL")]),
    ("doc8", "2026-09-24", "prescription", "Throat infection medicines", "Dr. Anil Menon, PHC Ettumanoor",
     "Clarithromycin 500 twice a day for 7 days for throat infection. Metformin 500 was also written.",
     "തൊണ്ടയിലെ അണുബാധയ്ക്ക് 7 ദിവസം Clarithromycin 500 ദിവസം രണ്ടു നേരം. Metformin 500-ഉം എഴുതിയിട്ടുണ്ട്.",
     ["infection"],
     [{"name": "Clarithromycin 500", "generic": "clarithromycin", "dose": "500 mg", "frequency": "Twice daily", "duration": "7 days"},
      {"name": "Metformin 500", "generic": "metformin", "dose": "500 mg", "frequency": "Twice daily", "duration": "Ongoing"}],
     []),
]

MEDICINES = [
    dict(id="med1", document_id="doc2", name="Glycomet 500", generic="metformin", dose="500 mg", frequency="Twice daily",
         times=["08:00", "20:00"], instructions="After food", start_date="2024-11-12", prescribed_by="Dr. Thomas Kurian"),
    dict(id="med2", document_id="doc2", name="Telma 40", generic="telmisartan", dose="40 mg", frequency="Once daily",
         times=["08:00"], instructions="Morning, before or after food", start_date="2024-11-12", prescribed_by="Dr. Thomas Kurian"),
    dict(id="med3", document_id="doc4", name="Atorva 20", generic="atorvastatin", dose="20 mg", frequency="Once at night",
         times=["21:00"], instructions="At bedtime", start_date="2025-03-15", prescribed_by="Dr. Thomas Kurian"),
]

ALERTS = [
    dict(id="alert1", severity="high", kind="interaction", title="Clarithromycin + Atorvastatin",
         message="Clarithromycin (new, from Dr. Menon) can raise Atorva levels and cause muscle damage. Show this to your doctor before taking both. Do not stop any medicine on your own.",
         message_ml="Clarithromycin (ഡോ. മേനോൻ എഴുതിയത്) Atorva-യുടെ അളവ് കൂട്ടി പേശികൾക്ക് ദോഷം ചെയ്യാം. രണ്ടും കഴിക്കുന്നതിന് മുമ്പ് ഡോക്ടറെ കാണിക്കുക. സ്വയം മരുന്ന് നിർത്തരുത്."),
    dict(id="alert2", severity="medium", kind="duplicate", title="Metformin written twice",
         message="Metformin 500 (Dr. Menon) is the same medicine as Glycomet 500 you already take. Taking both doubles the dose. Ask your doctor which one to take.",
         message_ml="Metformin 500 (ഡോ. മേനോൻ) നിങ്ങൾ ഇപ്പോൾ കഴിക്കുന്ന Glycomet 500-ന്റെ അതേ മരുന്നാണ്. രണ്ടും കഴിച്ചാൽ ഡോസ് ഇരട്ടിയാകും. ഏത് കഴിക്കണമെന്ന് ഡോക്ടറോട് ചോദിക്കുക."),
    dict(id="alert3", severity="low", kind="lab", title="LDL cholesterol above target",
         message="Your last LDL was 118 mg/dL. Target is below 100. Discuss at your next visit.",
         message_ml="അവസാന LDL 118 mg/dL ആയിരുന്നു. ലക്ഷ്യം 100-ൽ താഴെ. അടുത്ത സന്ദർശനത്തിൽ സംസാരിക്കുക."),
]

ACCESS_LOG = [
    # (who, role, action, via, days_ago)
    ("Dr. Thomas Kurian", "Doctor", "Viewed full history", "QR scan", 190),
    ("Joseph Varghese", "Family (Son)", "Viewed medicines", "Family access", 12),
    ("Dr. Anil Menon", "Doctor", "Viewed timeline", "Share link", 7),
]


def seed_if_empty(db: Session) -> bool:
    if db.scalar(select(Patient.id).limit(1)) is not None:
        return False
    db.add(Patient(**PATIENT))
    db.flush()
    for (doc_id, date, typ, title, source, summary, summary_ml, tags, items, obs) in DOCUMENTS:
        if obs:
            items = [{"code": c, "name": n, "value": v, "unit": u} for c, n, v, u in obs]
        db.add(Document(id=doc_id, patient_id=DEMO_ID, date=date, type=typ, title=title, source=source,
                        summary=summary, summary_ml=summary_ml, tags=tags, items=items))
        db.flush()
        for c, n, v, u in obs:
            db.add(Observation(patient_id=DEMO_ID, document_id=doc_id, date=date, code=c, name=n, value=v, unit=u))
    for m in MEDICINES:
        db.add(Medicine(patient_id=DEMO_ID, **m))
    base = datetime(2026, 9, 24, 10, 30, tzinfo=timezone.utc)
    for a in ALERTS:
        db.add(Alert(patient_id=DEMO_ID, created_at=base, **a))
    now = datetime.now(timezone.utc)
    for who, role, action, via, days in ACCESS_LOG:
        db.add(AccessLog(patient_id=DEMO_ID, who=who, role=role, action=action, via=via, at=now - timedelta(days=days)))

    # Phase 5: seed reminder settings. Pre-fill the Telegram chat id from env
    # so the demo "fire reminder now" works out of the box.
    db.add(ReminderSettings(
        patient_id=DEMO_ID,
        enabled=False,  # off by default — the patient turns it on in the UI
        channel_phone=False,
        channel_telegram=bool(os.getenv("TELEGRAM_CHAT_ID")),
        channel_family=False,
        telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID"),
        family_chat_id=None,
        family_name="Joseph",
        missed_after_minutes=60,
    ))
    db.commit()
    return True
