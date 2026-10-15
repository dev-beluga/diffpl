import numpy as np
import polars as pl
import pytest

from diffpl.features.build import FEATURES
from diffpl.models.evaluate import calibration, log_loss, rps
from diffpl.models.two_part import N_BINS, TwoPartModel


def test_rps_is_zero_for_a_perfect_forecast_and_grows_with_distance() -> None:
    perfect = np.eye(N_BINS)[[2]]
    assert rps(perfect, np.array([2]))[0] == 0
    near = rps(np.eye(N_BINS)[[3]], np.array([2]))[0]
    far = rps(np.eye(N_BINS)[[9]], np.array([2]))[0]
    assert 0 < near < far


def test_log_loss_of_uniform() -> None:
    uniform = np.full((1, N_BINS), 1 / N_BINS)
    assert log_loss(uniform, np.array([0]))[0] == pytest.approx(np.log(N_BINS))


def test_calibration_buckets() -> None:
    rng = np.random.default_rng(0)
    p = rng.random(5000)
    outcome = rng.random(5000) < p
    cal = calibration(p, outcome)
    assert cal.height == 10
    assert np.abs(cal["predicted"] - cal["observed"]).max() < 0.06


def synthetic(n: int, seed: int) -> pl.DataFrame:
    """Players whose recent minutes predict whether they play and score."""
    rng = np.random.default_rng(seed)
    data = {c: rng.random(n) for c in FEATURES}
    starter = rng.random(n) < 0.5
    data["minutes_last3"] = np.where(starter, 85.0, 5.0)
    minutes = np.where(starter, 90, np.where(rng.random(n) < 0.3, 20, 0))
    points = np.where(minutes >= 60, rng.integers(2, 10, n), np.where(minutes > 0, 1, 0))
    return pl.DataFrame({**data, "position": ["MID"] * n, "minutes": minutes, "points": points})


def test_two_part_learns_minutes_and_returns_valid_distributions() -> None:
    model = TwoPartModel(max_rounds=60).fit(synthetic(3000, 1), synthetic(800, 2))
    test = synthetic(500, 3)
    dist = model.predict_dist(test)
    assert dist.shape == (500, N_BINS)
    assert np.allclose(dist.sum(axis=1), 1)
    exp = model.expected_points(dist)
    starters = test["minutes_last3"].to_numpy() > 50
    assert exp[starters].mean() > exp[~starters].mean() + 2
