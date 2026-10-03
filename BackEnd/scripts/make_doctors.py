"""Writes BackEnd/data/doctors.json: a FICTIONAL, Kerala heavy doctor directory for the demo.

Every name, clinic, phone number and review is made up. Coordinates are real town centres with a small random
offset so pins don't stack. It's seeded, so running it again gives the same file.

    cd BackEnd && ./venv/bin/python scripts/make_doctors.py
"""
from __future__ import annotations

import json
import random
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "data" / "doctors.json"
# Same file for the frontend's mock mode and the offline single-file build.
FRONT = Path(__file__).resolve().parents[2] / "Frontend" / "src" / "data" / "doctors.sample.json"
rng = random.Random(2026)

# (town, district, state, lat, lng, weight), weight = how many practices to put there.
KERALA = [
    ("Kochi", "Ernakulam", "Kerala", 9.9312, 76.2673, 7), ("Kakkanad", "Ernakulam", "Kerala", 10.0159, 76.3419, 3),
    ("Edappally", "Ernakulam", "Kerala", 10.0261, 76.3083, 3), ("Aluva", "Ernakulam", "Kerala", 10.1076, 76.3516, 2),
    ("Muvattupuzha", "Ernakulam", "Kerala", 9.9894, 76.5790, 2),
    ("Thiruvananthapuram", "Thiruvananthapuram", "Kerala", 8.5241, 76.9366, 6),
    ("Kazhakkoottam", "Thiruvananthapuram", "Kerala", 8.5686, 76.8731, 2),
    ("Kozhikode", "Kozhikode", "Kerala", 11.2588, 75.7804, 5), ("Thrissur", "Thrissur", "Kerala", 10.5276, 76.2144, 5),
    ("Chalakudy", "Thrissur", "Kerala", 10.3070, 76.3330, 2), ("Kottayam", "Kottayam", "Kerala", 9.5916, 76.5222, 4),
    ("Pala", "Kottayam", "Kerala", 9.7130, 76.6830, 2), ("Changanassery", "Kottayam", "Kerala", 9.4440, 76.5400, 2),
    ("Kollam", "Kollam", "Kerala", 8.8932, 76.6141, 3), ("Kottarakkara", "Kollam", "Kerala", 9.0040, 76.7730, 2),
    ("Alappuzha", "Alappuzha", "Kerala", 9.4981, 76.3388, 3), ("Kannur", "Kannur", "Kerala", 11.8745, 75.3704, 3),
    ("Palakkad", "Palakkad", "Kerala", 10.7867, 76.6548, 3), ("Malappuram", "Malappuram", "Kerala", 11.0510, 76.0711, 2),
    ("Perinthalmanna", "Malappuram", "Kerala", 10.9760, 76.2254, 2), ("Tirur", "Malappuram", "Kerala", 10.9150, 75.9220, 2),
    ("Pathanamthitta", "Pathanamthitta", "Kerala", 9.2648, 76.7870, 2), ("Thodupuzha", "Idukki", "Kerala", 9.8959, 76.7184, 2),
    ("Kalpetta", "Wayanad", "Kerala", 11.6085, 76.0830, 2), ("Kasaragod", "Kasaragod", "Kerala", 12.4996, 74.9869, 2),
]
INDIA = [
    ("Bengaluru", "Bengaluru Urban", "Karnataka", 12.9716, 77.5946, 3), ("Chennai", "Chennai", "Tamil Nadu", 13.0827, 80.2707, 3),
    ("Mumbai", "Mumbai", "Maharashtra", 19.0760, 72.8777, 2), ("New Delhi", "New Delhi", "Delhi", 28.6139, 77.2090, 2),
    ("Hyderabad", "Hyderabad", "Telangana", 17.3850, 78.4867, 2), ("Mangaluru", "Dakshina Kannada", "Karnataka", 12.9141, 74.8560, 2),
    ("Coimbatore", "Coimbatore", "Tamil Nadu", 11.0168, 76.9558, 2), ("Madurai", "Madurai", "Tamil Nadu", 9.9252, 78.1198, 1),
    ("Mysuru", "Mysuru", "Karnataka", 12.2958, 76.6394, 1), ("Pune", "Pune", "Maharashtra", 18.5204, 73.8567, 1),
    ("Kolkata", "Kolkata", "West Bengal", 22.5726, 88.3639, 1), ("Nagercoil", "Kanyakumari", "Tamil Nadu", 8.1833, 77.4119, 1),
]

