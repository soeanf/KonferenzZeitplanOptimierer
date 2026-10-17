"""Adapter: Kollegiumsliste (Lehrer -> Faecher/Gruppen) als Konferenzen (Eintrag -> Lehrer).

Die Spaltenzahl ist beliebig: Auf `Name` folgen so viele Eintraege wie die Lehrkraft hat.
Zwei Konferenzarten unterscheiden sich nur in der Beschriftung (PRESETS):
- fach:   alle Lehrkraefte eines Fachs kommen zusammen (Fachkonferenz)
- klasse: alle Lehrkraefte einer Klasse, eines Jahrgangs oder Kurses kommen zusammen
          (Noten-, Zeugnis-, Jahrgangs-, Kurs- und paedagogische Konferenzen)
"""
from __future__ import annotations

import csv
import io
from pathlib import Path

from ..core.model import Labels, Problem

PRESETS: dict[str, Labels] = {
    "fach": Labels("Fach", "Lehrer*innen", "Fächer"),
    "klasse": Labels("Gruppe", "Lehrer*innen", "Gruppen"),
}


def _read_text(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"Encoding von {path} nicht erkannt")


def _normalize(subject: str) -> str:
    return " ".join(subject.split())


def parse_teachers(rows: list[list[str]]) -> dict[str, list[str]]:
    """Zeilen im Format Name,Eintrag1,Eintrag2,... -> Lehrer -> Eintraege (in Reihenfolge)."""
    teachers: dict[str, list[str]] = {}
    canonical: dict[str, str] = {}  # casefold -> erste Schreibweise
    rows = [r for r in rows if any(c.strip() for c in r)]
    if rows and rows[0][0].strip().casefold() == "name":
        rows = rows[1:]
    for row in rows:
        name = row[0].strip()
        if not name:
            raise ValueError(f"Zeile ohne Namen: {row}")
        subjects = teachers.setdefault(name, [])
        for cell in row[1:]:
            subject = _normalize(cell)
            if subject:
                subject = canonical.setdefault(subject.casefold(), subject)
                if subject not in subjects:
                    subjects.append(subject)
    return teachers


def problem_from_teachers(teachers: dict[str, list[str]], labels: Labels | None = None) -> Problem:
    events: dict[str, set[str]] = {}
    for name, subjects in teachers.items():
        for subject in subjects:
            events.setdefault(subject, set()).add(name)
    return Problem({e: frozenset(m) for e, m in events.items()}, labels or PRESETS["fach"])


def parse_rows(rows: list[list[str]], labels: Labels | None = None) -> Problem:
    return problem_from_teachers(parse_teachers(rows), labels)


def read_teachers(path: str | Path) -> dict[str, list[str]]:
    text = _read_text(Path(path))
    first = text.splitlines()[0] if text.strip() else ""
    delimiter = ";" if first.count(";") > first.count(",") else ","
    return parse_teachers(list(csv.reader(io.StringIO(text), delimiter=delimiter)))


def load_teacher_subjects(path: str | Path, labels: Labels | None = None) -> Problem:
    return problem_from_teachers(read_teachers(path), labels)
