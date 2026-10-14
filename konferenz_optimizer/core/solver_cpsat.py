"""Exakter Loeser (OR-Tools CP-SAT), lexikographisch in drei Stufen:
A) Verluste (nicht teilnehmbare Konferenzen) minimieren,
B) Slotzahl minimieren,
C) Leerlauf (Luecken) der Teilnehmer minimieren.
"""
from __future__ import annotations

import time

from ortools.sat.python import cp_model

from .model import Problem, Schedule, evaluate
from .solver_heur import dsatur, loss_weights


def solve_cpsat(
    problem: Problem,
    max_slots: int | None = None,
    objective: str = "teilnehmer",
    time_limit: float = 30.0,
    workers: int = 0,
) -> Schedule:
    events = sorted(problem.events)
    if not events:
        return evaluate(problem, [], "leer")
    ub = max(dsatur(problem.conflict_graph()).values()) + 1
    n_slots = ub if max_slots is None else min(max_slots, ub)
    parts = [(sorted(evs)) for evs in problem.participants.values()]
    w_unhappy, w_missed = loss_weights(problem, objective)

    m = cp_model.CpModel()
    x = {(e, s): m.new_bool_var(f"x_{e}_{s}") for e in events for s in range(n_slots)}
    for e in events:
        m.add_exactly_one(x[e, s] for s in range(n_slots))
    used = [m.new_bool_var(f"used_{s}") for s in range(n_slots)]
    for s in range(n_slots):
        for e in events:
            m.add_implication(x[e, s], used[s])
        if s + 1 < n_slots:
            m.add_implication(used[s + 1], used[s])  # Slots ohne Luecke belegen

    loss_terms, gap_terms = [], []
    for pi, evs in enumerate(parts):
        if len(evs) < 2:
            continue
        y = []
        first = m.new_int_var(0, n_slots - 1, f"first_{pi}")
        last = m.new_int_var(0, n_slots - 1, f"last_{pi}")
        for s in range(n_slots):
            v = m.new_bool_var(f"y_{pi}_{s}")
            for e in evs:
                m.add_implication(x[e, s], v)
            m.add(v <= sum(x[e, s] for e in evs))
            m.add(first <= s).only_enforce_if(v)
            m.add(last >= s).only_enforce_if(v)
            y.append(v)
        attended = sum(y)
        missed = len(evs) - attended
        unhappy = m.new_bool_var(f"unhappy_{pi}")
        m.add(len(evs) * unhappy >= missed)
        loss_terms += [w_unhappy * unhappy, w_missed * missed]
        gap_terms.append(last - first + 1 - attended)

    loss = sum(loss_terms)
    gaps = sum(gap_terms)
    slots_used = sum(used)
    all_optimal = True
    deadline = time.monotonic() + time_limit

    def run(expr, share: float) -> dict:
        """Minimiert expr, fixiert das Ergebnis als Schranke, liefert die Belegung."""
        nonlocal all_optimal
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = max(1.0, (deadline - time.monotonic()) * share)
        solver.parameters.num_workers = workers
        m.clear_hints()
        m.minimize(expr)
        status = solver.solve(m)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            raise RuntimeError("Kein zulaessiger Plan gefunden (Zeitlimit zu knapp?)")
        all_optimal &= status == cp_model.OPTIMAL
        m.add(expr <= int(round(solver.objective_value)))
        return {k: solver.value(v) for k, v in x.items()}

    if n_slots < ub:
        run(loss, 0.4)
    else:
        m.add(loss <= 0)
    run(slots_used, 0.5)
    solution = run(gaps, 1.0)

    slots: list[list[str]] = [[] for _ in range(n_slots)]
    for (e, s), val in solution.items():
        if val:
            slots[s].append(e)
    return evaluate(problem, slots, "optimal" if all_optimal else "beste gefundene Loesung (Zeitlimit)")
