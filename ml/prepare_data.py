"""Build the Laya training and evaluation files in ml/data/ from open datasets, generated text and hand-written tests.

    cd BackEnd && ./venv/bin/python ../ml/prepare_data.py

Output (all JSONL, one example per line, the format Laya's trainer reads: state / questions / gold are JSON strings):
    train.jsonl                triage rows + consultation-line rows
    test_handwritten.jsonl     67 human-written triage messages (EN / Malayalam / Manglish), both questions
    test_gretel.jsonl          real-language symptom descriptions, specialist question only
    test_lines.jsonl           held-out consultation lines (synthetic)
    redteam.jsonl              emergencies that must never be missed
    SOURCES.json               what went in, with licences and counts

Honest limits: urgency labels come from synthetic or rule-mapped sources, specialist labels for gretel rows come from
OUR mapping of its diagnosis column (the model never outputs a diagnosis). Nothing here is clinical ground truth.
"""
from __future__ import annotations

import hashlib
import json
import random
import sys
from collections import Counter
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "BackEnd"))
sys.path.insert(0, str(Path(__file__).resolve().parent / "seed"))

from ai import laya_schema as S  # noqa: E402
import handwritten  # noqa: E402
import handwritten_train  # noqa: E402

DATA = Path(__file__).resolve().parent / "data"
RAW = DATA / "raw"
SEED = Path(__file__).resolve().parent / "seed"
HF = "https://huggingface.co/datasets"
SOURCES = {
    "gretel_train.jsonl": f"{HF}/gretelai/symptom_to_diagnosis/resolve/main/train.jsonl",
    "gretel_test.jsonl": f"{HF}/gretelai/symptom_to_diagnosis/resolve/main/test.jsonl",
    "triage500.jsonl": f"{HF}/syntech-ai/medical-triage-500/resolve/main/medical_triage_500.jsonl",
}

# gretelai/symptom_to_diagnosis: diagnosis -> (specialist id, urgency distribution). OUR mapping, weak labels.
GRETEL_MAP = {
    "cervical spondylosis": ("orthopaedician", {"routine": 0.8, "urgent": 0.2}),
    "impetigo": ("dermatologist", {"routine": 0.8, "urgent": 0.2}),
    "arthritis": ("orthopaedician", {"routine": 0.9, "self_care": 0.1}),
    "dengue": ("general_physician", {"urgent": 0.8, "emergency": 0.1, "routine": 0.1}),
    "drug reaction": ("general_physician", {"urgent": 0.7, "emergency": 0.2, "routine": 0.1}),
    "malaria": ("general_physician", {"urgent": 0.8, "emergency": 0.1, "routine": 0.1}),
    "allergy": ("general_physician", {"routine": 0.6, "self_care": 0.2, "urgent": 0.2}),
    "bronchial asthma": ("pulmonologist", {"urgent": 0.6, "routine": 0.3, "emergency": 0.1}),
    "varicose veins": ("general_physician", {"routine": 0.9, "self_care": 0.1}),
    "hypertension": ("cardiologist", {"routine": 0.8, "urgent": 0.2}),
    "psoriasis": ("dermatologist", {"routine": 0.9, "self_care": 0.1}),
    "diabetes": ("diabetologist", {"routine": 0.7, "urgent": 0.3}),
    "chicken pox": ("general_physician", {"routine": 0.6, "urgent": 0.4}),
    "urinary tract infection": ("urologist", {"routine": 0.6, "urgent": 0.4}),
    "common cold": ("general_physician", {"self_care": 0.7, "routine": 0.3}),
    "fungal infection": ("dermatologist", {"routine": 0.7, "self_care": 0.3}),
    "gastroesophageal reflux disease": ("gastroenterologist", {"routine": 0.8, "self_care": 0.2}),
    "typhoid": ("general_physician", {"urgent": 0.8, "routine": 0.2}),
    "pneumonia": ("pulmonologist", {"urgent": 0.8, "emergency": 0.2}),
    "peptic ulcer disease": ("gastroenterologist", {"routine": 0.6, "urgent": 0.4}),
    "jaundice": ("gastroenterologist", {"urgent": 0.8, "routine": 0.2}),
    "migraine": ("neurologist", {"routine": 0.7, "urgent": 0.2, "self_care": 0.1}),
}


def fetch() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    for name, url in SOURCES.items():
        path = RAW / name
        if not path.exists() or path.stat().st_size < 1000:
            print(f"downloading {name}")
            r = httpx.get(url, follow_redirects=True, timeout=60.0)
            r.raise_for_status()
            path.write_bytes(r.content)


def jl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.open(encoding="utf-8") if l.strip()]


def smooth(label: str, labels, eps: float) -> dict:
    """Hard label, or a little probability spread to the others for synthetic rows (eps=0 for human labels)."""
    labels = list(labels)
    return {k: (1 - eps) if k == label else eps / (len(labels) - 1) for k in labels}


def triage_row(text, urgency=None, specialist=None, urg_dist=None, eps=0.0, meta=None) -> dict:
    q = S.triage_questions()
    gold = {}
    if urg_dist or urgency:
        gold["urgency"] = {"probabilities": urg_dist or smooth(urgency, S.URGENCY, eps)}
    if specialist:
        gold["specialist"] = {"probabilities": smooth(specialist, S.SPECIALISTS, eps)}
    q = {k: v for k, v in q.items() if k in gold}
    return {"state": json.dumps(S.triage_state(text), ensure_ascii=False), "questions": json.dumps(q, ensure_ascii=False),
            "gold": json.dumps(gold), "meta": meta or {}}


