# Plan: Konferenzzeitplan-Optimierer

## Ziel

Fachkonferenzen so auf Zeit-Slots legen, dass jeder Lehrer an allen Konferenzen seiner Fächer teilnehmen kann,
dabei möglichst viele Konferenzen parallel laufen (kurzer Gesamtzeitraum) und die Lehrer möglichst wenig Leerlauf
zwischen ihren Konferenzen haben. Später übertragbar auf z. B. Zeugniskonferenzen (Klasse -> Lehrer).

## Modell

- **Ereignis** (Fach bzw. Klasse) mit einer Menge von **Teilnehmern** (Lehrer): `Problem = dict[Ereignis, set[Teilnehmer]]`.
- Adapter bilden Eingaben darauf ab: Kollegiumsliste (Lehrer -> Fächer) wird zu Fach -> Lehrer invertiert,
  Zeugniskonferenzen (Klasse -> Lehrer) passen direkt.
- Zwei Ereignisse stehen in Konflikt, wenn sie einen gemeinsamen Teilnehmer haben; sie dürfen nicht im selben Slot liegen.

## Optimierung (lexikographisch)

1. Ohne Obergrenze: minimale Slotzahl ohne Konflikte (Graphfärbung).
2. Mit `--max-slots N` (max. N Konferenzen hintereinander, beliebig viele parallel): Reicht N nicht, minimiere
   die Zahl der Lehrer mit verpassten Konferenzen (alternativ: Summe der verpassten Termine).
3. Danach Slotzahl, dann Leerlauf (Lücken zwischen erstem und letztem Termin) minimieren.
- Alle Konferenzen am selben Tag, keine Zeitwünsche in der ersten Iteration.

## Verfahren

- Hauptsolver: OR-Tools CP-SAT (exakt, mit Zeitlimit).
- Fallback ohne Abhängigkeiten: DSATUR + Simulated Annealing.

## Architektur

```
konferenz_optimizer/
  core/      # Modell, Solver (CP-SAT, Heuristik)
  adapters/  # Eingabeformate (Lehrer -> Fächer, später Klasse -> Lehrer)
  cli.py
  gui/       # später, nutzt nur core + adapters
tests/
```

## Schritte

1. Gerüst, Kernmodell, CSV-Adapter mit Tests
2. Phase A ohne Limit (Heuristik, CP-SAT)
3. Phase A mit `--max-slots` und Verlustminimierung
4. Kopplung mit Slot-Reihenfolge / Lückenminimierung
5. CLI-Ausgabe und Export
6. Tests (Zufallsinstanzen, Heuristik gegen CP-SAT)
7. Später: GUI, PyInstaller-EXE mit Größenoptimierung, Klassenkonferenz-Adapter
