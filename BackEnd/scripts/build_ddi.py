"""Download DDInter (drug-drug interactions) and build BackEnd/data/ddi/ddi.sqlite.

    cd BackEnd && ./venv/bin/python scripts/build_ddi.py            # download what is missing, then build
    ./venv/bin/python scripts/build_ddi.py --no-download            # rebuild from the files already in data/ddi/raw

Source: DDInter 2.0, https://ddinter2.scbdd.com/download/ (Computational Biology & Drug Design Group, CSUT).
Licence: Creative Commons Attribution-NonCommercial-ShareAlike 4.0 (as published for DDInter downloads). Fine for
this project; do not ship it in a paid product. The downloaded files and the built database are gitignored.

Each CSV row is (DDInterID_A, Drug_A, DDInterID_B, Drug_B, Level) with Level Major / Moderate / Minor / Unknown.
"""
from __future__ import annotations

import csv
import hashlib
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ai.ddi import normalise  # noqa: E402

BASE = "https://ddinter2.scbdd.com/static/media/download/ddinter_downloads_code_{}.csv"
CODES = "ABDHLPRV"
DATA = Path(__file__).resolve().parents[1] / "data" / "ddi"
RAW = DATA / "raw"
DB = DATA / "ddi.sqlite"
MIN_BYTES = {"A": 3_000_000, "B": 800_000, "D": 1_400_000, "H": 600_000, "L": 3_500_000, "P": 250_000, "R": 1_500_000, "V": 600_000}


def download(code: str) -> Path:
    path = RAW / f"ddinter_{code}.csv"
    if path.exists() and path.stat().st_size >= MIN_BYTES[code]:
        return path
    part = path.with_suffix(".part")
    for attempt in range(1, 5):
        try:
            with httpx.stream("GET", BASE.format(code), timeout=httpx.Timeout(30.0, read=90.0), follow_redirects=True) as r:
                r.raise_for_status()
                with part.open("wb") as f:
                    for chunk in r.iter_bytes():
                        f.write(chunk)
            if part.stat().st_size < MIN_BYTES[code]:
                raise RuntimeError(f"short file ({part.stat().st_size} bytes)")
            part.rename(path)
            print(f"downloaded {path.name} ({path.stat().st_size // 1024} KB)")
            return path
        except Exception as e:
            print(f"  {code}: attempt {attempt} failed ({type(e).__name__}: {e})")
            time.sleep(2 * attempt)
    raise SystemExit(f"could not download DDInter file {code}")


def build() -> None:
    DB.unlink(missing_ok=True)
    con = sqlite3.connect(DB)
    con.executescript("""
        CREATE TABLE ddi (a TEXT NOT NULL, b TEXT NOT NULL, level TEXT NOT NULL, PRIMARY KEY (a, b)) WITHOUT ROWID;
        CREATE TABLE drugs (name TEXT PRIMARY KEY) WITHOUT ROWID;
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
    """)
    rank = {"Major": 3, "Moderate": 2, "Minor": 1, "Unknown": 0}
    pairs: dict[tuple[str, str], str] = {}
    names: set[str] = set()
    digest = hashlib.sha256()
    for code in CODES:
        path = RAW / f"ddinter_{code}.csv"
        digest.update(path.read_bytes())
        for row in csv.DictReader(path.open(encoding="utf-8-sig")):
            if not (row.get("Drug_A") and row.get("Drug_B") and row.get("Level")):
                continue
            a, b = normalise(row["Drug_A"]), normalise(row["Drug_B"])
            level = row["Level"].strip().title()
            key = tuple(sorted((a, b)))
            if level in rank and rank[level] >= rank.get(pairs.get(key, ""), -1):
                pairs[key] = level
            names |= {a, b}
    con.executemany("INSERT INTO ddi VALUES (?,?,?)", [(a, b, lv) for (a, b), lv in pairs.items()])
    con.executemany("INSERT INTO drugs VALUES (?)", [(n,) for n in sorted(names)])
    con.executemany("INSERT INTO meta VALUES (?,?)", [
        ("source", "DDInter 2.0 https://ddinter2.scbdd.com/"), ("license", "CC BY-NC-SA 4.0"),
        ("built_at", datetime.now(timezone.utc).isoformat()), ("sha256", digest.hexdigest()),
        ("pairs", str(len(pairs))), ("drugs", str(len(names)))])
    con.commit()
    counts = dict(con.execute("SELECT level, COUNT(*) FROM ddi GROUP BY level").fetchall())
    con.close()
    print(f"built {DB.name}: {len(pairs):,} pairs, {len(names):,} drugs, {counts}, {DB.stat().st_size // 1024} KB")


if __name__ == "__main__":
    RAW.mkdir(parents=True, exist_ok=True)
    if "--no-download" not in sys.argv:
        for c in CODES:
            download(c)
    build()
