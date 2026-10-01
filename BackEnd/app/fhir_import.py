"""Hospital record import from a FHIR R4 Bundle (Phase 6).

Reads Patient, Encounter, Observation, Condition, MedicationStatement,
MedicationRequest (+ Medication) and DiagnosticReport. Any other resource type
is skipped without failing. Records are mapped onto the same tables as uploads
and checked with the same rules (status bands, duplicate / allergy / clash,
trend) and the same Groq summary + Malayalam step.

Dedupe: every timeline card gets a stable `external_id` built from its source
resources (type, id and a content hash). A card whose id already exists for the
patient is skipped, so importing the same bundle twice adds nothing.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime

from sqlalchemy import select

from ai import reminders as reminders_mod
from ai.jev_client import analyse
from ai.translator import summarise
from .database import SessionLocal
from .labs import CODE_BY_LOINC, RULES, loinc_for
from .models import AccessLog, Alert, Document, Medicine, Observation, Patient
from .schemas import alert_out, document_out
from .trends import check_trends

MAX_BYTES = 2 * 1024 * 1024
MAX_SUMMARIES = 12  # Groq calls are slow; later cards get the plain fallback text
LOINC_SYS = "loinc.org"
ICD10_HINT = "icd-10"  # matches .../sid/icd-10, icd-10-cm, icd-10-who, id.who.int/icd10 below
ACTIVE_MED = {"active", "intended", "on-hold", "draft", "unknown", ""}


class FhirImportError(Exception):
    """A problem the patient can fix. The message is shown as-is."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


# ---------- small FHIR readers ----------

def _date(*vals) -> str | None:
    for v in vals:
        if not isinstance(v, str):
            continue
        m = re.match(r"^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?", v)
        if m:
            y, mo, d = m.group(1), m.group(2) or "01", m.group(3) or "01"
            try:
                datetime(int(y), int(mo), int(d))
            except ValueError:
                continue
            return f"{y}-{mo}-{d}"
    return None


def _text(cc: dict | None) -> str | None:
    if not isinstance(cc, dict):
        return None
    if cc.get("text"):
        return str(cc["text"])
    for c in cc.get("coding") or []:
        if c.get("display"):
            return str(c["display"])
    return None


def _coding(cc: dict | None, system_hint: str) -> dict | None:
    for c in (cc or {}).get("coding") or []:
        if system_hint in (c.get("system") or "").lower().replace("icd10", "icd-10") and c.get("code"):
            return c
    return None


def _ref(r) -> str | None:
    """'Encounter/e1' or 'urn:uuid:..' -> normalised key."""
    if isinstance(r, dict):
        r = r.get("reference")
    if not isinstance(r, str) or not r:
        return None
    return r.split("/_history")[0]


def _display(x) -> str | None:
    if isinstance(x, dict):
        return x.get("display") or None
    return None


def _rkey(res: dict) -> str:
    """Stable id for a resource: type/id plus a short hash of its content."""
    blob = json.dumps(res, sort_keys=True, ensure_ascii=False).encode()
    return f"{res.get('resourceType')}/{res.get('id', '-')}:{hashlib.sha1(blob).hexdigest()[:10]}"


def _card_key(prefix: str, keys: list[str]) -> str:
    return f"fhir:{prefix}:{hashlib.sha1('|'.join(sorted(keys)).encode()).hexdigest()[:20]}"


# ---------- parsing ----------

def parse_bundle(raw: bytes) -> dict:
    if len(raw) > MAX_BYTES:
        raise FhirImportError("This file is bigger than 2 MB. Please send a smaller hospital export.", 413)
    try:
        bundle = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise FhirImportError("This file is not valid JSON. Please choose the hospital's FHIR .json file.")
    if not isinstance(bundle, dict) or bundle.get("resourceType") != "Bundle":
        raise FhirImportError("This is JSON, but it is not a FHIR Bundle (resourceType should be \"Bundle\").")
    if not isinstance(bundle.get("entry"), list) or not bundle["entry"]:
        raise FhirImportError("This FHIR Bundle has no records inside it.")
    return bundle


def _observations_from(res: dict) -> list[dict]:
    """One Observation resource -> list of {code, loinc, name, value, unit, date}. BP panels give two."""
    date = _date(res.get("effectiveDateTime"), (res.get("effectivePeriod") or {}).get("start"), res.get("issued"))
    out = []
    parts = [res] + [c for c in (res.get("component") or []) if isinstance(c, dict)]
    for p in parts:
        q = p.get("valueQuantity")
        if not isinstance(q, dict) or not isinstance(q.get("value"), (int, float)):
            continue
        loinc = (_coding(p.get("code"), LOINC_SYS) or {}).get("code")
        code = CODE_BY_LOINC.get(loinc or "")
        name = RULES[code]["name"] if code else (_text(p.get("code")) or "Result")
        out.append({"code": code or "unknown", "loinc": loinc or loinc_for(code), "name": name,
                    "value": float(q["value"]), "unit": q.get("unit") or q.get("code") or (RULES[code]["unit"] if code else ""),
                    "date": date})
    return out


