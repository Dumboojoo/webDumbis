#!/usr/bin/env python3
"""Vergleicht die eigenen Kurscodes aus dem Schul-PDF mit dem aktuellen Stand in
WebUntis und schlägt Einträge für build/course-code-overrides.json vor, wenn die
Schule einen Kurs umbenannt hat (Stundenplan und Lehrkraft bleiben gleich, nur der
Code ändert sich, z. B. "d2" -> "d3").

Grundsatz wie überall bei webDumbis: nichts wird automatisch als "richtig" angenommen.
Das Skript zeigt für jede Stunde PDF-Stand und WebUntis-Stand nebeneinander und schlägt
eine Umbenennung nur vor, wenn die Lehrkraft an der Stunde übereinstimmt (nur der Code
unterscheidet sich). Übernommen wird eine Umbenennung erst nach Bestätigung – und selbst
dann bitte den Report von parse_pdfs.py danach noch mal quer lesen, bevor committet wird.

Einfach starten:

    python3 build/check_course_codes.py

Beim ersten Mal fragt das Skript nach Schule, Login, Stufe und der eigenen
webDumbis-Schülernummer und speichert das in build/untis-config.json (steht in
.gitignore, kommt also NICHT ins Repo).
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date, timedelta
from getpass import getpass
from pathlib import Path

try:
    import requests
    import webuntis
except ImportError:
    sys.exit("Einmalig installieren:  pip3 install -r build/requirements.txt")

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
BUILD_DIR = Path(__file__).resolve().parent
CONFIG = BUILD_DIR / "untis-config.json"
CODE_OVERRIDE_FILE = BUILD_DIR / "course-code-overrides.json"
SCHOOLQUERY = "https://mobile.webuntis.com/ms/schoolquery2"
DAYS = ["Mo", "Di", "Mi", "Do", "Fr"]


# --------------------------------------------------------------------- Setup
def search_schools(name: str) -> list[dict]:
    r = requests.post(SCHOOLQUERY, timeout=15, headers={"User-Agent": "webDumbis"},
                      json={"id": "1", "method": "searchSchool", "jsonrpc": "2.0",
                            "params": [{"search": name}]})
    r.raise_for_status()
    return r.json().get("result", {}).get("schools", [])


def ask_school() -> dict:
    while True:
        q = input("Schulname (Teil reicht, z. B. Schmitthenner): ").strip()
        if not q:
            sys.exit("Abgebrochen.")
        try:
            hits = search_schools(q)
        except Exception as e:  # noqa: BLE001
            print(f"  Schulsuche geht gerade nicht ({e}).")
            url = input("  WebUntis-Adresse einfügen (…webuntis.com/WebUntis/?school=…): ").strip()
            try:
                host = url.split("//", 1)[1].split("/", 1)[0]
                school = url.split("?school=", 1)[1].split("#", 1)[0].split("&", 1)[0]
                return {"server": host, "loginName": school, "displayName": school}
            except Exception:  # noqa: BLE001
                print("  Konnte die Adresse nicht lesen, nochmal.")
                continue
        if not hits:
            print("  Nichts gefunden, nochmal.")
            continue
        if len(hits) == 1:
            return hits[0]
        for i, s in enumerate(hits, 1):
            print(f"  [{i}] {s['displayName']} – {s.get('address', '')}")
        try:
            return hits[int(input("  Nummer: ")) - 1]
        except (ValueError, IndexError):
            print("  Ungültig, nochmal.")


def run_setup() -> dict:
    print("== WebUntis einrichten (nur beim ersten Mal) ==")
    sc = ask_school()
    print(f"  Schule: {sc['displayName']}")
    username = input("WebUntis-Benutzername: ").strip()
    password = getpass("WebUntis-Passwort (wird lokal in untis-config.json gespeichert): ")
    stufe = ""
    while stufe not in ("k1", "k2"):
        stufe = input("Deine Stufe – k1 oder k2: ").strip().lower()
    student_nr = ""
    while not re.match(r"^\d+$", student_nr):
        student_nr = input("Deine Schülernummer wie auf webDumbis (z. B. 042): ").strip()
    cfg = {
        "server": sc["server"], "school": sc["loginName"],
        "displayName": sc["displayName"], "username": username, "password": password,
        "cohort": stufe, "studentNr": student_nr,
    }
    CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  Gespeichert in build/{CONFIG.name}\n")
    return cfg


def load_config() -> dict:
    if not CONFIG.exists():
        return run_setup()
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    if not cfg.get("password"):
        cfg["password"] = getpass(f"Passwort für {cfg.get('username', '?')}: ")
    if not cfg.get("studentNr"):
        cfg["studentNr"] = input("Deine Schülernummer wie auf webDumbis (z. B. 042): ").strip()
        CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")
    return cfg


# ------------------------------------------------------------------- Zeitraster
def _hhmm(t) -> str:
    if t is None:
        return ""
    if isinstance(t, int):
        return f"{t // 100:02d}:{t % 100:02d}"
    if hasattr(t, "strftime"):
        return t.strftime("%H:%M")
    s = str(t)
    return f"{int(s) // 100:02d}:{int(s) % 100:02d}" if s.isdigit() else s[:5]


def build_period_map(session) -> dict[str, int]:
    pmap: dict[str, int] = {}
    try:
        for day in session.timegrid_units():
            for idx, unit in enumerate(getattr(day, "timeUnits", []) or [], start=1):
                start = unit.get("startTime") if isinstance(unit, dict) else getattr(unit, "start", None)
                hh = _hhmm(start)
                if hh:
                    pmap.setdefault(hh, idx)
    except Exception as e:  # noqa: BLE001
        print(f"  Hinweis: Zeitraster nicht abrufbar ({e}), nutze Standardraster.")
    if not pmap:
        for i, hh in enumerate(["07:45", "08:30", "09:35", "10:20", "11:25", "12:10",
                                "13:15", "14:00", "14:45", "15:30"], start=1):
            pmap[hh] = i
    return pmap


def period_number(pmap: dict, dt) -> int:
    target = dt.hour * 60 + dt.minute
    slots = sorted((int(k[:2]) * 60 + int(k[3:]), v) for k, v in pmap.items())
    best = slots[0][1] if slots else 0
    for m, v in slots:
        if m <= target + 1:
            best = v
        else:
            break
    return best


# -------------------------------------------------------------- lokale Daten
def load_local(cohort: str, student_nr: str) -> tuple[dict, dict]:
    students = json.loads((DATA_DIR / cohort / "students.json").read_text(encoding="utf-8"))
    courses = json.loads((DATA_DIR / cohort / "courses.json").read_text(encoding="utf-8"))
    by_nr = {s["nr"]: s for s in students["students"]}
    by_code = {c["code"]: c for c in courses["courses"]}
    if student_nr not in by_nr:
        sys.exit(f"Schülernummer {student_nr} gibt es in data/{cohort}/students.json nicht.")
    return by_nr[student_nr], by_code


def guess_code(group: str, subject: str) -> str:
    """Aus dem WebUntis-'studentGroup'/Fach-Feld den reinen Kurscode extrahieren, z. B.
    '11D3' oder 'K2-D3' -> 'd3'. Grobe Heuristik, wird im Report immer mit angezeigt,
    damit man's von Auge gegenchecken kann."""
    raw = (group or subject or "").strip()
    m = re.search(r"([A-Za-zÄÖÜäöüß]{1,5}\d{0,2})$", raw)
    return (m.group(1) if m else raw).lower()


