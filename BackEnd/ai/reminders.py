"""Turn extractor medicines + follow-up into [{id,title,when,until}] reminders."""
from __future__ import annotations

import re
import uuid
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

SCHEDULE_TIMES: dict[str, list[str]] = {
    "od":  ["08:00"],
    "bd":  ["08:00", "20:00"],
    "tds": ["08:00", "14:00", "20:00"],
    "qid": ["08:00", "12:00", "16:00", "20:00"],
    "qds": ["08:00", "12:00", "16:00", "20:00"],
    "hs":  ["21:00"],
    "sos": [],
    "prn": [],
}


def parse_schedule(sched: str | None) -> list[str]:
    """Return clock times from a schedule like BD / 1-0-1 / twice daily."""
    if not sched:
        return []
    s = sched.strip().lower()

    # 1-0-1 style (morning-afternoon-night; optional 4th slot = bedtime)
    m = re.match(r"^(\d)\s*[-x]\s*(\d)\s*[-x]\s*(\d)(?:\s*[-x]\s*(\d))?$", s)
    if m:
        slots = ["08:00", "14:00", "20:00", "22:00"]
        out = []
        for i, g in enumerate(m.groups()):
            if g and int(g) > 0:
                out.append(slots[i])
        return out

    # Abbreviations (BD, TDS, etc) possibly embedded
    for tag, times in SCHEDULE_TIMES.items():
        if re.search(rf"\b{tag}\b", s):
            return list(times)

    if "once" in s or "daily" in s and "twice" not in s and "three" not in s:
        if "night" in s or "bedtime" in s or "hs" in s:
            return ["21:00"]
        return ["08:00"]
    if "twice" in s:
        return ["08:00", "20:00"]
    if "three" in s or "thrice" in s:
        return ["08:00", "14:00", "20:00"]
    if "four" in s:
        return ["08:00", "12:00", "16:00", "20:00"]
    if "bedtime" in s or "night" in s:
        return ["21:00"]
    return []


def parse_duration_days(schedule: str | None, duration: str | None) -> int | None:
    """x7d / 7 days / 1 week → number of days. None = ongoing."""
    for src in (duration, schedule):
        if not src:
            continue
        s = src.lower()
        m = re.search(r"(\d+)\s*(?:d|day|days)\b", s)
        if m:
            return int(m.group(1))
        m = re.search(r"(\d+)\s*(?:w|wk|week|weeks)\b", s)
        if m:
            return int(m.group(1)) * 7
        m = re.search(r"(\d+)\s*(?:month|months)\b", s)
        if m:
            return int(m.group(1)) * 30
        m = re.search(r"x\s*(\d+)\b", s)
        if m:
            return int(m.group(1))
    return None


def _next_occurrence(now: datetime, clock: str) -> datetime:
    hh, mm = (int(x) for x in clock.split(":"))
    today_time = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if today_time <= now:
        today_time += timedelta(days=1)
    return today_time


def build_reminders(medicines: list[dict], follow_up: str | None, start: datetime | None = None) -> list[dict]:
    now = start or datetime.now(IST)
    out: list[dict] = []

    for m in medicines:
        times = m.get("times") or parse_schedule(m.get("schedule"))
        if not times:
            continue
        days = parse_duration_days(m.get("schedule"), m.get("duration"))
        until = (now + timedelta(days=days or 90)).date().isoformat() if days else None
        label = f"{m.get('name', 'Medicine')}"
        if m.get("dose"):
            label += f" {m['dose']}"
        for clock in times:
            when = _next_occurrence(now, clock)
            out.append({
                "id": uuid.uuid4().hex[:10],
                "title": label,
                "when": when.isoformat(),
                "until": until,
                "time": clock,  # convenience for the UI
            })

    if follow_up:
        # Pull "N days" out of the follow-up text if present, else default to 7 days.
        days = parse_duration_days(None, follow_up) or 7
        when = (now + timedelta(days=days)).replace(hour=10, minute=0, second=0, microsecond=0)
        out.append({
            "id": uuid.uuid4().hex[:10],
            "title": f"Follow-up: {follow_up}",
            "when": when.isoformat(),
            "until": when.date().isoformat(),
            "time": "10:00",
        })

    out.sort(key=lambda r: r["when"])
    return out