def _is_vital(res: dict) -> bool:
    return any(c.get("code") == "vital-signs" for cat in (res.get("category") or []) for c in cat.get("coding") or [])


def _med_from(res: dict, meds_by_ref: dict[str, dict]) -> dict | None:
    cc = res.get("medicationCodeableConcept")
    if cc is None and res.get("medicationReference"):
        ref = meds_by_ref.get(_ref(res["medicationReference"]) or "")
        cc = (ref or {}).get("code")
        if not _text(cc):
            cc = {"text": _display(res["medicationReference"])}
    name = _text(cc)
    if not name:
        return None
    dose_i = (res.get("dosageInstruction") or res.get("dosage") or [{}])[0] or {}
    q = ((dose_i.get("doseAndRate") or [{}])[0] or {}).get("doseQuantity") or {}
    dose = f"{q['value']:g} {q.get('unit') or q.get('code') or ''}".strip() if isinstance(q.get("value"), (int, float)) else None
    rep = (dose_i.get("timing") or {}).get("repeat") or {}
    schedule = dose_i.get("text")
    if not schedule and rep.get("frequency") and rep.get("period") in (1, 1.0) and rep.get("periodUnit") == "d":
        schedule = {1: "Once daily", 2: "Twice daily", 3: "Three times daily", 4: "Four times daily"}.get(rep["frequency"])
    bd = rep.get("boundsDuration") or {}
    duration = f"{bd['value']:g} days" if bd.get("value") and bd.get("unit") in ("d", "day", "days") else None
    status = (res.get("status") or "").lower()
    who = (_display(res.get("requester")) or _display(res.get("informationSource")) or "")
    return {
        "name": name, "dose": dose, "schedule": schedule, "duration": duration,
        "purpose": (_text((res.get("reasonCode") or [None])[0]) if res.get("reasonCode") else None),
        "doctor": who or None, "active": status in ACTIVE_MED,
        "date": _date(res.get("authoredOn"), (res.get("effectivePeriod") or {}).get("start"),
                      res.get("effectiveDateTime"), res.get("dateAsserted")),
        "enc": _ref(res.get("encounter")) or _ref(res.get("context")),
    }


# ---------- the import ----------

