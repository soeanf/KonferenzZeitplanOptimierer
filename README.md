# Konferenzzeitplan-Optimierer

Werkzeug, das Fachkonferenzen (später auch andere Konferenzarten) so auf Zeit-Slots verteilt, dass möglichst jede Lehrkraft an allen Konferenzen ihrer Fächer teilnehmen kann.

> **Status:** Kommandozeilen-Tool, GUI und Standalone-EXE sind einsatzbereit. Geplant ist noch ein Adapter für Klassenkonferenzen. Der ursprüngliche Entwurf steht in [PLAN.md](PLAN.md).

| Version | Inhalt |
| --- | --- |
| 1.0 | Kommandozeilen-Tool |
| 2.0 | grafische Oberfläche, ausführbare EXE-Dateien |

## Download

Fertige Programme für Windows (ohne Python-Installation) gibt es unter **Releases**:
- `Konferenzplaner.exe` – die grafische Oberfläche, einfach starten
- `Konferenzplaner-cli.exe` – die Kommandozeilenversion

Die Dateien sind nicht signiert, Windows kann beim ersten Start warnen („Weitere Informationen“ → „Trotzdem ausführen“). Wer selbst bauen oder mit Python arbeiten möchte, findet die Schritte unten.

## Problem

Es stehen Fachkonferenzen an. Jede Lehrkraft unterrichtet mehrere Fächer und soll an allen zugehörigen Konferenzen teilnehmen können.

- Möglichst viele Konferenzen sollen **gleichzeitig** stattfinden, damit insgesamt nur ein kurzer Zeitraum geblockt werden muss.
- Optional gibt es eine **Obergrenze an Slots** (z. B. höchstens 6 Konferenzen hintereinander). Reicht sie nicht aus, verpassen möglichst wenige Lehrkräfte Konferenzen.
- Die Slots werden so angeordnet, dass jede Lehrkraft möglichst **wenig Leerlauf** zwischen ihren Konferenzen hat.
- Alle Konferenzen finden am selben Tag statt. Zeitwünsche werden nicht berücksichtigt.

## Installation (für die Arbeit mit Python)

Voraussetzung ist Python ab 3.10.

```
python -m venv .venv
.venv\Scripts\python -m pip install ortools sv-ttk pytest
```

Nur zum Bauen der EXEs bzw. Icons zusätzlich: `pyinstaller` und `pillow`.

## Eingabe

CSV im Format `Name,Fach1,Fach2,Fach3,Fach4` (siehe [beispiel.csv](beispiel.csv)).

- Fach 3 und 4 sind optional, leere Felder werden ignoriert.
- Eine Kopfzeile wird erkannt, das Trennzeichen (`,` oder `;`) und die Kodierung (UTF-8 oder cp1252) werden automatisch erkannt.
- Whitespace und Groß-/Kleinschreibung bei Fächern werden normalisiert.

## Verwendung

### GUI

```
.venv\Scripts\python -m konferenz_optimizer.gui
```

Die Oberfläche führt in vier Schritten durch den Ablauf. Mit „Hell/Dunkel“ lässt sich das Design wechseln, die Windows-Titelleiste passt sich an.

1. **Daten laden:** CSV-Datei auswählen.
2. **Daten prüfen:** Lehrkräfte und Fächer in einer Tabelle ansehen (mit Suchfeld). Per Klick auf das ✓ bzw. ✗ vor dem Namen (oder mit der Leertaste) lässt sich eine Lehrkraft komplett von der Berechnung ausnehmen. Die Schaltflächen „Alle“, „Keine“ und „Umkehren“ wirken auf die gerade angezeigten Lehrkräfte. Ebenso lässt sich jedes einzelne Fach einer Lehrkraft per Klick auf sein ✓ bzw. ✗ ausnehmen. Rechts steht eine Fächerübersicht mit der Zahl der Teilnehmer, die sich per Klick auf die Spaltenköpfe nach Fach oder Teilnehmerzahl sortieren lässt. Ausnahmen gelten nur für die laufende Sitzung und werden nicht in die CSV zurückgeschrieben.
3. **Berechnen:** optionale Slot-Obergrenze, Ziel bei zu wenigen Slots und Zeitlimit festlegen. Die Berechnung läuft im Hintergrund, ein Balken zeigt, dass sie läuft. Das Zeitlimit ist die maximale Rechenzeit (siehe „Zeitlimit“ unten).
4. **Ergebnis:** Slots mit ihren Fächern und Plan pro Lehrkraft mit Leerlauf. Lehrkräfte mit verpassten Konferenzen sind rot markiert. Der Export erfolgt als CSV oder JSON.

### Kommandozeile

```
.venv\Scripts\python -m konferenz_optimizer beispiel.csv [Optionen]
```

