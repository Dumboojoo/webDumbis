#!/usr/bin/env python3
"""Holt Ausfälle / Vertretungen aus WebUntis nach data/<stufe>/events.json.

Einfach starten:

    python3 build/fetch_untis.py

Beim ersten Mal fragt das Skript nach Schule, Login und Stufe und speichert das in
build/untis-config.json (steht in .gitignore, kommt also NICHT ins Repo). Danach
reicht der eine Befehl – es holt die aktuellen Ausfälle und lädt sie (nach Rückfrage)
gleich auf GitHub hoch.
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
SCHOOLQUERY = "https://mobile.webuntis.com/ms/schoolquery2"


# --------------------------------------------------------------------- Setup
def search_schools(name: str) -> list[dict]:
    r = requests.post(SCHOOLQUERY, timeout=15, headers={"User-Agent": "webDumbis"},
                      json={"id": "1", "method": "searchSchool", "jsonrpc": "2.0",
                            "params": [{"search": name}]})
    r.raise_for_status()
    return r.json().get("result", {}).get("schools", [])


def ask_school() -> dict:
    """Schule per Suche finden – oder Fallback: WebUntis-URL einfügen."""
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
    cfg = {
        "server": sc["server"], "school": sc["loginName"],
        "displayName": sc["displayName"], "username": username, "password": password,
        "cohort": stufe, "weeksAhead": 4, "autoPush": True, "subjectMap": {},
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
    """Startzeit 'HH:MM' -> Stundennummer 1..N (aus dem WebUntis-Zeitraster)."""
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
    hh = dt.strftime("%H:%M")
    if hh in pmap:
        return pmap[hh]
    target = dt.hour * 60 + dt.minute
    best = min(pmap.items(), key=lambda kv: abs(int(kv[0][:2]) * 60 + int(kv[0][3:]) - target),
              default=("", 0))
    return best[1]


# ------------------------------------------------------------------- Abholen
def fetch_events(session, cfg, pmap) -> list[dict]:
    smap = {k: v for k, v in (cfg.get("subjectMap") or {}).items() if not k.startswith("_")}
    weeks = int(cfg.get("weeksAhead", 4))
    start = date.today() - timedelta(days=date.today().weekday())
    seen: dict[tuple, dict] = {}

    for w in range(weeks):
        mon = start + timedelta(days=7 * w)
        try:
            periods = session.my_timetable(start=mon, end=mon + timedelta(days=4))
        except Exception as e:  # noqa: BLE001
            print(f"  ! Plan {mon}: {e}")
            continue
        for p in periods:
            if p.code not in ("cancelled", "irregular"):
                continue
            subj = getattr(p.subjects[0], "name", "") if p.subjects else ""
            subj = smap.get(subj, subj) or getattr(p, "studentGroup", "") or "?"
            teacher = getattr(p.teachers[0], "name", "") if p.teachers else ""
            room = getattr(p.rooms[0], "name", "") if p.rooms else ""
            pn = period_number(pmap, p.start)
            en = period_number(pmap, p.end - timedelta(minutes=1)) or pn
            ev = {
                "date": p.start.date().isoformat(), "period": pn, "endPeriod": max(pn, en),
                "code": subj, "type": "ausfall" if p.code == "cancelled" else "vertretung",
                "teacher": teacher, "newTeacher": teacher if p.code == "irregular" else "",
                "room": room,
                "text": (getattr(p, "lstext", "") or getattr(p, "substText", "") or "").strip(),
            }
            seen[(ev["date"], ev["period"], ev["code"], ev["type"])] = ev
    return sorted(seen.values(), key=lambda e: (e["date"], e["period"], e["code"]))


def known_codes(cid: str) -> set[str]:
    f = DATA_DIR / cid / "courses.json"
    if not f.exists():
        return set()
    return {c["code"].lower() for c in json.loads(f.read_text(encoding="utf-8")).get("courses", [])}


def git_push(cid: str) -> None:
    rel = f"data/{cid}/events.json"
    try:
        subprocess.run(["git", "-C", str(ROOT), "add", rel], check=True)
        r = subprocess.run(["git", "-C", str(ROOT), "commit", "-q", "-m",
                            "Ausfälle aktualisiert"], capture_output=True)
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
    cid = cfg.get("cohort", "k1")
    print(f"Login bei {cfg.get('displayName', cfg['server'])} …")
    try:
        session = webuntis.Session(
            server=cfg["server"], school=cfg["school"],
            username=cfg["username"], password=cfg["password"],
            useragent="webDumbis").login()
    except Exception as e:  # noqa: BLE001
        sys.exit(f"Login fehlgeschlagen: {e}\n"
                 f"Prüfe Benutzername/Passwort in build/untis-config.json. "
                 f"Bei 2-Faktor-Anmeldung sag Bescheid.")

    with session:
        pmap = build_period_map(session)
        events = fetch_events(session, cfg, pmap)

    out = DATA_DIR / cid / "events.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "source": "WebUntis", "events": events,
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\n{len(events)} Einträge ({cid}):")
    kc = known_codes(cid)
    unmatched = set()
    for e in events:
        tag = "ENTFÄLLT  " if e["type"] == "ausfall" else "Vertretung"
        print(f"  {e['date']}  {e['period']}.-{e['endPeriod']}.  {e['code']:<7} {tag} {e['text']}")
        if kc and e["code"].lower() not in kc:
            unmatched.add(e["code"])
    if unmatched:
        print(f"\n  Achtung: {sorted(unmatched)} passt zu keinem Kurscode in webDumbis.")
        print(f"  In build/untis-config.json unter \"subjectMap\" zuordnen, z. B. "
              f'{{"{sorted(unmatched)[0]}": "…"}}, dann nochmal starten.')

    if not events:
        print("  (Aktuell keine Ausfälle im Zeitraum.)")
    if cfg.get("autoPush", True) and input("\nJetzt auf GitHub hochladen? [J/n] ").strip().lower() in ("", "j", "y"):
        git_push(cid)
    else:
        print(f"Nicht hochgeladen. Später:  git add data/{cid}/events.json && git commit && git push")


if __name__ == "__main__":
    main()