def line_row(speaker, text, flags: dict, meta=None) -> dict:
    gold = {k: {"probabilities": {"true": 0.97 if flags.get(k) else 0.03, "false": 0.03 if flags.get(k) else 0.97}}
            for k in S.LINE_FLAGS}
    return {"state": json.dumps(S.line_state(speaker, text), ensure_ascii=False),
            "questions": json.dumps(S.line_questions()), "gold": json.dumps(gold), "meta": meta or {}}


def triage500_text(r: dict) -> tuple[str, str]:
    p, pres = r["patient"], r["presentation"]
    text = (f"{p['age']} year old {p['gender']} with {' and '.join(pres['symptoms'])} for {pres['duration']}, "
            f"{pres['onset']} onset, {pres['context']}")
    flags = set(r["risk_assessment"].get("red_flags", []))
    cat = r["triage_classification"]["urgency_category"]
    urg = "emergency" if cat == "immediate" and flags & {"chest pain", "shortness of breath"} else \
          "urgent" if cat in ("immediate", "urgent") else "routine"
    return text, urg


def keep_test(text: str) -> bool:
    return int(hashlib.sha1(text.encode()).hexdigest(), 16) % 7 == 0  # about 14% of generated rows held out


def main() -> None:
    fetch()
    DATA.mkdir(parents=True, exist_ok=True)
    train: list[dict] = []
    test_gretel: list[dict] = []
    held_gen: list[dict] = []
    counts: Counter = Counter()

    for r in jl(RAW / "gretel_train.jsonl"):
        spec, dist = GRETEL_MAP[r["output_text"].strip().lower()]
        train.append(triage_row(r["input_text"], specialist=spec, urg_dist=dist, eps=0.02, meta={"source": "gretelai/symptom_to_diagnosis", "synthetic": False, "weak_urgency": True}))
        counts["gretel_train"] += 1
    for r in jl(RAW / "gretel_test.jsonl"):
        spec, _ = GRETEL_MAP[r["output_text"].strip().lower()]
        test_gretel.append(triage_row(r["input_text"], specialist=spec, meta={"source": "gretelai/symptom_to_diagnosis"}))

    t500 = jl(RAW / "triage500.jsonl")
    random.Random(7).shuffle(t500)
    for r in t500[:250]:
        text, urg = triage500_text(r)
        train.append(triage_row(text, urgency=urg, eps=0.1, meta={"source": "syntech-ai/medical-triage-500", "synthetic": True}))
        counts["triage500"] += 1

    gen = SEED / "generated_triage.jsonl"
    for r in (jl(gen) if gen.exists() else []):
        row = triage_row(r["text"], urgency=r["urgency"], specialist=r["specialist"], eps=0.06,
                         meta={"source": "groq-generated", "synthetic": True, "lang": r["lang"]})
        (held_gen if keep_test(r["text"]) else train).append(row)
        counts[f"generated_{r['lang']}"] += 1

    hand = [triage_row(t, urgency=u, specialist=s, meta={"source": "handwritten", "lang": l}) for t, u, s, l in handwritten.TEST]
    red = [triage_row(t, urgency="emergency", meta={"source": "handwritten-redteam", "lang": l}) for t, l in handwritten.REDTEAM]

    # Person-written Malayalam / Manglish TRAINING rows. They must never appear in the held-out test or red-team sets.
    test_texts = {t.strip().lower() for t, *_ in handwritten.TEST} | {t.strip().lower() for t, _ in handwritten.REDTEAM}
    clash = [t for t, *_ in handwritten_train.TRAIN if t.strip().lower() in test_texts]
    if clash:
        raise SystemExit(f"handwritten_train.py overlaps the held-out test set (would inflate the score): {clash[:3]}")
    for t, u, sp, l in handwritten_train.TRAIN:
        for _ in range(handwritten_train.UPSAMPLE):
            train.append(triage_row(t, urgency=u, specialist=sp, meta={"source": "handwritten-train", "lang": l}))
    counts["handwritten_train"] = len(handwritten_train.TRAIN)

    lines_src = SEED / "generated_lines.jsonl"
    line_train, line_test = [], []
    for r in (jl(lines_src) if lines_src.exists() else []):
        row = line_row(r["speaker"], r["text"], r, meta={"source": "groq-generated", "synthetic": True})
        (line_test if keep_test(r["text"]) else line_train).append(row)
        counts["lines"] += 1
    train += line_train

    random.Random(11).shuffle(train)
    for name, rows in (("train", train), ("test_handwritten", hand), ("test_gretel", test_gretel), ("test_generated_held_out", held_gen),
                       ("test_lines", line_test), ("redteam", red)):
        with (DATA / f"{name}.jsonl").open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"{name}: {len(rows)} rows")
    (DATA / "SOURCES.json").write_text(json.dumps({
        "counts": dict(counts),
        "sources": {
            "gretelai/symptom_to_diagnosis": "Apache-2.0; diagnosis mapped to a specialist by our own table; urgency is a weak prior",
            "syntech-ai/medical-triage-500": "CC BY-NC 4.0 (non-commercial); synthetic; 250 rows used with 'immediate' downgraded to urgent unless a chest-pain or breathlessness red flag",
            "groq-generated": "wording by openai/gpt-oss-120b, labels from ml/scenarios.py; synthetic; 14% held out",
            "handwritten": "ml/seed/handwritten.py, written by a person, test only",
            "handwritten-train": "ml/seed/handwritten_train.py, written by a person, Malayalam + Manglish, repeated x4 in training; checked for no overlap with the test set",
        }}, indent=2))


if __name__ == "__main__":
    main()