KERALA_FIRST = ["Anil", "Priya", "Thomas", "Fathima", "Suresh", "Deepa", "Joseph", "Lakshmi", "Abdul", "Sreeja",
                "George", "Anitha", "Rajesh", "Mini", "Haris", "Divya", "Biju", "Shalini", "Mathew", "Reshma",
                "Vinod", "Asha", "Shibu", "Nisha", "Rahul", "Soumya", "Jacob", "Ramya", "Faisal", "Teena",
                "Hari", "Neethu", "Arun", "Bindu", "Sajan", "Gopika", "Zainab", "Manoj", "Elizabeth", "Prakash"]
KERALA_LAST = ["Nair", "Menon", "Pillai", "Kurian", "Mathew", "Varghese", "Rahman", "Nambiar", "Krishnan", "Jose",
               "Philip", "Antony", "Raghavan", "Varma", "Muhammed", "Thomas", "Panicker", "Kutty", "George", "Das"]
INDIA_FIRST = ["Arjun", "Kavya", "Rohit", "Meera", "Sanjay", "Ananya", "Vikram", "Pooja", "Karthik", "Sneha",
               "Imran", "Divya", "Aditya", "Nandini", "Ravi", "Shreya"]
INDIA_LAST = ["Rao", "Iyer", "Sharma", "Reddy", "Gupta", "Shetty", "Patel", "Bose", "Hegde", "Singh", "Kulkarni", "Naidu"]

CLINIC_WORDS = ["Sahya", "Periyar", "Nila", "Malabar", "Sree", "Hill View", "Lakeside", "Green Valley", "Sunrise",
                "Kairali", "Coastal", "Harmony", "CareWell", "Lotus", "Bharath", "Anugraha", "Santhwanam", "Arogya"]

SPECIALTIES = {
    "General Physician": 9, "Cardiologist": 5, "Diabetologist": 4, "Nephrologist": 2, "Pulmonologist": 2,
    "Gastroenterologist": 2, "Endocrinologist": 2, "Haematologist": 1, "Neurologist": 2, "Orthopaedician": 2,
    "Gynaecologist": 2, "Paediatrician": 2, "Dermatologist": 1, "Ophthalmologist": 1, "ENT specialist": 1,
    "Psychiatrist": 1, "Urologist": 1, "Dentist": 1,
}
CLINIC_SUFFIX = {
    "General Physician": "Family Clinic", "Cardiologist": "Heart Clinic", "Diabetologist": "Diabetes Centre",
    "Nephrologist": "Kidney Care", "Pulmonologist": "Chest Clinic", "Gastroenterologist": "Gut & Liver Clinic",
    "Endocrinologist": "Thyroid & Hormone Clinic", "Haematologist": "Blood Care Clinic", "Neurologist": "Neuro Clinic",
    "Orthopaedician": "Bone & Joint Clinic", "Gynaecologist": "Women's Clinic", "Paediatrician": "Children's Clinic",
    "Dermatologist": "Skin Clinic", "Ophthalmologist": "Eye Clinic", "ENT specialist": "ENT Clinic",
    "Psychiatrist": "Mind Clinic", "Urologist": "Urology Clinic", "Dentist": "Dental Studio",
}

PRAISE = [
    "Listens patiently and explains everything in simple words.",
    "Explained my reports clearly and did not rush.",
    "Very kind with elderly patients. My mother felt at ease.",
    "Spoke to us in Malayalam, which made it much easier.",
    "Clean clinic, short wait, and the staff were helpful.",
    "Gave a clear plan and called back to check on us.",
    "Did not order unnecessary tests. Honest doctor.",
    "Very experienced. Spotted something others missed.",
    "Reasonable fees and good follow-up on WhatsApp.",
    "Took time to answer all our questions.",
]
GRIPE = [
    "Waiting time can be long in the evenings.",
    "Parking is difficult near the clinic.",
    "Appointments get booked out quickly.",
    "Consultation is short when the clinic is busy.",
    "Fees are a little on the higher side.",
    "Phone line is often busy; better to go in person.",
]
EMERGENCY_PRAISE = [
    "Emergency team acted fast when my father had chest pain.",
    "24-hour casualty with a doctor always present.",
    "ICU staff kept us informed at every step.",
]

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def jitter(v: float, amt: float = 0.018) -> float:
    return round(v + rng.uniform(-amt, amt), 5)


def hours(open_sunday: bool, evening: bool) -> dict:
    start = rng.choice(["08:00", "08:30", "09:00", "09:30", "10:00"])
    end = rng.choice(["13:00", "17:00", "18:00", "19:00", "20:00", "21:00"] if evening else ["13:00", "16:00", "17:00"])
    h = {d: f"{start}-{end}" for d in DAYS[:6]}
    h["sun"] = f"{start}-13:00" if open_sunday else None
    return h


