#!/usr/bin/env python3
"""Holt den kompletten K1-Kursplan direkt aus WebUntis nach data/k1/untis-plan.json.

Anders als parse_pdfs.py (Quelle: Schul-PDF) zeigt der Reiter "K1 Plan" auf der
Webseite bewusst ungefiltert, was WebUntis gerade sagt – keine Kurscode-Logik,
kein Abgleich, kein Raten. Betrifft nur K1, nur diesen einen zusätzlichen Reiter;
Schüler/Kurse/Lehrkräfte bleiben wie bisher PDF-basiert.

Einfach starten:

    python3 build/fetch_k1_plan.py

Beim ersten Mal fragt das Skript nach Schule und Login und speichert das in
build/untis-config.json (steht in .gitignore, kommt also NICHT ins Repo). Nutzt
dieselbe Datei wie build/check_course_codes.py, falls die schon existiert.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import date, datetime, timedelta
from getpass import getpass
from pathlib import Path

try:
    import requests
    import webuntis
except ImportError:
    sys.exit("Einmalig installieren:  pip3 install -r build/requirements.txt")

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
CONFIG = Path(__file__).resolve().parent / "untis-config.json"
ABBR_FILE = Path(__file__).resolve().parent / "teacher-abbr.json"
SCHOOLQUERY = "https://mobile.webuntis.com/ms/schoolquery2"
DAYS = ["Mo", "Di", "Mi", "Do", "Fr"]
KLASSE_NAME = "K1"


def load_abbr_map() -> dict[str, str]:
    if not ABBR_FILE.exists():
        return {}
    raw = json.loads(ABBR_FILE.read_text(encoding="utf-8"))
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def split_untis_code(raw: str, klasse_name: str = KLASSE_NAME) -> tuple[str, str]:
    """WebUntis liefert den Kursnamen als "<Kurscode>_K1_<Lehrkraft-Kürzel>",
    z. B. "spo2_K1_Gör" -> ("spo2", "Gör"). Mindestens 3 Teile noetig (Kurscode,
    Klasse, Kuerzel); manche Kurse ohne feste Lehrkraft (z. B. Seminarkurs) haben
    stattdessen "semk1_K1_K1" - letzter Teil wiederholt nur die Klasse, kein
    Kuerzel. Passt das Format nicht (oder letzter Teil == Klasse), bleibt nur der
    erste Teil als Code, das Kürzel leer."""
    parts = raw.split("_")
    if len(parts) >= 3 and parts[0] and parts[-1] and parts[-1] != klasse_name:
        return parts[0], parts[-1]
    return parts[0] if parts and parts[0] else raw, ""


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
    cfg = {
        "server": sc["server"], "school": sc["loginName"],
        "displayName": sc["displayName"], "username": username, "password": password,
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


# --------------------------------------------------------------------- Klasse
def find_klasse(session, wanted: str):
    klassen = session.klassen()
    exact = [k for k in klassen if k.name.strip().lower() == wanted.lower()]
    if exact:
        return exact[0]
    candidates = [k for k in klassen if wanted.lower() in k.name.lower()]
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        names = ", ".join(k.name for k in klassen)
        sys.exit(f"Keine Klasse gefunden, die zu \"{wanted}\" passt.\nVerfügbare Klassen: {names}")
    for i, k in enumerate(candidates, 1):
        print(f"  [{i}] {k.name} ({k.long_name})")
    try:
        return candidates[int(input("  Welche Klasse? Nummer: ")) - 1]
    except (ValueError, IndexError):
        sys.exit("Ungültig.")


# ------------------------------------------------------------------- Abholen
def fetch_plan(session, klasse, pmap, abbr_map: dict[str, str]) -> tuple[list[dict], set[str]]:
    monday = date.today() - timedelta(days=date.today().weekday())
    periods = None
    for w in range(4):  # notfalls bis zu 4 Wochen weitersuchen (Ferienwoche o.ä.)
        mon = monday + timedelta(days=7 * w)
        try:
            p = session.timetable_extended(start=mon, end=mon + timedelta(days=4), klasse=klasse)
        except Exception as e:  # noqa: BLE001
            sys.exit(f"Plan konnte nicht geladen werden: {e}")
        if p:
            periods = p
            print(f"Hole Plan der Woche ab {mon.isoformat()} …\n")
            break
    if not periods:
        sys.exit("Keine Stunden in den nächsten 4 Wochen gefunden (Ferien?). Später nochmal versuchen.")

    courses: dict[str, dict] = {}
    unresolved: set[str] = set()
    for p in periods:
        day_idx = p.start.weekday()
        if day_idx > 4:
            continue
        pn = period_number(pmap, p.start)
        en = period_number(pmap, p.end - timedelta(minutes=1)) or pn
        raw_code = (getattr(p, "studentGroup", "") or "").strip()
        code, abbr = split_untis_code(raw_code) if raw_code else ("", "")
        subj = getattr(p.subjects[0], "long_name", "") if getattr(p, "subjects", None) else ""
        subj_short = getattr(p.subjects[0], "name", "") if getattr(p, "subjects", None) else ""
        api_teacher = getattr(p.teachers[0], "surname", "") if getattr(p, "teachers", None) else ""
        room = getattr(p.rooms[0], "name", "") if getattr(p, "rooms", None) else ""

        # Lehrkraft: bevorzugt über das bestaetigte Kuerzel (build/teacher-abbr.json)
        # aufloesen - nicht raten. Nur wenn das Kuerzel fehlt, den rohen WebUntis-
        # Lehrkraft-Namen als Notloesung nehmen.
        teacher = abbr_map.get(abbr, "") if abbr else ""
        if not teacher and abbr:
            unresolved.add(abbr)
        if not teacher and not abbr:
            teacher = api_teacher

        key = code or f"{subj_short}-{abbr or api_teacher}"
        c = courses.setdefault(key, {
            "code": code or subj_short, "subject": subj or subj_short,
            "teacher": teacher, "teacherAbbr": abbr, "room": room, "times": [],
        })
        for x in range(pn, max(pn, en) + 1):
            slot = {"day": DAYS[day_idx], "period": x}
            if slot not in c["times"]:
                c["times"].append(slot)

    for c in courses.values():
        c["times"].sort(key=lambda t: (DAYS.index(t["day"]), t["period"]))
    return sorted(courses.values(), key=lambda c: (c["code"] or "").lower()), unresolved


def git_push() -> None:
    rel = "data/k1/untis-plan.json"
    try:
        subprocess.run(["git", "-C", str(ROOT), "add", rel], check=True)
        r = subprocess.run(["git", "-C", str(ROOT), "commit", "-q", "-m",
                            "K1 Plan (WebUntis) aktualisiert"], capture_output=True)
        if r.returncode != 0:
            print("  Nichts Neues zum Hochladen.")
            return
        subprocess.run(["git", "-C", str(ROOT), "push", "-q"], check=True)
        print("  Auf GitHub hochgeladen. Die Seite aktualisiert sich in ~1–2 Minuten.")
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"  Hochladen fehlgeschlagen ({e}). Von Hand:  git add {rel} && git commit && git push")


# ------------------------------------------------------------------- main
def main():
    cfg = load_config()
    print(f"Login bei {cfg.get('displayName', cfg['server'])} …")
    try:
        session = webuntis.Session(
            server=cfg["server"], school=cfg["school"],
            username=cfg["username"], password=cfg["password"],
            useragent="webDumbis").login()
    except Exception as e:  # noqa: BLE001
        sys.exit(f"Login fehlgeschlagen: {e}\n"
                 f"Prüfe Benutzername/Passwort in build/untis-config.json.")

    abbr_map = load_abbr_map()
    try:
        pmap = build_period_map(session)
        klasse = find_klasse(session, KLASSE_NAME)
        courses, unresolved = fetch_plan(session, klasse, pmap, abbr_map)
    finally:
        try:
            session.logout()
        except Exception:  # noqa: BLE001
            pass

    out = {
        "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "source": "WebUntis", "className": klasse.name,
        "courses": courses,
    }
    out_file = DATA_DIR / "k1" / "untis-plan.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"{len(courses)} Kurse ({klasse.name}):")
    for c in courses:
        times = fmt_times(c["times"])
        teacher = c["teacher"] or (f"? ({c['teacherAbbr']})" if c["teacherAbbr"] else "")
        print(f"  {c['code']:<8} {c['subject']:<22} {teacher:<20} {c['room']:<6} {times}")

    if unresolved:
        print(f"\nUnbekannte Lehrkraft-Kürzel (in build/teacher-abbr.json ergänzen): "
              f"{', '.join(sorted(unresolved))}")

    if input("\nJetzt auf GitHub hochladen? [J/n] ").strip().lower() in ("", "j", "y"):
        git_push()
    else:
        print("Nicht hochgeladen. Später:  git add data/k1/untis-plan.json && git commit && git push")


def fmt_times(times: list[dict]) -> str:
    by_day: dict[str, list[int]] = {}
    for t in times:
        by_day.setdefault(t["day"], []).append(t["period"])
    parts = []
    for d in DAYS:
        if d not in by_day:
            continue
        ps = sorted(set(by_day[d]))
        runs, start = [], ps[0]
        prev = ps[0]
        for p in ps[1:] + [None]:
            if p == prev + 1:
                prev = p
                continue
            runs.append(f"{start}." if start == prev else f"{start}.–{prev}.")
            if p is not None:
                start = prev = p
        parts.append(f"{d} {', '.join(runs)}")
    return " · ".join(parts)


if __name__ == "__main__":
    main()
