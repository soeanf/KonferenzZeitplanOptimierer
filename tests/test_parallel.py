import random

import pytest

from konferenz_optimizer.adapters.teacher_subjects import PRESETS, parse_rows, parse_teachers
from konferenz_optimizer.cli import main
from konferenz_optimizer.core.solver_cpsat import solve_cpsat
from konferenz_optimizer.core.solver_heur import check_capacity, dsatur, solve_heuristic
from tests.test_basic import random_problem


def test_parse_many_columns():
    row = ["Lehrer"] + [f"{c}" for c in ("5a", "5b", "6a", "6b", "7a", "7b", "8a", "8b")]
    teachers = parse_teachers([row, ["Zweiter", "5a"]])
    assert len(teachers["Lehrer"]) == 8
    assert teachers["Zweiter"] == ["5a"]


def test_presets_labels():
    p = parse_rows([["A", "5a", "5b"]], PRESETS["klasse"])
    assert p.labels.event == "Gruppe" and p.labels.event_plural == "Gruppen"
    assert "kurs" not in PRESETS
    assert parse_rows([["A", "x"]]).labels.event == "Fach"


def capacity_ok(schedule, cap):
    return all(len(s) <= cap for s in schedule.slots)


@pytest.mark.parametrize("seed", range(4))
@pytest.mark.parametrize("cap", [1, 2, 3])
def test_max_parallel_respected(seed, cap):
    p = random_problem(random.Random(seed))
    c = solve_cpsat(p, max_parallel=cap, time_limit=20)
    h = solve_heuristic(p, max_parallel=cap, time_limit=1)
    assert capacity_ok(c, cap) and capacity_ok(h, cap)
    assert c.metrics.missed == 0
    assert sorted(e for s in c.slots for e in s) == sorted(p.events)


@pytest.mark.parametrize("seed", range(3))
def test_max_parallel_with_slot_limit(seed):
    p = random_problem(random.Random(seed))
    cap = 2
    slots = -(-len(p.events) // cap)  # knapp: jeder Slot muss voll belegt werden
    c = solve_cpsat(p, max_slots=slots, max_parallel=cap, time_limit=20)
    h = solve_heuristic(p, max_slots=slots, max_parallel=cap, time_limit=1)
    assert c.metrics.num_slots <= slots and capacity_ok(c, cap)
    assert h.metrics.num_slots <= slots and capacity_ok(h, cap)
    assert (c.metrics.unhappy, c.metrics.missed) <= (h.metrics.unhappy, h.metrics.missed)


def test_dsatur_capacity():
    graph = {e: set() for e in "abcdef"}
    colors = dsatur(graph, 2)
    assert max(colors.values()) + 1 == 3


def test_capacity_infeasible_raises():
    with pytest.raises(ValueError):
        check_capacity(10, 3, 3)
    p = random_problem(random.Random(0))
    with pytest.raises(ValueError):
        solve_cpsat(p, max_slots=1, max_parallel=1)
    with pytest.raises(ValueError):
        solve_heuristic(p, max_slots=1, max_parallel=1)


def test_cli_max_parallel(tmp_path, capsys):
    csv_file = tmp_path / "k.csv"
    csv_file.write_text("Name,K1,K2,K3\nA,5a,5b,5c\nB,5a,6a\nC,6a,6b,6c\n", encoding="utf-8")
    assert main([str(csv_file), "--art", "klasse", "--max-parallel", "1", "--time-limit", "5"]) == 0
    out = capsys.readouterr().out
    assert out.count("Slot ") >= 6 and "Slot 6" in out
    assert main([str(csv_file), "--max-slots", "1", "--max-parallel", "1"]) == 2