def languages(state: str) -> list[str]:
    base = {"Kerala": ["Malayalam", "English"], "Tamil Nadu": ["Tamil", "English"], "Karnataka": ["Kannada", "English"],
            "Maharashtra": ["Marathi", "Hindi", "English"], "Delhi": ["Hindi", "English"], "Telangana": ["Telugu", "Hindi", "English"],
            "West Bengal": ["Bengali", "Hindi", "English"]}[state]
    extra = []
    if state == "Kerala":
        extra = rng.sample(["Hindi", "Tamil", "Arabic"], k=rng.choice([0, 1, 1, 2]))
    elif rng.random() < 0.35:
        extra = ["Malayalam"]  # many Malayali doctors outside Kerala
    return base + [x for x in extra if x not in base]


_DECK: list[str] = []


def pick_specialty(i: int, town_slots: int) -> str:
    """The first practice in every town is a GP, the rest come from a shuffled, weighted deck of other specialties."""
    if i == 0:
        return "General Physician"
    if not _DECK:
        _DECK.extend(s for s, w in SPECIALTIES.items() if s != "General Physician" for _ in range(w))
        rng.shuffle(_DECK)
    return _DECK.pop()


def phone(n: int) -> str:
    # 00000 block: not a real Indian mobile range. Shown as a sample.
    return f"+91 00000 {10000 + n:05d}"


def make() -> list[dict]:
    out: list[dict] = []
    n = 0
    used_names: set[str] = set()
    for towns, first, last in ((KERALA, KERALA_FIRST, KERALA_LAST), (INDIA, INDIA_FIRST, INDIA_LAST)):
        for town, district, state, lat, lng, slots in towns:
            for i in range(slots):
                n += 1
                spec = pick_specialty(i, slots)
                while True:
                    name = f"Dr. {rng.choice(first)} {rng.choice(last)}"
                    if name not in used_names:
                        used_names.add(name)
                        break
                # The last slot in towns with 3+ practices is a multi-specialty hospital with 24x7 casualty.
                hospital = slots >= 3 and i == slots - 1 or (slots == 2 and i == 1 and rng.random() < 0.5)
                word = rng.choice(CLINIC_WORDS)
                if hospital:
                    clinic = f"{word} {'Multispeciality Hospital' if rng.random() < 0.6 else 'Medical Centre'}"
                    specs = sorted({spec, "Emergency", "General Physician", "Cardiologist",
                                    *rng.sample(list(SPECIALTIES), k=3)})
                else:
                    clinic = f"{word} {CLINIC_SUFFIX[spec]}"
                    specs = [spec] + (["Diabetologist"] if spec == "General Physician" and rng.random() < 0.4 else [])
                rating = round(min(4.9, max(3.4, rng.gauss(4.3, 0.35))), 1)
                reviews = int(rng.choice([rng.randint(8, 60), rng.randint(60, 300), rng.randint(300, 1400)]))
                snippets = rng.sample(PRAISE, k=2) + [rng.choice(GRIPE)]
                if hospital:
                    snippets = [rng.choice(EMERGENCY_PRAISE)] + snippets[1:]  # keep one praise + the gripe
                out.append({
                    "id": f"doc{n:03d}",
                    "name": name,
                    "specialty": spec,
                    "specialties": specs,
                    "clinic": clinic,
                    "type": "hospital" if hospital else "clinic",
                    "address": f"{rng.randint(1, 48)}/{rng.randint(100, 999)}, {rng.choice(['MG Road', 'Market Road', 'Hospital Road', 'Church Road', 'Temple Road', 'Bypass Road', 'Station Road', 'NH Junction'])}, {town}",
                    "city": town, "district": district, "state": state,
                    "lat": jitter(lat), "lng": jitter(lng),
                    "rating": rating, "reviews": reviews, "reviewSnippets": snippets,
                    "experienceYears": rng.randint(4, 32),
                    "feeInr": 0 if rng.random() < 0.06 else rng.choice([200, 300, 350, 400, 500, 600, 700, 800, 1000]),
                    "languages": languages(state),
                    "hours": {d: "00:00-23:59" for d in DAYS} if hospital else hours(rng.random() < 0.3, rng.random() < 0.7),
                    "emergency24x7": hospital,
                    "teleconsult": rng.random() < 0.45,
                    "waitMinutes": rng.choice([10, 15, 20, 30, 45, 60]),
                    "phone": phone(n),
                    "sample": True,
                })
    return out


if __name__ == "__main__":
    docs = make()
    OUT.parent.mkdir(exist_ok=True)
    payload = {"note": "FICTIONAL sample data for the MediThread demo. Names, clinics, phone numbers and "
                       "reviews are made up. Do not use for real care.", "doctors": docs}
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1))
    FRONT.write_text(json.dumps(payload, ensure_ascii=False))
    kerala = sum(d["state"] == "Kerala" for d in docs)
    print(f"Wrote {len(docs)} doctors ({kerala} in Kerala) to {OUT}")
