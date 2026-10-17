"""Exakter Loeser (OR-Tools CP-SAT), lexikographisch in drei Stufen:
A) Verluste (nicht teilnehmbare Konferenzen) minimieren,
B) Slotzahl minimieren,
C) Leerlauf (Luecken) der Teilnehmer minimieren.
"""
from __future__ import annotations

import time

from ortools.sat.python import cp_model

from .cancel import CancelToken
from .model import Problem, Schedule, evaluate
from .solver_heur import STOPPED, check_capacity, dsatur, greedy_slots, loss_weights


def solve_cpsat(
    problem: Problem,
    max_slots: int | None = None,
    objective: str = "teilnehmer",
    time_limit: float = 180.0,
    workers: int = 0,
    max_parallel: int | None = None,
    cancel: CancelToken | None = None,
) -> Schedule:
    events = sorted(problem.events)
    if not events:
        return evaluate(problem, [], "leer")
    check_capacity(len(events), max_slots, max_parallel)
    coloring = dsatur(problem.conflict_graph(), max_parallel)
    ub = max(coloring.values()) + 1
    n_slots = ub if max_slots is None else min(max_slots, ub)
    parts = [(sorted(evs)) for evs in problem.participants.values()]
    w_unhappy, w_missed = loss_weights(problem, objective)

    m = cp_model.CpModel()
    x = {(e, s): m.new_bool_var(f"x_{e}_{s}") for e in events for s in range(n_slots)}
    for e in events:
        m.add_exactly_one(x[e, s] for s in range(n_slots))
    used = [m.new_bool_var(f"used_{s}") for s in range(n_slots)]
    for s in range(n_slots):
        if max_parallel is not None:
            m.add(sum(x[e, s] for e in events) <= max_parallel)
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

    def initial_plan() -> dict:
        """Gueltiger Startplan; sichert, dass nie 'kein Plan' herauskommt."""
        if n_slots == ub:
            slot_of = coloring  # konfliktfrei
        else:
            groups = [g for g in greedy_slots(problem, n_slots, max_parallel) if g]
            slot_of = {e: i for i, g in enumerate(groups) for e in g}  # Slots ohne Luecke
        return {(e, s): int(slot_of[e] == s) for e in events for s in range(n_slots)}

    best = initial_plan()

    def run(expr, share: float) -> dict | None:
        """Minimiert expr, fixiert das Ergebnis als Schranke, liefert die Belegung.

        Startet vom bisher besten Plan. Gibt None zurueck, wenn die Stufe keine Loesung
        mehr findet (Zeitanteil aufgebraucht) oder der Benutzer stoppt; dann gilt der
        bisher beste Plan.
        """
        nonlocal all_optimal
        if cancel:
            cancel.raise_if_cancelled()
            if cancel.stop_requested:
                return None
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = max(1.0, (deadline - time.monotonic()) * share)
        solver.parameters.num_workers = workers
        m.clear_hints()
        for key, value in best.items():
            m.add_hint(x[key], value)
        m.minimize(expr)
        if cancel:
            cancel.attach(solver)
        try:
            status = solver.solve(m)
        finally:
            if cancel:
                cancel.detach()
        if cancel:
            cancel.raise_if_cancelled()
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            if not (cancel and cancel.stop_requested):
                all_optimal = False
            return None
        all_optimal &= status == cp_model.OPTIMAL
        m.add(expr <= int(round(solver.objective_value)))
        return {k: solver.value(v) for k, v in x.items()}

    stages = [(slots_used, 0.5), (gaps, 1.0)]
    if n_slots < ub:
        stages.insert(0, (loss, 0.4))
    else:
        m.add(loss <= 0)
    completed = True
    for expr, share in stages:
        solution = run(expr, share)
        if solution is None:
            completed = False
            break
        best = solution

    slots: list[list[str]] = [[] for _ in range(n_slots)]
    for (e, s), val in best.items():
        if val:
            slots[s].append(e)
    if cancel and cancel.stop_requested and not (completed and all_optimal):
        status = STOPPED
    elif completed and all_optimal:
        status = "optimal"
    else:
        status = "beste gefundene Loesung (Zeitlimit)"
    return evaluate(problem, slots, status)
