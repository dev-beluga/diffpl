"""Scores for points distributions (ADR-0006).

- RPS: ranked probability score over points bins, the discrete form of CRPS. Lower is better.
- Log loss: minus the log probability of the observed bin. Lower is better.
- MAE: of expected points. Compared against simple baselines.
- Calibration: predicted vs observed frequency, by predicted-probability decile.
"""

from __future__ import annotations

import numpy as np
import polars as pl

EPS = 1e-12


def rps(dist: np.ndarray, observed_bin: np.ndarray) -> np.ndarray:
    cdf = np.cumsum(dist, axis=1)
    obs = (np.arange(dist.shape[1])[None, :] >= observed_bin[:, None]).astype(float)
    return np.asarray(((cdf - obs) ** 2).sum(axis=1))


def log_loss(dist: np.ndarray, observed_bin: np.ndarray) -> np.ndarray:
    return np.asarray(-np.log(dist[np.arange(len(dist)), observed_bin] + EPS))


def climatology(
    train_bins: np.ndarray, train_pos: np.ndarray, pos: np.ndarray, n_bins: int
) -> np.ndarray:
    """Baseline distribution: training points-bin frequencies for the player's position."""
    out = np.zeros((len(pos), n_bins))
    for p in np.unique(pos):
        freq = np.bincount(train_bins[train_pos == p], minlength=n_bins).astype(float)
        out[pos == p] = freq / freq.sum()
    return out


def calibration(prob: np.ndarray, outcome: np.ndarray, n: int = 10) -> pl.DataFrame:
    """Mean predicted vs observed rate per predicted-probability decile."""
    edges = np.quantile(prob, np.linspace(0, 1, n + 1))
    idx = np.clip(np.searchsorted(edges, prob, side="right") - 1, 0, n - 1)
    df = pl.DataFrame({"bucket": idx, "predicted": prob, "observed": outcome.astype(float)})
    return (
        df.group_by("bucket")
        .agg(pl.col("predicted").mean(), pl.col("observed").mean(), pl.len())
        .sort("bucket")
    )


def summary(
    position: np.ndarray,
    observed_bin: np.ndarray,
    points: np.ndarray,
    models: dict[str, tuple[np.ndarray, np.ndarray]],
) -> pl.DataFrame:
    """Per model and position: mean RPS, log loss and MAE. `models` maps name to
    (distribution or empty array, expected points)."""
    rows = []
    for name, (dist, exp) in models.items():
        for pos in ["ALL", *sorted(set(position.tolist()))]:
            m = np.ones(len(points), bool) if pos == "ALL" else position == pos
            row: dict[str, object] = {"model": name, "position": pos, "n": int(m.sum())}
            row["mae"] = float(np.abs(exp[m] - points[m]).mean())
            if dist.size:
                row["rps"] = float(rps(dist[m], observed_bin[m]).mean())
                row["log_loss"] = float(log_loss(dist[m], observed_bin[m]).mean())
            rows.append(row)
    return pl.DataFrame(rows)
