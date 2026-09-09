# webDumbis – Stundenpläne

Statische Webseite, um die Stundenpläne der Kursstufe des Adolf-Schmitthenner-Gymnasiums
bequem zu durchsuchen. **K1 und K2 sind vollständig getrennt** – jede Stufe hat eigene
Schüler-, Kurs- und Lehrkräftedaten.

Oben (Seitenleiste am Desktop, Kopfzeile am Handy) wird die **Stufe** gewählt; die Wahl
merkt sich der Browser und steht in der Adresse. Der Schriftzug **webDumbis** führt zur
Startseite. Ansichten je Stufe:

- **Suche** – Schüler nach **Name oder Schülernummer** finden.
- **Schüler/innen** – alphabetische Gesamtliste, führt zum Profil mit Wochenstundenplan.
- **Kurse** – nach Fach gruppiert, mit Filterfeld (Fach, Kürzel, Lehrkraft);
  führt zum Kursprofil mit Lehrkraft und Teilnehmerliste.
- **Gemeinsame Kurse** – zwei Personen wählen, es werden alle gemeinsam belegten Kurse angezeigt.
- **Lehrkräfte** – Liste aller Lehrkräfte, führt zu „alle Kurse dieser Lehrkraft".

Im Stundenplan sind die Kurskürzel anklickbar; Lehrkräfte verlinken auf ihre Kursübersicht.
Über dem Stundenplan lässt sich zwischen **Kalenderwochen** blättern (echte Datumsangaben,
„heute" datumsgenau); Ferien-/Feiertagswochen werden als solche markiert.

Direktlinks (mit Stufe `k1`/`k2` als erstem Segment):
`#/k1/s/<nummer>` (Schülerprofil), `#/k1/s/<nummer>/w/<YYYY-MM-DD>` (bestimmte Woche,
Datum = Montag), `#/k2/k/<code>` (Kursprofil), `#/k1/l/<lehrkraft>` (Lehrkraft),
`#/k2/gemeinsam/<nr1>/<nr2>` (gemeinsame Kurse).
Links ohne Stufe (`#/kurse`) landen automatisch in der zuletzt gewählten Stufe.

Reines HTML/CSS/JavaScript – **kein Backend**, direkt über GitHub Pages hostbar.

## Aufbau

```
index.html             Seite
css/style.css           Styling
js/app.js               Routing, Suche, Anzeige
data/meta.json          Liste der Stufen, Datenstand, offene Punkte
data/calendar.json      Ferien / Feiertage (von Hand gepflegt)
data/k1/students.json   Schülerdaten K1     (erzeugt, im Repo)
data/k1/courses.json    Kursdaten K1
data/k1/events.json     Ausfälle / Vertretungen K1 (aus WebUntis, siehe unten)
data/k2/…               dasselbe für K2
build/parse_pdfs.py     PDF-Konverter (nur lokal nötig)
build/subjects.json     Fach-Kürzel → ausgeschriebener Name (von Hand pflegbar)
build/course-teachers.json  Lehrkräfte, die im PDF fehlen (von Hand nachtragen)
build/fetch_untis.py    holt Ausfälle aus WebUntis (nur lokal, siehe unten)
```

## Ferien & Feiertage

`data/calendar.json` steuert, welche Tage/Wochen als unterrichtsfrei angezeigt werden.

- `schoolYearStart` / `schoolYearEnd` – Grenzen für das Wochen-Blättern.
- `free` – Liste von Einträgen, je entweder ein Zeitraum
  `{ "from": "YYYY-MM-DD", "to": "YYYY-MM-DD", "label": "…" }` oder ein Einzeltag
  `{ "date": "YYYY-MM-DD", "label": "…" }`.

Die aktuell hinterlegten Werte sind eine **erste Näherung** – bitte gegen den offiziellen
BW-Ferienkalender **und** den Jahresplan der Schule prüfen und die **beweglichen
Ferientage** ergänzen. Nach dem Ändern einfach `data/calendar.json` committen und pushen.

## Ausfälle aus WebUntis

`data/<stufe>/events.json` enthält Ausfälle und Vertretungen; sie werden im Stundenplan
angezeigt (durchgestrichen + „entfällt" bzw. „Vertretung"). Gefüllt wird die Datei
**lokal** mit `build/fetch_untis.py` – nicht automatisch, nicht im Browser (WebUntis
blockt Cross-Origin, und Zugangsdaten dürfen nicht ins öffentliche Repo).

```
pip install -r build/requirements.txt
cp build/untis-config.example.json build/untis-config.json     # dann ausfüllen
python3 build/fetch_untis.py
```

- `build/untis-config.json` (Server, Schule, Login, Klassen je Stufe) steht in
  `.gitignore` und darf **nicht** committet werden.
- Die Ausgabe zeigt eine Tabelle aller gefundenen Änderungen – prüfen, ob die
  Fachkürzel zu den webDumbis-Kurscodes passen. Wenn nicht: `subjectMap` in der Config
  setzen (z. B. `{"GK": "gk3"}`).
- Passt alles: `data/**/events.json` committen und pushen.

## Fehlende Lehrkräfte

Wenn im Schul-PDF für einen Kurs keine Lehrkraft steht (z. B. K2 `gk3`, `m1`), meldet
`parse_pdfs.py` das. Echte Namen in `build/course-teachers.json` eintragen
(`{ "k2": { "gk3": "Frau …" } }`) und `python3 build/parse_pdfs.py` erneut ausführen.
Solange nichts eingetragen ist, zeigt die Seite „Lehrkraft: noch nicht hinterlegt".

## Daten aktualisieren

Die PDFs in `assets/` müssen so heißen (das Skript erkennt Stufen automatisch am Namen):

```
<Jahr> - K<n> - Schüler-Stundenpläne.pdf
<Jahr> - K<n> - Kurslisten nach LK sortiert.pdf
```

Ablauf:

1. Neue PDFs nach `assets/` legen (alte derselben Stufe ersetzen).
2. `pip3 install -r build/requirements.txt`
3. `python3 build/parse_pdfs.py` – schreibt `data/<stufe>/*.json` und `data/meta.json`.
4. Report am Ende prüfen:
   - `UNBEKANNTE Fach-Kürzel` → in `build/subjects.json` ergänzen und erneut ausführen.
   - `Bitte Fachnamen prüfen` → unsichere Zuordnungen in `build/subjects.json` kontrollieren.
5. Geänderte `data/**` committen und pushen.

Die PDFs selbst müssen **nicht** ins Repo – nach dem Build kann `assets/` gelöscht werden.

## GitHub Pages einrichten

1. Repo auf GitHub anlegen (öffentlich) und pushen.
2. **Settings → Pages → Deploy from a branch**, Branch `main`, Ordner `/ (root)`.
3. Nach ein paar Minuten unter `https://<user>.github.io/<repo>/` erreichbar.

`.nojekyll` sorgt dafür, dass GitHub die Ordner unverändert ausliefert.

## Lokal testen

```
python3 -m http.server
```

Dann <http://localhost:8000/> öffnen.

## Hinweis zum Datenschutz

Die Seite zeigt bewusst die echten Namen. Über GitHub Pages ist sie öffentlich im Internet
und kann von Suchmaschinen erfasst werden.
