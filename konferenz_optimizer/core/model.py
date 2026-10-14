"""Generisches Modell: Ereignisse (Faecher/Klassen) mit Teilnehmern (Lehrern)."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Labels:
    event: str = "Fach"
    participant: str = "Lehrer"


@dataclass
class Problem:
    events: dict[str, frozenset[str]]
    labels: Labels = field(default_factory=Labels)

    @property
    def participants(self) -> dict[str, frozenset[str]]:
        """Teilnehmer -> Menge seiner Ereignisse."""
        result: dict[str, set[str]] = {}
        for event, members in self.events.items():
            for member in members:
                result.setdefault(member, set()).add(event)
        return {p: frozenset(e) for p, e in result.items()}

    def conflict_graph(self) -> dict[str, set[str]]:
        graph: dict[str, set[str]] = {e: set() for e in self.events}
        for evs in self.participants.values():
            for a in evs:
                graph[a] |= evs - {a}
        return graph


@dataclass
class ParticipantReport:
    name: str
    slots: dict[int, list[str]]  # Slot -> eigene Ereignisse in diesem Slot
    attended: list[str]
    missed: list[str]
    gaps: int


@dataclass
class Metrics:
    num_slots: int
    unhappy: int  # Teilnehmer, die mindestens ein Ereignis verpassen
    missed: int  # Summe verpasster Ereignisse
    gaps: int  # Summe der Leer-Slots zwischen erstem und letztem Termin


@dataclass
class Schedule:
    problem: Problem
    slots: list[list[str]]  # Index = Slot, Inhalt = parallel stattfindende Ereignisse
    metrics: Metrics
    reports: list[ParticipantReport]
    status: str = ""


def evaluate(problem: Problem, slots: list[list[str]], status: str = "") -> Schedule:
    slots = [sorted(s) for s in slots if s]
    slot_of = {e: i for i, evs in enumerate(slots) for e in evs}
    reports: list[ParticipantReport] = []
    for name, evs in sorted(problem.participants.items()):
        per_slot: dict[int, list[str]] = {}
        for e in sorted(evs):
            per_slot.setdefault(slot_of[e], []).append(e)
        attended = [v[0] for v in per_slot.values()]
        missed = [e for v in per_slot.values() for e in v[1:]]
        used = sorted(per_slot)
        gaps = used[-1] - used[0] + 1 - len(used)
        reports.append(ParticipantReport(name, per_slot, attended, sorted(missed), gaps))
    metrics = Metrics(
        num_slots=len(slots),
        unhappy=sum(1 for r in reports if r.missed),
        missed=sum(len(r.missed) for r in reports),
        gaps=sum(r.gaps for r in reports),
    )
    return Schedule(problem, slots, metrics, reports, status)
