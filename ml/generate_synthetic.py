"""Generates synthetic training messages with Groq. The LABELS come from ml/scenarios.py, the LLM only writes wording.

    cd BackEnd && ./venv/bin/python ../ml/generate_synthetic.py            # triage messages -> ml/seed/generated_triage.jsonl
    cd BackEnd && ./venv/bin/python ../ml/generate_synthetic.py --lines    # consultation lines -> ml/seed/generated_lines.jsonl

The output is committed, so training data can be rebuilt without Groq quota. Every row is marked synthetic.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "BackEnd"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv
from groq import Groq

from scenarios import SCENARIOS

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
SEED = Path(__file__).resolve().parent / "seed"
MODEL = "openai/gpt-oss-120b"
client = Groq(api_key=os.environ["GROQ_API_KEY"], timeout=60.0)

LANGS = {
    "en": "plain English, the way an ordinary person would type or say it (some short, some longer, no medical jargon)",
    "ml-latin": "Malayalam written in English letters (Manglish), the way people text, mixed with a few English words",
    "ml": "Malayalam in Malayalam script (മലയാളം), simple everyday words",
}


def ask(prompt: str, max_tokens: int = 2500) -> str:
    for attempt in range(4):
        try:
            r = client.chat.completions.create(model=MODEL, messages=[{"role": "user", "content": prompt}],
                                               max_tokens=max_tokens, temperature=0.9, reasoning_effort="low")
            return r.choices[0].message.content or ""
        except Exception as e:
            print(f"  retry {attempt + 1}: {type(e).__name__}")
            time.sleep(4 * (attempt + 1))
    return ""


def json_list(text: str) -> list:
    m = re.search(r"\[.*\]", text, re.S)
    try:
        return json.loads(m.group(0)) if m else []
    except json.JSONDecodeError:
        return []


def triage(per_call: int = 6, workers: int = 3) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Lock

    out = SEED / "generated_triage.jsonl"
    done = {(json.loads(l)["scenario"], json.loads(l)["lang"]) for l in out.open()} if out.exists() else set()
    tasks = [(i, lang) for i in range(len(SCENARIOS)) for lang in LANGS if (i, lang) not in done]
    lock = Lock()

    def work(task):
        i, lang = task
        urg, spec, situation = SCENARIOS[i]
        prompt = (
            f"Write {per_call} different short messages that a patient or a family member might send to describe this situation: "
            f"{situation}.\nStyle: {LANGS[lang]}.\nVary age, wording and detail. Do not give advice or a diagnosis. "
            "Reply with ONLY a JSON array of strings."
        )
        rows = [t.strip() for t in json_list(ask(prompt)) if isinstance(t, str) and 8 <= len(t.strip()) <= 300]
        if lang == "ml":
            rows = [t for t in rows if re.search(r"[\u0D00-\u0D7F]", t)]
        with lock, out.open("a", encoding="utf-8") as f:
            for t in rows:
                f.write(json.dumps({"text": t, "urgency": urg, "specialist": spec, "lang": lang, "scenario": i,
                                    "synthetic": True, "source": "groq-generated"}, ensure_ascii=False) + "\n")
        print(f"scenario {i + 1}/{len(SCENARIOS)} {lang}: {len(rows)} rows", flush=True)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(work, tasks))


def lines() -> None:
    out = SEED / "generated_lines.jsonl"
    themes = ["a first visit for cough and fever", "a diabetes and blood pressure review", "knee pain and joint stiffness",
              "stomach pain and acidity", "a child's fever (parent speaking)", "chest discomfort and breathlessness",
              "a prescription change after lab results", "an allergy history discussion", "follow-up planning",
              "headache and dizziness", "a skin rash", "wrapping up the visit"]
    with out.open("w", encoding="utf-8") as f:
        for theme in themes:
            prompt = (
                f"Write 24 short lines from a doctor-patient consultation about {theme}. Mix doctor lines and patient lines. "
                "For each line give four true/false labels:\n"
                "emergency_phrase: describes an emergency symptom (chest pain, trouble breathing, fainting, stroke signs, heavy bleeding);\n"
                "mentions_allergy: talks about an allergy or reaction to a medicine;\n"
                "orders_medicine: the doctor starts, changes or stops a medicine;\n"
                "gives_follow_up: sets a follow-up visit, review date or tests to come back for.\n"
                "Make about a third of the lines have at least one true label and the rest plain (greetings, history, explanations). "
                'Reply with ONLY a JSON array of objects: {"speaker":"doctor"|"patient","text":"...","emergency_phrase":bool,"mentions_allergy":bool,"orders_medicine":bool,"gives_follow_up":bool}.'
            )
            rows = [r for r in json_list(ask(prompt, 4000)) if isinstance(r, dict) and isinstance(r.get("text"), str)]
            for r in rows:
                f.write(json.dumps({**{k: bool(r.get(k)) for k in ("emergency_phrase", "mentions_allergy", "orders_medicine", "gives_follow_up")},
                                    "speaker": r.get("speaker", "doctor"), "text": r["text"].strip(), "synthetic": True,
                                    "source": "groq-generated"}, ensure_ascii=False) + "\n")
            print(f"{theme}: {len(rows)} lines", flush=True)
            time.sleep(1.2)


if __name__ == "__main__":
    lines() if "--lines" in sys.argv else triage()
