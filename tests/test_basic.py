import random

import pytest

from konferenz_optimizer.adapters.teacher_subjects import parse_rows
from konferenz_optimizer.core.model import Problem, evaluate
from konferenz_optimizer.core.solver_cpsat import solve_cpsat
from konferenz_optimizer.core.solver_heur import solve_heuristic


def test_parse_inverts_and_normalizes():
    p = parse_rows([["Name", "F1", "F2"], ["A", "Mathe", " physik "], ["B", "mathe", "", ""]])
    assert p.events == {"Mathe": frozenset({"A", "B"}), "physik": frozenset({"A"})}


def test_gaps_and_missed():
    p = Problem({"a": frozenset("x"), "b": frozenset("x"), "c": frozenset("x"), "d": frozenset("y")})
    s = evaluate(p, [["a", "d"], ["b"], ["c"]])
    assert s.metrics.gaps == 0 and s.metrics.missed == 0
    s = evaluate(p, [["a", "b"], ["d"], ["c"]])
    assert s.metrics.missed == 1 and s.metrics.unhappy == 1 and s.metrics.gaps == 1


def random_problem(rng, n_events=8, n_people=14):
    events = {f"E{i}": set() for i in range(n_events)}
    for k in range(n_people):
        for e in rng.sample(sorted(events), rng.randint(1, 4)):
            events[e].add(f"P{k}")
    return Problem({e: frozenset(m) for e, m in events.items() if m})


@pytest.mark.parametrize("seed", range(4))
def test_cpsat_no_conflicts_without_limit(seed):
    p = random_problem(random.Random(seed))
    s = solve_cpsat(p, time_limit=20)
    assert s.metrics.missed == 0
    assert sorted(e for sl in s.slots for e in sl) == sorted(p.events)


@pytest.mark.parametrize("seed", range(4))
def test_cpsat_with_limit_not_worse_than_heuristic(seed):
    p = random_problem(random.Random(seed))
    h = solve_heuristic(p, max_slots=2, time_limit=1)
    c = solve_cpsat(p, max_slots=2, time_limit=20)
    assert c.metrics.num_slots <= 2
    assert (c.metrics.unhappy, c.metrics.missed) <= (h.metrics.unhappy, h.metrics.missed)


def test_heuristic_never_exceeds_max_slots():
    p = random_problem(random.Random(9))
    assert solve_heuristic(p, max_slots=2, time_limit=1).metrics.num_slots <= 2
