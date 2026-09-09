#!/usr/bin/env python3
"""Holt Ausfälle / Vertretungen aus WebUntis und schreibt sie nach data/<stufe>/events.json.

Lokal ausführen – nicht als GitHub Action gedacht. Die Zugangsdaten stehen in
build/untis-config.json (siehe build/untis-config.example.json); diese Datei steht
in .gitignore und darf NICHT ins Repo.

    pip install -r build/requirements.txt
    cp build/untis-config.example.json build/untis-config.json   # dann ausfüllen
    python3 build/fetch_untis.py

Danach die Ausgabe prüfen und – wenn sie stimmt – data/**/events.json committen & pushen.
Passen die Fachkürzel aus WebUntis nicht zu den webDumbis-Kurscodes, "subjectMap" in
der Config setzen (z. B. {"GK": "gk3"}).
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

try:
    import webuntis
except ImportError:
    sys.exit("Bitte zuerst installieren:  pip install -r build/requirements.txt")

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
CONFIG_FILE = Path(__file__).resolve().parent / "untis-config.json"


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        sys.exit(f"{CONFIG_FILE} fehlt. Vorlage kopieren: "
                 f"cp build/untis-config.example.json build/untis-config.json")
    cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    for key in ("server", "school", "username", "password"):
        if not cfg.get(key):
            sys.exit(f"'{key}' fehlt in {CONFIG_FILE}")
    return cfg


def monday_of(d: date) -> date:
    return d - timedelta(days=d.weekday())


def build_period_map(session) -> dict[tuple[int, str], int]:
    """(Wochentag 0-4, 'HH:MM' Startzeit) -> Stundennummer 1..N, aus dem WebUntis-Zeitraster."""
    pmap: dict[tuple[int, str], int] = {}
    try:
        units = session.timegrid_units()
    except Exception as e:  # noqa: BLE001
        print(f"  ! Zeitraster konnte nicht geladen werden ({e}); nutze Fallback.")
        units = []
    for day in units:
        wd = getattr(day, "day", None)          # 1 = Montag … 7 = Sonntag
        for idx, unit in enumerate(getattr(day, "timeUnits", []) or [], start=1):
            start = unit.get("startTime") if isinstance(unit, dict) else getattr(unit, "start", None)
            hhmm = _fmt_untis_time(start)
            if wd and hhmm:
                pmap[(wd - 1, hhmm)] = idx
    if not pmap:
        # Fallback: gängiges Raster (1. Std ab 07:45, je 45 min, Pausen grob geschätzt)
        starts = ["07:45", "08:30", "09:35", "10:20", "11:25", "12:10",
                  "13:15", "14:00", "14:45", "15:30"]
        for wd in range(5):
            for i, s in enumerate(starts, start=1):
                pmap[(wd, s)] = i
    return pmap


def _fmt_untis_time(t) -> str:
    """WebUntis-Zeit (int HHMM oder 'HH:MM' oder datetime) -> 'HH:MM'."""
    if t is None:
        return ""
    if isinstance(t, int):
        return f"{t // 100:02d}:{t % 100:02d}"
    if isinstance(t, str) and ":" in t:
        return t[:5]
    if hasattr(t, "strftime"):
        return t.strftime("%H:%M")
    s = str(t)
    return f"{int(s) // 100:02d}:{int(s) % 100:02d}" if s.isdigit() else s


def period_number(pmap, start_dt) -> int:
    wd = start_dt.weekday()
    hhmm = start_dt.strftime("%H:%M")
    if (wd, hhmm) in pmap:
        return pmap[(wd, hhmm)]
    # nächstgelegene Startzeit desselben Wochentags
    same_day = [(v, hh) for (d, hh), v in pmap.items() if d == wd]
    if not same_day:
        return 0
    target = start_dt.hour * 60 + start_dt.minute
    return min(same_day, key=lambda x: abs(int(x[1][:2]) * 60 + int(x[1][3:]) - target))[0]


def collect(session, klassen_names, subject_map, pmap, weeks_ahead):
    events: dict[tuple, dict] = {}
    start = monday_of(date.today())
    for name in klassen_names:
        matches = session.klassen().filter(name=name)
        if not matches:
            print(f"  ! Klasse '{name}' nicht gefunden – überspringe.")
            continue
        kl = matches[0]
        for w in range(weeks_ahead):
            mon = start + timedelta(days=7 * w)
            fri = mon + timedelta(days=4)
            try:
                periods = session.timetable_extended(klasse=kl, start=mon, end=fri)
            except Exception as e:  # noqa: BLE001
                print(f"  ! {name} {mon}: {e}")
                continue
            for p in periods:
                if p.code not in ("cancelled", "irregular"):
                    continue
                subj = ""
                if p.subjects:
                    subj = getattr(p.subjects[0], "name", "") or ""
                subj = subject_map.get(subj, subj) or getattr(p, "studentGroup", "") or "?"
                teacher = getattr(p.teachers[0], "name", "") if p.teachers else ""
                orig_t = ""
                try:
                    orig_t = getattr(p.original_teachers[0], "name", "") if p.original_teachers else ""
                except Exception:  # noqa: BLE001
                    pass
                room = getattr(p.rooms[0], "name", "") if p.rooms else ""
                pnum = period_number(pmap, p.start)
                enum = period_number(pmap, p.end - timedelta(minutes=1)) or pnum
                ev = {
                    "date": p.start.date().isoformat(),
                    "period": pnum,
                    "endPeriod": max(pnum, enum),
                    "code": subj,
                    "type": "ausfall" if p.code == "cancelled" else "vertretung",
                    "teacher": orig_t or teacher,
                    "newTeacher": teacher if (orig_t and teacher and teacher != orig_t) else "",
                    "room": room,
                    "text": (getattr(p, "substText", "") or getattr(p, "lstext", "") or "").strip(),
                }
                events[(ev["date"], ev["period"], ev["code"], ev["type"])] = ev
    return sorted(events.values(), key=lambda e: (e["date"], e["period"], e["code"]))


def main():
    cfg = load_config()
    subject_map = {k: v for k, v in (cfg.get("subjectMap") or {}).items() if not k.startswith("_")}
    weeks = int(cfg.get("weeksAhead", 4))

    print(f"Login {cfg['server']} / {cfg['school']} …")
    with webuntis.Session(server=cfg["server"], school=cfg["school"],
                          username=cfg["username"], password=cfg["password"],
                          useragent="webDumbis fetch_untis").login() as s:
        pmap = build_period_map(s)
        print(f"Zeitraster: {len(pmap)} Einträge")

        for cid, ccfg in (cfg.get("cohorts") or {}).items():
            names = ccfg.get("klassen") or []
            print(f"\n[{cid}] Klassen: {names}")
            evs = collect(s, names, subject_map, pmap, weeks)
            out = DATA_DIR / cid / "events.json"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps({
                "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "source": "WebUntis",
                "events": evs,
            }, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"  {len(evs)} Einträge -> {out.relative_to(ROOT)}")
            for e in evs:
                mark = "ENTFÄLLT " if e["type"] == "ausfall" else "Vertretung"
                print(f"    {e['date']}  {e['period']}.–{e['endPeriod']}.  "
                      f"{e['code']:<6} {mark} {e['text']}")

    print("\nWenn das passt: data/**/events.json committen und pushen.")


if __name__ == "__main__":
    main()
