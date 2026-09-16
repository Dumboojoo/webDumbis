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
- **Ferien** – alle Ferien und Feiertage des Schuljahres auf einen Blick.
- **Lehrkräfte** – Liste aller Lehrkräfte, führt zu „alle Kurse dieser Lehrkraft".
- **K1 Plan** (nur bei K1) – der komplette K1-Kursplan direkt aus WebUntis, ungefiltert.
  Andere Quelle als der Rest der Seite (siehe unten) – bei Abweichungen zählt hier WebUntis.

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
data/k1/untis-plan.json K1-Kursplan direkt aus WebUntis (Reiter "K1 Plan", siehe unten)
data/k2/…               dasselbe für K2 (kein untis-plan.json)
build/parse_pdfs.py     PDF-Konverter (nur lokal nötig)
build/subjects.json     Fach-Kürzel → ausgeschriebener Name (von Hand pflegbar)
build/course-teachers.json      Lehrkräfte korrigieren/nachtragen (von Hand)
build/course-code-overrides.json  Kurscodes umbenennen, wenn die Schule sie geändert hat
build/check_course_codes.py     vergleicht eigene Kurse mit WebUntis, schlägt Umbenennungen vor (nur lokal)
build/fetch_k1_plan.py  holt den kompletten K1-Plan aus WebUntis nach untis-plan.json (nur lokal)
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

Der Reiter **Ferien** auf der Webseite listet alle Einträge aus dieser Datei auf;
die Ferienwochen werden außerdem im Stundenplan markiert.

## Lehrkräfte korrigieren / nachtragen

`build/course-teachers.json` überschreibt falsche Lehrkräfte aus dem Schul-PDF oder
trägt fehlende nach. Pro Kurscode:

```json
"k1": {
  "d3": { "teacher": "Frau Moser", "abbr": "Mos" }
}
```

- Nur `teacher` → ändert den Namen im Kursprofil.
- Zusätzlich `abbr` → ersetzt auch das Kürzel in allen Stundenplan-Zellen des Kurses.
- `"gk3": ""` (leer) → Kurs bleibt „ohne Lehrkraft" (Seite zeigt „noch nicht hinterlegt").

Nach dem Ändern `python3 build/parse_pdfs.py` erneut ausführen und `data/**` committen.
Der Report zeigt an, welche Kurse korrigiert wurden und welche noch ohne Lehrkraft sind.

## Kurscodes umbenennen (wenn die Schule den Code geändert hat)

Manchmal ändert die Schule nach dem PDF-Druck den Code eines Kurses (Stundenplan und
Lehrkraft bleiben gleich, z. B. wird aus `d2` `d3`) – im gedruckten PDF steht dann noch
der alte Code, aktuell sichtbar ist das nur in WebUntis. `build/course-code-overrides.json`
benennt solche Kurse beim Build um:

```json
"k2": {
  "d2": { "newCode": "d3", "teacher": "Frau Moser" }
}
```

`teacher` ist eine Sicherung: die Umbenennung greift nur, wenn die im PDF hinterlegte
Lehrkraft exakt passt – sonst bricht `parse_pdfs.py` mit einer Warnung ab, statt etwas
Falsches umzubenennen.

Am besten trägt man diese Einträge nicht von Hand ein, sondern lässt sie sich vorschlagen:

```
pip3 install -r build/requirements.txt      # nur beim ersten Mal
python3 build/check_course_codes.py
```

Das Skript loggt sich **lokal** (nicht im Browser – WebUntis blockt Cross-Origin,
Zugangsdaten gehören nicht ins öffentliche Repo) mit dem eigenen WebUntis-Account ein,
vergleicht die eigene aktuelle Wochen-Stunde für Stunde mit dem PDF-Stand und schlägt nur
dort eine Umbenennung vor, wo die Lehrkraft übereinstimmt und nur der Code abweicht. Jeder
Vorschlag muss einzeln bestätigt werden, bevor er in `course-code-overrides.json` landet.
Beim ersten Start fragt es nach Schule, Login, Stufe und der eigenen
webDumbis-Schülernummer und speichert das in `build/untis-config.json` (steht in
`.gitignore`). Bei 2-Faktor-Anmeldung des WebUntis-Kontos klappt der Passwort-Login
(noch) nicht.

Danach wie gewohnt `python3 build/parse_pdfs.py` ausführen, den Report und `git diff` auf
`data/**` querlesen und erst dann committen.

## K1 Plan (roh aus WebUntis)

Der Reiter **K1 Plan** ist ein bewusster Sonderfall: er zeigt **ungefiltert**, was
WebUntis gerade sagt – kein Abgleich mit dem PDF, keine Kurscode-Logik, keine
Lehrkraft-Prüfung. Betrifft nur K1 und nur diesen einen Reiter; Suche, Schüler/innen,
Kurse und Lehrkräfte laufen für K1 weiterhin wie gewohnt über das Schul-PDF.

```
pip3 install -r build/requirements.txt      # nur beim ersten Mal
python3 build/fetch_k1_plan.py
```

Loggt sich **lokal** mit dem eigenen WebUntis-Account ein (dieselbe `untis-config.json`
wie oben), holt den kompletten K1-Kursplan der aktuellen Woche direkt aus WebUntis und
schreibt ihn nach `data/k1/untis-plan.json`. Danach fragt es nach, ob gleich auf GitHub
hochgeladen werden soll.

WebUntis liefert den Kursnamen im Format `<Kurscode>_K1_<Lehrkraft-Kürzel>`
(z. B. `spo2_K1_Gör`). `build/teacher-abbr.json` löst das Kürzel zum Klarnamen auf:

```json
{ "Gör": "Frau Görlich", "Hej": "Frau Herb", "Kne": "Herr Kneißle" }
```

Nur Kürzel eintragen, die bestätigt sind. Für alles andere zeigt der Reiter „K1 Plan"
nur das rohe Kürzel als „noch nicht zugeordnet", und `fetch_k1_plan.py` listet unbekannte
Kürzel am Ende noch mal extra auf.

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
