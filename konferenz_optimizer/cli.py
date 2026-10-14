from __future__ import annotations

import argparse
import csv
import json
import sys

from .adapters.teacher_subjects import load_teacher_subjects
from .core.model import Schedule
from .core.solver_heur import OBJECTIVES, solve_heuristic


def solve(problem, solver: str, max_slots, objective, time_limit) -> Schedule:
    if solver == "cpsat":
        try:
            from .core.solver_cpsat import solve_cpsat
        except ImportError:
            print("OR-Tools fehlt, verwende Heuristik.", file=sys.stderr)
        else:
            return solve_cpsat(problem, max_slots, objective, time_limit)
    return solve_heuristic(problem, max_slots, objective, time_limit)


def render(s: Schedule) -> str:
    ev, pa = s.problem.labels.event, s.problem.labels.participant
    out = []
    out.append(f"Status: {s.status}")
    m = s.metrics
    out.append(
        f"Slots: {m.num_slots} | {pa} mit verpassten {ev}-Konferenzen: {m.unhappy} | "
        f"verpasste Termine: {m.missed} | Leerlauf (Slots): {m.gaps}"
    )
    out.append("")
    for i, evs in enumerate(s.slots, 1):
        out.append(f"Slot {i}: {', '.join(evs)}")
    out.append("")
    width = max((len(r.name) for r in s.reports), default=0)
    for r in s.reports:
        cells = []
        for i in range(len(s.slots)):
            mine = r.slots.get(i)
            cells.append(("/".join(mine) if mine else "-"))
        info = f"  Leerlauf {r.gaps}" if r.gaps else ""
        if r.missed:
            info += f"  VERPASST: {', '.join(r.missed)}"
        out.append(f"{r.name:<{width}}  " + " | ".join(cells) + info)
    return "\n".join(out)


def export(s: Schedule, path: str) -> None:
    if path.lower().endswith(".json"):
        data = {
            "metrics": vars(s.metrics),
            "status": s.status,
            "slots": s.slots,
            "participants": {
                r.name: {"attended": r.attended, "missed": r.missed, "gaps": r.gaps}
                for r in s.reports
            },
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    else:
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["Slot", s.problem.labels.event])
            for i, evs in enumerate(s.slots, 1):
                w.writerow([i, ", ".join(evs)])
            w.writerow([])
            n = len(s.slots)
            w.writerow([s.problem.labels.participant, *[f"Slot {i + 1}" for i in range(n)], "Leerlauf", "Verpasst"])
            for r in s.reports:
                w.writerow([r.name, *["/".join(r.slots.get(i, [])) for i in range(n)], r.gaps, ", ".join(r.missed)])


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="konferenz-optimizer", description=__doc__)
    p.add_argument("csv", help="CSV: Name,Fach1,Fach2,[Fach3,Fach4]")
    p.add_argument("--max-slots", type=int, help="maximale Anzahl hintereinander liegender Slots")
    p.add_argument("--objective", choices=OBJECTIVES, default="teilnehmer",
                   help="teilnehmer: wenige betroffene Lehrer*innen; verpasst: wenige verpasste Termine")
    p.add_argument("--solver", choices=("cpsat", "heur"), default="cpsat")
    p.add_argument("--time-limit", type=float, default=30.0, help="Sekunden")
    p.add_argument("--out", help="Ergebnis in .csv oder .json speichern")
    args = p.parse_args(argv)
    if args.max_slots is not None and args.max_slots < 1:
        p.error("--max-slots muss >= 1 sein")
    try:
        problem = load_teacher_subjects(args.csv)
    except (OSError, ValueError) as exc:
        print(f"Fehler beim Lesen: {exc}", file=sys.stderr)
        return 2
    schedule = solve(problem, args.solver, args.max_slots, args.objective, args.time_limit)
    print(render(schedule))
    if args.out:
        export(schedule, args.out)
    return 0
