# Konferenzzeitplan-Optimierer

Werkzeug, das Fachkonferenzen (später auch andere Konferenzarten) so auf Zeit-Slots verteilt, dass möglichst jede Lehrkraft an allen Konferenzen ihrer Fächer teilnehmen kann.

> **Status: Planung.** Dieses README beschreibt Ziel, Modell und geplantes Vorgehen. Der Entwurf steht in [PLAN.md](PLAN.md).

## Problem

Es stehen Fachkonferenzen an. Jede Lehrkraft unterrichtet mehrere Fächer und soll an allen zugehörigen Konferenzen teilnehmen können.

- Möglichst viele Konferenzen sollen **gleichzeitig** stattfinden, damit insgesamt nur ein kurzer Zeitraum geblockt werden muss.
- Optional gibt es eine **Obergrenze an Slots** (z. B. höchstens 6 Konferenzen hintereinander). Reicht sie nicht aus, sollen möglichst wenige Lehrkräfte Konferenzen verpassen.
- Die Slots sollen so angeordnet werden, dass jede Lehrkraft möglichst **wenig Leerlauf** zwischen ihren Konferenzen hat.
- Alle Konferenzen finden am selben Tag statt. Zeitwünsche werden zunächst nicht berücksichtigt.

## Geplante Eingabe

CSV im Format `Name,Fach1,Fach2,Fach3,Fach4`. Fach 3 und 4 sind optional, leere Felder werden ignoriert.

## Modell

Das Problem wird allgemein beschrieben: **Ereignisse** (Fach bzw. Klasse) haben **Teilnehmer** (Lehrkräfte). Zwei Ereignisse stehen in Konflikt, wenn sie mindestens einen gemeinsamen Teilnehmer haben, und sollten nicht im selben Slot liegen.

Die Kollegiumsliste (Lehrkraft → Fächer) wird intern zu Fach → Lehrkräfte umgruppiert. Dadurch lässt sich dasselbe Verfahren später auch für Zeugniskonferenzen (Klasse → Lehrkräfte) verwenden.

## Geplantes Vorgehen

Die Optimierung läuft in dieser Rangfolge:

1. Ohne Obergrenze: minimale Slotzahl ohne Konflikte (Graphfärbung).
2. Mit Obergrenze: möglichst wenige Lehrkräfte mit verpassten Konferenzen, alternativ möglichst wenige verpasste Termine.
3. Danach: Slotzahl und Leerlauf der Lehrkräfte minimieren.

Als Solver ist OR-Tools CP-SAT vorgesehen. Ein Fallback ohne Abhängigkeiten (DSATUR plus Simulated Annealing) ist ebenfalls geplant.

## Geplante Schritte

1. Gerüst, Kernmodell und CSV-Adapter mit Tests
2. Zuordnung Fach → Slot ohne Obergrenze
3. Zuordnung mit Obergrenze und Minimierung der Verluste
4. Slot-Reihenfolge und Leerlauf
5. CLI-Ausgabe und Export
6. Tests mit Zufallsinstanzen
7. Später: GUI, Standalone-EXE und Adapter für Klassenkonferenzen