# ------------------------------------------------------------------- Abgleich
def compare(session, cfg, pmap, student, by_code):
    monday = date.today() - timedelta(days=date.today().weekday())
    periods = None
    for w in range(4):  # notfalls bis zu 4 Wochen weitersuchen (Ferienwoche o.ä.)
        mon = monday + timedelta(days=7 * w)
        try:
            p = session.my_timetable(start=mon, end=mon + timedelta(days=4))
        except Exception as e:  # noqa: BLE001
            sys.exit(f"Stundenplan konnte nicht geladen werden: {e}")
        if p:
            periods = p
            print(f"Vergleiche mit der Woche ab {mon.isoformat()}.\n")
            break
    if not periods:
        sys.exit("Keine Stunden in den nächsten 4 Wochen gefunden (Ferien?). Später nochmal versuchen.")

    rows = []
    for p in periods:
        day_idx = p.start.weekday()
        if day_idx > 4:
            continue
        pn = period_number(pmap, p.start)
        cell = (student["timetable"].get(DAYS[day_idx]) or [None] * 10)
        cell = cell[pn - 1] if 0 < pn <= len(cell) else None
        local_code = cell["code"] if cell else ""
        local_course = by_code.get(local_code, {})
        local_teacher = local_course.get("teacher", "")

        untis_teacher = getattr(p.teachers[0], "name", "") if getattr(p, "teachers", None) else ""
        untis_group = getattr(p, "studentGroup", "") or ""
        untis_subject = getattr(p.subjects[0], "name", "") if getattr(p, "subjects", None) else ""
        guessed = guess_code(untis_group, untis_subject)

        teacher_matches = bool(untis_teacher) and untis_teacher.lower() in local_teacher.lower()
        code_differs = bool(guessed) and guessed != local_code.lower()

        rows.append({
            "day": DAYS[day_idx], "period": pn,
            "local_code": local_code, "local_teacher": local_teacher,
            "untis_group": untis_group, "untis_subject": untis_subject,
            "untis_teacher": untis_teacher, "guessed": guessed,
            "teacher_matches": teacher_matches, "code_differs": code_differs,
        })
    rows.sort(key=lambda r: (DAYS.index(r["day"]), r["period"]))
    return rows


