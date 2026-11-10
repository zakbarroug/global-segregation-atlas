"""Synthetic analytical examples and independent published-reference comparisons."""

import math

import numpy as np
import pandas as pd
import pytest

from src.statistics.indices import (
    InvalidDistribution,
    compute_metrics,
    dissimilarity,
    information_theory,
    interaction,
    rank_order_information_theory,
    validate_counts,
)


def test_perfectly_even_d_zero():
    assert dissimilarity([10, 20, 30], [20, 40, 60]) == pytest.approx(0)


def test_maximal_separation_d_one():
    assert dissimilarity([100, 0], [0, 100]) == pytest.approx(1)


def test_manual_d():
    # |30/40 - 10/40| + |10/40 - 30/40|, divided by two.
    assert dissimilarity([30, 10], [10, 30]) == pytest.approx(0.5)


def test_manual_isolation():
    # .75*.3 + .25*.1 = .25; middle households stay in denominator.
    assert interaction([30, 10], [30, 10], [100, 100]) == pytest.approx(0.25)


def test_manual_exposure():
    assert interaction([30, 10], [10, 30], [100, 100]) == pytest.approx(0.15)


def test_isolation_is_not_exposure_complement_with_middle_group():
    assert interaction([30, 10], [30, 10], [100, 100]) + interaction(
        [30, 10], [10, 30], [100, 100]
    ) == pytest.approx(0.4)


@pytest.mark.parametrize("factor", [0.5, 2, 10000])
def test_scale_invariance(factor):
    low, high = np.array([30, 10]), np.array([10, 30])
    assert dissimilarity(low * factor, high * factor) == pytest.approx(dissimilarity(low, high))
    assert information_theory(np.column_stack([low, high]) * factor) == pytest.approx(
        information_theory(np.column_stack([low, high]))
    )


def test_area_permutation():
    matrix = np.array([[10, 5, 7], [20, 8, 1], [4, 18, 6]])
    assert information_theory(matrix) == pytest.approx(information_theory(matrix[[2, 0, 1]]))
    assert dissimilarity(matrix[:, 0], matrix[:, 1]) == pytest.approx(
        dissimilarity(matrix[::-1, 0], matrix[::-1, 1])
    )


@pytest.mark.parametrize("low,high", [([0, 0], [5, 10]), ([5, 10], [0, 0]), ([0, 0], [0, 0])])
def test_zero_group_unavailable(low, high):
    assert dissimilarity(low, high) is None


def test_zero_low_interaction_unavailable():
    assert interaction([0, 0], [1, 2], [5, 5]) is None


def test_zero_high_exposure_valid_zero():
    assert interaction([2, 3], [0, 0], [5, 5]) == 0


def test_empty_unit_handling():
    assert dissimilarity([10, 0, 0], [0, 10, 0]) == 1
    assert interaction([10, 0, 0], [10, 0, 0], [10, 10, 0]) == 1
    assert information_theory([[10, 0], [0, 10], [0, 0]]) == 1


@pytest.mark.parametrize(
    "data",
    [
        [],
        [[1, 2]],
        [[0, 0], [0, 0]],
        [[1, -1], [2, 3]],
        [[1, None], [2, 3]],
        [[1, float("inf")], [2, 3]],
        [[1, 2], [3]],
        [[1, 0], [0, 0]],
    ],
)
def test_invalid_distribution_rejected(data):
    with pytest.raises(InvalidDistribution):
        validate_counts(data)


def test_inconsistent_group_total_rejected():
    with pytest.raises(InvalidDistribution):
        interaction([5, 5], [8, 8], [6, 6])


def test_information_h_even():
    assert information_theory([[10, 20, 30], [20, 40, 60]]) == pytest.approx(0, abs=1e-12)


def test_information_h_separation():
    assert information_theory([[10, 0, 0], [0, 10, 0], [0, 0, 10]]) == pytest.approx(1)


def test_information_h_manual_binary():
    expected = 1 - (-0.75 * math.log(0.75) - 0.25 * math.log(0.25)) / math.log(2)
    assert information_theory([[75, 25], [25, 75]]) == pytest.approx(expected)


def test_single_city_group_h_undefined():
    assert information_theory([[5, 0], [10, 0]]) is None


def test_coarse_zoning_warning_and_fixed_thresholds():
    matrix = np.ones((3, 16))
    metrics = compute_metrics(matrix, ["dissimilarity", "isolation"])
    assert any("coarse" in warning for warning in metrics[0].warnings)
    assert metrics[1].value == pytest.approx(6 / 16)


def test_aggregation_can_hide_segregation():
    fine = [[100, 0], [0, 100], [100, 0], [0, 100]]
    coarse = [[100, 100], [100, 100]]
    assert information_theory(fine) == 1 and information_theory(coarse) == 0


def test_b19001_shape_required():
    with pytest.raises(InvalidDistribution):
        compute_metrics([[1, 2], [3, 4]])


def test_pysal_d_and_h_reference():
    from segregation.multigroup import MultiInfoTheory
    from segregation.singlegroup import Dissim

    frame = pd.DataFrame({"a": [30, 10, 20], "b": [5, 30, 20], "c": [5, 5, 20]})
    frame["pair"] = frame.a + frame.b
    assert dissimilarity(frame.a, frame.b) == pytest.approx(Dissim(frame, "a", "pair").statistic)
    assert information_theory(frame[["a", "b", "c"]]) == pytest.approx(
        MultiInfoTheory(frame, ["a", "b", "c"]).statistic
    )


def test_rank_order_even_closed_form():
    value, reason = rank_order_information_theory(np.tile(np.arange(1, 17), (4, 1)))
    assert reason is None
    assert value == pytest.approx(0, abs=1e-10)


def test_rank_order_full_separation_closed_form():
    value, reason = rank_order_information_theory(np.eye(16) * 100)
    assert reason is None
    assert value == pytest.approx(1, abs=1e-8)


def test_rank_order_not_enough_distinct_cutpoints():
    value, reason = rank_order_information_theory([[1, 2, 0], [2, 1, 0]])
    assert value is None and "cutpoints" in reason


@pytest.mark.parametrize("mode", ["warn", "raise", "ignore"])
def test_rank_order_independent_of_caller_numpy_error_mode(mode):
    with np.errstate(all=mode):
        before = np.geterr().copy()
        even, reason = rank_order_information_theory(np.tile(np.arange(1, 17), (4, 1)))
        separated, other_reason = rank_order_information_theory(np.eye(16) * 100)
        assert reason is None and other_reason is None
        assert even == pytest.approx(0, abs=1e-10)
        assert separated == pytest.approx(1, abs=1e-8)
        assert np.geterr() == before
