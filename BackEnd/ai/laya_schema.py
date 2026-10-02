"""The typed questions we put to Laya. ONE definition, shared by the backend (ai/decision.py), the training data
builder and the evaluation (ml/). Changing a label or an instruction changes what the model was trained on, so
retrain after editing this file.

Laya question types: "choice" (pick one label), "noul" (yes/no probability), "score" (ordinal).
"""
from __future__ import annotations

URGENCY = {
    "emergency": "life-threatening right now: chest pain, trouble breathing, stroke signs, heavy bleeding, fainting, severe allergic reaction, very high sugar with confusion",
    "urgent": "needs a doctor within a day: high fever, severe pain, vomiting that will not stop, sudden vision change, sugar very high",
    "routine": "needs a doctor in the next few days: ongoing symptoms, check-up, medicine refill, follow-up",
    "self_care": "mild and short-lived: common cold, slight headache, small scratch, feeling tired",
}

# id -> (display name used by the doctor finder, what it covers)
SPECIALISTS = {
    "general_physician": ("General Physician", "fever, cold, general weakness, infections, anything unclear"),
    "cardiologist": ("Cardiologist", "heart, chest pain, palpitations, blood pressure"),
    "diabetologist": ("Diabetologist", "blood sugar, diabetes, thirst, frequent urination"),
    "nephrologist": ("Nephrologist", "kidney, creatinine, swelling of feet"),
    "pulmonologist": ("Pulmonologist", "breathing, cough, wheeze, asthma, chest infection"),
    "gastroenterologist": ("Gastroenterologist", "stomach, liver, vomiting, diarrhoea, acidity, jaundice"),
    "endocrinologist": ("Endocrinologist", "thyroid, hormones, weight changes"),
    "haematologist": ("Haematologist", "anaemia, low platelets, bleeding disorders"),
    "neurologist": ("Neurologist", "headache, migraine, seizure, numbness, dizziness, stroke"),
    "orthopaedician": ("Orthopaedician", "bones, joints, back pain, knee, neck pain, fractures"),
    "gynaecologist": ("Gynaecologist", "periods, pregnancy, women's health"),
    "paediatrician": ("Paediatrician", "babies and children"),
    "dermatologist": ("Dermatologist", "skin, rash, itching, fungal infection"),
    "ophthalmologist": ("Ophthalmologist", "eye, vision"),
    "ent": ("ENT specialist", "ear, nose, throat, hearing, sinus"),
    "psychiatrist": ("Psychiatrist", "mood, anxiety, stress, sleep problems"),
    "urologist": ("Urologist", "urine, prostate, kidney stones"),
    "dentist": ("Dentist", "teeth and gums"),
}
SPECIALIST_NAME = {k: v[0] for k, v in SPECIALISTS.items()}
NAME_TO_ID = {v[0]: k for k, v in SPECIALISTS.items()}


def triage_questions() -> dict:
    return {
        "urgency": {"type": "choice", "instructions": "How urgent is this person's problem?", "criteria": dict(URGENCY)},
        "specialist": {"type": "choice", "instructions": "Which type of doctor should this person see?",
                       "criteria": {k: v[1] for k, v in SPECIALISTS.items()}},
    }


def triage_state(text: str) -> dict:
    return {"patient_message": (text or "").strip()[:600]}


# Consultation lines: several yes/no questions answered in one pass.
LINE_FLAGS = {
    "emergency_phrase": "Does this line describe an emergency symptom, such as chest pain, trouble breathing, fainting, stroke signs or heavy bleeding?",
    "mentions_allergy": "Does this line talk about an allergy or a reaction to a medicine?",
    "orders_medicine": "Is the doctor starting, changing or stopping a medicine in this line?",
    "gives_follow_up": "Does this line set a follow-up visit, review date or tests to come back for?",
}


def line_questions() -> dict:
    return {k: {"type": "noul", "instructions": v} for k, v in LINE_FLAGS.items()}


def line_state(speaker: str, text: str) -> dict:
    return {"speaker": speaker if speaker in ("doctor", "patient") else "doctor", "line": (text or "").strip()[:400]}
