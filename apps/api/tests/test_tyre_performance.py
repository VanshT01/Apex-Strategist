import numpy as np
import pytest
from app.simulation.distributions import sample_tyre_curve_uncertainty
from app.simulation.tyres import (
    advance_tyre_health,
    is_automatic_tyre_failure,
    tyre_pace_loss_seconds,
    tyre_state,
    tyre_wear_pct,
)


def test_health_and_wear_convention() -> None:
    assert tyre_wear_pct(100) == 0
    assert tyre_wear_pct(60) == 40
    assert tyre_wear_pct(0) == 100
    assert tyre_wear_pct(120) == 0
    assert tyre_wear_pct(-20) == 100


def test_pace_curve_is_strict_monotonic_and_accelerates_at_cliff() -> None:
    health = [100, 90, 80, 70, 60, 50, 40]
    loss = [tyre_pace_loss_seconds(value) for value in health]

    assert loss[0] == pytest.approx(0)
    assert all(right > left for left, right in zip(loss, loss[1:], strict=False))
    assert tyre_pace_loss_seconds(60) > 4.0
    # Equal 10-point health drops cost increasingly more once the 50%-wear cliff begins.
    assert loss[-1] - loss[-2] > loss[-2] - loss[-3]


@pytest.mark.parametrize(
    ("health", "failed"),
    [(5.0, False), (4.999, True), (4.0, True), (0.0, True)],
)
def test_automatic_failure_threshold_is_strict(health: float, failed: bool) -> None:
    assert is_automatic_tyre_failure(health) is failed


def test_crossing_failure_threshold_during_lap() -> None:
    transition = advance_tyre_health(5.4, 0.6)

    assert transition.end_health_pct == pytest.approx(4.8)
    assert transition.failed is True
    assert tyre_state(transition.end_health_pct) == "FAILED"


def test_seeded_tyre_curve_samples_are_reproducible_and_bounded() -> None:
    first_scale, first_cliff = sample_tyre_curve_uncertainty(np.random.default_rng(42), 1_000)
    second_scale, second_cliff = sample_tyre_curve_uncertainty(np.random.default_rng(42), 1_000)

    np.testing.assert_array_equal(first_scale, second_scale)
    np.testing.assert_array_equal(first_cliff, second_cliff)
    assert np.all((first_scale >= 0.9) & (first_scale <= 1.1))
    assert np.all((first_cliff >= 45.0) & (first_cliff <= 55.0))
