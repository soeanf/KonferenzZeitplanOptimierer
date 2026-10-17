import random
import threading
import time

import pytest

from konferenz_optimizer.core.cancel import Cancelled, CancelToken
from konferenz_optimizer.core.model import Problem
from konferenz_optimizer.core.solver_cpsat import solve_cpsat
from konferenz_optimizer.core.solver_heur import STOPPED, solve_heuristic


def hard_problem() -> Problem:
    rng = random.Random(3)
    classes = [f"{g}{c}" for g in range(5, 11) for c in "abc"]
    events: dict[str, set[str]] = {c: set() for c in classes}
    for i in range(30):
        for c in rng.sample(classes, rng.choice([2, 3, 4, 5, 9])):
            events[c].add(f"L{i}")
    return Problem({e: frozenset(m) for e, m in events.items()})


def test_cancel_before_start():
    token = CancelToken()
    token.cancel()
    with pytest.raises(Cancelled):
        solve_cpsat(hard_problem(), time_limit=60, cancel=token)
    with pytest.raises(Cancelled):
        solve_heuristic(hard_problem(), max_slots=4, time_limit=60, cancel=token)


@pytest.mark.parametrize("delay", [0.0, 0.3, 1.5])
def test_cancel_stops_cpsat_quickly(delay):
    token = CancelToken()
    threading.Timer(delay, token.cancel).start()
    start = time.monotonic()
    with pytest.raises(Cancelled):
        solve_cpsat(hard_problem(), max_slots=8, max_parallel=3, time_limit=120, cancel=token)
    assert time.monotonic() - start < 15


def test_cancel_stops_heuristic_quickly():
    token = CancelToken()
    threading.Timer(0.3, token.cancel).start()
    start = time.monotonic()
    with pytest.raises(Cancelled):
        solve_heuristic(hard_problem(), max_slots=8, max_parallel=3, time_limit=120, cancel=token)
    assert time.monotonic() - start < 5


def test_no_cancel_still_works():
    token = CancelToken()
    schedule = solve_cpsat(hard_problem(), max_slots=8, max_parallel=3, time_limit=3, cancel=token)
    assert schedule.metrics.num_slots <= 8


def assert_valid_plan(schedule, problem, max_slots, max_parallel):
    assert sorted(e for s in schedule.slots for e in s) == sorted(problem.events)
    assert schedule.metrics.num_slots <= max_slots
    assert all(len(s) <= max_parallel for s in schedule.slots)


@pytest.mark.parametrize("delay", [0.0, 0.3, 1.5])
def test_stop_returns_valid_best_plan_cpsat(delay):
    problem = hard_problem()
    token = CancelToken()
    threading.Timer(delay, token.stop).start()
    start = time.monotonic()
    schedule = solve_cpsat(problem, max_slots=8, max_parallel=3, time_limit=120, cancel=token)
    assert time.monotonic() - start < 15
    assert STOPPED in schedule.status or schedule.status == "optimal"
    assert_valid_plan(schedule, problem, 8, 3)


def test_stop_before_start_uses_fallback_plan():
    problem = hard_problem()
    token = CancelToken()
    token.stop()
    schedule = solve_cpsat(problem, max_slots=8, max_parallel=3, time_limit=60, cancel=token)
    assert schedule.status == STOPPED
    assert_valid_plan(schedule, problem, 8, 3)


def test_stop_returns_valid_best_plan_heuristic():
    problem = hard_problem()
    token = CancelToken()
    threading.Timer(0.3, token.stop).start()
    start = time.monotonic()
    schedule = solve_heuristic(problem, max_slots=8, max_parallel=3, time_limit=120, cancel=token)
    assert time.monotonic() - start < 5
    assert schedule.status == STOPPED
    assert_valid_plan(schedule, problem, 8, 3)


def test_stop_after_finish_keeps_optimal():
    p = Problem({"a": frozenset("x"), "b": frozenset("y")})
    token = CancelToken()
    schedule = solve_cpsat(p, time_limit=5, cancel=token)
    token.stop()
    assert schedule.status == "optimal"