def import_bundle(patient_id: str, raw: bytes) -> dict:
    bundle = parse_bundle(raw)
    fallback_date = _date(bundle.get("timestamp")) or datetime.now().date().isoformat()

    # Index resources. `refs` lets us resolve "Observation/o1" and "urn:uuid:.." links.
    ignored: dict[str, int] = {}
    by_type: dict[str, list[dict]] = {}
    refs: dict[str, dict] = {}
    ids_of: dict[int, list[str]] = {}  # id(resource) -> every reference string that points at it
    for e in bundle["entry"]:
        res = e.get("resource") if isinstance(e, dict) else None
        if not isinstance(res, dict) or not isinstance(res.get("resourceType"), str):
            continue
        rt = res["resourceType"]
        if rt not in {"Patient", "Encounter", "Observation", "Condition", "MedicationStatement",
                      "MedicationRequest", "Medication", "DiagnosticReport", "Organization", "Practitioner"}:
            ignored[rt] = ignored.get(rt, 0) + 1
            continue
        by_type.setdefault(rt, []).append(res)
        for r in (f"{rt}/{res['id']}" if res.get("id") else None, e.get("fullUrl")):
            if r:
                refs[r] = res
                ids_of.setdefault(id(res), []).append(r)
    for rt in ("Organization", "Practitioner"):  # only used to resolve names
        by_type.pop(rt, None)

    org_names = [r.get("name") for r in refs.values() if r.get("resourceType") == "Organization" and r.get("name")]
    provider_default = org_names[0] if org_names else None
    meds_by_ref = {k: v for k, v in refs.items() if v.get("resourceType") == "Medication"}

    # ---- conditions (-> patient.conditions with ICD-10) ----
    conditions = []
    for c in by_type.get("Condition", []):
        name = _text(c.get("code"))
        if not name:
            continue
        icd = (_coding(c.get("code"), ICD10_HINT) or {}).get("code")
        clinical = ((c.get("clinicalStatus") or {}).get("coding") or [{}])[0].get("code", "active")
        conditions.append({
            "name": name, "icd10": icd, "since": (_date(c.get("onsetDateTime"), c.get("recordedDate")) or "")[:4] or None,
            "status": "watch" if clinical in ("active", "recurrence", "relapse") else "good",
        })

    # ---- cards ----
    # card = {key, type, title, date, provider, doctor, tags, obs[], meds[], resource_keys[]}
    cards: dict[str, dict] = {}

    def card(cid: str, **kw) -> dict:
        return cards.setdefault(cid, {"obs": [], "meds": [], "keys": [], "tags": [], "doctor": None,
                                      "provider": provider_default, **kw})

    cond_tags = [c["name"] for c in conditions]
    for enc in by_type.get("Encounter", []):
        k = f"Encounter/{enc.get('id') or _rkey(enc)[-10:]}"
        part = ((enc.get("participant") or [{}])[0] or {}).get("individual")
        card(k, type="visit", title=_text((enc.get("type") or [None])[0]) or _text((enc.get("reasonCode") or [None])[0]) or "Hospital visit",
             date=_date((enc.get("period") or {}).get("start")) or fallback_date,
             provider=_display(enc.get("serviceProvider")) or provider_default, doctor=_display(part), tags=list(cond_tags))
        cards[k]["keys"].append(_rkey(enc))

    obs_card: dict[str, str] = {}  # Observation ref -> card id
    for dr in by_type.get("DiagnosticReport", []):
        k = f"DiagnosticReport/{dr.get('id') or _rkey(dr)[-10:]}"
        performer = _display((dr.get("performer") or [None])[0]) if dr.get("performer") else None
        card(k, type="lab", title=_text(dr.get("code")) or "Hospital report",
             date=_date(dr.get("effectiveDateTime"), (dr.get("effectivePeriod") or {}).get("start"), dr.get("issued")) or fallback_date,
             provider=performer or provider_default, tags=[])
        cards[k]["keys"].append(_rkey(dr))
        for r in dr.get("result") or []:
            obs_card[_ref(r) or ""] = k

    skipped_bad = 0
    n_obs = n_meds = 0
    for res in by_type.get("Observation", []):
        try:
            rows = _observations_from(res)
        except Exception:
            rows = []
        if not rows:
            skipped_bad += 1
            continue
        target = next((obs_card[r] for r in ids_of.get(id(res), []) if r in obs_card), None)
        enc = _ref(res.get("encounter"))
        if target is None and _is_vital(res) and enc and f"{enc}" in cards:
            target = enc
        if target is None:
            d = rows[0]["date"] or fallback_date
            target = f"results:{d}"
            card(target, type="lab", title="Hospital results", date=d, tags=[])
        for r in rows:
            r["date"] = r["date"] or cards[target]["date"]
            cards[target]["obs"].append(r)
        cards[target]["keys"].append(_rkey(res))
        n_obs += len(rows)

    for res in by_type.get("MedicationStatement", []) + by_type.get("MedicationRequest", []):
        m = _med_from(res, meds_by_ref)
        if m is None:
            skipped_bad += 1
            continue
        target = m["enc"] if m["enc"] in cards else None
        if target is None:
            d = m["date"] or fallback_date
            target = f"meds:{d}"
            card(target, type="prescription", title="Hospital prescription", date=d, doctor=m["doctor"], tags=[])
        m["date"] = m["date"] or cards[target]["date"]
        cards[target]["meds"].append(m)
        cards[target]["keys"].append(_rkey(res))
        n_meds += 1

    # Conditions live on the profile and ride along as tags on visit cards.

    with SessionLocal() as db:
        patient = db.get(Patient, patient_id)
        have = set(db.scalars(select(Document.external_id).where(Document.patient_id == patient_id, Document.external_id.is_not(None))))
        new_cards, dup_cards = [], 0
        for cid, c in cards.items():
            if not c["keys"]:
                continue
            c["external_id"] = _card_key(cid.split("/")[0].split(":")[0], c["keys"])
            if c["external_id"] in have:
                dup_cards += 1
            else:
                new_cards.append(c)

        # conditions: add when not already on the profile (match ICD-10 or name)
        known = patient.conditions or []
        have_c = {(c.get("icd10") or "").lower() for c in known} | {(c.get("name") or "").lower() for c in known}
        added_conditions = [c for c in conditions
                            if (c["icd10"] or "").lower() not in have_c and c["name"].lower() not in have_c]
        if added_conditions:
            patient.conditions = list(known) + added_conditions

        # ---- same checks as uploads, over only the NEW content ----
        new_meds = [m for c in new_cards for m in c["meds"] if m["active"]]
        new_obs = [o for c in new_cards for o in c["obs"]]
        existing = [{"name": m.name, "generic": m.generic} for m in db.scalars(
            select(Medicine).where(Medicine.patient_id == patient_id, Medicine.active.is_(True)))]
        analysis = analyse(
            patient_name=patient.name, patient_allergies=list(patient.allergies or []), existing_medicines=existing,
            new_medicines=[{"name": m["name"], "dose": m["dose"], "schedule": m["schedule"], "duration": m["duration"],
                            "purpose": m["purpose"]} for m in new_meds],
            observations=[dict(o) for o in new_obs],
        )
        status_of = {id(o): a for o, a in zip(new_obs, analysis["observations"])}
        generic_of = {id(m): a.get("generic") for m, a in zip(new_meds, analysis["medications"])}

        records = []
        summaries_left = MAX_SUMMARIES
        for c in sorted(new_cards, key=lambda c: c["date"]):
            doc_obs = [dict(o, **{k: status_of[id(o)].get(k) for k in ("status", "range")}) for o in c["obs"]]
            worst = max((o["status"] for o in doc_obs), key=["good", "watch", "alert"].index, default="good")
            doc_meds = [dict(m, generic=generic_of.get(id(m))) for m in c["meds"]]
            facts = {"hospital": c["provider"], "doctor": c["doctor"], "diagnoses": c["tags"] or [c["title"]],
                     "medicines": doc_meds, "observations": doc_obs, "follow_up": None}
            if summaries_left > 0:
                summaries_left -= 1
                summary = summarise(facts, [])
            else:
                summary = {"en": f"{c['title']} from {c['provider'] or 'the hospital'} was added to your records.", "ml": None}
            items = [{"name": o["name"], "code": o["code"], "value": o["value"], "unit": o["unit"],
                      "range": o.get("range"), "status": o.get("status")} for o in doc_obs]
            items += [{"name": m["name"], "generic": m["generic"], "dose": m["dose"], "frequency": m["schedule"],
                       "duration": m["duration"], "purpose": m["purpose"]} for m in doc_meds]
            d = Document(
                patient_id=patient_id, date=c["date"], type=c["type"], title=c["title"][:200],
                source=", ".join(x for x in (c["provider"], c["doctor"]) if x) or None,
                summary=summary["en"], summary_ml=summary["ml"], tags=c["tags"], items=items,
                status=worst, provider=c["provider"], doctor=c["doctor"], origin="fhir", external_id=c["external_id"],
            )
            db.add(d)
            db.flush()
            for o in doc_obs:
                db.add(Observation(patient_id=patient_id, document_id=d.id, date=o["date"], code=o["code"], name=o["name"],
                                   value=o["value"], unit=o["unit"], loinc=o["loinc"], source="fhir"))
            for m in doc_meds:
                db.add(Medicine(
                    patient_id=patient_id, document_id=d.id, name=m["name"], generic=m["generic"], dose=m["dose"],
                    frequency=m["schedule"], times=reminders_mod.parse_schedule(m["schedule"]), instructions=m["purpose"],
                    start_date=m["date"], prescribed_by=m["doctor"] or c["doctor"], active=m["active"],
                    duration_days=reminders_mod.parse_duration_days(m["schedule"], m["duration"]),
                ))
            records.append(d)

        alerts = []
        for a in analysis["alerts"]:
            row = Alert(patient_id=patient_id, severity=a["severity"], kind=a["kind"], title=a["title"], message=a["message"])
            db.add(row)
            db.flush()
            alerts.append(alert_out(row))
        db.flush()
        alerts += check_trends(db, patient_id)

        n_cards = len(new_cards)
        if n_cards or added_conditions:
            db.add(AccessLog(patient_id=patient_id, who=patient.name, role="Patient",
                             action="Imported hospital record", via="FHIR import"))
        db.commit()
        out_records = [document_out(d) for d in records]

    imported_obs = sum(len(c["obs"]) for c in new_cards)
    imported_meds = sum(len(c["meds"]) for c in new_cards)
    imported = {
        "timelineCards": len(new_cards), "observations": imported_obs, "conditions": len(added_conditions),
        "medicines": imported_meds,
    }
    total = imported_obs + imported_meds + len(added_conditions) + len(new_cards)
    already = bool(dup_cards) and not new_cards and not added_conditions
    if total:
        message = (f"Imported {total} records: {len(new_cards)} timeline "
                   f"{'card' if len(new_cards) == 1 else 'cards'}, {imported_obs} "
                   f"{'result' if imported_obs == 1 else 'results'}, {imported_meds} "
                   f"{'medicine' if imported_meds == 1 else 'medicines'}, {len(added_conditions)} "
                   f"{'condition' if len(added_conditions) == 1 else 'conditions'}.")
    elif already:
        message = "You already imported this hospital record. Nothing new was added."
    else:
        message = "Nothing in this file could be imported. It had no readable visits, results, conditions or medicines."
    return {
        "imported": imported, "total": total, "duplicates": dup_cards, "alreadyImported": already,
        "ignored": [{"type": t, "count": n} for t, n in sorted(ignored.items())],
        "skippedInvalid": skipped_bad, "records": out_records, "alerts": alerts, "message": message,
    }