def print_report(rows):
    print(f"{'Tag':<4} {'Std.':<5} {'PDF-Code':<10} {'PDF-Lehrkraft':<18} "
          f"{'WebUntis-Gruppe':<18} {'WebUntis-Lehrkraft':<18}")
    for r in rows:
        flag = "  <-- Code weicht ab, Lehrkraft passt" if (r["code_differs"] and r["teacher_matches"]) else ""
        print(f"{r['day']:<4} {r['period']:<5} {r['local_code'] or '–':<10} "
              f"{r['local_teacher'] or '–':<18} {r['untis_group'] or r['untis_subject'] or '–':<18} "
              f"{r['untis_teacher'] or '–':<18}{flag}")


def collect_proposals(rows) -> dict[str, dict]:
    """Gruppiert übereinstimmende Zeilen zu Vorschlägen alter Code -> neuer Code."""
    proposals: dict[str, dict] = {}
    conflicts: set[str] = set()
    for r in rows:
        if not (r["code_differs"] and r["teacher_matches"]):
            continue
        old, new = r["local_code"], r["guessed"]
        if old in proposals and proposals[old]["new"] != new:
            conflicts.add(old)
            continue
        p = proposals.setdefault(old, {"new": new, "teacher": r["local_teacher"], "n": 0})
        p["n"] += 1
    for old in conflicts:
        proposals.pop(old, None)
        print(f"  ! {old}: mehrdeutige WebUntis-Gruppen gefunden, übersprungen (von Hand prüfen).")
    return proposals


def write_overrides(cohort: str, proposals: dict[str, dict]):
    raw = json.loads(CODE_OVERRIDE_FILE.read_text(encoding="utf-8"))
    raw.setdefault(cohort, {})
    for old, p in proposals.items():
        raw[cohort][old] = {"newCode": p["new"], "teacher": p["teacher"]}
    CODE_OVERRIDE_FILE.write_text(json.dumps(raw, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nGespeichert in build/{CODE_OVERRIDE_FILE.name}.")
    print("Jetzt:  python3 build/parse_pdfs.py  ausführen, Report + git diff auf data/** "
          "durchsehen, dann committen und pushen.")


# ------------------------------------------------------------------- main
def main():
    cfg = load_config()
    cohort = cfg.get("cohort", "k1")
    student, by_code = load_local(cohort, cfg["studentNr"])
    print(f"Login bei {cfg.get('displayName', cfg['server'])} …")
    try:
        session = webuntis.Session(
            server=cfg["server"], school=cfg["school"],
            username=cfg["username"], password=cfg["password"],
            useragent="webDumbis").login()
    except Exception as e:  # noqa: BLE001
        sys.exit(f"Login fehlgeschlagen: {e}\n"
                 f"Prüfe Benutzername/Passwort in build/untis-config.json.")

    try:
        pmap = build_period_map(session)
        rows = compare(session, cfg, pmap, student, by_code)
    finally:
        try:
            session.logout()
        except Exception:  # noqa: BLE001
            pass

    print_report(rows)
    proposals = collect_proposals(rows)
    if not proposals:
        print("\nKeine Abweichungen gefunden, bei denen die Lehrkraft übereinstimmt "
              "(oder alles ist schon deckungsgleich).")
        return

    print(f"\n{len(proposals)} möglicher Umbenennung(en):")
    accepted = {}
    for old, p in proposals.items():
        print(f"\n  {old} -> {p['new']}  (Lehrkraft: {p['teacher']}, {p['n']} Stunde(n) als Beleg)")
        ans = input(f"  Übernehmen in build/course-code-overrides.json? [j/N] ").strip().lower()
        if ans in ("j", "y", "ja"):
            accepted[old] = p
    if accepted:
        write_overrides(cohort, accepted)
    else:
        print("\nNichts übernommen.")


if __name__ == "__main__":
    main()
