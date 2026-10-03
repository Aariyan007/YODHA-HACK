"""Drug interaction lookup using the DDInter data (built by scripts/build_ddi.py).

If data/ddi/ddi.sqlite doesn't exist, every function says "no data" and the caller uses the hand-written rules.
We never make up an interaction. An unknown drug just returns None.
"""
from __future__ import annotations

import sqlite3
from functools import lru_cache
from pathlib import Path

DB = Path(__file__).resolve().parents[1] / "data" / "ddi" / "ddi.sqlite"

# Names that differ between Indian/INN usage and the US names DDInter uses.
SYNONYMS = {
    "aspirin": "acetylsalicylic acid", "paracetamol": "acetaminophen", "salbutamol": "albuterol",
    "adrenaline": "epinephrine", "noradrenaline": "norepinephrine", "frusemide": "furosemide",
    "glibenclamide": "glyburide", "lignocaine": "lidocaine", "pethidine": "meperidine", "rifampicin": "rifampin",
    "cotrimoxazole": "sulfamethoxazole", "co-trimoxazole": "sulfamethoxazole", "thyroxine": "levothyroxine",
    "vitamin k": "phytonadione", "isoprenaline": "isoproterenol", "ciclosporin": "cyclosporine",
}


def normalise(name: str) -> str:
    n = " ".join((name or "").strip().lower().split())
    return SYNONYMS.get(n, n)


@lru_cache(maxsize=1)
def _con() -> sqlite3.Connection | None:
    if not DB.exists():
        return None
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, check_same_thread=False)
    return con


def available() -> bool:
    return _con() is not None


@lru_cache(maxsize=20000)
def level(a: str, b: str) -> str | None:
    """'Major', 'Moderate', 'Minor' or 'Unknown'. None if the pair isn't in the data."""
    con = _con()
    if con is None:
        return None
    x, y = sorted((normalise(a), normalise(b)))
    row = con.execute("SELECT level FROM ddi WHERE a = ? AND b = ?", (x, y)).fetchone()
    return row[0] if row else None


def known_drug(name: str) -> bool:
    con = _con()
    return bool(con and con.execute("SELECT 1 FROM drugs WHERE name = ?", (normalise(name),)).fetchone())


def info() -> dict:
    con = _con()
    if con is None:
        return {"available": False}
    return {"available": True, **dict(con.execute("SELECT key, value FROM meta").fetchall())}
