"""Calibration report for points distributions (ADR-0006).

- Reliability: predicted vs observed rate for threshold events (P(60+ minutes), P(points >= k)),
  per position, with expected calibration error (ECE).
- Randomized PIT: for a calibrated discrete forecast, u = F(y-1) + v * p(y) with v ~ U(0, 1)
  is uniform on [0, 1]. A U-shaped histogram means too narrow, a hump means too wide.
- Coverage: share of outcomes inside the central interval at each level, read off the same
  PIT values, so discrete bins do not inflate it. Calibrated means coverage == level.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import polars as pl

from diffpl.models.evaluate import calibration

# Points thresholds on the bin index (bin 0 holds <= 0 points).
THRESHOLDS = (1, 2, 6, 10)
LEVELS = (0.5, 0.8)
PIT_BINS = 10


def exceedance(dist: np.ndarray, k: int) -> np.ndarray:
    """P(points bin >= k) per row."""
    return np.asarray(dist[:, k:].sum(axis=1))


def ece(table: pl.DataFrame) -> float:
    """Count-weighted mean |predicted - observed| over reliability buckets."""
    w = table["len"].to_numpy()
    gap = np.abs(table["predicted"].to_numpy() - table["observed"].to_numpy())
    return float((w * gap).sum() / w.sum())


def randomized_pit(
    dist: np.ndarray, observed_bin: np.ndarray, rng: np.random.Generator
) -> np.ndarray:
    rows = np.arange(len(dist))
    below = np.cumsum(dist, axis=1)[rows, observed_bin] - dist[rows, observed_bin]
    return np.asarray(below + rng.random(len(dist)) * dist[rows, observed_bin])


def report(
    dist: np.ndarray,
    observed_bin: np.ndarray,
    p60: np.ndarray,
    played_60: np.ndarray,
    position: np.ndarray,
    seed: int,
) -> dict[str, pl.DataFrame]:
    """Tables: reliability (long), ece, pit (histogram), coverage. All split by position."""
    pit = randomized_pit(dist, observed_bin, np.random.default_rng(seed))
    events = {"p60": (p60, played_60)}
    for k in THRESHOLDS:
        events[f"pts_ge{k}"] = (exceedance(dist, k), observed_bin >= k)

    rel, eces, hist, cov = [], [], [], []
    for pos in ["ALL", *sorted(set(position.tolist()))]:
        m = np.ones(len(position), bool) if pos == "ALL" else position == pos
        for name, (prob, outcome) in events.items():
            t = calibration(prob[m], outcome[m])
            rel.append(t.with_columns(event=pl.lit(name), position=pl.lit(pos)))
            eces.append({"event": name, "position": pos, "ece": ece(t)})
        counts, _ = np.histogram(pit[m], bins=PIT_BINS, range=(0, 1))
        hist.append(
            pl.DataFrame(
                {
                    "position": pos,
                    "bin": np.arange(PIT_BINS),
                    "density": counts * PIT_BINS / counts.sum(),
                }
            )
        )
        for level in LEVELS:
            inside = np.abs(pit[m] - 0.5) <= level / 2
            cov.append({"position": pos, "level": level, "coverage": float(inside.mean())})
    return {
        "reliability": pl.concat(rel),
        "ece": pl.DataFrame(eces),
        "pit": pl.concat(hist),
        "coverage": pl.DataFrame(cov),
    }


def plot(tables: dict[str, pl.DataFrame], out: Path) -> list[Path]:
    """Reliability and PIT PNGs, one figure per position."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    paths = []
    rel, pit = tables["reliability"], tables["pit"]
    for pos in rel["position"].unique(maintain_order=True):
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4.5))
        ax1.plot([0, 1], [0, 1], color="grey", lw=1, ls="--")
        for event in rel["event"].unique(maintain_order=True):
            t = rel.filter((pl.col("position") == pos) & (pl.col("event") == event))
            ax1.plot(t["predicted"], t["observed"], marker="o", ms=3, label=event)
        ax1.set(xlabel="predicted", ylabel="observed", title=f"Reliability, {pos}")
        ax1.legend(fontsize=8)
        h = pit.filter(pl.col("position") == pos)
        ax2.bar((h["bin"] + 0.5) / PIT_BINS, h["density"], width=1 / PIT_BINS, edgecolor="white")
        ax2.axhline(1, color="grey", lw=1, ls="--")
        ax2.set(xlabel="PIT", ylabel="density", title=f"Randomized PIT, {pos}")
        path = out / f"calibration_{pos}.png"
        fig.tight_layout()
        fig.savefig(path, dpi=110)
        plt.close(fig)
        paths.append(path)
    return paths
