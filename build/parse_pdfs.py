#!/usr/bin/env python3
"""PDF -> JSON Konverter fuer die webDumbis Stundenplan-Webseite.

Findet in assets/ automatisch alle Jahrgaenge (K1, K2, ...) anhand der Dateinamen
    "<Jahr> - <Kx> - Schüler-Stundenpläne.pdf"
    "<Jahr> - <Kx> - Kurslisten nach LK sortiert.pdf"
und erzeugt pro Jahrgang getrennt:
    data/<kx>/students.json   - Schueler mit Wochenstundenplan
    data/<kx>/courses.json    - Kurse (Code -> Lehrkraft, Fach, Teilnehmerliste)
sowie eine gemeinsame
    data/meta.json            - Liste der Jahrgaenge, Stand, offene Punkte

Aufruf:  python3 build/parse_pdfs.py
Die PDFs werden nur hier gebraucht; nach dem Build koennen sie geloescht werden.
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import pdfplumber

ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = ROOT / "assets"
DATA_DIR = ROOT / "data"
SUBJECTS_FILE = Path(__file__).resolve().parent / "subjects.json"
TEACHER_OVERRIDE_FILE = Path(__file__).resolve().parent / "course-teachers.json"

DAYS = ["Mo", "Di", "Mi", "Do", "Fr"]
DAY_HEADERS = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag"]
N_PERIODS = 10

# Kuerzel, deren ausgeschriebener Name unsicher ist -> in meta.json melden.
FLAGGED = {"bll", "lth", "rrk"}

FILE_RE = re.compile(
    r"^(\d{4}) - (K\d) - (Schüler-Stundenpläne|Kurslisten nach LK sortiert)\.pdf$")


def load_subjects() -> dict[str, str]:
    raw = json.loads(SUBJECTS_FILE.read_text(encoding="utf-8"))
    return {k.lower(): v for k, v in raw.items() if not k.startswith("_")}


def load_teacher_overrides() -> dict[str, dict[str, str]]:
    if not TEACHER_OVERRIDE_FILE.exists():
        return {}
    raw = json.loads(TEACHER_OVERRIDE_FILE.read_text(encoding="utf-8"))
    return {k: v for k, v in raw.items() if not k.startswith("_") and isinstance(v, dict)}


def discover_cohorts():
    found: dict[str, dict] = {}
    for p in sorted(ASSETS_DIR.glob("*.pdf")):
        m = FILE_RE.match(unicodedata.normalize("NFC", p.name))
        if not m:
            continue
        year, kx, kind = m.groups()
        cid = kx.lower()
        c = found.setdefault(cid, {"id": cid, "label": kx, "abi": year})
        c["stundenplan" if kind.startswith("Schüler") else "kurslisten"] = p
    return [c for c in sorted(found.values(), key=lambda c: c["label"])
            if "stundenplan" in c and "kurslisten" in c]


def split_code(code: str) -> tuple[str, str, str]:
    """'GEO1' -> ('geo', 'LK', '1');  'd3' -> ('d', 'BK', '3')."""
    m = re.match(r"^([A-Za-zÄÖÜäöü]+?)(\d*)$", code)
    letters = m.group(1) if m else code
    index = m.group(2) if m else ""
    kind = "LK" if letters[:1].isupper() else "BK"
    return letters.lower(), kind, index


def make_label(code: str, subjects: dict[str, str], unknown: set[str]) -> str:
    letters, kind, index = split_code(code)
    name = subjects.get(letters)
    if not name:
        unknown.add(letters)
        return code
    return f"{code} ({name} {kind}{index})"


# --------------------------------------------------------------------------- #
# Kurslisten                                                                  #
# --------------------------------------------------------------------------- #
def parse_kurslisten(path: Path, subjects: dict[str, str]):
    courses: dict[str, dict] = {}
    unknown: set[str] = set()
    pdf = pdfplumber.open(path)
    last_code = None

    for page in pdf.pages:
        words = page.extract_words()
        header = [w for w in words if w["x0"] > 500 and 50 < w["top"] < 66]
        teacher_w = [w for w in words if w["x0"] > 400 and 66 <= w["top"] < 80]
        code = "".join(w["text"] for w in sorted(header, key=lambda w: w["x0"])).replace(" ", "")

        rows = extract_student_rows(words)
        if not code:
            if not rows:
                continue  # leere Ueberlauf-Seite
            code = last_code  # Fortsetzungsseite ohne Kopf
            if code is None:
                continue
        last_code = code

        if code not in courses:
            letters, kind, index = split_code(code)
            teacher = " ".join(w["text"] for w in sorted(teacher_w, key=lambda w: w["x0"]))
            knr = ""
            for w in words:
                m = re.match(r"^(\d+)\)$", w["text"])
                if m:
                    knr = str(int(m.group(1)))
            courses[code] = {
                "code": code,
                "teacher": teacher.strip(),
                "kind": kind,
                "subject": subjects.get(letters, ""),
                "index": index,
                "courseNr": knr,
                "label": make_label(code, subjects, unknown),
                "students": [],
            }
        for nr, _name, _grp in rows:
            if nr not in courses[code]["students"]:
                courses[code]["students"].append(nr)

    for c in courses.values():
        c["students"].sort()
    return courses, unknown


def extract_student_rows(words):
    """Findet (SchNr, 'Nachname, Vorname', Klasse/Tutor) Zeilen in einer Kursliste."""
    rows = []
    nr_words = [w for w in words if w["x0"] < 72 and re.match(r"^\d{3}$", w["text"])]
    for nw in nr_words:
        y = nw["top"]
        line = [w for w in words if abs(w["top"] - y) < 6]
        name_w = sorted((w for w in line if 78 < w["x0"] < 212), key=lambda w: w["x0"])
        grp_w = sorted((w for w in line if w["x0"] >= 212), key=lambda w: w["x0"])
        name = " ".join(w["text"] for w in name_w).replace(" ,", ",")
        grp = grp_w[0]["text"] if grp_w else ""
        if name:
            rows.append((nw["text"], name, grp))
    return rows


# --------------------------------------------------------------------------- #
# Schueler-Stundenplaene                                                      #
# --------------------------------------------------------------------------- #
def parse_stundenplaene(path: Path, courses: dict[str, dict], subjects: dict[str, str]):
    students: dict[str, dict] = {}
    unknown: set[str] = set()
    unmatched: set[str] = set()
    valid_from = ""
    pdf = pdfplumber.open(path)

    for page in pdf.pages:
        words = page.extract_words()
        if not valid_from:
            valid_from = extract_valid_from(words)

        montags = sorted((w for w in words if w["text"] == "Montag"), key=lambda w: w["top"])
        for bi, mw in enumerate(montags):
            top = mw["top"]
            bottom = montags[bi + 1]["top"] if bi + 1 < len(montags) else page.height
            block = [w for w in words if top - 70 <= w["top"] < bottom]

            header = parse_student_header(block, top)
            if not header:
                continue
            nr, name, grp = header

            centers = day_centers(block, top)
            timetable = parse_grid(block, top, bottom, centers, courses, subjects,
                                   unknown, unmatched)
            students[nr] = {"nr": nr, "name": name, "klasse": grp, "timetable": timetable}

    return students, valid_from, unknown, unmatched


MONTHS_DE = {"Januar": 1, "Februar": 2, "März": 3, "April": 4, "Mai": 5, "Juni": 6,
             "Juli": 7, "August": 8, "September": 9, "Oktober": 10, "November": 11,
             "Dezember": 12}


def extract_valid_from(words):
    line = sorted((w for w in words if 80 < w["top"] < 95 and w["x0"] > 400),
                  key=lambda w: w["x0"])
    m = re.search(r"(\d{1,2})\.\s*(\w+)\s*(\d{4})", " ".join(w["text"] for w in line))
    if not m:
        return ""
    mon = MONTHS_DE.get(m.group(2))
    if not mon:
        return ""
    day, year = int(m.group(1)), int(m.group(3))

    # WinProsa traegt in der "gültig ab"-Zeile oft ein altes Jahr ein. Das Druckdatum
    # (oben rechts, TT.MM.JJJJ) ist verlaesslicher: ein im August gedruckter Plan gilt
    # ab dem Schuljahr, das dann beginnt.
    pm = re.search(r"\b(\d{2})\.(\d{2})\.(\d{4})\b",
                   " ".join(w["text"] for w in words if w["top"] < 55 and w["x0"] > 400))
    if pm:
        print_month, print_year = int(pm.group(2)), int(pm.group(3))
        year = print_year if mon >= print_month else print_year + 1

    return f"{year}-{mon:02d}-{day:02d}"


def parse_student_header(block, grid_top):
    """Sucht 'NNN Nachname, Vorname' + Klasse/Tutor oberhalb des Rasters."""
    head = [w for w in block if grid_top - 70 <= w["top"] < grid_top - 8]
    nr_w = [w for w in head if w["x0"] > 300 and re.match(r"^\d{3}$", w["text"])]
    if not nr_w:
        return None
    nw = max(nr_w, key=lambda w: w["x0"])
    line = sorted((w for w in head if abs(w["top"] - nw["top"]) < 6 and w["x0"] >= nw["x0"]),
                  key=lambda w: w["x0"])
    name = " ".join(w["text"] for w in line[1:]).replace(" ,", ",")
    # Klasse (K1: "11b") bzw. Tutor-Kuerzel (K2: "Küh") steht rechts, kurz unter der Nummer.
    cand = [w for w in head if w["x0"] > 505 and nw["top"] + 6 < w["top"] < grid_top - 20]
    grp = min(cand, key=lambda w: w["top"])["text"] if cand else ""
    if not name:
        return None
    return nw["text"], name, grp


def day_centers(block, grid_top):
    centers = []
    for name in DAY_HEADERS:
        w = next((w for w in block if w["text"] == name and abs(w["top"] - grid_top) < 4), None)
        centers.append((w["x0"] + w["x1"]) / 2 if w else None)
    defaults = [184.0, 268.0, 353.0, 438.0, 523.0]
    return [c if c is not None else d for c, d in zip(centers, defaults)]


def nearest_day(x, centers):
    return min(range(5), key=lambda i: abs(x - centers[i]))


def parse_grid(block, grid_top, grid_bottom, centers, courses, subjects, unknown, unmatched):
    timetable = {d: [None] * N_PERIODS for d in DAYS}

    period_rows = {}
    for w in block:
        if w["x0"] < 95 and re.match(r"^(\d{1,2})\.$", w["text"]) and grid_top < w["top"] < grid_bottom:
            p = int(w["text"][:-1])
            if 1 <= p <= N_PERIODS:
                period_rows[p] = w["top"]

    for p, y in period_rows.items():
        cells = [w for w in block if abs(w["top"] - y) < 6 and w["x0"] > 140]
        by_day: dict[int, list] = {}
        for w in sorted(cells, key=lambda w: w["x0"]):
            by_day.setdefault(nearest_day(w["x0"], centers), []).append(w["text"])
        for di, toks in by_day.items():
            if not toks:
                continue
            code = toks[0]
            teacher = toks[1] if len(toks) > 1 else ""
            label = courses.get(code, {}).get("label")
            if not label:
                label = make_label(code, subjects, unknown)
                if code not in courses:
                    unmatched.add(code)
            timetable[DAYS[di]][p - 1] = {
                "p": p, "code": code, "teacher": teacher, "label": label,
            }
    return timetable


# --------------------------------------------------------------------------- #
def process_cohort(cohort: dict, subjects: dict[str, str],
                   teacher_overrides: dict[str, dict[str, str]]) -> dict:
    courses, unk_c = parse_kurslisten(cohort["kurslisten"], subjects)
    students, valid_from, unk_s, unmatched = parse_stundenplaene(
        cohort["stundenplan"], courses, subjects)

    # Fehlende Lehrkraefte aus build/course-teachers.json nachtragen.
    override = teacher_overrides.get(cohort["id"], {})
    missing_teachers = []
    for code, c in courses.items():
        if not c["teacher"]:
            c["teacher"] = (override.get(code) or "").strip()
        if not c["teacher"]:
            missing_teachers.append(code)
    missing_teachers.sort()

    out_dir = DATA_DIR / cohort["id"]
    out_dir.mkdir(parents=True, exist_ok=True)
    student_list = sorted(students.values(), key=lambda s: s["nr"])
    (out_dir / "students.json").write_text(
        json.dumps({"students": student_list}, ensure_ascii=False, indent=1), encoding="utf-8")
    (out_dir / "courses.json").write_text(
        json.dumps({"courses": [courses[k] for k in sorted(courses)]},
                   ensure_ascii=False, indent=1), encoding="utf-8")

    flagged = sorted({c["code"] for c in courses.values()
                      if split_code(c["code"])[0] in FLAGGED})
    empty = [s["nr"] for s in student_list
             if not any(v for day in s["timetable"].values() for v in day)]

    return {
        "id": cohort["id"], "label": cohort["label"], "abi": cohort["abi"],
        "validFrom": valid_from,
        "studentCount": len(student_list), "courseCount": len(courses),
        "unknown": sorted(unk_c | unk_s), "unmatched": sorted(unmatched),
        "flagged": flagged, "empty": empty, "missingTeachers": missing_teachers,
    }


def main():
    cohorts = discover_cohorts()
    if not cohorts:
        sys.exit(f"Keine passenden PDFs in {ASSETS_DIR} gefunden "
                 f"(erwartet: '<Jahr> - K<n> - Schüler-Stundenpläne.pdf' usw.).")

    subjects = load_subjects()
    teacher_overrides = load_teacher_overrides()
    DATA_DIR.mkdir(exist_ok=True)
    # Alte, nicht mehr genutzte Dateien im data/-Wurzelverzeichnis entfernen.
    for stale in ("students.json", "courses.json"):
        (DATA_DIR / stale).unlink(missing_ok=True)

    results = [process_cohort(c, subjects, teacher_overrides) for c in cohorts]

    unknown = sorted({u for r in results for u in r["unknown"]})
    flagged = sorted({f for r in results for f in r["flagged"]})
    missing_teachers = {r["id"]: r["missingTeachers"] for r in results if r["missingTeachers"]}
    meta = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "cohorts": [
            {"id": r["id"], "label": r["label"], "abi": r["abi"],
             "validFrom": r["validFrom"],
             "studentCount": r["studentCount"], "courseCount": r["courseCount"]}
            for r in results
        ],
        "unknownSubjects": unknown,
        "flaggedSubjects": flagged,
        "unmatchedCourseCodes": {r["id"]: r["unmatched"] for r in results if r["unmatched"]},
        "missingTeachers": missing_teachers,
    }
    (DATA_DIR / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")

    for r in results:
        print(f"[{r['label']}] Abi {r['abi']}: {r['studentCount']} Schueler, "
              f"{r['courseCount']} Kurse, gueltig ab {r['validFrom']}")
        if r["unmatched"]:
            print(f"    Kurscodes ohne Kursliste: {r['unmatched']}")
        if r["empty"]:
            print(f"    WARNUNG Schueler ohne Stunden: {r['empty']}")
    if unknown:
        print(f"UNBEKANNTE Fach-Kuerzel (in build/subjects.json ergaenzen): {unknown}")
    if flagged:
        print(f"Bitte Fachnamen pruefen (unsicher): {flagged}")
    if missing_teachers:
        pairs = ", ".join(f"{cid} {code}" for cid, cs in missing_teachers.items() for code in cs)
        print(f"Kurse ohne Lehrkraft (in build/course-teachers.json ergaenzen): {pairs}")


if __name__ == "__main__":
    main()
