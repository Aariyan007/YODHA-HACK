"""Laya decision service: a thin HTTP wrapper around the fine-tuned Laya checkpoint.

    POST /decide   {"state": {...}, "questions": {...}}  ->  {"answers": {...}, "model": "...", "ms": 12.3}
    GET  /health   liveness + whether the model is loaded
    GET  /info     model name, evaluation summary and whether the quality gate passed

Config (env): LAYA_MODEL_DIR (default /models/laya), LAYA_FALLBACK=typed-decisions (use the Hub checkpoint if the
folder is missing; development only), LAYA_API_KEY (optional shared secret), LAYA_MIN_URGENCY_ACC (default 0.80),
LAYA_MIN_SPECIALIST_ACC (default 0.70). The gate reads <model dir>/eval_report.json, the file ml/eval.py writes.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import laya
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

MODEL_DIR = Path(os.getenv("LAYA_MODEL_DIR", "/models/laya"))
FALLBACK = os.getenv("LAYA_FALLBACK", "").strip()
API_KEY = os.getenv("LAYA_API_KEY", "").strip()
MIN_URG = float(os.getenv("LAYA_MIN_URGENCY_ACC", "0.80"))
MIN_SPEC = float(os.getenv("LAYA_MIN_SPECIALIST_ACC", "0.70"))

app = FastAPI(title="Laya decision service")
state: dict = {"agent": None, "name": None, "report": None, "error": None}


def load() -> None:
    try:
        if (MODEL_DIR / "model.safetensors").exists():
            state["agent"] = laya.load(str(MODEL_DIR), device="cpu")
            state["name"] = str(MODEL_DIR.name)
            rep = MODEL_DIR / "eval_report.json"
            state["report"] = json.loads(rep.read_text()) if rep.exists() else None
        elif FALLBACK:
            state["agent"] = laya.load("convaiinnovations/laya", device="cpu", subfolder=FALLBACK)
            state["name"] = f"hub:{FALLBACK}"
        else:
            state["error"] = f"no model at {MODEL_DIR} and LAYA_FALLBACK not set"
        if state["agent"]:
            state["agent"].warmup()
    except Exception as e:  # keep the process up so /health explains what is wrong
        state["error"] = f"{type(e).__name__}: {e}"[:200]


def gate() -> dict:
    """The quality gate: a fine-tuned checkpoint is only used if its own evaluation cleared the bar."""
    rep = state["report"]
    if state["name"] and state["name"].startswith("hub:"):
        return {"ok": False, "why": "zero-shot Hub model, not evaluated for this app"}
    if not rep:
        return {"ok": False, "why": "no eval_report.json next to the model"}
    hw = rep.get("test_handwritten", {})
    urg = hw.get("urgency", {}).get("rules_plus_model", {}).get("accuracy", 0)
    spec = rep.get("test_gretel", {}).get("specialist", {}).get("accuracy", 0)
    red = rep.get("redteam", {}).get("gate_pass", False)
    ok = urg >= MIN_URG and spec >= MIN_SPEC and red
    return {"ok": ok, "urgency_accuracy": urg, "specialist_accuracy": spec, "redteam_pass": red,
            "needs": {"urgency": MIN_URG, "specialist": MIN_SPEC}}


def auth(x_api_key: str | None = Header(default=None)) -> None:
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(401, "bad key")


class DecideBody(BaseModel):
    state: dict | list | str
    questions: dict


@app.on_event("startup")
def startup() -> None:
    load()


@app.get("/health")
def health():
    ok = state["agent"] is not None
    if not ok:
        raise HTTPException(503, state["error"] or "loading")
    return {"ok": True, "model": state["name"]}


@app.get("/info")
def info(_=Depends(auth)):
    return {"model": state["name"], "loaded": state["agent"] is not None, "error": state["error"], "gate": gate(),
            "temperature": getattr(state["agent"], "temperature", None) if state["agent"] else None}


@app.post("/decide")
def decide(body: DecideBody, _=Depends(auth)):
    if state["agent"] is None:
        raise HTTPException(503, state["error"] or "model not loaded")
    t = time.perf_counter()
    try:
        out = state["agent"].predict(body.state, body.questions)
    except Exception as e:
        raise HTTPException(422, f"{type(e).__name__}: {str(e)[:120]}")
    return {"answers": out["answers"], "model": state["name"], "ms": round((time.perf_counter() - t) * 1000, 1)}
