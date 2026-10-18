from pathlib import Path

import numpy as np
import polars as pl
import pytest

from diffpl.features.build import FEATURES
from diffpl.models import calibration
from diffpl.models.evaluate import calibration as reliability
from diffpl.models.evaluate import log_loss, rps
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
    cal = reliability(p, outcome)
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


def test_randomized_pit_is_uniform_for_a_calibrated_forecast() -> None:
    rng = np.random.default_rng(0)
    dist = rng.dirichlet(np.ones(N_BINS), size=20000)
    observed = np.array([rng.choice(N_BINS, p=d) for d in dist])
    pit = calibration.randomized_pit(dist, observed, np.random.default_rng(1))
    counts, _ = np.histogram(pit, bins=10, range=(0, 1))
    assert np.abs(counts / len(pit) - 0.1).max() < 0.01


def test_overconfident_forecast_undercovers_and_shows_u_shaped_pit() -> None:
    rng = np.random.default_rng(0)
    observed = rng.integers(0, N_BINS, 5000)
    narrow = np.zeros((5000, N_BINS))
    narrow[:, 7:9] = 0.5
    tables = calibration.report(
        narrow, observed, np.full(5000, 0.5), rng.random(5000) < 0.5, np.array(["MID"] * 5000), 0
    )
    cov = tables["coverage"].filter(pl.col("position") == "MID")
    assert (cov["coverage"] < cov["level"] - 0.2).all()
    pit = tables["pit"].filter(pl.col("position") == "MID")["density"].to_numpy()
    assert pit[0] > 2 and pit[-1] > 2 and pit[4] < 1
    assert set(tables["ece"]["event"]) == {"p60", "pts_ge1", "pts_ge2", "pts_ge6", "pts_ge10"}


def test_plot_writes_one_png_per_position(tmp_path) -> None:
    rng = np.random.default_rng(0)
    dist = rng.dirichlet(np.ones(N_BINS), size=400)
    pos = np.array(["DEF", "MID"] * 200)
    tables = calibration.report(
        dist, rng.integers(0, N_BINS, 400), rng.random(400), rng.random(400) < 0.5, pos, 0
    )
    paths = calibration.plot(tables, tmp_path)
    assert sorted(p.name for p in paths) == [
        "calibration_ALL.png",
        "calibration_DEF.png",
        "calibration_MID.png",
    ]


def test_two_part_save_load_round_trip(tmp_path: Path) -> None:
    model = TwoPartModel(max_rounds=20).fit(synthetic(1500, 1), synthetic(400, 2))
    model.save(tmp_path / "model")
    loaded = TwoPartModel.load(tmp_path / "model")
    test = synthetic(200, 3)
    assert np.allclose(model.predict_dist(test), loaded.predict_dist(test))
    assert np.allclose(model.bin_values, loaded.bin_values)  # type: ignore[arg-type]
