"""Repair lab results that were filed under the wrong test before the index-test fix in app/labs.py.

An index test like "Mean Platelet Volume" (fL) or "Mean Corpuscular Haemoglobin" (pg) used to be filed under the main
test (platelets, haemoglobin) because its name contains that word. This gives those rows their own code, fixes the same
items on the timeline cards, re-runs the danger and trend checks for the patients touched, and closes lab alerts that
were only raised because of the wrong rule. It only touches rows whose NAME is an index test, nothing else.

    docker compose exec -T backend python scripts/fix_lab_codes.py            # dry run: print what would change
    docker compose exec -T backend python scripts/fix_lab_codes.py --apply    # write the changes
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.labs import RULES, _INDEX_TEST, lab_status, slug  # noqa: E402
from app.models import Alert, Document, Observation  # noqa: E402


def wrong(code: str | None, name: str | None) -> bool:
    return bool(code in RULES and name and _INDEX_TEST.search(name.lower()))


def main(apply: bool) -> None:
    from app import risk, trends
    with SessionLocal() as db:
        patients: set[str] = set()
        fixed_names: dict[str, set[str]] = {}
        for o in db.scalars(select(Observation)):
            if wrong(o.code, o.name):
                new = slug(o.name)
                print(f"observation {o.id}: {o.name!r} {o.value} {o.unit} code {o.code} -> {new}")
                patients.add(o.patient_id)
                fixed_names.setdefault(o.patient_id, set()).add(o.name)
                if apply:
                    o.code, o.loinc = new, None
        for d in db.scalars(select(Document)):
            items, changed = [], False
            for it in d.items or []:
                it = dict(it)
                if "value" in it and wrong(it.get("code"), it.get("name")):
                    print(f"document {d.id}: item {it.get('name')!r} code {it.get('code')} -> {slug(it.get('name'))}")
                    it["code"] = slug(it.get("name"))
                    it.pop("status", None)   # recomputed from the printed range when the card is shown
                    patients.add(d.patient_id)
                    changed = True
                items.append(it)
            if changed and apply:
                d.items = items
        for pid in patients:
            for a in db.scalars(select(Alert).where(Alert.patient_id == pid, Alert.kind == "lab", Alert.resolved.is_(False))):
                for name in fixed_names.get(pid, ()):
                    if a.title.lower().startswith(name.lower()):
                        last = db.scalar(select(Observation).where(Observation.patient_id == pid, Observation.name == name)
                                         .order_by(Observation.date.desc()))
                        rng = getattr(last, "ref_range", None)
                        ok = last is not None and lab_status(slug(name), float(last.value), rng) == "good"
                        print(f"alert {a.id}: {a.title!r} -> {'resolve (value is inside its printed range)' if ok else 'keep'}")
                        if ok and apply:
                            a.resolved = True
            if apply:
                db.flush()
                risks, _ = risk.refresh_risk_alerts(db, pid)
                trends.check_trends(db, pid)
                print(f"patient {pid}: danger checks re-run, {len(risks)} risk(s) now")
        if apply:
            db.commit()
            print("applied")
        else:
            print(f"dry run: {len(patients)} patient(s) would change. Run with --apply to write.")


if __name__ == "__main__":
    main("--apply" in sys.argv)
