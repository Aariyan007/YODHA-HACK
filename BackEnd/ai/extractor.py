"""Gemini vision: image / PDF → structured JSON about a medical document."""
from __future__ import annotations

import json
import os
import re

import time

from google import genai
from google.genai import types
from google.genai.errors import ClientError, ServerError

# SPEC's gemini-2.5-flash is retired for new users. 3.8-flash is overloaded a
# lot. Try the current stable alias first and fall back to older stable flashes.
MODELS = ("gemini-flash-latest", "gemini-3.5-flash", "gemini-3.7-flash", "gemini-3.8-flash")
TIMEOUT_S = 25.0

PROMPT = """You are reading an Indian medical document (prescription, lab report, visit note, or scan report).

Return STRICTLY a single JSON object with these keys. Use null when a value is not visible.
{
  "is_medical": true|false,     // false if the image is clearly not a medical document
  "handwritten": true|false,    // true if the main content (medicines, notes) is handwritten rather than printed
  "date_of_record": "YYYY-MM-DD",
  "doctor": "Dr Full Name" | null,
  "hospital": "Clinic / Hospital name" | null,
  "type": "lab" | "visit" | "prescription" | "scan",
  "diagnoses": [string, ...],
  "medicines": [
    {"name": "brand or drug name", "dose": "500 mg", "schedule": "BD" | "1-0-1" | "TDS" | "OD" | "HS" | plain words, "times": ["08:00","20:00"], "purpose": "short reason, if written"}
  ],
  "observations": [
    {"name": "HbA1c", "plain": "3-month sugar average", "loinc": null, "value": 8.2, "unit": "%", "range": "<5.7 normal"}
  ],
  "vitals": {"bp": "132/84", "pulse": 78, "weight_kg": null, "spo2": null, "temp_f": null},
  "follow_up": "come back in 7 days if fever persists" | null,
  "source_lines": ["raw text line 1", "raw text line 2", ...]
}

Rules:
- source_lines: every readable line of the document, in order.
- Clock times: if schedule is BD/1-0-1 give ["08:00","20:00"]; TDS → ["08:00","14:00","20:00"]; OD/1-0-0 → ["08:00"]; HS/0-0-1 → ["21:00"]. Preserve what is written.
- If the image is not a medical document, return {"is_medical": false} only.
- Output ONLY JSON. No markdown fences, no commentary.
"""


class ExtractError(Exception):
    pass


def _client() -> genai.Client:
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise ExtractError("Reading documents is not set up on this server yet (the Gemini key is missing). Ask the person running MediThread to add it.")
    return genai.Client(api_key=key)


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n", "", text)
        text = re.sub(r"\n```$", "", text).strip()
    return text


def _call(client: genai.Client, data: bytes, mime: str, prompt: str | None = None) -> str:
    cfg = types.GenerateContentConfig(
        response_mime_type="application/json",
        temperature=0.2,
    )
    part = types.Part.from_bytes(data=data, mime_type=mime)
    last: Exception | None = None
    for model in MODELS:
        for attempt in range(3):
            try:
                r = client.models.generate_content(
                    model=model,
                    contents=[part, prompt or PROMPT],
                    config=cfg,
                )
                return r.text or ""
            except ServerError as e:  # 503 UNAVAILABLE — Gemini is busy
                last = e
                if attempt == 2:
                    break  # move to next model
                time.sleep(1.5 + attempt)
            except ClientError as e:
                code = getattr(e, "code", None) or getattr(e, "status_code", None)
                print(f"[extractor] {model} attempt {attempt}: ClientError code={code} {str(e)[:200]}")
                if code == 404:
                    break  # model unavailable for this account; try next
                if code == 429 and attempt < 2:
                    last = e
                    time.sleep(2.0 + attempt)
                    continue
                last = e
                break  # try next model instead of giving up
    if last:
        raise last
    return ""


def explain_error(e: Exception) -> str:
    """Plain-language reason for a failed Gemini call. 'Try a sharper photo' is only right when the call worked."""
    code = getattr(e, "code", None) or getattr(e, "status_code", None)
    text = str(e).lower()
    if code == 429 or "resource_exhausted" in text or "quota" in text:
        return "The AI reading service has used up its free limit for now. Please try again later, or use one of the test images."
    if code in (400, 401, 403) and ("api key" in text or "api_key" in text or "permission" in text or "denied" in text or code in (401, 403)):
        return "The server's Gemini key is not accepted. Whoever runs this server should check GEMINI_API_KEY in .env (keys that were shared or published get disabled)."
    if code == 404:
        return "The AI model this server asks for is not available for its key. Whoever runs this server should check the model list in ai/extractor.py."
    if isinstance(e, ServerError) or code in (500, 502, 503, 504):
        return "The AI reading service is busy right now. Please try again in a minute."
    if isinstance(e, (TimeoutError,)) or "timed out" in text or "timeout" in text:
        return "Reading the document took too long. Please try again."
    return f"Could not read the document. Please try again, or try a sharper photo. ({type(e).__name__})"


def extract(data: bytes, mime: str = "image/png") -> dict:
    """Call Gemini. Returns the parsed dict (always with is_medical).

    Raises ExtractError with a user-friendly message on any failure.
    """
    client = _client()
    try:
        raw = _call(client, data, mime)
    except Exception as e:
        print(f"[extractor] failed: {type(e).__name__} code={getattr(e, 'code', None)}")
        raise ExtractError(explain_error(e)) from e

    text = _strip_fences(raw)
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        # Retry once with a stricter nudge.
        try:
            raw = _call(client, data, mime)
            obj = json.loads(_strip_fences(raw))
        except Exception as e:
            raise ExtractError("The document could not be understood. Please try a clearer photo.") from e

    if not obj.get("is_medical", True):
        raise ExtractError(
            "This does not look like a medical document. Please upload a prescription, lab report, or visit note."
        )

    # Normalise shape — fill defaults so downstream code is simple.
    obj.setdefault("date_of_record", None)
    obj.setdefault("doctor", None)
    obj.setdefault("hospital", None)
    obj.setdefault("type", "prescription")
    obj.setdefault("diagnoses", [])
    obj.setdefault("medicines", [])
    obj.setdefault("observations", [])
    obj.setdefault("vitals", {})
    obj.setdefault("follow_up", None)
    obj.setdefault("source_lines", [])
    obj.setdefault("uncertain_medicines", [])
    if obj.get("handwritten"):  # doctors' handwriting: read again, compare, and never trust a guessed drug name
        from . import handwriting
        handwriting.second_pass(client, _call, data, mime, obj)
    return obj
