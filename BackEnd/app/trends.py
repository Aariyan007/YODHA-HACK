"""Lab trend alert. Pure Python, no AI.

If a lab value has risen in each of the patient's last 3+ tests, keep ONE open
alert (kind "trend") with the real numbers. The wording states the numbers and
asks the patient to show them to a doctor. It never names a cause or a treatment.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .labs import CODE_BY_LOINC, RULES
from .models import Alert, Observation, now

MIN_RESULTS = 3
# Tests where a rising value is the worrying direction.
HIGHER_IS_WORSE = {"hba1c", "fbs", "ppbs", "ldl", "tg", "total_chol", "creatinine", "sbp", "dbp"}


def _fmt(v: float) -> str:
    return f"{v:g}"


def rising_run(values: list[float]) -> list[float]:
    """The strictly rising run that ends at the latest value (may be length 1)."""
    run = values[-1:]
    for v in reversed(values[:-1]):
        if v < run[0]:
            run.insert(0, v)
        else:
            break
    return run


def _series(rows: list[Observation]) -> list[float]:
    by_date: dict[str, float] = {}
    for o in sorted(rows, key=lambda o: o.date):  # stable: same-date rows keep insert order
        by_date[o.date] = o.value  # one result per day, the last one wins
    return [by_date[d] for d in sorted(by_date)]


_CODE_BY_NAME = {r["name"].lower(): k for k, r in RULES.items()}


def test_key(o: Observation) -> str:
    """Same test = same key: lab code, else LOINC, else name."""
    if o.code in RULES:
        return o.code
    return CODE_BY_LOINC.get(o.loinc or "") or _CODE_BY_NAME.get((o.name or "").strip().lower()) or (o.name or "").lower()


def check_trends(db: Session, patient_id: str) -> list[dict]:
    """Create or refresh trend alerts. Returns the alerts touched, as plain dicts.

    Match tests by LOINC when stored, else by lab code, else by name. Does not
    commit; the caller owns the transaction (flushes so the alert gets an id).
    """
    obs = list(db.scalars(select(Observation).where(Observation.patient_id == patient_id)))
    groups: dict[str, list[Observation]] = {}
    for o in obs:
        groups.setdefault(test_key(o), []).append(o)

    touched: list[dict] = []
    for key, rows in groups.items():
        if key not in HIGHER_IS_WORSE:
            continue
        run = rising_run(_series(rows))
        if len(run) < MIN_RESULTS:
            continue
        name = RULES[key]["name"]
        numbers = ", ".join(_fmt(v) for v in run)
        title = f"{name} is rising"
        message = f"Your {name} has risen in each of your last {len(run)} tests: {numbers}. Show this to your doctor."
        message_ml = (f"നിങ്ങളുടെ {name} അവസാന {len(run)} പരിശോധനകളിലും ഓരോ തവണയും കൂടിയിട്ടുണ്ട്: {numbers}. "
                      "ഇത് ഡോക്ടറെ കാണിക്കുക.")
        row = db.scalar(select(Alert).where(
            Alert.patient_id == patient_id, Alert.kind == "trend", Alert.title == title, Alert.resolved.is_(False)))
        if row is None:
            row = Alert(patient_id=patient_id, severity="high", kind="trend", title=title,
                        message=message, message_ml=message_ml)
            db.add(row)
        else:
            row.message, row.message_ml, row.created_at = message, message_ml, now()
        db.flush()
        touched.append({"id": row.id, "severity": row.severity, "kind": row.kind, "title": row.title,
                        "message": row.message, "messageMl": row.message_ml, "resolved": False,
                        "createdAt": row.created_at.isoformat()})
    return touched
