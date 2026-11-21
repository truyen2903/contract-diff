import random

import pytest

from app.engines.assignment import solve_assignment
from app.engines.alignment_budget import AlignmentBudget, AlignmentBudgetError
from experiments.reference_labels import assignment_objective, assignment_oracle


@pytest.mark.parametrize("matrix,alpha,expected", [
    ([[.95, .65], [.65, .39]], 0, [(0, 1), (1, 0)]),
    ([[1, .51], [.51, 0]], 0, [(0, 1), (1, 0)]),
    ([[1, .51], [.51, 0]], .2, [(0, 0)]),
    ([[.95, .41], [.41, 0]], 0, [(0, 0)]),
    ([[.5, .5000001], [.5, .5]], 0, [(0, 1), (1, 0)]),
    ([], 0, []), ([[], []], 0, []), ([[None, .39]], 0, []),
    ([[.8, .8, .8], [.8, .8, .8]], 0, [(0, 0), (1, 2)]),
])
def test_assignment(matrix, alpha, expected):
    assert solve_assignment(matrix, .4, alpha) == expected


def test_exhaustive_reference_and_determinism():
    rng = random.Random(2709)
    for _ in range(500):
        m, n = rng.randint(1, 5), rng.randint(1, 5)
        matrix = [rng.choices([None, .4, .5, .5000001, .8, 1.0], k=n) for _ in range(m)]
        alpha = rng.choice([0, .2])
        actual = solve_assignment(matrix, .4, alpha)
        expected = assignment_oracle(matrix, .4, alpha)
        score, tie = assignment_objective(matrix, actual, alpha)
        best_score, best_tie = assignment_objective(matrix, expected, alpha)
        assert score == best_score
        assert tie == best_tie
        assert solve_assignment(matrix, .4, alpha) == actual


def test_guard_and_cumulative_components():
    with pytest.raises(ValueError):
        solve_assignment([[.8]], .4, .4)
    with pytest.raises(ValueError):
        solve_assignment([[.8], []])
    budget = AlignmentBudget(max_cubic=1)
    assert solve_assignment([[.8]], budget=budget) == [(0, 0)]
    with pytest.raises(AlignmentBudgetError):
        solve_assignment([[.8]], budget=budget)
    with pytest.raises(AlignmentBudgetError):
        solve_assignment([[1, 1]], budget=AlignmentBudget(max_dimension=1))


def test_repeated_bodies_uncross_even_when_displacement_is_tied():
    rng = random.Random(300)
    for _ in range(300):
        i, j = sorted(rng.sample(range(6), 2))
        k, l = sorted(rng.sample(range(6, 12), 2))
        result = solve_assignment([[.8, .8], [.8, .8]], old_pos=[i, j], new_pos=[k, l],
                                  scope=(12, 12), old_keys=["a", "a"], new_keys=["a", "a"])
        assert result == [(0, 0), (1, 1)]


@pytest.mark.parametrize("extra", [
    {"scope": (1, 1), "old_pos": [1]},
    {"scope": (2, 2), "old_pos": [-1]},
    {"old_keys": ["a"]},
])
def test_invalid_original_positions_cannot_break_objective(extra):
    with pytest.raises(ValueError):
        solve_assignment([[.5]], **extra)