| Option | Bedeutung |
| --- | --- |
| `--max-slots N` | Obergrenze für die Zahl der hintereinanderliegenden Slots |
| `--objective teilnehmer\|verpasst` | Ziel, falls die Obergrenze nicht reicht: wenige betroffene Lehrkräfte (Standard) oder wenige verpasste Termine |
| `--solver cpsat\|heur` | exakter Solver (Standard) oder Heuristik ohne OR-Tools |
| `--time-limit S` | Zeitlimit in Sekunden (Standard 30) |
| `--out datei.csv\|datei.json` | Ergebnis speichern |

Die Ausgabe enthält:
- die Slot-Tabelle,
- den Ablauf jeder Lehrkraft mit Leerlauf und verpassten Terminen,
- Kennzahlen und Status (`optimal`, beste gefundene Lösung bei Zeitlimit oder `heuristisch`).

Der CSV-Export enthält die Slot-Tabelle und den Plan pro Lehrkraft, der JSON-Export zusätzlich die Kennzahlen.

## Vorgehen

Das Problem ist allgemein modelliert: **Ereignisse** (Fach bzw. Klasse) haben **Teilnehmer** (Lehrkräfte). Zwei Ereignisse stehen in Konflikt, wenn sie mindestens einen gemeinsamen Teilnehmer haben. Die Kollegiumsliste (Lehrkraft → Fächer) wird dafür intern zu Fach → Lehrkräfte umgruppiert.

Der Solver (OR-Tools CP-SAT) optimiert lexikographisch in drei Stufen:

1. Verluste minimieren, also Lehrkräfte bzw. Termine, die wegen Überschneidungen nicht besucht werden können. Diese Stufe entfällt, wenn ohne Obergrenze ein konfliktfreier Plan möglich ist.
2. Slotzahl minimieren.
3. Leerlauf der Lehrkräfte minimieren.

Als Fallback ohne Abhängigkeiten gibt es eine Heuristik (DSATUR plus Simulated Annealing). Sie liefert keine Optimalitätsgarantie.

### Zeitlimit

Meist ist der beste Plan nach wenigen Sekunden gefunden. Das Zeitlimit greift nur bei sehr großen oder verzwickten Datensätzen, bei denen der Nachweis, dass es nicht besser geht, lange dauern kann. Die Berechnung endet in jedem Fall, sie läuft nie endlos. Wird das Limit erreicht, erhältst du den besten bis dahin gefundenen, gültigen Plan (jedes Fach genau einem Slot zugeordnet, Obergrenze eingehalten). Er ist dann eventuell nicht der bestmögliche, etwa mit einem Slot mehr oder etwas mehr Leerlauf. Das steht im Status als „beste gefundene Lösung (Zeitlimit)“ statt „optimal“. Das Limit wird auf die drei Stufen aufgeteilt, jede Stufe bekommt mindestens eine Sekunde, die Gesamtzeit kann es deshalb leicht überschreiten.

## Projektstruktur

```
konferenz_optimizer/
  core/      Modell, Auswertung, Solver (solver_cpsat.py, solver_heur.py)
  adapters/  Eingabeformate (teacher_subjects.py: Lehrkraft → Fächer)
  cli.py     Kommandozeile
  gui/       GUI (tkinter + sv-ttk), Icons in gui/assets/
tests/       Tests inkl. Zufallsinstanzen (Heuristik gegen CP-SAT)
tools/       make_icon.py erzeugt die Icons (benötigt Pillow), icon.svg ist die Vektorvorlage
run_gui.py   Einstiegspunkt der GUI-EXE
run_cli.py   Einstiegspunkt der CLI-EXE
build_exe.bat  baut beide EXEs nach dist\
```

Tests ausführen:

```
.venv\Scripts\python -m pytest
```

## Standalone-EXE selbst bauen

Die fertigen Dateien gibt es unter Releases (siehe oben). Zum eigenen Bauen:

```
.venv\Scripts\python -m pip install pyinstaller
build_exe.bat
```

Ergebnis in `dist\`:
- `Konferenzplaner.exe` – die GUI (ca. 70 MB, enthält OR-Tools und Theme)
- `Konferenzplaner-cli.exe` – die Kommandozeile mit denselben Optionen wie oben, z. B. `Konferenzplaner-cli.exe kollegium.csv --max-slots 6 --out plan.csv` (ca. 65 MB)

Beide rechnen mit demselben Solver wie die Python-Variante, Ergebnis und Rechenzeit sind identisch. Beim Start wird die EXE zunächst in einen temporären Ordner entpackt, das kostet beim ersten Öffnen ein paar Sekunden. Da die EXEs nicht signiert sind, kann Windows SmartScreen beim ersten Start warnen.

## Geplant

- Adapter für Zeugniskonferenzen (Klasse → Lehrkräfte)
