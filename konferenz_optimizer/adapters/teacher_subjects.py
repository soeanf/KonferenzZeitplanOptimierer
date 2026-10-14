"""Adapter: Kollegiumsliste (Lehrer -> Faecher) als Fachkonferenzen (Fach -> Lehrer)."""
from __future__ import annotations

import csv
import io
from pathlib import Path

from ..core.model import Labels, Problem


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


def parse_rows(rows: list[list[str]]) -> Problem:
    """Zeilen im Format Name,Fach1,Fach2[,Fach3,Fach4]; Kopfzeile wird erkannt."""
    events: dict[str, set[str]] = {}
    canonical: dict[str, str] = {}  # casefold -> erste Schreibweise
    rows = [r for r in rows if any(c.strip() for c in r)]
    if rows and rows[0][0].strip().casefold() == "name":
        rows = rows[1:]
    for row in rows:
        name = row[0].strip()
        if not name:
            raise ValueError(f"Zeile ohne Namen: {row}")
        for cell in row[1:]:
            subject = _normalize(cell)
            if subject:
                subject = canonical.setdefault(subject.casefold(), subject)
                events.setdefault(subject, set()).add(name)
    return Problem({e: frozenset(m) for e, m in events.items()}, Labels("Fach", "Lehrer"))


def load_teacher_subjects(path: str | Path) -> Problem:
    text = _read_text(Path(path))
    first = text.splitlines()[0] if text.strip() else ""
    delimiter = ";" if first.count(";") > first.count(",") else ","
    return parse_rows(list(csv.reader(io.StringIO(text), delimiter=delimiter)))
