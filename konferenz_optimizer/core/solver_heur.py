"""Loesungsverfahren ohne externe Abhaengigkeiten (DSATUR + Simulated Annealing)."""
from __future__ import annotations

import math
import random
import time

from .model import Problem, Schedule, evaluate

OBJECTIVES = ("teilnehmer", "verpasst")


def dsatur(graph: dict[str, set[str]], capacity: int | None = None) -> dict[str, int]:
    """Greedy-Faerbung; liefert Ereignis -> Slot (obere Schranke der Slotzahl).

    Mit `capacity` nimmt kein Slot mehr als so viele Ereignisse auf.
    """
    color: dict[str, int] = {}
    neighbor_colors: dict[str, set[int]] = {v: set() for v in graph}
    load: dict[int, int] = {}
    while len(color) < len(graph):
        v = max(
            (u for u in graph if u not in color),
            key=lambda u: (len(neighbor_colors[u]), len(graph[u]), u),
        )
        c = 0
        while c in neighbor_colors[v] or (capacity is not None and load.get(c, 0) >= capacity):
            c += 1
        color[v] = c
        load[c] = load.get(c, 0) + 1
        for w in graph[v]:
            neighbor_colors[w].add(c)
    return color


def check_capacity(n_events: int, max_slots: int | None, max_parallel: int | None) -> None:
    if max_parallel is not None and max_parallel < 1:
        raise ValueError("Die Zahl gleichzeitiger Konferenzen muss mindestens 1 sein.")
    if max_slots is not None and max_parallel is not None and max_slots * max_parallel < n_events:
        raise ValueError(
            f"{n_events} Konferenzen passen nicht in {max_slots} Slots mit höchstens "
            f"{max_parallel} gleichzeitigen Konferenzen (Platz für {max_slots * max_parallel}). "
            "Bitte Obergrenzen erhöhen."
        )


def loss_weights(problem: Problem, objective: str) -> tuple[int, int]:
    """(Gewicht je unzufriedenem Teilnehmer, Gewicht je verpasstem Termin)."""
    if objective == "verpasst":
        return 1, len(problem.participants) + 1
    return len(problem.events) * len(problem.participants) + 1, 1


def solve_heuristic(
    problem: Problem,
    max_slots: int | None = None,
    objective: str = "teilnehmer",
    time_limit: float = 10.0,
    seed: int = 0,
    max_parallel: int | None = None,
) -> Schedule:
    events = sorted(problem.events)
    if not events:
        return evaluate(problem, [], "leer")
    check_capacity(len(events), max_slots, max_parallel)
    graph = problem.conflict_graph()
    coloring = dsatur(graph, max_parallel)
    n_colors = max(coloring.values()) + 1
    n_slots = n_colors if max_slots is None else min(max_slots, n_colors)
    cap = max_parallel if max_parallel is not None else len(events)
    idx = {e: i for i, e in enumerate(events)}
    parts = [[idx[e] for e in evs] for evs in problem.participants.values()]
    w_unhappy, w_missed = loss_weights(problem, objective)
    w_slots = len(parts) * n_slots + 1
    w_loss = (len(events) + 1) * w_slots * max(w_unhappy, w_missed) + 1

    def cost(assign: list[int]) -> int:
        unhappy = missed = gaps = 0
        for p in parts:
            used = {assign[i] for i in p}
            m = len(p) - len(used)
            if m:
                unhappy += 1
                missed += m
            gaps += max(used) - min(used) + 1 - len(used)
        return (unhappy * w_unhappy + missed * w_missed) * w_loss + len(set(assign)) * w_slots + gaps

    rng = random.Random(seed)
    load = [0] * n_slots
    if n_slots == n_colors:
        assign = [coloring[e] for e in events]
        for s in assign:
            load[s] += 1
    else:
        assign = []
        for _ in events:
            s = rng.choice([s for s in range(n_slots) if load[s] < cap])
            assign.append(s)
            load[s] += 1
    cur = cost(assign)
    best, best_assign = cur, assign[:]
    temp = max(1.0, w_slots / 2)
    deadline = time.monotonic() + time_limit
    while time.monotonic() < deadline:
        a = rng.randrange(len(events))
        old = assign[a]
        if rng.random() < 0.5 and len(events) > 1:
            b = rng.randrange(len(events))
            assign[a], assign[b] = assign[b], assign[a]
            undo = (a, old, b, assign[a])
        else:
            target = rng.randrange(n_slots)
            if load[target] >= cap and target != old:
                continue
            assign[a] = target
            undo = (a, old, None, None)
        new = cost(assign)
        if new <= cur or rng.random() < math.exp((cur - new) / temp):
            cur = new
            if undo[2] is None:
                load[old] -= 1
                load[assign[a]] += 1
            if cur < best:
                best, best_assign = cur, assign[:]
        elif undo[2] is None:
            assign[a] = old
        else:
            assign[a], assign[undo[2]] = old, undo[3]
        temp = max(0.05, temp * 0.9995)
    slots: list[list[str]] = [[] for _ in range(n_slots)]
    for e, s in zip(events, best_assign):
        slots[s].append(e)
    return evaluate(problem, slots, "heuristisch (nicht als optimal bewiesen)")
